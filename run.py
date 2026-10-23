"""GridFlex end-to-end run.

    python run.py                     # 60-day replay, 14 held-out days, all scenarios
    python run.py --quick             # 7 held-out days, no sweeps (fast)
    python run.py --seeds 20          # multi-seed confidence intervals
    python run.py --oracle            # add the perfect-foresight upper bound
    python run.py --sizing            # full sizing sweep
    python run.py --tou               # time-of-use sensitivity (unverified for LT-I)
    python run.py --refresh-weather   # re-fetch the cached real weather
"""
import argparse
import json
import os
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace

# single-threaded linear algebra: parallel seeds are the parallelism we want,
# otherwise every worker spawns a full BLAS pool and they fight over the cores
for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

import numpy as np

from gridflex.config import P, assumptions_table, config_dict
from gridflex.data import make_data
from gridflex.discom import console
from gridflex.economics import annual_cost, unit_economics
from gridflex.equity import archetype_metrics, rule_sensitivity
from gridflex.forecast import Forecaster, PersistenceForecaster
from gridflex.report import build_payload, make_dashboard, make_plots
from gridflex.simulate import metrics, run
from gridflex.sizing import (lifeline_availability, sweep, summary as sizing_summary,
                             with_reliability_value)
from gridflex.weather import build_cache, PROV_JSON

FULL = ["grid_only", "pv_batt_naive", "rule_reserve_tou", "mpc_no_dr",
        "mpc_persistence", "mpc_full", "oracle"]
SEED_MODES = ["grid_only", "pv_batt_naive", "rule_reserve_tou", "mpc_no_dr",
              "mpc_persistence", "mpc_full", "oracle"]


# what-if dimensions the deck promises: battery size, outage rate, cloudiness
# and e-rickshaw / 2W charging share. Each point is a real simulation.
WHATIF_BATS = (70, 100, 150)
WHATIF_OUTAGE = (0.75, 1.0, 1.25)
WHATIF_CLOUD = (1.0, 0.8)       # PV and irradiance scaled: clear vs cloudy year
WHATIF_EV = (1.0, 1.6)         # e-rickshaw / 2W charging energy share


def _whatif_group(args):
    """One (cloudiness, EV share) slice of the what-if grid, in a worker."""
    p, seed, w0, t1, cloud, ev_scale = args
    out = []
    for mult in WHATIF_OUTAGE:
        pm = replace(p, outage_h_per_day=p.outage_h_per_day * mult)
        dm = make_data(pm, seed=seed + 11)
        if cloud != 1.0:
            for col in ("pv", "ghi", "ghi_fc"):
                dm[col] = dm[col] * cloud
        if ev_scale != 1.0:
            dm["E_ev"] = dm["E_ev"] * ev_scale
        fcm = Forecaster(dm, pm.train_end(), pv_kwp=pm.pv_kwp, seed=seed)
        for b in WHATIF_BATS:
            pb = replace(pm, bat_kwh=float(b), bat_kw=40.0, resolve_every=8)
            rr = run(pb, dm, fcm, "mpc_full", w0, t1)
            mm = metrics(pb, rr)
            out.append(dict(bat_kwh=b, outage_mult=mult, pv_scale=cloud,
                            ev_scale=ev_scale,
                            outage_hours_per_day=mm["outage_hours_per_day"],
                            evening_availability_pct=mm["evening_availability_pct"],
                            lifeline_availability_pct=lifeline_availability(pb, rr),
                            bill_inr_per_hh_month=mm["bill_inr_per_hh_month"],
                            cost_per_hh_month_inr=annual_cost(pb)["per_hh_month_inr"]))
    return out


def _seed_job(args):
    """One independent stochastic seed: data draw + retrain + scenarios."""
    P0, seed, t0, t1, oracle, voltage = args
    p = replace(P0, enforce_voltage=voltage)
    df = make_data(p, seed=seed)
    fc = Forecaster(df, t0, pv_kwp=p.pv_kwp, seed=seed)
    out = {}
    for mode in SEED_MODES:
        if mode == "oracle" and not oracle:
            continue
        r = run(p, df, fc, mode, t0, t1, oracle=(mode == "oracle"))
        out[mode] = metrics(p, r)
    return seed, out


def aggregate(per_seed):
    """mean and 95 % CI across seeds."""
    out = {}
    modes = list(per_seed[0][1].keys())
    n = len(per_seed)
    for mode in modes:
        out[mode] = {}
        for key in per_seed[0][1][mode]:
            vals = [s[1][mode][key] for s in per_seed]
            if not all(isinstance(v, (int, float)) for v in vals):
                continue
            m = float(np.mean(vals))
            sd = float(np.std(vals, ddof=1)) if n > 1 else 0.0
            half = 1.96 * sd / np.sqrt(n) if n > 1 else 0.0
            out[mode][key] = dict(mean=m, lo=m - half, hi=m + half, sd=sd, n=n)
    return out


def ablation(M):
    """Gain of GridFlex over each baseline, and of each component."""
    base = "mpc_full"
    rows = []
    for name, m in M.items():
        if name == base:
            continue
        rows.append(dict(
            scenario=name,
            outage_gain_pct=_pct(m["outage_hours_per_day"], M[base]["outage_hours_per_day"]),
            availability_gain_pp=m["evening_availability_pct"] - M[base]["evening_availability_pct"],
            bill_delta_inr=m["bill_inr_per_hh_month"] - M[base]["bill_inr_per_hh_month"],
            unserved_delta_kwh=m["unserved_critical_kwh_per_day"]
            - M[base]["unserved_critical_kwh_per_day"],
        ))
    # component value: ML vs persistence, DR vs no DR
    comps = []
    if "mpc_persistence" in M and "mpc_full" in M:
        comps.append(dict(component="ML forecast vs persistence",
                          outage_delta=M["mpc_full"]["outage_hours_per_day"]
                          - M["mpc_persistence"]["outage_hours_per_day"],
                          bill_delta=M["mpc_full"]["bill_inr_per_hh_month"]
                          - M["mpc_persistence"]["bill_inr_per_hh_month"]))
    if "mpc_no_dr" in M and "mpc_full" in M:
        comps.append(dict(component="demand response",
                          outage_delta=M["mpc_full"]["outage_hours_per_day"]
                          - M["mpc_no_dr"]["outage_hours_per_day"],
                          bill_delta=M["mpc_full"]["bill_inr_per_hh_month"]
                          - M["mpc_no_dr"]["bill_inr_per_hh_month"]))
    if "pv_batt_naive" in M and "mpc_full" in M:
        comps.append(dict(component="full control vs rule",
                          outage_delta=M["mpc_full"]["outage_hours_per_day"]
                          - M["pv_batt_naive"]["outage_hours_per_day"],
                          bill_delta=M["mpc_full"]["bill_inr_per_hh_month"]
                          - M["pv_batt_naive"]["bill_inr_per_hh_month"]))
    return dict(vs_full=rows, components=comps)


def _pct(base, new):
    return float(100 * (base - new) / base) if base else 0.0


def write_docs(p, acc, ci):
    os.makedirs("docs", exist_ok=True)
    rows = assumptions_table(p)
    with open("docs/ASSUMPTIONS.md", "w", encoding="utf-8") as f:
        f.write("# GridFlex assumptions and sources\n\n")
        f.write("Every number a judge could question, its type (real / cited / assumption), "
                "source and plausible range. Generated from `gridflex/config.py`.\n\n")
        f.write("| parameter | value | unit | kind | source | range |\n|---|---|---|---|---|---|\n")
        for r in rows:
            f.write(f"| `{r['param']}` | {r['value']} | {r['unit']} | {r['kind']} | "
                    f"{r['source']} | {r['range']} |\n")
    prov = {}
    if os.path.exists(PROV_JSON):
        prov = json.load(open(PROV_JSON))
    with open("docs/DATA.md", "w", encoding="utf-8") as f:
        f.write("# GridFlex data provenance\n\n")
        f.write("| signal | kind | source | notes |\n|---|---|---|---|\n")
        obs = prov.get("observations", {})
        fc = prov.get("forecasts", {})
        f.write(f"| irradiance, temperature, wind | real (reanalysis) | {obs.get('source','-')} "
                f"| {obs.get('url','-')} |\n")
        f.write(f"| day-ahead weather forecast | real (archived operational run) | "
                f"{fc.get('source','-')} | lead time {fc.get('lead_time_hours','-')} h, "
                f"{fc.get('url','-')} |\n")
        pv_model = prov.get("pv_model", {})
        f.write(f"| PV output | modelled from real GHI | {pv_model.get('detail','-')} | "
                f"PVGIS validation {pv_model.get('validation_pvgis',{}).get('error_pct','-')} % |\n")
        f.write("| critical + flexible load | calibrated synthetic | Telangana LT-I consumption "
                "slabs + published Indian residential shape | no public household microdata used |\n")
        f.write("| outages | simulated, calibrated | CEEW 2019: 3.5 outage h/day in notified "
                "town areas, 1.3 in district HQ | realised value reported per run |\n")
        f.write(f"\nForecast skill on held-out days: load MAPE {acc.get('load_mape_pct', 0):.1f} %, "
                f"PV nMAE {acc.get('pv_nmae_pct', 0):.1f} %, 80 % interval coverage "
                f"{acc.get('pv_coverage80_pct', 0):.0f} % (PV).\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--seeds", type=int, default=0, help="multi-seed CI count (0 = off)")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--oracle", action="store_true")
    ap.add_argument("--sizing", action="store_true")
    ap.add_argument("--no-voltage", action="store_true")
    ap.add_argument("--no-whatif", action="store_true")
    ap.add_argument("--tou", action="store_true")
    ap.add_argument("--refresh-weather", action="store_true")
    args = ap.parse_args()

    t_start = time.time()
    p = P()
    if args.quick:
        p = replace(p, n_test_days=7)
    if args.no_voltage:
        p = replace(p, enforce_voltage=False)
    if args.tou:
        p = replace(p, tariff_mode="tou")

    build_cache(p, refresh=args.refresh_weather)
    df = make_data(p, seed=args.seed)
    t0 = p.train_end()
    fc = Forecaster(df, t0, pv_kwp=p.pv_kwp, seed=args.seed)
    acc = fc.evaluate(t0, len(df))
    pacc = PersistenceForecaster(df).evaluate(t0, len(df))
    print("forecast ML  :", {k: round(v, 2) for k, v in acc.items() if v is not None})
    print("forecast lag :", {k: round(v, 2) for k, v in pacc.items() if v is not None})
    print(f"realised outage: {df.is_outage.mean()*24:.2f} h/day (target {p.outage_h_per_day})")

    modes = [m for m in FULL if m != "oracle" or args.oracle]
    runs, M = {}, {}
    for m in modes:
        t = time.time()
        runs[m] = run(p, df, fc, m, t0, len(df))
        M[m] = metrics(p, runs[m])
        print(f"  {m:18s} {time.time()-t:5.1f}s  outage {M[m]['outage_hours_per_day']:.2f} h/day "
              f"evening {M[m]['evening_availability_pct']:.0f}% bill {M[m]['bill_inr_per_hh_month']:.0f}")

    am = archetype_metrics(runs["mpc_full"], p, "equal")
    runs["mpc_full_proportional"] = run(p, df, fc, "mpc_full", t0, len(df),
                                        rule="proportional")
    equity = {"archetypes": {k: v for k, v in am.items() if k != "fairness"},
              "fairness": am["fairness"],
              "rules": rule_sensitivity(p, {"equal": runs["mpc_full"],
                                            "proportional": runs["mpc_full_proportional"]})}

    # ---------------- sizing sweep -------------------------------------
    sizes = ([(40, 20), (70, 40), (100, 40), (150, 40)] if not args.sizing else
             [(b, k) for b in (20, 40, 70, 100, 150) for k in (10, 20, 40)])
    # the affordability frontier depends on the tariff scheme as much as on kWh
    size_cfgs = [(b, k, s) for (b, k) in sizes for s in ("lifeline", "flat")]
    s0 = max(t0, len(df) - 7 * 96)          # 7-day screening window keeps the run fast
    rows = sweep(p, df, fc, size_cfgs, s0, len(df), resolve_every=8)
    rows = with_reliability_value(rows, p, M["pv_batt_naive"],
                                  archetype_metrics(runs["pv_batt_naive"], p))
    size = sizing_summary(p, rows)
    print("sizing points:", [(r["bat_kwh"], round(r["cost_per_hh_month_inr"]),
                              round(r["outage_hours_per_day"], 2)) for r in rows])

    # ---------------- what-if grid -------------------------------------
    whatif = []
    if not args.no_whatif and not args.quick:
        t = time.time()
        w0 = max(t0, len(df) - 7 * 96)      # 7-day screening window
        groups = [(p, args.seed, w0, len(df), cloud, ev)
                  for cloud in WHATIF_CLOUD for ev in WHATIF_EV]
        with ProcessPoolExecutor(max_workers=min(len(groups), args.workers,
                                                 os.cpu_count() or 2)) as ex:
            for part in ex.map(_whatif_group, groups):
                whatif.extend(part)
        print(f"what-if points: {len(whatif)} ({time.time()-t:.0f}s)")

    # ---------------- multi-seed CI ------------------------------------
    ci = {}
    if args.seeds and args.seeds > 1:
        t = time.time()
        jobs = [(p, s, t0, len(df), args.oracle, p.enforce_voltage)
                for s in range(args.seeds)]
        with ProcessPoolExecutor(max_workers=min(args.workers, args.seeds,
                                                 os.cpu_count() or 2)) as ex:
            per = list(ex.map(_seed_job, jobs))
        ci = aggregate(per)
        print(f"multi-seed CI: {args.seeds} seeds in {time.time()-t:.0f}s")

    econ = unit_economics(p, M["pv_batt_naive"], M["mpc_full"], M["grid_only"])
    discom = console(p, df, runs["mpc_full"], M["mpc_full"], t0, fc,
                     r_base=runs["pv_batt_naive"])
    ablation_rows = ablation(M)

    # one consistent headline: the multi-seed mean when available, never the
    # single seed presented as if it were the expected value
    headline = {}
    for key in ("outage_hours_per_day", "evening_availability_pct", "critical_served_pct",
                "unserved_critical_kwh_per_day", "bill_inr_per_hh_month",
                "self_consumption_pct"):
        c = ci.get("mpc_full", {}).get(key)
        headline[key] = dict(value=(c["mean"] if c else M["mpc_full"][key]),
                             single_seed=M["mpc_full"][key],
                             lo=(c["lo"] if c else None), hi=(c["hi"] if c else None),
                             seeds=(c["n"] if c else 1))

    prov = {}
    if os.path.exists(PROV_JSON):
        prov = json.load(open(PROV_JSON))

    results = dict(
        meta=dict(seed=args.seed, seeds=args.seeds, quick=args.quick, oracle=args.oracle,
                  site=p.site_name, window=[p.weather_start, p.weather_end],
                  forecast_ml=acc, forecast_persistence=pacc,
                  outage_h_target=p.outage_h_per_day,
                  outage_h_realised=float(df.is_outage.mean() * 24),
                  runtime_s=None),
        metrics=M, headline=headline, ci=ci, ablation=ablation_rows, equity=equity,
        economics=econ,
        sizing=size, whatif=whatif, discom=discom,
        config=config_dict(p), assumptions=assumptions_table(p), data_provenance=prov,
    )

    os.makedirs("outputs", exist_ok=True)
    payload = build_payload(p, df, runs, M, acc, econ, equity, size,
                            dict(results=whatif), discom, ci=ci, provenance=prov,
                            headline=headline)
    make_dashboard(payload, "outputs/dashboard.html",
                   site_path="outputs/site/index.html")
    make_plots(p, df, runs, M, size, "outputs")
    results["meta"]["runtime_s"] = round(time.time() - t_start, 1)
    results["meta"]["dashboard"] = "outputs/dashboard.html"
    json.dump(results, open("outputs/results.json", "w"), indent=1, default=float)
    write_docs(p, acc, ci)

    print(f"\nheadline: outage {M['mpc_full']['outage_hours_per_day']:.2f} h/day "
          f"(grid only {M['grid_only']['outage_hours_per_day']:.2f}, "
          f"unmanaged {M['pv_batt_naive']['outage_hours_per_day']:.2f}, "
          f"rule {M['rule_reserve_tou']['outage_hours_per_day']:.2f})")
    print("economics:", {k: round(v, 1) for k, v in econ.items()
                         if isinstance(v, (int, float))})
    print(f"artefacts: outputs/dashboard.html, outputs/results.json, outputs/*.png "
          f"({time.time()-t_start:.0f}s)")


if __name__ == "__main__":
    main()

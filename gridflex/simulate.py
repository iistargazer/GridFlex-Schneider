"""Plant simulation and controllers.

Scenarios (all on identical weather / load / outages):
  grid_only        today's feeder: no PV, no battery, no control
  pv_batt_naive    PV + battery with a self-consumption rule, proportional cuts
  rule_reserve_tou rule-based evening reserve + solar-aware flexible shifting
  mpc_no_dr        GridFlex MILP but flexible loads run when they arrive
  mpc_persistence  GridFlex MILP with persistence (yesterday) forecasts
  mpc_full         GridFlex: ML forecasts + rolling MILP + windowed DR + fairness
  oracle           mpc_full with perfect foresight (upper bound)

Every step is checked for energy balance; SOC, cap and voltage violations are
counted, never hidden.
"""
import numpy as np
import pandas as pd

from .config import P
from .data import FLEX
from .equity import groups, split_by_rule
from .forecast import PersistenceForecaster
from .network import import_limits, loss_kw, voltages
from .optimizer import solve

SCENARIOS = {
    "grid_only": dict(pv=False, bat=False, ctrl="rule", dr=False, rule="none"),
    "pv_batt_naive": dict(pv=True, bat=True, ctrl="rule", dr=False, rule="naive"),
    "rule_reserve_tou": dict(pv=True, bat=True, ctrl="rule", dr=True, rule="reserve"),
    "mpc_no_dr": dict(pv=True, bat=True, ctrl="mpc", dr=False, rule="naive",
                      discom_cap=True),
    "mpc_persistence": dict(pv=True, bat=True, ctrl="mpc", dr=True, fc="persistence",
                            rule="naive", discom_cap=True),
    "mpc_full": dict(pv=True, bat=True, ctrl="mpc", dr=True, fc="ml", rule="naive",
                     discom_cap=True),
    "oracle": dict(pv=True, bat=True, ctrl="mpc", dr=True, fc="oracle", rule="naive",
                   discom_cap=True),
}
ALIASES = {"status_quo": "grid_only", "unmanaged": "pv_batt_naive", "gridflex": "mpc_full"}


class Bat:
    def __init__(s, P, on):
        s.P, s.on = P, on
        s.soc = P.soc0_frac * P.bat_kwh if on else 0.0

    def apply(s, req):
        """req>0 discharge to bus, req<0 charge (kW). Returns actual kW (same sign)."""
        P = s.P
        if not s.on or abs(req) < 1e-9:
            return 0.0
        if req > 0:
            out = min(req, P.bat_kw, max(0.0, (s.soc - P.soc_min_frac * P.bat_kwh) * P.eta / P.dt))
            s.soc -= out * P.dt / P.eta
            return out
        inp = min(-req, P.bat_kw, max(0.0, (P.bat_kwh - s.soc) / (P.eta * P.dt)))
        s.soc += inp * P.eta * P.dt
        return -inp


def global_windows(df):
    """All flexible windows in the dataset: cls -> [(start, end, energy, rate)]."""
    out = {}
    for name, (a, b, rate, _per_hh) in FLEX.items():
        w = []
        arr = df[f"E_{name}"].values
        for s in np.where(arr > 0)[0]:
            span = (b - a) if b > a else (24 - a + b)
            w.append((int(s), int(s + round(span * 4)), float(arr[s]), rate))
        out[name] = w
    return out


def _active(win, t):
    for w in win:
        if w[0] <= t < w[1]:
            return w
    return None


def _windows_for_solve(W, t, T, remaining, clsvars):
    out = []
    for cls in clsvars:
        for (s, e, _E, rate) in W[cls]:
            if e <= t or s >= t + T:
                continue
            rem = remaining.get((cls, s), _E)
            if rem <= 1e-6:
                continue
            out.append(dict(cls=cls, start=max(0, s - t), end=min(T, e - t),
                            energy=rem, rate=rate))
    return out


def _risk_profile(df, t0):
    """Historical outage frequency by hour of day, normalised to [0.3, 1]."""
    train = df.iloc[:t0]
    if len(train) == 0:
        return np.ones(24)
    by_hour = train.groupby(train.index.hour)["is_outage"].mean().reindex(range(24)).fillna(0)
    mx = max(float(by_hour.max()), 1e-6)
    return np.clip(by_hour.values / mx, 0.3, 1.0)


def _forecast(source, P, df, t, T, oracle):
    if oracle:
        return df["pv"].values[t:t + T], df["Dc"].values[t:t + T]
    r = P.risk
    pv = (1 - r) * source.predict("pv", .5, t, T) + r * source.predict("pv", .1, t, T)
    Dc = (1 - r) * source.predict("Dc", .5, t, T) + r * source.predict("Dc", .9, t, T)
    return pv, Dc


def run(P, df, fc, mode, t0, t1, oracle=False, rule="equal", resolver=None):
    mode = ALIASES.get(mode, mode)
    spec = dict(SCENARIOS[mode])
    if oracle:
        spec.update(fc="oracle", ctrl="mpc")
    has_pv, has_bat, dr = spec["pv"], spec["bat"], spec["dr"]
    fc = fc if fc is not None else PersistenceForecaster(df)
    bat = Bat(P, has_bat)
    n_all = len(df)
    W = global_windows(df)
    # only windows inside the simulated window: a window that closed before t0 is
    # not "unserved demand", and counting it would inflate the flex metric
    remaining = {(c, s): e for c, wins in W.items() for (s, _e, e, _r) in wins
                 if t0 <= s < t1}
    risk = _risk_profile(df, t0)
    pfc = PersistenceForecaster(df)
    g_lim_v, ex_lim_v = import_limits(P)
    plan, pt0 = None, 0
    clsvars = tuple(FLEX) if (spec["ctrl"] == "mpc" and dr) else ()
    agg = groups(P)
    names = [g[0] for g in agg]
    ns = np.array([g[1] for g in agg], float)
    rec = []
    balance_err = cap_viol = vviol = 0.0

    for t in range(t0, t1):
        pv = df["pv"].values[t] if has_pv else 0.0
        Dc = float(df["Dc"].values[t])
        dcs = np.array([df[f"Dc_{n}"].values[t] for n in names])
        cap, price = float(df["cap"].values[t]), float(df["price"].values[t])
        cap_eff = min(cap, g_lim_v) if P.enforce_voltage else cap
        hour = df.index[t].hour + df.index[t].minute / 60
        if spec.get("discom_cap") and 18 <= hour < 22:
            cap_eff = min(cap_eff, P.discom_evening_cap_kw)

        # ---------------- plan (rolling MILP) --------------------------------
        if spec["ctrl"] == "mpc" and (t - t0) % P.resolve_every == 0:
            H = min(P.H, n_all - t)
            src = pfc if spec.get("fc") == "persistence" else (resolver or fc)
            pv_f, Dc_f = _forecast(src, P, df, t, H, spec.get("fc") == "oracle")
            cap_f = df["cap_plan"].values[t:t + H].astype(float).copy()
            if t > 0 and df["cap"].values[t - 1] == 0:
                cap_f[:8] = 0.0                      # ongoing outage assumed to persist
            res_kwh = P.reserve_hours * Dc_f * np.array(
                [risk[int(df.index[t + i].hour)] for i in range(H)])
            wins = _windows_for_solve(W, t, H, remaining, clsvars)
            rates = {c: df[f"rate_{c}"].values[t:t + H] for c in clsvars}
            fixed = None
            if not dr:
                fixed = np.zeros(H)
                for i in range(H):
                    for cls in FLEX:
                        w = _active(W[cls], t + i)
                        if w is not None:
                            fixed[i] += min(df[f"rate_{cls}"].values[t + i],
                                            max(0.0, remaining.get((cls, w[0]), 0.0)) / P.dt)
            g_lim = np.minimum(cap_f, g_lim_v)
            if spec.get("discom_cap"):
                hrs = np.array([df.index[t + i].hour for i in range(H)])
                g_lim = np.where((hrs >= 18) & (hrs < 22),
                                 np.minimum(g_lim, P.discom_evening_cap_kw), g_lim)
            plan = solve(P, pv_f, Dc_f, cap_f, df["price"].values[t:t + H], bat.soc,
                         wins, res_kwh, flex_rate=rates, clsvars=clsvars,
                         fixed_flex=fixed, g_limits=g_lim,
                         export_limit=min(ex_lim_v, P.export_limit_kw))
            pt0 = t

        # ---------------- flexible service -----------------------------------
        f_serve = {cls: 0.0 for cls in FLEX}
        for cls in FLEX:
            w = _active(W[cls], t)
            if w is None:
                continue
            rem = remaining.get((cls, w[0]), 0.0)
            if rem <= 1e-9:
                continue
            rate = min(float(df[f"rate_{cls}"].values[t]), rem / P.dt)
            if spec["ctrl"] == "mpc" and plan is not None and f"f_{cls}" in plan:
                f_serve[cls] = float(plan[f"f_{cls}"][t - pt0])
            elif spec["rule"] == "reserve":
                end_step = min(w[1], n_all) - 1
                end_h = df.index[end_step].hour + df.index[end_step].minute / 60
                solar = pv > Dc + 0.3 * rate
                room = cap_eff >= Dc + 0.8 * rate and not df["is_outage"].values[t]
                late = hour >= end_h - 3.0
                f_serve[cls] = rate if (solar or room or late) else 0.0
            else:
                f_serve[cls] = rate
            f_serve[cls] = max(0.0, min(f_serve[cls], rate))

        # ---------------- battery dispatch -----------------------------------
        f_tot = sum(f_serve.values())
        net = Dc + f_tot - pv
        if spec["ctrl"] == "mpc" and plan is not None:
            req = float(plan["dis"][t - pt0] - plan["ch"][t - pt0])
        elif not has_bat:
            req = 0.0
        elif spec["rule"] == "reserve":
            in_stress = bool(df["is_stress"].values[t]) or cap_eff < P.cap_normal_kw
            keep = 0.45 * P.bat_kwh
            if in_stress:
                req = max(net, 0.0)
            elif net < 0:
                req = net
            elif hour < 16 and bat.soc < keep:
                req = -min(P.bat_kw, (keep - bat.soc) / (P.eta * P.dt))
            elif hour >= 22 and bat.soc > keep and net > 0:
                req = min(net, (bat.soc - keep) * P.eta / P.dt)
            else:
                req = 0.0
        else:
            req = net
        bat_out = bat.apply(req)

        # ---------------- real-time correction ------------------------------
        r = Dc + f_tot - pv - bat_out
        if r > cap_eff and bat_out < 0:              # stop charging before shedding
            undo = min(-bat_out, r - cap_eff)
            bat.apply(+undo)
            bat_out += undo
            r = Dc + f_tot - pv - bat_out
        if r > cap_eff:
            extra = bat.apply(min(r - cap_eff, P.bat_kw))
            bat_out += extra
            r -= extra

        shed_c = shed_f = 0.0
        f_orig = dict(f_serve)
        if r > cap_eff + 1e-9:
            short = r - cap_eff
            g = cap_eff
            if dr:
                shed_f = min(short, f_tot)
                shed_c = short - shed_f
            else:
                tot = Dc + f_tot
                shed_c = short * Dc / max(tot, 1e-9)
                shed_f = short - shed_c
        else:
            g = min(max(r, 0.0), cap_eff)

        served_f = f_tot - shed_f
        if shed_f > 1e-9 and f_tot > 1e-9:           # reduce service pro-rata
            for cls in FLEX:
                f_serve[cls] *= served_f / f_tot

        served_c = max(0.0, Dc - shed_c)
        served_arch = (split_by_rule(served_c, dcs, ns, rule)
                       if Dc > 1e-9 else np.zeros(len(names)))
        shed_arch = dcs - served_arch

        # ---------------- surplus -> charge / export / curtail --------------
        curt = exp = 0.0
        surplus = -r if r < -1e-9 else 0.0
        if surplus > 1e-9:
            extra = bat.apply(-min(surplus, P.bat_kw))
            bat_out += extra
            surplus += extra
            exp = min(surplus, P.export_limit_kw if P.allow_export else 0.0)
            curt = max(0.0, surplus - exp)

        # ---------------- flexible accounting -------------------------------
        for cls in FLEX:
            w = _active(W[cls], t)
            if w is not None:
                key = (cls, w[0])
                serve = min(f_serve[cls] * P.dt, remaining.get(key, 0.0))
                remaining[key] = remaining.get(key, 0.0) - serve
        if not dr and shed_f > 1e-9:
            # without demand response an interrupted appliance run is simply lost
            for cls in FLEX:
                w = _active(W[cls], t)
                if w is None or f_orig.get(cls, 0.0) <= 1e-9:
                    continue
                key = (cls, w[0])
                lost = min(remaining.get(key, 0.0), shed_f * f_orig[cls] / f_tot * P.dt)
                remaining[key] = remaining.get(key, 0.0) - lost

        # ---------------- invariants ----------------------------------------
        dis_kw, ch_kw = max(bat_out, 0.0), max(-bat_out, 0.0)
        bal = (g + pv + dis_kw) - (served_c + served_f + ch_kw + curt + exp)
        balance_err = max(balance_err, abs(bal))
        cap_viol += int(g > cap + 1e-6)
        v = voltages(P, [g])[0]
        vviol += int(((v < P.v_min_pu - 1e-6) | (v > P.v_max_pu + 1e-6)).sum())

        row = dict(ts=df.index[t], pv=pv, Dc=Dc, cap=cap_eff, g=g, soc=bat.soc,
                   dis=dis_kw, ch=ch_kw, curt=curt, exp=exp, shed_c=shed_c,
                   shed_f=shed_f, served_f=served_f,
                   flex_req=sum(df[f"E_{c}"].values[t] / P.dt for c in FLEX),
                   price=price, cost=g * price * P.dt,
                   loss=float(loss_kw(P, [g])[0]),
                   v_min=float(v.min()), v_max=float(v.max()), balance_err=bal,
                   is_stress=bool(df["is_stress"].values[t]),
                   is_outage=bool(df["is_outage"].values[t]))
        for i, n in enumerate(names):
            row[f"Dc_{n}"] = dcs[i]
            row[f"shed_{n}"] = shed_arch[i]
        for cls in FLEX:
            row[f"f_{cls}"] = f_serve[cls]
        rec.append(row)

    rdf = pd.DataFrame(rec).set_index("ts")
    rdf.attrs.update(balance_max_error_kw=balance_err, cap_violations=cap_viol,
                     voltage_violations=vviol, flex_unserved_kwh=float(sum(remaining.values())),
                     mode=mode, rule=rule)
    return rdf


def metrics(P, r, label=""):
    dt, days = P.dt, len(r) / 96
    idx = r.index
    ev = (idx.hour >= 18) & (idx.hour < 23)
    hit = r.shed_c > 0.05 * np.maximum(r.Dc, 1e-9)
    ev_hit = (r.shed_c[ev] > 0.05 * np.maximum(r.Dc[ev], 1e-9))
    flex_req = float(r.flex_req.sum() * dt)
    flex_srv = float(r.served_f.sum() * dt)
    unserved = float(r.attrs.get("flex_unserved_kwh", max(0.0, flex_req - flex_srv)))
    ep = (idx.hour >= 18) & (idx.hour < 22)
    mp = (idx.hour >= 6) & (idx.hour < 10)
    ep_peak = float(r.g[ep].groupby(idx[ep].date).max().mean()) if ep.any() else 0.0
    mp_peak = float(r.g[mp].groupby(idx[mp].date).max().mean()) if mp.any() else 0.0
    served_energy = float(((r.Dc - r.shed_c) + r.served_f).sum() * dt)
    return dict(
        critical_served_pct=float(100 * (1 - (r.shed_c * dt).sum() / max((r.Dc * dt).sum(), 1e-9))),
        outage_hours_per_day=float(hit.sum() * dt / days),
        evening_availability_pct=float(100 * (1 - ev_hit.mean())),
        unserved_critical_kwh_per_day=float(r.shed_c.sum() * dt / days),
        flex_requested_kwh_per_day=float(flex_req / days),
        flex_served_pct=float(100 * min(1.0, flex_srv / max(flex_req, 1e-9))),
        flex_unserved_kwh_per_day=float(max(0.0, unserved) / days),
        curtailment_pct=float(100 * r.curt.sum() * dt / max(r.pv.sum() * dt, 1e-9)),
        export_kwh_per_day=float(r.exp.sum() * dt / days),
        self_consumption_pct=float(100 * (1 - (r.exp.sum() + r.curt.sum()) * dt
                                          / max(r.pv.sum() * dt, 1e-9))),
        peak_import_kw=float(r.g.max()),
        evening_peak_import_kw=ep_peak,
        morning_peak_import_kw=mp_peak,
        transformer_loading_pct=float(100 * r.g.max() / P.rating_kw),
        grid_energy_kwh_per_day=float(r.g.sum() * dt / days),
        bill_inr_per_hh_month=float(r.cost.sum() / days * 30 / P.n_hh),
        saidi_minutes_per_day=float(hit.mean() * 1440.0),
        voltage_min_pu=float(r.v_min.min()),
        voltage_max_pu=float(r.v_max.max()),
        voltage_violations=int(r.attrs.get("voltage_violations", 0)),
        loss_pct=float(100 * r.loss.sum() * dt / max(served_energy, 1e-9)),
        critical_served_kwh_per_day=float(((r.Dc - r.shed_c).sum() * dt) / days),
        energy_balance_max_error_kw=float(r.attrs.get("balance_max_error_kw", 0.0)),
        cap_violations=int(r.attrs.get("cap_violations", 0)),
    )

"""Payload builder, PNG figures and the dashboard writer.

Everything is precomputed in Python so the page works offline in a judging room:
no server, no CDN, no API keys. The page itself (design, copy, interaction) lives
in `dashboard.py`; this module only assembles the payload and the matplotlib
figures the deck uses.
"""
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from .config import assumptions_table
from .dashboard import render
from .data import FLEX
from .network import voltages

R = lambda a: [round(float(x), 2) for x in a]
ASSET = os.path.join(os.path.dirname(__file__), "assets", "chart.umd.min.js")


def _day_pack(P, df, runs, modes):
    full = runs["mpc_full"]
    days = []
    n_days = len(full) // 96
    for d in range(n_days):
        sl = slice(d * 96, (d + 1) * 96)
        g = full.iloc[sl]
        cap = g.cap.values
        outage = bool(g.is_outage.any())
        stress = bool(g.is_stress.any())
        tag = "outage" if outage else ("DISCOM stress" if stress else "normal")
        v = voltages(P, g.g.values)
        item = dict(label=f"{g.index[0].strftime('%d %b')} · {tag}",
                    load=R(g.Dc + g.served_f), pv=R(g.pv), cap=R(cap),
                    g={}, soc={}, shed={}, flex={}, exp=R(g.exp), curt=R(g.curt),
                    v=[R(v[:, b]) for b in range(v.shape[1])])
        for m in modes:
            rr = runs[m].iloc[sl]
            item["g"][m] = R(rr.g)
            item["soc"][m] = R(rr.soc)
            item["shed"][m] = R(rr.shed_c)
        for cls in FLEX:
            item["flex"][cls] = R(g[f"f_{cls}"])
        days.append(item)
    return days


def _reasons(P, runs, df):
    from .explain import day_summary, hourly
    full, base = runs["mpc_full"], runs["pv_batt_naive"]
    diff = [(full.iloc[d * 96:(d + 1) * 96].shed_c.sum()
             - base.iloc[d * 96:(d + 1) * 96].shed_c.sum()) for d in range(len(df) // 96)]
    best = int(np.argmax(diff))
    sl = slice(best * 96, (best + 1) * 96)
    return dict(day=full.index[best * 96].strftime("%d %b %Y"),
                summary=day_summary(P, full, sl),
                hourly=hourly(P, full, sl))


def build_payload(P, df, runs, M, acc, econ, equity, sizing, whatif, discom,
                  ci=None, provenance=None, headline=None):
    modes = ["grid_only", "pv_batt_naive", "rule_reserve_tou", "mpc_no_dr",
             "mpc_persistence", "mpc_full", "oracle"]
    modes = [m for m in modes if m in runs]
    best = runs["mpc_full"].index[0]
    return dict(
        meta=dict(site=P.site_name, start=str(df.index[0].date()), end=str(df.index[-1].date()),
                  days=P.n_days, test_days=P.n_test_days,
                  generated=pd_now(), n_hh=P.n_hh, pv_kwp=P.pv_kwp,
                  bat_kwh=P.bat_kwh, bat_kw=P.bat_kw,
                  outage_h_target=P.outage_h_per_day,
                  outage_h_realised=round(float(df.is_outage.mean() * 24), 2),
                  forecast=acc, provenance=provenance,
                  tariff_mode=P.tariff_mode, tariff=P.tariff_flat,
                  full_day=str(best.date())),
        scenarios=M, headline=headline or {}, ci=ci or {},
        days=_day_pack(P, df, runs, modes),
        reasons=_reasons(P, runs, df),
        equity=equity, econ=econ, sizing=sizing, whatif=whatif, discom=discom,
        assumptions=assumptions_table(P),
        modes=modes,
    )


def pd_now():
    import datetime
    return datetime.datetime.now().strftime("%d %b %Y %H:%M")


def make_dashboard(payload, path, site_path=None):
    """Write the self-contained dashboard, plus its publishable copy.

    One writer, one HTML string: the local page and the file a judge uploads are
    written in the same call, so they cannot drift apart. Chart.js is inlined, so
    no sidecar asset is produced and the page works from a file path or a server.
    """
    chart = open(ASSET, encoding="utf-8").read()
    html = render(payload, chart)
    for target in ([path] if not site_path else [path, site_path]):
        os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
        open(target, "w", encoding="utf-8").write(html)


# ---------------------------------------------------------------------------
# PNG figures for the deck
# ---------------------------------------------------------------------------
def make_plots(P, df, runs, M, sizing, outdir):
    os.makedirs(outdir, exist_ok=True)
    modes = [m for m in ["grid_only", "pv_batt_naive", "rule_reserve_tou",
                         "mpc_no_dr", "mpc_persistence", "mpc_full", "oracle"] if m in M]
    labels = [m.replace("_", "\n") for m in modes]
    colors = ["#b3402f", "#8a8f98", "#c98b2e", "#5b7fbf", "#7a5fa8", "#1f7a4d", "#0f5132"]
    fig, ax = plt.subplots(1, 2, figsize=(11, 4))
    ax[0].bar(labels, [M[m]["outage_hours_per_day"] for m in modes], color=colors)
    ax[0].set_ylabel("interrupted critical hours/day")
    ax[0].set_title("Reliability by scenario")
    ax[1].bar(labels, [M[m]["bill_inr_per_hh_month"] for m in modes], color=colors)
    ax[1].set_ylabel("Rs / household / month")
    ax[1].set_title("Grid bill by scenario")
    for a in ax:
        a.tick_params(axis="x", labelsize=7)
    plt.tight_layout()
    plt.savefig(f"{outdir}/scenarios.png", dpi=150)
    plt.close()

    # worst day
    full, base = runs["mpc_full"], runs["pv_batt_naive"]
    diff = [(full.iloc[d * 96:(d + 1) * 96].shed_c.sum()
             - base.iloc[d * 96:(d + 1) * 96].shed_c.sum()) for d in range(len(df) // 96)]
    k = int(np.argmax(diff))
    sl = slice(k * 96, (k + 1) * 96)
    g, u = full.iloc[sl], base.iloc[sl]
    x = np.arange(96) / 4
    fig, ax = plt.subplots(2, 1, figsize=(10, 6), sharex=True)
    ax[0].plot(x, g.Dc + g.served_f, "k", label="Load")
    ax[0].plot(x, g.pv, "#e8a33d", label="Solar")
    ax[0].plot(x, g.g, "#1f7a4d", label="Grid import - GridFlex")
    ax[0].plot(x, u.g, "#8a8f98", ls="--", label="Grid import - unmanaged")
    ax[0].step(x, g.cap, "#b3402f", ls=":", label="Feeder limit")
    ax[0].legend(ncol=3, fontsize=8)
    ax[0].set_ylabel("kW")
    ax[0].set_title(g.index[0].strftime("%d %b %Y"))
    ax[1].plot(x, g.soc, "#1f7a4d", label="SOC - GridFlex")
    ax[1].plot(x, u.soc, "#8a8f98", label="SOC - unmanaged")
    ax[1].fill_between(x, g.shed_c, color="#1f7a4d", alpha=.35, label="unserved critical")
    ax[1].fill_between(x, u.shed_c, color="#b3402f", alpha=.25, label="unserved - unmanaged")
    ax[1].set_ylabel("kWh / kW")
    ax[1].set_xlabel("hour")
    ax[1].legend(fontsize=8)
    plt.tight_layout()
    plt.savefig(f"{outdir}/day_plot.png", dpi=150)
    plt.close()

    if sizing and sizing.get("points"):
        pts = sizing["points"]
        fig, ax = plt.subplots(figsize=(6, 4))
        for scheme, colour in (("lifeline", "#1f7a4d"), ("flat", "#c98b2e")):
            s = [p for p in pts if p.get("fee_scheme") == scheme]
            if not s:
                continue
            ax.scatter([p["outage_hours_per_day"] for p in s],
                       [p["net_cost_low_income_per_hh_month_inr"] for p in s],
                       c=colour, label=f"{scheme} tariff")
            for p in s:
                ax.annotate(f"{p['bat_kwh']:.0f}kWh", (p["outage_hours_per_day"],
                                                       p["net_cost_low_income_per_hh_month_inr"]),
                            fontsize=7, xytext=(4, 3), textcoords="offset points")
        ax.set_xlabel("interrupted critical hours/day")
        ax.set_ylabel("net cost, low-income Rs/hh/month")
        ax.set_title("Battery sizing frontier by tariff")
        ax.legend(fontsize=7)
        plt.tight_layout()
        plt.savefig(f"{outdir}/sizing.png", dpi=150)
        plt.close()

    fig, ax = plt.subplots(figsize=(6, 4))
    v = voltages(P, full.g.values)
    for b in range(v.shape[1]):
        ax.plot(np.arange(len(v)) / 96, v[:, b], label=f"branch {b+1}")
    ax.axhline(P.v_min_pu, color="#b3402f", ls="--", label="limit")
    ax.set_ylim(0.92, 1.01)
    ax.set_xlabel("day"); ax.set_ylabel("voltage (pu)")
    ax.set_title("End-of-feeder voltage, GridFlex")
    ax.legend(fontsize=7)
    plt.tight_layout()
    plt.savefig(f"{outdir}/voltage.png", dpi=150)
    plt.close()

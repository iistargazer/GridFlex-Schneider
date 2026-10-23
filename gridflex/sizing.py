"""Battery sizing sweep: reliability vs affordability, with a lifeline tariff axis.

Each point is a real simulation. Two axes matter for affordability:
the battery size (cost and reliability) and the tariff scheme - `lifeline`
(low-income households pay Rs0, others cross-subsidise) versus `flat` (everyone
pays the standard fee). The low-income net cost is built from that household
group's own metered served energy and unserved energy, not from the archetype
shares, so the two schemes genuinely move the frontier.

Reliability value, bill saving and the DISCOM peak credit use the same
definitions as `economics.unit_economics`, so the sizing table and the
unit-economics table cannot disagree.
"""
from dataclasses import replace

import numpy as np

from .config import P
from .economics import annual_cost
from .equity import archetype_metrics, groups
from .simulate import metrics, run

LI = "low_income"
STD_FEE = 60.0


def lifeline_availability(P, r):
    """Availability of the lifeline share of critical load, served first."""
    dc = r.Dc.values
    served = dc - r.shed_c.values
    target = P.lifeline_fraction * dc
    got = np.minimum(target, served)
    return float(100 * got.sum() / max(target.sum(), 1e-9))


def evaluate(base: P, df, fc, t0, t1, kwh, kw, resolve_every=None,
             rule="equal", fee_scheme="lifeline"):
    p = replace(base, bat_kwh=float(kwh), bat_kw=float(kw),
                resolve_every=resolve_every or base.resolve_every)
    r = run(p, df, fc, "mpc_full", t0, t1, rule=rule)
    m = metrics(p, r)
    eq = archetype_metrics(r, p, rule)
    names = [n for n, _c, _m, _pv in groups(p)]
    li = eq[LI]
    served_total = sum(eq[n]["served_kwh_per_day"] for n in names)
    ac = annual_cost(p)
    return dict(bat_kwh=float(kwh), bat_kw=float(kw), fee_scheme=fee_scheme,
                fee_li_inr=0.0 if fee_scheme == "lifeline" else STD_FEE,
                capex_per_hh_inr=ac["capex_inr"] / p.n_hh,
                cost_per_hh_month_inr=ac["per_hh_month_inr"],
                outage_hours_per_day=m["outage_hours_per_day"],
                evening_availability_pct=m["evening_availability_pct"],
                lifeline_availability_pct=lifeline_availability(p, r),
                unserved_critical_kwh_per_day=m["unserved_critical_kwh_per_day"],
                evening_peak_import_kw=m["evening_peak_import_kw"],
                curtailment_pct=m["curtailment_pct"],
                bill_inr_per_hh_month=m["bill_inr_per_hh_month"],
                li_served_kwh_per_day=li["served_kwh_per_day"],
                li_served_share=float(li["served_kwh_per_day"]
                                      / max(served_total, 1e-9)),
                li_unserved_critical_kwh_per_day=li["unserved_critical_kwh_per_day"],
                li_self_consumption_pct=li["self_consumption_pct"],
                li_served_kwh_per_hh_day=li["served_kwh_per_hh_day"])


def sweep(base: P, df, fc, configs, t0, t1, resolve_every=None, rule="equal"):
    """configs: (kwh, kw) or (kwh, kw, fee_scheme)."""
    out = []
    for cfg in configs:
        kwh, kw = cfg[0], cfg[1]
        scheme = cfg[2] if len(cfg) > 2 else "lifeline"
        out.append(evaluate(base, df, fc, t0, t1, kwh, kw,
                            resolve_every=resolve_every, rule=rule,
                            fee_scheme=scheme))
    return out


def with_reliability_value(rows, base: P, m_base, eq_base=None, voll=None):
    """Attach the three value components and the low-income net cost.

    Components match `unit_economics`: bill saving vs the same PV+battery with no
    control, avoided unserved energy at VoLL, and the DISCOM evening-peak credit.
    """
    voll = base.voll_household if voll is None else voll
    n_li = dict((n, c) for n, c, _m, _pv in groups(base))[LI]
    for row in rows:
        bill_saving = m_base["bill_inr_per_hh_month"] - row["bill_inr_per_hh_month"]
        unserved_cut = max(0.0, m_base["unserved_critical_kwh_per_day"]
                           - row["unserved_critical_kwh_per_day"])
        relief = unserved_cut * 30 / base.n_hh * voll
        peak_cut = max(0.0, m_base["evening_peak_import_kw"]
                       - row["evening_peak_import_kw"])
        discom = peak_cut * base.discom_peak_value_inr_per_kw_month / base.n_hh
        row["bill_saving_per_hh_month_inr"] = bill_saving
        row["reliability_value_per_hh_month_inr"] = relief
        row["discom_credit_per_hh_month_inr"] = discom
        row["net_cost_per_hh_month_inr"] = (row["cost_per_hh_month_inr"]
                                            - bill_saving - relief - discom)
        li_share = row["li_served_share"]
        li_cut = unserved_cut * li_share
        if eq_base is not None:
            li_cut = max(0.0, eq_base[LI]["unserved_critical_kwh_per_day"]
                         - row["li_unserved_critical_kwh_per_day"])
        row["li_unserved_avoided_kwh_per_day"] = li_cut
        li_bill = bill_saving * li_share
        li_discom = discom * li_share
        li_relief = li_cut * 30 / max(n_li, 1) * voll
        row["net_cost_low_income_per_hh_month_inr"] = (
            row["cost_per_hh_month_inr"] - li_bill - li_relief - li_discom
            + row["fee_li_inr"])
    return rows


def pareto(rows, cost_key="net_cost_low_income_per_hh_month_inr"):
    """Non-dominated (cost, outage) points, cheapest first."""
    keep = []
    for r in sorted(rows, key=lambda x: (x[cost_key], x["outage_hours_per_day"])):
        if not keep or r["outage_hours_per_day"] < keep[-1]["outage_hours_per_day"] - 1e-9:
            keep.append(r)
    return keep


def knee(rows, cost_key="net_cost_low_income_per_hh_month_inr"):
    """Balanced point on the frontier (normalised cost + outage)."""
    p = pareto(rows, cost_key)
    if len(p) <= 2:
        return p[-1] if p else None
    costs = np.array([x[cost_key] for x in p])
    out = np.array([x["outage_hours_per_day"] for x in p])
    c = (costs - costs.min()) / max(np.ptp(costs), 1e-9)
    o = (out - out.min()) / max(np.ptp(out), 1e-9)
    return p[int(np.argmin(c + o))]


def summary(base: P, rows):
    schemes = sorted({r["fee_scheme"] for r in rows})
    key = "net_cost_low_income_per_hh_month_inr"
    by_scheme = {s: pareto([r for r in rows if r["fee_scheme"] == s], key)
                 for s in schemes}
    knees = {s: knee([r for r in rows if r["fee_scheme"] == s], key) for s in schemes}
    main = "lifeline" if "lifeline" in schemes else (schemes[0] if schemes else None)
    return dict(points=rows,
                schemes=schemes,
                # headline frontier is the recommended (lifeline) scheme; mixing
                # schemes on one frontier would compare different fee policies
                pareto=by_scheme.get(main, []),
                pareto_by_scheme=by_scheme,
                knee=knees.get(main),
                knee_by_scheme=knees,
                cost_axis=key,
                reference_config=dict(bat_kwh=base.bat_kwh, bat_kw=base.bat_kw))

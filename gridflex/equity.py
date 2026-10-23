"""Fair-access layer: archetypes, equal-per-household critical allocation, Jain index.

The challenge asks for fair-access dispatch rules. During a shortfall the
controller serves each connected household the *same* amount of critical energy
before any household gets a second share (equal per household), so a large villa
cannot crowd out a one-room home.

Per-archetype metrics are computed from metered flows, not from the archetype
shares alone: each archetype is credited with its own critical demand and its
own share of the PV capacity, and battery discharge is split by the energy each
archetype actually had served that step. Self-consumption is therefore
`local PV + battery energy / critical demand`, and the fairness index is computed
on served kWh per household, which differs between allocation rules.

`allocation="proportional"` reproduces the naive proportional cut and is run as a
sensitivity by run.py.
"""
import numpy as np

from .config import P


def groups(p: P):
    """(name, n_hh, load_multiplier_normalised, pv_share) per archetype."""
    total_w = sum(s * m for _, s, m, _ in p.archetypes)
    return [(name, int(round(p.n_hh * share)), mult / total_w, pv)
            for name, share, mult, pv in p.archetypes]


def allocate(served_total, demand, n_hh, iters=30):
    """Water-fill served_total kW across groups, equal per household, capped by demand."""
    served = np.zeros(len(demand))
    remaining = max(0.0, float(served_total))
    active = list(range(len(demand)))
    for _ in range(iters):
        if remaining <= 1e-9 or not active:
            break
        per_hh = remaining / max(sum(n_hh[i] for i in active), 1)
        delivered = 0.0
        nxt = []
        for i in active:
            room = demand[i] - served[i]
            give = min(room, per_hh * n_hh[i])
            served[i] += give
            delivered += give
            if room - give > 1e-7:
                nxt.append(i)
        remaining -= delivered
        if delivered <= 1e-9:
            break
        active = nxt
    return served


def split_by_rule(served_total, demand, n_hh, rule="equal"):
    if rule == "proportional":
        tot = max(float(np.sum(demand)), 1e-9)
        return np.asarray(demand, float) * served_total / tot
    return allocate(served_total, demand, n_hh)


def jain(values):
    x = np.asarray(values, float)
    if len(x) == 0 or np.allclose(x, 0):
        return 1.0
    return float((x.sum() ** 2) / (len(x) * np.sum(x ** 2)))


def _pv_weights(p: P):
    """PV capacity weight per archetype, from its household share and PV ownership."""
    raw = np.array([share * pv for _, share, _m, pv in p.archetypes], float)
    total = raw.sum()
    return raw / total if total > 0 else np.full(len(raw), 1.0 / len(raw))


def archetype_metrics(r, p: P, rule="equal"):
    """Per-archetype reliability and local-supply metrics from metered flows."""
    g = groups(p)
    days = max(len(r) / 96, 1e-9)
    ev = (r.index.hour >= 18) & (r.index.hour < 23)
    w = _pv_weights(p)
    dc = {name: r[f"Dc_{name}"].values for name, _n, _m, _pv in g}
    total_served_step = sum(dc[name] - r[f"shed_{name}"].values
                            for name, _n, _m, _pv in g)
    pv, dis = r.pv.values, r.dis.values
    out = {}
    for i, (name, n, _m, _pv) in enumerate(g):
        d_i = dc[name]
        shed = r[f"shed_{name}"].values
        served = np.maximum(d_i - shed, 0.0)
        pv_i = pv * w[i]
        share = np.divide(served, total_served_step,
                          out=np.zeros_like(served), where=total_served_step > 1e-9)
        dis_i = dis * share
        local = np.minimum(d_i, pv_i + dis_i)
        hit = shed > 0.05 * np.maximum(d_i, 1e-9)
        out[name] = dict(
            households=n,
            critical_served_pct=float(100 * (1 - shed.sum() / max(d_i.sum(), 1e-9))),
            outage_hours_per_day=float(hit.sum() * p.dt / days),
            evening_availability_pct=float(100 * (1 - hit[ev].mean())),
            unserved_critical_kwh_per_day=float(shed.sum() * p.dt / days),
            served_kwh_per_day=float(served.sum() * p.dt / days),
            served_kwh_per_hh_day=float(served.sum() * p.dt / days / max(n, 1)),
            self_consumption_pct=float(100 * local.sum() / max(d_i.sum(), 1e-9)),
            grid_import_kwh_per_day=float(
                np.maximum(0.0, served - pv_i - dis_i).sum() * p.dt / days),
        )
    served_pct = [v["critical_served_pct"] for v in out.values()]
    out["fairness"] = dict(
        # fraction served, not absolute kWh: households differ in demand, so a
        # Jain index on kWh would grade their size rather than their service
        jain_index=jain([x / 100.0 for x in served_pct]),
        low_income_gap_pp=float(out[g[0][0]]["critical_served_pct"]
                                - np.mean(served_pct)),
        low_income_served_kwh_per_hh_day=out[g[0][0]]["served_kwh_per_hh_day"],
        metric="Jain index on the served fraction of each archetype's critical demand",
        rule=("equal-per-household critical allocation" if rule == "equal"
              else "proportional-to-demand critical allocation"),
    )
    return out


def rule_sensitivity(p: P, runs_by_rule):
    """Compare allocation rules on the same dispatch, from metered flows."""
    out = {}
    for rule, r in runs_by_rule.items():
        m = archetype_metrics(r, p, rule)
        out[rule] = dict(
            fairness=m["fairness"],
            archetypes={k: v for k, v in m.items() if k != "fairness"},
        )
    return out

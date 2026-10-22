"""Plant simulation + controllers. Three scenarios on identical weather/load/outages:
  status_quo : grid only (no PV, no battery, no load control)         -> what the feeder experiences today
  unmanaged  : PV + community battery with simple self-consumption rule, no forecasting, no load control
  gridflex   : forecasts -> rolling MILP -> battery + flexible-load scheduling + critical-load priority
"""
import numpy as np, pandas as pd
from .optimizer import solve


class Bat:
    def __init__(s, P, on):
        s.P, s.on = P, on
        s.soc = P.soc0_frac * P.bat_kwh if on else 0.0

    def apply(s, req):
        """req>0 discharge to bus, req<0 charge from bus (kW). returns actual kW (same sign)."""
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


def run(P, df, fc, mode, t0, t1, oracle=False):
    has_pv, has_bat, smart = mode != "status_quo", mode != "status_quo", mode == "gridflex"
    bat, backlog, plan, pt0 = Bat(P, has_bat), 0.0, None, 0
    n, dt = len(df), P.dt
    A = {k: df[k].values for k in ("pv", "Dc", "F", "cap", "cap_plan", "price")}
    rec = []
    for t in range(t0, t1):
        if smart and (t - t0) % P.resolve_every == 0:
            T = min(P.H, n - t)
            if oracle:
                pv_f, Dc_f, F_f = A["pv"][t:t + T], A["Dc"][t:t + T], A["F"][t:t + T]
            else:
                r = P.risk
                pv_f = (1 - r) * fc.predict("pv", .5, t, T) + r * fc.predict("pv", .1, t, T)
                Dc_f = (1 - r) * fc.predict("Dc", .5, t, T) + r * fc.predict("Dc", .9, t, T)
                F_f = fc.predict("F", .5, t, T)
            cap_f = A["cap_plan"][t:t + T].copy()
            if t > 0 and A["cap"][t - 1] == 0:
                cap_f[:8] = 0.0                      # ongoing outage assumed to persist ~2 h
            cap_f[0] = A["cap"][t]
            plan, pt0 = solve(P, pv_f, Dc_f, F_f, cap_f, A["price"][t:t + T], bat.soc, backlog), t
        pv = A["pv"][t] if has_pv else 0.0
        Dc, F, cap, price = A["Dc"][t], A["F"][t], A["cap"][t], A["price"][t]
        avail = backlog / dt + F
        if smart and plan is not None:
            k = t - pt0
            f = min(plan["f"][k], avail); req = plan["dis"][k] - plan["ch"][k]
        else:
            f = avail; req = None
        need = Dc + f
        out = bat.apply(req if req is not None else need - pv)       # rule: cover deficit / absorb surplus
        r = need - pv - out
        g = curt = shed_c = shed_f = 0.0
        if r > 1e-9:
            g = min(r, cap); r -= g
            if r > 1e-9:
                r -= bat.apply(r)                                       # emergency discharge if cap binds
            if r > 1e-9:
                if smart:                                               # priority: defer flexible first
                    shed_f = min(r, f); shed_c = r - shed_f
                else:                                                   # no load control: proportional cut
                    shed_c, shed_f = r * Dc / need, r * f / need
        elif r < -1e-9:
            ch = bat.apply(r)                                           # absorb surplus
            curt = -r + ch
        served_f = f - shed_f
        if smart:
            backlog = max(0.0, backlog + (F - served_f) * dt)
        else:
            backlog = 0.0                                               # unmanaged: shed flexible demand is simply lost
        rec.append((df.index[t], pv, Dc, F, cap, g, bat.soc, curt, shed_c, shed_f, served_f, backlog, price,
                    g * price * dt, bat.soc))
    cols = ["ts", "pv", "Dc", "F", "cap", "g", "soc", "curt", "shed_c", "shed_f", "served_f", "backlog", "price", "cost", "_"]
    return pd.DataFrame(rec, columns=cols).drop(columns="_").set_index("ts")


def metrics(P, r, label=""):
    dt, days = P.dt, len(r) / 96
    ev = (r.index.hour >= 18) & (r.index.hour < 23)
    hit = r.shed_c > 0.05 * r.Dc
    return dict(
        critical_served_pct=100 * (1 - r.shed_c.sum() / r.Dc.sum()),
        outage_hours_per_day=hit.sum() * dt / days,
        evening_availability_pct=100 * (1 - hit[ev].mean()),
        unserved_critical_kwh_per_day=r.shed_c.sum() * dt / days,
        flex_unserved_kwh_per_day=((r.F.sum() - r.served_f.sum()) * dt - r.backlog.iloc[-1]) / days,
        curtailment_pct=100 * r.curt.sum() / max(r.pv.sum(), 1e-9) if r.pv.sum() > 0 else 0.0,
        peak_import_kw=r.g.max(),
        evening_peak_import_kw=r.g[(r.index.hour >= 18) & (r.index.hour < 22)].groupby(r.index[(r.index.hour >= 18) & (r.index.hour < 22)].date).max().mean(),
        grid_energy_kwh_per_day=r.g.sum() * dt / days,
        bill_inr_per_hh_month=r.cost.sum() / days * 30 / P.n_hh,
    )

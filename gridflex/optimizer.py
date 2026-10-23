"""Rolling-horizon MILP solved with open-source HiGHS via scipy.

Decision variables per step t (T steps of dt hours):
  g[t]      grid import (kW)                      exp[t]  export (kW)
  ch[t]     battery charge (kW)                   dis[t]  discharge (kW)
  soc[t]    stored energy (kWh)                   u[t]    binary: charging
  gc[t]     part of ch taken from the grid        curt[t] PV curtailed (kW)
  sc[t]     critical load shed (kW)               rs[t]   reserve slack (kWh)
  f_<cls>[t] flexible energy served (kW)          sf_<cls>[t] flexible energy forfeited (kWh)

Flexible loads are *windowed*: each window has an energy request E, a service
rate cap and a deadline. The constraint sum(f*dt) + sum(sf) >= E is applied per
window, so the optimiser may shift energy inside the window (e.g. pump at noon
solar) but cannot invent flexibility outside it.

`fixed_flex` lets a no-demand-response controller pass a greedy flexible-load
profile (kW) that the MILP must plan around but cannot move.
"""
import numpy as np
import scipy.sparse as sp
from scipy.optimize import Bounds, LinearConstraint, milp

BASE = ["g", "ch", "dis", "soc", "u", "gc", "curt", "exp", "sc", "rs"]


def solve(P, pv, Dc, cap, price, soc0, windows, reserve_kwh,
          flex_rate=None, clsvars=(), fixed_flex=None, g_limits=None,
          export_limit=None, time_limit=8):
    """Return a dict of arrays, or None when the MILP is infeasible."""
    T, dt = len(pv), P.dt
    names = BASE + [f"f_{c}" for c in clsvars] + [f"sf_{c}" for c in clsvars]
    ix = {n: i * T for i, n in enumerate(names)}
    N = len(names) * T
    I = sp.identity(T, format="csr")
    S = sp.diags([np.ones(T - 1)], [-1], format="csr")
    Z = sp.csr_matrix((T, T))

    def row(**kw):
        return sp.hstack([kw.get(n, Z) for n in names], format="csr")

    pmax = P.bat_kw
    smin, smax = P.soc_min_frac * P.bat_kwh, P.bat_kwh
    rows, lb, ub = [], [], []

    def add(A, lo, hi):
        rows.append(A)
        lb.append(np.broadcast_to(np.asarray(lo, float), (A.shape[0],)))
        ub.append(np.broadcast_to(np.asarray(hi, float), (A.shape[0],)))

    flex_cols = {f"f_{c}": -I for c in clsvars}
    fixed = np.zeros(T) if fixed_flex is None else np.asarray(fixed_flex, float)
    # 1. power balance: g + pv + dis - sc - sum(f) - ch - curt - exp = Dc + fixed - pv
    add(row(g=I, dis=I, sc=-I, ch=-I, curt=-I, exp=-I, **flex_cols),
        Dc + fixed - pv, Dc + fixed - pv)
    # 2. state of charge
    rhs_soc = np.zeros(T)
    rhs_soc[0] = soc0
    add(row(soc=I - S, ch=-dt * P.eta * I, dis=dt / P.eta * I), rhs_soc, rhs_soc)
    # 3. charge/discharge exclusivity
    add(row(ch=I, u=-pmax * I), -np.inf, np.zeros(T))
    add(row(dis=I, u=pmax * I), -np.inf, np.full(T, pmax))
    # 4. grid-charging split, transformer-friendly charging, PV-only remainder
    add(row(gc=I, ch=-I), -np.inf, np.zeros(T))
    add(row(gc=I), -np.inf, np.full(T, P.grid_charge_cap_kw))
    add(row(ch=I, gc=-I), -np.inf, pv)
    # 5. soft reserve for unannounced outages
    add(row(soc=I, rs=I), reserve_kwh, np.full(T, np.inf))

    # 6. flexible windows: -sum(f*dt) - sum(sf) <= -E
    for w in windows:
        a, b = max(0, int(w["start"])), min(T, int(w["end"]))
        if b <= a:
            continue
        r = sp.lil_matrix((1, N))
        c = w["cls"]
        if c in clsvars:
            r[0, ix[f"f_{c}"] + a: ix[f"f_{c}"] + b] = -dt
            r[0, ix[f"sf_{c}"] + a: ix[f"sf_{c}"] + b] = -1.0
            rows.append(r.tocsr())
            lb.append(np.array([-np.inf]))
            ub.append(np.array([-float(w["energy"])]))

    A = sp.vstack(rows, format="csr")
    cvec = np.zeros(N)

    def put(n, v):
        cvec[ix[n]:ix[n] + T] += v

    put("g", price * dt)
    put("ch", P.deg_cost * dt / 2)
    put("dis", P.deg_cost * dt / 2)
    put("sc", P.voll_critical * dt)
    put("curt", P.curt_pen * dt)
    put("exp", -P.feed_in_tariff * dt)
    put("rs", P.reserve_pen)
    cvec[ix["soc"] + T - 1] -= P.term_soc_val
    for c in clsvars:
        put(f"sf_{c}", P.voll_flex)

    lo = np.zeros(N)
    hi = np.zeros(N)

    def bnd(n, l, h):
        lo[ix[n]:ix[n] + T] = l
        hi[ix[n]:ix[n] + T] = h

    g_max = cap.copy() if g_limits is None else np.minimum(cap, g_limits)
    bnd("g", 0, g_max)
    bnd("ch", 0, pmax)
    bnd("dis", 0, pmax)
    bnd("soc", smin, smax)
    bnd("u", 0, 1)
    bnd("gc", 0, pmax)
    bnd("curt", 0, pv)
    ex_max = 0.0 if not P.allow_export else (
        P.export_limit_kw if export_limit is None else min(P.export_limit_kw, export_limit))
    bnd("exp", 0, ex_max)
    bnd("sc", 0, Dc)
    bnd("rs", 0, smax)
    for c in clsvars:
        rate = flex_rate.get(c, np.zeros(T)) if flex_rate else np.zeros(T)
        bnd(f"f_{c}", 0, np.asarray(rate, float))
        bnd(f"sf_{c}", 0, np.inf)

    integ = np.zeros(N)
    integ[ix["u"]:ix["u"] + T] = 1
    res = milp(cvec,
               constraints=LinearConstraint(A, np.concatenate(lb), np.concatenate(ub)),
               integrality=integ, bounds=Bounds(lo, hi),
               options=dict(time_limit=time_limit, mip_rel_gap=0.002, presolve=True))
    if res.x is None:
        return None
    out = {n: res.x[ix[n]:ix[n] + T] for n in names}
    out["ok"] = True
    return out

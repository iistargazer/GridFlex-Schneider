"""Rolling-horizon MILP (open-source HiGHS via scipy). No Gurobi/CPLEX licence needed -> fits low-cost deployment."""
import numpy as np, scipy.sparse as sp
from scipy.optimize import milp, LinearConstraint, Bounds

NAMES = ["g", "ch", "dis", "soc", "u", "curt", "sc", "f", "b", "sf", "rs"]


def solve(P, pv, Dc, F, cap, price, soc0, b0, time_limit=6):
    """Decide per step: grid import g, battery ch/dis (binary u forbids both), curtailment, critical shed sc,
    flexible service f (deferrable; backlog b), flexible shed sf. Minimise cost + wear + weighted unserved energy."""
    T, dt = len(pv), P.dt
    ix = {n: i * T for i, n in enumerate(NAMES)}
    N = len(NAMES) * T
    I, S = sp.identity(T, format="csr"), sp.diags([np.ones(T - 1)], [-1], format="csr")
    Z = sp.csr_matrix((T, T))

    def row(**kw):
        return sp.hstack([kw.get(n, Z) for n in NAMES], format="csr")

    pmax = P.bat_kw
    smin, smax = P.soc_min_frac * P.bat_kwh, P.bat_kwh
    rhs_soc = np.zeros(T); rhs_soc[0] = soc0
    rhs_b = dt * F; rhs_b = rhs_b.copy(); rhs_b[0] += b0
    A = sp.vstack([
        row(g=I, dis=I, ch=-I, curt=-I, sc=I, f=-I),                                   # power balance
        row(soc=I - S, ch=-dt * P.eta * I, dis=dt / P.eta * I),                         # SOC dynamics
        row(b=I - S, f=dt * I, sf=dt * I),                                              # flexible backlog
        row(ch=I, u=-pmax * I),                                                         # ch <= Pmax*u
        row(dis=I, u=pmax * I),                                                         # dis <= Pmax*(1-u)
        row(soc=I, rs=I),                                                               # soft reserve: soc + rs >= reserve
    ], format="csr")
    lb = np.concatenate([Dc - pv, rhs_soc, rhs_b, np.full(T, -np.inf), np.full(T, -np.inf), np.full(T, P.reserve_frac * P.bat_kwh)])
    ub = np.concatenate([Dc - pv, rhs_soc, rhs_b, np.zeros(T), np.full(T, pmax), np.full(T, np.inf)])
    c = np.zeros(N)
    def put(n, v): c[ix[n]:ix[n] + T] += v
    put("g", price * dt); put("ch", P.deg_cost * dt / 2); put("dis", P.deg_cost * dt / 2)
    put("sc", P.voll_critical * dt); put("sf", P.voll_flex * dt); put("curt", P.curt_pen * dt); put("b", P.backlog_pen); put("rs", P.reserve_pen)
    c[ix["soc"] + T - 1] -= P.term_soc_val; c[ix["b"] + T - 1] += P.term_backlog
    lo, hi = np.zeros(N), np.zeros(N)
    def bnd(n, l, h): lo[ix[n]:ix[n] + T] = l; hi[ix[n]:ix[n] + T] = h
    bnd("g", 0, cap); bnd("ch", 0, pmax); bnd("dis", 0, pmax); bnd("soc", smin, smax); bnd("u", 0, 1)
    bnd("curt", 0, pv); bnd("sc", 0, Dc); bnd("f", 0, P.flex_rate_kw); bnd("b", 0, 1e4); bnd("sf", 0, P.flex_rate_kw); bnd("rs", 0, smax)
    integ = np.zeros(N); integ[ix["u"]:ix["u"] + T] = 1
    res = milp(c, constraints=LinearConstraint(A, lb, ub), integrality=integ, bounds=Bounds(lo, hi),
               options=dict(time_limit=time_limit, mip_rel_gap=0.005))
    if res.x is None:
        return None
    return {n: res.x[ix[n]:ix[n] + T] for n in NAMES}

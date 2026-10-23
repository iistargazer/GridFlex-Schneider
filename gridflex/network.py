"""LinDistFlow-lite model of the LT feeder behind one distribution transformer.

Three radial branches, balanced, constant power factor. For branch b carrying
P_b = share_b * P_import, the per-unit voltage drop at the branch end is

    dv_b = (R_b * P_b + X_b * Q_b) / (V_kv^2 * 1000)     [pu, P in kW]

which is linear in the transformer import, so it becomes a simple bound on
grid import inside the MILP. Technical loss proxy is sum_b 3 I_b^2 R_b.

This is deliberately a *lite* model: no phase imbalance, no PV located at
branch ends, no shunt capacitance. It is enough to show the evening dip and the
noon rise and to make the voltage limit bind at realistic loading; it is not a
substitute for a load-flow study.
"""
import numpy as np

from .config import P


def branch_k(p: P):
    """pu voltage drop per kW of transformer import, per branch."""
    tanphi = np.tan(np.arccos(p.power_factor))
    k = []
    for L, share in zip(p.branch_km, p.branch_share):
        r, x = p.r_ohm_per_km * L, p.x_ohm_per_km * L
        k.append(share * (r + x * tanphi) / (0.415 ** 2 * 1000.0))
    return np.array(k)


def import_limits(p: P):
    """(max import kW, max export kW) allowed by the voltage band."""
    k = branch_k(p).max()
    g_max = (1.0 - p.v_min_pu) / k if k > 0 else np.inf
    g_export = (p.v_max_pu - 1.0) / k if k > 0 else 0.0
    return float(g_max), float(g_export)


def voltages(p: P, g):
    """Per-branch end-of-feeder voltage (pu) for an import series g (kW)."""
    k = branch_k(p)
    return 1.0 - np.outer(np.asarray(g, float), k)


def loss_kw(p: P, g):
    """Technical loss proxy (kW) for transformer import g (kW)."""
    g = np.asarray(g, float)
    out = np.zeros_like(g)
    for L, share in zip(p.branch_km, p.branch_share):
        r = p.r_ohm_per_km * L
        P_b = share * g
        I = P_b / (np.sqrt(3) * 0.415 * p.power_factor)      # A (P in kW)
        out += 3 * I ** 2 * r / 1000.0
    return out


def energy_loss_pct(p: P, g, served):
    """Losses as % of energy served (kWh basis)."""
    g = np.asarray(g, float)
    served = np.asarray(served, float)
    e_loss = float(loss_kw(p, g).sum() * p.dt)
    e_served = float(served.sum() * p.dt)
    return 100.0 * e_loss / max(e_served, 1e-9)


def voltage_summary(p: P, g):
    v = voltages(p, g)
    return dict(v_min_pu=float(v.min()), v_max_pu=float(v.max()),
                violations=int(((v < p.v_min_pu - 1e-6) | (v > p.v_max_pu + 1e-6)).sum()))

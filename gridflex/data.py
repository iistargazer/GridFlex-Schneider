"""Synthetic but India-shaped neighbourhood data: 15-min PV, critical load, flexible load, NWP forecasts, feeder cap."""
import numpy as np, pandas as pd


def _g(h, mu, sd):
    return np.exp(-0.5 * ((h - mu) / sd) ** 2)


def make_data(P, seed=7):
    rng = np.random.default_rng(seed)
    n = P.n_days * 96
    idx = pd.date_range("2026-04-01", periods=n, freq="15min")
    h = idx.hour.values + idx.minute.values / 60
    day = np.arange(n) // 96
    # --- weather
    ar = np.zeros(P.n_days)
    for d in range(1, P.n_days):
        ar[d] = 0.6 * ar[d - 1] + rng.normal(0, 0.6)
    daycf = np.clip(0.8 + 0.22 * ar, 0.25, 1.0)
    x = np.zeros(n)
    for t in range(1, n):
        x[t] = 0.9 * x[t - 1] + rng.normal(0, 0.05 + 0.12 * (1 - daycf[day[t]]))
    cf = np.clip(daycf[day] + x, 0.05, 1.05)
    cs = 1000 * np.clip(np.sin(np.pi * (h - 6) / 12), 0, None) ** 1.2
    ghi = cs * cf
    temp = 32 + 6 * np.sin(2 * np.pi * (h - 9) / 24) + rng.normal(0, 1.5, P.n_days)[day] + rng.normal(0, .3, n)
    pv = P.pv_kwp * 0.78 * ghi / 1000
    ghi_fc = cs * np.clip(0.5 * cf + 0.5 * daycf[day] + rng.normal(0, 0.1, n), 0, 1.05)  # imperfect NWP
    temp_fc = temp + rng.normal(0, 1.0, n)
    # --- load (kW, aggregate of n_hh households)
    wk = (idx.dayofweek.values >= 5).astype(float)
    crit = 0.12 + 0.08 * _g(h, 7.5, 1.2) + 0.30 * _g(h, 20.5, 2.0) + 0.06 * _g(h, 13, 2.5)
    crit = crit * (1 + 0.03 * (temp - 32)) * (1 + 0.06 * wk)
    flex = (0.10 * _g(h, 6.5, .8) + 0.05 * _g(h, 6.0, .7) + 0.08 * _g(h, 10.5, 1.3)
            + 0.05 * _g(h, 18, 1.0) + 0.14 * _g(h, 21, 1.5)) * (1 + 0.3 * wk * _g(h, 11, 3))
    noise = lambda s: 1 + np.convolve(rng.normal(0, s, n), np.ones(3) / 3, "same")
    dayfx = rng.normal(1, 0.05, P.n_days)[day]
    Dc = P.n_hh * crit * noise(0.07) * dayfx
    F = P.n_hh * flex * noise(0.12)
    # --- feeder import capacity (DISCOM): planned evening stress windows (known) + unplanned outages (unknown)
    cap_plan = np.full(n, P.cap_normal)
    cap = cap_plan.copy()
    for d in range(P.n_days):
        base = d * 96
        if rng.random() < 0.45:
            cap_plan[base + 74: base + 90] = P.cap_stress  # 18:30-22:30
        for _ in range(rng.poisson(0.6)):
            s = int(rng.choice([rng.integers(68, 92), rng.integers(0, 96)], p=[0.6, 0.4]))
            dur = int(rng.integers(2, 9))
            a = base + s
            cap[a: min(a + dur, base + 96)] = 0.0
    cap = np.minimum(cap, cap_plan)
    price = np.where((h >= 18) & (h < 22), P.tariff_peak, np.where((h >= 6) & (h < 18), P.tariff_normal, P.tariff_offpeak))
    return pd.DataFrame(dict(pv=pv, Dc=Dc, F=F, temp=temp, ghi_fc=ghi_fc, temp_fc=temp_fc,
                             cap_plan=cap_plan, cap=cap, price=price, hour=h,
                             dow=idx.dayofweek.values), index=idx)

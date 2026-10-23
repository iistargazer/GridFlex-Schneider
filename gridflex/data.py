"""Neighbourhood dataset: real weather, calibrated-synthetic load, calibrated outages.

What is real / calibrated / simulated (this is carried into results.json and the
dashboard so nothing is over-claimed):

  real          weather (ERA5 reanalysis), day-ahead NWP (archived Open-Meteo
                operational forecast), PV (modelled from real GHI, validated
                against PVGIS within ~3 %)
  calibrated    critical + flexible load shapes anchored to Telangana LT-I
                monthly consumption and a published Indian residential shape
  simulated     outage process calibrated so the grid-only baseline sees the
                CEEW-measured 3.5 outage h/day of a notified town area
  assumption    DISCOM stress windows, tariffs, all prices (see config.PROVENANCE)

Flexible demand is *windowed*: each class has a window, a daily energy request
and a service-rate cap. Requests are treated as declared by households at the
start of the window (no forecast needed), which is also how a real aggregator
would receive them.
"""
import numpy as np
import pandas as pd

from .config import P
from .weather import load_cache

# flexible-load classes: name -> (start hour, end hour, rate kW, kWh per hh/day)
FLEX = {
    "pump": (9.0, 16.0, 60.0, 0.35),      # water pumping / washing
    "hotwater": (5.0, 8.0, 40.0, 0.55),   # geysers
    "ev": (21.0, 6.0, 40.0, 0.30),        # e-rickshaw / 2W charging (crosses midnight)
}


def _g(h, mu, sd):
    return np.exp(-0.5 * ((h - mu) / sd) ** 2)


def _ar1(rng, n, rho=0.85, sd=1.0):
    x = np.zeros(n)
    for i in range(1, n):
        x[i] = rho * x[i - 1] + rng.normal(0, sd)
    return x


def make_data(P, seed=7):
    rng = np.random.default_rng(seed)
    w = load_cache()
    if len(w) != P.n_days * 96:
        raise ValueError(f"weather cache has {len(w)} steps, expected {P.n_days * 96}; "
                         "rebuild with python -m gridflex.weather --refresh")
    idx = w.index
    h = idx.hour.values + idx.minute.values / 60
    day = np.arange(len(w)) // 96
    temp = w.temp.values
    dow = idx.dayofweek.values
    wk = (dow >= 5).astype(float)

    # ---------------- critical load (calibrated-synthetic) ----------------
    shape = (0.10 + 0.075 * _g(h, 7.5, 1.2) + 0.30 * _g(h, 20.5, 2.0)
             + 0.055 * _g(h, 13.0, 2.5))
    shape = shape * (1 + 0.035 * (temp - 30.0)) * (1 + 0.05 * wk)
    dayfx = 1 + 0.04 * _ar1(rng, P.n_days, 0.5)
    cols = {}
    total_w = sum(s * m for _, s, m, _ in P.archetypes)
    for name, share, mult, _pv in P.archetypes:
        noise = 1 + _ar1(rng, len(w), 0.8, 0.05)
        cols[name] = P.n_hh * share * (mult / total_w) * shape * dayfx[day] * noise
    Dc = sum(cols.values())

    # ---------------- flexible requests (windowed) -----------------------
    df = pd.DataFrame(index=idx)
    for name, (a, b, rate, per_hh) in FLEX.items():
        e = np.zeros(len(w))
        starts = (h >= a) & (h < min(b, 24)) if b > a else (h >= a) | (h < b)
        # arrivals at the window start: a single energy block per day
        start_steps = np.where(np.isclose(h, a))[0]
        for s in start_steps:
            weekend = 1.25 if dow[s] >= 5 else 1.0
            draw = rng.normal(1.0, 0.12)
            e[s] = max(0.0, per_hh * P.n_hh * weekend * draw)
        df[f"E_{name}"] = e
        df[f"rate_{name}"] = np.where(starts, rate, 0.0)
    df["Dc"] = Dc
    df["F"] = 0.0

    # ---------------- feeder capacity ------------------------------------
    n = len(w)
    cap_plan = np.full(n, P.cap_normal_kw)
    is_stress = np.zeros(n, bool)
    for d in range(P.n_days):
        if rng.random() < P.stress_day_prob:
            s = d * 96 + int(18.5 * 4)
            cap_plan[s:s + 16] = P.cap_stress_kw      # 18:30-22:30
            is_stress[s:s + 16] = True

    # unannounced outages, calibrated to the CEEW outage-hours target
    rate = P.outage_h_per_day / P.outage_mean_duration_h
    outage = np.zeros(n, bool)
    for d in range(P.n_days):
        for _ in range(rng.poisson(rate)):
            dur = float(np.clip(rng.exponential(P.outage_mean_duration_h), 0.5, 5.0))
            start = d * 96 + int(rng.integers(0, 96))
            k = int(round(dur * 4))
            outage[start:min(start + k, d * 96 + 96)] = True
    cap = np.minimum(cap_plan, np.where(outage, 0.0, cap_plan))

    if P.tariff_mode == "tou":
        price = np.where((h >= 18) & (h < 22), P.tariff_peak,
                         np.where((h >= 6) & (h < 18), P.tariff_flat,
                                  P.tariff_offpeak))
    else:
        price = np.full(n, P.tariff_flat)

    for k, v in cols.items():
        df[f"Dc_{k}"] = v
    df["pv"] = w.pv.values
    df["ghi"] = w.ghi.values
    df["temp"] = temp
    df["ghi_fc"] = w.ghi_fc.values
    df["temp_fc"] = w.temp_fc.values
    df["cap_plan"] = cap_plan
    df["is_stress"] = is_stress
    df["is_outage"] = outage
    df["cap"] = cap
    df["price"] = price
    df["hour"] = h
    df["dow"] = dow
    df["outage_hours"] = float(outage.mean() * 24.0)

    # per-day realised outage hours (used by the calibration report)
    return df


def flex_windows(df, t, horizon, served):
    """Windows visible from step t, with energy remaining to be served.

    `served` maps (class, window_start_step) -> kWh already delivered.
    Returns one dict per window whose deadline is after t and whose start is
    inside the horizon.
    """
    n = len(df)
    H = df.index
    out = []
    for name, (a, b, rate, _per_hh) in FLEX.items():
        for s in range(max(0, t - 96), min(n, t + horizon)):
            h = H[s].hour + H[s].minute / 60
            if not np.isclose(h, a):
                continue
            span = (b - a) if b > a else (24 - a + b)
            e = float(df[f"E_{name}"].iloc[s])
            if e <= 0:
                continue
            end = s + int(round(span * 4))
            if end <= t:
                continue
            done = served.get((name, s), 0.0)
            out.append(dict(cls=name, start=s, end=min(end, n), energy=max(0.0, e - done),
                            rate=rate, key=(name, s)))
    return out

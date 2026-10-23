"""Direct multi-horizon forecasters (gradient-boosted trees, quantile loss).

Features are known at decision time only: calendar terms for the target step,
lead time, the archived day-ahead NWP forecast (GHI and temperature), the value
at the same clock time yesterday, and the last observation / 4-step mean at the
decision origin. No target-step observation is ever used.

`PersistenceForecaster` is the no-ML ablation: "same time yesterday".
"""
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor as HGB

SPEC = [("pv", .5), ("pv", .1), ("pv", .9), ("Dc", .1), ("Dc", .5), ("Dc", .9)]


def pinball(y, qhat, q):
    d = y - qhat
    return float(np.mean(np.maximum(q * d, (q - 1) * d)))


class Forecaster:
    def __init__(self, df, train_end, pv_kwp=100.0, seed=0):
        self.df, self.n, self.pv_kwp = df, len(df), pv_kwp
        self.y = {k: np.array(df[k].values, dtype=float) for k in ("pv", "Dc")}
        self.y4 = {k: pd.Series(v).rolling(4, min_periods=1).mean().values
                   for k, v in self.y.items()}
        # persistence anchor: same clock time yesterday (available at decision time)
        self.lag = {k: np.concatenate([np.zeros(96), v[:-96]]) for k, v in self.y.items()}
        self.ghi, self.tf, self.dow = (df.ghi_fc.values, df.temp_fc.values,
                                       df.dow.values)
        rng = np.random.default_rng(seed)
        tau = np.repeat(np.arange(96, train_end), 3)
        h = rng.integers(1, 97, len(tau))
        self.models = {}
        for name, q in SPEC:
            X = self._X(name, tau, tau - h, h)
            target = self.y[name][tau] - self.lag[name][tau]
            self.models[(name, q)] = HGB(loss="quantile", quantile=q, max_iter=200,
                                         learning_rate=0.07, min_samples_leaf=20,
                                         random_state=seed).fit(X, target)

    def _X(self, name, tau, t0, h):
        y = self.y[name]
        ang = (tau % 96) / 96 * 2 * np.pi
        t0 = np.maximum(t0, 0)
        return np.column_stack([
            np.sin(ang), np.cos(ang), self.dow[tau], h,
            self.ghi[tau], self.tf[tau],
            y[np.maximum(tau - 96, 0)], y[np.maximum(t0 - 1, 0)],
            self.y4[name][np.maximum(t0 - 1, 0)],
        ])

    def predict(self, name, q, t, T):
        tau = np.arange(t, t + T)
        h = tau - (t - 1)
        out = self.models[(name, q)].predict(self._X(name, tau, np.full(T, t - 1), h))
        out = out + self.lag[name][tau]          # forecast = persistence + learned correction
        out = np.maximum(out, 0.0)
        if name == "pv":
            # physical ceiling: cannot exceed rated output at the forecast irradiance
            out = np.minimum(out, self.pv_kwp * 0.9 * np.minimum(1.0, self.ghi[tau] / 1000.0))
        return out

    def evaluate(self, lo, hi, step=4):
        mape, pv_pe, cpv, cdc = [], [], [], []
        pi = {"pv10": [], "dc90": []}
        pv_max = max(float(self.y["pv"].max()), 1e-9)
        for t in range(lo, hi - 96, step):
            D50 = self.predict("Dc", .5, t, 96)
            D10 = self.predict("Dc", .1, t, 96)
            D90 = self.predict("Dc", .9, t, 96)
            P50 = self.predict("pv", .5, t, 96)
            P10 = self.predict("pv", .1, t, 96)
            P90 = self.predict("pv", .9, t, 96)
            A = self.y["Dc"][t:t + 96]
            Apv = self.y["pv"][t:t + 96]
            mape.append(np.mean(np.abs(D50 - A) / np.maximum(A, 1e-9)))
            pv_pe.append(np.mean(np.abs(P50 - Apv)) / pv_max)
            cpv.append(float(np.mean((Apv >= P10) & (Apv <= P90))))
            cdc.append(float(np.mean((A >= D10) & (A <= D90))))
            pi["pv10"].append(pinball(Apv, P10, .1))
            pi["dc90"].append(pinball(A, D90, .9))
        return dict(load_mape_pct=float(100 * np.mean(mape)),
                    pv_nmae_pct=float(100 * np.mean(pv_pe)),
                    pv_coverage80_pct=float(100 * np.mean(cpv)),
                    load_coverage80_pct=float(100 * np.mean(cdc)),
                    pinball_pv_q10=float(np.mean(pi["pv10"])),
                    pinball_dc_q90=float(np.mean(pi["dc90"])))


class PersistenceForecaster:
    """Predict the value at the same clock time yesterday."""

    def __init__(self, df):
        self.y = {k: np.array(df[k].values, dtype=float) for k in ("pv", "Dc")}
        self.n = len(df)

    def predict(self, name, q, t, T):
        # same point forecast for every quantile, widened by a fixed empirical
        # spread so the risk-hedging controller treats both forecast sources alike
        spread = {("pv", .1): 0.80, ("pv", .9): 1.20,
                  ("Dc", .1): 0.85, ("Dc", .9): 1.18}.get((name, q), 1.0)
        tau = np.arange(t, t + T)
        src = np.clip(tau - 96, 0, self.n - 1)
        return np.maximum(self.y[name][src] * spread, 0.0)

    def evaluate(self, lo, hi, step=4):
        mape, pv_pe = [], []
        pv_max = max(float(self.y["pv"].max()), 1e-9)
        for t in range(lo, hi - 96, step):
            D = self.predict("Dc", .5, t, 96)
            P50 = self.predict("pv", .5, t, 96)
            A = self.y["Dc"][t:t + 96]
            Apv = self.y["pv"][t:t + 96]
            mape.append(np.mean(np.abs(D - A) / np.maximum(A, 1e-9)))
            pv_pe.append(np.mean(np.abs(P50 - Apv)) / pv_max)
        return dict(load_mape_pct=float(100 * np.mean(mape)),
                    pv_nmae_pct=float(100 * np.mean(pv_pe)),
                    pv_coverage80_pct=None, load_coverage80_pct=None,
                    pinball_pv_q10=None, pinball_dc_q90=None)

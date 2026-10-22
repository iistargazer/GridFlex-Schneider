"""Direct multi-horizon forecasters (gradient-boosted trees, quantile loss). Features are known at decision time only."""
import numpy as np, pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor as HGB

SPEC = [("pv", .5), ("pv", .1), ("Dc", .5), ("Dc", .9), ("F", .5)]


class Forecaster:
    def __init__(self, df, train_end, seed=0):
        self.df, self.n = df, len(df)
        self.y = {k: df[k].values for k in ("pv", "Dc", "F")}
        self.y4 = {k: pd.Series(v).rolling(4, min_periods=1).mean().values for k, v in self.y.items()}
        self.ghi, self.tf, self.dow = df.ghi_fc.values, df.temp_fc.values, df.dow.values
        rng = np.random.default_rng(seed)
        tau = np.repeat(np.arange(100, train_end), 3)
        h = rng.integers(1, 97, len(tau))
        self.models = {}
        for name, q in SPEC:
            X = self._X(name, tau, tau - h)
            self.models[(name, q)] = HGB(loss="quantile", quantile=q, max_iter=150, learning_rate=0.08,
                                         random_state=seed).fit(X, self.y[name][tau])

    def _X(self, name, tau, t0):
        y, ang = self.y[name], (tau % 96) / 96 * 2 * np.pi
        return np.column_stack([np.sin(ang), np.cos(ang), self.dow[tau], tau - t0, self.ghi[tau], self.tf[tau],
                                y[tau - 96], y[t0], self.y4[name][t0]])

    def predict(self, name, q, t, T):
        """Forecast steps t..t+T-1 using observations up to t-1."""
        tau = np.arange(t, t + T)
        out = self.models[(name, q)].predict(self._X(name, tau, np.full(T, t - 1)))
        out = np.maximum(out, 0)
        if name == "pv":
            out = np.minimum(out, self.df.ghi_fc.values[tau] * 0.1)  # PV can't exceed NWP-based ceiling
        return out

    def evaluate(self, lo, hi, step=4):
        """Day-ahead accuracy over origins in [lo,hi): MAPE (total load) and PV nMAE (% of kWp)."""
        ape, pe, pv_pe = [], [], []
        for t in range(lo, hi - 96, step):
            L = self.predict("Dc", .5, t, 96) + self.predict("F", .5, t, 96)
            A = self.y["Dc"][t:t + 96] + self.y["F"][t:t + 96]
            ape.append(np.mean(np.abs(L - A) / A))
            pv_pe.append(np.mean(np.abs(self.predict("pv", .5, t, 96) - self.y["pv"][t:t + 96])) / self.y["pv"].max())
        return dict(load_mape_pct=100 * np.mean(ape), pv_nmae_pct=100 * np.mean(pv_pe))

"""python run.py [--oracle]  ->  outputs/results.json, outputs/dashboard.html, outputs/*.png"""
import json, sys, time, numpy as np
from gridflex.config import P
from gridflex.data import make_data
from gridflex.forecast import Forecaster
from gridflex.simulate import run, metrics
from gridflex.economics import unit_economics
from gridflex.report import make_dashboard, make_plots

P_ = P(); df = make_data(P_)
tr = (P_.n_days - P_.n_test_days) * 96
t = time.time(); fc = Forecaster(df, tr)
acc = fc.evaluate(tr, len(df)); print("forecast (day-ahead, held-out):", acc)
runs = {m: run(P_, df, fc, m, tr, len(df)) for m in ("status_quo", "unmanaged", "gridflex")}
if "--oracle" in sys.argv:
    runs["oracle"] = run(P_, df, fc, "gridflex", tr, len(df), oracle=True)
M = {k: {a: float(b) for a, b in metrics(P_, v).items()} for k, v in runs.items()}
econ = unit_economics(P_, M["unmanaged"], M["gridflex"])
for k, v in M.items(): print(k, {a: round(b, 2) for a, b in v.items()})
print("economics", {a: round(b, 1) for a, b in econ.items()})
json.dump(dict(forecast=acc, metrics=M, economics=econ, config=P_.__dict__), open("outputs/results.json", "w"), indent=1, default=float)
make_dashboard(P_, runs, M, econ, acc, "outputs/dashboard.html"); make_plots(P_, runs, M, "outputs")
print("done in", round(time.time() - t), "s")

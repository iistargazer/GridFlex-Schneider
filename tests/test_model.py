"""Focused tests for the simulation's invariants and the decision logic."""
import numpy as np
import pandas as pd
import pytest
from dataclasses import replace

from gridflex.config import P
from gridflex.data import FLEX, make_data
from gridflex.economics import annual_cost, unit_economics
from gridflex.equity import allocate, groups, jain
from gridflex.network import import_limits, loss_kw, voltages
from gridflex.simulate import Bat, metrics, run


def mini(seed=3, days=2, outage=True):
    """Small deterministic dataset with the same schema as make_data()."""
    n = days * 96
    idx = pd.date_range("2026-09-01", periods=n, freq="15min", tz="Asia/Kolkata")
    h = idx.hour.values + idx.minute.values / 60
    rng = np.random.default_rng(seed)
    shape = 0.12 + 0.25 * np.exp(-0.5 * ((h - 20) / 2) ** 2) + 0.05 * np.exp(-0.5 * ((h - 8) / 1.5) ** 2)
    df = pd.DataFrame(index=idx)
    df["Dc"] = 15 * shape * (1 + 0.02 * rng.normal(size=n))
    df["Dc_low_income"] = 0.45 * df.Dc * 0.65
    df["Dc_lower_middle"] = 0.35 * df.Dc
    df["Dc_middle"] = df.Dc - df.Dc_low_income - df.Dc_lower_middle
    df["pv"] = 70 * np.clip(np.sin(np.pi * (h - 6) / 12), 0, None) ** 1.2
    df["ghi"] = 900 * np.clip(np.sin(np.pi * (h - 6) / 12), 0, None)
    df["ghi_fc"] = df.ghi
    df["temp"] = 28 + 3 * np.sin(2 * np.pi * (h - 9) / 24)
    df["temp_fc"] = df.temp + 0.5
    for cls, (a, b, rate, per_hh) in FLEX.items():
        df[f"E_{cls}"] = 0.0
        df.loc[np.isclose(h, a), f"E_{cls}"] = per_hh * 80
        df[f"rate_{cls}"] = np.where((h >= a) & (h < b) if b > a else (h >= a) | (h < b), rate, 0.0)
    df["cap_plan"] = np.where((h >= 18.5) & (h < 22.5), 25.0, 80.0)
    df["cap"] = df.cap_plan.copy()
    df["is_stress"] = (h >= 18.5) & (h < 22.5)
    df["is_outage"] = False
    if outage:
        df.iloc[100:112, df.columns.get_loc("cap")] = 0.0
        df.iloc[100:112, df.columns.get_loc("is_outage")] = True
    df["price"] = 7.0
    df["hour"] = h
    df["dow"] = idx.dayofweek.values
    return df


@pytest.mark.parametrize("mode", ["grid_only", "pv_batt_naive", "mpc_full"])
def test_energy_balance_and_limits(mode):
    p = replace(P(), n_test_days=2, H=96, resolve_every=8)
    df = mini()
    r = run(p, df, None, mode, 0, 96)
    assert r.attrs["balance_max_error_kw"] < 1e-6
    assert r.attrs["cap_violations"] == 0
    assert (r.shed_c >= -1e-9).all() and (r.shed_f >= -1e-9).all()
    if mode != "grid_only":
        assert (r.soc >= p.soc_min_frac * p.bat_kwh - 1e-6).all()
        assert (r.soc <= p.bat_kwh + 1e-6).all()
    assert (r.g <= r.cap + 1e-6).all()
    assert (r.g >= -1e-9).all()


def test_milp_respects_flexible_windows():
    p = replace(P(), n_test_days=2, H=96, resolve_every=8)
    df = mini()
    r = run(p, df, None, "mpc_full", 0, 96)
    for cls in FLEX:
        served = float(r[f"f_{cls}"].sum() * p.dt)
        requested = float(df[f"E_{cls}"].sum())
        assert served <= requested + 1e-6
        outside = r[f"f_{cls}"][df[f"rate_{cls}"].values[:96] == 0]
        assert float(outside.abs().sum()) < 1e-6


def test_mpc_fallback_when_infeasible(monkeypatch):
    import gridflex.simulate as sim
    monkeypatch.setattr(sim, "solve", lambda *a, **k: None)
    p = replace(P(), n_test_days=2)
    df = mini()
    r = sim.run(p, df, None, "mpc_full", 0, 96)
    assert len(r) == 96
    assert metrics(p, r)["critical_served_pct"] > 50


def test_battery_limits():
    p = P()
    b = Bat(p, True)
    assert b.apply(1000) <= p.bat_kw
    assert b.soc >= p.soc_min_frac * p.bat_kwh - 1e-6
    b2 = Bat(p, True)
    assert b2.apply(-1000) >= -p.bat_kw
    assert b2.soc <= p.bat_kwh + 1e-6
    off = Bat(p, False)
    assert off.apply(10) == 0.0


def test_metrics_non_negative():
    p = replace(P(), n_test_days=2)
    r = run(p, mini(), None, "mpc_full", 0, 96)
    m = metrics(p, r)
    for k in ("critical_served_pct", "outage_hours_per_day", "unserved_critical_kwh_per_day",
              "flex_unserved_kwh_per_day", "curtailment_pct", "loss_pct"):
        assert m[k] >= -1e-9
    assert 0 <= m["critical_served_pct"] <= 100


def test_equity_equal_per_household():
    served = allocate(10.0, np.array([12.0, 8.0, 6.0]), np.array([36, 28, 16]))
    per_hh = served / np.array([36, 28, 16])
    assert np.allclose(per_hh[served > 0], per_hh[served > 0][0], atol=1e-6)
    assert (served <= np.array([12.0, 8.0, 6.0]) + 1e-9).all()
    assert abs(served.sum() - 10.0) < 1e-6
    assert jain([100, 100, 100]) == pytest.approx(1.0)
    assert jain([100, 50, 50]) < 1.0


def test_network_voltage_and_loss():
    p = P()
    gmax, gexp = import_limits(p)
    assert gmax > 0 and gexp > 0
    v_low = voltages(p, [60.0])[0]
    v_high = voltages(p, [10.0])[0]
    assert (v_low < v_high).all()
    assert loss_kw(p, [60.0])[0] > loss_kw(p, [10.0])[0]
    assert v_low.min() >= p.v_min_pu - 1e-9


def test_economics_ranges():
    p = P()
    ac = annual_cost(p)
    assert ac["per_hh_month_inr"] > 0
    m = dict(bill_inr_per_hh_month=400.0, unserved_critical_kwh_per_day=10.0,
             evening_peak_import_kw=40.0, critical_served_pct=97.0,
             critical_served_kwh_per_day=320.0)
    m2 = dict(m, bill_inr_per_hh_month=390.0, unserved_critical_kwh_per_day=4.0,
              evening_peak_import_kw=30.0, critical_served_pct=99.0,
              critical_served_kwh_per_day=325.0)
    e = unit_economics(p, m, m2, dict(m, bill_inr_per_hh_month=900.0))
    assert e["net_value_range_inr"][0] <= e["net_value_range_inr"][1]
    assert e["cost_per_kwh_unserved_avoided_inr"] > 0
    assert 0 <= e["fee_tiers"]["gross_cost_recovery_pct"] <= 100


def test_data_quality_and_calibration():
    p = P()
    df = make_data(p, seed=7)
    assert len(df) == p.n_days * 96
    assert not df[["pv", "Dc", "cap"]].isna().any().any()
    assert df.pv.max() <= p.pv_kwp + 1e-6
    assert 2.0 <= df.is_outage.mean() * 24 <= 5.0
    assert (df.cap <= df.cap_plan + 1e-9).all()
    for cls in FLEX:
        assert df[f"E_{cls}"].sum() > 0
        assert (df[f"rate_{cls}"][df[f"E_{cls}"] > 0] > 0).all()
    assert set(["low_income", "lower_middle", "middle"]).issubset(
        [c.replace("Dc_", "") for c in df.columns if c.startswith("Dc_")])


def test_forecaster_does_not_leak_future():
    """Overwriting every observation at and after the decision origin must not
    change the forecast: only t-1 and earlier may be used."""
    from gridflex.forecast import Forecaster
    df = make_data(P(), seed=7)
    t0 = P().train_end()
    fc = Forecaster(df, t0, pv_kwp=100)
    t = t0 + 96
    before = fc.predict("Dc", .5, t, 24).copy()
    for name in ("pv", "Dc"):
        fc.y[name][t:] = 1e6
    after = fc.predict("Dc", .5, t, 24)
    assert np.allclose(before, after)


def test_groups_sum_to_neighbourhood():
    p = P()
    g = groups(p)
    assert sum(n for _, n, _, _ in g) == p.n_hh
    weighted = sum(share * m for (_, share, _, _), (_, _, m, _) in zip(p.archetypes, g))
    assert abs(weighted - 1.0) < 1e-9


def _stressed(df):
    """Same dataset, tight evening limit: forces a shortfall to allocate."""
    df = df.copy()
    h = df.index.hour
    df["cap"] = np.where((h >= 18) & (h < 22), 2.0, df["cap"])
    return df


def test_discom_actions_are_derived_and_ranked():
    from gridflex.discom import console
    p = replace(P(), n_test_days=2, resolve_every=8, enforce_voltage=False)
    df = mini()
    r = run(p, df, None, "mpc_full", 0, 192)
    base = run(p, df, None, "pv_batt_naive", 0, 192)
    c = console(p, df, r, metrics(p, r), 0, r_base=base)
    acts = c["dr_actions"]
    assert acts, "console must recommend at least one action on a normal day"
    assert [a["rank"] for a in acts] == list(range(1, len(acts) + 1))
    assert all(a["credit_inr"] == a["credit_inr"] for a in acts)   # not NaN
    assert [a["credit_inr"] for a in acts] == sorted(
        [a["credit_inr"] for a in acts], reverse=True)
    assert all(a["kw"] >= 0 and a["kwh"] >= 0 for a in acts)
    d = r.iloc[-96:]
    assert c["loss_kwh_per_day"] == pytest.approx(float(d.loss.sum() * p.dt), rel=1e-6)
    assert (c["loss_kwh_per_day"] > 0) == bool((d.g > 0).any())
    # every action cites a physical basis and a rupee valuation
    assert all(a["basis"] and "tariff" in a["basis"] or "rate" in a["basis"]
               or "feed-in" in a["basis"] or "lost load" in a["basis"] for a in acts)


def test_sizing_lifeline_axis_moves_the_frontier():
    from gridflex.equity import archetype_metrics
    from gridflex.sizing import pareto, sweep, with_reliability_value
    p = replace(P(), n_test_days=2, resolve_every=8, enforce_voltage=False)
    df = mini()
    rows = sweep(p, df, None, [(40, 20, "lifeline"), (40, 20, "flat")],
                 96, 192, resolve_every=8)
    base = run(p, df, None, "pv_batt_naive", 96, 192)
    rows = with_reliability_value(rows, p, metrics(p, base),
                                  archetype_metrics(base, p))
    assert {r["fee_scheme"] for r in rows} == {"lifeline", "flat"}
    a, b = rows[0], rows[1]
    # identical dispatch, so the two points differ by exactly the fee
    assert a["cost_per_hh_month_inr"] == pytest.approx(b["cost_per_hh_month_inr"])
    assert (b["net_cost_low_income_per_hh_month_inr"]
            - a["net_cost_low_income_per_hh_month_inr"]) == pytest.approx(60.0)
    assert a["net_cost_low_income_per_hh_month_inr"] <= a["net_cost_per_hh_month_inr"]
    assert pareto(rows)


def test_allocation_rule_is_measurable():
    from gridflex.equity import archetype_metrics
    p = replace(P(), n_test_days=2, resolve_every=8, enforce_voltage=False,
                bat_kwh=0.0, bat_kw=0.0)
    df = _stressed(mini())
    eq = run(p, df, None, "mpc_full", 0, 192, rule="equal")
    pr = run(p, df, None, "mpc_full", 0, 192, rule="proportional")
    me, mp = archetype_metrics(eq, p, "equal"), archetype_metrics(pr, p, "proportional")
    # the same shortfall, allocated differently: the equal rule favours low income
    assert float(eq.shed_c.sum()) == pytest.approx(float(pr.shed_c.sum()))
    assert me["low_income"]["critical_served_pct"] > mp["low_income"]["critical_served_pct"]
    assert me["fairness"]["low_income_gap_pp"] > mp["fairness"]["low_income_gap_pp"]
    assert mp["fairness"]["jain_index"] >= me["fairness"]["jain_index"] - 1e-9
    assert me["fairness"]["jain_index"] != pytest.approx(mp["fairness"]["jain_index"])
    # self-consumption is metered, so it cannot exceed 100 % or go negative
    for m in (me, mp):
        for k, v in m.items():
            if k != "fairness":
                assert 0 <= v["self_consumption_pct"] <= 100

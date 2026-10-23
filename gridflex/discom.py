"""DISCOM-facing view: feeder risk, loading, technical-loss proxy and DR actions.

The risk forecast is deliberately transparent: outage probability by hour from
the observed outage history of this feeder, applied to the forecast net load.
It is not a black box and it does not pretend to predict unannounced outages;
it quantifies the exposure and the local resources available to cover it.

Every action and every credit below is read off the simulated dispatch for the
selected day; nothing is inferred from an archetype definition. Credits use the
same config prices as the unit-economics table (energy at the flat tariff,
export at the feed-in tariff, peak capacity at the DISCOM rate, unserved energy
at the value of lost load), so the console and the economics tab agree.
"""
import numpy as np

from .config import P
from .data import FLEX


def outage_probability(df, t0):
    """P(outage) by hour of day from the training portion of this feeder."""
    train = df.iloc[:t0]
    p = train.groupby(train.index.hour)["is_outage"].mean().reindex(range(24)).fillna(0.0)
    stress = train.groupby(train.index.hour)["is_stress"].mean().reindex(range(24)).fillna(0.0)
    return p.values, stress.values


def feeder_risk(P, df, fc, t0, day_start):
    """Next-24 h risk profile for the DISCOM console (15-min resolution)."""
    H = 96
    pv = np.maximum(fc.predict("pv", .1, day_start, H), 0)
    Dc = fc.predict("Dc", .9, day_start, H)
    flex = np.array([sum(df[f"E_{c}"].values[day_start + i] for c in FLEX) / P.dt
                     for i in range(H)])
    cap = df["cap_plan"].values[day_start:day_start + H]
    p_out, p_stress = outage_probability(df, t0)
    hours = np.array([df.index[day_start + i].hour for i in range(H)])
    prob = np.clip(np.where(cap <= 0, 1.0, p_out[hours] + p_stress[hours]), 0.0, 1.0)
    net = Dc + flex - pv
    exposure = np.maximum(0.0, net - cap)
    shortfall = np.where(prob > 0, np.maximum(exposure, net * (cap > 0) * prob), 0.0)
    return dict(prob=prob.tolist(), exposure_kw=exposure.tolist(),
                expected_shortfall_kw=shortfall.tolist(),
                net_load_kw=net.tolist(), cap_kw=cap.tolist(),
                battery_available_kwh=P.bat_kwh * (1 - P.soc_min_frac),
                outage_probability_by_hour=p_out.tolist())


def _day_slice(r, n=96):
    return slice(max(0, len(r) - n), len(r))


def dr_actions(P, r, day_slice=None, r_base=None):
    """Ranked actions for the selected day, with kW, kWh and a rupee credit.

    Credit is the value the action created for that day under the config prices:
    solar charging avoids buying later at the tariff instead of exporting;
    discharging displaces imports; flexible loads served on solar displace
    imports; peak reduction earns the DISCOM capacity credit; curtailment and
    unserved energy are costs (negative credit).
    """
    if day_slice is None:
        day_slice = _day_slice(r)
    d = r.iloc[day_slice]
    if len(d) == 0:
        return []
    dt, acts = P.dt, []
    pv, dc = d.pv.values, d.Dc.values

    charge = d.ch.values
    solar_charge = float(np.minimum(charge, np.maximum(pv - dc, 0.0)).sum() * dt)
    if solar_charge > 0.5:
        acts.append(dict(
            action="charge the battery from rooftop solar",
            detail=f"{solar_charge:.0f} kWh absorbed instead of exported",
            kw=round(float(charge.max()), 1), kwh=round(solar_charge, 1),
            credit_inr=round(solar_charge * (P.tariff_flat - P.feed_in_tariff), 1),
            basis="avoided import at tariff minus forgone feed-in"))

    dis = d.dis.values
    dis_kwh = float(dis.sum() * dt)
    if dis_kwh > 0.5:
        stress = (d.is_stress | d.is_outage).values
        stress_kwh = float(dis[stress].sum() * dt)
        acts.append(dict(
            action="discharge the battery into the evening peak",
            detail=f"{dis_kwh:.0f} kWh, {stress_kwh:.0f} kWh while the feeder was constrained",
            kw=round(float(dis.max()), 1), kwh=round(dis_kwh, 1),
            credit_inr=round(dis_kwh * P.tariff_flat, 1),
            basis="displaced grid import at the tariff"))

    for cls in FLEX:
        f = d[f"f_{cls}"].values * dt
        solar = float(f[pv > dc].sum())
        total = float(f.sum())
        if solar > 0.5:
            acts.append(dict(
                action=f"run {cls.replace('_', ' ')} load in the solar window",
                detail=f"{total:.0f} kWh served, {solar:.0f} kWh while PV exceeded load",
                kw=round(float(d[f"f_{cls}"].max()), 1), kwh=round(solar, 1),
                credit_inr=round(solar * P.tariff_flat, 1),
                basis="solar-served flexible energy offsets import at the tariff"))

    ev = (d.index.hour >= 18) & (d.index.hour < 22)
    if r_base is not None and len(r_base) >= len(r) and ev.any():
        b = r_base.iloc[day_slice]
        cut = max(0.0, float(b.g[ev].max()) - float(d.g[ev].max()))
        if cut > 0.5:
            acts.append(dict(
                action="hold the evening feeder peak below the unmanaged case",
                detail=f"{cut:.1f} kW lower evening peak than the same PV+battery without control",
                kw=round(cut, 1), kwh=0.0,
                credit_inr=round(cut * P.discom_peak_value_inr_per_kw_month / 30, 1),
                basis="DISCOM avoided-capacity rate per kW-month / 30"))

    export_kwh = float(d.exp.sum() * dt)
    if export_kwh > 0.5:
        acts.append(dict(
            action="export surplus solar within the sanctioned limit",
            detail=f"{export_kwh:.0f} kWh exported",
            kw=round(float(d.exp.max()), 1), kwh=round(export_kwh, 1),
            credit_inr=round(export_kwh * P.feed_in_tariff, 1),
            basis="feed-in tariff"))

    curt_kwh = float(d.curt.sum() * dt)
    if curt_kwh > 0.5:
        acts.append(dict(
            action="curtailed surplus PV",
            detail=f"{curt_kwh:.0f} kWh wasted after the export limit",
            kw=round(float(d.curt.max()), 1), kwh=round(curt_kwh, 1),
            credit_inr=round(-curt_kwh * P.feed_in_tariff, 1),
            basis="forgone feed-in revenue"))

    shed_kwh = float(d.shed_c.sum() * dt)
    if shed_kwh > 0.5:
        acts.append(dict(
            action="critical load left unserved",
            detail=f"{shed_kwh:.0f} kWh could not be supplied",
            kw=round(float(d.shed_c.max()), 1), kwh=round(shed_kwh, 1),
            credit_inr=round(-shed_kwh * P.voll_household, 1),
            basis="value of lost load"))

    acts.sort(key=lambda a: a["credit_inr"], reverse=True)
    for i, a in enumerate(acts, 1):
        a["rank"] = i
    return acts


def console(P, df, r, M, t0, fc=None, r_base=None):
    """Console for the last simulated day; all slices are relative to the run."""
    day_slice = _day_slice(r)
    d = r.iloc[day_slice]
    if fc is None:
        from .forecast import PersistenceForecaster
        fc = PersistenceForecaster(df)
    loss_kwh_day = float(d.loss.sum() * P.dt) if len(d) else 0.0
    return dict(
        day=str(d.index[0].date()) if len(d) else None,
        participating_homes=P.n_hh,
        transformer_rating_kw=P.rating_kw,
        peak_import_kw=M["peak_import_kw"],
        evening_peak_import_kw=M["evening_peak_import_kw"],
        transformer_loading_pct=M["transformer_loading_pct"],
        loss_pct=M["loss_pct"],
        loss_kwh_per_day=round(loss_kwh_day, 2),
        loss_kw_at_peak=round(float(d.loss.iloc[int(np.argmax(d.g.values))]), 3)
        if len(d) else 0.0,
        loss_kw_peak=round(float(d.loss.max()), 3) if len(d) else 0.0,
        self_consumption_pct=M["self_consumption_pct"],
        saidi_minutes_per_day=M["saidi_minutes_per_day"],
        critical_served_pct=M["critical_served_pct"],
        evening_availability_pct=M["evening_availability_pct"],
        voltage_min_pu=M["voltage_min_pu"],
        voltage_violations=M["voltage_violations"],
        dr_actions=dr_actions(P, r, day_slice, r_base),
        risk=feeder_risk(P, df, fc, t0, max(0, len(df) - 96)),
    )

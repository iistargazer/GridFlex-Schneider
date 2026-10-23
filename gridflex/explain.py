"""Explainability: turn each dispatch step into a plain-language reason.

Only statements the simulation can verify are generated from the recorded
dispatch (battery flows, PV, flexible service, export/curtail, shedding). This is
what the dashboard's "why" panel and the demo narrative use.
"""
import numpy as np

from .data import FLEX


def hourly(P, r, day_slice):
    d = r.iloc[day_slice]
    out = []
    for ts, row in d.iterrows():
        reasons = []
        pv, Dc = float(row.pv), float(row.Dc)
        if row.ch > 0.3:
            src = "rooftop solar" if pv > Dc else "the grid"
            reasons.append(f"charging {row.ch:.0f} kW from {src}")
        if row.dis > 0.3:
            why = "covering the evening limit" if row.is_stress or row.is_outage else "displacing imports"
            reasons.append(f"discharging {row.dis:.0f} kW ({why})")
        for cls in FLEX:
            f = float(row.get(f"f_{cls}", 0.0))
            if f > 0.3:
                solar = pv > Dc
                reasons.append(f"{cls} running {f:.0f} kW"
                               + (" on solar surplus" if solar else ""))
        if row.exp > 0.3:
            reasons.append(f"exporting {row.exp:.0f} kW")
        if row.curt > 0.3:
            reasons.append(f"curtailing {row.curt:.0f} kW")
        if row.shed_c > 0.1:
            reasons.append(f"critical load short by {row.shed_c:.1f} kW")
        if not reasons:
            reasons.append(f"grid import {row.g:.0f} kW, SOC {row.soc:.0f} kWh")
        out.append(dict(time=ts.strftime("%H:%M"), text="; ".join(reasons),
                        soc=round(float(row.soc), 1), g=round(float(row.g), 1),
                        pv=round(pv, 1), shed=round(float(row.shed_c), 2)))
    return out


def day_summary(P, r, day_slice):
    d = r.iloc[day_slice]
    served = float(((d.Dc - d.shed_c).sum() * P.dt))
    ev = (d.index.hour >= 18) & (d.index.hour < 23)
    avail = float(100 * (1 - (d.shed_c[ev] > 0.05 * d.Dc[ev]).mean())) if ev.any() else 100.0
    return dict(
        pv_kwh=round(float(d.pv.sum() * P.dt), 1),
        load_kwh=round(float((d.Dc + d.served_f).sum() * P.dt), 1),
        grid_kwh=round(float(d.g.sum() * P.dt), 1),
        export_kwh=round(float(d.exp.sum() * P.dt), 1),
        curtailed_kwh=round(float(d.curt.sum() * P.dt), 1),
        critical_served_kwh=round(served, 1),
        unserved_kwh=round(float(d.shed_c.sum() * P.dt), 1),
        max_import_kw=round(float(d.g.max()), 1),
        min_soc_kwh=round(float(d.soc.min()), 1),
        evening_available_pct=round(avail, 1),
    )

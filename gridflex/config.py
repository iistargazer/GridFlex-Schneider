"""All tunable assumptions live here. Numbers marked (ASSUMPTION) are placeholders - replace with real data/quotes."""
from dataclasses import dataclass


@dataclass
class P:
    # time grid
    dt: float = 0.25            # hours per step (15 min)
    H: int = 96                 # planning horizon steps (24 h)
    resolve_every: int = 4      # re-solve MILP every N steps (hourly, rolling horizon)
    n_days: int = 60
    n_test_days: int = 14
    # neighbourhood (one 11 kV/415 V distribution transformer area)
    n_hh: int = 80
    pv_kwp: float = 100.0       # existing rooftop PV, aggregate
    bat_kwh: float = 100.0      # community battery (second-life) (ASSUMPTION)
    bat_kw: float = 40.0
    eta: float = 0.95           # one-way efficiency (~90% round trip)
    soc_min_frac: float = 0.10
    soc0_frac: float = 0.50
    flex_rate_kw: float = 60.0  # max flexible-load service rate
    # feeder / DISCOM supply
    cap_normal: float = 80.0    # kW import limit (transformer)
    cap_stress: float = 20.0    # kW import limit in DISCOM-announced evening stress windows
    # tariff Rs/kWh (ASSUMPTION, ToU illustrative)
    tariff_offpeak: float = 5.0
    tariff_normal: float = 7.0
    tariff_peak: float = 9.5
    # optimiser weights (Rs/kWh)
    deg_cost: float = 1.5       # battery wear per kWh throughput
    voll_critical: float = 60.0
    voll_flex: float = 20.0
    curt_pen: float = 4.0
    backlog_pen: float = 0.15   # per kWh per step a flexible load waits
    term_soc_val: float = 4.0
    term_backlog: float = 5.0
    reserve_frac: float = 0.30  # soft backup reserve for unannounced outages
    reserve_pen: float = 0.5
    risk: float = 0.5           # 0 = median forecast, 1 = fully conservative quantile
    # economics (ASSUMPTION - verify with vendor quotes)
    bat_capex_per_kwh: float = 6000.0
    controls_capex_per_hh: float = 1500.0   # smart-plug/relay + gateway share
    annual_om_frac: float = 0.03
    life_years: int = 8
    discount: float = 0.12
    voll_household: float = 30.0            # Rs per kWh of critical energy not served (value of lost load, survey needed)

"""Unit economics for the community asset - every input carries a source/range.

The honest counterfactual matters. Two bill comparisons are reported:
  * vs `grid_only`     - includes the benefit of the PV the neighbourhood already
                         owns, so it is NOT a fair cost of GridFlex alone;
  * vs `pv_batt_naive` - same PV + battery but no forecasting/demand response,
                         which isolates what the software adds.
The affordability test uses the second (plus reliability value) because the
battery and controls are the incremental cost.
"""


def crf(rate, years):
    return rate * (1 + rate) ** years / ((1 + rate) ** years - 1)


def capex(P):
    bat = P.bat_kwh * P.bat_capex_per_kwh
    controls = P.controls_capex_per_hh * P.n_hh
    total = bat + controls
    return dict(battery_inr=bat, controls_inr=controls, total_inr=total,
                per_hh_inr=total / P.n_hh,
                battery_per_hh_inr=bat / P.n_hh)


def annual_cost(P, bat_kwh=None, bat_price=None):
    b = P.bat_kwh if bat_kwh is None else bat_kwh
    price = P.bat_capex_per_kwh if bat_price is None else bat_price
    cap = b * price + P.controls_capex_per_hh * P.n_hh
    ann = cap * crf(P.discount, P.life_years) + cap * P.annual_om_frac
    return dict(capex_inr=cap, annual_inr=ann, per_hh_month_inr=ann / 12 / P.n_hh)


def unit_economics(P, m_base, m_gf, m_grid=None):
    """m_base = pv_batt_naive (no control), m_gf = GridFlex, m_grid = grid only."""
    c = capex(P)
    ac = annual_cost(P)
    days = 30.0
    bill_saving_control = m_base["bill_inr_per_hh_month"] - m_gf["bill_inr_per_hh_month"]
    bill_saving_total = ((m_grid["bill_inr_per_hh_month"] if m_grid else m_base[
        "bill_inr_per_hh_month"]) - m_gf["bill_inr_per_hh_month"])
    unserved_cut = (m_base["unserved_critical_kwh_per_day"]
                    - m_gf["unserved_critical_kwh_per_day"]) * days / P.n_hh
    outage_val = unserved_cut * P.voll_household
    peak_cut = max(0.0, m_base["evening_peak_import_kw"] - m_gf["evening_peak_import_kw"])
    discom_credit = peak_cut * P.discom_peak_value_inr_per_kw_month / P.n_hh
    ac_hi = annual_cost(P, bat_price=P.bat_capex_range[1])
    ac_lo = annual_cost(P, bat_price=P.bat_capex_range[0])
    net_central = bill_saving_control + outage_val + discom_credit - ac["per_hh_month_inr"]
    net_low = (bill_saving_control + unserved_cut * P.voll_household_range[0]
               + discom_credit - ac_hi["per_hh_month_inr"])
    net_high = (bill_saving_control + unserved_cut * P.voll_household_range[1]
                + discom_credit - ac_lo["per_hh_month_inr"])
    net_need = ac["per_hh_month_inr"] - bill_saving_control - outage_val - discom_credit
    delivered_day = m_gf["critical_served_kwh_per_day"]
    delivered_month_per_hh = delivered_day * 30 / P.n_hh
    fee_lifeline = 0.0
    fee_standard = 60.0
    fee_plus = 120.0
    shares = [0.45, 0.35, 0.20]           # low-income / lower-middle / middle
    collected = (fee_lifeline * shares[0] + fee_standard * shares[1]
                 + fee_plus * shares[2])
    return dict(
        capex_total_inr=c["total_inr"],
        capex_per_hh_inr=c["per_hh_inr"],
        battery_capex_per_kwh_inr=P.bat_capex_per_kwh,
        annualised_cost_per_hh_month_inr=ac["per_hh_month_inr"],
        bill_saving_vs_grid_only_per_hh_month_inr=bill_saving_total,
        bill_saving_vs_pv_battery_per_hh_month_inr=bill_saving_control,
        avoided_unserved_kwh_per_hh_month=unserved_cut,
        outage_value_per_hh_month_inr=outage_val,
        discom_peak_credit_per_hh_month_inr=discom_credit,
        evening_peak_reduction_kw=peak_cut,
        net_value_per_hh_month_inr=net_central,
        net_value_range_inr=[net_low, net_high],
        breakeven_fee_per_hh_month_inr=max(0.0, ac["per_hh_month_inr"]
                                           - bill_saving_control - outage_val - discom_credit),
        cost_per_kwh_critical_delivered_inr=ac["per_hh_month_inr"]
        / max(delivered_month_per_hh, 1e-9),
        cost_per_kwh_unserved_avoided_inr=ac["per_hh_month_inr"]
        / max(unserved_cut, 1e-9),
        critical_kwh_delivered_per_hh_month=delivered_month_per_hh,
        payback_years=(c["total_inr"] / max(
            1e-9, (bill_saving_control + outage_val + discom_credit) * 12 * P.n_hh)),
        fee_tiers=dict(lifeline_low_income_inr=fee_lifeline,
                       standard_inr=fee_standard, higher_use_inr=fee_plus,
                       collected_per_hh_month_inr=collected,
                       gross_cost_recovery_pct=100 * collected
                       / max(ac["per_hh_month_inr"], 1e-9),
                       # 100 % once non-fee value covers the remaining cost;
                       # a bare ratio would divide by ~0 and print nonsense
                       net_cost_recovery_pct=(min(100.0, 100 * collected / net_need)
                                              if net_need > 1.0 else 100.0),
                       net_cost_remaining_per_hh_month_inr=net_need),
        lifeline_note="low-income homes pay Rs0 for lights/fans/fridge/router; "
                      "the gap to full cost recovery is covered by avoided outage "
                      "costs, the DISCOM peak credit and cross-subsidy - fee income "
                      "alone does not recover the asset (stated honestly)",
        counterfactual="vs pv_batt_naive (same PV+battery, no forecasting/DR); "
                       "PV capex is excluded because the array already exists",
    )

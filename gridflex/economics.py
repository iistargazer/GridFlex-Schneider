"""Unit economics per household. All inputs are ASSUMPTIONS in config.py - replace with quotes/surveys before claiming."""


def unit_economics(P, m_unman, m_flex):
    capex = P.bat_kwh * P.bat_capex_per_kwh + P.controls_capex_per_hh * P.n_hh
    crf = P.discount * (1 + P.discount) ** P.life_years / ((1 + P.discount) ** P.life_years - 1)
    cost_month = (capex * crf + capex * P.annual_om_frac) / 12 / P.n_hh
    bill_saving = m_unman["bill_inr_per_hh_month"] - m_flex["bill_inr_per_hh_month"]
    ue_avoided = (m_unman["unserved_critical_kwh_per_day"] - m_flex["unserved_critical_kwh_per_day"]) * 30 / P.n_hh
    outage_value = ue_avoided * P.voll_household
    return dict(capex_total_inr=capex, capex_per_hh_inr=capex / P.n_hh,
                annualised_cost_per_hh_month_inr=cost_month,
                bill_saving_per_hh_month_inr=bill_saving,
                avoided_unserved_kwh_per_hh_month=ue_avoided,
                outage_value_per_hh_month_inr=outage_value,
                total_benefit_per_hh_month_inr=bill_saving + outage_value,
                net_per_hh_month_inr=bill_saving + outage_value - cost_month,
                breakeven_fee_per_hh_month_inr=max(cost_month - bill_saving, 0.0))

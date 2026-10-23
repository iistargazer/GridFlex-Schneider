# GridFlex assumptions and sources

Every number a judge could question, its type (real / cited / assumption), source and plausible range. Generated from `gridflex/config.py`.

| parameter | value | unit | kind | source | range |
|---|---|---|---|---|---|
| `site` | Hyderabad 17.385 N, 78.487 E |  | real | NASA POWER + Open-Meteo (see weather.py provenance.json) | single pilot-like site |
| `pv_kwp` | 100.0 | kWp | assumption | handoff: aggregate rooftop PV for 80 homes | 60-140 kWp |
| `bat_kwh` | 100.0 | kWh | assumption | handoff: shared second-life community battery | 20-150 kWh (sizing sweep) |
| `bat_kw` | 40.0 | kW | assumption | handoff: inverter rating | 10-40 kW |
| `transformer_rating_kva` | 100.0 | kVA | cited | CSPDCL 11 kV DT schedule lists 25/63/100/200/315/500 kVA | 25-500 kVA |
| `cap_normal_kw` | 80.0 | kW | assumption | 80 % of a 100 kVA / pf 0.9 transformer | 72-90 kW |
| `cap_stress_kw` | 20.0 | kW | assumption | DISCOM evening load-management limit in handoff | 10-30 kW |
| `grid_charge_cap_kw` | 20.0 | kW | assumption | avoid battery charging setting the feeder peak | 10-40 kW |
| `discom_evening_cap_kw` | 45.0 | kW | assumption | evening feeder allocation GridFlex agrees to respect with the DISCOM (18:00-22:00) | 30-60 kW |
| `tariff_flat` | 7.0 | Rs/kWh | cited | TGSPDCL LT-I FY2025-26 slabs 1.95-10.00 Rs/kWh (bharatsmartservices.com) plus fixed/customer charges | 5.5-9.0 effective |
| `feed_in_tariff` | 2.8 | Rs/kWh | assumption | net-metering settlement at avoided generation cost; verify with TGSPDCL net-metering order | 2.0-3.5 |
| `voll_critical` | 60.0 | Rs/kWh | cited | IGC/RePEc Delhi household VoLL US$1.50/kWh ~ Rs124/kWh (2024); central value 60 because rural/peri-urban WTP is lower | 30-124 Rs/kWh |
| `voll_flex` | 20.0 | Rs/kWh | assumption | inconvenience of a deferred pump/geyser run | 5-40 Rs/kWh |
| `bat_capex_per_kwh` | 6000.0 | Rs/kWh | cited | IEC/UC Berkeley 2025: India BESS pack ~US$60/kWh (Rs5,040), co-located BESS US$114-126/kWh (Rs9,576-10,584) | 5,040-10,584 Rs/kWh |
| `controls_capex_per_hh` | 1500.0 | Rs/hh | cited | TP-Link Tapo P110 smart plug Rs848 x2 + gateway share | 1,300-2,500 Rs/hh |
| `annual_om_frac` | 0.03 | fraction of capex/yr | assumption | typical BESS O&M for a community asset | 0.02-0.05 |
| `life_years` | 10 | years | assumption | LFP cycle life at one cycle/day; second-life may be 6-8 | 6-12 years |
| `discount` | 0.1 | fraction/yr | assumption | social discount rate for community infrastructure | 0.08-0.12 |
| `voll_household` | 60.0 | Rs/kWh | cited | see voll_critical; household survey value 124 | 30-124 |
| `discom_peak_value_inr_per_kw_month` | 150.0 | Rs/kW/month | assumption | avoided distribution-capacity cost proxy; needs DISCOM validation | 75-300 |
| `outage_h_per_day` | 3.5 | h/day | cited | CEEW 'What Smart Meters Can Tell Us' (2019): 3.5 outage h/day in notified town areas, 1.3 in district HQ | 1.3-3.5 h/day |
| `branch_km` | (0.25, 0.55, 0.85) | km | assumption | typical LT feeder branch lengths so that the CEA voltage band binds at realistic peak loading; shorter spans leave it inert | 0.15-1.0 km |
| `r_ohm_per_km` | 0.5426 | ohm/km | cited | ACSR Rabbit 50 mm2 DC resistance at 20 C | 0.54-0.60 at operating temperature |
| `v_min_pu` | 0.94 | pu | cited | CEA distribution voltage limits (+/-6 %); 0.94 is a stricter proxy | 0.90-0.95 |
| `lifeline_fraction` | 0.55 | fraction of critical | assumption | lights, fans, fridge, router, phone charging | 0.45-0.65 |

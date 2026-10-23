# GridFlex — deck script (11 slides, numbers from `outputs/results.json`)

Rules for whoever presents: every number on a slide must appear in
`outputs/results.json` or `docs/ASSUMPTIONS.md`. If a judge asks "where does that come
from", the answer is a file, not a feeling.

---

## 1. Title
**GridFlex — the last mile of reliability.**
One transformer area, 80 homes, PV and a battery that already exist. Software decides what
they do at 19:40 when the feeder is cut.
*Note: challenge 3, simulation + dashboard, no hardware.*

## 2. The household problem
3.5 outage h/day in notified town areas (CEEW 2019); the cut lands in the evening peak.
PV is gone by 19:00. A battery on a self-consumption rule is empty when the outage starts.
*Note: this is why "buy a battery" is not an answer.*

## 3. What we built
Forecast → hourly MILP (96 × 15 min, HiGHS) → dispatch → measured outcomes.
35 min full run, 16 tests, 7 scenarios on identical draws.
Battery, flexible windows (pump / hot water / EV), grid-charge cap, export, outage reserve,
feeder voltage limit, equal-per-household allocation.
*Visual: docs/architecture.png.*

## 4. Data honesty slide
Real: ERA5 weather (5,760 quarter-hours, Hyderabad), archived day-ahead forecasts, PVGIS
validation (2.83 % yield error), NASA cross-check r = 0.94.
Calibrated: load, outages (realised 3.22 vs 3.5 h/day target).
Cited with ranges: every price. *Point at docs/ASSUMPTIONS.md.*

## 5. The result that matters
Interrupted critical hours/day, 20-seed mean [95 % CI]:
grid only **4.52 [4.10, 4.94]** → unmanaged PV + battery **1.77 [1.55, 1.98]** →
**GridFlex 0.87 [0.71, 1.02]**.
Say out loud: the controller is worth ~0.9 h/day **on top of** the hardware.

## 6. Ablation — what earns the gain
MPC without DR 1.41 → GridFlex 0.87: **demand response = 0.54 h/day** (0.45 on seed 7).
Control vs rule 1.75 → 0.87. Oracle 0.88, so we are within 0.01 h/day of perfect foresight.
*Note: the remaining gap is energy, not forecast accuracy.*

## 7. The result that hurts
Persistence forecast 0.86 vs ML 0.87 h/day — statistically a tie, and the 80 % intervals are
under-covered (70 % / 58 %). We report the cheaper variant as equally valid.
*Note: judges trust the deck more after this slide, not less.*

## 8. Money
₹9,000/hh upfront → ₹144.6/hh/month annualised. Bill **+₹53.9 worse**, avoided outage value
**+₹293.9**, DISCOM peak credit **+₹30.5** → **net +₹126.0/hh/month**.
Fees ₹0/₹60/₹120 collect ₹45 → 31 % of gross cost. The rest is reliability value and
cross-subsidy, stated, not hidden.
*Note: if VoLL is ₹30/kWh the net value is ~zero. Say so before they ask.*

## 9. Sizing and the lifeline axis
40 kWh → 1.86 h/day, ₹72/hh-month; 70 kWh → 1.21 h/day, ₹108; 100 kWh → 1.18, ₹145;
150 kWh → 1.14, ₹205. Low-income net cost: cheapest **70 kWh at ₹23.6**, knee **100 kWh at ₹30.5**.
Lifeline tariff moves that net cost by exactly ₹60 at every point — a real axis, not a label.
*Visual: outputs/sizing.png.*

## 10. Fairness and the DISCOM
Equal-per-household water-filling: low-income 96.90 %, lower-middle 96.82 %, middle 96.63 %
(Jain 1.000; +0.12 pp to low-income). Proportional sensitivity: 96.76 % / 96.80 %.
Stressed feeder: 83.6 % vs 76.9 % for low-income — the rule matters when it matters.
DISCOM console: ranked actions with ₹ — ₹708/day of evening discharge, ₹396 of solar charging,
₹386 of export, loss 2.78 kWh/day, voltage 0.940 pu, 0 violations.

## 11. Limits and next step
Synthetic load/outages, flat ₹7/kWh tariff (ToU unverified), illustrative feeder, no pilot.
Next: one RWA + one feeder engineer, 8 weeks, meter the four numbers we already report
(outage h/day, evening availability, unserved kWh, peak kW) and replace the calibrated load.
Ask: a feeder and a second-life battery partner.

---

### Demo script (3 minutes, `outputs/dashboard.html`, offline)
1. Overview: headline h/day with the CI label, day view on the worst day, "why the controller
   acted" list.
2. Scenarios tab: ablation bars + the 20-seed CI table.
3. DISCOM tab: risk curve, voltage, ranked actions with rupee credits.
4. Equity tab: three archetypes + the rule sensitivity line.
5. Economics tab: KPI row, sizing frontier (two tariff schemes), fee table.
6. What-if tab: battery, outage stress, cloudiness and EV/2W share sliders (36 precomputed
   simulations), day player.
7. Method tab: the assumption table — stop here if time is short; it is the credibility slide.

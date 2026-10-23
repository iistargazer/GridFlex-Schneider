# GridFlex — keeping the lights on at the end of the feeder

*Schneider Electric Yuva Yodha, Challenge 3 — solution write-up (working simulation + dashboard)*

## 1. The problem, as a household sees it

In Telangana's notified town areas a household loses power for about **3.5 hours a day** on
average (CEEW, 2019), concentrated in the evening peak when the LT feeder is loaded and the DISCOM
is doing load management. The same household has already paid for rooftop PV, and its society may
soon buy a shared battery. Neither helps on its own: PV is gone by 19:00, and a battery with a
naive self-consumption rule is empty exactly when the outage starts.

The question this project answers is narrow and measurable: **with the PV and battery already
there, how many hours of critical supply can software recover, at what cost per household, and
who gets served first?**

## 2. What GridFlex is

A forecast → optimisation → dispatch loop for one 100 kVA distribution transformer area
(80 homes, 100 kWp PV, 100 kWh / 40 kW second-life battery):

1. **Day ahead:** ingest the archived 24 h weather forecast, the household flexible-load windows
   (pump, hot water, EV/e-rickshaw charging), the DISCOM's announced evening allocation and the
   feeder's outage history.
2. **Every hour:** solve a 96-step (15 min) mixed-integer linear programme with open-source HiGHS —
   battery charge/discharge, which flexible windows to serve and when, a grid-charging cap, export
   and curtailment, a reserve for unannounced outages, and the feeder's voltage limit.
3. **Every 15 minutes:** apply the first steps, correct in real time if the feeder limit binds,
   and record the outcome. Every step is checked for energy balance, SOC, cap and voltage
   violations; violations are counted and printed, never hidden.
4. **Afterwards:** per-archetype reliability, unit economics, battery sizing and a DISCOM console
   are computed from the same dispatch record, and a 36-point what-if grid (battery size ×
   outage rate × cloudiness × e-rickshaw/2W charging share) is precomputed for the live demo.

Seven scenarios run on **identical** weather, load and outage draws: grid only, PV + battery
unmanaged, rule + reserve + solar DR, MPC without demand response, MPC with persistence
forecasts, GridFlex, and a perfect-foresight oracle (upper bound).

## 3. Data: real weather, calibrated everything else

- **Real:** ERA5 reanalysis irradiance, temperature and wind (Open-Meteo archive) for Hyderabad
  (17.385 N, 78.487 E), 23 Aug – 21 Oct 2026, 5,760 quarter-hours, cached with provenance.
- **Real:** archived **day-ahead operational forecasts** (previous-day run API, 24 h lead) — the
  same information a controller would actually have.
- **Modelled from real GHI:** PV output (Erbs diffuse fraction, isotropic transposition, NOCT cell
  temperature, 14 % system losses), validated against PVGIS at **2.83 %** annual-yield error and
  cross-checked against NASA POWER (r = 0.94 on hourly GHI; mean 264 vs 270 W/m²).
- **Calibrated synthetic:** critical and flexible load (TGSPDCL LT-I slabs, published Indian
  residential shape, three archetypes); outages drawn to reproduce CEEW's 3.5 h/day, realised
  **3.22 h/day**; prices and costs cited with explicit ranges.

Every tunable lives in `gridflex/config.py` with a kind (**real / cited / assumption**), a source
and a plausible range; `docs/ASSUMPTIONS.md` is generated from that registry. There is no number
in the model that this document cannot attribute.

## 4. Results (60-day replay, 14 held-out days, 20 seeds)

Interrupted critical-supply hours per day, seed 7 and **20-seed mean [95 % CI]**:

| | h/day | evening availability | unserved kWh/day | bill ₹/hh/month |
|---|---|---|---|---|
| grid only | 4.98 · **4.52 [4.10, 4.94]** | 58.4 % | 60.3 | 964 |
| PV + battery, unmanaged | 2.05 · **1.77 [1.55, 1.98]** | 82.0 % | 21.9 | 398 |
| rule + reserve + solar DR | 2.04 · **1.75 [1.53, 1.97]** | 82.2 % | 19.0 | 440 |
| MPC, no DR | 1.50 · **1.41 [1.17, 1.65]** | 83.2 % | 17.4 | 447 |
| MPC, persistence | 1.00 · **0.86 [0.70, 1.02]** | 94.1 % | 9.7 | 452 |
| **GridFlex** | 1.05 · **0.87 [0.71, 1.02]** | 94.4 % | 10.0 | 451 |
| oracle | 1.04 · **0.88 [0.73, 1.04]** | 94.2 % | 10.2 | 442 |

Three findings we would defend in a viva:

**Control, not hardware, is the second half of the gain.** PV + battery alone takes 4.52 → 1.77
h/day. The controller takes it to 0.87. Demand response contributes 0.54 h/day on the 20-seed
means (1.41 → 0.87; 0.45 on seed 7) and is the only component that keeps flexible-load service
at 99 % while doing it.

**The ML forecaster does not earn its keep here.** Persistence is statistically indistinguishable
(0.86 vs 0.87 h/day; load MAPE 6.83 % vs 7.11 %; PV nMAE 2.05 % vs 1.80 %) and the 80 % intervals
are too narrow (70 % PV, 58 % load coverage). We report the cheaper variant as equally valid
rather than claiming a forecast win we cannot show.

**GridFlex is within 0.01 h/day of perfect foresight**, so what remains is an energy and outage
limit, not a prediction limit. The correct next rupee is not forecast accuracy but battery
capacity or outage scheduling.

Also measured: flexible demand served 98.9 % (unmanaged 87.8 %), PV self-consumed 57.1 %,
curtailment 0 %, export 203 kWh/day, transformer peak 77.6 kW (86 % of rating), technical loss
0.69 % of delivered energy, end-of-feeder voltage 0.940 pu with zero violations of the CEA ±6 %
band, SAIDI-like 63 min/day (grid only 299).

## 5. Affordability, stated plainly

₹9,000 per household upfront (100 kWh at ₹6,000/kWh + ₹1,500 of plugs and gateway) annualises to
**₹144.6/hh/month** (10 yr, 10 %, 3 % O&M). Against the same PV + battery with no control:

| component | ₹/hh/month |
|---|---|
| annualised capex | −144.6 |
| grid bill (GridFlex is ₹53.9 **more** expensive) | −53.9 |
| avoided unserved energy, 4.9 kWh/hh/month at VoLL ₹60/kWh | +293.9 |
| DISCOM evening-peak credit, 16.3 kW × ₹150/kW-month | +30.5 |
| **net** | **+126.0** |

The asset does not pay for itself through the bill; it pays through reliability. At the bottom of
the VoLL range (₹30/kWh) the net value falls to roughly zero, and the dashboard shows the range
rather than a single payback number. Fee tiers are ₹0 (low-income lifeline) / ₹60 / ₹120, which
collect ₹45/hh/month — 31 % of gross cost — so the honest statement is that the remainder is
social value plus cross-subsidy, not fee revenue.

Battery sizing, each point a real simulation on a 7-day screening window (lifeline tariff):
40 kWh → 1.86 h/day at ₹72/hh-month; 70 kWh → 1.21 h/day at ₹108; 100 kWh → 1.18 h/day at ₹145;
150 kWh → 1.14 h/day at ₹205. On the low-income net-cost axis (bill saving, reliability value and
DISCOM credit included) the cheapest point is **70 kWh at ₹23.6/hh-month net**, the knee is
**100 kWh at ₹30.5**, and 150 kWh buys 0.04 h/day for ₹9 more. The tariff-scheme axis is swept
too: the lifeline scheme moves the low-income net cost by exactly the ₹60 fee at every size, which
is what makes it a real axis rather than a label.

## 6. Who gets served first

During a shortfall the controller water-fills critical energy **equal per household**, so a villa
cannot crowd out a one-room home. On the held-out days: low-income 96.90 % of critical served,
lower-middle 96.82 %, middle 96.63 % — Jain index 1.000 on the served fraction, +0.12 pp in favour
of low-income. Proportional-to-demand allocation, run as the promised sensitivity, gives 96.76 %
for low-income and 96.80 % for the middle archetype (−0.03 pp), so at this reliability level the
rule is nearly free. On a deliberately
stressed feeder (2 kW cap, no battery) it is not: low-income 83.6 % under equal allocation versus
76.9 % under proportional, at the cost of the middle archetype dropping 76.9 % → 71.4 %. That
stress case is a unit test, and the trade-off is stated rather than optimised away.

## 7. What the DISCOM gets

A console built from the last simulated day, with every figure traceable to the dispatch record:
ranked actions with kW, kWh and a rupee credit — discharge into the evening peak (39.8 kW,
101 kWh, ₹708/day), charge from rooftop solar (40 kW, 94 kWh, ₹396), export surplus (51 kW,
138 kWh, ₹386), run pump load on solar (48 kW, 33 kWh, ₹232), hot-water load on solar (40 kW,
21 kWh, ₹150) — each with its price basis, plus a 24 h outage-risk and expected-shortfall curve
from the feeder's own outage history, technical loss (2.78 kWh/day; 1.33 kW at peak) and the
voltage trace. The DISCOM is a counterparty, not an owner: it publishes the allocation, reads the
console, and pays for verified peak reduction.

## 8. Limitations

Loads and outages are calibrated synthetic; tariffs are an effective flat ₹7/kWh (domestic ToU is
unverified, so ToU is a labelled sensitivity); the feeder is a three-branch illustration, not a
protection study; unannounced outages are not predictable and are handled by a reserve, not a
forecast; forecast intervals are under-covered; the value case rests on VoLL ₹30–124/kWh; there is
no hardware-in-the-loop and no pilot. Each of these is visible in the dashboard's Method tab.

## 9. Reproduce

    python run.py --oracle --seeds 20 --workers 8      # 35 min → outputs/, docs/ASSUMPTIONS.md
    python -m pytest tests                             # 16 tests, 40 s

Artefacts: `outputs/results.json` (every metric, CI, ablation, assumption),
`outputs/dashboard.html` (seven tabs, offline), PNG figures, and this document set.

# GridFlex — forecast-driven neighbourhood reliability (Schneider Yuva Yodha, Challenge 3)

One 100 kVA distribution transformer, 80 homes, 100 kWp of existing rooftop PV and a
100 kWh / 40 kW shared battery. GridFlex forecasts the next 24 h, solves a rolling MILP
every hour, and dispatches the battery plus the households' flexible loads so that
critical load survives the feeder's planned and unplanned outages — inside the
transformer limit and the CEA voltage band.

Everything below is produced by one command on real Hyderabad weather:

    pip install numpy pandas scipy scikit-learn matplotlib pytest
    python run.py --oracle --seeds 20 --workers 8      # ~35 min (measured 2,121 s)
    python -m pytest -q                                # 30 tests, ~12 s
    open outputs/dashboard.html                        # self-contained, works offline

## Headline (14 held-out days, 60-day replay)

Real ERA5 / Open-Meteo weather for Hyderabad (17.385 N, 78.487 E), 23 Aug – 21 Oct 2026.
Realised outage exposure 3.22 h/day (CEEW-calibrated target 3.5). Single seed 7, with the
20-seed mean and 95 % CI where it exists:

| scenario | interrupted critical h/day | evening availability 18–23 h | unserved critical kWh/day | grid bill ₹/hh/month |
|---|---|---|---|---|
| grid only (today) | 4.98 · **4.52** [4.10, 4.94] | 55.7 % · **58.4 %** | 60.4 · **60.3** | 976 · **964** |
| PV + battery, unmanaged | 2.05 · **1.77** [1.55, 1.98] | 80.0 % · **82.0 %** | 24.2 · **21.9** | 404 · **398** |
| rule + reserve + solar DR | 2.04 · **1.75** [1.53, 1.97] | 80.4 % · **82.2 %** | 21.4 · **19.0** | 443 · **440** |
| MPC, no demand response | 1.50 · **1.41** [1.17, 1.65] | 82.1 % · **83.2 %** | 18.3 · **17.4** | 450 · **447** |
| MPC, persistence forecast | 1.00 · **0.86** [0.70, 1.02] | 95.7 % · **94.1 %** | 10.5 · **9.7** | 460 · **452** |
| **GridFlex** (ML + DR + fairness) | 1.05 · **0.87** [0.71, 1.02] | 95.4 % · **94.4 %** | 11.2 · **10.0** | 458 · **451** |
| oracle (perfect foresight) | 1.04 · **0.88** [0.73, 1.04] | 95.4 % · **94.2 %** | 11.0 · **10.2** | 452 · **442** |

Read the ablation honestly:

- **Control is where the gain is.** 4.52 → 1.77 h/day comes from PV + a battery; 1.77 → 0.87 h/day
  comes from the controller (MPC vs rule-based self-consumption). Demand response is worth
  another 0.54 h/day on the 20-seed means (1.41 → 0.87; 0.45 on seed 7) and it is the only
  component that lifts flexible-load service back to 99 %.
- **The ML forecaster does not beat persistence on this window** (0.87 vs 0.86 h/day; load MAPE
  6.83 % vs 7.11 %, PV nMAE 2.05 % vs 1.80 %). The 80 % intervals are also too narrow
  (70 % PV / 58 % load coverage). GridFlex is therefore reported with the persistence variant
  as an equally good, cheaper option — not hidden.
- **GridFlex is within 0.01 h/day of the perfect-foresight bound**, so the remaining 0.87 h/day is
  an energy/outage limit, not a forecasting limit. Buying forecast accuracy would not help.
- **The bill is ₹53.9/hh/month *higher* than the unmanaged case.** The controller moves
  flexible load into the evening peak it protects and keeps more reserve; that cost is real and
  is not netted out of the headline.

Other measured outputs (seed 7): flexible demand served 98.9 % (unmanaged 87.8 %), PV
self-consumed 57.1 %, curtailment 0 %, export 203 kWh/day, transformer peak 77.6 kW
(86 % of rating), technical loss 0.69 % of delivered energy, end-of-feeder voltage
0.940 pu with **0** violations of the CEA ±6 % band, SAIDI-like 63 min/day (grid only 299).
The digital-twin what-if grid is precomputed too: 36 real simulations over battery size
(70/100/150 kWh) × outage rate (0.75/1.0/1.25×) × cloudiness (100 %/80 % of clear-sky PV) ×
e-rickshaw/2W charging share (1.0×/1.6×), exposed as discrete presets in the What-if tab — the
page never interpolates between runs.

## What is real, what is modelled

| Signal | Status |
|---|---|
| Irradiance, temperature, wind | **real** — ERA5 reanalysis via Open-Meteo archive, 5,760 quarter-hours |
| Day-ahead weather forecast | **real** — archived operational runs (previous-day run, 24 h lead) |
| PV output | modelled from real GHI (Erbs + isotropic, NOCT), validated against PVGIS: **2.83 %** annual-yield error; NASA POWER cross-check r = 0.94 |
| Critical + flexible load | calibrated synthetic (TGSPDCL LT-I slabs, published Indian residential shape) |
| Outages | simulated to CEEW's measured 3.5 h/day; realised 3.22 h/day is reported each run |
| Tariffs, capex, VoLL, DISCOM rate | cited with a range in `docs/ASSUMPTIONS.md` |

## Affordability (the number a judge should attack)

| item | ₹ / household / month |
|---|---|
| annualised capex (₹9,000/hh upfront, 10 yr, 10 %) | **−144.6** |
| bill saving vs the same PV + battery with no control | **−53.9** (a cost, not a saving) |
| avoided unserved energy at VoLL ₹60/kWh (4.9 kWh/hh/month) | **+293.9** |
| DISCOM evening-peak credit (16.3 kW × ₹150/kW-month) | **+30.5** |
| **net value** | **+126.0** |

So the asset does not pay for itself out of the electricity bill — it pays for itself out of
reliability. Fee tiers (₹0 low-income / ₹60 standard / ₹120 higher-use) collect ₹45/hh/month,
31 % of gross cost; the rest is covered by the same reliability value the household avoids, which
is why the break-even feeis ₹0 and the honest caveat is that this is a **willingness-to-pay** argument at VoLL ₹30–124/kWh, not a metered cash flow. Battery sizing (7-day screening):
40 kWh ₹72/hh-month at 1.86 h/day → 70 kWh ₹108 at 1.21 → 100 kWh ₹145 at 1.18 → 150 kWh ₹205 at
1.14. On the low-income net-cost axis the cheapest point is **70 kWh at ₹23.6/hh-month net**, the
knee **100 kWh at ₹30.5**, and 150 kWh buys 0.04 h/day for ₹9 more; the lifeline tariff moves that
net cost by exactly the ₹60 fee at every point.

## Fair access

Critical energy is water-filled **equal per household** during a shortfall, so a one-room homeis not crowded out by a villa. Measured on the held-out days: low-income 96.90 % of critical served,
lower-middle 96.82 %, middle 96.63 % (Jain 1.000 on the served fraction; +0.12 pp in favour of
low-income). The promised sensitivity is run: proportional-to-demand allocation gives 96.76 % for
low-income and 96.80 % for the middle archetype (Jain 1.000, −0.03 pp). On a deliberately stressed feeder (cap 2 kW, no battery) the
rule matters — low-income 83.6 % under equal allocation vs 76.9 % under proportional, middle
71.4 % vs 76.9 % — and that case is a unit test, not a claim.

## DISCOM console

The console turns the last simulated day into ranked, monetised actions read off the dispatch:
discharge into the evening peak (39.8 kW, 101 kWh, ₹708/day), charge from rooftop solar
(40 kW, 94 kWh, ₹396), export surplus (51 kW, 138 kWh, ₹386), run pump load on solar (48 kW,
33 kWh, ₹232), run hot-water load on solar (40 kW, 21 kWh, ₹150) — each with the price basis
that produced the rupee figure, plus 24 h outage-risk and expected-shortfall curves from the
feeder's own outage history, technical loss (2.78 kWh/day, 1.33 kW at peak) and voltage.

## The dashboard a judge opens

`outputs/dashboard.html` is the deliverable: one self-contained file, Chart.js inlined and the
whole results payload embedded, with no network requests at view time. Seven tabs, each answering
a different question:

| Tab | What it shows |
|---|---|
| Overview | The headline (0.87 h/day, 20-seed mean and CI) with a reliability ladder against the bare grid and uncontrolled PV + battery, six indicators with deltas, a 96-step supply ribbon, the selected day's dispatch and the controller's own reasons |
| Scenarios | The ablation ranked as bars, every scenario side by side, the bill each one buys, and the 20-seed means with 95 % CI drawn as range bars |
| DISCOM | A 24-cell feeder-risk strip, expected shortfall and net load, end-of-feeder voltage, and the ranked DR actions with their rupee credit |
| Equity | The three archetypes with metered served energy, the Jain index, and the proportional-allocation sensitivity |
| Economics | Cost/value ledger down to the net figure, the VoLL range bar, the sizing frontier labelled by battery size, fee tiers and the cost build-up |
| What-if | 36 precomputed cases over battery × outage stress × PV × EV share, plus a day player that scrubs a held-out day quarter by quarter |
| Method | Provenance cards (real / modelled / calibrated), forecast accuracy, the controller flow, limitations and every assumption with its source |

`outputs/site/index.html` is byte-identical, written by the same `make_dashboard` call for static
hosting. `tests/test_artifacts.py` fails if the pair diverges, if the page gains an external
asset, or if a headline figure quoted in these docs stops matching `outputs/results.json`.

## Repository map

| File | Responsibility |
|---|---|
| `run.py` | pipeline: data → forecast → scenarios → sizing → what-if → seed CI → artefacts |
| `gridflex/config.py` | **every** tunable with kind (real/cited/assumption), source and range |
| `gridflex/weather.py` | fetch + cache real observations, archived forecasts, PVGIS validation |
| `gridflex/data.py` | PV model, archetype loads, window-based flexible demand, outages |
| `gridflex/forecast.py` | direct multi-horizon HGB with quantile loss; persistence ablation |
| `gridflex/optimizer.py` | HiGHS MILP over 96 × 15 min steps (battery, windows, grid-charge cap, export) |
| `gridflex/simulate.py` | plant + real-time correction, 7 scenarios, invariant checks, metrics |
| `gridflex/network.py` | three-branch LT feeder: loss and end-of-feeder voltage |
| `gridflex/equity.py` | archetypes, equal-per-household water-filling, Jain, rule sensitivity |
| `gridflex/economics.py` | capex/CRF, bill split by meter, VoLL, DISCOM credit, fee tiers |
| `gridflex/sizing.py` | battery × tariff-scheme sweep, Pareto/knee on low-income net cost |
| `gridflex/discom.py` | feeder risk, loss, ranked DR actions with rupee credit |
| `gridflex/report.py` | results payload for the page + the matplotlib PNG figures |
| `gridflex/dashboard.py` | the page itself: HTML/CSS/Chart.js, tab composition and copy |
| `gridflex/explain.py` | per-step controller reasons shown in the dashboard |

Artefacts: `outputs/dashboard.html` (offline, 7 tabs) and its byte-identical publishing copy
`outputs/site/index.html`; `outputs/results.json` (all metrics, CIs, ablation, assumptions);
`outputs/{scenarios,day_plot,sizing,voltage}.png`; and `docs/`:
`WRITEUP.md` (submission write-up), `DECK.md` (slide-by-slide), `SUBMISSION_GUIDE.md` (form and
demo script), `ASSUMPTIONS.md` (generated), `DATA.md` (generated), `OPERATIONS.md` (ownership,
O&M, failure modes), `architecture.html` + `architecture.png`.

## Honest limitations

1. **Loads and outages are calibrated synthetic**, not metered. Real feeder data would change
   the absolute numbers, not the ordering.
2. **Tariffs are an effective flat ₹7/kWh**; domestic ToU is not verified for TGSPDCL LT-I, so the
   ToU mode is a labelled sensitivity (`--tou`), not a claim.
3. **The feeder is illustrative** (three LT branches, ACSR Rabbit). It shows the voltage band can
   bind and that the controller respects it; it is not a protection or phase-imbalance study.
4. **Unannounced outages are not predictable.** The controller holds a reserve; the risk curve
   quantifies exposure from history and says so.
5. **The forecast intervals are under-covered** (70 % at the 80 % nominal level), which makes the
   controller slightly optimistic about its own forecasts.
6. **The value case rests on VoLL ₹30–124/kWh.** At the low end the net value per household falls
   to roughly break-even; the dashboard shows the range.
7. **No hardware-in-the-loop, no pilot.** The demo is a simulation and a static dashboard.

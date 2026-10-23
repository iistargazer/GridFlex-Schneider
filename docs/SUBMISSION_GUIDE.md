# Submission guide — what to send, where it lives, and what to say

Status: working simulation, real Hyderabad weather, 20-seed results, offline dashboard.
No hardware. Every number below is in `outputs/results.json`.

## 1. Deliverables → artefacts

| Required by the challenge | Artefact in this repo | Notes |
|---|---|---|
| Solution write-up, Indian conditions | [`docs/WRITEUP.md`](WRITEUP.md) | 9 sections, ~1,500 words, all figures sourced |
| Architecture / flow diagram | [`docs/architecture.png`](architecture.png), [`docs/architecture.html`](architecture.html) | data → forecast → MILP → plant → metrics → artefacts |
| Design artefacts | dashboard (7 tabs) + `outputs/day_plot.png`, `outputs/scenarios.png`, `outputs/sizing.png`, `outputs/voltage.png` | screenshots for the deck |
| Prototype / simulation | `run.py` + `gridflex/` | 7 scenarios, 30 tests, ~35 min full run |
| Measurable reliability gain vs baseline | 4.52 → 1.77 → **0.87** interrupted critical h/day (20-seed means) | grid only → unmanaged PV+battery → GridFlex |
| Ownership, O&M, unit economics | [`docs/OPERATIONS.md`](OPERATIONS.md) + Economics tab | ₹144.6/hh-month cost, +₹126.0 net value |
| Deck | [`docs/DECK.md`](DECK.md) | 11 slides, speaker notes, 3-minute demo script |

The demo itself is `outputs/dashboard.html` — a single self-contained file with Chart.js, both
typefaces and the stylesheet inlined; it works with no network, no server, no API key.
`outputs/site/index.html` is byte-identical to it, written by the same `make_dashboard` call for
static hosting. The page is built from `gridflex/dashboard.py`, with its visual system in
`gridflex/assets/theme.css` and its type in `gridflex/assets/fonts`; `gridflex/report.py`
assembles its payload and the PNG figures.

## 2. Form fields (draft answers)

- **Prototype stage:** working simulation + dashboard; no hardware, no pilot.
- **Data used:** *real* ERA5 reanalysis weather and archived day-ahead forecasts for Hyderabad
  (Open-Meteo, 23 Aug – 21 Oct 2026), PV validated against PVGIS (2.83 % yield error). Load and
  outages are calibrated synthetic — say this explicitly.
- **Tech:** Python, NumPy/pandas, scikit-learn (quantile HGB), SciPy/HiGHS MILP, matplotlib,
  Chart.js. No commercial solver, no paid API.
- **Cost to build:** team time; software cost ₹0 (open-source stack).
- **Cost to scale:** ₹9,000 per household upfront (₹6,000/kWh battery + ₹1,500 controls),
  ₹144.6/hh-month annualised — labelled assumption with a ₹5,040–10,584/kWh band.
- **Success metric:** interrupted critical-supply hours per day, with evening (18–23 h)
  availability and unserved critical kWh as secondary.
- **What is measured vs claimed:** measured in simulation only. The four numbers a pilot would
  meter are exactly the ones reported: outage h/day, evening availability, unserved kWh,
  peak kW.
- **Next steps:** one RWA + one DISCOM feeder engineer, 8 weeks, meter those four numbers and
  replace the calibrated load; second-life battery partner.

## 3. Judging-criteria map

| Criterion | Where to point |
|---|---|
| Problem understanding | Write-up §1, dashboard Overview |
| Technical depth | MILP formulation (`optimizer.py`), forecast leakage test, voltage/loss model |
| Data credibility | `docs/DATA.md`, `docs/ASSUMPTIONS.md`, 20-seed CIs |
| Impact | 4.52 → 0.87 h/day, 60.3 → 10.0 unserved kWh/day |
| Feasibility & cost | ₹9,000/hh, ₹144.6/hh-month, fee tiers, sizing knee at 100 kWh |
| Inclusion | lifeline tier ₹0, equal-per-household allocation, Jain + rule sensitivity |
| Honesty | ML ≈ persistence reported; bill ₹53.9 worse reported; forecast coverage gap reported |

## 4. Demo script (3 minutes)

Seven tabs, in the order a judge should see them:

| Tab | What it answers |
|---|---|
| Overview | Did the neighbourhood stay supplied? Headline h/day with its 95 % CI, the ladder against grid-only and uncontrolled PV + battery, six indicators with deltas, a supply ribbon and the selected day's dispatch plus the controller's reasons |
| Scenarios | Which component earns the gain? Ranked ablation, all scenarios side by side, the bill each buys, and the 20-seed means with CI range bars |
| DISCOM | What does the feeder engineer see? 24-cell risk strip, shortfall and voltage curves, ranked actions with rupee credits |
| Equity | Who gets the critical energy? Archetype cards, Jain index, proportional-rule sensitivity |
| Economics | What does it cost and return? Cost/value ledger to net value, VoLL range bar, sizing frontier, fee tiers |
| What-if | Size it for your feeder: 36 precomputed cases as discrete presets, plus the day player |
| Method | What is real, modelled, assumed? Provenance cards, forecast accuracy, limitations, every assumption with its source |

See §"Demo script" in [`docs/DECK.md`](DECK.md) for what to say on each. Keep the Method tab for
the credibility close.

## 5. Before you submit — checklist

- [x] Real weather + archived forecasts, cached and cited
- [x] Seven scenarios including oracle, all on identical draws
- [x] 20-seed 95 % CIs for every scenario row
- [x] Ablation (DR, ML vs persistence, control vs rule)
- [x] Affordability with lifeline tariff axis and Pareto/knee
- [x] Equity with metered flows and a rule sensitivity
- [x] Digital-twin what-if grid: battery × outage × cloudiness × EV/2W share (36 runs), discrete presets in the What-if tab
- [x] DISCOM console with ranked, monetised actions
- [x] Voltage-lite + technical loss, violations counted
- [x] Offline dashboard, 7 tabs, per-step explanations, one self-contained file written twice
- [x] Tests (30) covering balance, limits, windows, fallback, equity, sizing, console, plus the
      dashboard/site byte-identity and doc-figure drift guards
- [x] README, write-up, deck script, operations, assumptions, data provenance
- [ ] Hosted demo URL — `outputs/site/` is ready; needs a host/account to publish
- [ ] Pilot partner (RWA + feeder engineer) — not started

## 6. Known soft spots (rehearse the answers)

1. **"Your ML is not better than persistence."** Correct on this window — 0.86 vs 0.87 h/day.
   That is why the remaining gap to the oracle (0.88) is energy, not forecast skill.
2. **"Your bill went up."** By ₹53.9/hh-month, yes: the controller holds reserve and shifts load.
   The value is reliability (₹293.9), and that is shown as a separate line, not netted away.
3. **"VoLL is a guess."** It is a cited range (₹30–124/kWh). At ₹30 the net value is ~zero; the
   dashboard shows the range.
4. **"Synthetic load."** Yes — stated on every artifact, and the pilot plan is to meter exactly
   the four reported quantities.
5. **"Why not just a bigger battery?"** 150 kWh buys 0.04 h/day over 100 kWh for ₹60/hh-month gross;
   the sizing tab and the knee exist to answer this with numbers.

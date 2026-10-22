# Phase 2 submission guide

## Plan around end-sems (22 Oct -> 8 Dec)
- Now-10 Nov (light): swap in real irradiance/load data; fix limitations 3-4; ask a teammate to own the demo video script.
- 11-18 Nov: end-sems, nothing.
- 19 Nov-30 Nov: sensitivity runs (battery size, outage rate, forecast error), O&M model, wireframes (screenshot dashboard + sketch DISCOM view), deck (max 15 slides).
- 1-6 Dec: record 3-5 min demo, repo README, fill form, submit by ~6 Dec (buffer). Register on the Schneider Talent Community link (required field).

## Challenge deliverables -> where covered
| Required | Artefact |
|---|---|
| Solution write-up, Indian conditions | Write from README + config assumptions: evening peak 18-23h, planned DISCOM load-management windows, unannounced outages, rooftop PV, low-income users |
| Architecture / flow diagram | Redraw phase-1 loop, add: energy flows (PV, grid, battery, critical vs flexible loads), data flows (meters, NWP, DISCOM schedule), money flows (ToU bill, fee, DISCOM revenue share) |
| Design artefacts | Dashboard screenshots, MILP formulation page, resident/operator/DISCOM UX sketches |
| Prototype/simulation | This repo |
| Measurable reliability gain vs baseline | `outage_hours_per_day`, `evening_availability_pct`: grid-only 1.55 -> unmanaged 0.89 -> GridFlex 0.12 h/day (synthetic, 14 held-out days) |
| Ownership, O&M, unit economics | `economics.py` output + operating model below |

## Form fields (Phase 2)
Prototype stage: working simulation + dashboard, no hardware. Data used: *simulated* (say so; list real sources once swapped). Tech: Python, scikit-learn, SciPy/HiGHS MILP, Chart.js. Third-party APIs: none yet (NASA POWER/OpenWeather later). Cost to build: team time + Rs0 software (open-source solver); cost to scale: capex/hh from `economics.py` (label as assumption). Success metric: interrupted critical-supply hours/day. Next steps: pilot with a housing society/RWA + a DISCOM feeder engineer, hardware-in-loop later.

## Operating model to write up (not yet in the deck)
Community battery owned by RWA/cooperative or a local ESCO; DISCOM provides outage/stress schedule and gets feeder-peak reduction + dashboard; a trained local technician (per ~10 neighbourhoods) does O&M; households pay a small monthly fee or get it via bill credit. Use `breakeven_fee_per_hh_month_inr` honestly; show levers: larger shared batch of homes, DISCOM capex avoidance payments, second-life battery cost, subsidy schemes (verify current ones).

## Fix in phase-1 deck before submitting
1. Gurobi/CPLEX are commercial -> contradicts "affordable". Say open-source HiGHS.
2. Numbers (18.7% cost, 32% curtailment, 40% transformer, 3.8% MAPE, 2.5x degradation, 35-50% curtailment) must come from your runs or be cited; judges ask how they were measured. Current prototype gives different figures.
3. EV-centric framing misfits low-income India; lead with pumps, water heaters, e-rickshaw/2W charging, critical loads.
4. Missing in deck: outage-hours baseline, O&M/ownership, unit economics, voltage (be explicit it's future work).
5. Paillier/RLWE privacy slide is a distraction; replace with DISCOM-facing analytics.

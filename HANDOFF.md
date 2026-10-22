# GridFlex - handoff + roadmap (for freebuff / any coding agent)

Goal: win Schneider Electric Yuva Yodha, Challenge 3 (Grid Reliability / renewable intermittency). Phase 2 deadline **8 Dec 2026** (aim to submit 6 Dec). Team has end-sems ~11-18 Nov. Treat 1 Dec as feature freeze.

## 0. What judges asked for (from the challenge page) - every roadmap item maps to one of these
1. Solution write-up: how it works, assumptions, why suited to **Indian distribution-grid** conditions
2. Architecture diagram: components + data/energy/money flows
3. Design artefacts: UX wireframes, process/service design, data/model design
4. Prototype/simulation (encouraged, no hardware)
5. **Measurable reliability improvement** (outage hours or availability in intermittency windows) vs a **defined baseline**
6. **Ownership, O&M model + unit economics showing affordability for low-income communities**
Solution must: bridge intermittency gaps, stay local/manageable, be genuinely affordable (low-income urban/peri-urban), support the DISCOM (feeder loads, technical losses).
Form also needs: demo video 3-5 min, repo link, deck PDF <=15 slides, cost to build + cost to scale, business model, next steps, broader impact, Schneider Talent Community registration.

## 1. Current state (built 22 Oct 2026)
Runs end-to-end: `pip install numpy pandas scipy scikit-learn matplotlib; python run.py [--oracle]` (~1 min). Outputs in `outputs/` (results.json, dashboard.html, day_plot.png, outage_hours.png).

Files (units: kW, kWh, Rs; dt=0.25 h; 96 steps/day):
- `gridflex/config.py` - dataclass `P`, ALL assumptions (neighbourhood size, PV, battery, tariffs, penalties, economics). Placeholders are marked ASSUMPTION.
- `gridflex/data.py` - `make_data(P, seed)`: synthetic 60 days: PV from clear-sky x cloud AR(1); critical load `Dc`, flexible request `F` (pumps, geyser, washing, 2W/e-rickshaw charging); imperfect NWP (`ghi_fc`, `temp_fc`); feeder import cap: `cap_plan` (known DISCOM evening stress, 20 kW 18:30-22:30 on ~45% of days) and `cap` (= plan + unannounced outages, cap 0, Poisson 0.6/day).
- `gridflex/forecast.py` - direct multi-horizon HistGradientBoosting, quantile loss: pv q50/q10, Dc q50/q90, F q50. Features known at decision time only (tod sin/cos, dow, horizon, NWP, lag-24h, last obs, 4-step mean). `evaluate()` gives day-ahead MAPE / PV nMAE.
- `gridflex/optimizer.py` - `solve()`: MILP via `scipy.optimize.milp` (HiGHS). Vars per step: grid g, ch, dis, soc, binary u (no simultaneous ch/dis), curtail, critical shed sc, flexible served f, backlog b, flexible shed sf, reserve slack rs. Constraints: power balance, SOC dynamics, flex backlog, ch/dis exclusivity, soft reserve. Objective: ToU grid cost + battery wear + VoLL-weighted shed + curtail penalty + backlog (waiting) penalty + reserve penalty - terminal SOC value.
- `gridflex/simulate.py` - `run(P, df, fc, mode, t0, t1, oracle=False)`; modes `status_quo` (grid only), `unmanaged` (PV+battery self-consumption rule, proportional load cuts, no forecasting), `gridflex` (rolling MILP every hour, executes plan with real-time correction: emergency discharge if cap binds, priority shedding: defer flexible first). `metrics()`.
- `gridflex/economics.py` - capex, annualised cost (CRF), bill saving, avoided-unserved value, break-even fee per household.
- `gridflex/report.py` - static Chart.js dashboard (data embedded) + matplotlib PNGs.
- `docs/SUBMISSION_GUIDE.md` - deliverable mapping, form-field draft, deck fixes.

Train/test: days 0-45 train, last 14 days held out; all scenarios share identical weather/load/outages.

### Snapshot of results (synthetic data - never present as field results)
| metric (14 held-out days) | grid only | unmanaged | GridFlex | oracle forecast |
|---|---|---|---|---|
| interrupted-critical hours/day | 1.55 | 0.89 | 0.12 | 0.11 |
| evening 18-23h availability % | 72.9 | 82.9 | 97.9 | 98.2 |
| unserved critical kWh/day | 30.1 | 18.2 | 2.6 | 2.5 |
| solar curtailed % | - | 40.7 | 38.8 | 28.1 |
| bill Rs/hh/month | 1276 | 527 | 506 | 395 |
Forecast (day-ahead): load MAPE 5.4%, PV nMAE 2.9% (easy: synthetic). Economics at placeholder costs: capex ~Rs9,000/hh, break-even fee ~Rs152/hh/month -> likely NOT affordable. This is the main weakness.

## 2. Known issues / honesty traps (fix early)
1. **Baseline may look like a strawman**: unmanaged has no reserve, no ToU awareness, proportional cuts. Add stronger baselines (rule-based with fixed backup reserve + ToU charging; "battery only, no DR") so the claimed gain is credible. Report gain vs each.
2. Grid import peaks at 80 kW (= transformer cap) from night grid-charging. Add `grid_charge_cap_kw` (and consider a transformer-loading % metric).
3. Curtailment ~39%: PV large vs battery; flexible loads can only be deferred, not advanced. Add flexible "windows" (e.g. pumps/water heating can run any time 10-16h) so noon solar is used directly; allow limited export or report curtailment honestly.
4. `risk=0.5` blend of q50/q10-q90 is untuned; oracle shows forecast risk hedging costs curtailment/bill. Tune via sweep; consider scenario-based/stochastic handling.
5. Unplanned outages are unforecastable in sim; `reserve_frac=0.30` is a blunt hedge. Learn outage risk by hour/day-type from data, size reserve accordingly.
6. NWP in `data.py` is derived from the truth with noise -> real NWP errors will differ; expect forecast error to rise on real data. `forecast.py` has a PV ceiling hack (`ghi_fc*0.1`) - make it principled.
7. Metrics quirks: `flex_unserved_kwh_per_day` subtracts final backlog; unmanaged loses shed flexible load while GridFlex defers it (document or equalise). `evening_peak_import_kw` code is clumsy - simplify.
8. Stress/outage rates, tariffs, battery cost, VoLL are guesses. Anything shown to judges must be sourced or labelled as assumption with a sensitivity range.
9. No voltage/network model (phase-1 deck claims Vmin<=V<=Vmax - either implement lite version or remove claim).
10. Only one seed/one 14-day window: add multiple seeds + confidence intervals before quoting numbers.

## 3. Roadmap (priority = impact on winning / effort). Do P0 first; stop adding features 1 Dec.

### P0 - credibility (before 10 Nov, ~10-15 h total, light work)
- [ ] **Baselines + ablation table**: grid-only, PV+battery rule, PV+battery rule+reserve/ToU, GridFlex-no-forecast (persistence), GridFlex-no-DR, GridFlex-full, oracle. Shows which component earns what. (accept: one table in results.json + dashboard)
- [ ] **Multi-seed evaluation**: 20 seeds x 14 test days, report mean +/- 95% CI for outage hours, availability, bill. (`run.py --seeds 20`; keep runtime <15 min; parallelise with multiprocessing)
- [ ] **Real data swap-in, labelled honestly**: irradiance/temperature from a free reanalysis source (e.g. NASA POWER or PVGIS) for a real Indian pilot-like site; load shape from a public Indian household/feeder dataset if one can be found, else calibrated-synthetic from published profiles. Keep the generator as fallback. Update "data used" field: real / calibrated / simulated per signal.
- [ ] Fix issues 2, 3, 7 above.
- [ ] Add pytest: energy balance holds every step, SOC within bounds, cap never exceeded, MILP infeasible-fallback path works.

### P1 - win the criteria judges will score (19-30 Nov, main build)
1. **Affordability engine (biggest differentiator)**. Add `sizing.py`: sweep battery kWh x kW x critical-circuit share; plot cost-per-household-month vs outage-hours-avoided (Pareto). Add a **"lifeline critical-circuit" tier**: only fans, lights, fridge, phone/router, small pump guaranteed; everything else best-effort -> much smaller battery. Add fee tiers + DISCOM payment for avoided capex/peak reduction + carbon/REC-style credit as *scenarios*. Target: a defensible configuration where household net cost is small or covered by DISCOM/avoided-diesel/inverter savings; state source of every cost. Output a one-page unit-economics table incl. cost per kWh of critical energy delivered and payback.
2. **Equity / fair-access layer** (matches the challenge's "fair-access pricing and dispatch rules"): split the 80 homes into archetypes (low-income / lower-middle / middle, different loads, some without rooftop PV). Allocate battery critical energy by rule (equal share, need-weighted); report outage hours per archetype and a fairness index (e.g. Jain). Show low-income homes get >= average reliability.
3. **DISCOM console** (explicit requirement): feeder risk forecast for next 24h (probability/size of shortfall), transformer loading %, peak-reduction kW, estimated technical-loss reduction (relative I^2R proxy: sum of load^2 baseline vs GridFlex), recommended DR actions list, SAIDI-like minutes per customer. Put as a second dashboard tab.
4. **Network-lite voltage model**: radial feeder with 3 branches, LinDistFlow linearised voltage; show evening-end-of-feeder voltage dip and noon rise baseline vs GridFlex; add voltage constraint (or penalty) in MILP. If it won't fit by freeze, delete V from slides instead.
5. **Digital-twin interactivity** (deck promises it): precompute a grid of scenario runs (battery size, outage rate, cloudiness, EV/2W share) and embed in the dashboard with sliders + day player (play/pause through 24h, showing flows). Static + precomputed is safer than a live server; optionally deploy later.
6. **Decision rationale/explainability**: for each hour GridFlex outputs "why" strings (e.g. "holding 60 kWh for DISCOM stress 18:30; deferring pump to 11:00 solar"). Great for demo.
7. **Multi-agent claim made real, minimally**: household/pump/battery/grid agents as classes with a coordinator that gathers flexibility offers and dispatches; the MILP sits inside the coordinator. Do only if time; otherwise reword the slide to "coordinator + asset models".

### P2 - wow factor (only if P0+P1 done and time remains)
- Software-in-the-loop: Python gateway talking MQTT to simulated smart-plugs/battery inverter (mosquitto locally), showing a command round-trip + failure fallback to rule mode (edge-safe: if optimiser/network dies, local rule keeps critical loads up).
- Robust/stochastic MILP using outage scenarios (e.g. 10 sampled outage paths) vs reserve heuristic.
- Learned outage-risk model by hour/weekday; warm-start MILP and receding-horizon speedups.
- Consumer UX: WhatsApp/SMS-style alerts mock ("Run pump before 3 pm; evening supply limited 6:30-10:30") - strong for low-income, low-smartphone context; Hindi/Telugu strings.
- Sensitivity/tornado chart for the economics; carbon avoided estimate (with cited grid emission factor).

### P3 - delivery (1-6 Dec)
- 15-slide deck (see 4). Repo README with one-command run, screenshots, results table, limitations. Demo video 3-5 min (see 4). Form text drafted from `docs/SUBMISSION_GUIDE.md`. Dry-run: fresh clone -> run -> dashboard in <10 min. Submit 6 Dec; 7-8 Dec reserved for failures.

## 4. Narrative that wins
One-line pitch: "GridFlex turns a neighbourhood's rooftop solar, a shared second-life battery and deferrable loads into a software-only reliability service for the families the grid fails first - at a price they and the DISCOM can afford."
Demo story (3-5 min): (1) 7 pm in a peri-urban neighbourhood, DISCOM announces evening limit + unannounced outage hits -> today: lights off (grid-only 1.55 h/day); (2) forecast + plan: battery reserved, pumps ran at noon; (3) same day with GridFlex: critical circuit never drops; (4) DISCOM console: feeder peak down, technical loss proxy down; (5) equity chart: low-income homes protected; (6) cost per household and who owns/operates it; (7) honest limitations + pilot plan.
Headline numbers must come from multi-seed runs with CIs and stronger baselines, not the current single run.
Deck fixes: drop Gurobi/CPLEX (say HiGHS), remove or reproduce all unreproduced numbers, de-emphasise EV, drop Paillier slide for DISCOM analytics, add outage-hours baseline + O&M + economics slides.

## 5. Working rules for the agent
- Never fabricate data/citations; label synthetic vs real; every cost has a source or ASSUMPTION tag + sensitivity range.
- Keep `python run.py` working at all times; add flags instead of breaking defaults; keep runtime reasonable (<15 min full).
- Keep assumptions only in `config.py`; metrics only in `simulate.metrics`; add tests with every new constraint.
- Verify results before updating slides/README; regenerate `outputs/` from code.
- Suggested first prompts: (a) "Implement P0 baselines + ablation table + multi-seed CI, run, show table." (b) "Add grid_charge_cap and flexible time windows, rerun, report curtailment/outage change." (c) "Build sizing.py Pareto + lifeline tier + unit-economics table." (d) "Add archetypes + fairness metrics." (e) "Add DISCOM tab + precomputed what-if sliders to dashboard."

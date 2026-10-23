# Ownership, operations and maintenance model

GridFlex is software plus a shared battery and cheap retrofit controls. It is
designed to be owned and run **inside** the neighbourhood, not by the DISCOM.

## Who owns what

| Asset | Owner | Why |
|---|---|---|
| Rooftop PV (existing) | Individual households | Already installed under PM Surya Ghar / state schemes; GridFlex does not touch ownership |
| Community battery (100 kWh second-life LFP) | Registered housing-society / RWA cooperative, or a local energy-service company (ESCO) contracted by it | Keeps the asset local and mortgageable; the cooperative can raise a small loan against the reliability fee |
| Smart plugs, gateway, LT panel instrumentation | Same owner as the battery | ~₹1,500 per household, recovered through the fee |
| Control software (GridFlex) | Licensed to the owner; open-source stack (Python, SciPy/HiGHS) | No per-household licence fee, no commercial solver |
| Feeder, transformer, protection | DISCOM | GridFlex never operates utility equipment; it only responds to signals |

The DISCOM is a **counterparty, not an owner**: it publishes the evening
allocation and outage schedule, receives the analytics console, and pays for
verified peak reduction and loss reduction.

## Who operates it

| Role | Who | Time | Paid by |
|---|---|---|---|
| Neighbourhood operator | One trained resident (or RWA secretary) | ~2 h/week: approve schedules, handle opt-outs, read the console | Fee (₹3,000–5,000/month) |
| Field technician | Shared across ~10 neighbourhoods | 1 visit/month per site + fault call-outs | O&M budget (3 % of capex) |
| DISCOM feeder engineer | Existing staff | Reads the console, sets the evening allocation | Existing salary |
| Software maintainer | Team/ESCO | Remote updates, model retraining | Licence/support contract |

No new utility staff, no control room, no hardware in the substation.

## Operating rhythm

- **Day ahead (18:00):** the system ingests the archived NWP forecast, household
  flexible-load declarations (pump/geyser/EV windows), the DISCOM's announced
  evening allocation and the feeder outage history.
- **Hourly:** the MILP re-plans the next 24 h and dispatches the first hour.
- **Every 15 min:** meter data updates state of charge and flexible-load progress;
  the real-time correction overrides the plan if the feeder limit binds.
- **Monthly:** the operator reviews reliability per archetype, the fee ledger and
  the DISCOM settlement; the technician checks battery health and connections.
- **Yearly:** battery capacity test; re-tune the reserve using the past year of
  outage data.

## Failure modes and fallbacks

| Failure | Behaviour |
|---|---|
| Optimiser or network unreachable | Local rule engine holds a 2 h reserve for the lifeline circuit and serves flexible loads inside their windows |
| Meter/telemetry loss | Battery reverts to a fixed evening reserve; residents keep supply |
| Battery unavailable | Bypass to grid-only; the dashboard flags reduced reliability |
| DISCOM stress window extended | The controller re-solves with the new cap; critical load is protected first |
| Household opts out | Its flexible loads are removed from the offer pool; critical service is unaffected |

The rule fallback is implemented and tested (`tests/test_model.py::test_mpc_fallback_when_infeasible`),
not just described.

## Economics responsibility

- Households pay a tiered fee: **₹0 for the low-income lifeline tier**, ₹60 for
  standard, ₹120 for higher-use homes (weighted income is shown in the dashboard).
Numbers from the current build: ₹9,000/hh upfront → ₹144.6/hh/month annualised; the grid bill
is ₹53.9/hh/month **higher** than the unmanaged case; avoided outage value ₹293.9 and the DISCOM
peak credit ₹30.5 give a net **+₹126.0/hh/month**. The fee tiers collect ₹45/hh/month, 31 % of
gross cost, so the honest statement is "reliability value plus cross-subsidy", not "self-funding".
At the bottom of the VoLL range (₹30/kWh) the net value approaches zero.

- Fee income alone does **not** recover the asset at ₹6,000/kWh. The gap is closed
  by (a) the household bill saving from self-consumption, (b) the avoided cost of
  outages (VoLL ₹30–124/kWh), (c) the DISCOM peak/loss payment, and (d) any
  state or CSR support for second-life storage. This is stated explicitly in the
  unit-economics table rather than hidden in a single "payback" number.
- The DISCOM payment should be a **verified** monthly settlement: measured evening
  peak reduction against the counterfactual schedule, and loss reduction from the
  feeder model. No payment for unverified claims.

## Scaling model

One operator covers one transformer area (80–150 homes). A cluster of ~10
neighbourhoods shares one technician and one DISCOM relationship. Software cost
is effectively fixed, so cost per household falls with each additional site; the
battery is the only cost that scales linearly. The pilot should start with one
feeder, one RWA and a second-life battery supplier, and publish the measured
reliability before expanding.

## Run, verify and reproduce

    pip install numpy pandas scipy scikit-learn matplotlib pytest
    python run.py --oracle --seeds 20 --workers 8    # ~35 min, writes outputs/ + docs/ASSUMPTIONS.md
    python -m pytest tests                           # 16 tests, ~40 s
    python run.py --quick --no-whatif                # ~4 min smoke test

Data are cached in `data/hyderabad/`; `--refresh-weather` re-fetches them. The dashboard is a
single file with Chart.js vendored in, so the judging demo needs no network.

**Reproducibility caveat.** The MILP runs with an 8 s solve limit and a 0.2 % optimality gap to
keep the 20-seed sweep inside half an hour. Solutions are therefore near-optimal, not identical:
two full runs of the same command have differed by up to ~0.02 interrupted h/day. Multi-seed
means in `results.json` are the numbers to quote; the single-seed column is one draw.

**What each run writes.** `outputs/results.json` (metrics for seven scenarios, 20-seed CIs and
95 % intervals, ablation, equity incl. rule sensitivity, economics, sizing on two tariff schemes,
what-if grid, DISCOM console, full assumption registry), `outputs/dashboard.html`,
`outputs/{scenarios,day_plot,sizing,voltage}.png`, `docs/ASSUMPTIONS.md`, `docs/DATA.md`.

**Regression tests** cover energy balance and cap/voltage/SOC limits per scenario, flexible
windows, optimiser fallback, battery limits, metric ranges, equal-per-household allocation, the
feeder model, economics ranges, data calibration, forecast leakage (no future information), and
the three newer surfaces: DISCOM actions are non-empty/ranked/monetised, the lifeline tariff axis
moves the frontier by exactly the fee, and the allocation rule is measurable on a stressed feeder.

## Version control and the delivered build

The deliverable is one local commit on top of the handoff baseline (`Baseline: original GridFlex
prototype as handed off`). There is **no remote**: `git remote -v` is empty by design, so nothing
has been pushed. Adding one is a single command when a host is chosen:

    git remote add origin <url> && git push -u origin master

The build commit adds the source, tests, docs and the rendered artefacts. Read its hash with:

    git log -1 --format='%H %s'

**Reproduce from a clean clone** (the cached real weather is committed, so no network is needed
for the simulation itself):

    pip install numpy pandas scipy scikit-learn matplotlib pytest
    python run.py --oracle --seeds 20 --workers 8    # 35 min, rewrites outputs/ and docs/ASSUMPTIONS.md
    python -m pytest tests -q                        # 16 tests
    python -m http.server 8000                       # open http://localhost:8000/outputs/dashboard.html

**What is committed, and why**

| Path | Committed | Reason |
|---|---|---|
| `gridflex/`, `run.py`, `tests/` | yes | the prototype itself |
| `docs/*.md`, `docs/architecture.{html,png}` | yes | write-up, deck script, operations, generated assumptions/data provenance |
| `data/hyderabad/` (388 KB) | yes | cached real observations, archived day-ahead forecast and provenance - the run is reproducible offline and the "real data" claim is auditable |
| `outputs/results.json` | yes | every number in the docs and dashboard can be checked without repeating the 35-minute run |
| `outputs/dashboard.html`, `outputs/site/index.html` | yes | the judge-facing artefact, self-contained (Chart.js inlined), works offline; both are written by the same `make_dashboard` call, so they cannot diverge |
| `outputs/{scenarios,day_plot,sizing,voltage}.png` | yes | deck screenshots, regenerated by the same run |
| `outputs/v1_baseline/` | yes, unchanged | pre-work prototype outputs kept as the before/after comparison; already in the baseline commit, so removing it would drop provenance |
| `outputs/*.log`, `*.pid`, caches | no (ignored) | generated run state |

`outputs/outage_hours.png` is a tracked, unreferenced figure from the handoff build; it is left in
place rather than deleted so the baseline history and the current tree stay comparable.

## Publishing the demo

Upload **one file**: `outputs/site/index.html` (about 570 KB). It is written by the same
`make_dashboard` call that writes `outputs/dashboard.html`, so the two are byte-identical, and it
is fully self-contained: Chart.js is inlined, all 14 days of scenario data are embedded, there are
no external requests and no absolute paths. It renders the same from a file path or a web server,
so a judge can open it offline and a host can serve it as-is. Do **not** upload anything else from
`outputs/site/` - the directory contains only that page.

Choose one host:

1. **Netlify Drop (fastest, no CLI or account needed to start).** Open <https://app.netlify.com/drop>
   in a browser and drag the `outputs/site` folder onto the page. A public URL appears in seconds;
   claim the site with an account only if it should stay up permanently.
2. **GitHub Pages (needs the repo remote first).** `git remote add origin <url>`, `git push -u
   origin master`, then in the repository: Settings -> Pages -> Deploy from a branch, pick a
   `gh-pages` branch whose root contains `index.html`. Pages serves a branch root, not
   `outputs/site/`, so put the file at the root of that branch.
3. **Freebuff Sites (in-app, Worker-backed).** Creates a project under this Freebuff account and
   needs a static-assets manifest plus an explicit publish step. The URL is public, so publish only
   with the owner's go-ahead; the free plan allows three published sites.

Check the page after upload: the KPI row should read `0.87 h/day`, `94.4%`, `97.1%`, `28.5 kW`,
`451 ₹`; all seven tabs should open; and the browser console should be empty. Nothing in the page
needs a server, so if a host adds redirects or rewrites, disable them - a plain static file is the
intended deployment.

# GridFlex prototype (Schneider Yuva Yodha, Challenge 3)

Forecast -> MILP -> dispatch loop for one distribution-transformer neighbourhood (80 homes, 100 kWp rooftop PV, 100 kWh community battery).

    pip install numpy pandas scipy scikit-learn matplotlib
    python run.py            # ~1 min; add --oracle for perfect-forecast upper bound
    open outputs/dashboard.html

Files: `gridflex/config.py` (every assumption) · `data.py` (synthetic data + feeder outages) · `forecast.py` (HistGradientBoosting, quantile loss, 24h direct forecasts) · `optimizer.py` (HiGHS MILP, 96 steps) · `simulate.py` (plant + 3 scenarios) · `economics.py` · `report.py`.

Scenarios on identical weather/load/outages (last 14 days held out): grid-only, PV+battery unmanaged (self-consumption rule, proportional load cuts), GridFlex (forecast + MILP + critical-load priority + deferrable flexible loads + soft backup reserve).

## Known limitations (fix in this order)
1. Data is synthetic -> swap `data.make_data` for real/semi-real data (irradiance: NASA POWER/PVGIS; load: any public Indian smart-meter or feeder dataset; or scale a public profile).
2. No network physics (voltage, losses). Feeder = single import limit. Add LinDistFlow later if time.
3. Grid-charging at night hits the 80 kW transformer limit (peak_import_kw). Add a charge-from-grid cap.
4. Curtailment ~39% = PV is large vs battery. Allow export / larger battery / shift flexible loads to noon (try raising backlog_pen, lowering flexible deadline).
5. Economics: breakeven fee ~Rs150/hh/month at current assumptions - too high for low-income users. Needs cost-down levers (see docs/SUBMISSION_GUIDE.md).
6. Unplanned outages are not forecast; `reserve_frac` is a blunt hedge. Could learn outage-risk by hour.

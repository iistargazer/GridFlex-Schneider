# GridFlex data provenance

| signal | kind | source | notes |
|---|---|---|---|
| irradiance, temperature, wind | real (reanalysis) | ERA5 reanalysis via Open-Meteo archive API | https://archive-api.open-meteo.com/v1/archive |
| day-ahead weather forecast | real (archived operational run) | Open-Meteo previous-runs API (archived operational forecasts) | lead time 24 h, https://previous-runs-api.open-meteo.com/v1/forecast |
| PV output | modelled from real GHI | Erbs diffuse fraction, isotropic transposition, tilt=lat, NOCT cell temperature, 14 % system losses | PVGIS validation 2.83 % |
| critical + flexible load | calibrated synthetic | Telangana LT-I consumption slabs + published Indian residential shape | no public household microdata used |
| outages | simulated, calibrated | CEEW 2019: 3.5 outage h/day in notified town areas, 1.3 in district HQ | realised value reported per run |

Forecast skill on held-out days: load MAPE 6.8 %, PV nMAE 2.0 %, 80 % interval coverage 70 % (PV).

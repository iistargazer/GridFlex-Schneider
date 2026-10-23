"""Real weather + real day-ahead forecasts for the pilot site, cached for offline runs.

Sources (all verified reachable at build time):
  * Open-Meteo archive API (ERA5 reanalysis) - observed GHI, 2 m temperature
    and 10 m wind. NASA POWER's hourly solar product lags ~4 months (its
    `ALLSKY_SFC_SW_DWN` is -999 fill for this window), so ERA5 is the source of
    record and NASA POWER is used as an independent cross-check on an older
    overlapping month.
  * Open-Meteo previous-runs API - archived operational forecasts with explicit
    lead time (`*_previous_day1`), i.e. a genuine day-ahead NWP forecast.
  * PVGIS v5.3 seriescalc (2023) - independent PV yield used only to validate
    the simple PV model below (PVGIS has no 2026 series yet).

The PV model (Erbs diffuse fraction + isotropic transposition + NOCT cell
temperature + system losses) is documented, deterministic and validated against
PVGIS; the validation error is written into provenance.json and quoted in docs.

Run `python -m gridflex.weather --refresh` to rebuild the cache.
"""
import json
import os
from datetime import datetime

import numpy as np
import pandas as pd

from .config import P

CACHE_DIR = os.path.join("data", "hyderabad")
CACHE_CSV = os.path.join(CACHE_DIR, "weather_15min.csv")
PROV_JSON = os.path.join(CACHE_DIR, "provenance.json")

NASA_URL = "https://power.larc.nasa.gov/api/temporal/hourly/point"
OMA_URL = "https://archive-api.open-meteo.com/v1/archive"
OM_URL = "https://previous-runs-api.open-meteo.com/v1/forecast"
PVGIS_URL = "https://re.jrc.ec.europa.eu/api/v5_3/seriescalc"


# ---------------------------------------------------------------------------
# PV model
# ---------------------------------------------------------------------------
def solar_geometry(idx, lat, lon):
    """Cosine of zenith and of incidence on a south-facing tilt=lat array."""
    doy = idx.dayofyear.values
    # local solar time = IST + (lon - 82.5 E) * 4 min
    solar_hour = idx.hour.values + idx.minute.values / 60 + (lon - 82.5) / 15.0
    decl = np.radians(23.45 * np.sin(np.radians(360 * (284 + doy) / 365)))
    ha = np.radians(15 * (solar_hour - 12))
    lat_r, tilt = np.radians(lat), np.radians(abs(lat))
    cosz = np.sin(lat_r) * np.sin(decl) + np.cos(lat_r) * np.cos(decl) * np.cos(ha)
    cos_t = (np.sin(decl) * np.sin(lat_r - tilt)
             + np.cos(decl) * np.cos(lat_r - tilt) * np.cos(ha))
    return np.clip(cosz, 0, None), np.clip(cos_t, 0, None)


def pv_from_ghi(idx, ghi, temp, lat, lon, kwp, ws=None):
    """AC PV power (kW) from GHI. Erbs diffuse split + isotropic sky + NOCT."""
    cosz, cos_t = solar_geometry(idx, lat, lon)
    ghi = np.clip(np.asarray(ghi, float), 0, None)
    temp = np.asarray(temp, float)
    kt = np.where(cosz > 0.05, ghi / (1367 * np.maximum(cosz, 0.05)), 0)
    kt = np.clip(kt, 0, 1)
    df = np.where(kt <= 0.22, 1 - 0.09 * kt,
                  np.where(kt <= 0.8, 0.9511 - 0.1604 * kt + 4.388 * kt**2
                           - 16.638 * kt**3 + 12.336 * kt**4, 0.165))
    dhi = np.clip(df, 0, 1) * ghi
    dni = np.where(cosz > 0.05, (ghi - dhi) / np.maximum(cosz, 0.05), 0)
    tilt = np.radians(abs(lat))
    poa = (dni * cos_t + dhi * (1 + np.cos(tilt)) / 2
           + ghi * 0.2 * (1 - np.cos(tilt)) / 2)
    poa = np.clip(poa, 0, None)
    tcell = temp + poa / 800.0 * 25.0              # NOCT 45 C, 20 C ambient
    dc = kwp * poa / 1000.0 * (1 - 0.004 * (tcell - 25))
    return np.clip(dc * 0.86, 0, kwp)               # 14 % system losses


# ---------------------------------------------------------------------------
# Fetching
# ---------------------------------------------------------------------------
def _get(url, params, timeout=120):
    import requests
    r = requests.get(url, params=params, timeout=timeout)
    r.raise_for_status()
    return r.json()


def fetch_observations(p: P):
    """ERA5 reanalysis via the Open-Meteo archive API (real observations)."""
    params = dict(latitude=p.site_lat, longitude=p.site_lon,
                  start_date=p.weather_start, end_date=p.weather_end,
                  hourly="shortwave_radiation,temperature_2m,wind_speed_10m",
                  timezone="Asia/Kolkata")
    j = _get(OMA_URL, params)
    h = j["hourly"]
    df = pd.DataFrame(dict(idx=pd.to_datetime(h["time"]),
                           ghi=h["shortwave_radiation"], temp=h["temperature_2m"],
                           ws=h["wind_speed_10m"])).set_index("idx")
    df.index = df.index.tz_localize("Asia/Kolkata")
    return df.astype(float)


def fetch_nasa_crosscheck(p: P):
    """NASA POWER GHI for a month where its hourly product exists."""
    params = dict(parameters="ALLSKY_SFC_SW_DWN,T2M", community="RE",
                  longitude=p.site_lon, latitude=p.site_lat,
                  start="20260501", end="20260531", format="JSON",
                  **{"time-standard": "lst"})
    j = _get(NASA_URL, params)
    par = j["properties"]["parameter"]
    df = pd.DataFrame([dict(idx=pd.to_datetime(k, format="%Y%m%d%H"),
                            ghi=v, temp=par["T2M"][k])
                       for k, v in par["ALLSKY_SFC_SW_DWN"].items()]).set_index("idx")
    df.index = df.index.tz_localize("Asia/Kolkata")
    return df[df.ghi >= 0]


def fetch_forecast(p: P):
    params = dict(latitude=p.site_lat, longitude=p.site_lon,
                  hourly="shortwave_radiation_previous_day1,"
                         "temperature_2m_previous_day1",
                  start_date=p.weather_start, end_date=p.weather_end,
                  timezone="Asia/Kolkata")
    j = _get(OM_URL, params)
    h = j["hourly"]
    df = pd.DataFrame(dict(idx=pd.to_datetime(h["time"]),
                           ghi_fc=h["shortwave_radiation_previous_day1"],
                           temp_fc=h["temperature_2m_previous_day1"])).set_index("idx")
    df.index = df.index.tz_localize("Asia/Kolkata")
    return df.astype(float)


def fetch_pvgis_validation(p: P, year=2023):
    """Annual PVGIS yield for a south-facing tilt=lat array (validation only)."""
    out = {}
    for tag, params in dict(
        tilted=dict(angle=abs(p.site_lat), aspect=0),
        horizontal=dict(angle=0, aspect=0),
    ).items():
        q = dict(lat=p.site_lat, lon=p.site_lon, startyear=year, endyear=year,
                 pvcalculation=1, peakpower=1, loss=14, outputformat="json",
                 browser=0, **params)
        j = _get(PVGIS_URL, q)
        df = pd.DataFrame(j["outputs"]["hourly"])
        out[tag] = df
    tilted, horiz = out["tilted"], out["horizontal"]
    # PVGIS timestamps are UTC; convert for the geometry model
    idx = pd.to_datetime(tilted["time"], format="%Y%m%d:%H%M").dt.tz_localize("UTC")
    idx = idx.dt.tz_convert("Asia/Kolkata")
    ghi = horiz["G(i)"].values
    temp = tilted["T2m"].values
    model = pv_from_ghi(pd.DatetimeIndex(idx), ghi, temp, p.site_lat, p.site_lon, 1.0)
    pvgis_kwh = float(tilted["P"].sum()) / 1000.0
    model_kwh = float(model.sum())
    return dict(year=year, pvgis_kwh_per_kwp=round(pvgis_kwh, 1),
                model_kwh_per_kwp=round(model_kwh, 1),
                error_pct=round(100 * (model_kwh - pvgis_kwh) / max(pvgis_kwh, 1e-9), 2))


# ---------------------------------------------------------------------------
# Cache build / load
# ---------------------------------------------------------------------------
def build_cache(p=P(), refresh=False):
    os.makedirs(CACHE_DIR, exist_ok=True)
    if os.path.exists(CACHE_CSV) and not refresh:
        return load_cache()

    obs = fetch_observations(p)
    fc = fetch_forecast(p)
    full = pd.date_range(f"{p.weather_start} 00:00", f"{p.weather_end} 23:45",
                         freq="15min", tz="Asia/Kolkata")
    obs = obs.resample("15min").interpolate("linear").reindex(full).ffill().bfill()
    fc = fc.resample("15min").interpolate("linear").reindex(full).ffill().bfill()
    df = obs.join(fc, how="left").ffill().bfill()
    df["pv"] = pv_from_ghi(df.index, df.ghi, df.temp, p.site_lat, p.site_lon, p.pv_kwp)
    df = df[["ghi", "temp", "ws", "pv", "ghi_fc", "temp_fc"]]
    df.index.name = "ts"
    df.round(3).to_csv(CACHE_CSV, float_format="%.3f")

    try:
        val = fetch_pvgis_validation(p)
    except Exception as e:                        # validation is best-effort
        val = dict(error="validation unavailable: %s" % e)

    try:
        nasa = fetch_nasa_crosscheck(p)
        era5 = fetch_observations(P(site_lat=p.site_lat, site_lon=p.site_lon,
                                    weather_start="2026-05-01", weather_end="2026-05-31",
                                    n_days=31))
        common = nasa.join(era5[['ghi']], how="inner", lsuffix="_nasa", rsuffix="_era5")
        cross = dict(source="NASA POWER vs ERA5 GHI, 2026-05",
                     nasa_mean=round(float(nasa.ghi.mean()), 1),
                     era5_mean=round(float(era5.ghi.mean()), 1),
                     correlation=round(float(common.ghi_nasa.corr(common.ghi_era5)), 3),
                     n_hours=int(len(common)))
    except Exception as e:
        cross = dict(error="NASA cross-check unavailable: %s" % e)

    prov = dict(
        built_at=datetime.now().isoformat(timespec="seconds"),
        site=dict(name=p.site_name, lat=p.site_lat, lon=p.site_lon),
        window=dict(start=p.weather_start, end=p.weather_end, days=p.n_days),
        observations=dict(source="ERA5 reanalysis via Open-Meteo archive API",
                          parameters=["shortwave_radiation", "temperature_2m",
                                      "wind_speed_10m"],
                          url=OMA_URL, time_standard="Asia/Kolkata (IST)",
                          licence="Open-Meteo data under CC-BY 4.0; ERA5 (C3S)",
                          kind="real (reanalysis)",
                          nasa_crosscheck=cross),
        forecasts=dict(source="Open-Meteo previous-runs API (archived operational forecasts)",
                       variables=["shortwave_radiation_previous_day1",
                                  "temperature_2m_previous_day1"],
                       url=OM_URL, lead_time_hours=24,
                       licence="Open-Meteo data under CC-BY 4.0",
                       kind="real"),
        pv_model=dict(kind="modelled from real GHI",
                      detail="Erbs diffuse fraction, isotropic transposition, tilt=lat, "
                             "NOCT cell temperature, 14 % system losses",
                      validation_pvgis=val),
        pv_annual_mean_kwh_per_kwp=round(float(df.pv.sum() * 0.25 / p.pv_kwp / p.n_days * 365), 1),
        forecast_bias=dict(ghi_mean_obs=round(float(df.ghi.mean()), 2),
                           ghi_mean_fc=round(float(df.ghi_fc.mean()), 2),
                           ghi_mae=round(float((df.ghi_fc - df.ghi).abs().mean()), 2)),
    )
    json.dump(prov, open(PROV_JSON, "w"), indent=1)
    return load_cache()


def load_cache():
    if not os.path.exists(CACHE_CSV):
        raise FileNotFoundError(
            "weather cache missing - run `python -m gridflex.weather --refresh`")
    df = pd.read_csv(CACHE_CSV, parse_dates=["ts"], index_col="ts")
    return df


if __name__ == "__main__":
    import sys
    p = P()
    d = build_cache(p, refresh="--refresh" in sys.argv)
    print(d.describe().round(2))
    print(json.dumps(json.load(open(PROV_JSON)), indent=1)[:2000])

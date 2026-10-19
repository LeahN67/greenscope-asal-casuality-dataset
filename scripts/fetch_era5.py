"""
Step 3. Download ERA5-Land monthly means (potential evaporation, soil moisture layer 1) from the
Copernicus Climate Data Store, and correct the months ECMWF has flagged as wrong.

ECMWF known issue: in the "monthly_averaged_reanalysis" product, every accumulated variable
(potential evaporation among them) is wrong for September 2022 to February 2024, and ECMWF will not
replace those data. Its recommended workaround is the "monthly_averaged_reanalysis_by_hour_of_day"
product at 00:00, which holds the same quantity (mean daily total). This script downloads that product
for the affected months and writes it over potential evaporation in those months. Soil moisture is
not accumulated and is not affected.
https://forum.ecmwf.int/t/issue-affecting-era5-land-monthly-averaged-reanalysis-for-the-period-september-2022-to-february-2024/2370

Credentials: set CDSAPI_KEY (your CDS personal access token) or keep it in ~/.cdsapirc.
Never put the key in this file or commit a .cdsapirc file.

    python scripts/fetch_era5.py                      # download 2000 to 2025, or correct an existing file
    python scripts/fetch_era5.py --start 2000 --end 2025 --force
    python scripts/fetch_era5.py --insecure           # only if your network breaks SSL checks

The CDS often delivers a ZIP; it is unpacked and merged into one file.
Output: data/raw/era5_land/era5_land_monthly.nc
"""
import argparse
import json
import os
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from gs_common import (ERA5, ERA5_BAD_MONTHS, ERA5_DIR, ERA5_FIX_ATTR, ERA5_LEGACY, ERA5_REQUEST,
                       record_download)

DATASET = "reanalysis-era5-land-monthly-means"
VARIABLES = ["potential_evaporation", "volumetric_soil_water_layer_1"]
ACCUMULATED = {"potential_evaporation": "pev"}    # requested name: name in the NetCDF file
AREA = [5.5, 33.5, -5.0, 42.0]          # North, West, South, East; covers the ASAL bounding box


def time_name(ds):
    return "valid_time" if "valid_time" in ds.dims else "time"


def month_keys(ds):
    return pd.DatetimeIndex(ds[time_name(ds)].values).strftime("%Y-%m")


def affected_months(ds):
    m = month_keys(ds)
    return [k for k in m if ERA5_BAD_MONTHS[0] <= k <= ERA5_BAD_MONTHS[1]]


def apply_fix(ds, fix, variables=("pev",)):
    """Overwrite the affected months of the accumulated variables in ds with the values in fix.

    Matching is by calendar month; the grids must be identical. Returns the corrected dataset and the
    list of months replaced."""
    months = affected_months(ds)
    if not months:
        return ds, []
    fkeys = list(month_keys(fix))
    missing = [m for m in months if m not in fkeys]
    if missing:
        raise SystemExit(f"The correction download lacks months {missing}")
    for coord in ("latitude", "longitude"):
        if ds[coord].size != fix[coord].size or not np.allclose(ds[coord].values, fix[coord].values):
            raise SystemExit(f"The correction download is on a different {coord} grid")
    tn, tf = time_name(ds), time_name(fix)
    dkeys = list(month_keys(ds))
    out = ds.copy(deep=True)
    for v in variables:
        data = out[v].values
        for m in months:
            data[dkeys.index(m)] = fix[v].isel({tf: fkeys.index(m)}).values
        out[v] = (out[v].dims, data, out[v].attrs)
    out.attrs[ERA5_FIX_ATTR] = (
        f"{', '.join(variables)} for {months[0]} to {months[-1]} ({len(months)} months) replaced by the "
        "ERA5-Land monthly_averaged_reanalysis_by_hour_of_day product at 00:00 (ECMWF known issue for "
        f"accumulated variables in the monthly averaged product); applied {datetime.now(timezone.utc):%Y-%m-%d}")
    return out, months


def normalise(download, out):
    """Turn the CDS download (ZIP or NetCDF) into a single NetCDF file."""
    if not zipfile.is_zipfile(download):
        shutil.move(download, out)
        return
    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(download) as z:
            z.extractall(tmp)
        parts = sorted(Path(tmp).rglob("*.nc"))
        if not parts:
            raise SystemExit("The CDS ZIP contained no NetCDF files")
        print(f"   ZIP contained: {[p.name for p in parts]}")
        datasets = [xr.open_dataset(p).load() for p in parts]
        xr.merge(datasets, compat="override").to_netcdf(out)
        for d in datasets:
            d.close()
    Path(download).unlink()


def client_from_env(insecure):
    import cdsapi
    kwargs = {"url": "https://cds.climate.copernicus.eu/api", "verify": not insecure}
    if os.getenv("CDSAPI_KEY"):
        kwargs["key"] = os.environ["CDSAPI_KEY"]
    elif not (Path.home() / ".cdsapirc").exists():
        raise SystemExit("No CDS key found. Copy your Personal Access Token from "
                         "https://cds.climate.copernicus.eu/profile and set it in this window:\n"
                         '   PowerShell:  $env:CDSAPI_KEY = "your-token"\n'
                         "   Linux/macOS: export CDSAPI_KEY=your-token")
    return cdsapi.Client(**kwargs)    # falls back to ~/.cdsapirc when CDSAPI_KEY is not set


def correct_file(client, path=ERA5):
    """Download the by-hour-of-day product for the affected months and patch the file in place."""
    with xr.open_dataset(path) as ds:
        if ERA5_FIX_ATTR in ds.attrs:
            print(f"   already corrected: {ds.attrs[ERA5_FIX_ATTR]}")
            return
        months = affected_months(ds)
    if not months:
        print("   file does not cover the affected months; no correction needed")
        return
    years = sorted({m[:4] for m in months})
    request = {
        "product_type": "monthly_averaged_reanalysis_by_hour_of_day",
        "variable": list(ACCUMULATED),
        "year": years,
        "month": [f"{m:02d}" for m in range(1, 13)],
        "time": "00:00",
        "area": AREA,
        "data_format": "netcdf",
    }
    print(f"   correcting {months[0]} to {months[-1]}: requesting the by-hour-of-day product at 00:00")
    download = ERA5_DIR / "era5_fix_download.tmp"
    fix_path = ERA5_DIR / "era5_land_pev_by_hour_00.nc"
    client.retrieve(DATASET, request, str(download))
    normalise(download, fix_path)
    record_download("ERA5-Land monthly means by hour of day (00:00)", f"CDS {DATASET} {years[0]}-{years[-1]}",
                    fix_path, notes="correction for ECMWF known issue Sep 2022 to Feb 2024")

    ds = xr.open_dataset(path).load()
    fix = xr.open_dataset(fix_path).load()
    ds.close()
    before = float((-ds["pev"]).sel({time_name(ds): ds[time_name(ds)][
        np.isin(month_keys(ds), months)]}).mean()) * 1000
    out, replaced = apply_fix(ds, fix, tuple(ACCUMULATED.values()))
    after = float((-out["pev"]).sel({time_name(out): out[time_name(out)][
        np.isin(month_keys(out), months)]}).mean()) * 1000
    tmp = path.with_suffix(".tmp.nc")
    out.to_netcdf(tmp)
    fix.close()
    tmp.replace(path)
    print(f"   replaced {len(replaced)} months; mean potential evaporation in those months "
          f"{before:.2f} -> {after:.2f} mm/day")

    log = json.loads(ERA5_REQUEST.read_text()) if ERA5_REQUEST.exists() else {}
    log["correction_request"] = {"dataset": DATASET, "request": request, "months_replaced": replaced}
    ERA5_REQUEST.write_text(json.dumps(log, indent=1))
    record_download("ERA5-Land monthly means (corrected)", "merged file", path, notes=out.attrs[ERA5_FIX_ATTR])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start", type=int, default=2000)
    ap.add_argument("--end", type=int, default=2025)
    ap.add_argument("--force", action="store_true", help="download again even if the file exists")
    ap.add_argument("--insecure", action="store_true", help="disable SSL certificate checks (not recommended)")
    args = ap.parse_args()

    print("STEP 3  ERA5-Land monthly means")
    existing = ERA5 if ERA5.exists() else (ERA5_LEGACY if ERA5_LEGACY.exists() else None)
    if existing and not args.force:
        print(f"   using existing {existing}")
        with xr.open_dataset(existing) as ds:
            done = ERA5_FIX_ATTR in ds.attrs or not affected_months(ds)
        if not done:
            correct_file(client_from_env(args.insecure), existing)
        return

    client = client_from_env(args.insecure)
    request = {
        "product_type": "monthly_averaged_reanalysis",
        "variable": VARIABLES,
        "year": [str(y) for y in range(args.start, args.end + 1)],
        "month": [f"{m:02d}" for m in range(1, 13)],
        "time": "00:00",
        "area": AREA,
        "data_format": "netcdf",
    }
    ERA5_DIR.mkdir(parents=True, exist_ok=True)
    download = ERA5_DIR / "era5_download.tmp"
    print(f"   requesting {DATASET} {args.start}-{args.end} (queueing can take a while)")
    client.retrieve(DATASET, request, str(download))
    normalise(download, ERA5)
    ERA5_REQUEST.write_text(json.dumps({"dataset": DATASET, "request": request}, indent=1))
    record_download("ERA5-Land monthly means", f"CDS {DATASET} {args.start}-{args.end}", ERA5,
                    notes=",".join(VARIABLES))
    print(f"   saved {ERA5}")
    correct_file(client)


if __name__ == "__main__":
    main()

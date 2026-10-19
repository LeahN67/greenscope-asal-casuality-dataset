"""
Step 3. Download ERA5-Land monthly means (potential evaporation, soil moisture layer 1) from the
Copernicus Climate Data Store.

Credentials: set CDSAPI_KEY (your CDS personal access token) or keep it in ~/.cdsapirc.
Never put the key in this file or commit a .cdsapirc file.

    python scripts/fetch_era5.py                      # 2000 to 2025
    python scripts/fetch_era5.py --start 2000 --end 2025 --force
    python scripts/fetch_era5.py --insecure           # only if your network breaks SSL checks

The CDS often delivers a ZIP; it is unpacked and merged into one file.
Output: data/raw/era5_land/era5_land_monthly.nc
"""
import argparse
import os
import shutil
import tempfile
import zipfile
from pathlib import Path

import xarray as xr

from gs_common import ERA5, ERA5_DIR, record_download

DATASET = "reanalysis-era5-land-monthly-means"
VARIABLES = ["potential_evaporation", "volumetric_soil_water_layer_1"]
AREA = [5.5, 33.5, -5.0, 42.0]          # North, West, South, East; covers the ASAL bounding box


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


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start", type=int, default=2000)
    ap.add_argument("--end", type=int, default=2025)
    ap.add_argument("--force", action="store_true", help="download again even if the file exists")
    ap.add_argument("--insecure", action="store_true", help="disable SSL certificate checks (not recommended)")
    args = ap.parse_args()

    print("STEP 3  ERA5-Land monthly means")
    if ERA5.exists() and not args.force:
        print(f"   using existing {ERA5}")
        return

    import cdsapi
    kwargs = {"url": "https://cds.climate.copernicus.eu/api", "verify": not args.insecure}
    if os.getenv("CDSAPI_KEY"):
        kwargs["key"] = os.environ["CDSAPI_KEY"]
    client = cdsapi.Client(**kwargs)    # falls back to ~/.cdsapirc when CDSAPI_KEY is not set

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
    record_download("ERA5-Land monthly means", f"CDS {DATASET} {args.start}-{args.end}", ERA5,
                    notes=",".join(VARIABLES))
    print(f"   saved {ERA5}")


if __name__ == "__main__":
    main()

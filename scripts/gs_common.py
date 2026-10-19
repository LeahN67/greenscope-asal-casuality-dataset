"""
Shared paths, causal registry and download/provenance helpers for the GreenScope ASAL pipeline.

All scripts resolve paths from the project root, which is the current directory unless
the GREENSCOPE_PROJECT_ROOT environment variable is set. Run every script from the
repository root.
"""
import csv
import hashlib
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

# ------------------------------------------------------------------
# Paths
# ------------------------------------------------------------------
ROOT = Path(os.getenv("GREENSCOPE_PROJECT_ROOT", ".")).resolve()
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed" / "module0"

BOUNDARY_RAW = RAW / "boundaries" / "kenya_raw_adm1.geojson"
BOUNDARY = RAW / "boundaries" / "asal_boundary.geojson"
CHIRPS = RAW / "chirps" / "monthly" / "chirps-v2.0.monthly.nc"
ERA5_DIR = RAW / "era5_land"
ERA5 = ERA5_DIR / "era5_land_monthly.nc"
ERA5_LEGACY = ERA5_DIR / "data_stream-moda.nc"      # name used by earlier manual downloads
ERA5_REQUEST = ERA5_DIR / "era5_land_monthly.request.json"   # exact CDS request, written by fetch_era5.py
ENSO = RAW / "enso" / "nino34.txt"
IOD = RAW / "iod" / "dmi_noaa.txt"
MODIS_DIR = RAW / "modis_ndvi_monthly"               # AppEEARS GeoTIFFs land here
MODIS_NC = MODIS_DIR / "ndvi"                        # converted NDVI NetCDF files
MODIS_TASK = MODIS_DIR / "task_id.txt"               # AppEEARS task id, written by fetch_modis_ndvi.py
CUBE = PROCESSED / "module0_asal_datacube.nc"
FINAL_CUBE = PROCESSED / "greenscope_final_causal_cube.nc"
MANIFEST = RAW / "download_manifest.csv"
FIGURES = PROCESSED / "figures"

# Source locations, recorded in the cube metadata
CHIRPS_URL = "https://data.chc.ucsb.edu/products/CHIRPS-2.0/global_monthly/netcdf/chirps-v2.0.monthly.nc"
ENSO_URL = "https://psl.noaa.gov/data/correlation/nina34.data"
IOD_URL = "https://psl.noaa.gov/data/timeseries/month/data/dmi.had.long.data"

# ------------------------------------------------------------------
# Causal registry: one definition used by every script and written into the NetCDF attributes.
# It records a hypothesised driver -> mediator -> response ordering. It is a structural prior
# for causal discovery, not evidence that any relationship is causal.
# ------------------------------------------------------------------
CAUSAL_REGISTRY = {
    "enso_nino34": ("A", "global driver", "Nino 3.4 SST anomaly"),
    "iod_dmi": ("A", "global driver", "Indian Ocean Dipole Mode Index"),
    "precipitation": ("B", "local driver", "water input to the land surface"),
    "potential_evaporation": ("B", "local stressor", "atmospheric evaporative demand"),
    "soil_moisture": ("B", "mediator", "plant-available water in the top soil layer"),
    "ndvi": ("C", "response", "vegetation condition"),
}


# Variables that describe the data rather than the system; they carry no causal role
ANCILLARY = {
    "asal_mask": "1 where the grid-cell centre lies inside the ASAL county polygon, 0 elsewhere",
    "ndvi_good_fraction": ("monthly mean, across the available MODIS composites, of the share of pixels with a "
                           "valid NDVI value in the cell whose VI_Quality MODLAND bits (0-1) are 00 (good quality) "
                           "or 01 (produced, check other QA); a missing quality flag counts as not usable; lower "
                           "values indicate more cloud-affected pixels"),
}


def tag_causal_role(ds):
    """Write the registry into each variable's attributes."""
    for var, (layer, role, meaning) in CAUSAL_REGISTRY.items():
        if var in ds.data_vars:
            ds[var].attrs.update(causal_layer=layer, causal_role=role, causal_meaning=meaning)
    ds.attrs["causal_registry"] = "; ".join(
        f"{v}: layer {l}, {r}" for v, (l, r, _) in CAUSAL_REGISTRY.items() if v in ds.data_vars)
    return ds


# ------------------------------------------------------------------
# Provenance
# ------------------------------------------------------------------
def sha256_file(path, block=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(block), b""):
            h.update(chunk)
    return h.hexdigest()


def record_download(dataset, source, path, notes=""):
    """Append one row (time, dataset, source, file, size, SHA-256, notes) to the download manifest."""
    path = Path(path)
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    new = not MANIFEST.exists()
    with open(MANIFEST, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["utc_time", "dataset", "source", "file", "bytes", "sha256", "notes"])
        w.writerow([datetime.now(timezone.utc).isoformat(timespec="seconds"), dataset, source,
                    str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path),
                    path.stat().st_size, sha256_file(path), notes])


# ------------------------------------------------------------------
# Downloading
# ------------------------------------------------------------------
def download_with_resume(url, out_path, max_retries=5, base_delay=2, timeout=120, session=None):
    """
    Download `url` to `out_path`, resuming a partial `.part` file when the server supports it.
    Retries with exponential backoff (2, 4, 8, ... seconds). The final file only appears once
    the download is complete.
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    part = out_path.with_name(out_path.name + ".part")
    http = session or requests

    for attempt in range(max_retries):
        try:
            have = part.stat().st_size if part.exists() else 0
            headers = {"Range": f"bytes={have}-"} if have else {}
            with http.get(url, headers=headers, stream=True, timeout=timeout) as r:
                if r.status_code == 416:            # nothing left to fetch
                    part.replace(out_path)
                    return out_path
                if have and r.status_code == 200:   # server ignored Range: start again
                    have = 0
                r.raise_for_status()
                total = int(r.headers.get("content-length", 0)) + have
                with open(part, "ab" if have else "wb") as f:
                    done, last = have, 0.0
                    for chunk in r.iter_content(chunk_size=1 << 16):
                        f.write(chunk)
                        done += len(chunk)
                        if total and time.time() - last > 1:
                            print(f"\r   {done / 1e6:,.1f} / {total / 1e6:,.1f} MB", end="", flush=True)
                            last = time.time()
                if total and part.stat().st_size < total:
                    raise IOError(f"incomplete: {part.stat().st_size} of {total} bytes")
            print()
            part.replace(out_path)
            return out_path
        except (requests.RequestException, IOError) as e:
            if attempt == max_retries - 1:
                raise
            delay = base_delay * 2 ** attempt
            print(f"\n   attempt {attempt + 1} failed ({str(e)[:80]}); retrying in {delay}s")
            time.sleep(delay)

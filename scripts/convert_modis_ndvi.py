"""
Step 6. Convert the AppEEARS NDVI GeoTIFFs into one NetCDF per composite.

Only files whose name contains "_NDVI_doy" are used. AppEEARS puts the VI_Quality layer in the
same folder; converting those by mistake produces "NDVI" made of quality bit codes (values
around 2116 and 34896), so they are skipped and the first file is checked for a plausible range.

    python scripts/convert_modis_ndvi.py                 # convert (skips files already converted)
    python scripts/convert_modis_ndvi.py --dry-run       # list what would be converted
    python scripts/convert_modis_ndvi.py --src data/raw/modis_ndvi --dst data/raw/modis_ndvi/ndvi_fixed

Values stay as stored integers (NDVI x 10000); data_cube.py applies the 0.0001 scale factor.
Output: data/raw/modis_ndvi_monthly/ndvi/MODIS_NDVI_YYYYMMDD.nc
"""
import argparse
import re
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import rioxarray
import xarray as xr

from gs_common import MODIS_DIR, MODIS_NC

NDVI_PATTERN = re.compile(r"_NDVI_doy(\d{7})", re.IGNORECASE)
FILL = -9999.0


def read_tif(path):
    da = rioxarray.open_rasterio(path, masked=False).squeeze("band", drop=True)
    vals = da.values.astype("float32")
    nodata = da.rio.nodata
    if nodata is not None:
        vals[vals == nodata] = FILL
    lat, lon = da.y.values, da.x.values
    da.close()
    return vals, lat, lon


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", default=str(MODIS_DIR), help="folder with the AppEEARS GeoTIFFs")
    ap.add_argument("--dst", default=str(MODIS_NC), help="folder for the NetCDF files")
    ap.add_argument("--dry-run", action="store_true", help="list only, write nothing")
    args = ap.parse_args()
    src, dst = Path(args.src), Path(args.dst)

    print("STEP 6  Convert MODIS NDVI GeoTIFFs to NetCDF")
    tifs = sorted(src.rglob("*.tif"))
    ndvi = {}
    for p in tifs:
        m = NDVI_PATTERN.search(p.name)
        if m:
            d = datetime.strptime(m.group(1), "%Y%j")
            if d in ndvi:
                raise SystemExit(f"Two NDVI files for {d.date()}: {ndvi[d].name} and {p.name}")
            ndvi[d] = p
    print(f"   {len(tifs)} GeoTIFFs in {src}: {len(ndvi)} NDVI, {len(tifs) - len(ndvi)} other layers ignored")
    if not ndvi:
        raise SystemExit("No NDVI GeoTIFFs found (expected names containing '_NDVI_doy'). "
                         "Run fetch_modis_ndvi.py first or check --src.")
    print(f"   dates {min(ndvi).date()} to {max(ndvi).date()}")

    vals, _, _ = read_tif(ndvi[min(ndvi)])
    v = vals[vals != FILL]
    p1, p50, p99 = np.percentile(v, [1, 50, 99])
    print(f"   first file stored values: 1st/50th/99th percentile {p1:.0f} / {p50:.0f} / {p99:.0f}")
    if p99 > 10000 or p1 < -2000:
        raise SystemExit("Values are outside the NDVI range (-2000..10000); these are not NDVI files. Stopping.")

    if args.dry_run:
        print("   dry run: nothing written")
        return

    dst.mkdir(parents=True, exist_ok=True)
    written = 0
    for d, p in sorted(ndvi.items()):
        out = dst / f"MODIS_NDVI_{d:%Y%m%d}.nc"
        if out.exists():
            continue
        vals, lat, lon = read_tif(p)
        ds = xr.Dataset(
            {"NDVI": (("time", "latitude", "longitude"), vals[np.newaxis])},
            coords={"time": [pd.Timestamp(d)], "latitude": lat, "longitude": lon},
            attrs={"source_file": p.name, "note": "MODIS NDVI stored value (NDVI x 10000)"},
        )
        ds.to_netcdf(out, encoding={"NDVI": {"_FillValue": np.float32(FILL), "zlib": True, "complevel": 4}})
        written += 1
    print(f"   {written} files written, {len(ndvi) - written} already present, in {dst}")


if __name__ == "__main__":
    main()

"""
Step 6. Convert the AppEEARS MODIS GeoTIFFs into one NetCDF per composite date, holding NDVI and,
when present, its VI_Quality flags.

NDVI files are recognised by "_NDVI_doy" in the name and quality files by "_VI_Quality_doy". The two
must never be confused: converting quality codes (values around 2116 and 34896) as NDVI produces a
plausible-looking but meaningless vegetation index, so the first NDVI file is range-checked.

    python scripts/convert_modis_ndvi.py                 # convert (skips files already converted)
    python scripts/convert_modis_ndvi.py --dry-run       # list what would be converted
    python scripts/convert_modis_ndvi.py --src data/raw/modis_ndvi --dst data/raw/modis_ndvi/ndvi_fixed

NDVI stays as stored integers (NDVI x 10000); data_cube.py applies the 0.0001 scale factor.
VI_Quality stays as the 16-bit flag word. Fill values become -9999 (NDVI) and 65535 (quality).
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
QUAL_PATTERN = re.compile(r"_VI_Quality_doy(\d{7})", re.IGNORECASE)
NDVI_FILL = -9999.0
QUAL_FILL = 65535


def read_tif(path, fill, dtype):
    da = rioxarray.open_rasterio(path, masked=False).squeeze("band", drop=True)
    vals = da.values.astype(dtype)
    if da.rio.nodata is not None:
        vals[da.values == da.rio.nodata] = fill
    lat, lon = da.y.values, da.x.values
    da.close()
    return vals, lat, lon


def index_by_date(paths, pattern, kind):
    out = {}
    for p in paths:
        m = pattern.search(p.name)
        if not m:
            continue
        d = datetime.strptime(m.group(1), "%Y%j")
        if d in out:
            raise SystemExit(f"Two {kind} files for {d.date()}: {out[d].name} and {p.name}")
        out[d] = p
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", default=str(MODIS_DIR), help="folder with the AppEEARS GeoTIFFs")
    ap.add_argument("--dst", default=str(MODIS_NC), help="folder for the NetCDF files")
    ap.add_argument("--dry-run", action="store_true", help="list only, write nothing")
    args = ap.parse_args()
    src, dst = Path(args.src), Path(args.dst)

    print("STEP 6  Convert MODIS GeoTIFFs to NetCDF")
    tifs = sorted(src.rglob("*.tif"))
    ndvi = index_by_date(tifs, NDVI_PATTERN, "NDVI")
    qual = index_by_date(tifs, QUAL_PATTERN, "VI_Quality")
    print(f"   {len(tifs)} GeoTIFFs in {src}: {len(ndvi)} NDVI, {len(qual)} VI_Quality, "
          f"{len(tifs) - len(ndvi) - len(qual)} other layers ignored")
    if not ndvi:
        raise SystemExit("No NDVI GeoTIFFs found (expected names containing '_NDVI_doy'). "
                         "Run fetch_modis_ndvi.py first or check --src.")
    missing_q = sorted(set(ndvi) - set(qual))
    if missing_q:
        print(f"   {len(missing_q)} dates have no VI_Quality file; ndvi_good_fraction will be missing for them")
    print(f"   dates {min(ndvi).date()} to {max(ndvi).date()}")

    vals, _, _ = read_tif(ndvi[min(ndvi)], NDVI_FILL, "float32")
    v = vals[vals != NDVI_FILL]
    p1, p50, p99 = np.percentile(v, [1, 50, 99])
    print(f"   first NDVI file stored values: 1st/50th/99th percentile {p1:.0f} / {p50:.0f} / {p99:.0f}")
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
        vals, lat, lon = read_tif(p, NDVI_FILL, "float32")
        data = {"NDVI": (("time", "latitude", "longitude"), vals[np.newaxis])}
        enc = {"NDVI": {"_FillValue": np.float32(NDVI_FILL), "zlib": True, "complevel": 4}}
        sources = [p.name]
        if d in qual:
            q, qlat, qlon = read_tif(qual[d], QUAL_FILL, "uint16")
            if q.shape != vals.shape or not (np.allclose(qlat, lat) and np.allclose(qlon, lon)):
                raise SystemExit(f"NDVI and VI_Quality grids differ for {d.date()}")
            data["VI_Quality"] = (("time", "latitude", "longitude"), q[np.newaxis])
            enc["VI_Quality"] = {"_FillValue": np.uint16(QUAL_FILL), "zlib": True, "complevel": 4}
            sources.append(qual[d].name)
        ds = xr.Dataset(data, coords={"time": [pd.Timestamp(d)], "latitude": lat, "longitude": lon},
                        attrs={"source_files": ", ".join(sources),
                               "product": p.name.split("__")[0],
                               "note": "NDVI stored value (NDVI x 10000); VI_Quality 16-bit flag word"})
        ds.to_netcdf(out, encoding=enc)
        written += 1
    print(f"   {written} files written, {len(ndvi) - written} already present, in {dst}")


if __name__ == "__main__":
    main()

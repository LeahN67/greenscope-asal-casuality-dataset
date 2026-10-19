"""
Step 8. Add the global climate indices (Nino 3.4 anomaly, Dipole Mode Index) to the cube, matched
month by month. Each index is stored once per month (dimension: time). xarray broadcasts it against
the gridded variables automatically, so every grid cell sees the same regional value for that month.

    python scripts/causal_integration.py
    python scripts/causal_integration.py --allow-missing-index   # keep months without an index value as NaN

What it does:
  1. parses the NOAA PSL files by the year on each row (header and footer lines are skipped;
     values <= -90 such as -99.99 and -9999 become missing)
  2. converts the absolute Nino 3.4 SST to an anomaly against its 1991-2020 calendar-month mean
  3. matches each cube month exactly; stops if a month has no value unless --allow-missing-index
  4. writes the indices, their causal roles and input checksums into the final file

Output: data/processed/module0/greenscope_final_causal_cube.nc
"""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from gs_common import CUBE, ENSO, FINAL_CUBE, IOD, sha256_file, tag_causal_role

ENSO_ANOMALY_BASE = (1991, 2020)


def parse_noaa_index(file_path, var_name):
    """
    Parse a NOAA PSL monthly index file: rows of a 4-digit year followed by exactly 12 values.
    The time axis comes from each row's own year, and missing years raise an error, so a
    header line or a gap can never shift later months.
    """
    rows = {}
    for line in Path(file_path).read_text().splitlines():
        parts = line.split()
        if len(parts) != 13 or not (parts[0].isdigit() and len(parts[0]) == 4):
            continue
        try:
            vals = [float(x) for x in parts[1:]]
        except ValueError:
            continue
        year = int(parts[0])
        if year in rows:
            raise ValueError(f"Duplicate year {year} in {file_path}")
        rows[year] = vals
    if not rows:
        raise ValueError(f"No valid data rows found in {file_path}")
    years = sorted(rows)
    gaps = [y for y in range(years[0], years[-1] + 1) if y not in rows]
    if gaps:
        raise ValueError(f"Missing years in {file_path}: {gaps[:10]}")
    values = np.array([rows[y] for y in years], dtype=float).ravel()
    values[values <= -90] = np.nan
    time = pd.date_range(f"{years[0]}-01-01", periods=values.size, freq="MS")
    return xr.DataArray(values, coords=[("time", time)], name=var_name)


def monthly_anomaly(da, base=ENSO_ANOMALY_BASE):
    """Anomaly against the series' own calendar-month mean over the base period."""
    clim = da.sel(time=slice(f"{base[0]}-01-01", f"{base[1]}-12-31")).groupby("time.month").mean("time")
    if bool(clim.isnull().any()):
        raise ValueError(f"Base period {base} has calendar months with no data")
    anom = (da.groupby("time.month") - clim).drop_vars("month")
    anom.name = da.name
    return anom


def align_exact(da, cube_time, name, allow_missing=False):
    """Match a monthly index to the cube's months exactly (no nearest-month filling)."""
    months = pd.DatetimeIndex(cube_time.values).to_period("M").to_timestamp()
    aligned = da.reindex(time=months)
    missing = [str(t)[:7] for t in months[aligned.isnull().values]]
    print(f"   {name}: {len(months) - len(missing)} of {len(months)} cube months matched")
    if missing and not allow_missing:
        raise SystemExit(f"{name}: no value for {len(missing)} cube months, e.g. {missing[:6]}. "
                         "Download the index again, or rerun with --allow-missing-index to keep them as NaN.")
    aligned = aligned.assign_coords(time=cube_time.values)
    if missing:
        print(f"   {name}: left as NaN: {', '.join(missing)}")
        aligned.attrs["missing_months"] = ", ".join(missing)
    return aligned


def run_integration(cube=CUBE, enso=ENSO, iod=IOD, output=FINAL_CUBE, allow_missing=False):
    print("STEP 8  Add ENSO and IOD to the cube")
    for p, name in [(cube, "cube"), (enso, "Nino 3.4 file"), (iod, "DMI file")]:
        if not Path(p).exists():
            raise FileNotFoundError(f"{name} not found: {p}")

    ds = xr.open_dataset(cube).load()
    enso_abs = parse_noaa_index(enso, "enso_nino34")
    if float(enso_abs.mean()) < 15:
        raise SystemExit("The Nino 3.4 file already looks like an anomaly series; this script expects "
                         "absolute SST (nina34.data). Remove the anomaly step or use that file.")
    da_enso = monthly_anomaly(enso_abs)
    da_iod = parse_noaa_index(iod, "iod_dmi")

    out = ds.copy()
    out["enso_nino34"] = align_exact(da_enso, ds.time, "enso_nino34", allow_missing)
    out["iod_dmi"] = align_exact(da_iod, ds.time, "iod_dmi", allow_missing)
    out["enso_nino34"].attrs.update(
        units="degC", long_name="Nino 3.4 SST anomaly (ERSSTv5, NOAA CPC)",
        comment=f"absolute Nino 3.4 SST minus its {ENSO_ANOMALY_BASE[0]}-{ENSO_ANOMALY_BASE[1]} "
                "calendar-month mean; one regional value per month")
    out["iod_dmi"].attrs.update(
        units="degC", long_name="Dipole Mode Index (HadISST, NOAA PSL)",
        comment="SST anomaly 10S-10N 50-70E minus 10S-0 90-110E; one regional value per month")
    tag_causal_role(out)
    out.attrs["source_enso_file"] = f"{Path(enso).name} sha256={sha256_file(enso)}"
    out.attrs["source_iod_file"] = f"{Path(iod).name} sha256={sha256_file(iod)}"
    out.attrs["source_data_cube"] = f"{Path(cube).name} sha256={sha256_file(cube)}"
    out.attrs["history"] = (out.attrs.get("history", "") + "; causal_integration.py: Nino 3.4 converted to "
                            "anomaly, ENSO and DMI matched to cube months exactly").lstrip("; ")

    encoding = {v: {"zlib": True, "complevel": 4, "_FillValue": -9999.0} for v in out.data_vars}
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    out.to_netcdf(output, encoding=encoding)
    print(f"   saved {output}  ({Path(output).stat().st_size / 1e6:.1f} MB)")
    print(f"   variables: {list(out.data_vars)}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-cube", default=str(CUBE))
    ap.add_argument("--enso", default=str(ENSO))
    ap.add_argument("--iod", default=str(IOD))
    ap.add_argument("--output", default=str(FINAL_CUBE))
    ap.add_argument("--allow-missing-index", action="store_true",
                    help="keep cube months with no index value as NaN instead of stopping")
    args = ap.parse_args()
    run_integration(args.data_cube, args.enso, args.iod, args.output, args.allow_missing_index)


if __name__ == "__main__":
    main()

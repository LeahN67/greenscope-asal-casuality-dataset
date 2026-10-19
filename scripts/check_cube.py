"""
Step 9. Check the final cube and write a short report.

    python scripts/check_cube.py
    python scripts/check_cube.py --cube path/to/file.nc

Each variable is checked against a plausible physical range. FAIL means the cube should not be
used for analysis until the cause is found; WARN means look before relying on it.
Exit code is 1 if any check fails.
Output: data/processed/module0/cube_report.txt
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from gs_common import FINAL_CUBE

# variable: (hard minimum, hard maximum, description of a plausible median)
RANGES = {
    "precipitation": (0, 2000, (1, 200)),
    "potential_evaporation": (0, 25, (2, 12)),
    "soil_moisture": (-1e-6, 0.8, (0.02, 0.45)),
    "ndvi": (-0.2, 1.0, (0.1, 0.7)),
    "enso_nino34": (-5, 5, (-1.5, 1.5)),
    "iod_dmi": (-3, 3, (-1.5, 1.5)),
}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cube", default=str(FINAL_CUBE))
    args = ap.parse_args()
    cube = Path(args.cube)

    lines, failed = [], False

    def say(status, msg):
        nonlocal failed
        failed |= status == "FAIL"
        lines.append(f"{status:5s} {msg}")
        print(f"   {status:5s} {msg}")

    print("STEP 9  Check the cube")
    ds = xr.open_dataset(cube)
    t = pd.DatetimeIndex(ds.time.values)
    expected = pd.date_range(t[0], t[-1], freq="MS")
    say("PASS" if len(t) == len(expected) else "FAIL",
        f"time: {t[0]:%Y-%m} to {t[-1]:%Y-%m}, {len(t)} months, gaps: {len(expected) - len(t)}")
    say("PASS" if len(t) >= 120 else "WARN",
        f"record length {len(t)} months (under 120 months gives little power for lagged causal analysis)")

    for var, (lo, hi, (mlo, mhi)) in RANGES.items():
        if var not in ds.data_vars:
            say("FAIL", f"{var}: missing from the cube")
            continue
        v = ds[var].values.astype("float64")
        if "asal_mask" in ds and v.ndim == 3:
            v = v[:, ds["asal_mask"].values == 1]          # judge gridded variables inside the ASALs only
        nan = float(np.isnan(v).mean())
        f = v[np.isfinite(v)]
        if f.size == 0:
            say("FAIL", f"{var}: no valid values")
            continue
        q = np.percentile(f, [0, 50, 100])
        where = " inside ASAL" if "asal_mask" in ds and ds[var].ndim == 3 else ""
        desc = (f"{var}: min {q[0]:.3f} median {q[1]:.3f} max {q[2]:.3f} "
                f"[{ds[var].attrs.get('units', '?')}], missing{where} {nan:.1%}, role: {ds[var].attrs.get('causal_role', '?')}")
        if q[0] < lo or q[2] > hi:
            say("FAIL", desc + f"  (outside {lo}..{hi})")
        elif not mlo <= q[1] <= mhi or (var == "ndvi" and (np.abs(f - q[1]) < 0.005).mean() > 0.25):
            say("WARN", desc + "  (median or distribution unusual)")
        else:
            say("PASS", desc)
        if ds[var].attrs.get("missing_months"):
            say("WARN", f"{var}: months without a value: {ds[var].attrs['missing_months']}")

    if "asal_mask" in ds:
        m = ds["asal_mask"].values
        say("PASS" if m.sum() > 0 else "FAIL",
            f"asal_mask: {int(m.sum()):,} of {m.size:,} cells inside the ASAL polygon "
            f"(about {ds.attrs.get('asal_area_km2', '?')} km2); extent: {ds.attrs.get('spatial_extent', '?')}")
        if "masked" in ds.attrs.get("spatial_extent", "") or "inside" in ds.attrs.get("spatial_extent", ""):
            outside = ds["precipitation"].values[:, m == 0]
            say("PASS" if np.isnan(outside).all() else "FAIL", "cells outside the ASAL polygon are missing in every variable")
    else:
        say("WARN", "asal_mask: not present (cube built by an older version)")

    if "ndvi_good_fraction" in ds:
        g = ds["ndvi_good_fraction"].values
        g = g[np.isfinite(g)]
        if g.size and (g.min() < 0 or g.max() > 1):
            say("FAIL", f"ndvi_good_fraction outside 0..1 ({g.min():.3f} to {g.max():.3f})")
        elif g.size:
            say("PASS" if np.median(g) >= 0.5 else "WARN",
                f"ndvi_good_fraction: median {np.median(g):.2f}; share of cell-months below 0.5: {(g < 0.5).mean():.1%}")
    else:
        say("WARN", "ndvi_good_fraction: not present (no VI_Quality in the NDVI inputs)")

    for k in ("qc_ndvi_pixels_out_of_range", "qc_precipitation_negative_cells",
              "qc_pev_positive_cells_before_sign_reversal", "ndvi_regridding"):
        if k in ds.attrs:
            lines.append(f"INFO  {k}: {ds.attrs[k]}")

    report = cube.with_name("cube_report.txt")
    report.write_text("\n".join(lines) + "\n")
    print(f"\n   report saved to {report}")
    ds.close()
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()

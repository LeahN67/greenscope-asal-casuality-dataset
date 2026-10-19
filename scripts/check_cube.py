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
        nan = float(np.isnan(v).mean())
        f = v[np.isfinite(v)]
        if f.size == 0:
            say("FAIL", f"{var}: no valid values")
            continue
        q = np.percentile(f, [0, 50, 100])
        desc = (f"{var}: min {q[0]:.3f} median {q[1]:.3f} max {q[2]:.3f} "
                f"[{ds[var].attrs.get('units', '?')}], missing {nan:.1%}, role: {ds[var].attrs.get('causal_role', '?')}")
        if q[0] < lo or q[2] > hi:
            say("FAIL", desc + f"  (outside {lo}..{hi})")
        elif not mlo <= q[1] <= mhi or (var == "ndvi" and (np.abs(f - q[1]) < 0.005).mean() > 0.25):
            say("WARN", desc + "  (median or distribution unusual)")
        else:
            say("PASS", desc)
        if ds[var].attrs.get("missing_months"):
            say("WARN", f"{var}: months without a value: {ds[var].attrs['missing_months']}")

    report = cube.with_name("cube_report.txt")
    report.write_text("\n".join(lines) + "\n")
    print(f"\n   report saved to {report}")
    ds.close()
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()

"""
Run the whole GreenScope ASAL pipeline, step by step, from the repository root.

    python run_pipeline.py                         # all steps; downloads are skipped if files exist
    python run_pipeline.py --skip-download         # only steps 6 to 9 (data already in data/raw)
    python run_pipeline.py --from data_cube        # start at a given step
    python run_pipeline.py --allow-missing-index   # passed to causal_integration.py

Steps:
  1 boundaries   create_asal_boundaries.py   ASAL county polygon
  2 chirps       fetch_chirps.py             CHIRPS v2.0 monthly precipitation
  3 era5         fetch_era5.py               ERA5-Land potential evaporation, soil moisture (needs CDS key)
  4 enso, iod    fetch_enso.py, fetch_iod.py Nino 3.4 and Dipole Mode Index
  5 modis        fetch_modis_ndvi.py         MODIS NDVI via AppEEARS (needs Earthdata login; can take hours)
  6 convert      convert_modis_ndvi.py       NDVI GeoTIFFs to NetCDF
  7 data_cube    data_cube.py                gridded cube on the CHIRPS grid
  8 integrate    causal_integration.py       add ENSO and IOD
  9 check        check_cube.py               plausibility report

The pipeline stops at the first step that fails.
"""
import argparse
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent / "scripts"
STEPS = [
    ("boundaries", "create_asal_boundaries.py", True),
    ("chirps", "fetch_chirps.py", True),
    ("era5", "fetch_era5.py", True),
    ("enso", "fetch_enso.py", True),
    ("iod", "fetch_iod.py", True),
    ("modis", "fetch_modis_ndvi.py", True),
    ("convert", "convert_modis_ndvi.py", False),
    ("data_cube", "data_cube.py", False),
    ("integrate", "causal_integration.py", False),
    ("check", "check_cube.py", False),
]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--skip-download", action="store_true", help="skip steps 1 to 5")
    ap.add_argument("--from", dest="start", choices=[s[0] for s in STEPS], help="first step to run")
    ap.add_argument("--allow-missing-index", action="store_true")
    args = ap.parse_args()

    names = [s[0] for s in STEPS]
    first = names.index(args.start) if args.start else 0
    for name, script, is_download in STEPS[first:]:
        if is_download and args.skip_download:
            continue
        cmd = [sys.executable, str(SCRIPTS / script)]
        if name == "integrate" and args.allow_missing_index:
            cmd.append("--allow-missing-index")
        print(f"\n{'=' * 70}\n{name}: {' '.join(cmd[1:])}\n{'=' * 70}")
        if subprocess.run(cmd).returncode != 0:
            sys.exit(f"\nStopped: step '{name}' failed. Fix the problem above, then rerun with --from {name}")
    print("\nPipeline complete. Final cube: data/processed/module0/greenscope_final_causal_cube.nc")


if __name__ == "__main__":
    main()

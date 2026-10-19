"""
Step 2. Download CHIRPS v2.0 global monthly precipitation (single NetCDF, several GB).

    python scripts/fetch_chirps.py            # resumes a partial download, skips if complete
    python scripts/fetch_chirps.py --force    # download again (for example to get recent months)

Output: data/raw/chirps/monthly/chirps-v2.0.monthly.nc
"""
import argparse

from gs_common import CHIRPS, download_with_resume, record_download

URL = "https://data.chc.ucsb.edu/products/CHIRPS-2.0/global_monthly/netcdf/chirps-v2.0.monthly.nc"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--force", action="store_true", help="download again even if the file exists")
    args = ap.parse_args()

    print("STEP 2  CHIRPS v2.0 monthly precipitation")
    if CHIRPS.exists() and not args.force:
        print(f"   using existing {CHIRPS}")
        return
    if args.force and CHIRPS.exists():
        CHIRPS.unlink()
    print(f"   {URL}")
    download_with_resume(URL, CHIRPS)
    record_download("CHIRPS v2.0 monthly", URL, CHIRPS)
    print(f"   saved {CHIRPS}")


if __name__ == "__main__":
    main()

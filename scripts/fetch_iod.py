"""
Step 4b. Download the Indian Ocean Dipole Mode Index (HadISST, NOAA PSL).

The most recent months are often still missing (coded -9999) because the source updates with a
lag. causal_integration.py stops if cube months have no DMI value, unless you pass
--allow-missing-index.

    python scripts/fetch_iod.py             # always downloads the latest version (small file)

Output: data/raw/iod/dmi_noaa.txt
"""
import argparse

from gs_common import IOD, download_with_resume, record_download

URL = "https://psl.noaa.gov/data/timeseries/month/data/dmi.had.long.data"


def main():
    argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
    print("STEP 4b  IOD Dipole Mode Index (HadISST)")
    print(f"   {URL}")
    download_with_resume(URL, IOD)
    record_download("Dipole Mode Index (HadISST)", URL, IOD)
    print(f"   saved {IOD}")


if __name__ == "__main__":
    main()

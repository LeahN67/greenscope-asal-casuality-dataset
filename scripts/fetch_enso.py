"""
Step 4a. Download the Nino 3.4 index (ERSSTv5, NOAA CPC via NOAA PSL).

The file holds ABSOLUTE monthly SST (about 24 to 29 degC). causal_integration.py converts it
to an anomaly against a 1991-2020 climatology.

    python scripts/fetch_enso.py            # always downloads the latest version (small file)

Output: data/raw/enso/nino34.txt
"""
import argparse

from gs_common import ENSO, download_with_resume, record_download

URL = "https://psl.noaa.gov/data/correlation/nina34.data"


def main():
    argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
    print("STEP 4a  ENSO Nino 3.4 index (ERSSTv5)")
    print(f"   {URL}")
    download_with_resume(URL, ENSO)
    record_download("Nino 3.4 SST (ERSSTv5)", URL, ENSO, notes="absolute SST, converted to anomaly later")
    print(f"   saved {ENSO}")


if __name__ == "__main__":
    main()

"""
Step 1. Build the study-area boundary: the 23 ASAL counties of Kenya, dissolved into one polygon.

    python scripts/create_asal_boundaries.py            # skips steps whose output exists
    python scripts/create_asal_boundaries.py --force    # re-download and rebuild

Output: data/raw/boundaries/asal_boundary.geojson
"""
import proj_guard  # noqa: F401  (must come before any geospatial import)

import argparse
import json
from difflib import get_close_matches

import geopandas as gpd
import requests

from gs_common import BOUNDARY, BOUNDARY_RAW, download_with_resume, record_download

ASAL_COUNTIES = [
    "Turkana", "Marsabit", "Mandera", "Wajir", "Garissa", "Tana River",
    "Isiolo", "Samburu", "Baringo", "West Pokot", "Laikipia", "Narok",
    "Kajiado", "Makueni", "Kitui", "Tharaka-Nithi", "Meru", "Embu",
    "Nyeri", "Taita Taveta", "Kwale", "Kilifi", "Lamu",
]
GEOBOUNDARIES_API = "https://www.geoboundaries.org/api/current/gbOpen/KEN/ADM1/"
GADM_URL = "https://geodata.ucdavis.edu/gadm/gadm4.1/json/gadm41_KEN_1.json"
NAME_COLUMNS = ["shapeName", "NAME_1", "ADM1_EN", "name", "NAME"]


def download_raw():
    """geoBoundaries first, GADM as fallback."""
    try:
        meta = requests.get(GEOBOUNDARIES_API, timeout=30).json()
        url, source = meta["gjDownloadURL"], "geoBoundaries gbOpen KEN ADM1"
    except Exception as e:
        print(f"   geoBoundaries metadata failed ({e}); using GADM 4.1")
        url, source = GADM_URL, "GADM 4.1 KEN level 1"
    print(f"   downloading {source}")
    download_with_resume(url, BOUNDARY_RAW)
    json.loads(BOUNDARY_RAW.read_text(encoding="utf-8"))   # fails loudly if not valid GeoJSON
    record_download("Kenya ADM1 boundaries", url, BOUNDARY_RAW, notes=source)


def build_asal():
    gdf = gpd.read_file(BOUNDARY_RAW)
    name_col = next((c for c in NAME_COLUMNS if c in gdf.columns), None)
    if name_col is None:
        raise SystemExit(f"No county name column found; columns are {list(gdf.columns)}")

    def norm(s):
        return s.replace("-", " ").replace("_", " ").title().strip()

    gdf["match_name"] = gdf[name_col].astype(str).map(norm)
    wanted = [norm(c) for c in ASAL_COUNTIES]
    available = gdf["match_name"].tolist()
    matched = []
    for w in wanted:
        hit = w if w in available else (get_close_matches(w, available, n=1, cutoff=0.8) or [None])[0]
        if hit is None:
            raise SystemExit(f"County not found in boundary file: {w}")
        if hit != w:
            print(f"   matched '{w}' to '{hit}'")
        matched.append(hit)

    asal = gdf[gdf["match_name"].isin(matched)]
    print(f"   {len(asal)} of {len(ASAL_COUNTIES)} counties matched")
    dissolved = asal.dissolve().to_crs("EPSG:4326")[["geometry"]]
    dissolved.to_file(BOUNDARY, driver="GeoJSON")
    area = asal.to_crs("EPSG:32737").area.sum() / 1e6
    print(f"   saved {BOUNDARY}  (area {area:,.0f} km2)")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--force", action="store_true", help="re-download and rebuild")
    args = ap.parse_args()

    print("STEP 1  ASAL boundary")
    if args.force or not BOUNDARY_RAW.exists():
        download_raw()
    else:
        print(f"   using existing {BOUNDARY_RAW}")
    if args.force or not BOUNDARY.exists():
        build_asal()
    else:
        print(f"   using existing {BOUNDARY}")


if __name__ == "__main__":
    main()

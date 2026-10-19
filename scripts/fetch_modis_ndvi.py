"""
Step 5. Download MODIS NDVI for the ASAL polygon through NASA AppEEARS (GeoTIFF, geographic).

Default: MOD13A3 v061, monthly 1 km NDVI, February 2000 to December 2025. Monthly data match the
cube's time step, and the 1 km product is far smaller than 250 m MOD13Q1. AppEEARS also returns
the VI_Quality layer; convert_modis_ndvi.py uses only the NDVI files.

Credentials: NASA Earthdata login. Set EARTHDATA_USERNAME and EARTHDATA_PASSWORD, or you are prompted.

    python scripts/fetch_modis_ndvi.py                    # submit, wait, download
    python scripts/fetch_modis_ndvi.py --no-wait          # submit only; the task id is saved
    python scripts/fetch_modis_ndvi.py                    # rerun: continues the saved task, skips files already downloaded
    python scripts/fetch_modis_ndvi.py --resume TASK_ID   # continue a specific task
    python scripts/fetch_modis_ndvi.py --new              # ignore the saved task and submit a new one
    python scripts/fetch_modis_ndvi.py --product MOD13Q1.061 --layer _250m_16_days_NDVI --start 01-01-2020

Output: data/raw/modis_ndvi_monthly/*.tif   (task id in data/raw/modis_ndvi_monthly/task_id.txt)
"""
import argparse
import getpass
import json
import os
import time

import geopandas as gpd
import requests

from gs_common import BOUNDARY, MODIS_DIR, record_download

API = "https://appeears.earthdatacloud.nasa.gov/api"
TASK_FILE = MODIS_DIR / "task_id.txt"


def login():
    user = os.getenv("EARTHDATA_USERNAME") or input("NASA Earthdata username: ")
    pwd = os.getenv("EARTHDATA_PASSWORD") or getpass.getpass("NASA Earthdata password: ")
    r = requests.post(f"{API}/login", auth=(user, pwd), timeout=60)
    if r.status_code != 200:
        raise SystemExit(f"Earthdata login failed ({r.status_code}): {r.text[:200]}")
    return {"Authorization": f"Bearer {r.json()['token']}"}


def check_layer(product, layer):
    """Stop early with a useful message if the product or layer name is wrong."""
    try:
        r = requests.get(f"{API}/product/{product}", timeout=60)
    except requests.RequestException as e:
        print(f"   could not verify layer name ({e}); continuing")
        return
    if r.status_code != 200:
        raise SystemExit(f"Product {product} not found in AppEEARS ({r.status_code})")
    layers = r.json()
    if layer not in layers:
        ndvi = [k for k in layers if "ndvi" in k.lower()]
        raise SystemExit(f"Layer {layer} not in {product}. NDVI layers available: {ndvi}")


def submit(headers, product, layer, start, end):
    geo = json.loads(gpd.read_file(BOUNDARY).to_crs("EPSG:4326").to_json())
    task = {
        "task_type": "area",
        "task_name": f"GreenScope_ASAL_{product}_{start}_{end}".replace("-", ""),
        "params": {
            "dates": [{"startDate": start, "endDate": end}],
            "layers": [{"product": product, "layer": layer}],
            "output": {"format": {"type": "geotiff"}, "projection": "geographic"},
            "geo": geo,
        },
    }
    r = requests.post(f"{API}/task", json=task, headers=headers, timeout=120)
    if r.status_code not in (200, 202):
        raise SystemExit(f"Task submission failed ({r.status_code}): {r.text[:300]}")
    task_id = r.json()["task_id"]
    MODIS_DIR.mkdir(parents=True, exist_ok=True)
    TASK_FILE.write_text(task_id)
    print(f"   task submitted: {task_id}  (saved to {TASK_FILE})")
    return task_id


def wait(headers, task_id, interval=120):
    print("   waiting for AppEEARS to process the task (often hours; Ctrl+C is safe, then use --resume)")
    start = time.time()
    while True:
        try:
            status = requests.get(f"{API}/task/{task_id}", headers=headers, timeout=60).json().get("status")
        except requests.RequestException:
            status = "unreachable"
        mins = int((time.time() - start) / 60)
        print(f"\r   status: {status:12s} elapsed: {mins} min", end="", flush=True)
        if status == "done":
            print()
            return True
        if status == "error":
            print()
            raise SystemExit("AppEEARS reported an error for this task; check it on the AppEEARS website")
        time.sleep(interval)


def download(headers, task_id):
    r = requests.get(f"{API}/bundle/{task_id}", headers=headers, timeout=120)
    if r.status_code != 200:
        raise SystemExit(f"Bundle not available yet ({r.status_code}); try --resume later")
    files = [f for f in r.json().get("files", []) if f["file_name"].endswith(".tif")]
    print(f"   {len(files)} GeoTIFFs in bundle")
    failed = 0
    for i, f in enumerate(files, 1):
        out = MODIS_DIR / os.path.basename(f["file_name"])
        if out.exists() and out.stat().st_size > 0:
            continue
        for attempt in range(5):
            try:
                with requests.get(f"{API}/bundle/{task_id}/{f['file_id']}", headers=headers,
                                  stream=True, timeout=(30, 300)) as resp:
                    resp.raise_for_status()
                    tmp = out.with_name(out.name + ".part")
                    with open(tmp, "wb") as fh:
                        for chunk in resp.iter_content(1 << 16):
                            fh.write(chunk)
                    tmp.replace(out)
                record_download("MODIS NDVI (AppEEARS)", f"{API}/bundle/{task_id}", out)
                print(f"   [{i}/{len(files)}] {out.name}")
                break
            except requests.RequestException as e:
                if attempt == 4:
                    print(f"   [{i}/{len(files)}] FAILED {out.name}: {str(e)[:80]}")
                    failed += 1
                else:
                    time.sleep(2 * 2 ** attempt)
    if failed:
        raise SystemExit(f"{failed} files failed; rerun with --resume to fetch them")
    print(f"   all files in {MODIS_DIR}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--product", default="MOD13A3.061")
    ap.add_argument("--layer", default="_1_km_monthly_NDVI")
    ap.add_argument("--start", default="02-01-2000", help="MM-DD-YYYY")
    ap.add_argument("--end", default="12-31-2025", help="MM-DD-YYYY")
    ap.add_argument("--no-wait", action="store_true", help="submit the task and exit")
    ap.add_argument("--resume", metavar="TASK_ID", help="continue this AppEEARS task")
    ap.add_argument("--new", action="store_true", help="submit a new task even if one is saved")
    args = ap.parse_args()

    print("STEP 5  MODIS NDVI via AppEEARS")
    if not BOUNDARY.exists():
        raise SystemExit(f"Boundary not found: {BOUNDARY}. Run create_asal_boundaries.py first.")
    headers = login()
    task_id = args.resume or (TASK_FILE.read_text().strip() if TASK_FILE.exists() and not args.new else None)
    if task_id:
        print(f"   continuing task {task_id}")
    else:
        check_layer(args.product, args.layer)
        task_id = submit(headers, args.product, args.layer, args.start, args.end)
        if args.no_wait:
            print("   rerun later with --resume")
            return
    wait(headers, task_id)
    download(headers, task_id)


if __name__ == "__main__":
    main()

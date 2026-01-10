"""
Download MODIS MOD13Q1 NDVI data using NASA AppEEARS API
This downloads data as GeoTIFF (easier to process than HDF)

Features:
- Resume interrupted downloads
- Retry failed requests
- Progress tracking
- Error handling
"""

import requests
import json
import time
from pathlib import Path
import getpass
import sys
from typing import Optional, Dict, Any

class AppEEARSDownloader:
    """Download MODIS data via AppEEARS API with robust error handling."""
    
    def __init__(self):
        self.api_url = "https://appeears.earthdatacloud.nasa.gov/api"
        self.token = None
        self.max_retries = 3
        self.retry_delay = 5
        
    def login(self, username: Optional[str] = None, password: Optional[str] = None) -> bool:
        """Login to AppEEARS and get authentication token."""
        
        print("🔐 NASA Earthdata Login")
        print("=" * 70)
        
        if username is None:
            username = input("Enter your NASA Earthdata username: ")
        if password is None:
            password = getpass.getpass("Enter your NASA Earthdata password: ")
        
        print("\n🔄 Authenticating...")
        
        for attempt in range(self.max_retries):
            try:
                response = requests.post(
                    f"{self.api_url}/login",
                    auth=(username, password),
                    timeout=30
                )
                
                if response.status_code == 200:
                    self.token = response.json()["token"]
                    print("✅ Authentication successful!")
                    return True
                elif response.status_code == 401:
                    print("❌ Authentication failed: Invalid username or password")
                    return False
                else:
                    print(f"❌ Authentication failed: {response.status_code}")
                    if attempt < self.max_retries - 1:
                        print(f"   Retrying in {self.retry_delay} seconds...")
                        time.sleep(self.retry_delay)
                    
            except requests.exceptions.RequestException as e:
                print(f"❌ Connection error: {e}")
                if attempt < self.max_retries - 1:
                    print(f"   Retrying in {self.retry_delay} seconds...")
                    time.sleep(self.retry_delay)
                else:
                    print("   Max retries reached. Please check your internet connection.")
                    return False
        
        return False
    
    def create_area_request(self, aoi_file: Path, start_date: str, end_date: str, output_name: str) -> Optional[str]:
        """Create an area-based data request."""
        
        print(f"\n📝 Creating data request...")
        print(f"   Study area: {aoi_file}")
        print(f"   Date range: {start_date} to {end_date}")
        
        try:
            # Read the GeoJSON boundary
            import geopandas as gpd
            asal_gdf = gpd.read_file(aoi_file)
            
            # Convert to GeoJSON format for API
            geojson = json.loads(asal_gdf.to_json())
            
        except Exception as e:
            print(f"❌ Failed to read boundary file: {e}")
            return None
        
        # Build the request
        task = {
            "task_type": "area",
            "task_name": output_name,
            "params": {
                "dates": [
                    {
                        "startDate": start_date,
                        "endDate": end_date
                    }
                ],
                "layers": [
                    {
                        "product": "MOD13Q1.061",
                        "layer": "_250m_16_days_NDVI"
                    }
                ],
                "output": {
                    "format": {
                        "type": "geotiff"
                    },
                    "projection": "geographic"
                },
                "geo": geojson
            }
        }
        
        # Submit the request with retries
        for attempt in range(self.max_retries):
            try:
                response = requests.post(
                    f"{self.api_url}/task",
                    json=task,
                    headers={"Authorization": f"Bearer {self.token}"},
                    timeout=60
                )
                
                # 200 OK or 202 Accepted means success
                if response.status_code in [200, 202]:
                    result = response.json()
                    task_id = result.get("task_id")
                    status = result.get("status", "submitted")
                    
                    print(f"✅ Request submitted successfully!")
                    print(f"   Task ID: {task_id}")
                    print(f"   Status: {status}")
                    return task_id
                else:
                    print(f"❌ Request failed: {response.status_code}")
                    print(f"   Response: {response.text}")
                    if attempt < self.max_retries - 1:
                        print(f"   Retrying in {self.retry_delay} seconds...")
                        time.sleep(self.retry_delay)
                        
            except requests.exceptions.RequestException as e:
                print(f"❌ Connection error: {e}")
                if attempt < self.max_retries - 1:
                    print(f"   Retrying in {self.retry_delay} seconds...")
                    time.sleep(self.retry_delay)
        
        return None
    
    def check_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Check the status of a data request with retries."""
        
        for attempt in range(self.max_retries):
            try:
                response = requests.get(
                    f"{self.api_url}/task/{task_id}",
                    headers={"Authorization": f"Bearer {self.token}"},
                    timeout=30
                )
                
                if response.status_code == 200:
                    return response.json()
                elif response.status_code == 404:
                    print(f"❌ Task not found: {task_id}")
                    return None
                else:
                    if attempt < self.max_retries - 1:
                        time.sleep(self.retry_delay)
                        
            except requests.exceptions.RequestException as e:
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay)
                else:
                    print(f"❌ Failed to check status: {e}")
        
        return None
    
    def wait_for_completion(self, task_id: str, check_interval: int = 60) -> bool:
        """Wait for the data request to complete."""
        
        print(f"\n⏳ Waiting for data processing...")
        print(f"   This typically takes 1-3 hours for 5 years of data")
        print(f"   You can close this and check back later (Ctrl+C to exit)")
        
        start_time = time.time()
        consecutive_failures = 0
        max_consecutive_failures = 5
        
        try:
            while True:
                status = self.check_status(task_id)
                
                if status is None:
                    consecutive_failures += 1
                    if consecutive_failures >= max_consecutive_failures:
                        print(f"\n❌ Failed to check status {max_consecutive_failures} times in a row")
                        return False
                    time.sleep(check_interval)
                    continue
                
                consecutive_failures = 0
                state = status.get("status", "unknown")
                elapsed = int(time.time() - start_time)
                
                if state == "done":
                    print(f"\n✅ Processing complete! (took {elapsed//60} minutes)")
                    return True
                elif state == "error":
                    print(f"\n❌ Processing failed!")
                    print(f"   Error: {status.get('message', 'No error message')}")
                    return False
                else:
                    print(f"   Status: {state} | Elapsed: {elapsed//60} min | Press Ctrl+C to exit", end="\r")
                    time.sleep(check_interval)
                    
        except KeyboardInterrupt:
            print(f"\n\n⏸️  Interrupted by user")
            print(f"   Your task is still processing on NASA's servers")
            print(f"   Run the script again later to check status and download")
            return False
    
    def download_files(self, task_id: str, output_dir: Path) -> bool:
        """Download the processed files with resume capability."""
        
        print(f"\n📥 Downloading files...")
        
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Get the download bundle with retries
        bundle_response = None
        for attempt in range(self.max_retries):
            try:
                bundle_response = requests.get(
                    f"{self.api_url}/bundle/{task_id}",
                    headers={"Authorization": f"Bearer {self.token}"},
                    timeout=30
                )
                
                if bundle_response.status_code == 200:
                    break
                elif bundle_response.status_code == 404:
                    print(f"❌ Data not found. Task may not be complete yet.")
                    return False
                else:
                    if attempt < self.max_retries - 1:
                        time.sleep(self.retry_delay)
                        
            except requests.exceptions.RequestException as e:
                if attempt < self.max_retries - 1:
                    print(f"   Connection error, retrying...")
                    time.sleep(self.retry_delay)
                else:
                    print(f"❌ Failed to get download links: {e}")
                    return False
        
        if bundle_response is None or bundle_response.status_code != 200:
            print(f"❌ Failed to get download bundle")
            return False
        
        files = bundle_response.json().get("files", [])
        
        if not files:
            print("   No files found. Data may still be processing.")
            return False
        
        print(f"   Found {len(files)} files")
        
        # Download each file
        downloaded = 0
        skipped = 0
        failed = 0
        
        for i, file_info in enumerate(files, 1):
            file_id = file_info["file_id"]
            file_name = file_info["file_name"]
            
            # Skip non-GeoTIFF files
            if not file_name.endswith('.tif'):
                continue
            
            output_path = output_dir / file_name
            
            # Print immediately so user knows we're processing this file
            print(f"   [{i}/{len(files)}] {file_name}...", end=" ", flush=True)
            
            # Check if file already exists (resume capability)
            if output_path.exists():
                file_size = output_path.stat().st_size
                if file_size > 0:  # File exists and is not empty
                    print(f"⊙ (already exists, {file_size:,} bytes)")
                    skipped += 1
                    continue
                else:
                    # Remove empty file and continue to download
                    print("(empty, re-downloading...)", end=" ", flush=True)
                    output_path.unlink()
            
            # Download with retries
            download_success = False
            for attempt in range(self.max_retries):
                try:
                    # Request with connection and read timeouts
                    file_response = requests.get(
                        f"{self.api_url}/bundle/{task_id}/{file_id}",
                        headers={"Authorization": f"Bearer {self.token}"},
                        stream=True,
                        timeout=(30, 300)  # (connection timeout, read timeout)
                    )
                    
                    if file_response.status_code == 200:
                        # Create parent directories if needed
                        output_path.parent.mkdir(parents=True, exist_ok=True)
                        
                        # Download with progress and chunk timeout
                        bytes_downloaded = 0
                        chunk_start_time = time.time()
                        max_chunk_time = 60  # 60 seconds per chunk max
                        last_progress_update = time.time()
                        progress_interval = 2  # Update every 2 seconds
                        
                        with open(output_path, 'wb') as f:
                            for chunk in file_response.iter_content(chunk_size=8192):
                                if chunk:
                                    f.write(chunk)
                                    bytes_downloaded += len(chunk)
                                    
                                    # Show progress indicator
                                    current_time = time.time()
                                    if current_time - last_progress_update > progress_interval:
                                        mb_downloaded = bytes_downloaded / (1024 * 1024)
                                        print(f"[{mb_downloaded:.1f}MB]", end="", flush=True)
                                        last_progress_update = current_time
                                    
                                    # Check if chunk took too long
                                    if time.time() - chunk_start_time > max_chunk_time:
                                        raise requests.exceptions.Timeout("Chunk download timeout")
                                    
                                    chunk_start_time = time.time()  # Reset timer for next chunk
                        
                        # Verify file was written
                        if output_path.exists() and output_path.stat().st_size > 0:
                            file_size = output_path.stat().st_size
                            print(f"✓ ({file_size:,} bytes)")
                            downloaded += 1
                            download_success = True
                            break
                        else:
                            print("✗ (file empty)")
                            if output_path.exists():
                                output_path.unlink()
                    else:
                        if attempt < self.max_retries - 1:
                            print(f"✗ (status {file_response.status_code}, retrying...)", end=" ")
                            time.sleep(self.retry_delay)
                        
                except (requests.exceptions.RequestException, requests.exceptions.Timeout) as e:
                    # Clean up partial download
                    if output_path.exists():
                        output_path.unlink()
                    
                    if attempt < self.max_retries - 1:
                        print(f"✗ (timeout, retrying {attempt+2}/{self.max_retries}...)", end=" ")
                        time.sleep(self.retry_delay)
                    else:
                        print(f"✗ (failed: {str(e)[:50]})")
            
            if not download_success:
                print(f"✗ (failed after {self.max_retries} attempts)")
                failed += 1
        
        # Summary
        print(f"\n{'='*70}")
        print(f"📊 Download Summary:")
        print(f"   ✓ Downloaded: {downloaded} files")
        if skipped > 0:
            print(f"   ⊙ Skipped: {skipped} files (already existed)")
        if failed > 0:
            print(f"   ✗ Failed: {failed} files")
            print(f"\n💡 Run the script again to retry failed downloads")
        print(f"   📁 Location: {output_dir}")
        print(f"{'='*70}")
        
        return failed == 0


def download_modis_data():
    """Main function to download MODIS data."""
    
    print("🛰️  MODIS Data Downloader (AppEEARS API)")
    print("=" * 70)
    
    # Configuration
    AOI_FILE = Path("data/raw/boundaries/asal_boundary.geojson")
    START_DATE = "01-01-2020"
    END_DATE = "12-31-2025"
    OUTPUT_DIR = Path("data/raw/modis_ndvi")
    TASK_NAME = "MODIS_NDVI_Kenya_ASAL_2020_2025"
    
    # Check if boundary file exists
    if not AOI_FILE.exists():
        print(f"❌ Boundary file not found: {AOI_FILE}")
        print("   Please ensure your ASAL boundary GeoJSON exists")
        return
    
    # Initialize downloader
    downloader = AppEEARSDownloader()
    
    # Step 1: Login
    print("\n📋 You need a NASA Earthdata account")
    print("   If you don't have one, register at:")
    print("   https://urs.earthdata.nasa.gov/users/new")
    
    if not downloader.login():
        return
    
    # Step 2: Submit request
    task_id = downloader.create_area_request(
        AOI_FILE,
        START_DATE,
        END_DATE,
        TASK_NAME
    )
    
    if not task_id:
        return
    
    # Step 3: Save task ID for later
    task_file = Path("modis_download_task_id.txt")
    try:
        with open(task_file, 'w') as f:
            f.write(task_id)
        print(f"\n💾 Task ID saved to {task_file}")
        print(f"   You can resume download later using this ID")
    except Exception as e:
        print(f"⚠️  Warning: Could not save task ID: {e}")
        print(f"   Please note your task ID: {task_id}")
    
    # Step 4: Wait for completion
    print("\n" + "="*70)
    user_input = input("Wait for processing to complete? (y/n): ").lower().strip()
    
    if user_input == 'y':
        if downloader.wait_for_completion(task_id):
            # Step 5: Download files
            downloader.download_files(task_id, OUTPUT_DIR)
        else:
            print("\n⚠️  Processing not complete")
            print(f"   Run this script later to download files:")
            print(f"   python -m scripts.fetch_modis_ndvi {task_id}")
    else:
        print("\n💡 To check status or download files later, run:")
        print(f"   python -m scripts.fetch_modis_ndvi {task_id}")


def resume_download(task_id: str):
    """Resume a previous download using task ID."""
    
    print("🔄 Resuming MODIS download...")
    print("=" * 70)
    
    downloader = AppEEARSDownloader()
    
    if not downloader.login():
        return
    
    # Check status
    print("\n🔍 Checking task status...")
    status = downloader.check_status(task_id)
    
    if status is None:
        print("❌ Invalid task ID or authentication failed")
        print(f"   Task ID: {task_id}")
        return
    
    state = status.get("status", "unknown")
    print(f"   Status: {state}")
    
    if state == "done":
        print("✅ Data is ready for download!")
        OUTPUT_DIR = Path("data/raw/modis_ndvi")
        downloader.download_files(task_id, OUTPUT_DIR)
    elif state == "error":
        print("❌ Processing failed")
        error_msg = status.get("message", "No error message")
        print(f"   Error: {error_msg}")
    elif state in ["pending", "processing"]:
        print(f"⏳ Task is still {state}")
        print("   Estimated time: 1-3 hours from submission")
        print(f"\n💡 Check again later by running:")
        print(f"   python -m scripts.fetch_modis_ndvi {task_id}")
    else:
        print(f"❓ Unknown status: {state}")
        print("   Please check the AppEEARS website for more information")


if __name__ == '__main__':
    try:
        if len(sys.argv) > 1:
            # Resume with task ID
            task_id = sys.argv[1]
            resume_download(task_id)
        else:
            # New download
            download_modis_data()
    except KeyboardInterrupt:
        print("\n\n⏸️  Interrupted by user. Exiting gracefully...")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        print("   Please report this issue if it persists")
        sys.exit(1)
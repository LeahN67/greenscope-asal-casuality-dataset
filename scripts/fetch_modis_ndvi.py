"""
Download MODIS MOD13Q1 NDVI data using NASA AppEEARS API
This downloads data as GeoTIFF (easier to process than HDF)

Features:
- Resume interrupted downloads
- Retry failed requests
- Progress tracking
- Error handling
- Generalized paths and configuration
"""

import requests
import json
import time
from pathlib import Path
import getpass
import sys
import os
from typing import Optional, Dict, Any

# ------------------------------------------------------------------
# PATH CONFIGURATION
# ------------------------------------------------------------------
# Use environment variable with fallback to current directory
PROJECT_ROOT = Path(os.getenv('GREENSCOPE_PROJECT_ROOT', Path.cwd()))

# Default paths
DEFAULT_BOUNDARY_FILE = PROJECT_ROOT / "data" / "raw" / "boundaries" / "asal_boundary.geojson"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "raw" / "modis_ndvi"
DEFAULT_TASK_FILE = PROJECT_ROOT / "modis_download_task_id.txt"


class AppEEARSDownloader:
    """Download MODIS data via AppEEARS API with robust error handling."""
    
    def __init__(self, api_url=None, max_retries=3, retry_delay=5):
        """
        Initialize AppEEARS downloader.
        
        Parameters:
        -----------
        api_url : str, optional
            AppEEARS API URL (default: NASA EarthData Cloud)
        max_retries : int
            Maximum number of retry attempts (default: 3)
        retry_delay : int
            Delay between retries in seconds (default: 5)
        """
        self.api_url = api_url or "https://appeears.earthdatacloud.nasa.gov/api"
        self.token = None
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        
    def login(self, username: Optional[str] = None, password: Optional[str] = None) -> bool:
        """
        Login to AppEEARS and get authentication token.
        
        Parameters:
        -----------
        username : str, optional
            NASA Earthdata username (will prompt if not provided)
        password : str, optional
            NASA Earthdata password (will prompt if not provided)
            
        Returns:
        --------
        bool
            True if authentication successful, False otherwise
        """
        # Check for credentials in environment variables
        if username is None:
            username = os.getenv('NASA_EARTHDATA_USERNAME')
        if password is None:
            password = os.getenv('NASA_EARTHDATA_PASSWORD')
        
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
    
    def create_area_request(self, aoi_file: Path, start_date: str, end_date: str, 
                           output_name: str, product: str = "MOD13Q1.061",
                           layer: str = "_250m_16_days_NDVI") -> Optional[str]:
        """
        Create an area-based data request.
        
        Parameters:
        -----------
        aoi_file : Path
            Path to GeoJSON boundary file
        start_date : str
            Start date (MM-DD-YYYY format)
        end_date : str
            End date (MM-DD-YYYY format)
        output_name : str
            Name for the download task
        product : str
            MODIS product (default: MOD13Q1.061)
        layer : str
            Data layer to download (default: _250m_16_days_NDVI)
            
        Returns:
        --------
        str or None
            Task ID if successful, None otherwise
        """
        print(f"\n📝 Creating data request...")
        print(f"   Study area: {aoi_file}")
        print(f"   Date range: {start_date} to {end_date}")
        print(f"   Product: {product}")
        print(f"   Layer: {layer}")
        
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
                        "product": product,
                        "layer": layer
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
            print(f"\n\n⏸️ Interrupted by user")
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
                        
                        # Download with progress
                        bytes_downloaded = 0
                        chunk_start_time = time.time()
                        max_chunk_time = 60
                        last_progress_update = time.time()
                        progress_interval = 2
                        
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
                                    
                                    chunk_start_time = time.time()
                        
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


def download_modis_data(boundary_file=None, start_date="01-01-2020", end_date="12-31-2025",
                       output_dir=None, task_name=None, product="MOD13Q1.061",
                       layer="_250m_16_days_NDVI", username=None, password=None,
                       wait_for_completion=True):
    """
    Main function to download MODIS data.
    
    Parameters:
    -----------
    boundary_file : Path, optional
        Path to study area boundary GeoJSON
    start_date : str
        Start date in MM-DD-YYYY format
    end_date : str
        End date in MM-DD-YYYY format
    output_dir : Path, optional
        Output directory for downloaded files
    task_name : str, optional
        Name for the download task
    product : str
        MODIS product (default: MOD13Q1.061)
    layer : str
        Data layer (default: _250m_16_days_NDVI)
    username : str, optional
        NASA Earthdata username
    password : str, optional
        NASA Earthdata password
    wait_for_completion : bool
        Whether to wait for processing to complete
        
    Returns:
    --------
    str or None
        Task ID if successful, None otherwise
    """
    boundary_file = Path(boundary_file) if boundary_file else DEFAULT_BOUNDARY_FILE
    output_dir = Path(output_dir) if output_dir else DEFAULT_OUTPUT_DIR
    
    if task_name is None:
        task_name = f"MODIS_NDVI_{start_date.replace('-', '')}_{end_date.replace('-', '')}"
    
    print("🛰️ MODIS Data Downloader (AppEEARS API)")
    print("=" * 70)
    
    # Check if boundary file exists
    if not boundary_file.exists():
        print(f"❌ Boundary file not found: {boundary_file}")
        print("   Please ensure your boundary GeoJSON exists")
        return None
    
    # Initialize downloader
    downloader = AppEEARSDownloader()
    
    # Step 1: Login
    print("\n📋 You need a NASA Earthdata account")
    print("   If you don't have one, register at:")
    print("   https://urs.earthdata.nasa.gov/users/new")
    
    if not downloader.login(username, password):
        return None
    
    # Step 2: Submit request
    task_id = downloader.create_area_request(
        boundary_file,
        start_date,
        end_date,
        task_name,
        product,
        layer
    )
    
    if not task_id:
        return None
    
    # Step 3: Save task ID for later
    task_file = DEFAULT_TASK_FILE
    try:
        task_file.parent.mkdir(parents=True, exist_ok=True)
        with open(task_file, 'w') as f:
            f.write(task_id)
        print(f"\n💾 Task ID saved to {task_file}")
        print(f"   You can resume download later using this ID")
    except Exception as e:
        print(f"⚠️ Warning: Could not save task ID: {e}")
        print(f"   Please note your task ID: {task_id}")
    
    # Step 4: Wait for completion
    if wait_for_completion:
        print("\n" + "="*70)
        user_input = input("Wait for processing to complete? (y/n): ").lower().strip()
        
        if user_input == 'y':
            if downloader.wait_for_completion(task_id):
                # Step 5: Download files
                downloader.download_files(task_id, output_dir)
        else:
            print("\n💡 To check status or download files later, run:")
            print(f"   python fetch_modis_ndvi.py --resume {task_id}")
    
    return task_id


def resume_download(task_id: str, output_dir=None, username=None, password=None):
    """
    Resume a previous download using task ID.
    
    Parameters:
    -----------
    task_id : str
        AppEEARS task ID
    output_dir : Path, optional
        Output directory for files
    username : str, optional
        NASA Earthdata username
    password : str, optional
        NASA Earthdata password
    """
    output_dir = Path(output_dir) if output_dir else DEFAULT_OUTPUT_DIR
    
    print("🔄 Resuming MODIS download...")
    print("=" * 70)
    
    downloader = AppEEARSDownloader()
    
    if not downloader.login(username, password):
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
        downloader.download_files(task_id, output_dir)
    elif state == "error":
        print("❌ Processing failed")
        error_msg = status.get("message", "No error message")
        print(f"   Error: {error_msg}")
    elif state in ["pending", "processing"]:
        print(f"⏳ Task is still {state}")
        print("   Estimated time: 1-3 hours from submission")
        print(f"\n💡 Check again later by running:")
        print(f"   python fetch_modis_ndvi.py --resume {task_id}")
    else:
        print(f"❓ Unknown status: {state}")
        print("   Please check the AppEEARS website for more information")


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Download MODIS NDVI data via NASA AppEEARS API',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        '--project-root',
        type=str,
        help='Base project directory'
    )
    parser.add_argument(
        '--boundary',
        type=str,
        help='Path to boundary GeoJSON file'
    )
    parser.add_argument(
        '--start-date',
        type=str,
        default='01-01-2020',
        help='Start date (MM-DD-YYYY format, default: 01-01-2020)'
    )
    parser.add_argument(
        '--end-date',
        type=str,
        default='12-31-2025',
        help='End date (MM-DD-YYYY format, default: 12-31-2025)'
    )
    parser.add_argument(
        '--output-dir',
        type=str,
        help='Output directory for downloaded files'
    )
    parser.add_argument(
        '--task-name',
        type=str,
        help='Name for the download task'
    )
    parser.add_argument(
        '--product',
        type=str,
        default='MOD13Q1.061',
        help='MODIS product (default: MOD13Q1.061)'
    )
    parser.add_argument(
        '--layer',
        type=str,
        default='_250m_16_days_NDVI',
        help='Data layer (default: _250m_16_days_NDVI)'
    )
    parser.add_argument(
        '--username',
        type=str,
        help='NASA Earthdata username (or set NASA_EARTHDATA_USERNAME env var)'
    )
    parser.add_argument(
        '--password',
        type=str,
        help='NASA Earthdata password (or set NASA_EARTHDATA_PASSWORD env var)'
    )
    parser.add_argument(
        '--resume',
        type=str,
        metavar='TASK_ID',
        help='Resume download with existing task ID'
    )
    parser.add_argument(
        '--no-wait',
        action='store_true',
        help='Do not wait for processing to complete'
    )
    
    args = parser.parse_args()
    
    # Update paths if project root is provided
    if args.project_root:
        global PROJECT_ROOT, DEFAULT_BOUNDARY_FILE, DEFAULT_OUTPUT_DIR, DEFAULT_TASK_FILE
        PROJECT_ROOT = Path(args.project_root)
        DEFAULT_BOUNDARY_FILE = PROJECT_ROOT / "data" / "raw" / "boundaries" / "asal_boundary.geojson"
        DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "raw" / "modis_ndvi"
        DEFAULT_TASK_FILE = PROJECT_ROOT / "modis_download_task_id.txt"
    
    try:
        if args.resume:
            # Resume with task ID
            resume_download(
                task_id=args.resume,
                output_dir=args.output_dir,
                username=args.username,
                password=args.password
            )
        else:
            # New download
            download_modis_data(
                boundary_file=args.boundary,
                start_date=args.start_date,
                end_date=args.end_date,
                output_dir=args.output_dir,
                task_name=args.task_name,
                product=args.product,
                layer=args.layer,
                username=args.username,
                password=args.password,
                wait_for_completion=not args.no_wait
            )
    except KeyboardInterrupt:
        print("\n\n⏸️ Interrupted by user. Exiting gracefully...")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        print("   Please report this issue if it persists")
        sys.exit(1)
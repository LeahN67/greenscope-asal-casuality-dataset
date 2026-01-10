import requests
from pathlib import Path
import time
from utils.logger import log_download
from utils.checksum import file_checksum

# Updated URL - NOAA PSL has moved their time-series data
URL = "https://psl.noaa.gov/data/timeseries/month/data/dmi.had.long.data"
OUT_DIR = Path("data/raw/iod")
OUT_FILE = OUT_DIR / "dmi_noaa.txt"

# Configuration
MAX_RETRIES = 3
RETRY_DELAY = 5  # seconds
CHUNK_SIZE = 8192
TEMP_SUFFIX = ".tmp"

def download_with_resume(url: str, out_path: Path, max_retries: int = MAX_RETRIES) -> bool:
    """
    Download a file with automatic resume capability and retry logic.
    
    Args:
        url: URL to download from
        out_path: Local path to save the file
        max_retries: Maximum number of retry attempts
    
    Returns:
        True if download succeeded, False otherwise
    """
    temp_path = Path(str(out_path) + TEMP_SUFFIX)
    
    for attempt in range(max_retries):
        try:
            # Check if temporary file exists and get its size
            existing_size = 0
            if temp_path.exists():
                existing_size = temp_path.stat().st_size
                print(f"   Found partial download: {existing_size} bytes")
            
            # Set up headers for resume
            headers = {}
            if existing_size > 0:
                headers['Range'] = f'bytes={existing_size}-'
                print(f"   Resuming from byte {existing_size}...")
            
            # Make the request
            with requests.get(url, headers=headers, stream=True, timeout=120) as r:
                # Handle 416 (Range Not Satisfiable) - file is complete
                if r.status_code == 416:
                    print(f"   Download already complete")
                    if temp_path.exists():
                        temp_path.rename(out_path)
                    return True
                
                # Check if server supports resume
                if existing_size > 0 and r.status_code == 200:
                    print(f"   ⚠ Server doesn't support resume, restarting download...")
                    existing_size = 0
                    temp_path.unlink(missing_ok=True)
                
                # For resume, we expect 206 (Partial Content)
                # For new downloads, we expect 200 (OK)
                if r.status_code not in [200, 206]:
                    r.raise_for_status()
                
                # Get total file size
                total_size = existing_size
                if 'content-range' in r.headers:
                    # Format: bytes start-end/total
                    total_size = int(r.headers['content-range'].split('/')[-1])
                elif 'content-length' in r.headers:
                    total_size = int(r.headers['content-length']) + existing_size
                
                # Open file in append mode if resuming, write mode if new
                mode = 'ab' if existing_size > 0 and r.status_code == 206 else 'wb'
                
                with open(temp_path, mode) as f:
                    downloaded = existing_size
                    last_print_time = time.time()
                    
                    for chunk in r.iter_content(chunk_size=CHUNK_SIZE):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            
                            # Print progress every 0.5 seconds
                            current_time = time.time()
                            if total_size > 0 and (current_time - last_print_time) > 0.5:
                                percent = (downloaded / total_size) * 100
                                kb_downloaded = downloaded / 1024
                                kb_total = total_size / 1024
                                print(f"\r   Progress: {percent:.1f}% ({kb_downloaded:.1f}/{kb_total:.1f} KB)", end="")
                                last_print_time = current_time
                
                print()  # New line after progress
                
                # Verify file size
                final_size = temp_path.stat().st_size
                if total_size > 0 and final_size < total_size:
                    print(f"   ⚠ Warning: Downloaded {final_size} bytes, expected {total_size}")
                    if attempt < max_retries - 1:
                        print(f"   Retrying... (attempt {attempt + 2}/{max_retries})")
                        time.sleep(RETRY_DELAY)
                        continue
                
                # Move temp file to final location
                temp_path.rename(out_path)
                print(f"   ✔ Download complete: {out_path.name}")
                
                return True
                
        except requests.exceptions.ConnectionError as e:
            print(f"\n   ❌ Connection error: {e}")
            if attempt < max_retries - 1:
                print(f"   Retrying in {RETRY_DELAY} seconds... (attempt {attempt + 2}/{max_retries})")
                time.sleep(RETRY_DELAY)
            else:
                print(f"   ❌ Failed after {max_retries} attempts")
                return False
                
        except requests.exceptions.Timeout as e:
            print(f"\n   ❌ Timeout: {e}")
            if attempt < max_retries - 1:
                print(f"   Retrying in {RETRY_DELAY} seconds... (attempt {attempt + 2}/{max_retries})")
                time.sleep(RETRY_DELAY)
            else:
                print(f"   ❌ Failed after {max_retries} attempts")
                return False
                
        except requests.exceptions.RequestException as e:
            print(f"\n   ❌ Request error: {e}")
            if attempt < max_retries - 1:
                print(f"   Retrying in {RETRY_DELAY} seconds... (attempt {attempt + 2}/{max_retries})")
                time.sleep(RETRY_DELAY)
            else:
                print(f"   ❌ Failed after {max_retries} attempts")
                return False
                
        except Exception as e:
            print(f"\n   ❌ Unexpected error: {e}")
            if attempt < max_retries - 1:
                print(f"   Retrying in {RETRY_DELAY} seconds... (attempt {attempt + 2}/{max_retries})")
                time.sleep(RETRY_DELAY)
            else:
                print(f"   ❌ Failed after {max_retries} attempts")
                return False
    
    return False

def main():
    print("="*60)
    print("Indian Ocean Dipole (IOD) Downloader")
    print("="*60)
    print("\nℹ  Dataset Information:")
    print("  - Index: Dipole Mode Index (DMI)")
    print("  - Source: NOAA PSL (HadISST1.1)")
    print("  - Coverage: January 1870 to near present")
    print("  - Update: Monthly")
    print("  - Format: Text file (Standard PSL Format)")
    print("="*60)
    
    # Create output directory
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # Check if file already exists
    if OUT_FILE.exists():
        file_size = OUT_FILE.stat().st_size
        print(f"\n✓ File already exists ({file_size} bytes)")
        response = input("Re-download? (y/n): ")
        if response.lower() != 'y':
            print("✔ Using existing file")
            
            # Still log and checksum the existing file
            try:
                checksum = file_checksum(OUT_FILE)
                print(f"   Checksum: {checksum}")
                log_download(
                    dataset="Indian Ocean Dipole (DMI)",
                    source=URL,
                    file_path=OUT_FILE,
                    notes=f"checksum={checksum} (existing file)"
                )
            except Exception as e:
                print(f"   ⚠ Warning: Could not compute checksum: {e}")
            
            return
        else:
            # Remove existing file to start fresh
            OUT_FILE.unlink()
    
    print(f"\n⬇ Downloading IOD Dipole Mode Index...")
    print(f"   URL: {URL}")
    print(f"   Output: {OUT_FILE.absolute()}")
    print(f"\n   Note: You can safely stop (Ctrl+C) and restart - download will resume!")
    print()
    
    try:
        success = download_with_resume(URL, OUT_FILE)
        
        if success:
            file_size = OUT_FILE.stat().st_size
            print(f"\n{'='*60}")
            print(f"✔ Download successful!")
            print(f"   File: {OUT_FILE.name}")
            print(f"   Size: {file_size:,} bytes ({file_size / 1024:.2f} KB)")
            print(f"   Location: {OUT_FILE.absolute()}")
            
            # Compute checksum and log
            try:
                print(f"\n   Computing checksum...")
                checksum = file_checksum(OUT_FILE)
                print(f"   Checksum: {checksum}")
                
                log_download(
                    dataset="Indian Ocean Dipole (DMI)",
                    source=URL,
                    file_path=OUT_FILE,
                    notes=f"checksum={checksum}"
                )
                print(f"   ✔ Download logged successfully")
                
            except Exception as e:
                print(f"   ⚠ Warning: Could not compute checksum or log download: {e}")
            
            print(f"{'='*60}")
            print(f"\n💡 Next steps:")
            print(f"   - Parse the DMI data for your analysis")
            print(f"   - Check for positive (warm) and negative (cool) IOD events")
            print(f"   - Correlate with regional climate patterns")
            print(f"\n📊 Additional data formats available:")
            print(f"   - CSV: https://psl.noaa.gov/data/timeseries/month/data/dmi.had.long.csv")
            print(f"   - NetCDF: https://psl.noaa.gov/data/timeseries/month/data/dmi.had.long.nc")
            
        else:
            print(f"\n❌ Download failed after all retry attempts")
            print(f"   Please check your internet connection and try again")
            
    except KeyboardInterrupt:
        print(f"\n\n⏸ Download interrupted by user")
        temp_path = Path(str(OUT_FILE) + TEMP_SUFFIX)
        if temp_path.exists():
            partial_size = temp_path.stat().st_size
            print(f"   Partial file saved: {partial_size:,} bytes")
            print(f"   Run the script again to resume from where you left off!")
        else:
            print(f"   No partial download to resume")

if __name__ == "__main__":
    main()
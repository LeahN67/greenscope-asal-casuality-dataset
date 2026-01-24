import requests
from pathlib import Path
import time
import os

# ------------------------------------------------------------------
# PATH CONFIGURATION
# ------------------------------------------------------------------
# Use environment variable with fallback to current directory
PROJECT_ROOT = Path(os.getenv('GREENSCOPE_PROJECT_ROOT', Path.cwd()))

# Default output directories
DEFAULT_NETCDF_DIR = PROJECT_ROOT / "data" / "raw" / "chirps" / "monthly"
DEFAULT_GEOTIFF_DIR = PROJECT_ROOT / "data" / "raw" / "chirps" / "monthly_tifs_v2"

# Configuration
MAX_RETRIES = 3
RETRY_DELAY = 5
CHUNK_SIZE = 8192


def download_with_resume(url: str, out_path: Path, max_retries: int = MAX_RETRIES) -> bool:
    """
    Download a file with automatic resume capability and retry logic.
    
    Parameters:
    -----------
    url : str
        URL to download from
    out_path : Path
        Output file path
    max_retries : int
        Maximum number of retry attempts
        
    Returns:
    --------
    bool
        True if download successful, False otherwise
    """
    for attempt in range(max_retries):
        try:
            existing_size = 0
            if out_path.exists():
                existing_size = out_path.stat().st_size
            
            headers = {}
            if existing_size > 0:
                headers['Range'] = f'bytes={existing_size}-'
                print(f"   Resuming from {existing_size / (1024**2):.2f} MB")
            
            with requests.get(url, headers=headers, stream=True, timeout=120) as r:
                if r.status_code == 416:
                    print(f"   File already complete")
                    return True
                
                if r.status_code not in [200, 206]:
                    r.raise_for_status()
                
                total_size = existing_size
                if 'content-range' in r.headers:
                    total_size = int(r.headers['content-range'].split('/')[-1])
                elif 'content-length' in r.headers:
                    total_size = int(r.headers['content-length']) + existing_size
                
                mode = 'ab' if existing_size > 0 else 'wb'
                
                with open(out_path, mode) as f:
                    downloaded = existing_size
                    last_print_time = time.time()
                    
                    for chunk in r.iter_content(chunk_size=CHUNK_SIZE):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            
                            current_time = time.time()
                            if total_size > 0 and (current_time - last_print_time) > 0.5:
                                percent = (downloaded / total_size) * 100
                                mb_downloaded = downloaded / (1024**2)
                                mb_total = total_size / (1024**2)
                                print(f"\r   Progress: {percent:.1f}% ({mb_downloaded:.1f}/{mb_total:.1f} MB)", end="")
                                last_print_time = current_time
                
                print()
                return True
                
        except requests.exceptions.RequestException as e:
            print(f"\n   ❌ Error: {e}")
            if attempt < max_retries - 1:
                print(f"   Retrying in {RETRY_DELAY} seconds... (attempt {attempt + 2}/{max_retries})")
                time.sleep(RETRY_DELAY)
            else:
                return False
                
        except Exception as e:
            print(f"\n   ❌ Unexpected error: {e}")
            if attempt < max_retries - 1:
                print(f"   Retrying in {RETRY_DELAY} seconds... (attempt {attempt + 2}/{max_retries})")
                time.sleep(RETRY_DELAY)
            else:
                return False
    
    return False


def download_chirps_netcdf(output_dir=None, filename="chirps-v2.0.monthly.nc", 
                           force_redownload=False):
    """
    Download the complete CHIRPS v2 monthly NetCDF file.
    
    Parameters:
    -----------
    output_dir : str or Path, optional
        Output directory (default: data/raw/chirps/monthly)
    filename : str, optional
        Output filename (default: chirps-v2.0.monthly.nc)
    force_redownload : bool
        Force re-download even if file exists
        
    Returns:
    --------
    bool
        True if download successful, False otherwise
    """
    output_dir = Path(output_dir) if output_dir else DEFAULT_NETCDF_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print("="*60)
    print("CHIRPS v2 Monthly Data Downloader (NetCDF format)")
    print("="*60)
    
    url = "https://data.chc.ucsb.edu/products/CHIRPS-2.0/global_monthly/netcdf/chirps-v2.0.monthly.nc"
    out_path = output_dir / filename
    
    # Check if file already exists
    if out_path.exists() and not force_redownload:
        file_size = out_path.stat().st_size
        file_size_gb = file_size / (1024**3)
        
        # If file is larger than 1GB, it's probably complete
        if file_size > 1_000_000_000:
            print(f"\n✓ File already exists ({file_size_gb:.2f} GB)")
            response = input("Re-download? (y/n): ")
            if response.lower() != 'y':
                print("✓ Using existing file")
                print(f"   Location: {out_path.absolute()}")
                return True
        else:
            print(f"\n⚠ Partial file found ({file_size_gb:.2f} GB)")
            print("   Will resume download...")
    
    print(f"\n⬇ Downloading CHIRPS v2 monthly dataset...")
    print(f"   URL: {url}")
    print(f"   Output: {out_path.absolute()}")
    print(f"\n   Note: You can safely stop (Ctrl+C) and restart - download will resume!")
    print()
    
    try:
        success = download_with_resume(url, out_path)
        
        if success:
            file_size = out_path.stat().st_size
            print(f"\n✓ Successfully downloaded!")
            print(f"   File: {out_path.name}")
            print(f"   Size: {file_size / (1024**3):.2f} GB")
            print(f"   Location: {out_path.absolute()}")
            return True
        else:
            print(f"\n❌ Download failed after all retry attempts")
            return False
            
    except KeyboardInterrupt:
        print(f"\n\n⏸ Download interrupted by user")
        if out_path.exists():
            partial_size = out_path.stat().st_size
            print(f"   Partial file saved: {partial_size / (1024**2):.2f} MB")
            print(f"   Run the script again to resume!")
        return False


def download_chirps_geotiff(output_dir=None, start_year=1981, end_year=2024):
    """
    Download CHIRPS v2 monthly data as individual GeoTIFF files.
    
    Parameters:
    -----------
    output_dir : str or Path, optional
        Output directory (default: data/raw/chirps/monthly_tifs_v2)
    start_year : int
        First year to download (default: 1981)
    end_year : int
        Last year to download (default: 2024)
        
    Returns:
    --------
    bool
        True if at least one file downloaded successfully
    """
    output_dir = Path(output_dir) if output_dir else DEFAULT_GEOTIFF_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print("\n" + "="*60)
    print("CHIRPS v2 Monthly Data Downloader (GeoTIFF format)")
    print("="*60)
    
    BASE_URL = "https://data.chc.ucsb.edu/products/CHIRPS-2.0/global_monthly/tifs/"
    
    # Progress tracking
    progress_file = output_dir / ".download_progress.txt"
    completed = set()
    
    if progress_file.exists():
        with open(progress_file, 'r') as f:
            completed = set(line.strip() for line in f)
        print(f"\n✓ Resuming from previous session ({len(completed)} files completed)")
    
    success_count = 0
    fail_count = 0
    total_files = (end_year - start_year + 1) * 12
    
    print(f"\nDownloading {total_files} monthly files from {start_year} to {end_year}...")
    print(f"Output directory: {output_dir.absolute()}\n")
    
    try:
        for year in range(start_year, end_year + 1):
            for month in range(1, 13):
                fname = f"chirps-v2.0.{year}.{month:02d}.tif.gz"
                
                if fname in completed:
                    success_count += 1
                    continue
                
                url = BASE_URL + fname
                out_path = output_dir / fname
                
                # Check if file exists and is complete
                if out_path.exists() and out_path.stat().st_size > 100_000:
                    print(f"✓ Already complete: {fname}")
                    success_count += 1
                    completed.add(fname)
                    with open(progress_file, 'a') as f:
                        f.write(f"{fname}\n")
                    continue
                
                current_num = success_count + fail_count + 1
                print(f"⬇ [{current_num}/{total_files}] {fname}...")
                
                success = download_with_resume(url, out_path, max_retries=3)
                
                if success:
                    success_count += 1
                    completed.add(fname)
                    with open(progress_file, 'a') as f:
                        f.write(f"{fname}\n")
                else:
                    fail_count += 1
        
        print(f"\n{'='*60}")
        print(f"Download Summary:")
        print(f"  ✓ Successful: {success_count}/{total_files}")
        print(f"  ❌ Failed: {fail_count}/{total_files}")
        print(f"  📁 Location: {output_dir.absolute()}")
        print(f"{'='*60}")
        
        if fail_count > 0:
            print(f"\n💡 Run the script again to retry failed downloads")
        
        return success_count > 0
        
    except KeyboardInterrupt:
        print(f"\n\n⏸ Download interrupted")
        print(f"   Progress saved: {success_count} files completed")
        print(f"   Run again to continue!")
        return False


def main(project_root=None, format_choice=None, output_dir=None, 
         start_year=1981, end_year=2024, force_redownload=False):
    """
    Main function to download CHIRPS data.
    
    Parameters:
    -----------
    project_root : str or Path, optional
        Base project directory
    format_choice : str, optional
        Format to download ('netcdf' or 'geotiff')
    output_dir : str or Path, optional
        Custom output directory
    start_year : int
        First year for GeoTIFF downloads
    end_year : int
        Last year for GeoTIFF downloads
    force_redownload : bool
        Force re-download for NetCDF
    """
    global PROJECT_ROOT, DEFAULT_NETCDF_DIR, DEFAULT_GEOTIFF_DIR
    
    # Update paths if project root is provided
    if project_root:
        PROJECT_ROOT = Path(project_root)
        DEFAULT_NETCDF_DIR = PROJECT_ROOT / "data" / "raw" / "chirps" / "monthly"
        DEFAULT_GEOTIFF_DIR = PROJECT_ROOT / "data" / "raw" / "chirps" / "monthly_tifs_v2"
    
    print("\n" + "="*60)
    print("CHIRPS v2 Data Downloader")
    print("="*60)
    print("\nℹ️  CHIRPS v2.0 Information:")
    print("  - Coverage: 1981-present, 50°S-50°N")
    print("  - Resolution: 0.05° (~5.5 km)")
    print("  - Updated: Operational and maintained")
    print("="*60)
    
    if format_choice is None:
        print("\nChoose download format:")
        print("  1. NetCDF (single file, ~2-3 GB, recommended)")
        print("  2. GeoTIFF (individual monthly files, .gz compressed)")
        
        choice = input("\nEnter choice (1 or 2): ").strip()
        format_choice = "netcdf" if choice == "1" else "geotiff" if choice == "2" else "netcdf"
    
    if format_choice.lower() in ["netcdf", "nc", "1"]:
        return download_chirps_netcdf(
            output_dir=output_dir,
            force_redownload=force_redownload
        )
    elif format_choice.lower() in ["geotiff", "tiff", "tif", "2"]:
        return download_chirps_geotiff(
            output_dir=output_dir,
            start_year=start_year,
            end_year=end_year
        )
    else:
        print("\nInvalid choice. Defaulting to NetCDF...")
        return download_chirps_netcdf(
            output_dir=output_dir,
            force_redownload=force_redownload
        )


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Download CHIRPS v2 precipitation data'
    )
    parser.add_argument(
        '--project-root',
        type=str,
        help='Base project directory (default: current directory or GREENSCOPE_PROJECT_ROOT env var)'
    )
    parser.add_argument(
        '--format',
        type=str,
        choices=['netcdf', 'geotiff', 'nc', 'tiff'],
        help='Download format: netcdf or geotiff'
    )
    parser.add_argument(
        '--output-dir',
        type=str,
        help='Custom output directory'
    )
    parser.add_argument(
        '--start-year',
        type=int,
        default=1981,
        help='Start year for GeoTIFF downloads (default: 1981)'
    )
    parser.add_argument(
        '--end-year',
        type=int,
        default=2024,
        help='End year for GeoTIFF downloads (default: 2024)'
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='Force re-download even if file exists (NetCDF only)'
    )
    parser.add_argument(
        '--non-interactive',
        action='store_true',
        help='Run in non-interactive mode (requires --format)'
    )
    
    args = parser.parse_args()
    
    # Validate non-interactive mode
    if args.non_interactive and not args.format:
        parser.error("--non-interactive requires --format to be specified")
    
    # Run with arguments
    main(
        project_root=args.project_root,
        format_choice=args.format,
        output_dir=args.output_dir,
        start_year=args.start_year,
        end_year=args.end_year,
        force_redownload=args.force
    )
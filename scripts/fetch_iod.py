import requests
from pathlib import Path
import time
import os
import hashlib

# ------------------------------------------------------------------
# PATH CONFIGURATION
# ------------------------------------------------------------------
# Use environment variable with fallback to current directory
PROJECT_ROOT = Path(os.getenv('GREENSCOPE_PROJECT_ROOT', Path.cwd()))

# Default paths
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "raw" / "iod"
DEFAULT_OUTPUT_FILE = "dmi_noaa.txt"

# IOD data sources
IOD_SOURCES = {
    'dmi': {
        'txt': 'https://psl.noaa.gov/data/timeseries/month/data/dmi.had.long.data',
        'csv': 'https://psl.noaa.gov/data/timeseries/month/data/dmi.had.long.csv',
        'nc': 'https://psl.noaa.gov/data/timeseries/month/data/dmi.had.long.nc',
        'description': 'Dipole Mode Index (DMI) - HadISST1.1',
        'coverage': 'January 1870 to present'
    }
}

# Configuration
MAX_RETRIES = 3
RETRY_DELAY = 5  # seconds
CHUNK_SIZE = 8192
TEMP_SUFFIX = ".tmp"


def file_checksum(file_path: Path, algorithm: str = 'sha256') -> str:
    """
    Compute checksum of a file.
    
    Parameters:
    -----------
    file_path : Path
        Path to the file
    algorithm : str
        Hash algorithm (default: sha256)
        
    Returns:
    --------
    str
        Hexadecimal checksum string
    """
    hash_func = hashlib.new(algorithm)
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b''):
            hash_func.update(chunk)
    return hash_func.hexdigest()


def log_download(dataset: str, source: str, file_path: Path, notes: str = ""):
    """
    Log download information to a file.
    
    Parameters:
    -----------
    dataset : str
        Dataset name
    source : str
        Source URL
    file_path : Path
        Downloaded file path
    notes : str
        Additional notes
    """
    log_dir = file_path.parent / "logs"
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / "download_log.txt"
    
    timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
    log_entry = f"[{timestamp}] {dataset} | {source} | {file_path.name} | {notes}\n"
    
    with open(log_file, 'a') as f:
        f.write(log_entry)


def download_with_resume(url: str, out_path: Path, max_retries: int = MAX_RETRIES) -> bool:
    """
    Download a file with automatic resume capability and retry logic.
    
    Parameters:
    -----------
    url : str
        URL to download from
    out_path : Path
        Local path to save the file
    max_retries : int
        Maximum number of retry attempts
    
    Returns:
    --------
    bool
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
                print(f"   ✓ Download complete: {out_path.name}")
                
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


def download_iod_index(index_type='dmi', format_type='txt', output_dir=None, 
                       output_filename=None, force_redownload=False, 
                       compute_checksum=True, log_enabled=True):
    """
    Download Indian Ocean Dipole (IOD) index data from NOAA.
    
    Parameters:
    -----------
    index_type : str
        Type of IOD index (currently only 'dmi' supported)
    format_type : str
        File format ('txt', 'csv', or 'nc')
    output_dir : str or Path, optional
        Output directory
    output_filename : str, optional
        Custom output filename
    force_redownload : bool
        Force re-download even if file exists
    compute_checksum : bool
        Compute and log file checksum
    log_enabled : bool
        Enable download logging
        
    Returns:
    --------
    bool
        True if download successful, False otherwise
    """
    # Validate index type
    if index_type not in IOD_SOURCES:
        raise ValueError(f"Unknown index type: {index_type}. Choose from {list(IOD_SOURCES.keys())}")
    
    # Validate format
    if format_type not in IOD_SOURCES[index_type] or format_type == 'description' or format_type == 'coverage':
        raise ValueError(f"Unknown format: {format_type}. Choose from {[k for k in IOD_SOURCES[index_type].keys() if k not in ['description', 'coverage']]}")
    
    source_info = IOD_SOURCES[index_type]
    url = source_info[format_type]
    description = source_info['description']
    coverage = source_info['coverage']
    
    # Setup paths
    output_dir = Path(output_dir) if output_dir else DEFAULT_OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    
    if output_filename is None:
        output_filename = f"{index_type}_noaa.{format_type}"
    
    output_file = output_dir / output_filename
    
    print("="*60)
    print(f"Indian Ocean Dipole (IOD) Downloader")
    print("="*60)
    print(f"\nℹ️  Dataset Information:")
    print(f"  - Index: {description}")
    print(f"  - Source: NOAA PSL")
    print(f"  - Coverage: {coverage}")
    print(f"  - Update: Monthly")
    print(f"  - Format: {format_type.upper()}")
    print("="*60)
    
    # Check if file already exists
    if output_file.exists() and not force_redownload:
        file_size = output_file.stat().st_size
        print(f"\n✓ File already exists ({file_size} bytes)")
        response = input("Re-download? (y/n): ")
        if response.lower() != 'y':
            print("✓ Using existing file")
            
            # Still log and checksum the existing file
            if compute_checksum:
                try:
                    checksum = file_checksum(output_file)
                    print(f"   Checksum: {checksum}")
                    if log_enabled:
                        log_download(
                            dataset=f"IOD {index_type.upper()}",
                            source=url,
                            file_path=output_file,
                            notes=f"checksum={checksum} (existing file)"
                        )
                except Exception as e:
                    print(f"   ⚠ Warning: Could not compute checksum: {e}")
            
            return True
        else:
            # Remove existing file to start fresh
            output_file.unlink()
    
    print(f"\n⬇ Downloading {description}...")
    print(f"   URL: {url}")
    print(f"   Output: {output_file.absolute()}")
    print(f"\n   Note: You can safely stop (Ctrl+C) and restart - download will resume!")
    print()
    
    try:
        success = download_with_resume(url, output_file)
        
        if success:
            file_size = output_file.stat().st_size
            print(f"\n{'='*60}")
            print(f"✓ Download successful!")
            print(f"   File: {output_file.name}")
            print(f"   Size: {file_size:,} bytes ({file_size / 1024:.2f} KB)")
            print(f"   Location: {output_file.absolute()}")
            
            # Compute checksum and log
            if compute_checksum:
                try:
                    print(f"\n   Computing checksum...")
                    checksum = file_checksum(output_file)
                    print(f"   Checksum: {checksum}")
                    
                    if log_enabled:
                        log_download(
                            dataset=f"IOD {index_type.upper()}",
                            source=url,
                            file_path=output_file,
                            notes=f"checksum={checksum}"
                        )
                        print(f"   ✓ Download logged successfully")
                    
                except Exception as e:
                    print(f"   ⚠ Warning: Could not compute checksum or log download: {e}")
            
            print(f"{'='*60}")
            print(f"\n💡 Next steps:")
            print(f"   - Parse the DMI data for your analysis")
            print(f"   - Check for positive (warm) and negative (cool) IOD events")
            print(f"   - Correlate with regional climate patterns")
            
            if format_type == 'txt':
                print(f"\n📊 Additional formats available:")
                print(f"   - CSV: Use --format csv")
                print(f"   - NetCDF: Use --format nc")
            
            return True
            
        else:
            print(f"\n❌ Download failed after all retry attempts")
            print(f"   Please check your internet connection and try again")
            return False
            
    except KeyboardInterrupt:
        print(f"\n\n⏸ Download interrupted by user")
        temp_path = Path(str(output_file) + TEMP_SUFFIX)
        if temp_path.exists():
            partial_size = temp_path.stat().st_size
            print(f"   Partial file saved: {partial_size:,} bytes")
            print(f"   Run the script again to resume from where you left off!")
        else:
            print(f"   No partial download to resume")
        return False


def list_available_formats():
    """List all available IOD data formats."""
    print("\nAvailable IOD Data Sources and Formats:")
    print("="*60)
    for index, info in IOD_SOURCES.items():
        print(f"\n{index.upper()}:")
        print(f"  Description: {info['description']}")
        print(f"  Coverage: {info['coverage']}")
        print(f"  Formats:")
        for key, url in info.items():
            if key not in ['description', 'coverage']:
                print(f"    - {key.upper()}: {url}")
    print("="*60)


def main(project_root=None, index_type='dmi', format_type='txt', 
         output_dir=None, output_filename=None, force_redownload=False):
    """
    Main function to download IOD data.
    
    Parameters:
    -----------
    project_root : str or Path, optional
        Base project directory
    index_type : str
        Type of IOD index to download
    format_type : str
        File format to download
    output_dir : str or Path, optional
        Custom output directory
    output_filename : str, optional
        Custom output filename
    force_redownload : bool
        Force re-download even if file exists
    """
    global PROJECT_ROOT, DEFAULT_OUTPUT_DIR
    
    # Update paths if project root is provided
    if project_root:
        PROJECT_ROOT = Path(project_root)
        DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "raw" / "iod"
    
    return download_iod_index(
        index_type=index_type,
        format_type=format_type,
        output_dir=output_dir,
        output_filename=output_filename,
        force_redownload=force_redownload
    )


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Download Indian Ocean Dipole (IOD) indices from NOAA'
    )
    parser.add_argument(
        '--project-root',
        type=str,
        help='Base project directory (default: current directory or GREENSCOPE_PROJECT_ROOT env var)'
    )
    parser.add_argument(
        '--index-type',
        type=str,
        choices=['dmi'],
        default='dmi',
        help='IOD index type to download (default: dmi)'
    )
    parser.add_argument(
        '--format',
        type=str,
        choices=['txt', 'csv', 'nc'],
        default='txt',
        help='File format to download (default: txt)'
    )
    parser.add_argument(
        '--output-dir',
        type=str,
        help='Custom output directory'
    )
    parser.add_argument(
        '--output-filename',
        type=str,
        help='Custom output filename'
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='Force re-download even if file exists'
    )
    parser.add_argument(
        '--list-formats',
        action='store_true',
        help='List available data formats'
    )
    parser.add_argument(
        '--no-checksum',
        action='store_true',
        help='Skip checksum computation'
    )
    parser.add_argument(
        '--no-log',
        action='store_true',
        help='Disable download logging'
    )
    
    args = parser.parse_args()
    
    # List available formats
    if args.list_formats:
        list_available_formats()
        exit(0)
    
    # Update project root if provided
    if args.project_root:
        PROJECT_ROOT = Path(args.project_root)
        DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "raw" / "iod"
    
    # Download the specified index
    download_iod_index(
        index_type=args.index_type,
        format_type=args.format,
        output_dir=args.output_dir,
        output_filename=args.output_filename,
        force_redownload=args.force,
        compute_checksum=not args.no_checksum,
        log_enabled=not args.no_log
    )
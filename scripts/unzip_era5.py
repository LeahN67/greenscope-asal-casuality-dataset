"""
Extract and validate ERA5 NetCDF files from ZIP archives
Supports both ZIP files and direct NetCDF validation
"""
import zipfile
from pathlib import Path
import xarray as xr
import os
import sys

# ------------------------------------------------------------------
# PATH CONFIGURATION
# ------------------------------------------------------------------
# Use environment variable with fallback to current directory
PROJECT_ROOT = Path(os.getenv('GREENSCOPE_PROJECT_ROOT', Path.cwd()))

# Default paths
DEFAULT_ERA5_DIR = PROJECT_ROOT / "data" / "raw" / "era5_land"
DEFAULT_ZIP_FILE = DEFAULT_ERA5_DIR / "era5_complete_drivers.nc"
DEFAULT_OUTPUT_NAME = "era5_complete_drivers.nc"


def validate_netcdf(nc_file: Path, verbose: bool = True) -> bool:
    """
    Validate a NetCDF file and display information.
    
    Parameters:
    -----------
    nc_file : Path
        Path to NetCDF file
    verbose : bool
        Print detailed information
        
    Returns:
    --------
    bool
        True if valid, False otherwise
    """
    if verbose:
        print(f"\n✅ Validating: {nc_file.name}")
    
    # Try different engines
    engines = ['h5netcdf', 'netcdf4', 'scipy']
    ds = None
    successful_engine = None
    
    for engine in engines:
        try:
            ds = xr.open_dataset(nc_file, engine=engine)
            successful_engine = engine
            if verbose:
                print(f"   ✓ Successfully opened with {engine}!")
            break
        except Exception as e:
            if engine == engines[-1]:  # Last attempt
                if verbose:
                    print(f"   ✗ Failed to open with all engines")
                    print(f"   Last error ({engine}): {e}")
                return False
            continue
    
    if ds is None:
        return False
    
    # Display dataset information
    if verbose:
        print(f"\n📊 Dataset Information:")
        print(f"   Variables: {list(ds.data_vars)}")
        print(f"   Dimensions: {dict(ds.dims)}")
        
        if 'time' in ds.dims:
            print(f"   Time range: {ds.time.min().values} to {ds.time.max().values}")
            print(f"   Time points: {len(ds.time)}")
        
        # Check for common ERA5 variables
        print(f"\n🔍 Checking for common ERA5 variables:")
        
        var_checks = {
            'Potential Evaporation': ['pev', 'potential_evaporation', 'e'],
            'Soil Moisture': ['swvl1', 'volumetric_soil_water_layer_1', 'soil_moisture'],
            'Temperature': ['t2m', '2m_temperature', 'temperature'],
            'Precipitation': ['tp', 'total_precipitation', 'precipitation']
        }
        
        for var_name, possible_vars in var_checks.items():
            found = any(v in ds.data_vars for v in possible_vars)
            symbol = '✓' if found else '✗'
            print(f"   {symbol} {var_name}")
    
    ds.close()
    return True


def extract_and_validate(zip_path: Path, extract_dir: Path, 
                        output_name: str = None, remove_zip: bool = False) -> Path:
    """
    Extract ERA5 ZIP file and validate NetCDF contents.
    
    Parameters:
    -----------
    zip_path : Path
        Path to ZIP file
    extract_dir : Path
        Directory to extract files to
    output_name : str, optional
        Name for the final NetCDF file
    remove_zip : bool
        Remove ZIP file after successful extraction
        
    Returns:
    --------
    Path
        Path to validated NetCDF file, or None if failed
    """
    print("📦 Extracting ERA5 ZIP file...")
    print("="*70)
    
    if not zip_path.exists():
        print(f"✗ ZIP file not found: {zip_path}")
        return None
    
    # Ensure extract directory exists
    extract_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        # Open and inspect ZIP
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            files = zip_ref.namelist()
            print(f"📄 Files in ZIP archive:")
            for f in files:
                info = zip_ref.getinfo(f)
                size_mb = info.file_size / (1024*1024)
                print(f"   - {f} ({size_mb:.2f} MB)")
            
            # Extract all
            print(f"\n📂 Extracting to: {extract_dir}")
            zip_ref.extractall(extract_dir)
            print(f"   ✓ Extraction complete")
        
        # Find NetCDF files
        nc_files = list(extract_dir.glob("*.nc"))
        # Exclude the ZIP file if it has .nc extension
        nc_files = [f for f in nc_files if f != zip_path]
        
        if not nc_files:
            print("\n✗ No .nc files found after extraction!")
            print(f"   Files in directory: {list(extract_dir.glob('*'))}")
            return None
        
        print(f"\n🔍 Found NetCDF files:")
        for nc_file in nc_files:
            file_size = nc_file.stat().st_size / (1024*1024)
            print(f"   - {nc_file.name} ({file_size:.2f} MB)")
        
        # Use the first .nc file
        nc_file = nc_files[0]
        
        # Validate the NetCDF file
        if not validate_netcdf(nc_file):
            print("\n✗ NetCDF validation failed!")
            return None
        
        # Determine final path
        if output_name:
            final_path = extract_dir / output_name
        else:
            final_path = nc_file
        
        # Rename if needed
        if nc_file != final_path:
            print(f"\n📝 Renaming to: {final_path.name}")
            
            # Remove existing file if it exists
            if final_path.exists():
                final_path.unlink()
            
            nc_file.rename(final_path)
            print(f"   ✓ Renamed to {final_path.name}")
        
        # Remove ZIP file if requested
        if remove_zip and zip_path.exists() and zip_path != final_path:
            zip_path.unlink()
            print(f"\n🗑️ Removed ZIP file: {zip_path.name}")
        
        print(f"\n{'='*70}")
        print(f"✅ SUCCESS! NetCDF file is ready to use:")
        print(f"   📁 {final_path}")
        print(f"\n💡 Next steps:")
        print(f"   - Run data cube pipeline: python data_cube.py")
        print(f"   - Or verify again: python unzip_era5.py --validate {final_path}")
        print(f"{'='*70}")
        
        return final_path
        
    except zipfile.BadZipFile:
        print("\n✗ File is not a valid ZIP archive!")
        print("   The file might already be a NetCDF - try validating directly")
        return None
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return None


def main(zip_path=None, extract_dir=None, output_name=None, 
         validate_only=False, remove_zip=False):
    """
    Main function to extract and validate ERA5 data.
    
    Parameters:
    -----------
    zip_path : Path, optional
        Path to ZIP or NetCDF file
    extract_dir : Path, optional
        Directory to extract to
    output_name : str, optional
        Name for final NetCDF file
    validate_only : bool
        Only validate, don't extract
    remove_zip : bool
        Remove ZIP after extraction
    """
    global PROJECT_ROOT, DEFAULT_ERA5_DIR, DEFAULT_ZIP_FILE
    
    zip_path = Path(zip_path) if zip_path else DEFAULT_ZIP_FILE
    extract_dir = Path(extract_dir) if extract_dir else DEFAULT_ERA5_DIR
    output_name = output_name or DEFAULT_OUTPUT_NAME
    
    if validate_only:
        # Just validate the file
        print("🔍 Validating NetCDF file...")
        print("="*70)
        
        if not zip_path.exists():
            print(f"✗ File not found: {zip_path}")
            return False
        
        if validate_netcdf(zip_path, verbose=True):
            print("\n✅ File is valid!")
            return True
        else:
            print("\n✗ Validation failed!")
            return False
    
    else:
        # Extract and validate
        result = extract_and_validate(
            zip_path=zip_path,
            extract_dir=extract_dir,
            output_name=output_name,
            remove_zip=remove_zip
        )
        return result is not None


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Extract and validate ERA5 NetCDF files from ZIP archives'
    )
    
    parser.add_argument(
        '--project-root',
        type=str,
        help='Base project directory'
    )
    parser.add_argument(
        '--zip-file',
        type=str,
        help='Path to ZIP or NetCDF file (default: data/raw/era5_land/era5_complete_drivers.nc)'
    )
    parser.add_argument(
        '--extract-dir',
        type=str,
        help='Directory to extract to (default: data/raw/era5_land)'
    )
    parser.add_argument(
        '--output-name',
        type=str,
        help='Name for final NetCDF file (default: era5_complete_drivers.nc)'
    )
    parser.add_argument(
        '--validate',
        action='store_true',
        help='Only validate the file, do not extract'
    )
    parser.add_argument(
        '--remove-zip',
        action='store_true',
        help='Remove ZIP file after successful extraction'
    )
    
    args = parser.parse_args()
    
    # Update project root if provided
    if args.project_root:
        PROJECT_ROOT = Path(args.project_root)
        DEFAULT_ERA5_DIR = PROJECT_ROOT / "data" / "raw" / "era5_land"
        DEFAULT_ZIP_FILE = DEFAULT_ERA5_DIR / "era5_complete_drivers.nc"
    
    try:
        success = main(
            zip_path=args.zip_file,
            extract_dir=args.extract_dir,
            output_name=args.output_name,
            validate_only=args.validate,
            remove_zip=args.remove_zip
        )
        
        sys.exit(0 if success else 1)
        
    except KeyboardInterrupt:
        print("\n\n⏸️ Interrupted by user. Exiting...")
        sys.exit(130)
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
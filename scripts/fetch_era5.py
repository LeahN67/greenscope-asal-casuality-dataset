import cdsapi
import os
from pathlib import Path
import urllib3

# Suppress the "InsecureRequestWarning" to keep console clean
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ------------------------------------------------------------------
# PATH CONFIGURATION
# ------------------------------------------------------------------
# Use environment variable with fallback to current directory
PROJECT_ROOT = Path(os.getenv('GREENSCOPE_PROJECT_ROOT', Path.cwd()))

# Default paths
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "raw" / "era5_land"
DEFAULT_OUTPUT_FILE = "era5_complete_drivers.nc"

# Default spatial extent (East Africa/Kenya region)
DEFAULT_AREA = {
    'north': 5.5,
    'west': 33.5,
    'south': -5.0,
    'east': 42.0
}

# Available ERA5-Land variables
ERA5_VARIABLES = {
    'soil_moisture': 'volumetric_soil_water_layer_1',
    'potential_evaporation': 'potential_evaporation',
    'temperature': '2m_temperature',
    'precipitation': 'total_precipitation',
    'evaporation': 'evaporation',
    'runoff': 'runoff',
    'snow_depth': 'snow_depth',
    'soil_temperature': 'soil_temperature_level_1'
}


def get_cds_client(api_key=None, api_url=None, verify_ssl=False):
    """
    Initialize CDS API client.
    
    Parameters:
    -----------
    api_key : str, optional
        CDS API key (can also be set via CDS_API_KEY env var or ~/.cdsapirc)
    api_url : str, optional
        CDS API URL (default: https://cds.climate.copernicus.eu/api)
    verify_ssl : bool
        Whether to verify SSL certificates (default: False)
        
    Returns:
    --------
    cdsapi.Client
        Initialized CDS API client
    """
    # Check for API key in environment variable first
    api_key = api_key or os.getenv('CDS_API_KEY')
    api_url = api_url or "https://cds.climate.copernicus.eu/api"
    
    client_kwargs = {
        'url': api_url,
        'verify': verify_ssl
    }
    
    # Only add key if provided (otherwise will use ~/.cdsapirc)
    if api_key:
        client_kwargs['key'] = api_key
    
    try:
        return cdsapi.Client(**client_kwargs)
    except Exception as e:
        print(f"\n❌ Failed to initialize CDS API client: {e}")
        print("\n💡 To use the CDS API, you need to:")
        print("   1. Register at: https://cds.climate.copernicus.eu/")
        print("   2. Get your API key from: https://cds.climate.copernicus.eu/api-how-to")
        print("   3. Either:")
        print("      a. Set CDS_API_KEY environment variable")
        print("      b. Pass --api-key argument")
        print("      c. Create ~/.cdsapirc file with your credentials")
        raise


def download_era5_land(output_dir=None, output_filename=None, 
                       variables=None, start_year=2000, end_year=2025,
                       area=None, api_key=None, verify_ssl=False):
    """
    Download ERA5-Land reanalysis data from Copernicus CDS.
    
    Parameters:
    -----------
    output_dir : str or Path, optional
        Output directory
    output_filename : str, optional
        Output NetCDF filename
    variables : list, optional
        List of variables to download (default: ['potential_evaporation', 'soil_moisture'])
    start_year : int
        Start year for data (default: 2000)
    end_year : int
        End year for data (default: 2025)
    area : dict, optional
        Spatial extent {'north': lat, 'south': lat, 'east': lon, 'west': lon}
    api_key : str, optional
        CDS API key
    verify_ssl : bool
        Verify SSL certificates (default: False)
        
    Returns:
    --------
    bool
        True if download successful, False otherwise
    """
    # Setup paths
    output_dir = Path(output_dir) if output_dir else DEFAULT_OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / (output_filename or DEFAULT_OUTPUT_FILE)
    
    # Default variables
    if variables is None:
        variables = ['potential_evaporation', 'soil_moisture']
    
    # Map variable names to ERA5 codes
    era5_vars = []
    for var in variables:
        if var in ERA5_VARIABLES:
            era5_vars.append(ERA5_VARIABLES[var])
        else:
            # Assume it's already an ERA5 variable name
            era5_vars.append(var)
    
    # Use default area if not provided
    if area is None:
        area = DEFAULT_AREA
    
    print("="*60)
    print("ERA5-Land Data Downloader")
    print("="*60)
    print(f"\nVariables: {', '.join(variables)}")
    print(f"Period: {start_year}-{end_year}")
    print(f"Area: {area['north']}°N to {area['south']}°S, {area['west']}°E to {area['east']}°E")
    print(f"Output: {output_file.absolute()}")
    
    # Check if file exists
    if output_file.exists():
        file_size = output_file.stat().st_size / (1024**2)
        print(f"\n⚠ File already exists ({file_size:.2f} MB)")
        response = input("Overwrite? (y/n): ")
        if response.lower() != 'y':
            print("✓ Using existing file")
            return True
        output_file.unlink()
    
    print("\n🚀 Requesting ERA5-Land data from Copernicus CDS...")
    print("   Note: This may take several minutes to hours depending on the request size")
    print("   The CDS API will queue your request and process it when resources are available\n")
    
    try:
        # Initialize client
        client = get_cds_client(api_key=api_key, verify_ssl=verify_ssl)
        
        # Prepare request
        request = {
            'data_format': 'netcdf',
            'variable': era5_vars,
            'year': [str(y) for y in range(start_year, end_year + 1)],
            'month': [f"{m:02d}" for m in range(1, 13)],
            'time': '00:00',
            'area': [area['north'], area['west'], area['south'], area['east']],
            'product_type': 'monthly_averaged_reanalysis',
        }
        
        print("Request parameters:")
        for key, value in request.items():
            if key in ['year', 'month', 'variable']:
                print(f"   {key}: {len(value)} items")
            else:
                print(f"   {key}: {value}")
        print()
        
        # Submit request
        client.retrieve(
            'reanalysis-era5-land-monthly-means',
            request,
            str(output_file)
        )
        
        file_size = output_file.stat().st_size / (1024**2)
        print("\n" + "="*60)
        print("✅ Download successful!")
        print("="*60)
        print(f"📁 File: {output_file.name}")
        print(f"💾 Size: {file_size:.2f} MB")
        print(f"📍 Location: {output_file.absolute()}")
        print("="*60)
        
        return True
        
    except Exception as e:
        print(f"\n❌ Download failed: {e}")
        
        # Provide helpful error messages
        if "Unauthorized" in str(e) or "401" in str(e):
            print("\n💡 Authentication error. Please check:")
            print("   - Your CDS API key is correct")
            print("   - You've accepted the terms and conditions at:")
            print("     https://cds.climate.copernicus.eu/cdsapp/#!/terms/licence-to-use-copernicus-products")
        elif "Invalid request" in str(e):
            print("\n💡 Invalid request. Please check:")
            print("   - Variable names are correct")
            print("   - Date range is valid")
            print("   - Area coordinates are valid")
        
        return False


def list_available_variables():
    """List all available ERA5-Land variables."""
    print("\nAvailable ERA5-Land Variables:")
    print("="*60)
    for key, value in ERA5_VARIABLES.items():
        print(f"  {key:25} → {value}")
    print("="*60)
    print("\nUsage: Specify variables using the short names (left column)")
    print("Example: --variables soil_moisture temperature precipitation")


def main(project_root=None, output_dir=None, output_filename=None,
         variables=None, start_year=2000, end_year=2025,
         area=None, api_key=None, verify_ssl=False):
    """
    Main function to download ERA5-Land data.
    
    Parameters:
    -----------
    project_root : str or Path, optional
        Base project directory
    output_dir : str or Path, optional
        Output directory
    output_filename : str, optional
        Output filename
    variables : list, optional
        List of variables to download
    start_year : int
        Start year
    end_year : int
        End year
    area : dict, optional
        Spatial extent
    api_key : str, optional
        CDS API key
    verify_ssl : bool
        Verify SSL certificates
    """
    global PROJECT_ROOT, DEFAULT_OUTPUT_DIR
    
    # Update paths if project root is provided
    if project_root:
        PROJECT_ROOT = Path(project_root)
        DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "raw" / "era5_land"
    
    return download_era5_land(
        output_dir=output_dir,
        output_filename=output_filename,
        variables=variables,
        start_year=start_year,
        end_year=end_year,
        area=area,
        api_key=api_key,
        verify_ssl=verify_ssl
    )


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Download ERA5-Land reanalysis data from Copernicus CDS',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage (requires CDS API key)
  python fetch_era5.py --api-key YOUR_API_KEY
  
  # Download specific variables
  python fetch_era5.py --variables soil_moisture temperature precipitation
  
  # Custom date range
  python fetch_era5.py --start-year 2010 --end-year 2020
  
  # Custom spatial extent (Tanzania)
  python fetch_era5.py --north -1 --south -12 --west 29 --east 41
  
  # Use environment variable for API key
  export CDS_API_KEY=your_key_here
  python fetch_era5.py
        """
    )
    
    parser.add_argument(
        '--project-root',
        type=str,
        help='Base project directory (default: current directory or GREENSCOPE_PROJECT_ROOT env var)'
    )
    parser.add_argument(
        '--output-dir',
        type=str,
        help='Output directory'
    )
    parser.add_argument(
        '--output-filename',
        type=str,
        help='Output NetCDF filename'
    )
    parser.add_argument(
        '--variables',
        nargs='+',
        help='Variables to download (see --list-variables)'
    )
    parser.add_argument(
        '--start-year',
        type=int,
        default=2000,
        help='Start year (default: 2000)'
    )
    parser.add_argument(
        '--end-year',
        type=int,
        default=2025,
        help='End year (default: 2025)'
    )
    parser.add_argument(
        '--north',
        type=float,
        help='Northern latitude boundary'
    )
    parser.add_argument(
        '--south',
        type=float,
        help='Southern latitude boundary'
    )
    parser.add_argument(
        '--west',
        type=float,
        help='Western longitude boundary'
    )
    parser.add_argument(
        '--east',
        type=float,
        help='Eastern longitude boundary'
    )
    parser.add_argument(
        '--api-key',
        type=str,
        help='CDS API key (or set CDS_API_KEY environment variable)'
    )
    parser.add_argument(
        '--verify-ssl',
        action='store_true',
        help='Verify SSL certificates (default: False)'
    )
    parser.add_argument(
        '--list-variables',
        action='store_true',
        help='List available variables and exit'
    )
    
    args = parser.parse_args()
    
    # List variables if requested
    if args.list_variables:
        list_available_variables()
        exit(0)
    
    # Build area dict if coordinates provided
    area = None
    if any([args.north, args.south, args.west, args.east]):
        if not all([args.north, args.south, args.west, args.east]):
            parser.error("All area coordinates (--north, --south, --west, --east) must be provided together")
        area = {
            'north': args.north,
            'south': args.south,
            'west': args.west,
            'east': args.east
        }
    
    # Check for API key
    api_key = args.api_key or os.getenv('CDS_API_KEY')
    if not api_key and not Path.home().joinpath('.cdsapirc').exists():
        print("\n⚠️  WARNING: No CDS API key found!")
        print("   Please provide an API key using one of these methods:")
        print("   1. --api-key argument")
        print("   2. CDS_API_KEY environment variable")
        print("   3. ~/.cdsapirc configuration file")
        print("\n   Get your API key from: https://cds.climate.copernicus.eu/api-how-to\n")
    
    # Run download
    main(
        project_root=args.project_root,
        output_dir=args.output_dir,
        output_filename=args.output_filename,
        variables=args.variables,
        start_year=args.start_year,
        end_year=args.end_year,
        area=area,
        api_key=api_key,
        verify_ssl=args.verify_ssl
    )
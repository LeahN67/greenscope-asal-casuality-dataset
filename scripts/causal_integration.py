import xarray as xr
import pandas as pd
import numpy as np
from pathlib import Path
import os

# ------------------------------------------------------------------
# 1. SETUP PATHS - GENERALIZED
# ------------------------------------------------------------------
# Option 1: Use environment variable with fallback to current directory
BASE_PROJ = Path(os.getenv('GREENSCOPE_PROJECT_ROOT', Path.cwd()))

# Option 2: Use relative paths from script location
# BASE_PROJ = Path(__file__).parent.parent

# Define relative paths from base project directory
DATA_CUBE_PATH = BASE_PROJ / "data" / "processed" / "module0" / "module0_asal_datacube.nc"
ENSO_FILE = BASE_PROJ / "data" / "raw" / "enso" / "nino34.txt"
IOD_FILE = BASE_PROJ / "data" / "raw" / "iod" / "dmi_noaa.txt"
OUTPUT_FILE = BASE_PROJ / "data" / "processed" / "module0" / "greenscope_final_causal_cube.nc"

def parse_noaa_index(file_path, var_name):
    """Parses NOAA index files where col 0 is Year and 1-12 are Months"""
    # Read the file and identify numeric data rows
    with open(file_path, 'r') as f:
        lines = f.readlines()
    
    # Parse only lines that start with a 4-digit year
    data_rows = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        parts = stripped.split()
        # Check if first element is a 4-digit year
        if len(parts) > 0 and parts[0].isdigit() and len(parts[0]) == 4:
            try:
                year = int(parts[0])
                # Try to convert the monthly values to floats
                monthly_vals = [float(x) for x in parts[1:13]]
                data_rows.append([year] + monthly_vals)
            except (ValueError, IndexError):
                # Skip rows that can't be parsed
                continue
    
    if not data_rows:
        raise ValueError(f"No valid data found in {file_path}")
    
    # Convert to DataFrame
    df = pd.DataFrame(data_rows)
    years = df[0].values
    data_values = df.iloc[:, 1:13].values.flatten()
    
    # Ensure float type for NaN assignment
    data_values = data_values.astype(float)
    
    # Create time index starting from Jan of the first year
    time_idx = pd.date_range(start=f"{int(years[0])}-01-01", periods=len(data_values), freq='MS')
    
    # Replace missing values with NaN (NOAA uses -99.9 or -999.9)
    data_values[data_values < -90] = np.nan
    
    return xr.DataArray(data_values, coords=[('time', time_idx)], name=var_name)

# ------------------------------------------------------------------
# 2. THE LEFT JOIN LOGIC
# ------------------------------------------------------------------
def run_integration(data_cube_path=None, enso_file=None, iod_file=None, output_file=None):
    """
    Run the causal integration process.
    
    Parameters:
    -----------
    data_cube_path : str or Path, optional
        Path to the input data cube NetCDF file
    enso_file : str or Path, optional
        Path to ENSO NINO3.4 index file
    iod_file : str or Path, optional
        Path to IOD DMI index file
    output_file : str or Path, optional
        Path for the output NetCDF file
    """
    # Use provided paths or fall back to defaults
    data_cube_path = Path(data_cube_path) if data_cube_path else DATA_CUBE_PATH
    enso_file = Path(enso_file) if enso_file else ENSO_FILE
    iod_file = Path(iod_file) if iod_file else IOD_FILE
    output_file = Path(output_file) if output_file else OUTPUT_FILE
    
    # Validate input files exist
    for file_path, name in [(data_cube_path, "Data Cube"), 
                             (enso_file, "ENSO file"), 
                             (iod_file, "IOD file")]:
        if not file_path.exists():
            raise FileNotFoundError(f"{name} not found at: {file_path}")
    
    print(f"📂 Loading Local Data Cube from: {data_cube_path}")
    ds_cube = xr.open_dataset(data_cube_path)

    print(f"📊 Parsing Global Indices...")
    da_enso = parse_noaa_index(enso_file, "enso_nino34")
    da_iod = parse_noaa_index(iod_file, "iod_dmi")

    # Align ENSO/IOD to the exact time range of your Data Cube
    print(f"🔗 Aligning and Joining (Left Join)...")
    da_enso_aligned = da_enso.sel(time=ds_cube.time, method='nearest')
    da_iod_aligned = da_iod.sel(time=ds_cube.time, method='nearest')

    # Merge: This broadcasts the 1D index across the 3D (Lat/Lon/Time) Cube
    final_ds = xr.merge([ds_cube, da_enso_aligned, da_iod_aligned], compat='override')

    # ------------------------------------------------------------------
    # 3. SAVE FINAL OUTPUT
    # ------------------------------------------------------------------
    # Ensure output directory exists
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    final_ds.to_netcdf(output_file)
    print("\n" + "="*50)
    print("✅ INTEGRATION SUCCESSFUL")
    print(f"💾 Saved to: {output_file}")
    print(f"📋 Variables: {list(final_ds.data_vars)}")
    print("="*50)

if __name__ == "__main__":
    # Example: You can now pass custom paths via command line arguments
    import argparse
    
    parser = argparse.ArgumentParser(description='Integrate climate indices with data cube')
    parser.add_argument('--base-dir', type=str, help='Base project directory')
    parser.add_argument('--data-cube', type=str, help='Path to data cube file')
    parser.add_argument('--enso', type=str, help='Path to ENSO index file')
    parser.add_argument('--iod', type=str, help='Path to IOD index file')
    parser.add_argument('--output', type=str, help='Path to output file')
    
    args = parser.parse_args()
    
    # Update base directory if provided
    if args.base_dir:
        BASE_PROJ = Path(args.base_dir)
        # Recalculate default paths
        DATA_CUBE_PATH = BASE_PROJ / "data" / "processed" / "module0" / "module0_asal_datacube.nc"
        ENSO_FILE = BASE_PROJ / "data" / "raw" / "enso" / "nino34.txt"
        IOD_FILE = BASE_PROJ / "data" / "raw" / "iod" / "dmi_noaa.txt"
        OUTPUT_FILE = BASE_PROJ / "data" / "processed" / "module0" / "greenscope_final_causal_cube.nc"
    
    run_integration(
        data_cube_path=args.data_cube,
        enso_file=args.enso,
        iod_file=args.iod,
        output_file=args.output
    )
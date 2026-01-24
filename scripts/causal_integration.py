import xarray as xr
import pandas as pd
import numpy as np
from pathlib import Path

# ------------------------------------------------------------------
# 1. SETUP PATHS
# ------------------------------------------------------------------
BASE_PROJ = Path(r"C:\Users\HP\Documents\PhD_papers\StartUp\GreenScope_Analytics\Asal")
DATA_CUBE_PATH = BASE_PROJ / "data" / "processed" / "module0" / "module0_asal_datacube.nc"
ENSO_FILE = BASE_PROJ / "data" / "raw" / "enso" / "nino34.txt"
IOD_FILE  = BASE_PROJ / "data" / "raw" / "iod" / "dmi_noaa.txt"
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
def run_integration():
    print(f"📂 Loading Local Data Cube...")
    ds_cube = xr.open_dataset(DATA_CUBE_PATH)

    print(f"📊 Parsing Global Indices...")
    da_enso = parse_noaa_index(ENSO_FILE, "enso_nino34")
    da_iod  = parse_noaa_index(IOD_FILE, "iod_dmi")

    # Align ENSO/IOD to the exact time range of your Data Cube
    print(f"🔗 Aligning and Joining (Left Join)...")
    da_enso_aligned = da_enso.sel(time=ds_cube.time, method='nearest')
    da_iod_aligned  = da_iod.sel(time=ds_cube.time, method='nearest')

    # Merge: This broadcasts the 1D index across the 3D (Lat/Lon/Time) Cube
    final_ds = xr.merge([ds_cube, da_enso_aligned, da_iod_aligned], compat='override')

    # ------------------------------------------------------------------
    # 3. SAVE FINAL OUTPUT
    # ------------------------------------------------------------------
    final_ds.to_netcdf(OUTPUT_FILE)
    print("\n" + "="*50)
    print("✅ INTEGRATION SUCCESSFUL")
    print(f"💾 Saved to: {OUTPUT_FILE}")
    print(f"📋 Variables: {list(final_ds.data_vars)}")
    print("="*50)

if __name__ == "__main__":
    run_integration()
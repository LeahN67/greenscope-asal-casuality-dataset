import cdsapi
import os
import urllib3

# Suppress the "InsecureRequestWarning" to keep your console clean
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Ensure the directory exists
os.makedirs('data/raw/era5_land', exist_ok=True)

# Initialize the client with verify=False
c = cdsapi.Client(
    url="https://cds.climate.copernicus.eu/api",
    key="input your key",
    verify=False  # This bypasses the SSL certificate check
)

print("🚀 Requesting ERA5-Land (Soil Moisture + Potential Evaporation)...")

try:
    c.retrieve(
        'reanalysis-era5-land-monthly-means',
        {
            'data_format': 'netcdf',  # Changed from 'format' to 'data_format'
            'variable': [
                'potential_evaporation', 
                'volumetric_soil_water_layer_1',
            ],
            'year': [str(y) for y in range(2000, 2026)],
            'month': [f"{m:02d}" for m in range(1, 13)],
            'time': '00:00',  # Added time parameter (required for monthly means)
            'area': [5.5, 33.5, -5.0, 42.0],  # North, West, South, East
            'product_type': 'monthly_averaged_reanalysis',  # Changed product type
        },
        'data/raw/era5_land/era5_complete_drivers.nc'
    )
    print("✅ Download successful! File saved at: data/raw/era5_land/era5_complete_drivers.nc")
except Exception as e:
    print(f"❌ An error occurred: {e}")
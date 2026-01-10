"""Extract ERA5 ZIP file and validate NetCDF"""
import zipfile
from pathlib import Path
import xarray as xr

zip_path = Path('data/raw/era5_land/era5_complete_drivers.nc')
extract_dir = Path('data/raw/era5_land')

print("📦 Extracting ERA5 ZIP file...")
print("="*70)

if not zip_path.exists():
    print("❌ ZIP file not found!")
    exit(1)

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
    
    # Find the .nc file
    nc_files = list(extract_dir.glob("*.nc"))
    nc_files = [f for f in nc_files if f.name != zip_path.name]  # Exclude the ZIP
    
    if not nc_files:
        print("\n❌ No .nc files found after extraction!")
        print(f"   Files in directory: {list(extract_dir.glob('*'))}")
        exit(1)
    
    print(f"\n🔍 Found NetCDF files:")
    for nc_file in nc_files:
        print(f"   - {nc_file.name}")
    
    # Use the first .nc file (or the one that looks right)
    nc_file = nc_files[0]
    final_path = extract_dir / "era5_complete_drivers.nc"
    
    # Validate the NetCDF file
    print(f"\n✅ Validating: {nc_file.name}")
    try:
        ds = xr.open_dataset(nc_file, engine='h5netcdf')
        print(f"   ✓ Successfully opened with h5netcdf!")
    except:
        try:
            ds = xr.open_dataset(nc_file, engine='netcdf4')
            print(f"   ✓ Successfully opened with netcdf4!")
        except Exception as e:
            print(f"   ❌ Failed to open: {e}")
            exit(1)
    
    print(f"\n📊 Dataset Information:")
    print(f"   Variables: {list(ds.data_vars)}")
    print(f"   Dimensions: {dict(ds.dims)}")
    print(f"   Time range: {ds.time.min().values} to {ds.time.max().values}")
    print(f"   Time points: {len(ds.time)}")
    
    # Check variable names
    print(f"\n🔍 Checking for required variables:")
    has_pev = any(v in ds.data_vars for v in ['pev', 'potential_evaporation', 'e'])
    has_sm = any(v in ds.data_vars for v in ['swvl1', 'volumetric_soil_water_layer_1', 'soil_moisture'])
    
    print(f"   Potential Evaporation: {'✓' if has_pev else '✗'}")
    print(f"   Soil Moisture: {'✓' if has_sm else '✗'}")
    
    ds.close()
    
    # Rename if needed
    if nc_file != final_path:
        print(f"\n📝 Renaming to: {final_path.name}")
        # Remove ZIP file first
        if zip_path.exists() and zip_path != nc_file:
            zip_path.unlink()
            print(f"   ✓ Removed ZIP file")
        
        # Rename NC file
        nc_file.rename(final_path)
        print(f"   ✓ Renamed to {final_path.name}")
    
    print(f"\n✅ SUCCESS! NetCDF file is ready to use:")
    print(f"   {final_path}")
    print(f"\n   You can now run your pipeline:")
    print(f"   python -m scripts.data_cube")
    
except zipfile.BadZipFile:
    print("❌ File is not a valid ZIP archive!")
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
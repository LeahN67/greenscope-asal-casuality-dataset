"""
GreenScope – Module 0
Unified ASAL Data Cube (MEMORY-EFFICIENT FOR LARGE FILES)
"""

# ------------------------------------------------------------------
# PROJ SAFETY
# ------------------------------------------------------------------
import pyproj, os
os.environ["PROJ_LIB"] = pyproj.datadir.get_data_dir()

# ------------------------------------------------------------------
# Imports
# ------------------------------------------------------------------
import xarray as xr
import numpy as np
import geopandas as gpd
from pathlib import Path
import rioxarray
from dask.diagnostics import ProgressBar
import warnings
warnings.filterwarnings('ignore')

# ------------------------------------------------------------------
class Module0Pipeline:
    def __init__(self, chirps_path, era5_path, modis_dir, boundary_path, output_dir):
        self.chirps = Path(chirps_path)
        self.era5 = Path(era5_path)
        self.modis = Path(modis_dir)
        self.boundary = Path(boundary_path)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    # --------------------------------------------------------------
    def _get_bbox(self, gdf):
        """Get bounding box for spatial subsetting"""
        bounds = gdf.total_bounds  # [minx, miny, maxx, maxy]
        return {
            'lon_min': bounds[0],
            'lon_max': bounds[2],
            'lat_min': bounds[1],
            'lat_max': bounds[3]
        }

    # --------------------------------------------------------------
    def _spatial_subset(self, ds, bbox):
        """Subset data spatially using bounding box (MEMORY EFFICIENT)"""
        # Identify coordinate names
        lat_name = 'latitude' if 'latitude' in ds.coords else 'lat'
        lon_name = 'longitude' if 'longitude' in ds.coords else 'lon'
        
        # Check if latitude is ascending or descending
        lat_vals = ds[lat_name].values
        lat_ascending = lat_vals[0] < lat_vals[-1]
        
        # Set slice direction based on coordinate order
        if lat_ascending:
            lat_slice = slice(bbox['lat_min'], bbox['lat_max'])
        else:
            lat_slice = slice(bbox['lat_max'], bbox['lat_min'])
        
        # Longitude is typically ascending
        lon_slice = slice(bbox['lon_min'], bbox['lon_max'])
        
        # Subset using .sel() which is lazy
        ds = ds.sel(**{lat_name: lat_slice, lon_name: lon_slice})
        return ds

    # --------------------------------------------------------------
    def run(self):
        print("\n🚀 MODULE 0 – ASAL DATA CUBE")
        print("=" * 60)

        # Load boundary and get bbox
        gdf = gpd.read_file(self.boundary).to_crs("EPSG:4326")
        bbox = self._get_bbox(gdf)
        print(f"📍 Study area: {bbox['lat_min']:.2f}°-{bbox['lat_max']:.2f}°N, "
              f"{bbox['lon_min']:.2f}°-{bbox['lon_max']:.2f}°E")

        # ------------------- CHIRPS -------------------
        print("\n🌧️ Loading CHIRPS (chunked)...")
        ds_p = xr.open_dataset(self.chirps, chunks={'time': 12, 'latitude': 200, 'longitude': 200})
        pvar = next(v for v in ds_p.data_vars if "precip" in v.lower())
        ds_p = ds_p[[pvar]].rename({pvar: "precipitation"})
        
        # Spatial subset (lazy operation)
        ds_p = self._spatial_subset(ds_p, bbox)
        print(f"   Subset shape: {dict(ds_p.sizes)}")

        # ------------------- ERA5 ---------------------
        print("\n💧 Loading ERA5 (chunked)...")
        ds_e = xr.open_dataset(self.era5, chunks={'time': 12})
        
        # Safe renaming
        rename_map = {}
        if "valid_time" in ds_e.coords or "valid_time" in ds_e.dims:
            rename_map["valid_time"] = "time"
        if "pev" in ds_e.data_vars:
            rename_map["pev"] = "potential_evaporation"
        if "swvl1" in ds_e.data_vars:
            rename_map["swvl1"] = "soil_moisture"
        
        ds_e = ds_e.rename(rename_map)
        
        # Keep only what we need
        keep_vars = [v for v in ["potential_evaporation", "soil_moisture"] if v in ds_e.data_vars]
        ds_e = ds_e[keep_vars]
        
        # Spatial subset
        ds_e = self._spatial_subset(ds_e, bbox)
        print(f"   Subset shape: {dict(ds_e.sizes)}")

        # ------------------- MODIS --------------------
        print("\n🛰️ Loading MODIS NDVI (chunked)...")
        files = sorted(self.modis.glob("*.nc"))
        ds_n = xr.open_mfdataset(files, combine="by_coords", chunks={'time': 12})
        
        ndvi_var = next(v for v in ds_n.data_vars if "ndvi" in v.lower())
        ds_n = ds_n[[ndvi_var]].rename({ndvi_var: "ndvi"})
        
        # Spatial subset
        ds_n = self._spatial_subset(ds_n, bbox)
        
        print("   ⏳ Resampling to monthly...")
        ds_n = ds_n.resample(time="1MS").mean()
        print(f"   Subset shape: {dict(ds_n.sizes)}")

        # ------------------- STANDARDIZE COORDINATES --------------------
        print("\n📐 Standardizing coordinate names...")
        
        def rename_coords(dataset):
            """Ensure consistent lat/lon naming"""
            mapping = {}
            if 'lat' in dataset.coords: 
                mapping['lat'] = 'latitude'
            if 'lon' in dataset.coords: 
                mapping['lon'] = 'longitude'
            return dataset.rename(mapping) if mapping else dataset
        
        ds_p = rename_coords(ds_p)
        ds_e = rename_coords(ds_e)
        ds_n = rename_coords(ds_n)

        # Get reference grid from CHIRPS (highest spatial resolution)
        target_lat = ds_p.latitude
        target_lon = ds_p.longitude

        # ------------------- ALIGN TO CHIRPS GRID --------------------
        print("🔗 Aligning to CHIRPS grid (bilinear interpolation)...")
        
        # Interpolate ERA5 to CHIRPS grid (linear for continuous variables)
        ds_e = ds_e.interp(latitude=target_lat, longitude=target_lon, method="linear")
        
        # Interpolate MODIS to CHIRPS grid (linear for NDVI continuity)
        ds_n = ds_n.interp(latitude=target_lat, longitude=target_lon, method="linear")

        # ------------------- MERGE --------------------
        print("🔗 Merging datasets...")
        ds = xr.merge([ds_p, ds_e, ds_n], join="inner")
        print(f"   Merged shape: {dict(ds.sizes)}")

        # ------------------- CLEAN DATA -------------------
        print("\n🧹 Cleaning data...")
        ds["precipitation"] = ds["precipitation"].clip(min=0)
        ds["potential_evaporation"] = np.abs(ds["potential_evaporation"])
        ds["ndvi"] = ds["ndvi"].clip(-0.2, 1.0)

        # Convert to float32
        for v in ds.data_vars:
            ds[v] = ds[v].astype("float32")

        # ------------------- RECHUNK FOR EXPORT -------------------
        t_size = ds.sizes["time"]
        y_size = ds.sizes["latitude"]
        x_size = ds.sizes["longitude"]

        # Optimal chunks for writing
        chunk_t = min(12, t_size)
        chunk_y = min(100, y_size)
        chunk_x = min(100, x_size)
        
        print(f"📦 Rechunking for export: time={chunk_t}, lat={chunk_y}, lon={chunk_x}")
        ds = ds.chunk({"time": chunk_t, "latitude": chunk_y, "longitude": chunk_x})

        # ------------------- ENCODING -------------------
        encoding = {}
        for v in ds.data_vars:
            encoding[v] = {
                "zlib": True,
                "complevel": 4,
                "dtype": "float32",
                "chunksizes": (chunk_t, chunk_y, chunk_x),
                "_FillValue": -9999.0
            }

        for coord in ["latitude", "longitude", "time"]:
            encoding[coord] = {"_FillValue": None}

        # ------------------- EXPORT -------------------
        out = self.output_dir / "module0_asal_datacube.nc"
        print(f"\n💾 Writing to: {out}")
        print("   ⚠️  This will take several minutes for large datasets...")
        
        with ProgressBar():
            ds.to_netcdf(out, encoding=encoding, engine="netcdf4")

        # ------------------- SUMMARY -------------------
        file_size = out.stat().st_size / (1024**2)
        print("\n" + "="*60)
        print("✅ MODULE 0 COMPLETE - CAUSAL DATA CUBE READY")
        print("="*60)
        print(f"📊 Dimensions: {dict(ds.sizes)}")
        print(f"📁 Variables (Causal Registry):")
        print(f"   • precipitation (Stressor)")
        print(f"   • potential_evaporation (Stressor)")
        print(f"   • soil_moisture (Mediator)")
        print(f"   • ndvi (Response)")
        print(f"📅 Time range: {str(ds.time.min().values)[:10]} to {str(ds.time.max().values)[:10]}")
        print(f"🌍 Spatial extent: {float(ds.latitude.min()):.2f}° to {float(ds.latitude.max()):.2f}°N")
        print(f"                   {float(ds.longitude.min()):.2f}° to {float(ds.longitude.max()):.2f}°E")
        print(f"🔬 Interpolation: Bilinear (suitable for continuous variables)")
        print(f"💾 File size: {file_size:.1f} MB")
        print(f"📍 Saved to: {out}")
        print(f"\n🎯 Ready for Module 1: Causal Discovery")
        print("="*60)

# ------------------------------------------------------------------
if __name__ == "__main__":
    Module0Pipeline(
        chirps_path="data/raw/chirps/monthly/chirps-v2.0.monthly.nc",
        era5_path="data/raw/era5_land/data_stream-moda.nc",
        modis_dir="data/raw/modis_ndvi/ndvi",
        boundary_path="data/raw/boundaries/asal_boundary.geojson",
        output_dir="data/processed/module0"
    ).run()
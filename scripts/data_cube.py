"""
GreenScope – Module 0
Unified ASAL Data Cube (MEMORY-EFFICIENT FOR LARGE FILES)
"""

# ------------------------------------------------------------------
# PROJ SAFETY
# ------------------------------------------------------------------
import pyproj
import os
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
# PATH CONFIGURATION
# ------------------------------------------------------------------
# Use environment variable with fallback to current directory
PROJECT_ROOT = Path(os.getenv('GREENSCOPE_PROJECT_ROOT', Path.cwd()))

# Default paths (can be overridden)
DEFAULT_CHIRPS = PROJECT_ROOT / "data" / "raw" / "chirps" / "monthly" / "chirps-v2.0.monthly.nc"
DEFAULT_ERA5 = PROJECT_ROOT / "data" / "raw" / "era5_land" / "data_stream-moda.nc"
DEFAULT_MODIS = PROJECT_ROOT / "data" / "raw" / "modis_ndvi" / "ndvi"
DEFAULT_BOUNDARY = PROJECT_ROOT / "data" / "raw" / "boundaries" / "asal_boundary.geojson"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "processed" / "module0"


# ------------------------------------------------------------------
class Module0Pipeline:
    """
    Data cube creation pipeline for climate and vegetation data
    
    Parameters:
    -----------
    chirps_path : str or Path
        Path to CHIRPS precipitation NetCDF file
    era5_path : str or Path
        Path to ERA5 land data NetCDF file
    modis_dir : str or Path
        Directory containing MODIS NDVI NetCDF files
    boundary_path : str or Path
        Path to study area boundary GeoJSON file
    output_dir : str or Path
        Directory for output data cube
    output_filename : str, optional
        Name of output NetCDF file (default: module0_asal_datacube.nc)
    chunk_size : dict, optional
        Custom chunk sizes for processing
    """
    
    def __init__(self, chirps_path, era5_path, modis_dir, boundary_path, output_dir,
                 output_filename="module0_asal_datacube.nc", chunk_size=None):
        self.chirps = Path(chirps_path)
        self.era5 = Path(era5_path)
        self.modis = Path(modis_dir)
        self.boundary = Path(boundary_path)
        self.output_dir = Path(output_dir)
        self.output_filename = output_filename
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Default chunk sizes (can be customized)
        self.chunk_size = chunk_size or {
            'time': 12,
            'latitude': 200,
            'longitude': 200
        }
        
        # Validate input files
        self._validate_inputs()

    # --------------------------------------------------------------
    def _validate_inputs(self):
        """Validate that all input files exist"""
        if not self.chirps.exists():
            raise FileNotFoundError(f"CHIRPS file not found: {self.chirps}")
        if not self.era5.exists():
            raise FileNotFoundError(f"ERA5 file not found: {self.era5}")
        if not self.modis.exists():
            raise FileNotFoundError(f"MODIS directory not found: {self.modis}")
        if not self.boundary.exists():
            raise FileNotFoundError(f"Boundary file not found: {self.boundary}")
    
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
    def _rename_coords(self, dataset):
        """Ensure consistent lat/lon naming"""
        mapping = {}
        if 'lat' in dataset.coords: 
            mapping['lat'] = 'latitude'
        if 'lon' in dataset.coords: 
            mapping['lon'] = 'longitude'
        return dataset.rename(mapping) if mapping else dataset

    # --------------------------------------------------------------
    def load_precipitation(self, bbox):
        """Load and process precipitation data"""
        print("\n🌧️ Loading CHIRPS (chunked)...")
        ds_p = xr.open_dataset(
            self.chirps, 
            chunks={
                'time': self.chunk_size['time'], 
                'latitude': self.chunk_size['latitude'], 
                'longitude': self.chunk_size['longitude']
            }
        )
        
        # Find precipitation variable (flexible naming)
        pvar = next(v for v in ds_p.data_vars if "precip" in v.lower())
        ds_p = ds_p[[pvar]].rename({pvar: "precipitation"})
        
        # Spatial subset (lazy operation)
        ds_p = self._spatial_subset(ds_p, bbox)
        print(f"   Subset shape: {dict(ds_p.sizes)}")
        
        return ds_p

    # --------------------------------------------------------------
    def load_era5(self, bbox):
        """Load and process ERA5 land data"""
        print("\n💧 Loading ERA5 (chunked)...")
        ds_e = xr.open_dataset(self.era5, chunks={'time': self.chunk_size['time']})
        
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
        
        return ds_e

    # --------------------------------------------------------------
    def load_ndvi(self, bbox):
        """Load and process MODIS NDVI data"""
        print("\n🛰️ Loading MODIS NDVI (chunked)...")
        files = sorted(self.modis.glob("*.nc"))
        
        if not files:
            raise FileNotFoundError(f"No NetCDF files found in {self.modis}")
        
        ds_n = xr.open_mfdataset(files, combine="by_coords", chunks={'time': self.chunk_size['time']})
        
        # Find NDVI variable (flexible naming)
        ndvi_var = next(v for v in ds_n.data_vars if "ndvi" in v.lower())
        ds_n = ds_n[[ndvi_var]].rename({ndvi_var: "ndvi"})
        
        # Spatial subset
        ds_n = self._spatial_subset(ds_n, bbox)
        
        print("   ⏳ Resampling to monthly...")
        ds_n = ds_n.resample(time="1MS").mean()
        print(f"   Subset shape: {dict(ds_n.sizes)}")
        
        return ds_n

    # --------------------------------------------------------------
    def run(self):
        """Execute the complete data cube creation pipeline"""
        print("\n🚀 MODULE 0 – ASAL DATA CUBE")
        print("=" * 60)

        # Load boundary and get bbox
        gdf = gpd.read_file(self.boundary).to_crs("EPSG:4326")
        bbox = self._get_bbox(gdf)
        print(f"📍 Study area: {bbox['lat_min']:.2f}°-{bbox['lat_max']:.2f}°N, "
              f"{bbox['lon_min']:.2f}°-{bbox['lon_max']:.2f}°E")

        # Load datasets
        ds_p = self.load_precipitation(bbox)
        ds_e = self.load_era5(bbox)
        ds_n = self.load_ndvi(bbox)

        # Standardize coordinates
        print("\n🔄 Standardizing coordinate names...")
        ds_p = self._rename_coords(ds_p)
        ds_e = self._rename_coords(ds_e)
        ds_n = self._rename_coords(ds_n)

        # Get reference grid from CHIRPS (highest spatial resolution)
        target_lat = ds_p.latitude
        target_lon = ds_p.longitude

        # Align to CHIRPS grid
        print("🔗 Aligning to CHIRPS grid (bilinear interpolation)...")
        ds_e = ds_e.interp(latitude=target_lat, longitude=target_lon, method="linear")
        ds_n = ds_n.interp(latitude=target_lat, longitude=target_lon, method="linear")

        # Merge datasets
        print("🔗 Merging datasets...")
        ds = xr.merge([ds_p, ds_e, ds_n], join="inner")
        print(f"   Merged shape: {dict(ds.sizes)}")

        # Clean data
        print("\n🧹 Cleaning data...")
        ds["precipitation"] = ds["precipitation"].clip(min=0)
        ds["potential_evaporation"] = np.abs(ds["potential_evaporation"])
        ds["ndvi"] = ds["ndvi"].clip(-0.2, 1.0)

        # Convert to float32
        for v in ds.data_vars:
            ds[v] = ds[v].astype("float32")

        # Rechunk for export
        t_size = ds.sizes["time"]
        y_size = ds.sizes["latitude"]
        x_size = ds.sizes["longitude"]

        chunk_t = min(12, t_size)
        chunk_y = min(100, y_size)
        chunk_x = min(100, x_size)
        
        print(f"📦 Rechunking for export: time={chunk_t}, lat={chunk_y}, lon={chunk_x}")
        ds = ds.chunk({"time": chunk_t, "latitude": chunk_y, "longitude": chunk_x})

        # Encoding
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

        # Export
        out = self.output_dir / self.output_filename
        print(f"\n💾 Writing to: {out}")
        print("   ⚠️  This will take several minutes for large datasets...")
        
        with ProgressBar():
            ds.to_netcdf(out, encoding=encoding, engine="netcdf4")

        # Summary
        file_size = out.stat().st_size / (1024**2)
        print("\n" + "="*60)
        print("✅ MODULE 0 COMPLETE - CAUSAL DATA CUBE READY")
        print("="*60)
        print(f"📊 Dimensions: {dict(ds.sizes)}")
        print(f"📋 Variables (Causal Registry):")
        print(f"   • precipitation (Stressor)")
        print(f"   • potential_evaporation (Stressor)")
        print(f"   • soil_moisture (Mediator)")
        print(f"   • ndvi (Response)")
        print(f"📅 Time range: {str(ds.time.min().values)[:10]} to {str(ds.time.max().values)[:10]}")
        print(f"🌍 Spatial extent: {float(ds.latitude.min()):.2f}° to {float(ds.latitude.max()):.2f}°N")
        print(f"                   {float(ds.longitude.min()):.2f}° to {float(ds.longitude.max()):.2f}°E")
        print(f"🔬 Interpolation: Bilinear (suitable for continuous variables)")
        print(f"💾 File size: {file_size:.1f} MB")
        print(f"📁 Saved to: {out}")
        print(f"\n🎯 Ready for Module 1: Causal Discovery")
        print("="*60)
        
        return ds


# ------------------------------------------------------------------
def create_data_cube(chirps_path=None, era5_path=None, modis_dir=None, 
                     boundary_path=None, output_dir=None, **kwargs):
    """
    Convenience function to create data cube
    
    Parameters:
    -----------
    chirps_path : str or Path, optional
        Path to CHIRPS precipitation file
    era5_path : str or Path, optional
        Path to ERA5 land data file
    modis_dir : str or Path, optional
        Directory containing MODIS NDVI files
    boundary_path : str or Path, optional
        Path to boundary GeoJSON file
    output_dir : str or Path, optional
        Output directory
    **kwargs : additional arguments
        Additional arguments to pass to Module0Pipeline
    """
    # Use defaults if not provided
    chirps_path = chirps_path or DEFAULT_CHIRPS
    era5_path = era5_path or DEFAULT_ERA5
    modis_dir = modis_dir or DEFAULT_MODIS
    boundary_path = boundary_path or DEFAULT_BOUNDARY
    output_dir = output_dir or DEFAULT_OUTPUT
    
    pipeline = Module0Pipeline(
        chirps_path=chirps_path,
        era5_path=era5_path,
        modis_dir=modis_dir,
        boundary_path=boundary_path,
        output_dir=output_dir,
        **kwargs
    )
    
    return pipeline.run()


# ------------------------------------------------------------------
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Create unified climate and vegetation data cube'
    )
    parser.add_argument(
        '--project-root',
        type=str,
        help='Base project directory (default: current directory or GREENSCOPE_PROJECT_ROOT env var)'
    )
    parser.add_argument(
        '--chirps',
        type=str,
        help='Path to CHIRPS precipitation NetCDF file'
    )
    parser.add_argument(
        '--era5',
        type=str,
        help='Path to ERA5 land data NetCDF file'
    )
    parser.add_argument(
        '--modis',
        type=str,
        help='Directory containing MODIS NDVI NetCDF files'
    )
    parser.add_argument(
        '--boundary',
        type=str,
        help='Path to study area boundary GeoJSON file'
    )
    parser.add_argument(
        '--output-dir',
        type=str,
        help='Output directory for data cube'
    )
    parser.add_argument(
        '--output-filename',
        type=str,
        default='module0_asal_datacube.nc',
        help='Output NetCDF filename (default: module0_asal_datacube.nc)'
    )
    parser.add_argument(
        '--chunk-time',
        type=int,
        default=12,
        help='Chunk size for time dimension (default: 12)'
    )
    parser.add_argument(
        '--chunk-lat',
        type=int,
        default=200,
        help='Chunk size for latitude dimension (default: 200)'
    )
    parser.add_argument(
        '--chunk-lon',
        type=int,
        default=200,
        help='Chunk size for longitude dimension (default: 200)'
    )
    
    args = parser.parse_args()
    
    # Update project root if provided
    if args.project_root:
        global PROJECT_ROOT, DEFAULT_CHIRPS, DEFAULT_ERA5, DEFAULT_MODIS
        global DEFAULT_BOUNDARY, DEFAULT_OUTPUT
        
        PROJECT_ROOT = Path(args.project_root)
        DEFAULT_CHIRPS = PROJECT_ROOT / "data" / "raw" / "chirps" / "monthly" / "chirps-v2.0.monthly.nc"
        DEFAULT_ERA5 = PROJECT_ROOT / "data" / "raw" / "era5_land" / "data_stream-moda.nc"
        DEFAULT_MODIS = PROJECT_ROOT / "data" / "raw" / "modis_ndvi" / "ndvi"
        DEFAULT_BOUNDARY = PROJECT_ROOT / "data" / "raw" / "boundaries" / "asal_boundary.geojson"
        DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "processed" / "module0"
    
    # Custom chunk sizes
    chunk_size = {
        'time': args.chunk_time,
        'latitude': args.chunk_lat,
        'longitude': args.chunk_lon
    }
    
    # Run pipeline
    create_data_cube(
        chirps_path=args.chirps,
        era5_path=args.era5,
        modis_dir=args.modis,
        boundary_path=args.boundary,
        output_dir=args.output_dir,
        output_filename=args.output_filename,
        chunk_size=chunk_size
    )
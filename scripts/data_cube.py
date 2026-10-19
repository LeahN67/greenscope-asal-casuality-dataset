"""
Step 7. Build the gridded ASAL cube (Module 0): CHIRPS precipitation, ERA5-Land potential
evaporation and soil moisture, and MODIS NDVI on the CHIRPS 0.05 degree grid, monthly.

    python scripts/data_cube.py
    python scripts/data_cube.py --modis data/raw/modis_ndvi/ndvi_fixed --hash-inputs

What it does, in order:
  1. subsets every input to the bounding box of the ASAL boundary (no polygon mask)
  2. NDVI: scales stored values by 0.0001, masks values outside -2000..10000, monthly mean
  3. interpolates ERA5-Land and NDVI linearly onto the CHIRPS grid
  4. keeps months present in every input (inner join on time)
  5. floors precipitation at 0; reverses the ERA5-Land sign of potential evaporation and
     converts it from metres to mm per day
  6. writes variable units, causal roles and provenance into the NetCDF attributes

Output: data/processed/module0/module0_asal_datacube.nc
"""
import os

import pyproj

os.environ.setdefault("PROJ_LIB", pyproj.datadir.get_data_dir())

import argparse
import hashlib
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import numpy as np
import xarray as xr
from dask.diagnostics import ProgressBar

from gs_common import (BOUNDARY, CAUSAL_REGISTRY, CHIRPS, CUBE, ERA5, ERA5_LEGACY, MODIS_NC,
                       sha256_file, tag_causal_role)


def scale_and_mask_ndvi(da):
    """
    MODIS NDVI is stored as integers scaled by 0.0001, valid range -2000..10000. The GeoTIFFs carry
    no scale factor, so it is applied here. Out-of-range values are masked, not clipped.
    Returns the scaled array and the counts of in-range and out-of-range cells.
    """
    in_range = (da >= -2000) & (da <= 10000)
    out_of_range = da.notnull() & ~in_range
    n_valid = int(in_range.sum().compute())
    n_bad = int(out_of_range.sum().compute())
    scaled = da.where(in_range) * 0.0001
    scaled.attrs = {"units": "1", "long_name": "MODIS NDVI (stored value x 0.0001)"}
    return scaled, n_valid, n_bad


def describe_input(path, hash_it=False):
    p = Path(path)
    text = f"{p.name} ({p.stat().st_size} bytes)"
    return text + (f" sha256={sha256_file(p)}" if hash_it else "")


def find_era5(path):
    if path:
        return Path(path)
    return ERA5 if ERA5.exists() or not ERA5_LEGACY.exists() else ERA5_LEGACY


class Module0Pipeline:
    def __init__(self, chirps_path, era5_path, modis_dir, boundary_path, output_path,
                 chunk_size=None, hash_inputs=False):
        self.chirps = Path(chirps_path)
        self.era5 = Path(era5_path)
        self.modis = Path(modis_dir)
        self.boundary = Path(boundary_path)
        self.out = Path(output_path)
        self.hash_inputs = hash_inputs
        self.chunk_size = chunk_size or {"time": 12}
        for p, name in [(self.chirps, "CHIRPS file"), (self.era5, "ERA5-Land file"),
                        (self.modis, "MODIS NDVI folder"), (self.boundary, "boundary file")]:
            if not p.exists():
                raise FileNotFoundError(f"{name} not found: {p}")

    @staticmethod
    def _bbox(gdf):
        minx, miny, maxx, maxy = gdf.total_bounds
        return {"lon_min": minx, "lon_max": maxx, "lat_min": miny, "lat_max": maxy}

    @staticmethod
    def _subset(ds, bbox):
        lat = "latitude" if "latitude" in ds.coords else "lat"
        lon = "longitude" if "longitude" in ds.coords else "lon"
        v = ds[lat].values
        lat_slice = slice(bbox["lat_min"], bbox["lat_max"]) if v[0] < v[-1] else slice(bbox["lat_max"], bbox["lat_min"])
        return ds.sel({lat: lat_slice, lon: slice(bbox["lon_min"], bbox["lon_max"])})

    @staticmethod
    def _rename(ds):
        mapping = {k: v for k, v in {"lat": "latitude", "lon": "longitude"}.items() if k in ds.coords}
        return ds.rename(mapping) if mapping else ds

    def load_precipitation(self, bbox):
        print("\n   CHIRPS precipitation")
        ds = xr.open_dataset(self.chirps, chunks={})
        var = next(v for v in ds.data_vars if "precip" in v.lower())
        ds = self._subset(ds[[var]].rename({var: "precipitation"}), bbox)
        print(f"      subset {dict(ds.sizes)}")
        return ds

    def load_era5(self, bbox):
        print("   ERA5-Land potential evaporation and soil moisture")
        ds = xr.open_dataset(self.era5, chunks={})
        rename = {k: v for k, v in {"valid_time": "time", "pev": "potential_evaporation",
                                    "swvl1": "soil_moisture"}.items() if k in ds.variables}
        ds = ds.rename(rename)
        missing = [v for v in ("potential_evaporation", "soil_moisture") if v not in ds.data_vars]
        if missing:
            raise SystemExit(f"ERA5-Land file lacks {missing}; variables present: {list(ds.data_vars)}")
        ds = self._subset(ds[["potential_evaporation", "soil_moisture"]], bbox)
        print(f"      subset {dict(ds.sizes)}")
        return ds

    def load_ndvi(self, bbox):
        print("   MODIS NDVI")
        files = sorted(self.modis.glob("*.nc"))
        if not files:
            raise FileNotFoundError(f"No NetCDF files in {self.modis}; run convert_modis_ndvi.py first")
        ds = xr.open_mfdataset(files, combine="by_coords", data_vars="all", chunks=self.chunk_size)
        var = next(v for v in ds.data_vars if "ndvi" in v.lower())
        ds = self._subset(ds[[var]].rename({var: "ndvi"}), bbox)
        ds["ndvi"], n_valid, n_bad = scale_and_mask_ndvi(ds["ndvi"])
        print(f"      {len(files)} files; {n_valid:,} cells in range, {n_bad:,} outside -2000..10000 (masked)")
        ds = ds.resample(time="1MS").mean(keep_attrs=True)
        print(f"      monthly {dict(ds.sizes)}")
        return ds

    def run(self):
        print("STEP 7  Build the ASAL data cube")
        gdf = gpd.read_file(self.boundary).to_crs("EPSG:4326")
        bbox = self._bbox(gdf)
        print(f"   bounding box {bbox['lat_min']:.2f} to {bbox['lat_max']:.2f} N, "
              f"{bbox['lon_min']:.2f} to {bbox['lon_max']:.2f} E")

        ds_p = self._rename(self.load_precipitation(bbox))
        ds_e = self._rename(self.load_era5(bbox))
        ds_n = self._rename(self.load_ndvi(bbox))

        print("\n   interpolating ERA5-Land and NDVI onto the CHIRPS grid (linear)")
        ds_e = ds_e.interp(latitude=ds_p.latitude, longitude=ds_p.longitude, method="linear")
        ds_n = ds_n.interp(latitude=ds_p.latitude, longitude=ds_p.longitude, method="linear")

        ds = xr.merge([ds_p, ds_e, ds_n], join="inner", compat="override")
        if ds.sizes["time"] == 0:
            raise SystemExit("No months are shared by all inputs; check the date ranges of the downloads")
        print(f"   merged {dict(ds.sizes)}")
        with ProgressBar():
            ds = ds.compute()

        print("\n   cleaning")
        n = int((ds["precipitation"] < 0).sum())
        print(f"      precipitation: {n:,} negative cells set to 0")
        ds["precipitation"] = ds["precipitation"].clip(min=0)

        n = int((ds["potential_evaporation"] > 0).sum())
        print(f"      potential evaporation: {n:,} positive cells before sign reversal")
        ds["potential_evaporation"] = -ds["potential_evaporation"] * 1000.0

        ndvi = ds["ndvi"].values
        ndvi = ndvi[np.isfinite(ndvi)]
        lo, hi, med = float(ndvi.min()), float(ndvi.max()), float(np.median(ndvi))
        clustered = float((np.abs(ndvi - med) < 0.005).mean())
        print(f"      ndvi range {lo:.3f} to {hi:.3f}, median {med:.3f}, share within 0.005 of median {clustered:.2f}")
        if hi > 1.0 or lo < -0.2:
            raise ValueError("NDVI outside -0.2..1.0 after scaling; check the MODIS inputs")
        if clustered > 0.25:
            raise ValueError("NDVI values pile up on a few codes; the converted files probably hold the "
                             "VI_Quality layer, not NDVI. Rerun convert_modis_ndvi.py on the NDVI GeoTIFFs.")

        ds["precipitation"].attrs = {"units": "mm/month", "long_name": "CHIRPS v2.0 monthly precipitation"}
        ds["potential_evaporation"].attrs = {
            "units": "mm/day",
            "long_name": "ERA5-Land potential evaporation, monthly mean of daily totals",
            "comment": "ERA5-Land sign reversed so evaporation is positive; converted from metres to mm"}
        ds["soil_moisture"].attrs = {"units": "m3 m-3",
                                     "long_name": "ERA5-Land volumetric soil water, layer 1 (0-7 cm)"}
        ds["ndvi"].attrs = {"units": "1", "long_name": "MODIS NDVI, monthly mean"}
        for v in ds.data_vars:
            ds[v] = ds[v].astype("float32")

        modis_files = sorted(self.modis.glob("*.nc"))
        manifest = hashlib.sha256("\n".join(f"{f.name}:{f.stat().st_size}" for f in modis_files).encode()).hexdigest()
        ds.attrs = {
            "title": "GreenScope ASAL climate-vegetation data cube (Module 0)",
            "date_created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "source_chirps": describe_input(self.chirps, self.hash_inputs),
            "source_era5_land": describe_input(self.era5, self.hash_inputs),
            "source_modis_ndvi": (f"{len(modis_files)} files, {modis_files[0].name} to {modis_files[-1].name}, "
                                  f"file-list sha256={manifest}"),
            "history": ("data_cube.py: bounding-box subset (no polygon mask); NDVI x 0.0001 with values outside "
                        "-2000..10000 masked, monthly mean; ERA5-Land and NDVI linearly interpolated to the "
                        "CHIRPS 0.05 degree grid; inner join on time; precipitation floored at 0; potential "
                        "evaporation sign reversed and converted to mm/day"),
        }
        tag_causal_role(ds)

        chunks = (min(12, ds.sizes["time"]), min(100, ds.sizes["latitude"]), min(100, ds.sizes["longitude"]))
        encoding = {v: {"zlib": True, "complevel": 4, "dtype": "float32", "chunksizes": chunks,
                        "_FillValue": -9999.0} for v in ds.data_vars}
        encoding.update({c: {"_FillValue": None} for c in ("latitude", "longitude", "time")})
        self.out.parent.mkdir(parents=True, exist_ok=True)
        ds.to_netcdf(self.out, encoding=encoding, engine="netcdf4")

        print(f"\n   saved {self.out}  ({self.out.stat().st_size / 1e6:.1f} MB)")
        print(f"   dimensions {dict(ds.sizes)}")
        print(f"   time {str(ds.time.values[0])[:7]} to {str(ds.time.values[-1])[:7]}")
        for v in ds.data_vars:
            layer, role, _ = CAUSAL_REGISTRY[v]
            print(f"      {v:22s} layer {layer}  {role:15s} {ds[v].attrs['units']}")
        return ds


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--chirps", default=str(CHIRPS))
    ap.add_argument("--era5", default=None, help=f"default {ERA5} (or {ERA5_LEGACY.name} if that is all there is)")
    ap.add_argument("--modis", default=str(MODIS_NC), help="folder of converted NDVI NetCDF files")
    ap.add_argument("--boundary", default=str(BOUNDARY))
    ap.add_argument("--output", default=str(CUBE))
    ap.add_argument("--hash-inputs", action="store_true", help="record SHA-256 of CHIRPS and ERA5 (slow)")
    args = ap.parse_args()
    Module0Pipeline(args.chirps, find_era5(args.era5), args.modis, args.boundary, args.output,
                    hash_inputs=args.hash_inputs).run()


if __name__ == "__main__":
    main()

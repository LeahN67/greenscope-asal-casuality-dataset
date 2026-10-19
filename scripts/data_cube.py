"""
Step 7. Build the gridded ASAL cube (Module 0): CHIRPS precipitation, ERA5-Land potential
evaporation and soil moisture, and MODIS NDVI on the CHIRPS 0.05 degree grid, monthly.

    python scripts/data_cube.py
    python scripts/data_cube.py --no-mask              # keep the full bounding box
    python scripts/data_cube.py --modis data/raw/modis_ndvi/ndvi_fixed --no-hash-inputs

What it does, in order:
  1. checks that CHIRPS and ERA5-Land are monthly, then subsets every input to the bounding box
     of the ASAL boundary
  2. NDVI: scales stored values by 0.0001, masks values outside -2000..10000, monthly mean
  3. NDVI and its quality share: averages ALL MODIS pixels whose centres fall in each 0.05 degree
     cell (area average); ERA5-Land (coarser than the target grid) is interpolated linearly
  4. keeps months present in every input (inner join on time)
  5. masks every gridded variable to cells whose centre lies inside the ASAL polygon (unless --no-mask)
  6. floors precipitation at 0; reverses the ERA5-Land sign of potential evaporation and converts
     it from metres to mm per day, then checks the result is in a plausible range
  7. writes units, causal roles, quality-control counts and provenance (input checksums, source
     URLs, the ERA5-Land and AppEEARS requests) into the NetCDF attributes

Output: data/processed/module0/module0_asal_datacube.nc
        data/processed/module0/ndvi_input_files.csv   (SHA-256 of every NDVI input file)
"""
import os

import pyproj

os.environ.setdefault("PROJ_LIB", pyproj.datadir.get_data_dir())

import argparse
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
import xarray as xr

from gs_common import (ANCILLARY, BOUNDARY, CAUSAL_REGISTRY, CHIRPS, CHIRPS_URL, CUBE, ERA5,
                       ERA5_LEGACY, ERA5_REQUEST, MODIS_NC, MODIS_TASK, sha256_file, tag_causal_role)

KM_PER_DEGREE = 111.32


# ------------------------------------------------------------------ helpers
def scale_and_mask_ndvi(da):
    """
    MODIS NDVI is stored as integers scaled by 0.0001, valid range -2000..10000. The GeoTIFFs carry
    no scale factor, so it is applied here. Out-of-range values are masked, not clipped.
    Returns the scaled array and the counts of in-range and out-of-range pixels.
    """
    in_range = (da >= -2000) & (da <= 10000)
    out_of_range = da.notnull() & ~in_range
    n_valid = int(in_range.sum().compute())
    n_bad = int(out_of_range.sum().compute())
    scaled = da.where(in_range) * 0.0001
    scaled.attrs = {"units": "1", "long_name": "MODIS NDVI (stored value x 0.0001)"}
    return scaled, n_valid, n_bad


def usable_quality(ndvi, quality):
    """1 where the VI_Quality MODLAND bits (0-1) are 00 or 01, 0 where 10 or 11; NaN where NDVI is missing."""
    q = quality.fillna(65535).astype("int64")
    ok = ((q % 4) <= 1).astype("float32")
    return ok.where(ndvi.notnull())


def check_regular(coord, label, rtol=1e-3):
    """Stop unless the coordinate is strictly monotonic and evenly spaced (needed by area_average)."""
    c = np.asarray(coord, dtype="float64")
    d = np.diff(c)
    if c.size < 2 or not (np.all(d > 0) or np.all(d < 0)):
        raise SystemExit(f"{label}: coordinates are not strictly monotonic")
    if np.max(np.abs(np.abs(d) - np.abs(d).mean())) > rtol * np.abs(d).mean():
        raise SystemExit(f"{label}: coordinates are not evenly spaced")


def bin_positions(coord, centres):
    """For each fine coordinate, the index of the target cell whose span contains it (-1 if none)."""
    c = np.asarray(centres, dtype="float64")
    step = float(np.abs(np.diff(c)).mean())
    order = np.argsort(c)
    lo = c[order[0]] - step / 2
    idx = np.floor((np.asarray(coord, dtype="float64") - lo) / step).astype(int)
    pos = np.full(idx.shape, -1)
    ok = (idx >= 0) & (idx < c.size)
    pos[ok] = order[idx[ok]]
    return pos


def area_average(fine, target_lat, target_lon, name):
    """
    Unweighted mean of all fine-grid pixels whose centres fall inside each target cell, month by month.
    Pixel areas within one 0.05 degree cell differ by less than 0.01% (cosine of latitude over 0.05
    degree near the equator), so this approximates an area-weighted mean closely. Both grids must be
    regular (checked by check_regular). Cells with no valid pixel are NaN.
    """
    iy = bin_positions(fine.latitude.values, target_lat.values)
    ix = bin_positions(fine.longitude.values, target_lon.values)
    ny, nx = target_lat.size, target_lon.size
    Y, X = np.meshgrid(iy, ix, indexing="ij")
    inside = (Y >= 0) & (X >= 0)
    flat = (Y * nx + X)[inside]
    out = np.full((fine.sizes["time"], ny, nx), np.nan, dtype="float32")
    for t in range(fine.sizes["time"]):
        v = np.asarray(fine.isel(time=t).values)[inside]
        good = np.isfinite(v)
        s = np.bincount(flat[good], weights=v[good], minlength=ny * nx)
        n = np.bincount(flat[good], minlength=ny * nx)
        with np.errstate(invalid="ignore", divide="ignore"):
            out[t] = np.where(n > 0, s / np.maximum(n, 1), np.nan).reshape(ny, nx)
    return xr.DataArray(out, dims=("time", "latitude", "longitude"), name=name,
                        coords={"time": fine.time.values, "latitude": target_lat.values,
                                "longitude": target_lon.values})


def check_monthly(ds, label):
    t = pd.DatetimeIndex(ds.time.values)
    if len(t) > 2:
        gap = float(np.median(np.diff(t.values).astype("timedelta64[D]").astype(float)))
        if not 27 <= gap <= 32:
            raise SystemExit(f"{label}: median time step is {gap:.1f} days; expected monthly data")


def describe_input(path, hash_it=True):
    p = Path(path)
    text = f"{p.name} ({p.stat().st_size} bytes)"
    return text + (f" sha256={sha256_file(p)}" if hash_it else "")


def find_era5(path):
    if path:
        return Path(path)
    return ERA5 if ERA5.exists() or not ERA5_LEGACY.exists() else ERA5_LEGACY


def cell_area_km2(lat, step):
    return (KM_PER_DEGREE * step) ** 2 * np.cos(np.deg2rad(lat))


# ------------------------------------------------------------------ pipeline
class Module0Pipeline:
    def __init__(self, chirps_path, era5_path, modis_dir, boundary_path, output_path,
                 hash_inputs=True, mask=True):
        self.chirps = Path(chirps_path)
        self.era5 = Path(era5_path)
        self.modis = Path(modis_dir)
        self.boundary = Path(boundary_path)
        self.out = Path(output_path)
        self.hash_inputs = hash_inputs
        self.mask = mask
        self.qc = {}
        for p, name in [(self.chirps, "CHIRPS file"), (self.era5, "ERA5-Land file"),
                        (self.modis, "MODIS NDVI folder"), (self.boundary, "boundary file")]:
            if not p.exists():
                raise FileNotFoundError(f"{name} not found: {p}")

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
        ds = self._rename(xr.open_dataset(self.chirps, chunks={}))
        var = next(v for v in ds.data_vars if "precip" in v.lower())
        units = str(ds[var].attrs.get("units", ""))
        if units and "mm" not in units.lower():
            print(f"      WARNING: CHIRPS units are '{units}', expected mm (monthly totals)")
        check_monthly(ds, "CHIRPS")
        ds = self._subset(ds[[var]].rename({var: "precipitation"}), bbox)
        print(f"      subset {dict(ds.sizes)}")
        return ds

    def load_era5(self, bbox):
        print("   ERA5-Land potential evaporation and soil moisture")
        ds = xr.open_dataset(self.era5, chunks={})
        rename = {k: v for k, v in {"valid_time": "time", "pev": "potential_evaporation",
                                    "swvl1": "soil_moisture"}.items() if k in ds.variables}
        ds = self._rename(ds.rename(rename))
        missing = [v for v in ("potential_evaporation", "soil_moisture") if v not in ds.data_vars]
        if missing:
            raise SystemExit(f"ERA5-Land file lacks {missing}; variables present: {list(ds.data_vars)}")
        check_monthly(ds, "ERA5-Land")
        ds = self._subset(ds[["potential_evaporation", "soil_moisture"]], bbox)
        ds["time"] = pd.DatetimeIndex(ds.time.values).to_period("M").to_timestamp()
        print(f"      subset {dict(ds.sizes)}")
        return ds

    def load_ndvi(self, bbox):
        print("   MODIS NDVI")
        files = sorted(self.modis.glob("*.nc"))
        if not files:
            raise FileNotFoundError(f"No NetCDF files in {self.modis}; run convert_modis_ndvi.py first")
        ds = self._rename(xr.open_mfdataset(files, combine="by_coords", data_vars="all", chunks={"time": 12}))
        var = next(v for v in ds.data_vars if "ndvi" in v.lower())
        ds = self._subset(ds, bbox)
        ndvi, n_valid, n_bad = scale_and_mask_ndvi(ds[var])
        self.qc["qc_ndvi_pixels_out_of_range"] = n_bad
        print(f"      {len(files)} files; {n_valid:,} pixels in range, {n_bad:,} outside -2000..10000 (masked)")
        out = xr.Dataset({"ndvi": ndvi})
        if "VI_Quality" in ds.data_vars:
            out["ndvi_good_fraction"] = usable_quality(ndvi, ds["VI_Quality"])
        else:
            print("      no VI_Quality in the NDVI files; ndvi_good_fraction will not be produced")
        out = out.resample(time="1MS").mean()
        print(f"      monthly {dict(out.sizes)}")
        return out

    def regrid_ndvi(self, ds_n, target):
        fine_step = float(np.abs(np.diff(ds_n.latitude.values)).mean())
        target_step = float(np.abs(np.diff(target.latitude.values)).mean())
        if fine_step < target_step / 1.5:
            k = target_step / fine_step
            print(f"   averaging all MODIS pixels in each {target_step:.3f} degree cell "
                  f"(about {k * k:.0f} pixels per cell)")
            for coord, label in [(ds_n.latitude, "MODIS latitude"), (ds_n.longitude, "MODIS longitude"),
                                 (target.latitude, "CHIRPS latitude"), (target.longitude, "CHIRPS longitude")]:
                check_regular(coord.values, label)
            regridded = xr.Dataset({v: area_average(ds_n[v], target.latitude, target.longitude, v)
                                    for v in ds_n.data_vars})
            self.qc["ndvi_regridding"] = (f"unweighted mean of all MODIS pixels (about {fine_step:.4f} degree) whose "
                                          f"centres fall in each {target_step:.3f} degree cell (pixel areas within a "
                                          f"cell differ by less than 0.01%)")
        else:
            print("   MODIS grid is not finer than the target grid; interpolating linearly")
            regridded = ds_n.interp(latitude=target.latitude, longitude=target.longitude, method="linear")
            self.qc["ndvi_regridding"] = "linear interpolation (input not finer than target grid)"
        return regridded

    def asal_mask(self, gdf, lat, lon):
        geom = gdf.geometry.union_all() if hasattr(gdf.geometry, "union_all") else gdf.geometry.unary_union
        lon2, lat2 = np.meshgrid(lon.values, lat.values)
        inside = shapely.contains_xy(geom, lon2, lat2)
        # cells crossed by the polygon boundary: partly inside, partly outside
        h = float(np.abs(np.diff(lat.values)).mean()) / 2
        boxes = shapely.box(lon2 - h, lat2 - h, lon2 + h, lat2 + h)
        shapely.prepare(geom)
        straddle = shapely.intersects(geom, boxes) & ~shapely.contains(geom, boxes)
        self.qc["boundary_cells_kept"] = int((straddle & inside).sum())
        self.qc["boundary_cells_dropped"] = int((straddle & ~inside).sum())
        self.qc["mask_rule"] = "centre-in-polygon: a cell is kept when its centre lies inside the ASAL polygon"
        return xr.DataArray(inside.astype("int8"), dims=("latitude", "longitude"),
                            coords={"latitude": lat.values, "longitude": lon.values}, name="asal_mask")

    def provenance(self):
        attrs = {
            "source_chirps": describe_input(self.chirps, self.hash_inputs) + f"; {CHIRPS_URL}",
            "source_era5_land": describe_input(self.era5, self.hash_inputs),
        }
        if ERA5_REQUEST.exists() and self.era5.resolve().parent == ERA5_REQUEST.parent:
            attrs["source_era5_land_request"] = json.dumps(json.loads(ERA5_REQUEST.read_text()), separators=(",", ":"))
        files = sorted(self.modis.glob("*.nc"))
        rows = [(f.name, f.stat().st_size, sha256_file(f) if self.hash_inputs else "") for f in files]
        listing = self.out.parent / "ndvi_input_files.csv"
        listing.parent.mkdir(parents=True, exist_ok=True)
        with open(listing, "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["file", "bytes", "sha256"])
            w.writerows(rows)
        first = xr.open_dataset(files[0])
        product = first.attrs.get("product", "unknown")
        first.close()
        attrs["source_modis_ndvi"] = (f"{product}; {len(files)} files, {files[0].name} to {files[-1].name}; "
                                      f"per-file SHA-256 in {listing.name}; sha256 of that list="
                                      f"{hashlib.sha256(listing.read_bytes()).hexdigest()}")
        request = self.modis.parent / "request.json"
        if request.exists():
            attrs["source_modis_request"] = json.dumps(json.loads(request.read_text()), separators=(",", ":"))
        elif MODIS_TASK.exists():
            attrs["source_modis_request"] = f"AppEEARS task {MODIS_TASK.read_text().strip()}"
        return attrs

    def run(self):
        print("STEP 7  Build the ASAL data cube")
        gdf = gpd.read_file(self.boundary).to_crs("EPSG:4326")
        minx, miny, maxx, maxy = gdf.total_bounds
        bbox = {"lon_min": minx, "lon_max": maxx, "lat_min": miny, "lat_max": maxy}
        print(f"   bounding box {miny:.2f} to {maxy:.2f} N, {minx:.2f} to {maxx:.2f} E")

        ds_p = self.load_precipitation(bbox)
        ds_e = self.load_era5(bbox)
        ds_n = self.load_ndvi(bbox)
        ds_p["time"] = pd.DatetimeIndex(ds_p.time.values).to_period("M").to_timestamp()

        times = sorted(set(ds_p.time.values) & set(ds_e.time.values) & set(ds_n.time.values))
        if not times:
            raise SystemExit("No months are shared by all inputs; check the date ranges of the downloads")
        ds_p, ds_e, ds_n = (d.sel(time=times) for d in (ds_p, ds_e, ds_n))
        print(f"\n   {len(times)} months shared by all inputs: "
              f"{pd.Timestamp(times[0]):%Y-%m} to {pd.Timestamp(times[-1]):%Y-%m}")

        print("   interpolating ERA5-Land onto the CHIRPS grid (linear)")
        ds_p = ds_p.compute()
        ds_e = ds_e.interp(latitude=ds_p.latitude, longitude=ds_p.longitude, method="linear").compute()
        ds_n = self.regrid_ndvi(ds_n, ds_p)
        ds = xr.merge([ds_p, ds_e, ds_n], compat="override", join="exact")

        step = float(np.abs(np.diff(ds.latitude.values)).mean())
        mask = self.asal_mask(gdf, ds.latitude, ds.longitude)
        area = float((cell_area_km2(ds.latitude, step).broadcast_like(mask) * mask).sum())
        self.qc.update(asal_cells=int(mask.sum()), asal_area_km2=round(area))
        print(f"   ASAL polygon covers {int(mask.sum()):,} of {mask.size:,} grid cells (about {area:,.0f} km2); "
              f"{self.qc['boundary_cells_kept']:,} boundary cells kept and {self.qc['boundary_cells_dropped']:,} dropped "
              f"by the centre rule")
        if self.mask:
            for v in ds.data_vars:
                ds[v] = ds[v].where(mask == 1)
            print("   all gridded variables masked to the ASAL polygon")
        ds["asal_mask"] = mask

        print("\n   cleaning")
        n = int((ds["precipitation"] < 0).sum())
        self.qc["qc_precipitation_negative_cells"] = n
        print(f"      precipitation: {n:,} negative cells set to 0")
        ds["precipitation"] = ds["precipitation"].clip(min=0)

        n = int((ds["potential_evaporation"] > 0).sum())
        self.qc["qc_pev_positive_cells_before_sign_reversal"] = n
        print(f"      potential evaporation: {n:,} positive cells before sign reversal")
        ds["potential_evaporation"] = -ds["potential_evaporation"] * 1000.0
        pev_median = float(ds["potential_evaporation"].median())
        print(f"      potential evaporation median {pev_median:.2f} mm/day")
        if not 0.5 <= pev_median <= 20:
            raise SystemExit("Potential evaporation median is outside 0.5..20 mm/day after conversion. Check that "
                             "the ERA5-Land file holds monthly means of daily totals in metres "
                             "(product_type monthly_averaged_reanalysis).")

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
        ds["ndvi"].attrs = {"units": "1", "long_name": "MODIS NDVI, monthly mean of all pixels in the cell"}
        if "ndvi_good_fraction" in ds:
            ds["ndvi_good_fraction"].attrs = {"units": "1", "long_name": "Share of good-quality MODIS pixels",
                                              "comment": ANCILLARY["ndvi_good_fraction"]}
        ds["asal_mask"].attrs = {"units": "1", "long_name": "ASAL polygon mask", "comment": ANCILLARY["asal_mask"]}
        for v in ds.data_vars:
            if v != "asal_mask":
                ds[v] = ds[v].astype("float32")

        ds.attrs = {
            "title": "GreenScope ASAL climate-vegetation data cube (Module 0)",
            "date_created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "spatial_extent": ("grid cells whose centre lies inside the 23-county ASAL polygon; others missing"
                               if self.mask else "bounding box of the ASAL counties (no polygon mask)"),
            **self.provenance(),
            **{k: str(v) for k, v in self.qc.items()},
            "history": ("data_cube.py: bounding-box subset; NDVI x 0.0001 with values outside -2000..10000 masked, "
                        "monthly mean; NDVI and its quality share averaged over all MODIS pixels in each 0.05 "
                        "degree cell; ERA5-Land linearly interpolated to the CHIRPS grid; months shared by all "
                        "inputs kept; " + ("masked to the ASAL polygon; " if self.mask else "") +
                        "precipitation floored at 0; potential evaporation sign reversed and converted to mm/day"),
        }
        tag_causal_role(ds)

        chunks = (min(12, ds.sizes["time"]), min(100, ds.sizes["latitude"]), min(100, ds.sizes["longitude"]))
        encoding = {v: {"zlib": True, "complevel": 4, "dtype": "float32", "chunksizes": chunks,
                        "_FillValue": -9999.0} for v in ds.data_vars if v != "asal_mask"}
        encoding["asal_mask"] = {"dtype": "int8", "_FillValue": None}
        encoding.update({c: {"_FillValue": None} for c in ("latitude", "longitude", "time")})
        self.out.parent.mkdir(parents=True, exist_ok=True)
        ds.to_netcdf(self.out, encoding=encoding, engine="netcdf4")

        print(f"\n   saved {self.out}  ({self.out.stat().st_size / 1e6:.1f} MB)")
        print(f"   dimensions {dict(ds.sizes)}; time {pd.Timestamp(times[0]):%Y-%m} to {pd.Timestamp(times[-1]):%Y-%m}")
        for v in ds.data_vars:
            role = f"layer {CAUSAL_REGISTRY[v][0]}  {CAUSAL_REGISTRY[v][1]}" if v in CAUSAL_REGISTRY else "ancillary"
            print(f"      {v:22s} {role:25s} {ds[v].attrs.get('units', '')}")
        return ds


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--chirps", default=str(CHIRPS))
    ap.add_argument("--era5", default=None, help=f"default {ERA5} (or {ERA5_LEGACY.name} if that is all there is)")
    ap.add_argument("--modis", default=str(MODIS_NC), help="folder of converted NDVI NetCDF files")
    ap.add_argument("--boundary", default=str(BOUNDARY))
    ap.add_argument("--output", default=str(CUBE))
    ap.add_argument("--no-mask", action="store_true", help="keep the full bounding box instead of the ASAL polygon")
    ap.add_argument("--no-hash-inputs", action="store_true", help="skip SHA-256 of the inputs (faster, less provenance)")
    args = ap.parse_args()
    Module0Pipeline(args.chirps, find_era5(args.era5), args.modis, args.boundary, args.output,
                    hash_inputs=not args.no_hash_inputs, mask=not args.no_mask).run()


if __name__ == "__main__":
    main()

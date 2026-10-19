"""
Offline tests: synthetic inputs in the same formats as the real downloads, run end to end.

    pytest -q tests

No network access or credentials are needed.
"""
import http.server
import json
import os
import subprocess
import sys
import threading
from functools import partial
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import rasterio
import xarray as xr
from rasterio.transform import from_origin

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

import causal_integration as ci  # noqa: E402


# ------------------------------------------------------------------ helpers
def psl_file(path, y0, y1, fn, footer, last_valid_month=12, missing="-99.99"):
    """Write a NOAA PSL-style file: header 'y0 y1', one row per year, footer lines."""
    rows = [f"        {y0}        {y1}"]
    for y in range(y0, y1 + 1):
        vals = [f"{fn(y, m):8.3f}" if (y < y1 or m <= last_valid_month) else f"{missing:>8}"
                for m in range(1, 13)]
        rows.append(f" {y} " + " ".join(vals))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(rows + footer) + "\n")


def write_tif(path, array, nodata, res=1 / 120, west=34.9, north=2.1):
    with rasterio.open(path, "w", driver="GTiff", height=array.shape[0], width=array.shape[1], count=1,
                       dtype=array.dtype, crs="EPSG:4326", transform=from_origin(west, north, res, res),
                       nodata=nodata) as f:
        f.write(array, 1)


def make_inputs(root, modis_layer="NDVI"):
    rng = np.random.default_rng(42)
    raw = root / "data" / "raw"
    months = pd.date_range("2019-01-01", "2020-12-01", freq="MS")

    (raw / "boundaries").mkdir(parents=True)
    (raw / "boundaries" / "asal_boundary.geojson").write_text(json.dumps({
        "type": "FeatureCollection", "features": [{"type": "Feature", "properties": {}, "geometry": {
            "type": "Polygon", "coordinates": [[[35, 0], [37, 0], [37, 2], [35, 0]]]}}]}))

    lat = np.round(np.arange(-1.0, 3.0, 0.05), 3)
    lon = np.round(np.arange(34.0, 38.0, 0.05), 3)
    (raw / "chirps" / "monthly").mkdir(parents=True)
    xr.Dataset({"precip": (("time", "latitude", "longitude"),
                           rng.gamma(2.0, 20.0, (len(months), lat.size, lon.size)).astype("float32"))},
               coords={"time": months, "latitude": lat, "longitude": lon}
               ).to_netcdf(raw / "chirps" / "monthly" / "chirps-v2.0.monthly.nc")

    lat_e = np.round(np.arange(3.0, -1.05, -0.1), 2)     # descending, like ERA5
    lon_e = np.round(np.arange(34.0, 38.05, 0.1), 2)
    shape = (len(months), lat_e.size, lon_e.size)
    (raw / "era5_land").mkdir(parents=True)
    xr.Dataset({"pev": (("valid_time", "latitude", "longitude"), -rng.uniform(0.003, 0.011, shape).astype("float32")),
                "swvl1": (("valid_time", "latitude", "longitude"), rng.uniform(0.05, 0.4, shape).astype("float32"))},
               coords={"valid_time": months, "latitude": lat_e, "longitude": lon_e}
               ).to_netcdf(raw / "era5_land" / "era5_land_monthly.nc")

    mdir = raw / "modis_ndvi_monthly"
    mdir.mkdir(parents=True)
    for d in months:
        doy = f"{d:%Y}{d.dayofyear:03d}"
        ndvi = rng.integers(-500, 8500, (290, 290)).astype("int16")
        ndvi[:5, :] = -3000
        qual = rng.choice([2116, 2118, 34896], (290, 290)).astype("uint16")   # 2118: MODLAND bits 10 (cloudy)
        layers = {"NDVI": (ndvi, -3000), "VI_Quality": (qual, 65535)}
        if modis_layer == "quality_as_ndvi":          # reproduce the original bug
            layers["NDVI"] = (qual, 65535)
        for name, (arr, nod) in layers.items():
            write_tif(mdir / f"MOD13A3.061__1_km_monthly_{name}_doy{doy}000000_aid0001.tif", arr, nod)

    psl_file(raw / "enso" / "nino34.txt", 1948, 2025,
             lambda y, m: 26.8 + np.sin(2 * np.pi * (m - 3) / 12) + (1.2 if y == 2020 else 0.0),
             ["  -99.99", "  Nino 3.4 Mean using ersstv5 from CPC"], last_valid_month=11)
    psl_file(raw / "iod" / "dmi_noaa.txt", 1870, 2020, lambda y, m: 0.3 * np.sin(y + m),
             ["  using SST anomaly 10S:10N,50E-70E minus 10S:0,90E-110E", "  Preliminary."],
             last_valid_month=10, missing="-9999.000")
    return root


def run(script, root, *args):
    env = dict(os.environ, GREENSCOPE_PROJECT_ROOT=str(root))
    return subprocess.run([sys.executable, str(REPO / script), *args], cwd=root, env=env,
                          capture_output=True, text=True)


# ------------------------------------------------------------------ unit tests
def test_index_parser_uses_row_years(tmp_path):
    f = tmp_path / "idx.txt"
    psl_file(f, 1948, 2025, lambda y, m: (y - 1948) * 100 + m, ["  -99.99", "  footer text"])
    da = ci.parse_noaa_index(f, "x")
    assert str(da.time.values[0])[:7] == "1948-01" and str(da.time.values[-1])[:7] == "2025-12"
    assert float(da.sel(time="2025-01-01")) == 7701          # the old parser returned 7601 here
    assert float(da.sel(time="1948-01-01")) == 1


def test_missing_codes_and_gaps(tmp_path):
    f = tmp_path / "dmi.txt"
    psl_file(f, 2000, 2001, lambda y, m: 0.1, [], last_valid_month=4, missing="-9999.000")
    da = ci.parse_noaa_index(f, "d")
    assert np.isnan(float(da.sel(time="2001-05-01"))) and float(da.sel(time="2001-04-01")) == 0.1
    gap = tmp_path / "gap.txt"
    gap.write_text(" 2000 " + " 1.0" * 12 + "\n 2002 " + " 1.0" * 12 + "\n")
    with pytest.raises(ValueError, match="Missing years"):
        ci.parse_noaa_index(gap, "g")


def test_exact_alignment_never_fills(tmp_path):
    f = tmp_path / "idx.txt"
    psl_file(f, 2000, 2020, lambda y, m: 1.0, [], last_valid_month=10, missing="-99.99")
    da = ci.parse_noaa_index(f, "x")
    t = pd.date_range("2020-06-01", "2020-12-01", freq="MS")
    cube_time = xr.DataArray(t, dims="time", coords={"time": t})
    with pytest.raises(SystemExit):
        ci.align_exact(da, cube_time, "x")
    a = ci.align_exact(da, cube_time, "x", allow_missing=True)
    assert int(a.isnull().sum()) == 2 and a.attrs["missing_months"] == "2020-11, 2020-12"


def test_anomaly_removes_seasonal_cycle():
    t = pd.date_range("1950-01-01", "2025-12-01", freq="MS")
    s = xr.DataArray(26.5 + 1.5 * np.sin(2 * np.pi * (t.month - 1) / 12) + 0.5 * (t.year >= 2023),
                     coords=[("time", t)], name="e")
    a = ci.monthly_anomaly(s)
    assert abs(float(a.sel(time=slice("1991", "2020")).mean())) < 1e-9
    assert abs(float(a.sel(time="2024-06-01")) - 0.5) < 1e-9


def test_download_resume_and_manifest(tmp_path, monkeypatch):
    serve = tmp_path / "www"
    serve.mkdir()
    payload = os.urandom(300_000)
    (serve / "file.bin").write_bytes(payload)
    handler = partial(http.server.SimpleHTTPRequestHandler, directory=str(serve))
    handler.log_message = lambda *a, **k: None
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        monkeypatch.setenv("GREENSCOPE_PROJECT_ROOT", str(tmp_path))
        import importlib
        import gs_common
        importlib.reload(gs_common)
        out = tmp_path / "data" / "raw" / "x" / "file.bin"
        out.parent.mkdir(parents=True)
        out.with_name("file.bin.part").write_bytes(payload[:1000])   # stale partial; server ignores Range
        url = f"http://127.0.0.1:{httpd.server_address[1]}/file.bin"
        gs_common.download_with_resume(url, out, max_retries=2, base_delay=0)
        assert out.read_bytes() == payload
        gs_common.record_download("test", url, out)
        rows = gs_common.MANIFEST.read_text().splitlines()
        assert len(rows) == 2 and gs_common.sha256_file(out) in rows[1]
    finally:
        httpd.shutdown()


# ------------------------------------------------------------------ end to end
def test_pipeline_end_to_end(tmp_path):
    root = make_inputs(tmp_path)
    r = run("run_pipeline.py", root, "--skip-download", "--allow-missing-index")
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-3000:]
    assert "24 NDVI, 24 VI_Quality, 0 other layers ignored" in r.stdout

    f = xr.open_dataset(root / "data/processed/module0/greenscope_final_causal_cube.nc")
    assert set(f.data_vars) == {"precipitation", "potential_evaporation", "soil_moisture", "ndvi",
                                "enso_nino34", "iod_dmi", "asal_mask", "ndvi_good_fraction"}
    for v in ("precipitation", "potential_evaporation", "soil_moisture", "ndvi", "enso_nino34", "iod_dmi"):
        assert all(f[v].attrs.get(k) for k in ("units", "long_name", "causal_layer", "causal_role")), v
    mask = f.asal_mask.values
    assert 0 < mask.sum() < mask.size                                  # triangle: some cells outside
    for v in ("precipitation", "potential_evaporation", "soil_moisture", "ndvi", "ndvi_good_fraction"):
        assert np.isnan(f[v].values[:, mask == 0]).all(), f"{v} not masked"
        assert np.isfinite(f[v].values[:, mask == 1]).mean() > 0.8, f"{v} mostly missing inside"
    good = f.ndvi_good_fraction.values[np.isfinite(f.ndvi_good_fraction.values)]
    assert 0.5 < np.median(good) < 0.8                                # 2 of 3 synthetic codes are usable
    assert int(f.attrs["asal_cells"]) == int(mask.sum()) and "sha256" in f.attrs["source_chirps"]
    assert "MOD13A3.061" in f.attrs["source_modis_ndvi"]
    assert (root / "data/processed/module0/ndvi_input_files.csv").exists()
    assert f.sizes["time"] == 24
    nd = f.ndvi.values[np.isfinite(f.ndvi.values)]
    assert -0.2 <= nd.min() and nd.max() <= 1.0 and 0.2 < np.median(nd) < 0.6
    pev = f.potential_evaporation
    assert pev.attrs["units"] == "mm/day" and 2 < float(pev.median()) < 12
    assert f.enso_nino34.dims == ("time",) and f.iod_dmi.dims == ("time",)
    assert abs(float(f.enso_nino34.sel(time="2019-06-01"))) < 0.5
    assert float(f.enso_nino34.sel(time="2020-06-01")) > 1.0
    assert (f.ndvi * f.enso_nino34).dims == f.ndvi.dims        # lines up with the grid automatically
    assert f.iod_dmi.attrs["missing_months"] == "2020-11, 2020-12"
    assert f.ndvi.attrs["causal_role"] == "response" and f.enso_nino34.attrs["causal_layer"] == "A"
    assert all(k in f.attrs for k in ("source_chirps", "source_era5_land", "source_enso_file", "causal_registry"))
    report = (root / "data/processed/module0/cube_report.txt").read_text()
    assert "FAIL" not in report
    figs = root / "data/processed/module0/figures"
    for name in ("fig1_map.png", "fig2_timeseries.png", "fig3_lags.png", "table2_summary.csv",
                 "fig3_lags.csv", "paper_numbers.txt"):
        assert (figs / name).stat().st_size > 0, name
    assert "ASAL cells" in (figs / "paper_numbers.txt").read_text()


def test_pipeline_stops_without_allow_missing(tmp_path):
    root = make_inputs(tmp_path)
    r = run("run_pipeline.py", root, "--skip-download")
    assert r.returncode != 0 and "allow-missing-index" in (r.stdout + r.stderr)


def test_quality_layer_is_rejected(tmp_path):
    """The original bug: quality codes converted as NDVI. The cube builder must refuse them."""
    root = make_inputs(tmp_path, modis_layer="quality_as_ndvi")
    r = run("scripts/convert_modis_ndvi.py", root)
    assert r.returncode != 0 and "not NDVI" in (r.stdout + r.stderr)


def test_cube_rejects_quality_codes_even_if_converted(tmp_path):
    """Second line of defence: quality codes placed directly in the NDVI folder stop data_cube.py."""
    root = make_inputs(tmp_path)
    nd = root / "data/raw/modis_ndvi_monthly/ndvi"
    nd.mkdir(parents=True)
    rng = np.random.default_rng(0)
    lat = np.round(np.arange(2.1, -0.3, -1 / 120), 4)
    lon = np.round(np.arange(34.9, 37.3, 1 / 120), 4)
    for d in pd.date_range("2019-01-01", "2020-12-01", freq="MS"):
        codes = rng.choice([2116.0, 2120.0, 2185.0], (1, lat.size, lon.size)).astype("float32")
        xr.Dataset({"NDVI": (("time", "latitude", "longitude"), codes)},
                   coords={"time": [d], "latitude": lat, "longitude": lon}).to_netcdf(nd / f"MODIS_NDVI_{d:%Y%m%d}.nc")
    r = run("scripts/data_cube.py", root)
    assert r.returncode != 0 and "VI_Quality" in (r.stdout + r.stderr)


def test_area_average_is_exact():
    """Every fine pixel counts once, in the cell that contains its centre."""
    import data_cube as dc
    fine_lat = np.round(np.arange(0.1 - 1 / 240, 0.0, -1 / 120), 6)     # 12 pixels, descending like MODIS
    fine_lon = np.round(np.arange(35 + 1 / 240, 35.1, 1 / 120), 6)
    vals = np.arange(144, dtype="float32").reshape(1, 12, 12)
    vals[0, 0, 0] = np.nan
    fine = xr.DataArray(vals, dims=("time", "latitude", "longitude"),
                        coords={"time": [pd.Timestamp("2020-01-01")], "latitude": fine_lat, "longitude": fine_lon})
    tlat = xr.DataArray([0.025, 0.075], dims="latitude")
    tlon = xr.DataArray([35.025, 35.075], dims="longitude")
    out = dc.area_average(fine, tlat, tlon, "x").values[0]
    for i, la in enumerate((0.025, 0.075)):
        for j, lo in enumerate((35.025, 35.075)):
            sel = (np.abs(fine_lat - la) < 0.025)[:, None] & (np.abs(fine_lon - lo) < 0.025)[None, :]
            assert np.isclose(out[i, j], np.nanmean(vals[0][sel]))


def test_no_mask_keeps_bounding_box(tmp_path):
    root = make_inputs(tmp_path)
    assert run("scripts/convert_modis_ndvi.py", root).returncode == 0
    r = run("scripts/data_cube.py", root, "--no-mask", "--no-hash-inputs")
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]
    f = xr.open_dataset(root / "data/processed/module0/module0_asal_datacube.nc")
    assert np.isfinite(f.precipitation.values[:, f.asal_mask.values == 0]).all()
    assert "bounding box" in f.attrs["spatial_extent"]


def test_quality_flags_missing_or_invalid_count_as_not_usable():
    import data_cube as dc
    ndvi = xr.DataArray([0.5, 0.5, 0.5, 0.5, 0.5, np.nan], dims="x")
    # MODLAND bits: 2116 -> 00 good, 2117 -> 01 check QA, 2118 -> 10 cloudy, 2119 -> 11 not produced,
    # NaN -> missing flag; last pixel has no NDVI
    quality = xr.DataArray([2116, 2117, 2118, 2119, np.nan, 2116], dims="x")
    usable = dc.usable_quality(ndvi, quality).values
    assert list(usable[:5]) == [1, 1, 0, 0, 0] and np.isnan(usable[5])


def test_irregular_grid_is_refused():
    import data_cube as dc
    dc.check_regular(np.arange(0, 1, 0.05), "ok")
    dc.check_regular(np.arange(1, 0, -0.05), "descending ok")
    for bad in ([0.0, 0.05, 0.12, 0.15], [0.0, 0.05, 0.05, 0.1], [0.0, 0.1, 0.05, 0.15]):
        with pytest.raises(SystemExit):
            dc.check_regular(np.array(bad), "bad")


def test_boundary_cells_and_sensitivity_table(tmp_path):
    root = make_inputs(tmp_path)
    r = run("run_pipeline.py", root, "--skip-download", "--allow-missing-index")
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]
    f = xr.open_dataset(root / "data/processed/module0/greenscope_final_causal_cube.nc")
    assert int(f.attrs["boundary_cells_kept"]) > 0 and int(f.attrs["boundary_cells_dropped"]) > 0
    assert "centre-in-polygon" in f.attrs["mask_rule"]
    t3 = pd.read_csv(root / "data/processed/module0/figures/table3_ndvi_quality.csv")
    assert len(t3) == 3 and t3.cell_months_used_pct.iloc[0] == 100

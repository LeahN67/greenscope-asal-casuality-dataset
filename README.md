# GreenScope ASAL Causal Data Cube

A reproducible pipeline that builds a monthly, 0.05 degree climate and vegetation data cube for the 23 Arid and Semi-Arid Land (ASAL) counties of Kenya. It combines five public datasets on one grid and one monthly time axis, masked to the ASAL county polygons, and records a hypothesised driver, mediator and response ordering of the variables in the file itself. The cube is designed to support causal discovery and lagged analysis of how ocean-atmosphere drivers propagate through rainfall and soil moisture to vegetation.

The causal ordering is a structural prior that narrows which relationships are plausible. It does not by itself show that any relationship is causal.

## What the pipeline produces

`data/processed/module0/greenscope_final_causal_cube.nc`, a NetCDF4 file with six analysis variables and two ancillary variables:

| Variable | Source | Units | Dimensions | Causal layer and role |
|---|---|---|---|---|
| `enso_nino34` | Nino 3.4 SST (ERSSTv5, NOAA CPC), converted to anomaly against 1991-2020 | degC | time | A, global driver |
| `iod_dmi` | Dipole Mode Index (HadISST, NOAA PSL) | degC | time | A, global driver |
| `precipitation` | CHIRPS v2.0 monthly | mm/month | time, latitude, longitude | B, local driver |
| `potential_evaporation` | ERA5-Land monthly means | mm/day | time, latitude, longitude | B, local stressor |
| `soil_moisture` | ERA5-Land volumetric soil water, layer 1 (0-7 cm) | m3 m-3 | time, latitude, longitude | B, mediator |
| `ndvi` | MODIS MOD13A3 v061, monthly 1 km NDVI, averaged over all pixels in each cell | 1 | time, latitude, longitude | C, response |
| `ndvi_good_fraction` | MODIS VI_Quality: share of the cell's pixels with good quality flags | 1 | time, latitude, longitude | ancillary (no causal role) |
| `asal_mask` | 1 where the cell centre lies inside the ASAL polygon | 1 | latitude, longitude | ancillary (no causal role) |

The two indices hold one regional value per month. xarray broadcasts them against the gridded variables automatically, so `cube.ndvi * cube.enso_nino34` works without reshaping.

Every analysis variable carries `units`, `long_name`, `causal_layer` and `causal_role` attributes. Grid cells outside the ASAL polygon are missing in every gridded variable (`--no-mask` keeps the full bounding box). The file's global attributes record the input files with their SHA-256 checksums, the source URLs, the exact ERA5-Land and AppEEARS requests, quality-control counts and the processing steps applied; `ndvi_input_files.csv` lists the checksum of every NDVI input file.

## Quick start

```bash
git clone https://github.com/LeahN67/greenscope-asal-casuality-dataset.git
cd greenscope-asal-casuality-dataset
python -m venv venv
# Windows: venv\Scripts\activate      Linux/macOS: source venv/bin/activate
pip install -r requirements.txt
pytest -q tests                        # offline check that the pipeline works on this machine
```

Set your credentials (see below), then run everything from the repository root:

```bash
python run_pipeline.py
```

The MODIS step submits a request to NASA AppEEARS that can take several hours to process. If you stop the script while it waits, run `python run_pipeline.py --from modis` later: it continues the saved request instead of submitting a new one.

## Credentials

Two of the five sources need a free account. The scripts read credentials from environment variables, so no key is written into the code.

| Source | Account | What to set |
|---|---|---|
| ERA5-Land | Copernicus Climate Data Store, and accept the ERA5-Land licence on its dataset page | `CDSAPI_KEY` (your personal access token), or a `~/.cdsapirc` file |
| MODIS NDVI | NASA Earthdata | `EARTHDATA_USERNAME` and `EARTHDATA_PASSWORD`, or type them when prompted |

Windows PowerShell:

```powershell
$env:CDSAPI_KEY = "your-token"
$env:EARTHDATA_USERNAME = "your-username"
$env:EARTHDATA_PASSWORD = "your-password"
```

Linux or macOS: `export CDSAPI_KEY=your-token` and so on. Never commit a `.cdsapirc` or `.env` file; both are in `.gitignore`.

## Pipeline steps

Each step is a script you can also run on its own. Download steps skip files that already exist.

| Step | Script | Output |
|---|---|---|
| 1 | `scripts/create_asal_boundaries.py` | `data/raw/boundaries/asal_boundary.geojson` (23 counties, dissolved) |
| 2 | `scripts/fetch_chirps.py` | `data/raw/chirps/monthly/chirps-v2.0.monthly.nc` (global, several GB) |
| 3 | `scripts/fetch_era5.py` | `data/raw/era5_land/era5_land_monthly.nc` (2000-2025) |
| 4 | `scripts/fetch_enso.py`, `scripts/fetch_iod.py` | `data/raw/enso/nino34.txt`, `data/raw/iod/dmi_noaa.txt` |
| 5 | `scripts/fetch_modis_ndvi.py` | `data/raw/modis_ndvi_monthly/*.tif` (February 2000 to December 2025) |
| 6 | `scripts/convert_modis_ndvi.py` | `data/raw/modis_ndvi_monthly/ndvi/*.nc` (NDVI and VI_Quality per date) |
| 7 | `scripts/data_cube.py` | `data/processed/module0/module0_asal_datacube.nc`, `ndvi_input_files.csv` |
| 8 | `scripts/causal_integration.py` | `data/processed/module0/greenscope_final_causal_cube.nc` |
| 9 | `scripts/check_cube.py` | `data/processed/module0/cube_report.txt` |
| 10 | `scripts/make_figures.py` | `data/processed/module0/figures/` (maps, time series, lag correlations, Table 2, `paper_numbers.txt`) |

Every download is logged with its source, size and SHA-256 checksum in `data/raw/download_manifest.csv`. Downloads resume after interruption and retry with exponential backoff.

Useful options:

```bash
python run_pipeline.py --skip-download          # steps 6 to 10 only, on data already downloaded
python run_pipeline.py --from data_cube         # restart from a given step
python run_pipeline.py --allow-missing-index    # see "Index gaps" below
python scripts/<script>.py --help               # options for any single step
```

### Index gaps

The Dipole Mode Index is published with a lag, so its latest months are often missing (coded -9999). By default `causal_integration.py` stops and lists the cube months that have no index value, rather than filling them. Download the index again, or rerun with `--allow-missing-index` to keep those months as missing values; they are then listed in the variable's `missing_months` attribute.

## Checking the result

`check_cube.py` compares every variable with a plausible physical range and writes `cube_report.txt`. A FAIL means the cube should not be analysed until the cause is found. It also warns when the record is shorter than 120 months, which gives little statistical power for lagged causal analysis.

The cube builder refuses NDVI values that pile up on a few codes. This is the signature of the MODIS VI_Quality layer having been converted in place of NDVI, a mistake that is easy to make because AppEEARS delivers both layers into the same folder.

## Design choices and limitations

- **Spatial extent.** Every gridded variable is kept only in cells whose centre lies inside the dissolved polygon of the 23 ASAL counties (`asal_mask`). Cells straddling the boundary are kept or dropped by their centre. Whole counties are used, which includes humid upland parts of counties such as Meru, Embu and Nyeri. `--no-mask` produces the bounding-box version.
- **Regridding.** NDVI is the mean of all MODIS pixels whose centres fall in each 0.05 degree cell (about 36 pixels for 1 km data). ERA5-Land (0.1 degree) is coarser than the grid and is linearly interpolated onto it, which adds no information below its native resolution.
- **NDVI quality.** NDVI is not screened. Masking cloud-affected pixels would remove data mainly in rainy months, making the gaps depend on rainfall and biasing lagged analyses. Instead `ndvi_good_fraction` records, for every cell and month, the share of pixels whose VI_Quality flags mark them as good, so users can filter or weight observations themselves.
- **Time span.** Only months present in every input are kept. With the default downloads this is February 2000 to the latest month available in all sources.
- **Potential evaporation.** ERA5-Land monthly means of accumulated variables are mean daily totals; the sign is reversed so evaporation is positive, and values are converted to mm/day.
- **Causal ordering.** ENSO and IOD are treated as external drivers, although they are themselves statistically related. Land management, grazing pressure and fire are not in the cube and act as unobserved confounders for any causal analysis.

## Exploratory analysis

`eda/` holds exploratory scripts for CHIRPS, ENSO and IOD. `python eda/chirps_eda.py` analyses the precipitation in the final cube by default. These scripts are not part of the cube build.

## Tests

```bash
pytest -q tests
```

The tests create small synthetic inputs in the same formats as the real downloads (NetCDF, AppEEARS GeoTIFFs with both NDVI and quality layers, NOAA PSL text files with headers, footers and -9999 codes) and run the pipeline end to end. They need no network access or credentials. They also check the two failure modes this pipeline previously had (index files parsed one year out of step, and quality codes converted as NDVI), that every variable is masked to the ASAL polygon, and that the NDVI area average counts every pixel once.

## Repository layout

```
run_pipeline.py            runs steps 1 to 9 in order
scripts/gs_common.py       paths, causal registry, download and checksum helpers
scripts/                   one script per step (see table above)
eda/                       exploratory analysis
tests/test_pipeline.py     offline end-to-end tests
requirements.txt
```

To keep data somewhere other than the repository, set `GREENSCOPE_PROJECT_ROOT` to that folder; all `data/` paths are resolved from it.

## Data sources

- Funk, C. et al. (2015). The climate hazards infrared precipitation with stations, a new environmental record for monitoring extremes. *Scientific Data* 2, 150066.
- Munoz-Sabater, J. et al. (2021). ERA5-Land: a state-of-the-art global reanalysis dataset for land applications. *Earth System Science Data* 13, 4349-4383.
- Didan, K. (2021). MODIS/Terra Vegetation Indices Monthly L3 Global 1km SIN Grid V061 (MOD13A3). NASA LP DAAC. Accessed through AppEEARS.
- Huang, B. et al. (2017). Extended Reconstructed Sea Surface Temperature, Version 5 (ERSSTv5). *Journal of Climate* 30, 8179-8205.
- Saji, N. H. et al. (1999). A dipole mode in the tropical Indian Ocean. *Nature* 401, 360-363. DMI from NOAA PSL using HadISST (Rayner, N. A. et al., 2003, *Journal of Geophysical Research* 108, 4407).
- County boundaries: geoBoundaries (gbOpen, KEN ADM1), with GADM 4.1 as fallback.

Each source keeps its own licence and citation requirements.

## Citation

Njuguna, L. H. (2026). GreenScope ASAL Causal Data Cube: pipeline for a causally structured climate and vegetation data cube for Kenya's Arid and Semi-Arid Lands. GitHub. https://github.com/LeahN67/greenscope-asal-casuality-dataset

## License

Apache-2.0. See `LICENSE`.

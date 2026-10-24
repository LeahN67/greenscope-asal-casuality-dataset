# An ASAL Causal Data Cube

A reproducible pipeline that builds a monthly, 0.05 degree climate and vegetation data cube for the 23 Arid and Semi-Arid Land (ASAL) counties of Kenya. It combines five public environmental datasets, together with county boundary data, on one grid and one monthly time axis, masked to the ASAL county polygons, and records a hypothesised driver, mediator and response ordering of the variables in the file itself. The cube is designed to support causal discovery and lagged analysis of how ocean-atmosphere drivers propagate through rainfall and soil moisture to vegetation.

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
| `ndvi_good_fraction` | MODIS VI_Quality: monthly mean share of the cell's valid-NDVI pixels whose MODLAND bits are 00 or 01 (missing flags count as not usable) | 1 | time, latitude, longitude | ancillary (no causal role) |
| `asal_mask` | 1 where the cell centre lies inside the ASAL polygon | 1 | latitude, longitude | ancillary (no causal role) |

The two indices hold one regional value per month. xarray broadcasts them against the gridded variables automatically, so `cube.ndvi * cube.enso_nino34` works without reshaping.

Every analysis variable carries `units`, `long_name`, `causal_layer` and `causal_role` attributes. Grid cells outside the ASAL polygon are missing in every gridded variable (`--no-mask` keeps the full bounding box). The file's global attributes record the input files with their SHA-256 checksums, the source URLs, the exact ERA5-Land and AppEEARS requests, quality-control counts and the processing steps applied; `ndvi_input_files.csv` lists the checksum of every NDVI input file.

## Quick start

```bash
git clone https://github.com/LeahN67/asal-causality-dataset.git
cd asal-causality-dataset
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
| 3 | `scripts/fetch_era5.py` | `data/raw/era5_land/era5_land_monthly.nc` (2000-2025, with September 2022 to February 2024 corrected; see below) |
| 4 | `scripts/fetch_enso.py`, `scripts/fetch_iod.py` | `data/raw/enso/nino34.txt`, `data/raw/iod/dmi_noaa.txt` |
| 5 | `scripts/fetch_modis_ndvi.py` | `data/raw/modis_ndvi_monthly/*.tif` (February 2000 to December 2025) |
| 6 | `scripts/convert_modis_ndvi.py` | `data/raw/modis_ndvi_monthly/ndvi/*.nc` (NDVI and VI_Quality per date) |
| 7 | `scripts/data_cube.py` | `data/processed/module0/module0_asal_datacube.nc`, `ndvi_input_files.csv` |
| 8 | `scripts/causal_integration.py` | `data/processed/module0/greenscope_final_causal_cube.nc` |
| 9 | `scripts/check_cube.py` | `data/processed/module0/cube_report.txt` |
| 10 | `scripts/make_figures.py` | `data/processed/module0/figures/` (maps, time series, lag correlations, Table 2, NDVI quality sensitivity table, `paper_numbers.txt`) |

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

`check_cube.py` compares every variable with a plausible physical range and writes `cube_report.txt`. A FAIL means the cube should not be analysed until the cause is found. It also warns when the record is shorter than 120 months, which gives little statistical power for lagged causal analysis, when potential evaporation exceeds 25 mm/day (values the source delivers in hot, windy lowlands; kept, but reported), and when the ASAL mean of any gridded variable stays more than two standard deviations from its calendar-month mean for six or more consecutive months. That last check catches level shifts in a source product, which pass every range check.

The cube builder refuses NDVI values that pile up on a few codes. This is the signature of the MODIS VI_Quality layer having been converted in place of NDVI, a mistake that is easy to make because AppEEARS delivers both layers into the same folder.

## Design choices and limitations

- **Spatial extent.** Every gridded variable is kept only in cells whose centre lies inside the dissolved polygon of the 23 ASAL counties (`asal_mask`). Cells straddling the boundary are kept or dropped by their centre (a centre-in-polygon rule); the numbers kept and dropped are recorded in the cube attributes `boundary_cells_kept` and `boundary_cells_dropped`. Whole counties are used, which includes humid upland parts of counties such as Meru, Embu and Nyeri. `--no-mask` produces the bounding-box version.
- **Regridding.** NDVI is the unweighted mean of all MODIS pixels whose centres fall in each 0.05 degree cell (about 36 pixels for 1 km data); pixel areas within a cell differ by less than 0.01%, so this is effectively an area-weighted mean. Both grids must be regular and monotonic, which the builder checks. ERA5-Land (0.1 degree) is coarser than the grid and is linearly interpolated onto it for alignment only; its effective resolution remains 0.1 degree.
- **NDVI quality.** NDVI is not screened. Masking cloud-affected pixels would remove data mainly in rainy months, making the gaps depend on rainfall and biasing lagged analyses. Instead `ndvi_good_fraction` records, for every cell and month, the share of pixels whose VI_Quality flags mark them as good, so users can filter or weight observations themselves. `make_figures.py` reports how NDVI and the precipitation-to-NDVI lag change under no filtering, a 0.5 threshold and quality weighting (`table3_ndvi_quality.csv`).
- **Time span.** Only months present in every input are kept. With the default downloads this is February 2000 to the latest month available in all sources.
- **Potential evaporation.** ERA5-Land monthly means of accumulated variables are mean daily totals; the sign is reversed so evaporation is positive, and values are converted to mm/day. It is a potential rate from the land surface model and runs above reference evapotranspiration in hot, windy drylands; treat it as an index of atmospheric demand.
- **ERA5-Land correction, September 2022 to February 2024.** ECMWF has documented that every accumulated variable in the ERA5-Land `monthly_averaged_reanalysis` product is wrong for these 18 months and will not be replaced ([ECMWF Forum](https://forum.ecmwf.int/t/issue-affecting-era5-land-monthly-averaged-reanalysis-for-the-period-september-2022-to-february-2024/2370)); potential evaporation drops to about half. `fetch_era5.py` downloads ECMWF's recommended replacement, the `monthly_averaged_reanalysis_by_hour_of_day` product at 00:00, for those months only, writes it into the file and records the change in the file attribute `greenscope_accumulated_fix`. If you already have an uncorrected file, running `python scripts/fetch_era5.py` corrects it in place. `data_cube.py` refuses an uncorrected file. Soil moisture is not accumulated and is unaffected.
- **Inland water.** Lake Turkana and smaller water bodies inside the ASAL counties are part of the mask. Their cells have NDVI near zero and water-surface potential evaporation; exclude them with a threshold on long-term mean NDVI or an external water mask if needed.
- **ENSO baseline.** The Nino 3.4 anomaly is computed from the ERSSTv5 absolute series against one fixed 1991-2020 calendar-month mean, the current WMO standard normal period. NOAA CPC's Oceanic Nino Index uses centred 30-year base periods updated every five years and is now based on ERSSTv6, and CPC's official monitoring uses the Relative Oceanic Nino Index (RONI). Values in the cube are therefore close to, but not identical with, published ONI or RONI values, and a fixed base period leaves any long-term warming trend in the anomaly. For analyses sensitive to long-term sea surface temperature trends, remove the linear trend from `enso_nino34`, use a rolling baseline, or interpret the variable as combining interannual variability with long-term tropical warming.
- **Causal ordering.** ENSO and IOD are treated as external drivers, although they are themselves statistically related. Land management, grazing pressure and fire are not in the cube and act as unobserved confounders for any causal analysis.

## Exploratory analysis

`eda/` holds exploratory scripts for CHIRPS, ENSO and IOD. `python eda/chirps_eda.py` analyses the precipitation in the final cube by default. These scripts are not part of the cube build.

## Tests

```bash
pytest -q tests
```

The tests create small synthetic inputs in the same formats as the real downloads (NetCDF, AppEEARS GeoTIFFs with both NDVI and quality layers, NOAA PSL text files with headers, footers and -9999 codes) and run the pipeline end to end. They need no network access or credentials. They also check the two failure modes this pipeline previously had (index files parsed one year out of step, and quality codes converted as NDVI), that every variable is masked to the ASAL polygon, that the NDVI area average counts every pixel once, that the ERA5-Land correction replaces exactly the 18 flagged months, and that the cube builder refuses an uncorrected ERA5-Land file.

## Repository layout

```
run_pipeline.py            runs steps 1 to 10 in order
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

Njuguna, L. H. (2026). ASAL Causal Data Cube: pipeline for a causally structured climate and vegetation data cube for Kenya's Arid and Semi-Arid Lands. GitHub. https://github.com/LeahN67/asal-causality-dataset

## License

Apache-2.0. See `LICENSE`.

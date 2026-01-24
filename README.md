# GreenScope ASAL Causal Data Cube (Module 0)

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)

**Infrastructure Test Project: Validating Causal-Ready Data Pipelines for Kenya's ASALs**

## 📌 Overview

This repository serves as a **technical validation project** for the [GreenScope Analytics](https://greenscopeanalytics.com/) platform. It demonstrates how to transform fragmented, multi-source environmental data into a **certified 3D Data Cube** specifically designed for Kenya's Arid and Semi-Arid Lands (ASALs).

The project focuses on **Module 0: Data Capture & Readiness**, implementing the "Last Mile" of climate data engineering where raw datasets become analysis-ready, causally-structured data products.

---

## 🎯 Key Features

- ✅ **Fully Automated Pipeline** - From raw data to analysis-ready cube
- ✅ **Causal Structure** - Variables organized by causal hierarchy (Drivers → Stressors → Responses)
- ✅ **Multi-Source Integration** - Harmonizes CHIRPS, ERA5, MODIS, ENSO, and IOD data
- ✅ **Production Ready** - Includes error handling, logging, and resume capability
- ✅ **Reproducible** - All paths configurable, no hardcoded values
- ✅ **Open Source** - Apache 2.0 license, community contributions welcome

---

## 🏗️ GreenScope Infrastructure Principles

As a test project for the GreenScope platform, this pipeline validates four core infrastructure pillars:

### 1. **Causal Admissibility**
Variables are tiered (Global Drivers → Local Stressors → Ecosystem Responses) to prevent impossible causal loops and ensure scientifically valid inference.

### 2. **Physical Integrity**
"Sanity Gates" enforce real-world physical bounds (e.g., non-negative rainfall, NDVI within [-0.2, 1.0]) to catch data corruption early.

### 3. **Auditability**
SHA-256 checksums and immutable logging create a transparent data provenance record for every download and transformation.

### 4. **Interoperability**
Harmonizes different spatial resolutions (CHIRPS 0.05°, MODIS 250m, ERA5 0.1°) into a unified, analysis-ready grid using bilinear interpolation.

---

## 🧱 Causal Registry

This project implements the GreenScope **Layered Causal Registry**, which defines the role of each variable prior to ingestion:

| Layer | Type | Variable | Dataset Source | Spatial Res. | Temporal Res. | Platform Role |
|-------|------|----------|----------------|--------------|---------------|---------------|
| **Layer A** | **Global Driver** | ENSO (Niño 3.4) | NOAA ERSSTv5 | Global | Monthly | External Forcing |
| **Layer A** | **Global Driver** | IOD (DMI) | NOAA PSL | Global | Monthly | External Forcing |
| **Layer B** | **Local Stressor** | Precipitation | CHIRPS v2.0 | 0.05° (~5km) | Monthly | Primary Input |
| **Layer B** | **Mediator** | Potential Evaporation | ERA5-Land | 0.1° (~9km) | Monthly | System Process |
| **Layer B** | **Mediator** | Soil Moisture | ERA5-Land | 0.1° (~9km) | Monthly | System Buffer |
| **Layer C** | **Response** | NDVI | MODIS MOD13Q1 | 250m | 16-day | Observed Impact |

---

## 🚀 Quick Start

### Prerequisites

- Python 3.8+
- NASA Earthdata account ([register here](https://urs.earthdata.nasa.gov/users/new))
- Copernicus CDS account for ERA5 ([register here](https://cds.climate.copernicus.eu/))

### Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/greenscope-asal-datacube.git
cd greenscope-asal-datacube

# Install dependencies
pip install -r requirements.txt

# Set up environment
export GREENSCOPE_PROJECT_ROOT=$(pwd)
export CDS_API_KEY="your_uid:your_api_key"
export NASA_EARTHDATA_USERNAME="your_username"
export NASA_EARTHDATA_PASSWORD="your_password"
```

### Basic Usage

```bash
# 1. Create study area boundary
python scripts/create_asal_boundaries.py

# 2. Download climate data
python scripts/fetch_chirps.py --format netcdf --non-interactive
python scripts/fetch_era5.py --variables soil_moisture potential_evaporation
python scripts/fetch_enso.py --index-type nino34
python scripts/fetch_iod.py --format txt

# 3. Download MODIS NDVI (interactive, requires NASA login)
python scripts/fetch_modis_ndvi.py --start-date 01-01-2020 --end-date 12-31-2025

# 4. Create unified data cube
python scripts/data_cube.py

# 5. Integrate global climate indices
python scripts/causal_integration.py
```

---

## 📁 Project Structure

```
greenscope-asal-datacube/
├── data/
│   ├── raw/                        # Raw downloaded data (gitignored)
│   │   ├── boundaries/             # Study area boundaries
│   │   ├── chirps/                 # Precipitation data
│   │   ├── era5_land/              # ERA5 soil moisture & evaporation
│   │   ├── modis_ndvi/             # MODIS vegetation indices
│   │   ├── enso/                   # ENSO indices
│   │   └── iod/                    # IOD indices
│   └── processed/                  # Processed data cubes
│       └── module0/                # Final causal data cube
├── scripts/
│   ├── create_asal_boundaries.py   # Download admin boundaries
│   ├── fetch_chirps.py             # Download CHIRPS precipitation
│   ├── fetch_era5.py               # Download ERA5-Land data
│   ├── fetch_enso.py               # Download ENSO indices
│   ├── fetch_iod.py                # Download IOD indices
│   ├── fetch_modis_ndvi.py         # Download MODIS NDVI
│   ├── data_cube.py                # Create unified data cube
│   ├── causal_integration.py       # Integrate global indices
│   └── unzip_era5.py               # Extract/validate ERA5 files
├── requirements.txt                # Python dependencies
├── README.md                       # This file
├── LICENSE                         # Apache 2.0 license
└── .gitignore                      # Git ignore rules
```

---

## 🛠️ Detailed Pipeline Workflow

### Phase 1: Data Acquisition (The Vault)

Automated scrapers fetch raw data, verify integrity via checksums, and store them in an immutable `/raw` directory.

```bash
# Download all required datasets
python scripts/create_asal_boundaries.py
python scripts/fetch_chirps.py --format netcdf
python scripts/fetch_era5.py
python scripts/fetch_enso.py
python scripts/fetch_iod.py
python scripts/fetch_modis_ndvi.py
```

**Features:**
- Resume capability for interrupted downloads
- Automatic retry with exponential backoff
- SHA-256 checksum validation
- Download logging with timestamps

### Phase 2: Spatial Harmonization (The Harmonizer)

The `data_cube.py` engine performs spatial re-gridding and temporal resampling:

```bash
python scripts/data_cube.py
```

**Processing Steps:**
1. Loads boundary and extracts bounding box
2. Spatially subsets all datasets to study area
3. Regrids ERA5 (0.1°) and MODIS (250m) to CHIRPS grid (0.05°)
4. Resamples MODIS from 16-day to monthly
5. Aligns all time dimensions to monthly frequency
6. Applies physical sanity checks (e.g., precipitation ≥ 0)
7. Exports to compressed NetCDF with optimal chunking

### Phase 3: Causal Integration (The Left-Join)

Performs a **Temporal Left Join**, broadcasting 1D global indices (ENSO/IOD) across the 3D spatial grid:

```bash
python scripts/causal_integration.py
```

This makes every pixel "causally aware" of global climate states, enabling downstream causal inference and machine learning.

---

## 📊 Final Output

The pipeline produces a **GreenScope-Certified Data Cube**:

**File:** `data/processed/module0/greenscope_final_causal_cube.nc`

**Specifications:**
- **Spatial Coverage:** Kenya ASAL counties (23 counties, ~500,000 km²)
- **Spatial Resolution:** 0.05° (~5.5 km)
- **Temporal Coverage:** 2000 - Present
- **Temporal Resolution:** Monthly
- **Variables:** 7 (2 drivers + 3 stressors/mediators + 1 response + 1 global index)
- **Format:** NetCDF4 with compression
- **Size:** ~50-200 MB (depending on time range)

**Usage Example:**

```python
import xarray as xr

# Load the data cube
ds = xr.open_dataset('data/processed/module0/greenscope_final_causal_cube.nc')

# Explore structure
print(ds)

# Access variables
precip = ds['precipitation']
ndvi = ds['ndvi']
enso = ds['enso_nino34']

# Compute correlations
correlation = xr.corr(enso, ndvi.mean(dim=['latitude', 'longitude']))
```

---

## 🔧 Advanced Configuration

### Environment Variables

```bash
# Project root directory
export GREENSCOPE_PROJECT_ROOT=/path/to/project

# API credentials
export CDS_API_KEY="your_cds_uid:your_cds_key"
export NASA_EARTHDATA_USERNAME="your_nasa_username"
export NASA_EARTHDATA_PASSWORD="your_nasa_password"
```

### Custom Paths

All scripts accept custom paths via command-line arguments:

```bash
# Custom project root
python scripts/data_cube.py --project-root /custom/path

# Custom input/output paths
python scripts/data_cube.py \
  --chirps /path/to/chirps.nc \
  --era5 /path/to/era5.nc \
  --modis /path/to/modis \
  --boundary /path/to/boundary.geojson \
  --output-dir /path/to/output
```

### Custom Study Areas

Download boundaries for different countries or regions:

```bash
# Tanzania
python scripts/create_asal_boundaries.py --country TZA

# Custom county list
python scripts/create_asal_boundaries.py \
  --country KEN \
  --counties Turkana Marsabit Wajir
```

---

## 📚 Documentation

### Script Documentation

Each script has comprehensive help:

```bash
python scripts/data_cube.py --help
python scripts/fetch_chirps.py --help
```

### API Documentation

See individual script docstrings for programmatic usage:

```python
from scripts.data_cube import create_data_cube

# Create data cube programmatically
ds = create_data_cube(
    chirps_path='data/chirps.nc',
    era5_path='data/era5.nc',
    # ... other parameters
)
```

---

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

### Development Setup

```bash
# Clone and install in development mode
git clone https://github.com/yourusername/greenscope-asal-datacube.git
cd greenscope-asal-datacube
pip install -e .

# Run tests (if available)
pytest tests/
```

### Code Style

- Follow PEP 8 guidelines
- Use type hints where appropriate
- Add docstrings to all functions
- Keep functions focused and modular

---

## 📖 Citation

If you use this pipeline in your research, please cite:

```bibtex
@software{greenscope_asal_datacube,
  title = {GreenScope ASAL Causal Data Cube},
  author = {Your Name},
  year = {2024},
  url = {https://github.com/yourusername/greenscope-asal-datacube},
  license = {Apache-2.0}
}
```

---

## 🌍 About GreenScope Analytics

GreenScope is a data and AI infrastructure platform designed for climate and sustainability intelligence. We enable researchers and organizations to build decision-grade tools by providing a transparent, causal foundation for environmental data.

**Learn more at [greenscopeanalytics.com](https://greenscopeanalytics.com/)**

---

## 📄 License

This project is licensed under the **Apache License 2.0** - see the [LICENSE](LICENSE) file for details.

---

## 📧 Contact

For questions, collaborations, or feedback:

- **Email:** njugunalh@gmail.com
- **Website:** [greenscopeanalytics.com](https://greenscopeanalytics.com/)
- **Issues:** [GitHub Issues](https://github.com/yourusername/greenscope-asal-datacube/issues)

---

## 🙏 Acknowledgments

This project uses data from:

- **CHIRPS** - Climate Hazards Group, UC Santa Barbara
- **ERA5-Land** - European Centre for Medium-Range Weather Forecasts (ECMWF)
- **MODIS** - NASA Earth Observing System
- **ENSO/IOD Indices** - NOAA Physical Sciences Laboratory

---

*Built with ❤️ for the climate science community*
# GreenScope ASAL Causal Data Cube (Module 0)

**Infrastructure Test Project: Validating Causal-Ready Data Pipelines for Kenya's ASALs**

## 📌 Overview

This repository serves as a **technical validation project** for the [GreenScope Analytics](https://greenscopeanalytics.com/) platform.

The project focuses on **Module 0: Data Capture & Readiness**, demonstrating how the GreenScope infrastructure handles the "Last Mile" of climate data engineering. We transform fragmented, multi-source environmental data into a **certified 3D Data Cube** specifically for Kenya’s Arid and Semi-Arid Lands (ASALs).

---

## 🏗️ GreenScope Infrastructure Principles

As a test project for the GreenScope platform, this pipeline validates four core infrastructure pillars:

1. **Causal Admissibility**: Ensuring that variables are tiered (Global Drivers → Local Stressors → Ecosystem Responses) to prevent impossible causal loops.
2. **Physical Integrity**: Implementing "Sanity Gates" that enforce real-world physical bounds (e.g., non-negative rainfall).
3. **Auditability**: Using SHA-256 checksums and immutable logging to create a transparent data provenance record.
4. **Interoperability**: Harmonizing spatial resolutions (CHIRPS/MODIS/ERA5) into a unified, analysis-ready grid.

---

## 🧱 Causal Registry

This project implements the GreenScope **Layered Causal Registry**, which defines the role of each variable prior to ingestion:

| Layer | Type | Variable | Dataset Source | Platform Role |
| --- | --- | --- | --- | --- |
| **Layer A** | **Global Stressor** | ENSO (Nino 3.4) | NOAA ERSSTv5 | External Forcing |
| **Layer A** | **Global Stressor** | IOD (DMI) | NOAA PSL | External Forcing |
| **Layer B** | **Local Stressor** | Precipitation | CHIRPS v2.0 | Primary Input |
| **Layer B** | **Mediator** | Soil Moisture | ERA5-Land | System Buffer |
| **Layer C** | **Response** | NDVI | MODIS MOD13A1 | Observed Impact |

---

## 🛠️ Execution & Reproducibility

The pipeline is designed to be fully reproducible, simulating a GreenScope "Data Factory" environment.

### 1. Acquisition (The Vault)

Automated scrapers fetch raw data, verify integrity via checksums, and store them in an immutable `/raw` directory.

### 2. Processing (The Harmonizer)

The `data_cube.py` engine performs spatial re-gridding to 0.05° (~5km) and temporal resampling to a unified monthly frequency.

### 3. Integration (The Left-Join)

The pipeline performs a **Temporal Left Join**, broadcasting 1D global indices (ENSO/IOD) across the 3D spatial grid, making every pixel "causally aware" of global climate states.

---

## 📊 Final Artifact

The output is a **GreenScope-Certified Data Cube** (`greenscope_final_causal_cube.nc`):

* **Spatial Coverage**: Kenya ASAL Boundary.
* **Temporal Coverage**: 2000 – Present.
* **Variables**: Multi-layered (Drivers, Stressors, Mediators, Responses).

---

## 🌍 About GreenScope Analytics

GreenScope is a data and AI infrastructure platform designed for climate and sustainability intelligence. We enable researchers and organizations to build decision-grade tools by providing a transparent, causal foundation for environmental data.

**Learn more at [greenscopeanalytics.com**](https://greenscopeanalytics.com/)

## 📄 License

This test project is licensed under the **Apache License 2.0**.

---

*If you’re interested in collaborating or reviewing the approach, feel free to open an issue or start a discussion.*

# GreenScope ASAL Causal Data Cube  
**Foundational Climate Data Infrastructure for Kenya’s ASALs**

---

## 📌 Overview

This repository documents the **construction of a causal-ready climate data cube** for Kenya’s Arid and Semi-Arid Lands (ASALs).

The work is part of an **ongoing platform test for GreenScope Analytics**, focused on validating whether multi-source climate and environmental data can be integrated in a way that:

- preserves **causal directionality**
- respects **physical constraints**
- scales across space and time
- remains **auditable and reproducible**

This is **Module 0: Data Capture & Readiness** in the GreenScope platform.

---

## 🎯 Project Objective

The objective of this test project is to evaluate GreenScope’s ability to:

1. Integrate **global climate drivers** with **local environmental responses**
2. Harmonize datasets across **spatial, temporal, and resolution differences**
3. Produce a dataset suitable for **causal discovery**, not just prediction
4. Establish a repeatable pipeline for future regions and use cases

This repository focuses on the **process**, not downstream modeling results.

---

## 🧱 Causal Design Philosophy

Each dataset is assigned a **causal role before ingestion**, preventing post-hoc interpretation.

| Layer | Dataset | Role |
|------|--------|------|
| A | ENSO (Niño 3.4 Index) | Global climate driver |
| A | Indian Ocean Dipole (DMI) | Regional climate driver |
| B | CHIRPS Precipitation | Water input (stressor) |
| B | ERA5 PET | Atmospheric water demand |
| B | ERA5 Soil Moisture | Mediator |
| C | MODIS NDVI | Vegetation response |

This structure reflects the assumed **direction of influence**:
> Global climate → Local hydro-climate → Ecosystem response

---

## 🗺️ Spatial Scope

- Study area: **Kenya ASAL regions**
- Spatial masking is applied **before processing**
- Official ASAL boundaries are used
- Only spatially relevant data is loaded into memory

This ensures computational efficiency and causal relevance.

---

## ⏱️ Temporal Scope

- Monthly temporal resolution
- All datasets are aligned to a common timeline
- Lead–lag relationships are preserved
- No temporal aggregation is applied post-merge

---

## 📐 Spatial Harmonization

To avoid spatial bias:

- **CHIRPS** is used as the reference grid (highest spatial resolution)
- ERA5 and MODIS datasets are interpolated to the CHIRPS grid
- Bilinear interpolation is used for continuous variables
- No artificial sharpening or categorical smoothing

---

## 🧪 Physical & Statistical Sanity Checks

Before merging:

- Precipitation constrained to ≥ 0
- NDVI constrained to [-0.2, 1.0]
- Potential evapotranspiration treated as positive flux
- Variables cast to `float32` for efficiency
- Missing values tracked explicitly

These checks enforce physical plausibility.

---

## 🧩 Module 0 Output: Unified Causal Data Cube

The pipeline produces a single NetCDF file:

module0_asal_datacube.nc


**Dimensions**
- `time × latitude × longitude`

**Variables**
- `precipitation` (stressor)
- `potential_evaporation` (stressor)
- `soil_moisture` (mediator)
- `ndvi` (response)

This dataset is considered **causally admissible** and ready for downstream analysis.

---

## License

This project is licensed under the Apache License 2.0.  

---

## 📄 Disclaimer

This repository reflects **active platform development**.  
Methods, thresholds, and design choices may evolve as GreenScope Analytics matures.

---

## 🌍 About GreenScope Analytics

GreenScope Analytics is building decision-grade climate intelligence tools for resilience planning, adaptation, and sustainability — starting from **causal foundations**, not black-box models.

---

*If you’re interested in collaborating or reviewing the approach, feel free to open an issue or start a discussion.*

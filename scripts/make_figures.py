"""
Step 10. Figures, tables and numbers for the data article, computed from the final cube.

    python scripts/make_figures.py
    python scripts/make_figures.py --cube path/to/file.nc

Outputs in data/processed/module0/figures/:
  fig1_map.png             long-term mean NDVI inside the ASAL mask, with the county outline
  fig2_timeseries.png      ASAL-mean monthly series of the six variables
  fig3_lags.png            (a) lagged correlation of the Dipole Mode Index with ASAL-mean precipitation
                           anomalies, correctly aligned and with the index deliberately dated 12 months
                           late (the header-row error); (b) lagged correlation of precipitation with NDVI
  table2_summary.csv       minimum, median, maximum and missing share of every variable (inside the ASALs)
  fig3_lags.csv            the correlations behind Figure 3
  table3_ndvi_quality.csv  NDVI statistics and the precipitation-to-NDVI lag under three treatments of
                           cloud-affected pixels: none, cell-months with ndvi_good_fraction >= 0.5 only,
                           and ASAL means weighted by ndvi_good_fraction
  paper_numbers.txt        every number the data article needs, in one place

Area means use cos(latitude) weights over cells inside the ASAL mask. Anomalies are standardised by
calendar month over the full record. Correlations are Pearson coefficients on months where both
series have values; n is reported with each, and lags with fewer than 12 paired months are not plotted.
"""
import argparse
from pathlib import Path

import geopandas as gpd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import xarray as xr

from gs_common import BOUNDARY, FIGURES, FINAL_CUBE

INK, INK2, GRID = "#0b0b0b", "#52514e", "#e2e1dc"
SERIES_1, SERIES_2 = "#2a78d6", "#eb6834"          # validated categorical pair (blue, orange)
GRIDDED = ["precipitation", "potential_evaporation", "soil_moisture", "ndvi"]
INDICES = ["enso_nino34", "iod_dmi"]
LABELS = {"precipitation": "Precipitation (mm/month)", "potential_evaporation": "Potential evaporation (mm/day)",
          "soil_moisture": "Soil moisture, 0-7 cm (m3 m-3)", "ndvi": "NDVI",
          "enso_nino34": "Nino 3.4 anomaly (degC)", "iod_dmi": "Dipole Mode Index (degC)"}

plt.rcParams.update({
    "font.size": 8, "axes.edgecolor": INK2, "axes.labelcolor": INK, "xtick.color": INK2, "ytick.color": INK2,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6, "axes.spines.top": False,
    "axes.spines.right": False, "axes.titlesize": 8, "axes.titleweight": "bold", "axes.titlecolor": INK,
    "legend.frameon": False, "savefig.dpi": 300, "savefig.bbox": "tight",
})


def area_mean(ds, var, extra_weight=None, keep=None):
    """cos(latitude)-weighted mean over the ASAL mask; optional extra weight and cell-month filter."""
    w = np.cos(np.deg2rad(ds.latitude)).broadcast_like(ds[var])
    da = ds[var]
    if "asal_mask" in ds:
        da = da.where(ds["asal_mask"] == 1)
    if keep is not None:
        da = da.where(keep)
    if extra_weight is not None:
        w = w * extra_weight.fillna(0)
    return da.weighted(w.fillna(0)).mean(("latitude", "longitude")).to_series()


def standardised_anomaly(s):
    g = s.groupby(s.index.month)
    return (s - g.transform("mean")) / g.transform("std")


def lagged_corr(driver, response, max_lag):
    """Correlation of driver(t - lag) with response(t) for lag = 0..max_lag."""
    rows = []
    for lag in range(max_lag + 1):
        pair = pd.concat([driver.shift(lag), response], axis=1).dropna()
        r = pair.iloc[:, 0].corr(pair.iloc[:, 1]) if len(pair) > 2 else np.nan
        rows.append((lag, r, len(pair)))
    return pd.DataFrame(rows, columns=["lag_months", "r", "n"])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cube", default=str(FINAL_CUBE))
    ap.add_argument("--out", default=str(FIGURES))
    args = ap.parse_args()
    cube, out = Path(args.cube), Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    print("STEP 10  Figures and numbers for the data article")
    ds = xr.open_dataset(cube)
    t = pd.DatetimeIndex(ds.time.values)
    mask = ds["asal_mask"].values == 1 if "asal_mask" in ds else np.ones((ds.sizes["latitude"], ds.sizes["longitude"]), bool)

    # ---------------- Table 2
    rows = []
    for v in GRIDDED + INDICES + (["ndvi_good_fraction"] if "ndvi_good_fraction" in ds else []):
        vals = ds[v].values
        vals = vals[:, mask] if vals.ndim == 3 else vals
        f = vals[np.isfinite(vals)]
        rows.append({"variable": v, "units": ds[v].attrs.get("units", ""),
                     "min": f.min(), "median": np.median(f), "max": f.max(),
                     "missing_pct": 100 * float(np.isnan(vals).mean())})
    table = pd.DataFrame(rows)
    table.to_csv(out / "table2_summary.csv", index=False, float_format="%.4g")

    # ---------------- area means and anomalies
    series = {v: area_mean(ds, v) for v in GRIDDED}
    series.update({v: ds[v].to_series() for v in INDICES})
    anom = {v: standardised_anomaly(s) for v, s in series.items()}

    # ---------------- Figure 1: mean NDVI map
    gdf = gpd.read_file(BOUNDARY).to_crs("EPSG:4326") if BOUNDARY.exists() else None
    fig, ax = plt.subplots(figsize=(4.2, 4.6))
    mean_ndvi = ds["ndvi"].mean("time")
    im = ax.pcolormesh(ds.longitude, ds.latitude, mean_ndvi, cmap="Greens", vmin=0, vmax=max(0.6, float(mean_ndvi.max())),
                       shading="nearest")
    if gdf is not None:
        gdf.boundary.plot(ax=ax, color=INK, linewidth=0.6)
    ax.set_xlabel("Longitude (degrees E)")
    ax.set_ylabel("Latitude (degrees N)")
    ax.set_title(f"Mean NDVI, {t[0]:%b %Y} to {t[-1]:%b %Y}", loc="left")
    ax.set_aspect("equal")
    ax.grid(False)
    cb = fig.colorbar(im, ax=ax, shrink=0.7, pad=0.02)
    cb.set_label("NDVI", color=INK)
    cb.outline.set_edgecolor(INK2)
    fig.savefig(out / "fig1_map.png")
    plt.close(fig)

    # ---------------- Figure 2: ASAL-mean series, one panel per variable (no shared y-scale)
    order = INDICES + GRIDDED
    fig, axes = plt.subplots(len(order), 1, figsize=(7, 8), sharex=True)
    for ax, v in zip(axes, order):
        s = series[v]
        ax.plot(s.index, s.values, color=SERIES_1, linewidth=1)
        if v in INDICES:
            ax.axhline(0, color=INK2, linewidth=0.6)
        ax.set_title(("ASAL-mean " + LABELS[v][0].lower() + LABELS[v][1:]) if v in GRIDDED else LABELS[v], loc="left")
    axes[-1].set_xlabel("Month")
    fig.tight_layout()
    fig.savefig(out / "fig2_timeseries.png")
    plt.close(fig)

    # ---------------- Figure 3: lag structure, correct versus offset index
    precip = anom["precipitation"]
    dmi = series["iod_dmi"]
    dmi_offset = dmi.shift(12)                    # each value dated 12 months late, as the header-row error did
    lag_a = lagged_corr(dmi, precip, 12).assign(series="DMI correctly aligned")
    lag_b = lagged_corr(dmi_offset, precip, 12).assign(series="DMI dated 12 months late")
    lag_c = lagged_corr(precip, anom["ndvi"], 6).assign(series="Precipitation to NDVI")
    lags = pd.concat([lag_a, lag_b, lag_c])
    lags.to_csv(out / "fig3_lags.csv", index=False, float_format="%.4f")

    # ---------------- Table 3: sensitivity of NDVI to the treatment of cloud-affected pixels
    sens = []
    if "ndvi_good_fraction" in ds:
        gf = ds["ndvi_good_fraction"]
        inside = (ds["asal_mask"] == 1) if "asal_mask" in ds else xr.ones_like(gf, dtype=bool)
        valid = ds["ndvi"].notnull() & inside
        variants = {
            "no quality filtering": dict(),
            "cell-months with ndvi_good_fraction >= 0.5": dict(keep=gf >= 0.5),
            "weighted by ndvi_good_fraction": dict(extra_weight=gf),
        }
        for name, kw in variants.items():
            s_ndvi = area_mean(ds, "ndvi", **kw)
            kept = valid & kw["keep"] if "keep" in kw else valid
            d = lagged_corr(precip, standardised_anomaly(s_ndvi), 6)
            ok = d[d.n >= 12]
            best = ok.loc[ok.r.abs().idxmax()] if not ok.empty and ok.r.notna().any() else None
            sens.append({"treatment": name,
                         "asal_mean_ndvi_median": float(s_ndvi.median()),
                         "cell_months_used_pct": 100 * float(kept.sum()) / max(int(valid.sum()), 1),
                         "peak_lag_months": int(best.lag_months) if best is not None else np.nan,
                         "peak_r": float(best.r) if best is not None else np.nan})
        pd.DataFrame(sens).to_csv(out / "table3_ndvi_quality.csv", index=False, float_format="%.4g")

    fig, (a, b) = plt.subplots(1, 2, figsize=(7, 2.8))
    for d, color, style, label in [(lag_a, SERIES_1, "-", "Correctly aligned"),
                                   (lag_b, SERIES_2, "--", "Dated 12 months late")]:
        a.plot(d.lag_months, d.r.where(d.n >= 12), style, color=color, linewidth=2, marker="o", markersize=4, label=label)
    a.axhline(0, color=INK2, linewidth=0.6)
    a.set_xlabel("Lag: DMI leads precipitation (months)")
    a.set_ylabel("Correlation (r)")
    a.set_title("(a) DMI and precipitation anomaly", loc="left")
    a.set_xlim(-0.5, 12.5)
    b.plot(lag_c.lag_months, lag_c.r.where(lag_c.n >= 12), "-", color=SERIES_1, linewidth=2, marker="o", markersize=4)
    b.axhline(0, color=INK2, linewidth=0.6)
    b.set_xlabel("Lag: precipitation leads NDVI (months)")
    b.set_title("(b) Precipitation and NDVI anomaly", loc="left")
    fig.legend(*a.get_legend_handles_labels(), loc="lower left", bbox_to_anchor=(0.06, -0.02), ncol=2, fontsize=7)
    fig.tight_layout(rect=(0, 0.07, 1, 1))
    fig.savefig(out / "fig3_lags.png")
    plt.close(fig)

    # ---------------- numbers for the article
    def peak(d, min_n=12):
        d = d[d.n >= min_n].reset_index(drop=True)
        if d.empty or d.r.isna().all():
            return f"too few paired months (fewer than {min_n} at every lag)"
        i = d.r.abs().idxmax()
        return f"lag {int(d.lag_months[i])} months, r = {d.r[i]:.2f} (n = {int(d.n[i])})"

    lines = [
        f"Cube: {cube.name}, {cube.stat().st_size / 1e6:.1f} MB",
        f"Time: {t[0]:%B %Y} to {t[-1]:%B %Y}, {len(t)} months",
        f"Grid: {ds.sizes['latitude']} x {ds.sizes['longitude']} cells at 0.05 degree; "
        f"latitude {float(ds.latitude.min()):.3f} to {float(ds.latitude.max()):.3f}, "
        f"longitude {float(ds.longitude.min()):.3f} to {float(ds.longitude.max()):.3f}",
        f"ASAL cells: {int(mask.sum()):,} (about {ds.attrs.get('asal_area_km2', '?')} km2); "
        f"extent: {ds.attrs.get('spatial_extent', '?')}",
    ]
    for k in ("mask_rule", "boundary_cells_kept", "boundary_cells_dropped", "qc_ndvi_pixels_out_of_range", "qc_precipitation_negative_cells",
              "qc_pev_positive_cells_before_sign_reversal", "ndvi_regridding"):
        lines.append(f"{k}: {ds.attrs.get(k, 'not recorded')}")
    for v in INDICES:
        if ds[v].attrs.get("missing_months"):
            lines.append(f"{v} missing months: {ds[v].attrs['missing_months']}")
    lines += ["", "Table 2 (inside the ASAL mask):", table.to_string(index=False, float_format=lambda x: f"{x:.4g}"),
              "", "Figure 3 peaks (largest absolute correlation):",
              f"  DMI correctly aligned:      {peak(lag_a)}",
              f"  DMI dated 12 months late:   {peak(lag_b)}",
              f"  precipitation to NDVI:      {peak(lag_c)}"]
    if sens:
        lines += ["", "Table 3, NDVI under three treatments of cloud-affected pixels:",
                  pd.DataFrame(sens).to_string(index=False, float_format=lambda x: f"{x:.4g}")]
    (out / "paper_numbers.txt").write_text("\n".join(lines) + "\n")
    print("\n".join("   " + l for l in lines))
    print(f"\n   figures and tables saved in {out}")
    ds.close()


if __name__ == "__main__":
    main()

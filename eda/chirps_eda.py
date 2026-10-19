"""
GreenScope Analytics - CHIRPS v2.0 Exploratory Data Analysis
Streamlined version with smart error handling
"""

import xarray as xr
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
import pandas as pd
from scipy import stats
import warnings
warnings.filterwarnings('ignore')

plt.style.use('seaborn-v0_8-darkgrid')
sns.set_palette("husl")
plt.rcParams['figure.figsize'] = (14, 10)
plt.rcParams['font.size'] = 10

class CHIRPSExplorer:
    """Simplified CHIRPS EDA with robust handling for corrupted files"""
    
    def __init__(self, filepath):
        self.filepath = Path(filepath)
        self.ds = None
        self.precip = None
        self.use_sampling = False
        
    def load_data(self):
        """Load data without chunks to avoid HDF5 errors"""
        print("="*70)
        print("LOADING CHIRPS DATA")
        print("="*70)
        
        try:
            # Open WITHOUT chunks - this avoids the HDF5 compression error
            self.ds = xr.open_dataset(self.filepath)
            
            # Find precipitation variable
            precip_vars = [v for v in self.ds.data_vars if 'precip' in v.lower()]
            self.precip_var = precip_vars[0]
            self.precip = self.ds[self.precip_var]
            
            print(f"✓ Loaded: {self.precip_var}")
            print(f"✓ Shape: {self.precip.shape}")
            print(f"✓ Time: {self.ds.time.values[0]} to {self.ds.time.values[-1]}")
            return True
            
        except Exception as e:
            print(f"✗ Loading failed: {e}")
            return False
    
    def metadata(self):
        """Display basic information"""
        print("\n" + "="*70)
        print("DATASET OVERVIEW")
        print("="*70)
        
        # Get coordinates
        lat = self.ds.latitude.values if 'latitude' in self.ds.coords else self.ds.lat.values
        lon = self.ds.longitude.values if 'longitude' in self.ds.coords else self.ds.lon.values
        times = pd.to_datetime(self.ds.time.values)
        
        print(f"\n📐 Dimensions:")
        print(f"   Time:      {len(times)} months")
        print(f"   Latitude:  {len(lat)} ({lat.min():.2f}° to {lat.max():.2f}°)")
        print(f"   Longitude: {len(lon)} ({lon.min():.2f}° to {lon.max():.2f}°)")
        
        print(f"\n📅 Temporal:")
        print(f"   Start: {times[0].strftime('%Y-%m-%d')}")
        print(f"   End:   {times[-1].strftime('%Y-%m-%d')}")
        print(f"   Years: {(times[-1] - times[0]).days / 365.25:.1f}")
        
        print(f"\n💾 Storage:")
        print(f"   Type: {self.precip.dtype}")
        print(f"   Size: {self.filepath.stat().st_size / (1024**3):.2f} GB")
    
    def compute_stats_yearwise(self):
        """Compute statistics year-by-year to avoid memory issues"""
        print("\n" + "="*70)
        print("COMPUTING STATISTICS (YEAR-BY-YEAR)")
        print("="*70)
        
        times = pd.to_datetime(self.ds.time.values)
        years = sorted(set(times.year))
        
        all_means = []
        all_mins = []
        all_maxs = []
        
        print("\nProcessing years:")
        for year in years:
            try:
                # Load one year at a time
                yearly = self.ds.sel(time=str(year)).load()
                data = yearly[self.precip_var].values
                
                # Remove NaNs
                valid = data[~np.isnan(data)]
                
                if len(valid) > 0:
                    all_means.append(np.mean(valid))
                    all_mins.append(np.min(valid))
                    all_maxs.append(np.max(valid))
                
                print(f"   {year}: ✓")
                
            except Exception as e:
                print(f"   {year}: ✗ ({str(e)[:30]}...)")
                continue
        
        # Global statistics from yearly data
        if len(all_means) > 0:
            stats = {
                'Mean': np.mean(all_means),
                'Median': np.median(all_means),
                'Std Dev': np.std(all_means),
                'Min': np.min(all_mins),
                'Max': np.max(all_maxs),
            }
            
            print(f"\n📊 Global Statistics (mm/month):")
            for k, v in stats.items():
                print(f"   {k:12s}: {v:8.2f}")
            
            return stats
        else:
            print("\n⚠️  Could not compute statistics")
            return None
    
    def temporal_patterns(self):
        """Analyze temporal patterns using spatial means"""
        print("\n" + "="*70)
        print("TEMPORAL ANALYSIS")
        print("="*70)
        
        try:
            # Compute spatial mean for each timestep WITHOUT .compute()
            # This reads data but doesn't trigger chunked operations
            print("\nComputing time series (this may take a few minutes)...")
            
            times = pd.to_datetime(self.ds.time.values)
            means = []
            
            # Process in smaller batches
            batch_size = 12
            for i in range(0, len(times), batch_size):
                batch = self.precip.isel(time=slice(i, i+batch_size))
                batch_loaded = batch.load()
                batch_means = batch_loaded.mean(dim=['latitude', 'longitude']).values
                means.extend(batch_means)
                print(f"   Processed {min(i+batch_size, len(times))}/{len(times)} timesteps")
            
            # Create dataframe
            df = pd.DataFrame({'time': times, 'precip': means})
            df.set_index('time', inplace=True)
            
            # Annual stats
            annual = df.resample('YE')['precip'].agg(['mean', 'sum'])
            
            print(f"\n📈 Temporal Statistics:")
            print(f"   Mean monthly:    {df['precip'].mean():.2f} mm")
            print(f"   Mean annual:     {annual['sum'].mean():.1f} mm/year")
            print(f"   Driest year:     {annual['sum'].min():.1f} mm ({annual['sum'].idxmin().year})")
            print(f"   Wettest year:    {annual['sum'].max():.1f} mm ({annual['sum'].idxmax().year})")
            
            # Monthly climatology
            df['month'] = df.index.month
            monthly = df.groupby('month')['precip'].mean()
            
            print(f"\n🌦️  Seasonal:")
            print(f"   Wettest month:   {monthly.idxmax()} ({monthly.max():.1f} mm)")
            print(f"   Driest month:    {monthly.idxmin()} ({monthly.min():.1f} mm)")
            
            return df, monthly
            
        except Exception as e:
            print(f"\n⚠️  Temporal analysis failed: {e}")
            return None, None
    
    def spatial_patterns(self):
        """Compute spatial means"""
        print("\n" + "="*70)
        print("SPATIAL ANALYSIS")
        print("="*70)
        
        try:
            print("\nComputing long-term mean (processing in chunks)...")
            
            # Process year by year and average
            times = pd.to_datetime(self.ds.time.values)
            years = sorted(set(times.year))
            
            yearly_means = []
            for i, year in enumerate(years, 1):
                yearly = self.ds.sel(time=str(year)).load()
                yearly_mean = yearly[self.precip_var].mean(dim='time')
                yearly_means.append(yearly_mean)
                print(f"   Processed {i}/{len(years)} years")
            
            # Average all yearly means
            precip_mean = sum(yearly_means) / len(yearly_means)
            
            print(f"\n🗺️  Spatial Statistics:")
            print(f"   Range: {float(precip_mean.min()):.1f} - {float(precip_mean.max()):.1f} mm/month")
            print(f"   Mean:  {float(precip_mean.mean()):.1f} mm/month")
            
            return precip_mean
            
        except Exception as e:
            print(f"\n⚠️  Spatial analysis failed: {e}")
            return None
    
    def create_plots(self, df, monthly, spatial_mean):
        """Generate key visualizations"""
        print("\n" + "="*70)
        print("CREATING VISUALIZATIONS")
        print("="*70)
        
        if df is None:
            print("⚠️  Skipping - no temporal data")
            return
        
        fig, axes = plt.subplots(2, 3, figsize=(18, 10))
        
        # 1. Time series
        ax = axes[0, 0]
        df['precip'].plot(ax=ax, alpha=0.7, linewidth=0.8)
        df['precip'].rolling(12).mean().plot(ax=ax, color='red', linewidth=2, label='12-mo MA')
        ax.set_title('Precipitation Time Series', fontweight='bold')
        ax.set_ylabel('mm/month')
        ax.legend()
        ax.grid(alpha=0.3)
        
        # 2. Annual totals
        ax = axes[0, 1]
        annual = df.resample('YE')['precip'].sum()
        annual.plot(kind='bar', ax=ax, color='steelblue')
        ax.axhline(annual.mean(), color='red', linestyle='--', label=f'Mean: {annual.mean():.0f}')
        ax.set_title('Annual Precipitation', fontweight='bold')
        ax.set_ylabel('mm/year')
        ax.legend()
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=45)
        
        # 3. Monthly climatology
        ax = axes[0, 2]
        months = range(1, 13)
        ax.plot(months, monthly.values, 'o-', linewidth=2, markersize=8)
        ax.set_title('Monthly Climatology', fontweight='bold')
        ax.set_xlabel('Month')
        ax.set_ylabel('mm/month')
        ax.set_xticks(months)
        ax.set_xticklabels(['J','F','M','A','M','J','J','A','S','O','N','D'])
        ax.grid(alpha=0.3)
        
        # 4. Distribution
        ax = axes[1, 0]
        ax.hist(df['precip'].values, bins=50, edgecolor='black', alpha=0.7)
        ax.set_title('Precipitation Distribution', fontweight='bold')
        ax.set_xlabel('mm/month')
        ax.set_ylabel('Frequency')
        ax.grid(alpha=0.3)
        
        # 5. Box plot by month
        ax = axes[1, 1]
        df.boxplot(column='precip', by='month', ax=ax)
        ax.set_title('Monthly Variability', fontweight='bold')
        ax.set_xlabel('Month')
        ax.set_ylabel('mm/month')
        plt.sca(ax)
        plt.xticks(range(1, 13), ['J','F','M','A','M','J','J','A','S','O','N','D'])
        
        # 6. Spatial mean map
        ax = axes[1, 2]
        if spatial_mean is not None:
            spatial_mean.plot(ax=ax, cmap='YlGnBu', cbar_kwargs={'label': 'mm/month'})
            ax.set_title('Long-term Mean', fontweight='bold')
        else:
            ax.text(0.5, 0.5, 'Spatial analysis\nunavailable', 
                   ha='center', va='center', transform=ax.transAxes)
            ax.set_title('Spatial Mean (N/A)', fontweight='bold')
        
        plt.tight_layout()
        
        # Save
        output_dir = Path('reports/eda')
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / 'chirps_eda_summary.png'
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        print(f"\n✓ Saved: {output_path}")
        plt.show()
    
    def run(self):
        """Execute complete analysis"""
        print("\n")
        print("="*70)
        print("CHIRPS v2.0 EXPLORATORY DATA ANALYSIS")
        print("="*70)
        
        # Load
        if not self.load_data():
            print("\n❌ FAILED TO LOAD DATA")
            print("\nTroubleshooting:")
            print("  1. Check file exists")
            print("  2. Re-download from: https://data.chc.ucsb.edu/products/CHIRPS-2.0/")
            print("  3. Update libraries: pip install --upgrade xarray netCDF4")
            return
        
        # Metadata
        self.metadata()
        
        # Statistics
        stats = self.compute_stats_yearwise()
        
        # Temporal
        df, monthly = self.temporal_patterns()
        
        # Spatial
        spatial_mean = self.spatial_patterns()
        
        # Visualize
        self.create_plots(df, monthly, spatial_mean)
        
        # Summary
        print("\n" + "="*70)
        print("✅ ANALYSIS COMPLETE")
        print("="*70)
        print("\nOutputs:")
        print("  • Visualization: reports/eda/chirps_eda_summary.png")
        print("\nNext steps:")
        print("  • Review visualizations")
        print("  • Proceed with ERA5 and MODIS analysis")
        print("  • Begin causal inference modeling")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="CHIRPS EDA. Defaults to the precipitation in the ASAL cube; "
                                             "pass the raw global file only if you want global statistics.")
    ap.add_argument("path", nargs="?", default="data/processed/module0/greenscope_final_causal_cube.nc")
    explorer = CHIRPSExplorer(ap.parse_args().path)
    explorer.run()
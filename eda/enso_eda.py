"""
GreenScope Analytics - ENSO Niño 3.4 Index EDA
Analysis of Niño 3.4 SST anomalies for ASAL drought analysis
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
from scipy import stats
import warnings
warnings.filterwarnings('ignore')

plt.style.use('seaborn-v0_8-darkgrid')
sns.set_palette("husl")
plt.rcParams['figure.figsize'] = (16, 10)
plt.rcParams['font.size'] = 10

class NinoExplorer:
    """Exploratory Data Analysis for Niño 3.4 Index"""
    
    def __init__(self, filepath):
        self.filepath = Path(filepath)
        self.df = None
    
    def load_data(self):
        """Load Niño 3.4 data from NOAA PSL format"""
        print("="*70)
        print("LOADING NIÑO 3.4 DATA")
        print("="*70)
        
        if not self.filepath.exists():
            print(f"✗ File not found: {self.filepath}")
            return False
        
        try:
            # Read the file - NOAA PSL format is typically space-separated
            # Format: Year, then 12 monthly values
            with open(self.filepath, 'r') as f:
                lines = f.readlines()
            
            # Skip header lines (usually start with text)
            data_lines = []
            for line in lines:
                line = line.strip()
                if line and not line.startswith('#') and not line[0].isalpha():
                    data_lines.append(line)
            
            # Parse data
            # Check if data is absolute SST or anomaly by examining first few values
            
            records = []
            for line in data_lines:
                parts = line.split()
                if len(parts) >= 13:  # Year + 12 months
                    year = int(parts[0])
                    # NOAA missing codes include -99.99, -999 and -9999; treat anything <= -90 as missing
                    monthly_values = [float(x) if float(x) > -90 else np.nan for x in parts[1:13]]
                    
                    for month, value in enumerate(monthly_values, 1):
                        if not np.isnan(value):
                            date = pd.Timestamp(year=year, month=month, day=1)
                            records.append({'Date': date, 'Nino34': value})
            
            # Create initial dataframe
            self.df = pd.DataFrame(records)
            self.df.set_index('Date', inplace=True)
            self.df = self.df.sort_index()
            
            # Absolute SST (about 24 to 29 degC) rather than anomalies: convert to anomaly
            is_absolute_sst = self.df['Nino34'].median() > 15
            if is_absolute_sst:
                print(f"   Detected absolute SST values - computing anomalies...")
                # Climatology over 1991-2020, the same base period used for the cube
                base = self.df.loc['1991-01-01':'2020-12-31', 'Nino34']
                climatology = base.groupby(base.index.month).mean()
                # Subtract climatology from each value
                self.df['Nino34'] = self.df['Nino34'] - self.df.index.month.map(climatology)
                print(f"   ✓ Converted to anomalies (mean = {self.df['Nino34'].mean():.3f}°C)")
            
            
            print(f"✓ Loaded Niño 3.4 Index")
            print(f"✓ Records: {len(self.df)}")
            print(f"✓ Period: {self.df.index[0].strftime('%Y-%m')} to {self.df.index[-1].strftime('%Y-%m')}")
            print(f"✓ Missing: {self.df['Nino34'].isna().sum()} values")
            
            return True
            
        except Exception as e:
            print(f"✗ Error loading data: {e}")
            print("\nTrying alternative parsing method...")
            
            # Alternative: try reading as fixed-width or CSV
            try:
                self.df = pd.read_csv(self.filepath, sep=r'\s+', header=None, 
                                     skiprows=1, na_values=[-99.99, -999.00])
                
                # Reshape from wide to long
                self.df.columns = ['Year'] + list(range(1, 13))
                df_long = pd.melt(self.df, id_vars=['Year'], 
                                value_vars=range(1, 13),
                                var_name='Month', value_name='Nino34')
                
                df_long['Date'] = pd.to_datetime(df_long[['Year', 'Month']].assign(Day=1))
                df_long = df_long[['Date', 'Nino34']].dropna()
                df_long.set_index('Date', inplace=True)
                self.df = df_long.sort_index()
                
                print(f"✓ Loaded with alternative method")
                print(f"✓ Records: {len(self.df)}")
                print(f"✓ Period: {self.df.index[0].strftime('%Y-%m')} to {self.df.index[-1].strftime('%Y-%m')}")
                
                return True
                
            except Exception as e2:
                print(f"✗ Alternative method also failed: {e2}")
                return False
    
    def metadata(self):
        """Display dataset information"""
        print("\n" + "="*70)
        print("DATASET OVERVIEW")
        print("="*70)
        
        print(f"\n📊 Niño 3.4 Index (SST Anomaly):")
        print(f"   Source:      NOAA Physical Sciences Laboratory")
        print(f"   Region:      5°N-5°S, 120°-170°W (Central Pacific)")
        print(f"   Variable:    Sea Surface Temperature Anomaly (°C)")
        print(f"   Records:     {len(self.df)}")
        print(f"   Period:      {self.df.index[0].strftime('%Y-%m')} to {self.df.index[-1].strftime('%Y-%m')}")
        print(f"   Duration:    {(self.df.index[-1] - self.df.index[0]).days / 365.25:.1f} years")
        print(f"   Missing:     {self.df['Nino34'].isna().sum()} ({self.df['Nino34'].isna().sum()/len(self.df)*100:.2f}%)")
    
    def statistical_summary(self):
        """Compute comprehensive statistics"""
        print("\n" + "="*70)
        print("STATISTICAL SUMMARY")
        print("="*70)
        
        data = self.df['Nino34'].dropna()
        
        stats_dict = {
            'Mean': data.mean(),
            'Median': data.median(),
            'Std Dev': data.std(),
            'Min': data.min(),
            'Max': data.max(),
            'Q25': data.quantile(0.25),
            'Q75': data.quantile(0.75),
            'Skewness': data.skew(),
            'Kurtosis': data.kurtosis(),
            'Range': data.max() - data.min(),
            'IQR': data.quantile(0.75) - data.quantile(0.25)
        }
        
        print(f"\n📈 Basic Statistics (°C):")
        for key, value in stats_dict.items():
            print(f"   {key:12s}: {value:8.3f}")
        
        return stats_dict
    
    def enso_phases(self):
        """Classify ENSO phases and events"""
        print("\n" + "="*70)
        print("ENSO PHASE CLASSIFICATION")
        print("="*70)
        
        data = self.df['Nino34'].dropna()
        
        # Standard ONI thresholds (same as Niño 3.4 for most purposes)
        el_nino = (data >= 0.5).sum()
        la_nina = (data <= -0.5).sum()
        neutral = ((data > -0.5) & (data < 0.5)).sum()
        
        print(f"\n🌡️  Phase Distribution (threshold: ±0.5°C):")
        print(f"   El Niño:  {el_nino:5d} months ({el_nino/len(data)*100:5.1f}%)")
        print(f"   La Niña:  {la_nina:5d} months ({la_nina/len(data)*100:5.1f}%)")
        print(f"   Neutral:  {neutral:5d} months ({neutral/len(data)*100:5.1f}%)")
        
        # Strong events
        strong_el_nino = (data >= 1.5).sum()
        strong_la_nina = (data <= -1.5).sum()
        very_strong_el_nino = (data >= 2.0).sum()
        very_strong_la_nina = (data <= -2.0).sum()
        
        print(f"\n🔥 Event Intensity:")
        print(f"   Moderate El Niño (≥0.5°C):  {el_nino:5d} months")
        print(f"   Strong El Niño   (≥1.5°C):  {strong_el_nino:5d} months")
        print(f"   Very Strong      (≥2.0°C):  {very_strong_el_nino:5d} months")
        print(f"\n   Moderate La Niña (≤-0.5°C): {la_nina:5d} months")
        print(f"   Strong La Niña   (≤-1.5°C): {strong_la_nina:5d} months")
        print(f"   Very Strong      (≤-2.0°C): {very_strong_la_nina:5d} months")
        
        # Find extreme events
        print(f"\n🌊 Extreme Values:")
        print(f"   Warmest anomaly:  {data.max():+.2f}°C ({data.idxmax().strftime('%Y-%m')})")
        print(f"   Coldest anomaly:  {data.min():+.2f}°C ({data.idxmin().strftime('%Y-%m')})")
        
        # Recent major events
        recent = data[data.index >= '2000-01-01']
        recent_el_nino = recent[recent >= 1.5]
        recent_la_nina = recent[recent <= -1.5]
        
        if len(recent_el_nino) > 0:
            print(f"\n📅 Strong El Niño Events Since 2000:")
            years = recent_el_nino.index.year.unique()
            for year in sorted(years):
                year_data = recent_el_nino[recent_el_nino.index.year == year]
                print(f"   {year}: Max = {year_data.max():+.2f}°C")
        
        if len(recent_la_nina) > 0:
            print(f"\n❄️  Strong La Niña Events Since 2000:")
            years = recent_la_nina.index.year.unique()
            for year in sorted(years):
                year_data = recent_la_nina[recent_la_nina.index.year == year]
                print(f"   {year}: Min = {year_data.min():+.2f}°C")
    
    def temporal_analysis(self):
        """Analyze temporal patterns"""
        print("\n" + "="*70)
        print("TEMPORAL PATTERNS")
        print("="*70)
        
        data = self.df['Nino34'].dropna()
        
        # Seasonal cycle
        monthly_mean = data.groupby(data.index.month).mean()
        monthly_std = data.groupby(data.index.month).std()
        
        print(f"\n🌦️  Seasonal Cycle:")
        print(f"   Warmest month:  {monthly_mean.idxmax()} ({monthly_mean.max():+.3f}°C)")
        print(f"   Coolest month:  {monthly_mean.idxmin()} ({monthly_mean.min():+.3f}°C)")
        print(f"   Amplitude:      {monthly_mean.max() - monthly_mean.min():.3f}°C")
        
        # Annual statistics
        annual_mean = data.groupby(data.index.year).mean()
        annual_std = data.groupby(data.index.year).std()
        
        print(f"\n📊 Inter-annual Variability:")
        print(f"   Mean annual std: {annual_std.mean():.3f}°C")
        print(f"   Warmest year:    {annual_mean.idxmax()} ({annual_mean.max():+.2f}°C)")
        print(f"   Coolest year:    {annual_mean.idxmin()} ({annual_mean.min():+.2f}°C)")
        
        # Trend analysis
        x = np.arange(len(data))
        y = data.values
        slope, intercept, r_value, p_value, std_err = stats.linregress(x, y)
        
        trend_per_decade = slope * 120  # Monthly data -> 10 years
        
        print(f"\n📉 Long-term Trend:")
        print(f"   Slope:       {slope:.6f}°C/month")
        print(f"   Per decade:  {trend_per_decade:+.4f}°C")
        print(f"   R-squared:   {r_value**2:.4f}")
        print(f"   P-value:     {p_value:.4f}")
        
        if p_value < 0.05:
            direction = "warming" if slope > 0 else "cooling"
            print(f"   ⚠️  Significant {direction} trend detected!")
        else:
            print(f"   ✓ No significant trend")
        
        # Autocorrelation
        lag1_corr = data.autocorr(lag=1)
        lag3_corr = data.autocorr(lag=3)
        lag6_corr = data.autocorr(lag=6)
        
        print(f"\n🔄 Autocorrelation:")
        print(f"   Lag 1 month:  {lag1_corr:.3f}")
        print(f"   Lag 3 months: {lag3_corr:.3f}")
        print(f"   Lag 6 months: {lag6_corr:.3f}")
        print(f"   → High persistence indicates slow ENSO evolution")
        
        return monthly_mean, annual_mean
    
    def create_visualizations(self, monthly_mean, annual_mean):
        """Generate comprehensive visualizations"""
        print("\n" + "="*70)
        print("CREATING VISUALIZATIONS")
        print("="*70)
        
        fig = plt.figure(figsize=(18, 12))
        data = self.df['Nino34']
        
        # 1. Full time series
        ax1 = plt.subplot(3, 3, 1)
        data.plot(ax=ax1, linewidth=0.8, alpha=0.7, color='black')
        
        # Color code El Niño/La Niña
        el_nino_mask = data >= 0.5
        la_nina_mask = data <= -0.5
        ax1.fill_between(data.index, 0, data.values, 
                        where=el_nino_mask, color='red', alpha=0.3, label='El Niño')
        ax1.fill_between(data.index, 0, data.values,
                        where=la_nina_mask, color='blue', alpha=0.3, label='La Niña')
        
        ax1.axhline(0, color='black', linestyle='--', linewidth=0.5)
        ax1.axhline(0.5, color='red', linestyle=':', linewidth=0.5)
        ax1.axhline(-0.5, color='blue', linestyle=':', linewidth=0.5)
        ax1.set_title('Niño 3.4 Index Time Series', fontweight='bold', fontsize=12)
        ax1.set_ylabel('SST Anomaly (°C)')
        ax1.legend(loc='upper left')
        ax1.grid(alpha=0.3)
        
        # 2. Recent period (last 30 years)
        ax2 = plt.subplot(3, 3, 2)
        recent = data[data.index >= (data.index[-1] - pd.DateOffset(years=30))]
        recent.plot(ax=ax2, linewidth=1.2, color='black')
        
        el_nino_mask = recent >= 0.5
        la_nina_mask = recent <= -0.5
        ax2.fill_between(recent.index, 0, recent.values,
                        where=el_nino_mask, color='red', alpha=0.3)
        ax2.fill_between(recent.index, 0, recent.values,
                        where=la_nina_mask, color='blue', alpha=0.3)
        
        ax2.axhline(0, color='black', linestyle='--', linewidth=0.5)
        ax2.set_title('Last 30 Years', fontweight='bold', fontsize=12)
        ax2.set_ylabel('SST Anomaly (°C)')
        ax2.grid(alpha=0.3)
        
        # 3. Distribution
        ax3 = plt.subplot(3, 3, 3)
        ax3.hist(data.dropna(), bins=60, edgecolor='black', alpha=0.7, color='steelblue')
        ax3.axvline(0, color='black', linestyle='--', linewidth=2)
        ax3.axvline(0.5, color='red', linestyle=':', linewidth=1.5, label='El Niño threshold')
        ax3.axvline(-0.5, color='blue', linestyle=':', linewidth=1.5, label='La Niña threshold')
        ax3.set_title('Distribution', fontweight='bold', fontsize=12)
        ax3.set_xlabel('SST Anomaly (°C)')
        ax3.set_ylabel('Frequency')
        ax3.legend()
        ax3.grid(alpha=0.3)
        
        # 4. Seasonal cycle
        ax4 = plt.subplot(3, 3, 4)
        months = range(1, 13)
        monthly_std = data.groupby(data.index.month).std()
        ax4.plot(months, monthly_mean.values, 'o-', linewidth=2, markersize=8, color='darkblue')
        ax4.fill_between(months,
                        monthly_mean - monthly_std,
                        monthly_mean + monthly_std,
                        alpha=0.3, color='steelblue')
        ax4.axhline(0, color='black', linestyle='--', linewidth=0.5)
        ax4.set_title('Seasonal Cycle (Mean ± Std)', fontweight='bold', fontsize=12)
        ax4.set_xlabel('Month')
        ax4.set_ylabel('SST Anomaly (°C)')
        ax4.set_xticks(months)
        ax4.set_xticklabels(['J','F','M','A','M','J','J','A','S','O','N','D'])
        ax4.grid(alpha=0.3)
        
        # 5. Annual means
        ax5 = plt.subplot(3, 3, 5)
        annual_mean.plot(kind='bar', ax=ax5, color='steelblue', edgecolor='black', width=0.8)
        ax5.axhline(0, color='red', linestyle='--', linewidth=1)
        ax5.set_title('Annual Mean Values', fontweight='bold', fontsize=12)
        ax5.set_xlabel('Year')
        ax5.set_ylabel('SST Anomaly (°C)')
        ax5.grid(alpha=0.3, axis='y')
        plt.setp(ax5.xaxis.get_majorticklabels(), rotation=45)
        
        # 6. Phase distribution
        ax6 = plt.subplot(3, 3, 6)
        phases = pd.cut(data.dropna(), 
                       bins=[-np.inf, -0.5, 0.5, np.inf],
                       labels=['La Niña', 'Neutral', 'El Niño'])
        phase_counts = phases.value_counts()
        colors = ['blue', 'gray', 'red']
        phase_counts.plot(kind='bar', ax=ax6, color=colors, edgecolor='black')
        ax6.set_title('ENSO Phase Distribution', fontweight='bold', fontsize=12)
        ax6.set_xlabel('Phase')
        ax6.set_ylabel('Frequency (months)')
        ax6.set_xticklabels(ax6.get_xticklabels(), rotation=0)
        ax6.grid(alpha=0.3, axis='y')
        
        # 7. Box plot by month
        ax7 = plt.subplot(3, 3, 7)
        monthly_data = [data[data.index.month == m].dropna() for m in range(1, 13)]
        bp = ax7.boxplot(monthly_data, labels=['J','F','M','A','M','J','J','A','S','O','N','D'])
        ax7.axhline(0, color='black', linestyle='--', linewidth=0.5)
        ax7.axhline(0.5, color='red', linestyle=':', linewidth=0.5, alpha=0.5)
        ax7.axhline(-0.5, color='blue', linestyle=':', linewidth=0.5, alpha=0.5)
        ax7.set_title('Monthly Variability', fontweight='bold', fontsize=12)
        ax7.set_xlabel('Month')
        ax7.set_ylabel('SST Anomaly (°C)')
        ax7.grid(alpha=0.3)
        
        # 8. Rolling statistics
        ax8 = plt.subplot(3, 3, 8)
        data.plot(ax=ax8, alpha=0.2, label='Monthly', color='gray')
        data.rolling(12).mean().plot(ax=ax8, label='12-mo MA', linewidth=2, color='darkblue')
        data.rolling(12).std().plot(ax=ax8, label='12-mo Std', linewidth=2, 
                                    linestyle='--', color='darkred')
        ax8.axhline(0, color='black', linestyle='--', linewidth=0.5)
        ax8.set_title('Rolling Statistics', fontweight='bold', fontsize=12)
        ax8.set_ylabel('Value')
        ax8.legend()
        ax8.grid(alpha=0.3)
        
        # 9. Autocorrelation
        ax9 = plt.subplot(3, 3, 9)
        from pandas.plotting import autocorrelation_plot
        autocorrelation_plot(data.dropna(), ax=ax9)
        ax9.set_title('Autocorrelation Function', fontweight='bold', fontsize=12)
        ax9.set_xlabel('Lag (months)')
        ax9.set_ylabel('Autocorrelation')
        ax9.grid(alpha=0.3)
        
        plt.tight_layout()
        
        # Save
        output_dir = Path('reports/eda')
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / 'nino34_eda_summary.png'
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        print(f"\n✓ Saved: {output_path}")
        plt.show()
    
    def generate_report(self):
        """Generate markdown report"""
        print("\n" + "="*70)
        print("GENERATING REPORT")
        print("="*70)
        
        output_dir = Path('reports/eda')
        output_dir.mkdir(parents=True, exist_ok=True)
        report_path = output_dir / 'Nino34_EDA_Report.md'
        
        data = self.df['Nino34'].dropna()
        
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write("# Niño 3.4 Index - EDA Report\n\n")
            f.write(f"**Analysis Date**: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}\n\n")
            
            f.write("## Overview\n\n")
            f.write("The Niño 3.4 index is a measure of sea surface temperature (SST) anomalies ")
            f.write("in the central equatorial Pacific (5°N-5°S, 120°-170°W). It is the primary ")
            f.write("indicator used to monitor El Niño and La Niña events.\n\n")
            
            f.write("## Dataset Summary\n\n")
            f.write(f"- **Source**: NOAA Physical Sciences Laboratory (ERSSTv5)\n")
            f.write(f"- **Period**: {data.index[0].strftime('%Y-%m')} to {data.index[-1].strftime('%Y-%m')}\n")
            f.write(f"- **Duration**: {(data.index[-1] - data.index[0]).days / 365.25:.1f} years\n")
            f.write(f"- **Records**: {len(data)} monthly observations\n\n")
            
            el_nino = (data >= 0.5).sum()
            la_nina = (data <= -0.5).sum()
            neutral = ((data > -0.5) & (data < 0.5)).sum()
            
            f.write("## ENSO Phase Distribution\n\n")
            f.write(f"- **El Nino** (>=0.5 deg C): {el_nino} months ({el_nino/len(data)*100:.1f}%)\n")
            f.write(f"- **La Nina** (<=-0.5 deg C): {la_nina} months ({la_nina/len(data)*100:.1f}%)\n")
            f.write(f"- **Neutral**: {neutral} months ({neutral/len(data)*100:.1f}%)\n\n")
            
            f.write("## Key Statistics\n\n")
            f.write(f"- Mean: {data.mean():.3f} deg C\n")
            f.write(f"- Std Dev: {data.std():.3f} deg C\n")
            f.write(f"- Range: {data.min():.2f} deg C to {data.max():.2f} deg C\n\n")
            
            f.write("## Visualizations\n\n")
            f.write("![Niño 3.4 EDA](nino34_eda_summary.png)\n\n")
            
            f.write("## Key Findings\n\n")
            f.write("1. Clear alternation between El Niño and La Niña phases\n")
            f.write("2. Strong persistence/autocorrelation in ENSO states\n")
            f.write("3. Seasonal cycle influences ENSO development\n")
            f.write("4. Recent decades show several strong events\n\n")
            
            f.write("## Implications for Drought Analysis\n\n")
            f.write("- **El Niño years**: Often associated with above-average rainfall in East Africa\n")
            f.write("- **La Niña years**: Often associated with drought conditions in ASAL regions\n")
            f.write("- **Lag effects**: ENSO impacts typically lag SST anomalies by 1-3 months\n")
            f.write("- **Threshold effects**: Impacts strengthen with anomaly magnitude\n\n")
            
            f.write("## Recommendations for Causal Analysis\n\n")
            f.write("1. Use Niño 3.4 as primary ENSO covariate\n")
            f.write("2. Test multiple lag structures (0-6 months)\n")
            f.write("3. Consider categorical classification (El Niño/Neutral/La Niña)\n")
            f.write("4. Include interaction terms with seasonality\n")
            f.write("5. Account for ENSO phase transitions in model specification\n")
        
        print(f"✓ Saved: {report_path}")
    
    def run(self):
        """Execute complete EDA pipeline"""
        print("\n")
        print("="*70)
        print("NIÑO 3.4 INDEX - EXPLORATORY DATA ANALYSIS")
        print("="*70)
        
        # Load
        if not self.load_data():
            print("\n❌ FAILED TO LOAD DATA")
            return
        
        # Analysis
        self.metadata()
        self.statistical_summary()
        self.enso_phases()
        monthly_mean, annual_mean = self.temporal_analysis()
        
        # Visualize
        self.create_visualizations(monthly_mean, annual_mean)
        
        # Report
        self.generate_report()
        
        # Summary
        print("\n" + "="*70)
        print("✅ NIÑO 3.4 EDA COMPLETE")
        print("="*70)
        print("\nOutputs:")
        print("  • Visualization: reports/eda/nino34_eda_summary.png")
        print("  • Report: reports/eda/Nino34_EDA_Report.md")
        print("\nNext steps:")
        print("  • Merge with CHIRPS precipitation data")
        print("  • Test ENSO-drought lag relationships")
        print("  • Include in causal inference models")


if __name__ == "__main__":
    explorer = NinoExplorer("data/raw/enso/nino34.txt")
    explorer.run()
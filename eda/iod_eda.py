"""
GreenScope Analytics - IOD (Indian Ocean Dipole) Deep Dive EDA
Comprehensive analysis of Dipole Mode Index (DMI) for ASAL drought prediction
COMPLETE VERSION - Ready to run
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
from scipy import stats, signal
from scipy.fft import fft, fftfreq
import warnings
warnings.filterwarnings('ignore')

plt.style.use('seaborn-v0_8-darkgrid')
sns.set_palette("husl")
plt.rcParams['figure.figsize'] = (18, 12)
plt.rcParams['font.size'] = 10

class IODExplorer:
    """Deep exploratory analysis of Indian Ocean Dipole"""
    
    def __init__(self, filepath):
        self.filepath = Path(filepath)
        self.df = None
    
    def load_data(self):
        """Load DMI data from NOAA format"""
        print("="*80)
        print("LOADING IOD DIPOLE MODE INDEX (DMI)")
        print("="*80)
        
        if not self.filepath.exists():
            print(f"✗ File not found: {self.filepath}")
            return False
        
        try:
            with open(self.filepath, 'r') as f:
                lines = f.readlines()
            
            data_lines = []
            for line in lines:
                line = line.strip()
                if line and not line.startswith('#') and not line[0].isalpha():
                    data_lines.append(line)
            
            records = []
            for line in data_lines:
                parts = line.split()
                if len(parts) >= 13:
                    year = int(parts[0])
                    monthly_values = [float(x) if x not in ['-99.99', '-999.00', '-9.99'] else np.nan 
                                    for x in parts[1:13]]
                    
                    for month, value in enumerate(monthly_values, 1):
                        if not np.isnan(value):
                            date = pd.Timestamp(year=year, month=month, day=1)
                            records.append({'Date': date, 'DMI': value})
            
            self.df = pd.DataFrame(records)
            self.df.set_index('Date', inplace=True)
            self.df = self.df.sort_index()
            
            print(f"✓ Loaded IOD DMI")
            print(f"✓ Records: {len(self.df)}")
            print(f"✓ Period: {self.df.index[0].strftime('%Y-%m')} to {self.df.index[-1].strftime('%Y-%m')}")
            print(f"✓ Missing: {self.df['DMI'].isna().sum()} values")
            print(f"✓ Data range: {self.df['DMI'].min():.3f} to {self.df['DMI'].max():.3f}")
            return True
            
        except Exception as e:
            print(f"✗ Error loading data: {e}")
            print("\nTrying alternative parsing...")
            
            try:
                self.df = pd.read_csv(self.filepath, sep=r'\s+', header=None, 
                                     skiprows=1, na_values=[-99.99, -999.00, -9.99])
                
                self.df.columns = ['Year'] + list(range(1, 13))
                df_long = pd.melt(self.df, id_vars=['Year'], value_vars=range(1, 13),
                                var_name='Month', value_name='DMI')
                
                df_long['Date'] = pd.to_datetime(df_long[['Year', 'Month']].assign(Day=1))
                df_long = df_long[['Date', 'DMI']].dropna()
                df_long.set_index('Date', inplace=True)
                self.df = df_long.sort_index()
                
                print(f"✓ Loaded with alternative method")
                print(f"✓ Records: {len(self.df)}")
                return True
                
            except Exception as e2:
                print(f"✗ Alternative method failed: {e2}")
                return False
    
    def metadata(self):
        """Display comprehensive metadata"""
        print("\n" + "="*80)
        print("DATASET METADATA & CONTEXT")
        print("="*80)
        
        print(f"\n📊 Indian Ocean Dipole (IOD):")
        print(f"   Definition:  SST gradient between western (10S-10N, 50E-70E)")
        print(f"                and eastern (10S-0, 90E-110E) Indian Ocean")
        print(f"   Index:       Dipole Mode Index (DMI)")
        print(f"   Units:       Sea Surface Temperature anomaly difference (°C)")
        print(f"   Source:      NOAA Physical Sciences Laboratory")
        
        print(f"\n📅 Temporal Coverage:")
        print(f"   Start:       {self.df.index[0].strftime('%Y-%m')}")
        print(f"   End:         {self.df.index[-1].strftime('%Y-%m')}")
        print(f"   Duration:    {(self.df.index[-1] - self.df.index[0]).days / 365.25:.1f} years")
        print(f"   Records:     {len(self.df)} monthly observations")
        print(f"   Frequency:   Monthly")
        
        print(f"\n🔍 Data Quality:")
        print(f"   Missing:     {self.df['DMI'].isna().sum()} ({self.df['DMI'].isna().sum()/len(self.df)*100:.2f}%)")
        print(f"   Valid:       {self.df['DMI'].notna().sum()}")
        print(f"   Data type:   {self.df['DMI'].dtype}")
        
        print(f"\n🌍 Relevance for ASAL:")
        print(f"   • Positive IOD → Warmer western Indian Ocean → Enhanced East Africa rainfall")
        print(f"   • Negative IOD → Cooler western Indian Ocean → Reduced East Africa rainfall")
        print(f"   • IOD events often co-occur with ENSO but can occur independently")
        print(f"   • IOD typically peaks in September-November (SON)")
    
    def statistical_summary(self):
        """Comprehensive statistical analysis"""
        print("\n" + "="*80)
        print("STATISTICAL SUMMARY")
        print("="*80)
        
        data = self.df['DMI'].dropna()
        
        stats_dict = {
            'Count': len(data), 'Mean': data.mean(), 'Median': data.median(),
            'Std Dev': data.std(), 'Variance': data.var(), 'Min': data.min(),
            'Max': data.max(), 'Range': data.max() - data.min(),
            'Q25': data.quantile(0.25), 'Q75': data.quantile(0.75),
            'IQR': data.quantile(0.75) - data.quantile(0.25),
            'Skewness': data.skew(), 'Kurtosis': data.kurtosis()
        }
        
        print(f"\n📈 Descriptive Statistics (°C):")
        for key, value in stats_dict.items():
            if key == 'Count':
                print(f"   {key:12s}: {value:8.0f}")
            else:
                print(f"   {key:12s}: {value:8.3f}")
        
        print(f"\n📊 Distribution Analysis:")
        statistic, p_value = stats.normaltest(data)
        print(f"   Normality Test (D'Agostino-Pearson):")
        print(f"      Statistic: {statistic:.4f}, P-value: {p_value:.4f}")
        print(f"      Result: {'Non-normal' if p_value < 0.05 else 'Normal'} distribution")
        
        if len(data) < 5000:
            statistic, p_value = stats.shapiro(data)
            print(f"\n   Shapiro-Wilk Test:")
            print(f"      Statistic: {statistic:.4f}, P-value: {p_value:.4f}")
        
        Q1, Q3 = data.quantile(0.25), data.quantile(0.75)
        IQR = Q3 - Q1
        outliers = data[(data < Q1 - 1.5*IQR) | (data > Q3 + 1.5*IQR)]
        print(f"\n   Outlier Detection (IQR): {len(outliers)} ({len(outliers)/len(data)*100:.2f}%)")
        
        return stats_dict
    
    def iod_phases(self):
        """Classify IOD phases and extreme events"""
        print("\n" + "="*80)
        print("IOD PHASE CLASSIFICATION")
        print("="*80)
        
        data = self.df['DMI'].dropna()
        threshold = 0.4
        
        positive = (data >= threshold).sum()
        negative = (data <= -threshold).sum()
        neutral = ((data > -threshold) & (data < threshold)).sum()
        
        print(f"\n🌡️  Phase Distribution (threshold: ±{threshold}°C):")
        print(f"   Positive IOD: {positive:5d} months ({positive/len(data)*100:5.1f}%)")
        print(f"   Negative IOD: {negative:5d} months ({negative/len(data)*100:5.1f}%)")
        print(f"   Neutral:      {neutral:5d} months ({neutral/len(data)*100:5.1f}%)")
        
        print(f"\n🔥 Event Intensity:")
        print(f"   Strong Positive (>=0.8°C):  {(data >= 0.8).sum():5d} months")
        print(f"   Extreme Positive (>=1.2°C): {(data >= 1.2).sum():5d} months")
        print(f"   Strong Negative (<=-0.8°C): {(data <= -0.8).sum():5d} months")
        print(f"   Extreme Negative (<=-1.2°C):{(data <= -1.2).sum():5d} months")
        
        print(f"\n🌊 Extreme Values:")
        print(f"   Strongest positive: +{data.max():.2f}°C ({data.idxmax().strftime('%Y-%m')})")
        print(f"   Strongest negative: {data.min():.2f}°C ({data.idxmin().strftime('%Y-%m')})")
    
    def seasonal_analysis(self):
        """Deep dive into seasonal patterns"""
        print("\n" + "="*80)
        print("SEASONAL ANALYSIS")
        print("="*80)
        
        data = self.df['DMI']
        monthly_mean = data.groupby(data.index.month).mean()
        monthly_std = data.groupby(data.index.month).std()
        
        print(f"\n🌦️  Seasonal Cycle:")
        print(f"   Peak month:    {monthly_mean.idxmax()} ({monthly_mean.max():+.3f}°C)")
        print(f"   Minimum month: {monthly_mean.idxmin()} ({monthly_mean.min():+.3f}°C)")
        print(f"   Amplitude:     {monthly_mean.max() - monthly_mean.min():.3f}°C")
        
        son_data = data[data.index.month.isin([9, 10, 11])]
        other_data = data[~data.index.month.isin([9, 10, 11])]
        
        print(f"\n🍂 Peak Season (SON):")
        print(f"   Mean: {son_data.mean():+.3f}°C, Std: {son_data.std():.3f}°C")
        print(f"   Other months Mean: {other_data.mean():+.3f}°C")
        
        return monthly_mean, monthly_std
    
    def temporal_trends(self):
        """Analyze long-term trends and variability"""
        print("\n" + "="*80)
        print("TEMPORAL TRENDS & VARIABILITY")
        print("="*80)
        
        data = self.df['DMI'].dropna()
        x, y = np.arange(len(data)), data.values
        slope, intercept, r_value, p_value, std_err = stats.linregress(x, y)
        
        print(f"\n📉 Long-term Linear Trend:")
        print(f"   Per decade: {slope*120:+.4f}°C")
        print(f"   R-squared: {r_value**2:.4f}, P-value: {p_value:.4f}")
        print(f"   {'⚠️  Significant trend!' if p_value < 0.05 else '✓ No significant trend'}")
        
        annual_mean = data.groupby(data.index.year).mean()
        annual_std = data.groupby(data.index.year).std()
        
        print(f"\n📈 Inter-annual Variability:")
        print(f"   Mean annual std: {annual_std.mean():.3f}°C")
        
        return annual_mean, annual_std
    
    def persistence_analysis(self):
        """Analyze autocorrelation and persistence"""
        print("\n" + "="*80)
        print("PERSISTENCE & AUTOCORRELATION")
        print("="*80)
        
        data = self.df['DMI'].dropna()
        print(f"\n🔄 Autocorrelation:")
        for lag in [1, 2, 3, 6, 12]:
            print(f"   Lag {lag:2d} month(s): {data.autocorr(lag=lag):.3f}")
    
    def spectral_analysis(self):
        """Frequency domain analysis"""
        print("\n" + "="*80)
        print("SPECTRAL ANALYSIS")
        print("="*80)
        
        data = self.df['DMI'].dropna()
        detrended = signal.detrend(data.values)
        freqs, psd = signal.periodogram(detrended, fs=12)
        peak_indices = signal.find_peaks(psd, height=np.mean(psd))[0]
        
        print(f"\n📊 Dominant Periodicities:")
        if len(peak_indices) > 0:
            for idx in peak_indices[:5]:
                if freqs[idx] > 0:
                    period_years = 1 / (freqs[idx] * 12)
                    print(f"   Period: {period_years:.2f} years")
        else:
            print(f"   No significant periodicities detected")
    
    def extreme_events_analysis(self):
        """Detailed analysis of extreme events"""
        print("\n" + "="*80)
        print("EXTREME EVENTS ANALYSIS")
        print("="*80)
        
        data = self.df['DMI']
        years = (data.index[-1] - data.index[0]).days / 365.25
        
        n_positive = (data >= 1.0).sum()
        n_negative = (data <= -1.0).sum()
        
        print(f"\n📉 Return Period Estimation:")
        if n_positive > 0:
            print(f"   Events >= +1.0°C: ~every {years/(n_positive/12):.1f} years")
        if n_negative > 0:
            print(f"   Events <= -1.0°C: ~every {years/(n_negative/12):.1f} years")
    
    def create_visualizations(self, monthly_mean, monthly_std, annual_mean, annual_std):
        """Generate comprehensive visualization suite"""
        print("\n" + "="*80)
        print("CREATING VISUALIZATIONS")
        print("="*80)
        
        fig = plt.figure(figsize=(20, 14))
        data = self.df['DMI']
        
        # 1. Full time series
        ax1 = plt.subplot(4, 3, 1)
        data.plot(ax=ax1, linewidth=0.8, color='black', alpha=0.7)
        positive_mask, negative_mask = data >= 0.4, data <= -0.4
        ax1.fill_between(data.index, 0, data.values, where=positive_mask, 
                        color='red', alpha=0.3, label='Positive IOD')
        ax1.fill_between(data.index, 0, data.values, where=negative_mask, 
                        color='blue', alpha=0.3, label='Negative IOD')
        ax1.axhline(0, color='black', linestyle='--', linewidth=0.5)
        ax1.set_title('IOD DMI Time Series', fontweight='bold', fontsize=12)
        ax1.set_ylabel('DMI (°C)')
        ax1.legend(loc='upper left', fontsize=9)
        ax1.grid(alpha=0.3)
        
        # 2. Recent 30 years
        ax2 = plt.subplot(4, 3, 2)
        recent = data[data.index >= (data.index[-1] - pd.DateOffset(years=30))]
        recent.plot(ax=ax2, linewidth=1.2, color='black')
        ax2.axhline(0, color='black', linestyle='--', linewidth=0.5)
        ax2.set_title('Last 30 Years', fontweight='bold', fontsize=12)
        ax2.set_ylabel('DMI (°C)')
        ax2.grid(alpha=0.3)
        
        # 3. Distribution
        ax3 = plt.subplot(4, 3, 3)
        ax3.hist(data.dropna(), bins=60, edgecolor='black', alpha=0.7, color='teal')
        ax3.axvline(0, color='black', linestyle='--', linewidth=2)
        ax3.set_title('DMI Distribution', fontweight='bold', fontsize=12)
        ax3.set_xlabel('DMI (°C)')
        ax3.set_ylabel('Frequency')
        ax3.grid(alpha=0.3)
        
        # 4. Seasonal cycle
        ax4 = plt.subplot(4, 3, 4)
        months = range(1, 13)
        ax4.plot(months, monthly_mean.values, 'o-', linewidth=2, markersize=8, color='darkgreen')
        ax4.fill_between(months, monthly_mean - monthly_std, monthly_mean + monthly_std,
                        alpha=0.3, color='lightgreen')
        ax4.axhline(0, color='black', linestyle='--', linewidth=0.5)
        ax4.axvspan(8.5, 11.5, alpha=0.2, color='orange', label='SON season')
        ax4.set_title('Seasonal Cycle', fontweight='bold', fontsize=12)
        ax4.set_xlabel('Month')
        ax4.set_ylabel('DMI (°C)')
        ax4.set_xticks(months)
        ax4.set_xticklabels(['J','F','M','A','M','J','J','A','S','O','N','D'])
        ax4.legend(fontsize=9)
        ax4.grid(alpha=0.3)
        
        # 5. Annual means
        ax5 = plt.subplot(4, 3, 5)
        colors = ['red' if x > 0 else 'blue' for x in annual_mean.values]
        annual_mean.plot(kind='bar', ax=ax5, color=colors, width=0.8, alpha=0.7)
        ax5.axhline(0, color='black', linestyle='--', linewidth=1)
        ax5.set_title('Annual Mean DMI', fontweight='bold', fontsize=12)
        ax5.set_ylabel('DMI (°C)')
        ax5.grid(alpha=0.3, axis='y')
        plt.setp(ax5.xaxis.get_majorticklabels(), rotation=45, fontsize=7)
        
        # 6. Box plot by month
        ax6 = plt.subplot(4, 3, 6)
        data_by_month = [data[data.index.month == m].dropna() for m in range(1, 13)]
        bp = ax6.boxplot(data_by_month, labels=['J','F','M','A','M','J','J','A','S','O','N','D'])
        ax6.axhline(0, color='black', linestyle='--', linewidth=0.5)
        ax6.set_title('Monthly Variability', fontweight='bold', fontsize=12)
        ax6.set_ylabel('DMI (°C)')
        ax6.grid(alpha=0.3, axis='y')
        
        # 7. Heatmap by year and month
        ax7 = plt.subplot(4, 3, 7)
        pivot = data.reset_index()
        pivot['Year'] = pivot['Date'].dt.year
        pivot['Month'] = pivot['Date'].dt.month
        heatmap_data = pivot.pivot(index='Month', columns='Year', values='DMI')
        recent_years = heatmap_data.columns[-30:]
        sns.heatmap(heatmap_data[recent_years], cmap='RdBu_r', center=0, 
                   ax=ax7, cbar_kws={'label': 'DMI (°C)'})
        ax7.set_title('Monthly DMI Heatmap (Last 30 Years)', fontweight='bold', fontsize=12)
        ax7.set_ylabel('Month')
        
        # 8. Rolling mean
        ax8 = plt.subplot(4, 3, 8)
        data.plot(ax=ax8, linewidth=0.5, alpha=0.3, color='gray', label='Monthly')
        data.rolling(12).mean().plot(ax=ax8, linewidth=2, color='red', label='12-month MA')
        ax8.axhline(0, color='black', linestyle='--', linewidth=0.5)
        ax8.set_title('DMI with Rolling Mean', fontweight='bold', fontsize=12)
        ax8.set_ylabel('DMI (°C)')
        ax8.legend(fontsize=9)
        ax8.grid(alpha=0.3)
        
        # 9. Q-Q plot
        ax9 = plt.subplot(4, 3, 9)
        stats.probplot(data.dropna(), dist="norm", plot=ax9)
        ax9.set_title('Q-Q Plot (Normality Check)', fontweight='bold', fontsize=12)
        ax9.grid(alpha=0.3)
        
        # 10. Autocorrelation
        ax10 = plt.subplot(4, 3, 10)
        lags = range(0, 25)
        acf_vals = [data.dropna().autocorr(lag=i) for i in lags]
        ax10.bar(lags, acf_vals, color='steelblue', alpha=0.7)
        ax10.axhline(0, color='black', linewidth=0.5)
        ax10.axhline(0.2, color='red', linestyle='--', linewidth=0.5, alpha=0.5)
        ax10.axhline(-0.2, color='red', linestyle='--', linewidth=0.5, alpha=0.5)
        ax10.set_title('Autocorrelation Function', fontweight='bold', fontsize=12)
        ax10.set_xlabel('Lag (months)')
        ax10.set_ylabel('ACF')
        ax10.grid(alpha=0.3)
        
        # 11. Spectral analysis
        ax11 = plt.subplot(4, 3, 11)
        detrended = signal.detrend(data.dropna().values)
        freqs, psd = signal.periodogram(detrended, fs=12)
        periods = 1 / (freqs + 1e-10) / 12
        ax11.plot(periods, psd, linewidth=1.5, color='darkblue')
        ax11.set_xlim(0, 10)
        ax11.set_title('Power Spectral Density', fontweight='bold', fontsize=12)
        ax11.set_xlabel('Period (years)')
        ax11.set_ylabel('Power')
        ax11.grid(alpha=0.3)
        
        # 12. Year-over-year change
        ax12 = plt.subplot(4, 3, 12)
        annual_change = annual_mean.diff()
        colors = ['green' if x > 0 else 'red' for x in annual_change.values]
        annual_change.plot(kind='bar', ax=ax12, color=colors, width=0.8, alpha=0.7)
        ax12.axhline(0, color='black', linestyle='--', linewidth=1)
        ax12.set_title('Year-over-Year Change', fontweight='bold', fontsize=12)
        ax12.set_ylabel('Change in DMI (°C)')
        ax12.grid(alpha=0.3, axis='y')
        plt.setp(ax12.xaxis.get_majorticklabels(), rotation=45, fontsize=7)
        
        plt.tight_layout()
        return fig


def main():
    """Main execution function"""
    data_file = Path('data/raw/iod/dmi_noaa.txt')
    
    print("\n" + "🌊"*40)
    print("IOD DIPOLE MODE INDEX - COMPREHENSIVE EDA")
    print("GreenScope Analytics - ASAL Drought Prediction")
    print("🌊"*40 + "\n")
    
    explorer = IODExplorer(data_file)
    
    if not explorer.load_data():
        print("\n❌ Failed to load data. Check file path and format.")
        return
    
    try:
        explorer.metadata()
        explorer.statistical_summary()
        explorer.iod_phases()
        monthly_mean, monthly_std = explorer.seasonal_analysis()
        annual_mean, annual_std = explorer.temporal_trends()
        explorer.persistence_analysis()
        explorer.spectral_analysis()
        explorer.extreme_events_analysis()
        
        fig = explorer.create_visualizations(monthly_mean, monthly_std, annual_mean, annual_std)
        
        output_dir = Path('outputs/eda')
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = output_dir / 'iod_dmi_eda.png'
        plt.savefig(output_file, dpi=300, bbox_inches='tight')
        print(f"\n✓ Visualization saved: {output_file}")
        
        print("\n" + "="*80)
        print("✓ IOD EDA COMPLETE")
        print("="*80)
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
import requests
import geopandas as gpd
from pathlib import Path
import json
import time
import os

# ------------------------------------------------------------------
# SETUP PATHS - GENERALIZED
# ------------------------------------------------------------------
# Use environment variable with fallback to current directory
PROJECT_ROOT = Path(os.getenv('GREENSCOPE_PROJECT_ROOT', Path.cwd()))

# Define relative paths from project root
BASE_DIR = PROJECT_ROOT / "data" / "raw" / "boundaries"
BASE_DIR.mkdir(parents=True, exist_ok=True)
RAW_FILE = BASE_DIR / "kenya_raw_adm1.geojson"
FINAL_ASAL = BASE_DIR / "asal_boundary.geojson"

# ------------------------------------------------------------------
# CONFIGURATION
# ------------------------------------------------------------------
# ASAL Counties list - can be overridden via configuration
ASAL_COUNTIES = [
    "Turkana", "Marsabit", "Mandera", "Wajir", "Garissa", "Tana River", 
    "Isiolo", "Samburu", "Baringo", "West Pokot", "Laikipia", "Narok", 
    "Kajiado", "Makueni", "Kitui", "Tharaka-Nithi", "Meru", "Embu", 
    "Nyeri", "Taita Taveta", "Kwale", "Kilifi", "Lamu"
]

# Multiple sources (fallback strategy)
DATA_SOURCES = [
    {
        "name": "geoBoundaries",
        "url": "https://www.geoboundaries.org/api/current/gbOpen/KEN/ADM1/",
        "type": "api"
    },
    {
        "name": "GADM",
        "url": "https://geodata.ucdavis.edu/gadm/gadm4.1/json/gadm41_KEN_1.json",
        "type": "direct"
    },
    {
        "name": "HDX",
        "url": "https://data.humdata.org/dataset/cod-ab-ken",
        "type": "info"
    }
]


def download_with_retry(url, output_path, max_retries=3):
    """Download file with retry logic"""
    for attempt in range(max_retries):
        try:
            print(f"   Attempt {attempt + 1}/{max_retries}...")
            response = requests.get(url, timeout=60, stream=True)
            response.raise_for_status()
            
            # Check if we got actual data
            content_type = response.headers.get('content-type', '')
            if 'json' not in content_type and 'application' not in content_type:
                print(f"   ⚠ Unexpected content type: {content_type}")
                continue
            
            # Write to file
            with open(output_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            
            # Verify the file is valid
            file_size = output_path.stat().st_size
            if file_size < 1000:  # Less than 1KB is suspicious
                print(f"   ⚠ File too small ({file_size} bytes)")
                output_path.unlink()
                continue
            
            # Try to parse as JSON to verify
            with open(output_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if 'features' in data or 'type' in data:
                    print(f"   ✓ Downloaded {file_size:,} bytes")
                    return True
            
        except requests.exceptions.RequestException as e:
            print(f"   ✗ Network error: {e}")
        except json.JSONDecodeError as e:
            print(f"   ✗ Invalid JSON: {e}")
        except Exception as e:
            print(f"   ✗ Error: {e}")
        
        if attempt < max_retries - 1:
            print(f"   Retrying in 3 seconds...")
            time.sleep(3)
    
    return False


def download_from_geoboundaries_api(country_code="KEN", admin_level="ADM1", output_file=None):
    """
    Download from geoBoundaries API
    
    Parameters:
    -----------
    country_code : str
        ISO3 country code (default: KEN for Kenya)
    admin_level : str
        Administrative level (default: ADM1)
    output_file : Path, optional
        Output file path
    """
    output_file = output_file or RAW_FILE
    print(f"📥 Method 1: geoBoundaries API ({country_code}/{admin_level})")
    
    api_url = f"https://www.geoboundaries.org/api/current/gbOpen/{country_code}/{admin_level}/"
    
    try:
        # Get the metadata
        print("   Fetching metadata...")
        response = requests.get(api_url, timeout=30)
        response.raise_for_status()
        metadata = response.json()
        
        # Get the actual GeoJSON URL
        if 'gjDownloadURL' in metadata:
            download_url = metadata['gjDownloadURL']
            print(f"   Found download URL")
            return download_with_retry(download_url, output_file)
        else:
            print(f"   ✗ No download URL in metadata")
            return False
            
    except Exception as e:
        print(f"   ✗ API request failed: {e}")
        return False


def download_from_gadm(country_code="KEN", admin_level=1, output_file=None):
    """
    Download from GADM
    
    Parameters:
    -----------
    country_code : str
        ISO3 country code (default: KEN for Kenya)
    admin_level : int
        Administrative level (default: 1)
    output_file : Path, optional
        Output file path
    """
    output_file = output_file or RAW_FILE
    print(f"📥 Method 2: GADM Database ({country_code}/ADM{admin_level})")
    
    url = f"https://geodata.ucdavis.edu/gadm/gadm4.1/json/gadm41_{country_code}_{admin_level}.json"
    return download_with_retry(url, output_file)


def download_boundaries(country_code="KEN", admin_level=1, output_file=None):
    """
    Try multiple sources until one succeeds
    
    Parameters:
    -----------
    country_code : str
        ISO3 country code (default: KEN for Kenya)
    admin_level : int
        Administrative level (default: 1)
    output_file : Path, optional
        Output file path
    """
    output_file = output_file or RAW_FILE
    
    # Clean up any existing corrupted file
    if output_file.exists():
        output_file.unlink()
        print("🗑 Removed existing file\n")
    
    print("="*60)
    print(f"Downloading {country_code} Administrative Boundaries (Level {admin_level})")
    print("="*60)
    
    # Try geoBoundaries API first
    if download_from_geoboundaries_api(country_code, f"ADM{admin_level}", output_file):
        return True
    
    print("\n" + "-"*60 + "\n")
    
    # Try GADM as fallback
    if download_from_gadm(country_code, admin_level, output_file):
        return True
    
    print("\n" + "="*60)
    print("❌ All download methods failed")
    print("="*60)
    print("\n💡 Manual download option:")
    print("1. Visit: https://www.geoboundaries.org/downloadCGAZ.html")
    print(f"2. Select: {country_code} → ADM{admin_level}")
    print("3. Download the GeoJSON file")
    print(f"4. Save it as: {output_file.absolute()}")
    print("\nThen run this script again.")
    
    return False


def process_asal_boundary(raw_file=None, output_file=None, counties_list=None, 
                          name_column_hint=None):
    """
    Process the downloaded boundary file
    
    Parameters:
    -----------
    raw_file : Path, optional
        Path to raw boundary file
    output_file : Path, optional
        Path to save processed ASAL boundary
    counties_list : list, optional
        List of county names to filter
    name_column_hint : str, optional
        Hint for which column contains names
    """
    raw_file = raw_file or RAW_FILE
    output_file = output_file or FINAL_ASAL
    counties_list = counties_list or ASAL_COUNTIES
    
    if not raw_file.exists():
        print("❌ No boundary file found. Run download first.")
        return False
    
    print("\n" + "="*60)
    print("Processing ASAL Boundary")
    print("="*60)
    
    try:
        # Read the file
        print("📖 Reading boundary file...")
        gdf = gpd.read_file(raw_file)
        
        print(f"   ✓ Loaded {len(gdf)} administrative units")
        
        # Find the name column (different sources use different names)
        name_columns = ['shapeName', 'NAME_1', 'ADM1_EN', 'name', 'NAME']
        if name_column_hint:
            name_columns.insert(0, name_column_hint)
        
        name_col = None
        
        for col in name_columns:
            if col in gdf.columns:
                name_col = col
                break
        
        if name_col is None:
            print(f"   ⚠ Available columns: {list(gdf.columns)}")
            print("   ❌ Could not find name column")
            return False
        
        print(f"   Using name column: '{name_col}'")
        print(f"\n   Available regions: {sorted(gdf[name_col].unique())[:10]}...")
        
        # Standardize names for matching
        gdf['match_name'] = gdf[name_col].str.replace('-', ' ').str.replace('_', ' ').str.title().str.strip()
        clean_counties_list = [c.replace('-', ' ').title().strip() for c in counties_list]
        
        # Filter counties
        print(f"\n✂ Filtering {len(counties_list)} counties...")
        filtered_gdf = gdf[gdf['match_name'].isin(clean_counties_list)]
        
        if filtered_gdf.empty:
            print("   ❌ No matches found!")
            print("\n   Trying fuzzy matching...")
            
            # Try fuzzy matching
            from difflib import get_close_matches
            available_names = gdf['match_name'].tolist()
            
            matched = []
            for county in clean_counties_list:
                matches = get_close_matches(county, available_names, n=1, cutoff=0.8)
                if matches:
                    matched.append(matches[0])
                    print(f"   ~ Matched '{county}' → '{matches[0]}'")
            
            if matched:
                filtered_gdf = gdf[gdf['match_name'].isin(matched)]
        
        if filtered_gdf.empty:
            print("   ❌ Still no matches. Please check county names.")
            return False
        
        print(f"   ✓ Matched {len(filtered_gdf)} counties")
        
        # Dissolve into single boundary
        print("\n🔗 Merging into single boundary...")
        merged_boundary = filtered_gdf.dissolve()
        
        # Ensure output directory exists
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Save
        merged_boundary.to_file(output_file, driver='GeoJSON')
        
        print("\n" + "="*60)
        print("✅ SUCCESS!")
        print("="*60)
        print(f"📁 Boundary saved to: {output_file}")
        print(f"📊 Includes {len(filtered_gdf)} counties:")
        for county in sorted(filtered_gdf[name_col].tolist()):
            print(f"   • {county}")
        
        # Calculate area
        area_km2 = merged_boundary.to_crs('EPSG:32637').area.sum() / 1e6
        print(f"\n📏 Total area: {area_km2:,.0f} km²")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Processing error: {e}")
        import traceback
        traceback.print_exc()
        return False


def main(project_root=None, country_code="KEN", admin_level=1, 
         counties_list=None, force_reprocess=False):
    """
    Main function to generate boundary
    
    Parameters:
    -----------
    project_root : str or Path, optional
        Base project directory
    country_code : str
        ISO3 country code (default: KEN)
    admin_level : int
        Administrative level (default: 1)
    counties_list : list, optional
        List of counties to filter
    force_reprocess : bool
        Force reprocessing even if output exists
    """
    global PROJECT_ROOT, BASE_DIR, RAW_FILE, FINAL_ASAL
    
    # Update paths if project root is provided
    if project_root:
        PROJECT_ROOT = Path(project_root)
        BASE_DIR = PROJECT_ROOT / "data" / "raw" / "boundaries"
        BASE_DIR.mkdir(parents=True, exist_ok=True)
        RAW_FILE = BASE_DIR / f"{country_code.lower()}_raw_adm{admin_level}.geojson"
        FINAL_ASAL = BASE_DIR / "asal_boundary.geojson"
    
    counties_list = counties_list or ASAL_COUNTIES
    
    print("="*60)
    print(f"{country_code} ASAL Boundary Generator")
    print("="*60)
    
    # Step 1: Download
    if not RAW_FILE.exists() or RAW_FILE.stat().st_size < 1000:
        if not download_boundaries(country_code, admin_level, RAW_FILE):
            return
    else:
        print(f"✓ Boundary file exists ({RAW_FILE.stat().st_size:,} bytes)")
    
    # Step 2: Process
    if not FINAL_ASAL.exists() or force_reprocess:
        if not process_asal_boundary(RAW_FILE, FINAL_ASAL, counties_list):
            return
    else:
        print(f"\n✓ Boundary already exists at: {FINAL_ASAL}")
        response = input("Re-generate? (y/n): ")
        if response.lower() == 'y':
            process_asal_boundary(RAW_FILE, FINAL_ASAL, counties_list)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Generate ASAL boundary from administrative boundaries'
    )
    parser.add_argument(
        '--project-root', 
        type=str, 
        help='Base project directory (default: current directory or GREENSCOPE_PROJECT_ROOT env var)'
    )
    parser.add_argument(
        '--country', 
        type=str, 
        default='KEN',
        help='ISO3 country code (default: KEN)'
    )
    parser.add_argument(
        '--admin-level', 
        type=int, 
        default=1,
        help='Administrative level (default: 1)'
    )
    parser.add_argument(
        '--counties', 
        nargs='+',
        help='List of county names to include (default: Kenya ASAL counties)'
    )
    parser.add_argument(
        '--force', 
        action='store_true',
        help='Force reprocessing even if output exists'
    )
    
    args = parser.parse_args()
    
    main(
        project_root=args.project_root,
        country_code=args.country,
        admin_level=args.admin_level,
        counties_list=args.counties,
        force_reprocess=args.force
    )
import requests
import geopandas as gpd
from pathlib import Path
import json
import time

# Setup Paths
BASE_DIR = Path("data/raw/boundaries")
BASE_DIR.mkdir(parents=True, exist_ok=True)
RAW_FILE = BASE_DIR / "kenya_raw_adm1.geojson"
FINAL_ASAL = BASE_DIR / "asal_boundary.geojson"

# ASAL Counties list
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


def download_from_geoboundaries_api():
    """Download from geoBoundaries API"""
    print("📥 Method 1: geoBoundaries API")
    
    api_url = "https://www.geoboundaries.org/api/current/gbOpen/KEN/ADM1/"
    
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
            return download_with_retry(download_url, RAW_FILE)
        else:
            print(f"   ✗ No download URL in metadata")
            return False
            
    except Exception as e:
        print(f"   ✗ API request failed: {e}")
        return False


def download_from_gadm():
    """Download from GADM"""
    print("📥 Method 2: GADM Database")
    
    url = "https://geodata.ucdavis.edu/gadm/gadm4.1/json/gadm41_KEN_1.json"
    return download_with_retry(url, RAW_FILE)


def download_boundaries():
    """Try multiple sources until one succeeds"""
    
    # Clean up any existing corrupted file
    if RAW_FILE.exists():
        RAW_FILE.unlink()
        print("🗑 Removed existing file\n")
    
    print("="*60)
    print("Downloading Kenya Administrative Boundaries")
    print("="*60)
    
    # Try geoBoundaries API first
    if download_from_geoboundaries_api():
        return True
    
    print("\n" + "-"*60 + "\n")
    
    # Try GADM as fallback
    if download_from_gadm():
        return True
    
    print("\n" + "="*60)
    print("❌ All download methods failed")
    print("="*60)
    print("\n💡 Manual download option:")
    print("1. Visit: https://www.geoboundaries.org/downloadCGAZ.html")
    print("2. Select: Kenya → ADM1")
    print("3. Download the GeoJSON file")
    print(f"4. Save it as: {RAW_FILE.absolute()}")
    print("\nThen run this script again.")
    
    return False


def process_asal_boundary():
    """Process the downloaded boundary file"""
    
    if not RAW_FILE.exists():
        print("❌ No boundary file found. Run download first.")
        return False
    
    print("\n" + "="*60)
    print("Processing ASAL Boundary")
    print("="*60)
    
    try:
        # Read the file
        print("📖 Reading boundary file...")
        gdf = gpd.read_file(RAW_FILE)
        
        print(f"   ✓ Loaded {len(gdf)} administrative units")
        
        # Find the name column (different sources use different names)
        name_columns = ['shapeName', 'NAME_1', 'ADM1_EN', 'name', 'NAME']
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
        clean_asal_list = [c.replace('-', ' ').title().strip() for c in ASAL_COUNTIES]
        
        # Filter ASAL counties
        print(f"\n✂ Filtering {len(ASAL_COUNTIES)} ASAL counties...")
        asal_gdf = gdf[gdf['match_name'].isin(clean_asal_list)]
        
        if asal_gdf.empty:
            print("   ❌ No matches found!")
            print("\n   Trying fuzzy matching...")
            
            # Try fuzzy matching
            from difflib import get_close_matches
            available_names = gdf['match_name'].tolist()
            
            matched = []
            for asal in clean_asal_list:
                matches = get_close_matches(asal, available_names, n=1, cutoff=0.8)
                if matches:
                    matched.append(matches[0])
                    print(f"   ~ Matched '{asal}' → '{matches[0]}'")
            
            if matched:
                asal_gdf = gdf[gdf['match_name'].isin(matched)]
        
        if asal_gdf.empty:
            print("   ❌ Still no matches. Please check county names.")
            return False
        
        print(f"   ✓ Matched {len(asal_gdf)} counties")
        
        # Dissolve into single boundary
        print("\n🔗 Merging into single ASAL boundary...")
        asal_boundary = asal_gdf.dissolve()
        
        # Save
        asal_boundary.to_file(FINAL_ASAL, driver='GeoJSON')
        
        print("\n" + "="*60)
        print("✅ SUCCESS!")
        print("="*60)
        print(f"📍 ASAL boundary saved to: {FINAL_ASAL}")
        print(f"📊 Includes {len(asal_gdf)} counties:")
        for county in sorted(asal_gdf[name_col].tolist()):
            print(f"   • {county}")
        
        # Calculate area
        area_km2 = asal_boundary.to_crs('EPSG:32637').area.sum() / 1e6
        print(f"\n📐 Total area: {area_km2:,.0f} km²")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Processing error: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    print("="*60)
    print("Kenya ASAL Boundary Generator")
    print("="*60)
    
    # Step 1: Download
    if not RAW_FILE.exists() or RAW_FILE.stat().st_size < 1000:
        if not download_boundaries():
            return
    else:
        print(f"✓ Boundary file exists ({RAW_FILE.stat().st_size:,} bytes)")
    
    # Step 2: Process
    if not FINAL_ASAL.exists():
        if not process_asal_boundary():
            return
    else:
        print(f"\n✓ ASAL boundary already exists at: {FINAL_ASAL}")
        response = input("Re-generate? (y/n): ")
        if response.lower() == 'y':
            process_asal_boundary()


if __name__ == "__main__":
    main()
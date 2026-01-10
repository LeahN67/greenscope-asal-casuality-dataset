"""
Generate requirements.txt file without version numbers
"""

import subprocess
import sys
from pathlib import Path

def get_installed_packages():
    """Get list of installed packages."""
    result = subprocess.run(
        [sys.executable, '-m', 'pip', 'list', '--format=freeze'],
        capture_output=True,
        text=True
    )
    return result.stdout.strip().split('\n')


def create_requirements_no_versions():
    """Create requirements.txt without version numbers."""
    
    print("📦 Generating requirements.txt (without versions)")
    print("=" * 70)
    
    packages = get_installed_packages()
    
    # Remove version numbers
    package_names = []
    for pkg in packages:
        if '==' in pkg:
            name = pkg.split('==')[0]
            package_names.append(name)
    
    # Filter out common system packages that shouldn't be in requirements
    exclude = [
        'pip', 'setuptools', 'wheel', 'distribute',
        'pkg-resources'  # Linux-specific, causes issues
    ]
    
    package_names = [p for p in package_names if p not in exclude]
    
    # Sort alphabetically
    package_names.sort()
    
    # Write to file
    output_file = Path('requirements.txt')
    
    with open(output_file, 'w') as f:
        for pkg in package_names:
            f.write(f"{pkg}\n")
    
    print(f"\n✅ Created {output_file} with {len(package_names)} packages")
    print(f"\nPackages saved:")
    
    # Print in columns
    for i in range(0, len(package_names), 3):
        row = package_names[i:i+3]
        print(f"   {', '.join(row)}")
    
    print("\n" + "=" * 70)
    print("📋 Next steps:")
    print("\n1. Deactivate: deactivate")
    print("2. Backup old env: rename green_env green_env_old")
    print("3. Create new env: python -m venv green_env --system-site-packages")
    print("4. Activate: green_env\\Scripts\\activate")
    print("5. Install packages: pip install -r requirements.txt")
    print("6. Test GDAL: python -c \"from osgeo import gdal; print('Works!')\"")


if __name__ == '__main__':
    create_requirements_no_versions()
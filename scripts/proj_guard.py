"""
Ignore PROJ_LIB / PROJ_DATA when they point outside the active Python environment.

Other software (PostgreSQL/PostGIS, QGIS, older GDAL installs) often sets these variables system-wide
to its own PROJ database. rasterio, pyproj and geopandas then load that database, and if it is older
than the PROJ they were built with, every coordinate system lookup fails ("proj.db contains
DATABASE.LAYOUT.VERSION.MINOR = 0 whereas a number >= 6 is expected"). Without the variables, the
libraries use the PROJ data bundled with them. Import this module before any geospatial library.
"""
import os
import sys
from pathlib import Path

_prefix = Path(sys.prefix).resolve()
for _var in ("PROJ_DATA", "PROJ_LIB"):
    _val = os.environ.get(_var)
    if not _val:
        continue
    try:
        _inside = Path(_val).resolve().is_relative_to(_prefix)
    except OSError:
        _inside = False
    if not _inside:
        os.environ.pop(_var)
        print(f"   note: ignoring {_var}={_val}; it belongs to another PROJ installation (for example "
              "PostGIS), so the PROJ data bundled with this Python environment is used instead", file=sys.stderr)

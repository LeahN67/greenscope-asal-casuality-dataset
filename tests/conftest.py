import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import proj_guard  # noqa: E402,F401  (clears a foreign PROJ_LIB/PROJ_DATA before rasterio loads)

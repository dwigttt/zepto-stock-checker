import os
from pathlib import Path

PROXY_URL = os.environ.get("PROXY_URL") or None
DATABASE_PATH = Path(os.environ.get("DATABASE_PATH", "data/zepto.db"))
ZEPTO_CONCURRENCY = int(os.environ.get("ZEPTO_CONCURRENCY", "5"))
STATIC_DIR = Path(os.environ.get("STATIC_DIR", Path(__file__).resolve().parent.parent / "static"))

MAX_RADIUS_KM = 50.0
# Dark stores cover ~3km; probe points spaced wider than that may miss stores,
# tighter wastes requests.
GRID_SPACING_KM = 3.0
# A fresh probe within this distance of a grid point means the area is already mapped.
PROBE_COVERAGE_KM = 2.0
SERVICEABLE_PROBE_TTL_DAYS = 90
UNSERVICEABLE_PROBE_TTL_DAYS = 30

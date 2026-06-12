import os
from pathlib import Path


def _flag(name: str, default: bool) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


PROXY_URL = os.environ.get("PROXY_URL") or None
DATABASE_PATH = Path(os.environ.get("DATABASE_PATH", "data/zepto.db"))
ZEPTO_CONCURRENCY = int(os.environ.get("ZEPTO_CONCURRENCY", "5"))
STATIC_DIR = Path(os.environ.get("STATIC_DIR", Path(__file__).resolve().parent.parent / "static"))

# -- abuse controls --------------------------------------------------------
# Shared secret gating all /api access. Unset (default) = open, for self-host
# and local dev. Set it before exposing one instance to a group.
APP_TOKEN = os.environ.get("APP_TOKEN") or None
# Trust the leftmost X-Forwarded-For hop as the client IP. Correct behind a
# reverse proxy (Dokploy/Traefik); turn off if the app is directly exposed,
# since the header is client-controlled and would let anyone forge their IP.
TRUST_FORWARDED_FOR = _flag("TRUST_FORWARDED_FOR", True)
# General per-client request budget (geocode/suggest/resolve/place): burst then
# a sustained refill. Keeps autocomplete-style hammering in check.
REQUEST_BURST = int(os.environ.get("REQUEST_BURST", "30"))
REQUESTS_PER_MIN = int(os.environ.get("REQUESTS_PER_MIN", "60"))
# Per-client search budget — searches are the expensive sweep, so this is the
# main IP-protecting knob. Burst, then a slow daily refill.
SEARCH_BURST = int(os.environ.get("SEARCH_BURST", "5"))
SEARCHES_PER_DAY = int(os.environ.get("SEARCHES_PER_DAY", "100"))
# Hard cap on simultaneous sweeps across all clients — bounds the request rate
# Zepto sees regardless of how many people search at once.
MAX_CONCURRENT_SEARCHES = int(os.environ.get("MAX_CONCURRENT_SEARCHES", "3"))

# Public radius ceiling. A 50km cold sweep is hundreds of probes; keep it lower
# on a shared instance. Self-host can raise it back via env.
MAX_RADIUS_KM = float(os.environ.get("MAX_RADIUS_KM", "25"))
# Dark stores cover ~3km; probe points spaced wider than that may miss stores,
# tighter wastes requests.
GRID_SPACING_KM = 3.0
# A fresh probe within this distance of a grid point means the area is already mapped.
PROBE_COVERAGE_KM = 2.0
SERVICEABLE_PROBE_TTL_DAYS = 90
UNSERVICEABLE_PROBE_TTL_DAYS = 30

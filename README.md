# Zepto Finder

Paste a shared Zepto product link, set your location and a search radius (up to
50 km), and see which nearby Zepto dark stores actually have the item in stock —
on a map and a distance-sorted list, with per-store prices.

**How it answers "where can I get this?":** Zepto availability is per dark
store, not per pincode. The app geocodes your pincode (or uses GPS), checks your
own store first, then sweeps the radius with serviceability probes to discover
every dark store in the circle, and checks live stock at each one. Discovered
stores are cached in SQLite, so the first search in a new area is slow
(a 50 km sweep probes a few hundred points) but every later search there
finishes in seconds.

> ⚠️ This uses Zepto's **unofficial** internal API (the one their own website
> calls). It can break without notice — see `docs/zepto-api-notes.md` for the
> verified endpoints and `backend/scripts/smoke_zepto.py` to diagnose breakage.
> Keep it personal/low-volume.

## Stack

- **Backend** — FastAPI + httpx + SQLite (`backend/`). All Zepto specifics are
  isolated in `backend/app/zepto.py`. Results stream over SSE.
- **Frontend** — React + Vite + shadcn/ui + Leaflet (`frontend/`), served as
  static files by the backend in production.

## Development

```bash
# Terminal 1 — backend on :8400
cd backend
uv sync
uv run uvicorn app.main:app --port 8400 --reload

# Terminal 2 — frontend on :5173 (proxies /api to :8400)
cd frontend
pnpm install
pnpm dev
```

Tests and live smoke check:

```bash
cd backend
uv run pytest                          # unit tests, no network
uv run python scripts/smoke_zepto.py   # hits the real Zepto API
```

## Deployment (Dokploy)

Point Dokploy at this repo as a **Docker Compose** (or Dockerfile) app. The
container listens on port 8000 and stores its database in the `zepto-data`
volume (`/data`).

Environment variables:

| Variable            | Default         | Purpose                                              |
| ------------------- | --------------- | ---------------------------------------------------- |
| `PROXY_URL`         | _(none)_        | Route Zepto traffic through a proxy (use an Indian residential proxy if the VPS IP gets blocked) |
| `ZEPTO_CONCURRENCY` | `5`             | Max parallel requests to Zepto                       |
| `DATABASE_PATH`     | `/data/zepto.db`| SQLite location                                      |

There's no built-in auth — if you want to gate it for friends & family, put
Dokploy/Traefik basic-auth in front.

## How a search works

1. Share link → extract the product variant UUID (`/pvid/<uuid>`; Branch.io app
   links are followed server-side).
2. Pincode → lat/lng via Zepto's own geocoder; or browser GPS.
3. Your store is resolved and checked first. In stock → done (a button lets you
   sweep anyway).
4. Hex grid of probe points (~3 km spacing) covers the radius; points already
   covered by a fresh cached probe are skipped. Each probe resolves which store
   serves that spot.
5. Every unique store gets one live stock check; results stream onto the map
   and list as they arrive.

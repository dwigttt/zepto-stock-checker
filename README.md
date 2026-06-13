# Zepto Finder

Paste a shared Zepto product link, set your location and a search radius, and
see which nearby Zepto dark stores actually have the item in stock — on a map
and a distance-sorted list, with per-store prices. The radius cap is
configurable (25 km by default; see `MAX_RADIUS_KM`).

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

| Variable                  | Default          | Purpose                                                                              |
| ------------------------- | ---------------- | ------------------------------------------------------------------------------------ |
| `PROXY_URL`               | _(none)_         | Route Zepto traffic through a proxy (use an Indian residential proxy if the VPS IP gets blocked) |
| `ZEPTO_CONCURRENCY`       | `5`              | Max parallel requests to Zepto                                                       |
| `DATABASE_PATH`           | `/data/zepto.db` | SQLite location                                                                      |
| `APP_TOKEN`               | _(none)_         | Shared access token. Unset = open; set it to gate all `/api` access (see below)      |
| `MAX_RADIUS_KM`           | `15`             | Largest search radius accepted. Cold-sweep cost grows with area (~radius²), so this is a big bandwidth lever: 25km ≈ 253 probes, 15km ≈ 91, 10km ≈ 37 |
| `MAX_CONCURRENT_SEARCHES` | `3`              | Hard cap on simultaneous sweeps across all users — bounds the request rate Zepto sees |
| `PROBES_PER_DAY`          | `3000`           | **Whole-instance daily probe budget — the main knob for proxy cost.** Probing is the bulk of upstream traffic; a search past the budget still returns cached + partial results |
| `PROBE_BURST`             | `400`            | Probe budget burst (sized to allow a couple of full cold sweeps back-to-back)        |
| `GLOBAL_SEARCHES_PER_DAY` | `500`            | Whole-instance daily search cap (across everyone) — coarse backstop if a token leaks |
| `GLOBAL_SEARCH_BURST`     | `20`             | Global search burst allowance                                                        |
| `SEARCHES_PER_DAY`        | `30`             | Per-client (per-IP) daily search budget                                              |
| `SEARCH_BURST`            | `3`              | Per-client search burst allowance before the daily refill paces them                 |
| `REQUESTS_PER_MIN`        | `60`             | Per-client budget for the lighter endpoints (geocode/suggest/resolve)               |
| `REQUEST_BURST`           | `30`             | Per-client request burst allowance                                                   |
| `TRUST_FORWARDED_FOR`     | `true`           | Read the client IP from `X-Forwarded-For` (correct behind Dokploy/Traefik; turn off if the app is directly exposed, since the header is forgeable) |

### Sharing with a group

The app reads public price/stock data from Zepto's **unofficial** internal API,
so keep any shared instance small and low-volume — and **point `PROXY_URL` at an
Indian residential proxy**, since a VPS IP serving many users is the most likely
thing to get blocked.

Turn on the built-in abuse controls before exposing one instance to a group:

1. Set `APP_TOKEN` to a long random string. Every `/api` call then needs it.
2. Share the app with the token in the URL: `https://your-host/?token=<APP_TOKEN>`.
   The frontend stores the token, strips it from the URL, and sends it on every
   request (as a header, and as a query param on the search stream — `EventSource`
   can't send headers). Visitors without the token get a prompt to paste one.

With `APP_TOKEN` set, the per-IP and global search budgets plus the concurrency
cap keep total upstream traffic bounded even if the link leaks. The shared SQLite
cache helps a lot here: if the group is mostly in one or two cities, only the
first search in each area is expensive.

**Controlling proxy cost.** Residential proxies bill per GB, and the cold
discovery sweep is what spends it — a fresh 15km sweep is ~91 probes (~0.3 MB),
a 25km one ~253 (~0.75 MB), one-time per area then cached. The knobs, in order of
impact:

- **`PROBES_PER_DAY`** — a hard daily ceiling on total probing across everyone.
  At ~3 KB/probe, `3000` ≈ ~9 MB/day of probe traffic. Lower it to spend less;
  searches past it still work off the cache and say so in the UI.
- **`MAX_RADIUS_KM`** — smaller radius shrinks every cold sweep quadratically.
- **`GLOBAL_SEARCHES_PER_DAY` / `SEARCHES_PER_DAY`** — cap how many searches (and
  thus per-store stock checks, ~10–30 KB each) run per day, globally and per user.

> Alternatively, skip hosting and just share the repo — each person runs their
> own copy (the Docker setup makes this a one-liner), so traffic spreads across
> many home IPs and there's no shared instance to abuse.

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

## Contributing

Contributions are welcome. Open an issue to discuss a change first, then send a
pull request. Please keep the Zepto-specific bits isolated in
`backend/app/zepto.py`, run `uv run pytest` before submitting, and keep any
real-API testing personal and low-volume.

## Disclaimer

This project is an independent, unofficial tool. It is **not** affiliated with,
endorsed by, or connected to Zepto in any way, and it relies on Zepto's
undocumented internal API, which can change or break at any time. It is provided
for personal, educational use only — you are responsible for using it in line
with Zepto's terms of service and applicable law. See the warning above on
keeping usage low-volume.

## License

Released under the [MIT License](LICENSE).

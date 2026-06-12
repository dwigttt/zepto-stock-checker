# Zepto Finder — Design

**Date:** 2026-06-12
**Status:** Approved

## Purpose

Paste a shared Zepto product link, set a location (pincode or GPS) and a search
radius (1–50 km). The app checks the item at the user's location first; if it is
unavailable there, it finds every nearby Zepto dark store that has it in stock and
shows them on a map and a distance-sorted list (locality name, distance, price,
stock status).

**Audience:** personal use, shared with friends and family. Low request volume.
No accounts or in-app auth in v1; the deployment can be gated with Dokploy
basic-auth if desired.

## Background: how Zepto works (research findings, 2026-06-12)

- Share links contain a product variant UUID:
  `https://www.zeptonow.com/pn/<name-slug>/pvid/<uuid>`. App shares go through
  Branch.io links carrying the UUID in `deep_link_value`.
- There is **no official public API**. The zeptonow.com website uses an internal
  API at `https://api.zeptonow.com`. Guest (no-login) catalog reads work after a
  cookie handshake: a GET to `www.zeptonow.com` issues `session_id`, `device_id`,
  `XSRF-TOKEN`, and a `serviceability` cookie.
- Availability is **per dark store**, not per pincode. A coordinate resolves to a
  primary store (`serviceability` cookie → `primaryStore.storeId` /
  `serviceable: false`). Each store covers roughly a 3 km geofence polygon
  (exposed in store details responses).
- Useful endpoints (cross-confirmed from multiple open-source scrapers; must be
  re-verified against live DevTools traffic at implementation time):
  - `GET /api/v1/maps/place/autocomplete/?place_name={pincode}` and
    `GET /api/v1/maps/place/details/?place_id={id}` — pincode → lat/lng.
  - `GET /api/v3/store/selectableStores?lat=&lon=` — stores near a coordinate.
  - `POST /api/v3/search` (mode AUTOSUGGEST) — product search within a store
    context; returns `outOfStock` and prices in paise.
  - Store binding via headers: `store_id`/`storeId`/`X-Store-Id`, plus
    `platform: WEB`, `tenant: ZEPTO`, `x-without-bearer: true`, `app_version`,
    and the session cookies above.
- Anti-bot: AWS CloudFront, no Cloudflare/Akamai. Main friction is the
  cookie/header handshake and likely geofencing/rate-limiting of non-Indian IPs.
  `robots.txt` disallows crawling — this tool is a low-volume personal client,
  and request volume must be kept deliberately small (concurrency caps, caching,
  backoff).

## Architecture decision

**Chosen: cached store map + live stock checks.**

Alternatives considered:

1. *Stateless live sweep* — re-probe the full radius every search. Simple but
   400+ API calls per 50 km search, minutes of latency, high block risk.
2. **Cached store map (chosen)** — SQLite remembers every discovered store
   (location + coverage). Discovery runs once per area; later searches are
   ~1 availability call per cached store. Stock is always live; only store
   locations (which rarely change) are cached.
3. *Background scraper* — pre-scrape stores and stock on a schedule. Instant
   queries but stale stock, constant API load, more moving parts. Overkill.

## System components

Single Docker container deployed via Dokploy on the user's Oracle VPS.

### Backend — `backend/` (Python 3.12, FastAPI)

- **`zepto_client.py`** — the *only* module that knows Zepto specifics:
  endpoint URLs, headers, cookie bootstrap/refresh, response parsing. All
  outbound requests go through httpx with an optional `PROXY_URL` env var
  (Indian residential proxy). Global concurrency limit (4–6), small inter-request
  delays, retries with exponential backoff. If Zepto changes their API, fixes are
  contained here.
- **Link parser** — extracts the `pvid` UUID from `zeptonow.com/pn/.../pvid/<uuid>`
  URLs and Branch deep links (`deep_link_value` param); follows short-link
  redirects server-side.
- **Store cache (SQLite)** — tables:
  - `stores(id, name, lat, lng, geofence_json, discovered_at, last_seen_at)` —
    kept indefinitely.
  - `probed_points(lat, lng, serviceable, probed_at)` — negative/empty results
    expire after 30 days so unserved areas are eventually re-probed.
- **Search orchestrator** — the pipeline below, streaming progress over
  Server-Sent Events (SSE).
- Serves the built frontend as static files.

### Frontend — `frontend/` (React + Vite + TypeScript)

- Mobile-first single page.
- **Leaflet + OpenStreetMap** map (free, no API key).
- Components: link input + product card (image, name, price); location row
  (pincode field + "use my location" geolocation button); radius slider
  (1–50 km, default 10 km); results map (user marker, radius circle, store pins —
  green in stock / grey unavailable); distance-sorted result list. Tapping a pin
  highlights its list row and vice versa.
- Consumes the SSE stream: pins and list rows appear progressively with a
  "checked X/Y stores" progress indicator.

## Search pipeline

1. **Parse link** → `pvid` UUID. Fetch product details (name, image, price) for
   the product card.
2. **Resolve location** — pincode → lat/lng via Zepto's maps endpoints, or
   browser GPS coordinates directly.
3. **Check home location first** — resolve the user's primary store, check the
   product there. If in stock, report success immediately (nearby search still
   available on demand).
4. **Discover stores in radius** — load cached stores within the radius
   (haversine distance on store coordinates). For circle areas not covered by
   cached store geofences or fresh `probed_points`, generate a hex grid of probe
   points (~4 km spacing, ordered from center outward) and resolve each against
   Zepto serviceability; upsert discovered stores, record empty points.
   If `selectableStores` proves to return multiple stores per probe (verify at
   implementation), use it to cut probe count further.
5. **Check stock per store** — one catalog query per unique store with the
   store's headers; classify as in stock / out of stock / not carried; capture
   the store-local price (paise → rupees).
6. **Stream results** — each store result is sent as an SSE event the moment it
   resolves. First search in a new area is slow (a 50 km sweep may take a couple
   of minutes); subsequent searches in covered areas finish in seconds.

## API surface (backend)

- `POST /api/parse-link` `{url}` → `{pvid, name, image, price}` or error.
- `GET /api/geocode?pincode=` → `{lat, lng, label}` or error.
- `GET /api/search?pvid=&lat=&lng=&radius_km=` → SSE stream of events:
  `home_result`, `progress {checked, total}`, `store_result {store, distance_km,
  status, price}`, `done`, `warning`, `error`.

## Error handling

- Unparseable/non-Zepto link → inline message at the input.
- Pincode not found → inline message at the location field.
- Mid-sweep Zepto failures → emit `warning`, continue, finish with partial
  results and a visible banner; never a blank failure.
- Persistent Zepto API failure (blocked / endpoints changed) → explicit
  "Zepto API error" surfaced to the user; full request/response detail logged
  server-side for debugging.
- Geolocation denied → fall back to pincode entry.

## Testing strategy

- **Backend (pytest, TDD):** unit tests for the link parser, hex-grid generator,
  geofence/coverage math, store-cache queries, and SSE event assembly — all
  against recorded Zepto response fixtures, no live calls in the test suite.
- **Live smoke test:** a manual script (`scripts/smoke_zepto.py`) that runs the
  real handshake + one geocode + one availability check, used at implementation
  start (endpoint verification) and whenever Zepto seems broken.
- **Frontend:** type-check + production build in CI fashion; a few component
  tests for result-list rendering.

## Deployment

- One Dockerfile: build frontend → copy `dist/` into the Python image → uvicorn
  serves FastAPI + static files.
- SQLite database on a mounted volume.
- Env vars: `PROXY_URL` (optional), `DATABASE_PATH`, `ZEPTO_CONCURRENCY`
  (default 5).
- Deployed via Dokploy on the Oracle VPS. Optional protection via Dokploy
  basic-auth.

## Out of scope (v1)

- Accounts/login, back-in-stock notifications, price history, multi-product
  comparison, ordering/cart integration.

## Risks

- **Unofficial API drift:** endpoints/headers may change without notice.
  Mitigated by isolating everything in `zepto_client.py` and the smoke script.
  First implementation task is verifying current endpoints against live traffic.
- **Rate limiting / IP blocks:** mitigated by store caching, concurrency caps,
  backoff, and the residential proxy fallback.
- **Geocoding ambiguity:** a pincode can span multiple stores; coordinates are
  authoritative, pincode is a convenience input.

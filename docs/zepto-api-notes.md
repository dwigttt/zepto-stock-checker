# Zepto internal API — verified live 2026-06-12

Zepto migrated `www.zeptonow.com` → `www.zepto.com` (old domain 301s). The old
`api.zeptonow.com` host is dead (CloudFront distribution removed). The web app
now calls **`https://bff-gateway.zepto.com/`** (alias `bff-gateway.zeptonow.com`,
same CloudFront distribution) with microservice-prefixed paths.

All findings below were verified with live curl requests on 2026-06-12.

## Session handshake

`GET https://www.zepto.com/` with a browser User-Agent issues cookies:
`device_id`, `session_id`, `XSRF-TOKEN`, `csrfSecret`, `serviceability`,
`marketplace`. No login needed for catalog reads (`x-without-bearer: true`).

## Standard headers for bff-gateway calls

```
User-Agent: <browser UA>
Accept: application/json
platform: WEB
tenant: ZEPTO
x-without-bearer: true
app_version: 16.2.11        (web artifact version; bump if responses degrade)
Origin: https://www.zepto.com
Referer: https://www.zepto.com/
x-xsrf-token: <decoded XSRF-TOKEN cookie>
Cookie: <handshake cookies>
```

## Geocoding (pincode → lat/lng)

- `GET bff-gateway.zepto.com/api/v1/maps/place/autocomplete/?place_name={pincode}`
  → `predictions[0].place_id`, `.description`
- `GET bff-gateway.zepto.com/api/v1/maps/place/details/?place_id={place_id}`
  → `result.geometry.location.{lat,lng}`

## Store resolution (coordinate → dark store) — the sweep primitive

`HEAD https://www.zepto.com/` with cookie
`user_position={"latitude":<lat>,"longitude":<lng>}` (URL-encoded JSON).
The `user_position` cookie is what triggers resolution (bare `latitude`/
`longitude` cookies alone do NOT). HEAD works — no body transferred.

Response `set-cookie: serviceability=<urlencoded JSON>`:

```json
{
  "primaryStore": {"serviceable": true, "storeId": "b1403534-...", "etaInMinutes": 13, ...},
  "secondaryStore": {...},
  "storeDetailedInfo": {"city": "Bengaluru", "name": "BLR-RICHMOND TOWN"},
  "timeSaved": 1781248251223
}
```

Unserviceable coordinates return `{"primaryStore":{"serviceable":false},...}`.
No store coordinates are exposed — cache the store against the probe point
(running centroid across probes works well).

There is also `bff-gateway.zepto.com/serviceability-service/api/v1/serviceability`
but it returns `invalid_lat/lng/regionId` for every param shape tried
(query/header/cookie); the homepage set-cookie flow is the working primitive.

## Product detail + availability (per store)

```
GET bff-gateway.zepto.com/product-assortment-service/api/v2/product-detail
    ?storeId={storeUuid}&productVariantId={pvid}
```

Returns `product.name`, `.brand`, and `product.storeProducts[0]` with:
- `outOfStock` (bool) — the availability signal
- `availableQuantity`
- `discountedSellingPrice`, `mrp`, `superSaverSellingPrice` — **paise**, ÷100
- `productVariant.images[].path` → image URL is
  `https://cdn.zeptonow.com/production/{path}`

Sample store id seen in their JS (useful as fallback store context for fetching
product cards before the user shares a location):
`0059ff6a-7eb0-477a-a7f5-69256f2c444b` (sample superstore, lat 12.96902 lng 77.75395).

## Search (not needed for v1, verified working)

`POST bff-gateway.zepto.com/user-search-service/api/v3/search`
body `{"query","pageNumber":0,"mode":"AUTOSUGGEST","userSessionId":""}` → widget layout.

## Share links

- Web: `https://www.zepto.com/pn/{slug}/pvid/{uuid}` (zeptonow.com variants 301 to zepto.com)
- App shares: Branch.io links → follow redirects, then regex `/pvid/{uuid}` from
  the final URL (fallback: regex the body).

## Anonymous vs logged-in sessions (verified 2026-06-12)

Catalog reads work without login, but Zepto personalises what logged-in users
see. Confirmed differences:

- **The public API under-reports discounts.** The price gap is real and
  reproducible: for the same product, same store, same anonymous session, the
  public `product-detail` API returned `discountedSellingPrice: 4000`
  (no discount, `discountPercent: 0`) while zepto.com's own logged-out SSR
  product page rendered `discountedSellingPrice: 3800` (`discountPercent: 5`).
  The SSR page is a *fresh* render (`x-cache: Miss from cloudfront`,
  `max-age=0`), not stale caching — Zepto's server applies campaign pricing in
  a context the public anonymous API doesn't expose. **No anonymous request
  shaping reproduces the lower price** — tested handshake cookies, dropping
  `x-without-bearer`, `platform: APP`, and `user_position`; all return the
  undiscounted price. So our number is Zepto's *guest/list* price; the real
  checkout price (campaign + Pass) is often lower (user report: ₹93 vs ₹99).
  Getting it would require Zepto login (bearer token) or scraping the SSR PDP
  per product (home-store only, expensive). Anonymously,
  `discountedSellingPrice == superSaverSellingPrice` always, and
  `valueBasedDiscount` is `{}` — not a parsing bug, just the public tier.
- **Search is stubbed for anonymous API calls.**
  `user-search-service/api/v3/search` returns HTTP 200 with zero products —
  only an `UPDATE_APP_VERSION_ANDROID` banner widget. Harmless here (the app
  never searches), but don't build features on it without auth.
- **Availability may differ when logged in** (user report: item available in
  their logged-in app while this tool said out of stock — unconfirmed).
  product-detail *availability* matches the logged-out website exactly, so any
  stock gap is login personalisation or a different dark store (their saved
  address vs the searched pin), not a parsing bug. Use
  `scripts/compare_stock.py <link|pvid> <pincode|"lat,lng"> [--radius N]` to
  triage such reports — it cross-checks our API against zepto.com's own SSR
  page and tells you whether a mismatch is ours or expected personalisation.

## Anti-bot posture

AWS CloudFront only; no Cloudflare/JS challenge. Keep volume low: cache stores,
cap concurrency (~5), back off on 403/429. Non-Indian IPs may be geofenced —
route through `PROXY_URL` (Indian residential) if the VPS gets blocked.

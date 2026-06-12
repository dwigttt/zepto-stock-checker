"""All Zepto-specific knowledge lives here: hosts, headers, cookies, parsing.

Verified against live traffic on 2026-06-12 — see docs/zepto-api-notes.md.
If Zepto changes their API, this is the only module that should need fixing.
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from urllib.parse import quote, unquote

import httpx

from .links import PVID_RE

log = logging.getLogger("zepto")

WEB_BASE = "https://www.zepto.com"
BFF_BASE = "https://bff-gateway.zepto.com"
CDN_BASE = "https://cdn.zeptonow.com/production"
APP_VERSION = "16.2.11"
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0"
)
# Store id Zepto's own web app uses as a placeholder context; lets us fetch a
# product card before the user has shared a serviceable location.
SAMPLE_STORE_ID = "0059ff6a-7eb0-477a-a7f5-69256f2c444b"

HANDSHAKE_MAX_AGE_S = 6 * 3600
RETRY_STATUSES = {403, 429, 500, 502, 503, 504}


@dataclass
class StoreResolution:
    serviceable: bool
    store_id: str | None = None
    store_name: str | None = None
    city: str | None = None
    eta_minutes: int | None = None


@dataclass
class ProductAtStore:
    status: str  # in_stock | out_of_stock | not_carried | error
    name: str | None = None
    brand: str | None = None
    image_url: str | None = None
    price: float | None = None
    mrp: float | None = None
    available_quantity: int | None = None


class ZeptoError(Exception):
    pass


class ZeptoClient:
    def __init__(self, proxy_url: str | None = None, concurrency: int = 5):
        self._client = httpx.AsyncClient(
            proxy=proxy_url,
            timeout=httpx.Timeout(20.0),
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT, "Accept-Language": "en-IN,en;q=0.9"},
        )
        self._sem = asyncio.Semaphore(concurrency)
        self._handshake_at: float = 0.0
        self._handshake_lock = asyncio.Lock()

    async def aclose(self) -> None:
        await self._client.aclose()

    # -- session ---------------------------------------------------------

    async def _ensure_session(self, force: bool = False) -> None:
        async with self._handshake_lock:
            if not force and time.monotonic() - self._handshake_at < HANDSHAKE_MAX_AGE_S:
                return
            resp = await self._client.get(WEB_BASE + "/", headers={"Accept": "text/html"})
            resp.raise_for_status()
            if not self._client.cookies.get("session_id"):
                raise ZeptoError("handshake did not issue session cookies")
            self._handshake_at = time.monotonic()
            log.info("zepto handshake ok")

    def _bff_headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "platform": "WEB",
            "tenant": "ZEPTO",
            "x-without-bearer": "true",
            "app_version": APP_VERSION,
            "Origin": WEB_BASE,
            "Referer": WEB_BASE + "/",
        }
        xsrf = self._client.cookies.get("XSRF-TOKEN")
        if xsrf:
            headers["x-xsrf-token"] = unquote(xsrf)
        return headers

    async def _request(self, method: str, url: str, **kwargs) -> httpx.Response:
        await self._ensure_session()
        last: httpx.Response | None = None
        for attempt in range(3):
            async with self._sem:
                try:
                    resp = await self._client.request(method, url, **kwargs)
                except httpx.HTTPError as e:
                    if attempt == 2:
                        raise ZeptoError(f"request failed: {e}") from e
                    await asyncio.sleep(1.5 * 2**attempt)
                    continue
            if resp.status_code not in RETRY_STATUSES:
                return resp
            last = resp
            if resp.status_code in (401, 403):
                await self._ensure_session(force=True)
            await asyncio.sleep(1.5 * 2**attempt)
        return last  # caller decides what a non-2xx means

    # -- geocoding -------------------------------------------------------

    async def autocomplete(self, query: str) -> list[dict]:
        """Free-text place/pincode → ranked place suggestions."""
        resp = await self._request(
            "GET",
            f"{BFF_BASE}/api/v1/maps/place/autocomplete/",
            params={"place_name": query},
            headers=self._bff_headers(),
        )
        if resp.status_code != 200:
            raise ZeptoError(f"autocomplete failed: HTTP {resp.status_code}")
        predictions = resp.json().get("predictions") or []
        results = []
        for p in predictions[:6]:
            fmt = p.get("structured_formatting") or {}
            results.append(
                {
                    "place_id": p["place_id"],
                    "description": p.get("description", ""),
                    "main_text": fmt.get("main_text", p.get("description", "")),
                    "secondary_text": fmt.get("secondary_text", ""),
                }
            )
        return results

    async def place_details(self, place_id: str, label: str = "") -> dict | None:
        resp = await self._request(
            "GET",
            f"{BFF_BASE}/api/v1/maps/place/details/",
            params={"place_id": place_id},
            headers=self._bff_headers(),
        )
        if resp.status_code != 200:
            raise ZeptoError(f"place details failed: HTTP {resp.status_code}")
        loc = resp.json().get("result", {}).get("geometry", {}).get("location")
        if not loc:
            return None
        return {"lat": loc["lat"], "lng": loc["lng"], "label": label or place_id}

    async def geocode(self, query: str) -> dict | None:
        """Pincode or free-text place → {lat, lng, label} (best match)."""
        suggestions = await self.autocomplete(query)
        if not suggestions:
            return None
        best = suggestions[0]
        return await self.place_details(best["place_id"], best["description"])

    # -- store resolution (the sweep primitive) ---------------------------

    async def resolve_store(self, lat: float, lng: float) -> StoreResolution:
        """Which dark store serves this coordinate?

        A HEAD to the homepage with a user_position cookie makes the server
        answer in a serviceability set-cookie. Cheap: no response body.
        """
        position = quote(
            json.dumps({"latitude": lat, "longitude": lng}, separators=(",", ":")), safe=""
        )
        resp = await self._request(
            "HEAD",
            WEB_BASE + "/",
            headers={"Accept": "text/html", "Cookie": f"user_position={position}"},
        )
        if resp.status_code != 200:
            raise ZeptoError(f"serviceability probe failed: HTTP {resp.status_code}")
        for set_cookie in resp.headers.get_list("set-cookie"):
            if not set_cookie.startswith("serviceability="):
                continue
            raw = set_cookie.split(";", 1)[0].split("=", 1)[1]
            data = json.loads(unquote(raw))
            primary = data.get("primaryStore") or {}
            info = data.get("storeDetailedInfo") or {}
            if primary.get("serviceable") and primary.get("storeId"):
                return StoreResolution(
                    serviceable=True,
                    store_id=primary["storeId"],
                    store_name=info.get("name"),
                    city=info.get("city"),
                    eta_minutes=primary.get("etaInMinutes"),
                )
            return StoreResolution(serviceable=False)
        raise ZeptoError("no serviceability cookie in probe response")

    # -- product availability ---------------------------------------------

    async def product_at_store(self, pvid: str, store_id: str) -> ProductAtStore:
        # Without a storeId *header* the endpoint returns a stub with
        # outOfStock=true for everything; the query param alone is not enough.
        resp = await self._request(
            "GET",
            f"{BFF_BASE}/product-assortment-service/api/v2/product-detail",
            params={"storeId": store_id, "productVariantId": pvid},
            headers={**self._bff_headers(), "storeId": store_id},
        )
        if resp.status_code in (400, 404):
            return ProductAtStore(status="not_carried")
        if resp.status_code != 200:
            return ProductAtStore(status="error")
        product = resp.json().get("product") or {}
        store_products = product.get("storeProducts") or []
        if not store_products:
            return ProductAtStore(status="not_carried", name=product.get("name"))
        sp = store_products[0]
        variant = sp.get("productVariant") or {}
        images = variant.get("images") or []
        image_url = f"{CDN_BASE}/{images[0]['path']}" if images else None
        price_paise = sp.get("discountedSellingPrice") or sp.get("superSaverSellingPrice")
        mrp_paise = sp.get("mrp") or variant.get("mrp")
        return ProductAtStore(
            status="out_of_stock" if sp.get("outOfStock") else "in_stock",
            name=product.get("name"),
            brand=product.get("brand"),
            image_url=image_url,
            price=price_paise / 100 if price_paise else None,
            mrp=mrp_paise / 100 if mrp_paise else None,
            available_quantity=sp.get("availableQuantity"),
        )

    # -- share links -------------------------------------------------------

    async def resolve_share_link(self, url: str) -> str | None:
        """Follow a share link's redirects and extract the pvid."""
        try:
            resp = await self._request("GET", url, headers={"Accept": "text/html"})
        except ZeptoError:
            return None
        m = PVID_RE.search(str(resp.url))
        if m:
            return m.group(1).lower()
        m = PVID_RE.search(resp.text[:200_000])
        return m.group(1).lower() if m else None

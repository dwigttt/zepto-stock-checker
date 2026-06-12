"""Triage a "the app is wrong about stock/price" report.

Given a product link (or bare pvid) and a location, prints what our API sees
and cross-checks it against Zepto's own logged-out website for the same spot.
If the two agree, a different answer in someone's Zepto app means login
personalisation or a different dark store — not a bug in this app.

  cd backend && uv run python scripts/compare_stock.py <link-or-pvid> <pincode|"lat,lng"> [--radius 5]
"""

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.links import extract_pvid, first_url, looks_like_zepto  # noqa: E402
from app.search import run_search  # noqa: E402
from app.store_cache import StoreCache  # noqa: E402
from app.zepto import WEB_BASE, ZeptoClient  # noqa: E402

LATLNG_RE = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$")


async def resolve_pvid(client: ZeptoClient, text: str) -> str | None:
    pvid = extract_pvid(text)
    if pvid:
        return pvid
    if re.fullmatch(r"[0-9a-fA-F-]{36}", text.strip()):
        return text.strip().lower()
    url = first_url(text)
    if url and looks_like_zepto(url):
        return await client.resolve_share_link(url)
    return None


SP_PRICE_RE = re.compile(r'"storeProduct":\{.{0,800}?"discountedSellingPrice":(\d+)')
SP_OOS_RE = re.compile(r'"storeProduct":\{.{0,800}?"outOfStock":(true|false)')


async def website_view(client: ZeptoClient, pvid: str, lat: float, lng: float) -> dict:
    """What does zepto.com itself (logged out) show for this product here?

    Reads the server-rendered product page. The product JSON ships inside an
    escaped RSC stream (`\\"storeProduct\\":{...}`), so we unescape first, then
    read the main product's `storeProduct` block. When in stock, the SSR omits
    the `outOfStock` flag, so absence-with-a-price means in stock. The visible
    buy-box text is a cross-check.
    """
    position = quote(
        json.dumps({"latitude": lat, "longitude": lng}, separators=(",", ":")), safe=""
    )
    resp = await client._client.get(
        f"{WEB_BASE}/pn/p/pvid/{pvid}",
        headers={"Accept": "text/html", "Cookie": f"user_position={position}"},
    )
    html = resp.text
    unescaped = html.replace('\\"', '"')
    price_m = SP_PRICE_RE.search(unescaped)
    oos_m = SP_OOS_RE.search(unescaped)
    buybox_oos = "out of stock" in html.lower() or "sold out" in html.lower()
    price = int(price_m.group(1)) / 100 if price_m else None
    if oos_m is not None:
        oos = oos_m.group(1) == "true"
    elif price is not None:
        oos = buybox_oos  # storeProduct present, no flag → trust the buy-box
    else:
        oos = None  # couldn't read the product block at all
    return {"http": resp.status_code, "oos": oos, "price": price, "page_says_oos": buybox_oos}


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("product", help="Zepto product link, share text, or bare pvid")
    ap.add_argument("location", help='pincode / place name, or "lat,lng"')
    ap.add_argument(
        "--radius", type=float, default=0, help="also sweep stores within this many km"
    )
    args = ap.parse_args()

    client = ZeptoClient()
    try:
        pvid = await resolve_pvid(client, args.product)
        if not pvid:
            print("could not extract a pvid from that input")
            return 1
        print(f"pvid: {pvid}")

        m = LATLNG_RE.match(args.location)
        if m:
            lat, lng = float(m.group(1)), float(m.group(2))
            label = args.location
        else:
            geo = await client.geocode(args.location)
            if not geo:
                print(f"could not geocode {args.location!r}")
                return 1
            lat, lng, label = geo["lat"], geo["lng"], geo["label"]
        print(f"location: {label} ({lat:.5f}, {lng:.5f})")

        home = await client.resolve_store(lat, lng)
        if not home.serviceable or not home.store_id:
            print("Zepto does not serve this exact spot — no home store to compare.")
            return 1
        print(f"home store: {home.store_name} ({home.store_id})")

        api = await client.product_at_store(pvid, home.store_id)
        print(f"\nour API     : {api.status}  price={api.price}  qty={api.available_quantity}")

        web = await website_view(client, pvid, lat, lng)
        web_status = (
            "unknown"
            if web["oos"] is None
            else ("out_of_stock" if web["oos"] else "in_stock")
        )
        print(
            f"zepto.com   : {web_status}  price={web['price']}  "
            f"(HTTP {web['http']}, buy-box says OOS: {web['page_says_oos']})"
        )

        stock_agrees = web["oos"] is not None and (api.status == "out_of_stock") == web["oos"]
        price_differs = (
            web["price"] is not None
            and api.price is not None
            and api.price != web["price"]
        )

        if web["oos"] is None:
            print("\nverdict: couldn't read the website's availability — compare manually.")
        elif not stock_agrees:
            print(
                "\nverdict: STOCK MISMATCH between our API and zepto.com — this is on us.\n"
                "Re-check parsing in app/zepto.py product_at_store()."
            )
        elif price_differs:
            print(
                f"\nverdict: stock agrees, but PRICE differs — we show "
                f"₹{api.price:g}, the website shows ₹{web['price']:g}.\n"
                "Expected: zepto.com applies campaign/Pass discounts in its own\n"
                "render that the public anonymous API doesn't expose. We can't get\n"
                "the lower price without Zepto login. Our number is the guest price."
            )
        else:
            print(
                "\nverdict: our API matches zepto.com's logged-out view exactly.\n"
                "If a logged-in Zepto app disagrees, the cause is login\n"
                "personalisation (Pass/tier pricing, personalised assortment) or a\n"
                "different dark store serving their saved address — not this app."
            )

        if args.radius > 0:
            print(f"\nsweeping stores within {args.radius} km (guest view):")
            cache = StoreCache(":memory:")
            try:
                async for ev in run_search(
                    client, cache, pvid, lat, lng, args.radius, force=True
                ):
                    if ev["type"] == "store_result":
                        print(
                            f"  {ev['status']:<13} {ev['store'].get('name') or '?':<38}"
                            f" {ev['distance_km']:>5} km  price={ev['price']}"
                        )
                    elif ev["type"] == "done":
                        print(f"  summary: {ev['summary']}")
            finally:
                cache.close()
        return 0
    finally:
        await client.aclose()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

"""Manual smoke test against the live Zepto API.

Run whenever Zepto seems broken:  cd backend && uv run python scripts/smoke_zepto.py
"""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.zepto import ZeptoClient  # noqa: E402

TEST_PINCODE = "560034"  # Koramangala, Bengaluru
TEST_LINK = "https://www.zepto.com/pn/amul-rabri-cup/pvid/579bf27b-6d7a-4aa8-83d2-2d3455e515d8"


async def main() -> int:
    # Honour PROXY_URL so this doubles as a proxy check (non-Indian IPs are
    # geofenced; route through PROXY_URL to confirm it reaches Zepto).
    proxy = os.environ.get("PROXY_URL") or None
    print(f"proxy: {'on' if proxy else 'off (direct)'}")
    client = ZeptoClient(proxy)
    failures = 0
    try:
        geo = await client.geocode(TEST_PINCODE)
        print(f"geocode({TEST_PINCODE}) -> {geo}")
        failures += geo is None

        store = await client.resolve_store(geo["lat"], geo["lng"])
        print(f"resolve_store -> {store}")
        failures += not store.serviceable

        pvid = await client.resolve_share_link(TEST_LINK)
        print(f"resolve_share_link -> {pvid}")
        failures += pvid is None

        product = await client.product_at_store(pvid, store.store_id)
        print(f"product_at_store -> {product}")
        failures += product.status == "error"
    finally:
        await client.aclose()
    print("SMOKE", "FAIL" if failures else "OK")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

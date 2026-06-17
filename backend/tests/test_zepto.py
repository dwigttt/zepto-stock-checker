"""Pure-parser tests for zepto.py — no network.

Covers the two anonymous-API quirks that caused false "out of stock":
  * serviceability lists a secondaryStore Zepto also fulfils from
  * product-detail returns fallback data (fallbackType != NONE) when the
    requested store doesn't carry the variant
"""

import json
from urllib.parse import quote

import httpx
import pytest

from app.zepto import ZeptoClient, ZeptoError, _parse_product_detail, _parse_serviceability


def _serviceability_cookie(payload: dict) -> str:
    return f"serviceability={quote(json.dumps(payload))}; Path=/; HttpOnly"


# -- serviceability ---------------------------------------------------------

def test_parse_serviceability_extracts_primary_and_secondary():
    cookie = _serviceability_cookie(
        {
            "primaryStore": {"serviceable": True, "storeId": "primary-1", "etaInMinutes": 9},
            "secondaryStore": {"serviceable": True, "storeId": "secondary-2", "etaInMinutes": 27},
            "storeDetailedInfo": {"name": "MUM-Sainath Nagar", "city": "Mumbai"},
        }
    )
    res = _parse_serviceability(["other=x", cookie])
    assert res.serviceable
    assert res.store_id == "primary-1"
    assert res.store_name == "MUM-Sainath Nagar"
    assert res.eta_minutes == 9
    assert res.secondary_store_id == "secondary-2"
    assert res.secondary_eta_minutes == 27


def test_parse_serviceability_without_secondary():
    cookie = _serviceability_cookie(
        {
            "primaryStore": {"serviceable": True, "storeId": "primary-1", "etaInMinutes": 10},
            "storeDetailedInfo": {"name": "Store", "city": "City"},
        }
    )
    res = _parse_serviceability([cookie])
    assert res.store_id == "primary-1"
    assert res.secondary_store_id is None
    assert res.secondary_eta_minutes is None


def test_parse_serviceability_ignores_unserviceable_secondary():
    cookie = _serviceability_cookie(
        {
            "primaryStore": {"serviceable": True, "storeId": "primary-1", "etaInMinutes": 10},
            "secondaryStore": {"serviceable": False, "storeId": "secondary-2", "etaInMinutes": 40},
        }
    )
    res = _parse_serviceability([cookie])
    assert res.secondary_store_id is None


def test_parse_serviceability_not_serviceable():
    cookie = _serviceability_cookie({"primaryStore": {"serviceable": False}})
    res = _parse_serviceability([cookie])
    assert res.serviceable is False
    assert res.store_id is None


# -- product detail ---------------------------------------------------------

def test_parse_product_detail_fallback_is_not_carried():
    """fallbackType != NONE means the store doesn't carry the variant — Zepto
    returned a fallback/sample store's data, which must NOT be read as OOS."""
    data = {
        "fallbackType": "PRODUCT_VARIANT_ID",
        "product": {"name": "Nourish You Plant Protein", "storeProducts": [
            {"outOfStock": True, "availableQuantity": 0, "discountedSellingPrice": 96400}
        ]},
    }
    res = _parse_product_detail(data)
    assert res.status == "not_carried"
    assert res.name == "Nourish You Plant Protein"


def test_parse_product_detail_in_stock():
    data = {
        "fallbackType": "NONE",
        "product": {"name": "X", "brand": "B", "storeProducts": [
            {"outOfStock": False, "availableQuantity": 2, "discountedSellingPrice": 99300, "mrp": 100000}
        ]},
    }
    res = _parse_product_detail(data)
    assert res.status == "in_stock"
    assert res.price == 993.0
    assert res.mrp == 1000.0
    assert res.available_quantity == 2


def test_parse_product_detail_out_of_stock_when_carried():
    data = {
        "fallbackType": "NONE",
        "product": {"name": "X", "storeProducts": [
            {"outOfStock": True, "availableQuantity": 0, "discountedSellingPrice": 5000}
        ]},
    }
    res = _parse_product_detail(data)
    assert res.status == "out_of_stock"


def test_parse_product_detail_empty_store_products_is_not_carried():
    data = {"fallbackType": "NONE", "product": {"name": "X", "storeProducts": []}}
    res = _parse_product_detail(data)
    assert res.status == "not_carried"


# -- bandwidth: handshake + share-link should avoid downloading page bodies ---

async def test_handshake_uses_head_not_get():
    """The session handshake only needs the set-cookie headers, not the 125 KB
    homepage body — so it must use HEAD."""
    methods = []

    def handler(request):
        methods.append(request.method)
        return httpx.Response(200, headers={"set-cookie": "session_id=abc; Path=/"})

    client = ZeptoClient(transport=httpx.MockTransport(handler))
    try:
        await client._ensure_session(force=True)
    finally:
        await client.aclose()
    assert methods == ["HEAD"]


async def test_resolve_share_link_uses_head_when_pvid_in_url():
    """The pvid is in the link's (redirected) URL, so a HEAD resolves it without
    downloading the ~77 KB product page body."""
    PVID = "11111111-1111-1111-1111-111111111111"
    calls = []

    def handler(request):
        calls.append((request.method, request.url.path))
        if request.url.path == "/":
            return httpx.Response(200, headers={"set-cookie": "session_id=x; Path=/"})
        return httpx.Response(200, text="body should not be downloaded")

    client = ZeptoClient(transport=httpx.MockTransport(handler))
    try:
        pvid = await client.resolve_share_link(f"https://www.zepto.com/pn/foo/pvid/{PVID}")
    finally:
        await client.aclose()
    assert pvid == PVID
    product_methods = [m for (m, p) in calls if p != "/"]
    assert product_methods == ["HEAD"]  # body never fetched


async def test_handshake_blocked_raises_zepto_error_not_raw_httpx():
    """A blocked proxy IP (403) must surface as ZeptoError so callers' existing
    `except ZeptoError` handling degrades gracefully instead of a raw 500."""
    def handler(request):
        return httpx.Response(403)

    client = ZeptoClient(transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(ZeptoError):
            await client._ensure_session(force=True)
    finally:
        await client.aclose()


async def test_handshake_falls_back_to_get_when_head_rejected():
    """If a cold HEAD is rejected (some WAFs/edges do) but GET works, recover."""
    methods = []

    def handler(request):
        methods.append(request.method)
        if request.method == "HEAD":
            return httpx.Response(403)
        return httpx.Response(200, headers={"set-cookie": "session_id=ok; Path=/"})

    client = ZeptoClient(transport=httpx.MockTransport(handler))
    try:
        await client._ensure_session(force=True)  # must not raise
    finally:
        await client.aclose()
    assert methods == ["HEAD", "GET"]


async def test_resolve_share_link_falls_back_to_body():
    """When the URL alone doesn't reveal the pvid, fall back to reading the body."""
    PVID = "22222222-2222-2222-2222-222222222222"

    def handler(request):
        if request.url.path == "/":
            return httpx.Response(200, headers={"set-cookie": "session_id=x; Path=/"})
        if request.method == "HEAD":
            return httpx.Response(200)  # nothing in the URL to go on
        return httpx.Response(200, text=f'<a href="/pvid/{PVID}">buy</a>')

    client = ZeptoClient(transport=httpx.MockTransport(handler))
    try:
        pvid = await client.resolve_share_link("https://www.zepto.com/share/abc")
    finally:
        await client.aclose()
    assert pvid == PVID

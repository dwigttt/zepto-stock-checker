import hmac
import json
import logging
from contextlib import asynccontextmanager
from dataclasses import asdict

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config
from .links import extract_pvid, first_url, looks_like_zepto
from .ratelimit import ConcurrencyGate, RateLimiter, TokenBucket
from .search import run_search
from .store_cache import StoreCache
from .zepto import SAMPLE_STORE_ID, ZeptoClient, ZeptoError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.zepto = ZeptoClient(config.PROXY_URL, config.ZEPTO_CONCURRENCY)
    app.state.cache = StoreCache(config.DATABASE_PATH)
    app.state.limiter = RateLimiter(
        request_capacity=config.REQUEST_BURST,
        request_refill_per_sec=config.REQUESTS_PER_MIN / 60,
        search_capacity=config.SEARCH_BURST,
        search_refill_per_sec=config.SEARCHES_PER_DAY / 86_400,
    )
    app.state.search_gate = ConcurrencyGate(config.MAX_CONCURRENT_SEARCHES)
    # Whole-instance daily backstops, the main levers on total upstream/proxy
    # traffic: a coarse search cap and a fine-grained probe (bandwidth) budget.
    app.state.global_searches = TokenBucket(
        config.GLOBAL_SEARCH_BURST, config.GLOBAL_SEARCHES_PER_DAY / 86_400
    )
    app.state.probe_budget = TokenBucket(
        config.PROBE_BURST, config.PROBES_PER_DAY / 86_400
    )
    yield
    await app.state.zepto.aclose()
    app.state.cache.close()


app = FastAPI(title="zepto-finder", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# -- abuse controls ---------------------------------------------------------


def client_ip(request: Request) -> str:
    """Identity for per-client rate limiting. Behind a proxy the real client is
    in X-Forwarded-For; direct, it's the socket peer."""
    if config.TRUST_FORWARDED_FOR:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _provided_token(request: Request) -> str | None:
    # Header for normal fetches; query param for EventSource, which can't set
    # custom headers.
    return request.headers.get("x-app-token") or request.query_params.get("token")


def auth_ok(request: Request) -> bool:
    if not config.APP_TOKEN:
        return True
    token = _provided_token(request)
    return bool(token) and hmac.compare_digest(token, config.APP_TOKEN)


async def require_rate(request: Request) -> None:
    """Per-client request budget. No auth — used by the public /api/config."""
    if not request.app.state.limiter.allow_request(client_ip(request)):
        raise HTTPException(429, "Too many requests. Slow down for a bit.")


async def require_access(request: Request) -> None:
    """Token auth + per-client request budget for the data endpoints."""
    if not auth_ok(request):
        raise HTTPException(401, "Access token missing or invalid.")
    await require_rate(request)


class ResolveRequest(BaseModel):
    url: str
    lat: float | None = None
    lng: float | None = None


@app.get("/api/config")
async def public_config(_: None = Depends(require_rate)):
    """Settings the frontend needs before it can talk to the gated endpoints."""
    return {
        "auth_required": config.APP_TOKEN is not None,
        "max_radius_km": config.MAX_RADIUS_KM,
    }


@app.post("/api/resolve", dependencies=[Depends(require_access)])
async def resolve_link(body: ResolveRequest):
    """Share link (or pasted share text) → pvid + product card."""
    zepto: ZeptoClient = app.state.zepto
    text = body.url.strip()
    pvid = extract_pvid(text)
    if not pvid:
        url = first_url(text)
        if not url or not looks_like_zepto(url):
            raise HTTPException(422, "That doesn't look like a Zepto product link.")
        pvid = await zepto.resolve_share_link(url)
    if not pvid:
        raise HTTPException(422, "Couldn't find a product id in that link.")

    store_id = SAMPLE_STORE_ID
    if body.lat is not None and body.lng is not None:
        try:
            home = await zepto.resolve_store(body.lat, body.lng)
            if home.serviceable and home.store_id:
                store_id = home.store_id
        except ZeptoError:
            pass
    try:
        product = await zepto.product_at_store(pvid, store_id)
    except ZeptoError as e:
        raise HTTPException(502, f"Zepto API error: {e}")
    if product.status == "error":
        raise HTTPException(502, "Zepto API error while fetching the product.")
    return {"pvid": pvid, "product": asdict(product)}


@app.get("/api/geocode", dependencies=[Depends(require_access)])
async def geocode(q: str = Query(min_length=2)):
    zepto: ZeptoClient = app.state.zepto
    try:
        result = await zepto.geocode(q)
    except ZeptoError as e:
        raise HTTPException(502, f"Zepto API error: {e}")
    if not result:
        raise HTTPException(404, "Location not found. Try a pincode or locality name.")
    return result


@app.get("/api/suggest", dependencies=[Depends(require_access)])
async def suggest(q: str = Query(min_length=2)):
    zepto: ZeptoClient = app.state.zepto
    try:
        return {"suggestions": await zepto.autocomplete(q)}
    except ZeptoError as e:
        raise HTTPException(502, f"Zepto API error: {e}")


@app.get("/api/place", dependencies=[Depends(require_access)])
async def place(place_id: str = Query(min_length=4), label: str = ""):
    zepto: ZeptoClient = app.state.zepto
    try:
        result = await zepto.place_details(place_id, label)
    except ZeptoError as e:
        raise HTTPException(502, f"Zepto API error: {e}")
    if not result:
        raise HTTPException(404, "Couldn't locate that place.")
    return result


SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


def _sse_error(message: str) -> StreamingResponse:
    """A one-shot SSE stream carrying an error. EventSource can't read HTTP
    status codes, so auth/limit rejections are delivered in-band — and the
    client closes on a `done`/`error` event, so it won't reconnect-loop."""
    async def stream():
        yield f"data: {json.dumps({'type': 'error', 'message': message})}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream", headers=SSE_HEADERS)


@app.get("/api/search")
async def search(
    request: Request,
    pvid: str = Query(pattern=r"^[0-9a-f-]{36}$"),
    lat: float = Query(ge=-90, le=90),
    lng: float = Query(ge=-180, le=180),
    radius_km: float = Query(default=10, ge=1, le=config.MAX_RADIUS_KM),
    force: bool = Query(default=False),
):
    state = request.app.state
    if not auth_ok(request):
        return _sse_error("Access token missing or invalid.")
    # Check the cheap concurrency gate before spending any budget, so a "server
    # busy" rejection doesn't cost a search token.
    if not state.search_gate.try_acquire():
        return _sse_error("The server is busy with other searches right now — try again shortly.")
    if not state.limiter.allow_search(client_ip(request)):
        state.search_gate.release()
        return _sse_error("You've reached your search limit for now. Try again later.")
    if not state.global_searches.take():
        state.search_gate.release()
        return _sse_error("The app has hit today's overall search limit. Try again later.")

    async def stream():
        try:
            async for event in run_search(
                state.zepto, state.cache, pvid, lat, lng, radius_km, force,
                probe_budget=state.probe_budget,
            ):
                yield f"data: {json.dumps(event)}\n\n"
        finally:
            state.search_gate.release()

    return StreamingResponse(stream(), media_type="text/event-stream", headers=SSE_HEADERS)


@app.get("/api/stats", dependencies=[Depends(require_access)])
async def stats():
    return app.state.cache.stats()


if config.STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=config.STATIC_DIR, html=True), name="static")

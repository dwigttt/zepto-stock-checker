import json
import logging
from contextlib import asynccontextmanager
from dataclasses import asdict

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config
from .links import extract_pvid, first_url, looks_like_zepto
from .search import run_search
from .store_cache import StoreCache
from .zepto import SAMPLE_STORE_ID, ZeptoClient, ZeptoError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.zepto = ZeptoClient(config.PROXY_URL, config.ZEPTO_CONCURRENCY)
    app.state.cache = StoreCache(config.DATABASE_PATH)
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


class ResolveRequest(BaseModel):
    url: str
    lat: float | None = None
    lng: float | None = None


@app.post("/api/resolve")
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


@app.get("/api/geocode")
async def geocode(q: str = Query(min_length=2)):
    zepto: ZeptoClient = app.state.zepto
    try:
        result = await zepto.geocode(q)
    except ZeptoError as e:
        raise HTTPException(502, f"Zepto API error: {e}")
    if not result:
        raise HTTPException(404, "Location not found. Try a pincode or locality name.")
    return result


@app.get("/api/suggest")
async def suggest(q: str = Query(min_length=2)):
    zepto: ZeptoClient = app.state.zepto
    try:
        return {"suggestions": await zepto.autocomplete(q)}
    except ZeptoError as e:
        raise HTTPException(502, f"Zepto API error: {e}")


@app.get("/api/place")
async def place(place_id: str = Query(min_length=4), label: str = ""):
    zepto: ZeptoClient = app.state.zepto
    try:
        result = await zepto.place_details(place_id, label)
    except ZeptoError as e:
        raise HTTPException(502, f"Zepto API error: {e}")
    if not result:
        raise HTTPException(404, "Couldn't locate that place.")
    return result


@app.get("/api/search")
async def search(
    pvid: str = Query(pattern=r"^[0-9a-f-]{36}$"),
    lat: float = Query(ge=-90, le=90),
    lng: float = Query(ge=-180, le=180),
    radius_km: float = Query(default=10, ge=1, le=config.MAX_RADIUS_KM),
    force: bool = Query(default=False),
):
    async def stream():
        async for event in run_search(app.state.zepto, app.state.cache, pvid, lat, lng, radius_km, force):
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/stats")
async def stats():
    return app.state.cache.stats()


if config.STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=config.STATIC_DIR, html=True), name="static")

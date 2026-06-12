"""Search orchestrator: home check → store discovery sweep → per-store stock checks.

Yields SSE-ready event dicts as results arrive so the UI fills in live.
"""

import asyncio
import logging
from dataclasses import asdict
from typing import AsyncIterator

from .config import GRID_SPACING_KM, PROBE_COVERAGE_KM
from .grid import haversine_km, hex_grid
from .ratelimit import TokenBucket
from .store_cache import Store, StoreCache
from .zepto import ZeptoClient, ZeptoError

log = logging.getLogger("search")


async def run_search(
    client: ZeptoClient,
    cache: StoreCache,
    pvid: str,
    lat: float,
    lng: float,
    radius_km: float,
    force: bool = False,
    probe_budget: TokenBucket | None = None,
) -> AsyncIterator[dict]:
    queue: asyncio.Queue[dict | None] = asyncio.Queue()
    checked: set[str] = set()
    check_tasks: list[asyncio.Task] = []
    counts = {"in_stock": 0, "out_of_stock": 0, "not_carried": 0, "error": 0, "stores": 0}

    async def emit(event: dict) -> None:
        await queue.put(event)

    async def check_store(store: Store) -> None:
        distance = haversine_km(lat, lng, store.lat, store.lng)
        try:
            result = await client.product_at_store(pvid, store.id)
        except ZeptoError as e:
            log.warning("stock check failed for %s: %s", store.id, e)
            result = None
        status = result.status if result else "error"
        counts[status] = counts.get(status, 0) + 1
        await emit(
            {
                "type": "store_result",
                "store": asdict(store),
                "distance_km": round(distance, 1),
                "status": status,
                "price": result.price if result else None,
                "mrp": result.mrp if result else None,
            }
        )

    def start_check(store: Store) -> None:
        if store.id in checked:
            return
        checked.add(store.id)
        counts["stores"] += 1
        check_tasks.append(asyncio.create_task(check_store(store)))

    async def probe_point(plat: float, plng: float, progress: dict) -> None:
        try:
            res = await client.resolve_store(plat, plng)
        except ZeptoError as e:
            log.warning("probe (%.4f, %.4f) failed: %s", plat, plng, e)
            progress["failed"] += 1
            return
        finally:
            progress["probed"] += 1
            if progress["probed"] % 5 == 0 or progress["probed"] == progress["total"]:
                await emit({"type": "discovery_progress", **progress})
        store = cache.record_probe(plat, plng, res.store_id, res.store_name, res.city)
        # The probe point itself is inside the radius, so this store serves the
        # search area even if its (approximate) centroid lands slightly outside.
        if store:
            start_check(store)

    async def main_flow() -> None:
        try:
            # 1. The user's own location.
            home = await client.resolve_store(lat, lng)
            home_product = None
            if home.serviceable and home.store_id:
                checked.add(home.store_id)
                cache.record_probe(lat, lng, home.store_id, home.store_name, home.city)
                home_product = await client.product_at_store(pvid, home.store_id)
            await emit(
                {
                    "type": "home_result",
                    "serviceable": home.serviceable,
                    "city": home.city,
                    "store_name": home.store_name,
                    "eta_minutes": home.eta_minutes,
                    "product": asdict(home_product) if home_product else None,
                }
            )

            # Available right here — no need to sweep unless explicitly asked.
            if home_product and home_product.status == "in_stock" and not force:
                await emit({"type": "done", "summary": dict(counts)})
                return

            # 2. Stock checks for already-known stores start immediately...
            # (one grid cell of margin: a store just outside still serves the rim)
            for store in cache.stores_within(lat, lng, radius_km + GRID_SPACING_KM):
                start_check(store)

            # 3. ...while undiscovered parts of the circle are swept in parallel.
            undiscovered = [
                p
                for p in hex_grid(lat, lng, radius_km, GRID_SPACING_KM)
                if not cache.has_fresh_probe_near(p[0], p[1], PROBE_COVERAGE_KM)
            ]
            # Probing is the bulk of upstream (and proxy) traffic. A global daily
            # probe budget caps it: when short, map as much as the budget allows
            # and tell the user the rest was skipped rather than silently capping.
            if probe_budget is not None:
                granted = probe_budget.take_up_to(len(undiscovered))
            else:
                granted = len(undiscovered)
            to_probe = undiscovered[:granted]
            budget_limited = granted < len(undiscovered)

            progress = {"probed": 0, "failed": 0, "total": len(to_probe)}
            await emit(
                {
                    "type": "discovery_start",
                    "points_to_probe": len(to_probe),
                    "cached_stores": counts["stores"],
                }
            )
            if budget_limited:
                log.warning("probe budget limited sweep: %d/%d points", granted, len(undiscovered))
                await emit(
                    {
                        "type": "notice",
                        "message": "Daily store-mapping limit reached — some far stores may be missing. Try again later.",
                    }
                )
            if to_probe:
                await asyncio.gather(*(probe_point(p[0], p[1], progress) for p in to_probe))

            await emit({"type": "checking", "total_stores": counts["stores"]})
            if check_tasks:
                await asyncio.gather(*check_tasks)
            await emit({"type": "done", "summary": dict(counts)})
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("search failed")
            await emit({"type": "error", "message": "Search failed — Zepto API may be down or blocking. Check server logs."})
        finally:
            await queue.put(None)

    flow = asyncio.create_task(main_flow())
    try:
        while (event := await queue.get()) is not None:
            yield event
    finally:
        flow.cancel()
        for t in check_tasks:
            t.cancel()

"""run_search with a fake Zepto client — no network. Focus: the global probe
budget caps how many discovery probes a cold sweep issues."""

from app.ratelimit import TokenBucket
from app.search import run_search
from app.store_cache import StoreCache
from app.zepto import ProductAtStore, StoreResolution

PVID = "0059ff6a-7eb0-477a-a7f5-69256f2c444b"


class FakeClient:
    """Every coordinate is serviceable by a distinct store; nothing is in stock,
    so a search always proceeds to the discovery sweep."""

    def __init__(self):
        self.resolve_calls = 0
        self.product_calls = 0

    async def resolve_store(self, lat, lng):
        self.resolve_calls += 1
        return StoreResolution(
            serviceable=True,
            store_id=f"s-{lat:.3f}-{lng:.3f}",
            store_name="Store",
            city="City",
            eta_minutes=10,
        )

    async def product_at_store(self, pvid, store_id):
        self.product_calls += 1
        return ProductAtStore(status="out_of_stock")


async def collect(agen):
    return [event async for event in agen]


async def test_zero_probe_budget_skips_the_sweep():
    client = FakeClient()
    cache = StoreCache(":memory:")
    budget = TokenBucket(capacity=0, refill_per_sec=0.0)
    await collect(
        run_search(client, cache, PVID, 12.97, 77.59, 10, probe_budget=budget)
    )
    # Only the user's own location is resolved; no discovery probes.
    assert client.resolve_calls == 1


async def test_probe_budget_limits_number_of_probes():
    client = FakeClient()
    cache = StoreCache(":memory:")
    budget = TokenBucket(capacity=3, refill_per_sec=0.0)
    events = await collect(
        run_search(client, cache, PVID, 12.97, 77.59, 10, probe_budget=budget)
    )
    # 1 home resolve + exactly 3 granted probes.
    assert client.resolve_calls == 4
    # The cap is surfaced, not silent.
    assert any(e["type"] == "notice" for e in events)


async def test_no_budget_means_full_sweep():
    client = FakeClient()
    cache = StoreCache(":memory:")
    events = await collect(run_search(client, cache, PVID, 12.97, 77.59, 10))
    assert client.resolve_calls > 4  # many probes, unbounded
    assert not any(e["type"] == "notice" for e in events)

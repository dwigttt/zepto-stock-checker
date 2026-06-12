from app.store_cache import StoreCache


def make_cache():
    return StoreCache(":memory:")


def test_record_and_find_store():
    cache = make_cache()
    store = cache.record_probe(12.97, 77.59, "store-1", "BLR-TEST", "Bengaluru")
    assert store.id == "store-1"
    found = cache.stores_within(12.97, 77.59, 5)
    assert [s.id for s in found] == ["store-1"]
    assert cache.stores_within(13.5, 77.59, 5) == []


def test_centroid_updates_on_repeat_probes():
    cache = make_cache()
    cache.record_probe(12.96, 77.59, "store-1")
    store = cache.record_probe(12.98, 77.59, "store-1")
    assert abs(store.lat - 12.97) < 1e-9
    assert store == cache.stores_within(12.97, 77.59, 5)[0]


def test_fresh_probe_coverage():
    cache = make_cache()
    assert not cache.has_fresh_probe_near(12.97, 77.59, 2.0)
    cache.record_probe(12.97, 77.59, None)  # unserviceable probe
    assert cache.has_fresh_probe_near(12.97, 77.59, 2.0)
    assert cache.has_fresh_probe_near(12.975, 77.59, 2.0)  # ~0.5km away
    assert not cache.has_fresh_probe_near(13.1, 77.59, 2.0)  # ~14km away

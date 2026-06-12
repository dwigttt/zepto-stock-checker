from app.ratelimit import ConcurrencyGate, RateLimiter, TokenBucket


class FakeClock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


def test_bucket_allows_up_to_capacity_then_denies():
    clock = FakeClock()
    bucket = TokenBucket(capacity=3, refill_per_sec=0.0, clock=clock)
    assert bucket.take() is True
    assert bucket.take() is True
    assert bucket.take() is True
    assert bucket.take() is False  # empty, no refill


def test_bucket_refills_over_time():
    clock = FakeClock()
    bucket = TokenBucket(capacity=2, refill_per_sec=1.0, clock=clock)
    assert bucket.take() is True
    assert bucket.take() is True
    assert bucket.take() is False
    clock.advance(1.0)  # one token back
    assert bucket.take() is True
    assert bucket.take() is False


def test_bucket_never_exceeds_capacity():
    clock = FakeClock()
    bucket = TokenBucket(capacity=2, refill_per_sec=1.0, clock=clock)
    clock.advance(100)  # would refill 100 tokens, but cap is 2
    assert bucket.take() is True
    assert bucket.take() is True
    assert bucket.take() is False


def test_limiter_separates_clients():
    clock = FakeClock()
    limiter = RateLimiter(
        request_capacity=1,
        request_refill_per_sec=0.0,
        search_capacity=1,
        search_refill_per_sec=0.0,
        clock=clock,
    )
    assert limiter.allow_request("1.1.1.1") is True
    assert limiter.allow_request("1.1.1.1") is False  # client A exhausted
    assert limiter.allow_request("2.2.2.2") is True  # client B independent


def test_limiter_request_and_search_budgets_are_independent():
    clock = FakeClock()
    limiter = RateLimiter(
        request_capacity=1,
        request_refill_per_sec=0.0,
        search_capacity=1,
        search_refill_per_sec=0.0,
        clock=clock,
    )
    assert limiter.allow_request("ip") is True
    assert limiter.allow_request("ip") is False
    assert limiter.allow_search("ip") is True  # search bucket untouched by requests
    assert limiter.allow_search("ip") is False


def test_concurrency_gate_caps_active_and_releases():
    gate = ConcurrencyGate(limit=2)
    assert gate.try_acquire() is True
    assert gate.try_acquire() is True
    assert gate.try_acquire() is False  # at limit
    gate.release()
    assert gate.try_acquire() is True  # slot freed

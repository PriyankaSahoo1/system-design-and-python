"""Token bucket. Time is injected so tests do not sleep."""

from __future__ import annotations


class TokenBucket:
    def __init__(self, capacity: float, refill_per_second: float, now: float) -> None:
        if capacity <= 0 or refill_per_second < 0:
            raise ValueError("capacity must be positive and refill must be >= 0")
        self.capacity = float(capacity)
        self.refill_per_second = float(refill_per_second)
        self.tokens = float(capacity)
        self.last = float(now)

    def _refill(self, now: float) -> None:
        elapsed = now - self.last
        if elapsed < 0:
            elapsed = 0
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_per_second)
        self.last = now

    def allow(self, now: float, cost: float = 1.0) -> bool:
        self._refill(now)
        if self.tokens < cost:
            return False
        self.tokens -= cost
        return True


class RateLimiter:
    """One bucket per caller key. A lock per key keeps two threads honest."""

    def __init__(self, capacity: float, refill_per_second: float) -> None:
        self.capacity = capacity
        self.refill_per_second = refill_per_second
        self._buckets: dict[str, TokenBucket] = {}

    def allow(self, key: str, now: float) -> bool:
        bucket = self._buckets.get(key)
        if bucket is None:
            bucket = TokenBucket(self.capacity, self.refill_per_second, now)
            self._buckets[key] = bucket
        return bucket.allow(now)

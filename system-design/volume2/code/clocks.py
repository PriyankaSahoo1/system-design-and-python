"""Lamport clocks, vector clocks, and a lease lock with a fencing token."""

from __future__ import annotations


class LamportClock:
    def __init__(self) -> None:
        self.time = 0

    def tick(self) -> int:
        self.time += 1
        return self.time

    def receive(self, incoming: int) -> int:
        self.time = max(self.time, incoming) + 1
        return self.time


class VectorClock:
    def __init__(self, node_id: str, nodes: list[str]) -> None:
        self.node_id = node_id
        self.time = {node: 0 for node in nodes}

    def tick(self) -> dict[str, int]:
        self.time[self.node_id] += 1
        return dict(self.time)

    def receive(self, incoming: dict[str, int]) -> dict[str, int]:
        for node, value in incoming.items():
            self.time[node] = max(self.time[node], value)
        self.time[self.node_id] += 1
        return dict(self.time)


def happened_before(left: dict[str, int], right: dict[str, int]) -> bool:
    """True when left is a causal ancestor of right."""
    less_or_equal = all(left[key] <= right[key] for key in left)
    strictly_less = any(left[key] < right[key] for key in left)
    return less_or_equal and strictly_less


def concurrent(left: dict[str, int], right: dict[str, int]) -> bool:
    return not happened_before(left, right) and not happened_before(right, left)


class StaleFencingToken(Exception):
    pass


class LeaseLock:
    """The lock can expire. The fencing token is what makes a late writer harmless."""

    def __init__(self) -> None:
        self.holder: str | None = None
        self.expires_at = 0.0
        self.token = 0

    def acquire(self, client: str, now: float, ttl: float) -> int | None:
        if self.holder not in (None, client) and now < self.expires_at:
            return None
        self.token += 1
        self.holder = client
        self.expires_at = now + ttl
        return self.token


class FencedStore:
    def __init__(self) -> None:
        self.seen = 0
        self.value: str | None = None

    def write(self, token: int, value: str) -> None:
        if token < self.seen:
            raise StaleFencingToken(token)
        self.seen = token
        self.value = value

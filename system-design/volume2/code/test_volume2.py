"""Run from this directory: python test_volume2.py"""

from __future__ import annotations

import threading

from clocks import FencedStore, LamportClock, LeaseLock, VectorClock, concurrent, happened_before
from codec import decode, encode
from elevator import Elevator
from ledger import GroupLedger, Unbalanced
from logger import ListAppender, Logger
from lru import LruCache
from parking import Full, HourlyFee, ParkingLot, Row, Spot, Vehicle
from raft_model import Cluster, Entry, RaftNode
from rate_limiter import RateLimiter, TokenBucket
from storage import LsmTree, Mvcc, PageStore
from tickets import BadState, Show, Unavailable
from tinylink import (
    ClickQueue,
    Conflict,
    CreateCommand,
    Expired,
    IdSource,
    LinkService,
    MemoryCache,
    MemoryRepo,
    NotFound,
    shard_for,
)


def test_lru() -> None:
    cache = LruCache(2)
    cache.put("a", 1)
    cache.put("b", 2)
    assert cache.get("a") == 1
    cache.put("c", 3)
    assert cache.get("b") is None
    assert cache.get("a") == 1
    cache.put("a", 9)
    cache.put("d", 4)
    assert cache.get("c") is None
    assert cache.get("a") == 9
    assert len(cache) == 2


def test_rate_limiter() -> None:
    bucket = TokenBucket(capacity=2, refill_per_second=1, now=0)
    assert bucket.allow(0)
    assert bucket.allow(0)
    assert not bucket.allow(0)
    assert bucket.allow(1.0)
    limiter = RateLimiter(1, 0)
    assert limiter.allow("priya", 0)
    assert not limiter.allow("priya", 0)
    assert limiter.allow("arun", 0)


def test_codec_and_tinylink() -> None:
    assert decode(encode(0)) == 0
    assert decode(encode(3844)) == 3844
    service = LinkService(MemoryRepo(), MemoryCache(), IdSource(), ClickQueue())
    link = service.create(CreateCommand("https://example.com/a", "tok-1"), now=10)
    again = service.create(CreateCommand("https://example.com/a", "tok-1"), now=11)
    assert again.code == link.code
    assert service.open(link.code, now=12) == "https://example.com/a"
    try:
        service.create(CreateCommand("https://example.com/b", "tok-2", custom_code=link.code), now=13)
        raise AssertionError("expected conflict")
    except Conflict:
        pass
    try:
        service.create(CreateCommand("notaurl", "tok-3"), now=13)
        raise AssertionError("expected bad url")
    except ValueError:
        pass
    short = service.create(
        CreateCommand("https://example.com/c", "tok-4", expires_at=20),
        now=14,
    )
    service.cache.fail = True
    assert service.open(short.code, now=15) == "https://example.com/c"
    try:
        service.open(short.code, now=20)
        raise AssertionError("expected expired")
    except Expired:
        pass
    try:
        service.open("missing", now=15)
        raise AssertionError("expected missing")
    except NotFound:
        pass
    assert shard_for(link.code, 4) == link.id % 4


def test_parking() -> None:
    spots = [Spot(f"s{i}", "C") for i in range(6)] + [Spot("m0", "M")]
    lot = ParkingLot([Row(spots)], HourlyFee(10))
    bus = lot.park(Vehicle("BUS1", "bus"), now=0)
    assert len(bus.spot_ids) == 5
    bike = lot.park(Vehicle("BIKE", "motorcycle"), now=0)
    assert bike.spot_ids == ["m0"]
    try:
        lot.park(Vehicle("BUS2", "bus"), now=0)
        raise AssertionError("expected full")
    except Full:
        pass
    assert lot.leave(bus.ticket_id, now=3601) == 20
    assert lot.leave(bus.ticket_id, now=99999) == 20
    car = lot.park(Vehicle("CAR", "car"), now=10)
    assert car.spot_ids[0].startswith("s")


def test_tickets() -> None:
    show = Show(["A1", "A2"])
    booking = show.hold(["A1"], "priya", now=0)
    try:
        show.hold(["A1"], "arun", now=1)
        raise AssertionError("expected unavailable")
    except Unavailable:
        pass
    show.confirm(booking.booking_id, now=10)
    assert show.confirm(booking.booking_id, now=11).state == "CONFIRMED"
    held = show.hold(["A2"], "arun", now=0, ttl=5)
    assert show.expire(now=5) == 1
    try:
        show.confirm(held.booking_id, now=6)
        raise AssertionError("expected bad state")
    except BadState:
        pass

    race = Show(["Z"])
    wins: list[str] = []

    def grab(user: str) -> None:
        try:
            wins.append(race.hold(["Z"], user, now=0).user_id)
        except Unavailable:
            pass

    threads = [threading.Thread(target=grab, args=(name,)) for name in ("priya", "arun")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert wins == ["priya"] or wins == ["arun"]
    assert len(wins) == 1


def test_elevator() -> None:
    car = Elevator()
    car.call(3, "UP")
    for _ in range(3):
        car.step()
    assert car.floor == 3
    car.step()
    assert car.doors_open
    assert car.direction == "IDLE"

    car = Elevator()
    car.choose(5)
    car.step()
    car.step()
    car.call(1, "DOWN")
    while car.floor != 5:
        car.step()
    car.step()
    assert car.doors_open and car.floor == 5
    while not (car.floor == 1 and car.doors_open):
        car.step()
    assert car.floor == 1


def test_logger() -> None:
    first = ListAppender()
    second = ListAppender()
    second.fail = True
    log = Logger("api", "INFO", [first, second])
    log.log("DEBUG", "hidden")
    log.log("ERROR", "disk", code="aZ")
    assert len(first.events) == 1
    assert first.events[0].context["code"] == "aZ"
    assert log.dropped_errors == 1


def test_ledger() -> None:
    group = GroupLedger()
    group.add_expense("anu", {"anu": 50, "ben": 50})
    assert group.nets() == {"anu": 50, "ben": -50}
    assert group.simplified() == [("ben", "anu", 50)]
    group.settle("ben", "anu", 50)
    assert group.nets() == {}
    try:
        group.add_expense("anu", {"anu": -1})
        raise AssertionError("expected unbalanced")
    except Unbalanced:
        pass


def test_raft() -> None:
    cluster = Cluster(["a", "b", "c"])
    assert cluster.elect("a")
    assert cluster.nodes["a"].role == "leader"
    assert cluster.propose("a", "seat-1") == 0
    for node in cluster.nodes.values():
        assert [entry.command for entry in node.log] == ["seat-1"]
        assert node.commit_index == 0

    blocked = Cluster(["a", "b", "c"])
    assert not blocked.elect("a", voters=["a"])
    assert blocked.nodes["a"].role != "leader"

    fresh = RaftNode("b")
    fresh.current_term = 1
    fresh.log = [Entry(1, "newer")]
    term, granted = fresh.request_vote(2, "a", last_log_index=-1, last_log_term=0)
    assert term == 2 and not granted


def test_storage_and_clocks() -> None:
    store = PageStore()
    store.put("k", "v1")
    store.crash_after_log("k", "v2")
    assert store.pages["k"] == "v1"
    store.recover()
    assert store.pages["k"] == "v2"

    tree = LsmTree()
    tree.put("k", "old")
    tree.flush()
    tree.put("k", "new")
    assert tree.get("k") == "new"
    tree.delete("k")
    tree.flush()
    assert tree.get("k") is None
    tree.compact()
    assert tree.get("k") is None
    assert all(value is not None for run in tree.runs for value in run.values())

    db = Mvcc()
    t1, snap1 = db.begin()
    db.write(t1, "a", "one")
    t_early, snap_early = db.begin()
    db.commit(t1)
    t2, snap2 = db.begin()
    assert db.read(t_early, snap_early, "a") is None
    assert db.read(t2, snap2, "a") == "one"
    assert db.read(t1, snap1, "a") == "one"

    lamport = LamportClock()
    assert lamport.tick() == 1
    assert lamport.receive(5) == 6

    nodes = ["a", "b"]
    va = VectorClock("a", nodes)
    vb = VectorClock("b", nodes)
    first = va.tick()
    second = vb.receive(first)
    assert happened_before(first, second)
    side = vb.tick()
    other = va.tick()
    assert concurrent(side, other)

    lock = LeaseLock()
    store_fence = FencedStore()
    first_token = lock.acquire("old", now=0, ttl=5)
    assert lock.acquire("new", now=1, ttl=5) is None
    second_token = lock.acquire("new", now=5, ttl=5)
    assert first_token is not None and second_token is not None
    store_fence.write(second_token, "fresh")
    try:
        store_fence.write(first_token, "late")
        raise AssertionError("expected stale token")
    except Exception as exc:
        assert exc.__class__.__name__ == "StaleFencingToken"
    assert store_fence.value == "fresh"


if __name__ == "__main__":
    test_lru()
    test_rate_limiter()
    test_codec_and_tinylink()
    test_parking()
    test_tickets()
    test_elevator()
    test_logger()
    test_ledger()
    test_raft()
    test_storage_and_clocks()
    print("all tests passed")

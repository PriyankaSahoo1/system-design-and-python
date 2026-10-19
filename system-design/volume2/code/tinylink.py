"""TinyLink rules, with an in-memory notebook that enforces unique keys."""

from __future__ import annotations

from dataclasses import dataclass

from codec import decode, encode


class Conflict(Exception):
    pass


class NotFound(Exception):
    pass


class Expired(Exception):
    pass


@dataclass
class Link:
    id: int
    code: str
    long_url: str
    created_at: float
    expires_at: float | None
    click_count: int
    request_token: str | None


@dataclass
class CreateCommand:
    long_url: str
    request_token: str
    custom_code: str | None = None
    expires_at: float | None = None


class MemoryRepo:
    def __init__(self) -> None:
        self.by_code: dict[str, Link] = {}
        self.by_token: dict[str, Link] = {}

    def find_by_code(self, code: str) -> Link | None:
        return self.by_code.get(code)

    def find_by_token(self, token: str) -> Link | None:
        return self.by_token.get(token)

    def insert(self, link: Link) -> None:
        if link.code in self.by_code:
            raise Conflict(link.code)
        if link.request_token and link.request_token in self.by_token:
            raise Conflict(link.request_token)
        self.by_code[link.code] = link
        if link.request_token:
            self.by_token[link.request_token] = link


class MemoryCache:
    def __init__(self) -> None:
        self.store: dict[str, Link] = {}
        self.fail = False

    def get(self, code: str) -> Link | None:
        if self.fail:
            raise RuntimeError("cache down")
        return self.store.get(code)

    def put(self, code: str, link: Link) -> None:
        if self.fail:
            return
        self.store[code] = link


class IdSource:
    def __init__(self, start: int = 1) -> None:
        self._next = start

    def next_id(self) -> int:
        value = self._next
        self._next += 1
        return value


class ClickQueue:
    def __init__(self) -> None:
        self.events: list[str] = []

    def publish(self, code: str) -> None:
        self.events.append(code)


def valid_url(url: str) -> bool:
    if len(url) > 2048:
        return False
    return url.startswith("http://") or url.startswith("https://")


class LinkService:
    def __init__(self, repo: MemoryRepo, cache: MemoryCache, ids: IdSource, clicks: ClickQueue) -> None:
        self.repo = repo
        self.cache = cache
        self.ids = ids
        self.clicks = clicks

    def create(self, command: CreateCommand, now: float) -> Link:
        if not valid_url(command.long_url):
            raise ValueError("invalid url")
        existing = self.repo.find_by_token(command.request_token)
        if existing is not None:
            return existing
        if command.custom_code:
            code = command.custom_code
            link_id = self.ids.next_id()
        else:
            link_id = self.ids.next_id()
            code = encode(link_id)
        link = Link(
            id=link_id,
            code=code,
            long_url=command.long_url,
            created_at=now,
            expires_at=command.expires_at,
            click_count=0,
            request_token=command.request_token,
        )
        try:
            self.repo.insert(link)
        except Conflict:
            if command.custom_code:
                raise
            raise
        self.cache.put(code, link)
        return link

    def open(self, code: str, now: float) -> str:
        link = None
        try:
            link = self.cache.get(code)
        except RuntimeError:
            link = None
        if link is None:
            link = self.repo.find_by_code(code)
            if link is not None:
                try:
                    self.cache.put(code, link)
                except RuntimeError:
                    pass
        if link is None:
            raise NotFound(code)
        if link.expires_at is not None and link.expires_at <= now:
            raise Expired(code)
        self.clicks.publish(code)
        return link.long_url


def apply_click(repo: MemoryRepo, code: str) -> None:
    """Worker. Adding 1 on the stored row is safe to repeat only if the event id is new.

    This helper is the approximate-counter version: each delivery adds one.
    Callers that need exactly-once must dedupe event ids before calling it.
    """
    link = repo.find_by_code(code)
    if link is None:
        return
    link.click_count += 1


def shard_for(code: str, shard_count: int) -> int:
    """Range-style home: decode the code back to the id, then mod."""
    return decode(code) % shard_count

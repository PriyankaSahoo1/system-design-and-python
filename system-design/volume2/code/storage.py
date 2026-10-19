"""Small working models of a write-ahead log, an LSM tree, and MVCC."""

from __future__ import annotations


class PageStore:
    """Log the change, then touch the page. Recovery replays anything not applied."""

    def __init__(self) -> None:
        self.pages: dict[str, str] = {}
        self.wal: list[tuple[str, str]] = []
        self.applied = 0

    def put(self, key: str, value: str) -> None:
        self.wal.append((key, value))
        self._apply_next()

    def crash_after_log(self, key: str, value: str) -> None:
        """The log has the write. The page does not. This is a crash window."""
        self.wal.append((key, value))

    def recover(self) -> None:
        while self.applied < len(self.wal):
            self._apply_next()

    def _apply_next(self) -> None:
        key, value = self.wal[self.applied]
        self.pages[key] = value
        self.applied += 1


class LsmTree:
    """Writes land in memory. Flushes become sorted runs. Reads start at the newest run."""

    def __init__(self) -> None:
        self.mem: dict[str, str | None] = {}
        self.runs: list[dict[str, str | None]] = []

    def put(self, key: str, value: str) -> None:
        self.mem[key] = value

    def delete(self, key: str) -> None:
        self.mem[key] = None

    def flush(self) -> None:
        if not self.mem:
            return
        self.runs.append(self.mem)
        self.mem = {}

    def get(self, key: str) -> str | None:
        if key in self.mem:
            return self.mem[key]
        for run in reversed(self.runs):
            if key in run:
                return run[key]
        return None

    def compact(self) -> None:
        merged: dict[str, str | None] = {}
        for run in self.runs:
            merged.update(run)
        merged.update(self.mem)
        self.runs = [{key: value for key, value in merged.items() if value is not None}]
        self.mem = {}


class Mvcc:
    """Readers see a snapshot. Writers add a new version. They do not block each other."""

    def __init__(self) -> None:
        self._next = 1
        self.committed: set[int] = set()
        self.versions: dict[str, list[tuple[int, int | None, str | None]]] = {}

    def begin(self) -> tuple[int, frozenset[int]]:
        txn = self._next
        self._next += 1
        return txn, frozenset(self.committed)

    def commit(self, txn: int) -> None:
        self.committed.add(txn)

    def write(self, txn: int, key: str, value: str | None) -> None:
        chain = self.versions.setdefault(key, [])
        for index, (xmin, xmax, _) in enumerate(chain):
            if xmax is None and self._visible_creator(xmin, txn, frozenset(self.committed)):
                chain[index] = (xmin, txn, chain[index][2])
        chain.append((txn, None, value))

    def read(self, txn: int, snapshot: frozenset[int], key: str) -> str | None:
        for xmin, xmax, value in reversed(self.versions.get(key, [])):
            if self._visible(xmin, xmax, txn, snapshot):
                return value
        return None

    def _visible(self, xmin: int, xmax: int | None, txn: int, snapshot: frozenset[int]) -> bool:
        created = self._visible_creator(xmin, txn, snapshot)
        deleted = xmax is not None and (xmax == txn or xmax in snapshot)
        return created and not deleted

    def _visible_creator(self, xmin: int, txn: int, snapshot: frozenset[int]) -> bool:
        return xmin == txn or xmin in snapshot

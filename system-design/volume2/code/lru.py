"""Least-recently-used cache. get and put are O(1)."""

from __future__ import annotations


class _Node:
    def __init__(self, key: object, value: object) -> None:
        self.key = key
        self.value = value
        self.prev: _Node | None = None
        self.next: _Node | None = None


class LruCache:
    def __init__(self, capacity: int) -> None:
        if capacity < 1:
            raise ValueError("capacity must be at least 1")
        self.capacity = capacity
        self._map: dict[object, _Node] = {}
        self._head = _Node(None, None)
        self._tail = _Node(None, None)
        self._head.next = self._tail
        self._tail.prev = self._head

    def __len__(self) -> int:
        return len(self._map)

    def get(self, key: object) -> object:
        node = self._map.get(key)
        if node is None:
            return None
        self._move_to_front(node)
        return node.value

    def put(self, key: object, value: object) -> None:
        node = self._map.get(key)
        if node is not None:
            node.value = value
            self._move_to_front(node)
            return
        node = _Node(key, value)
        self._map[key] = node
        self._insert_front(node)
        if len(self._map) > self.capacity:
            evicted = self._tail.prev
            assert evicted is not None and evicted is not self._head
            self._unlink(evicted)
            del self._map[evicted.key]

    def _insert_front(self, node: _Node) -> None:
        nxt = self._head.next
        assert nxt is not None
        node.prev = self._head
        node.next = nxt
        self._head.next = node
        nxt.prev = node

    def _unlink(self, node: _Node) -> None:
        assert node.prev is not None and node.next is not None
        node.prev.next = node.next
        node.next.prev = node.prev
        node.prev = None
        node.next = None

    def _move_to_front(self, node: _Node) -> None:
        self._unlink(node)
        self._insert_front(node)

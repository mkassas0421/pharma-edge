"""Bounded FIFO-set for URL / accession-number deduplication."""
from collections import OrderedDict


class BoundedSet:
    """A set-like container with a maximum size (FIFO eviction)."""

    def __init__(self, maxsize: int = 2000):
        self._maxsize = maxsize
        self._store: OrderedDict[str, None] = OrderedDict()

    def add(self, item: str) -> None:
        if item not in self._store:
            self._store[item] = None
        while len(self._store) > self._maxsize:
            self._store.popitem(last=False)

    def __contains__(self, item: str) -> bool:
        return item in self._store

    def __len__(self) -> int:
        return len(self._store)

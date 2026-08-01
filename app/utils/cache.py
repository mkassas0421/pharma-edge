"""Lightweight in-memory TTL cache for dashboard responses.

The app runs as a single process on Render, so a module-level dict is
sufficient — no Redis needed. Entries expire after a fixed TTL; writers
invalidate explicitly when the underlying data changes (ticker/event
CRUD, price refresh, event pruning).
"""

import threading
import time
from typing import Any


class TTLCache:
    """Dict-like cache where entries expire after ``ttl_seconds``."""

    def __init__(self, ttl_seconds: float = 60):
        self._ttl = ttl_seconds
        self._store: dict[str, tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Any | None:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            expiry, value = entry
            if time.time() > expiry:
                del self._store[key]
                return None
            return value

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._store[key] = (time.time() + self._ttl, value)

    def invalidate_all(self) -> None:
        with self._lock:
            self._store.clear()


# Dashboard: prices refresh every 5 minutes, so 60 s keeps it fresh enough
# while collapsing load during the auto-refresh cycles.
dashboard_cache = TTLCache(ttl_seconds=60)
stats_cache = TTLCache(ttl_seconds=120)

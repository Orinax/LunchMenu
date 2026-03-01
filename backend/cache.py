"""Simple in-memory TTL cache."""
import time
from typing import Any, Optional


class TTLCache:
    def __init__(self, ttl_seconds: int = 21600):
        self._ttl = ttl_seconds
        self._data: Optional[Any] = None
        self._timestamp: float = 0.0

    def get(self) -> Optional[Any]:
        if self._data is not None and (time.time() - self._timestamp) < self._ttl:
            return self._data
        return None

    def set(self, value: Any) -> None:
        self._data = value
        self._timestamp = time.time()

    def invalidate(self) -> None:
        self._data = None
        self._timestamp = 0.0

    @property
    def last_fetched(self) -> Optional[float]:
        return self._timestamp if self._data is not None else None

import time
from typing import Optional, Any
from dataclasses import dataclass


@dataclass
class CacheEntry:
    data: Any
    expires_at: float


class UserCache:
    _instance: Optional["UserCache"] = None

    def __new__(cls) -> "UserCache":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._store: dict[int, CacheEntry] = {}
        return cls._instance

    def get(self, user_id: int) -> Optional[Any]:
        entry = self._store.get(user_id)
        if entry is None:
            return None
        if time.time() > entry.expires_at:
            del self._store[user_id]
            return None
        return entry.data

    def set(self, user_id: int, data: Any, ttl: int = 300) -> None:
        self._store[user_id] = CacheEntry(data=data, expires_at=time.time() + ttl)

    def invalidate(self, user_id: int) -> None:
        self._store.pop(user_id, None)

    def clear(self) -> None:
        self._store.clear()

"""Redis access with graceful degradation.

Redis is an accelerator, never the source of truth. If Redis is not
configured or unreachable, every operation falls back to a process-local
in-memory implementation and the app keeps working (with per-process
rate limits / locks instead of distributed ones).
"""

from __future__ import annotations

import json
import logging
import threading
import time
from contextlib import contextmanager
from typing import Any, Iterator

from app.core.config import get_settings
from app.core.logging import log_event

log = logging.getLogger(__name__)


class _MemoryStore:
    def __init__(self) -> None:
        self._data: dict[str, tuple[Any, float | None]] = {}
        self._lock = threading.Lock()

    def _alive(self, key: str) -> bool:
        item = self._data.get(key)
        if item is None:
            return False
        if item[1] is not None and item[1] < time.monotonic():
            self._data.pop(key, None)
            return False
        return True

    def get(self, key: str) -> Any:
        with self._lock:
            return self._data[key][0] if self._alive(key) else None

    def set(self, key: str, value: Any, ttl: int | None = None, nx: bool = False) -> bool:
        with self._lock:
            if nx and self._alive(key):
                return False
            self._data[key] = (value, time.monotonic() + ttl if ttl else None)
            return True

    def incr(self, key: str, ttl: int) -> int:
        with self._lock:
            if not self._alive(key):
                self._data[key] = (0, time.monotonic() + ttl)
            value, exp = self._data[key]
            self._data[key] = (value + 1, exp)
            return value + 1

    def delete(self, key: str) -> None:
        with self._lock:
            self._data.pop(key, None)


class Cache:
    def __init__(self, url: str | None) -> None:
        self._memory = _MemoryStore()
        self._redis = None
        self._url = url
        self._last_error_at = 0.0
        if url:
            try:
                import redis

                self._redis = redis.Redis.from_url(url, socket_timeout=0.5, socket_connect_timeout=0.5)
            except Exception as exc:  # pragma: no cover
                log_event("redis.init_failed", logging.WARNING, error=str(exc))

    @property
    def configured(self) -> bool:
        return self._redis is not None

    def _client(self):
        # Back off for 30s after a failure so a dead Redis doesn't add latency to every call.
        if self._redis is None or time.monotonic() - self._last_error_at < 30:
            return None
        return self._redis

    def _failed(self, exc: Exception) -> None:
        self._last_error_at = time.monotonic()
        log_event("redis.unavailable", logging.WARNING, error=str(exc))

    def ping(self) -> tuple[bool, str]:
        if self._redis is None:
            return False, "Not configured; using in-process fallback"
        try:
            self._redis.ping()
            return True, "Connected"
        except Exception as exc:
            self._failed(exc)
            return False, f"Unreachable ({type(exc).__name__}); using in-process fallback"

    def get_json(self, key: str) -> Any:
        client = self._client()
        if client is not None:
            try:
                raw = client.get(key)
                return json.loads(raw) if raw else None
            except Exception as exc:
                self._failed(exc)
        return self._memory.get(key)

    def set_json(self, key: str, value: Any, ttl: int) -> None:
        client = self._client()
        if client is not None:
            try:
                client.set(key, json.dumps(value, default=str), ex=ttl)
                return
            except Exception as exc:
                self._failed(exc)
        self._memory.set(key, value, ttl)

    def incr(self, key: str, ttl: int) -> int:
        client = self._client()
        if client is not None:
            try:
                pipe = client.pipeline()
                pipe.incr(key)
                pipe.expire(key, ttl, nx=True)
                return int(pipe.execute()[0])
            except Exception as exc:
                self._failed(exc)
        return self._memory.incr(key, ttl)

    @contextmanager
    def lock(self, name: str, ttl: int = 60) -> Iterator[bool]:
        """Non-blocking distributed lock. Yields True if acquired."""
        key = f"lock:{name}"
        token = str(time.time_ns())
        acquired = False
        client = self._client()
        used_redis = False
        if client is not None:
            try:
                acquired = bool(client.set(key, token, nx=True, ex=ttl))
                used_redis = True
            except Exception as exc:
                self._failed(exc)
        if not used_redis:
            acquired = self._memory.set(key, token, ttl, nx=True)
        try:
            yield acquired
        finally:
            if acquired:
                if used_redis:
                    try:
                        if (client.get(key) or b"").decode() == token:
                            client.delete(key)
                    except Exception:
                        pass
                else:
                    self._memory.delete(key)


_cache: Cache | None = None


def get_cache() -> Cache:
    global _cache
    if _cache is None:
        _cache = Cache(get_settings().redis_url)
    return _cache

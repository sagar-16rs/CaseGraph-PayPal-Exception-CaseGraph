from __future__ import annotations

import asyncio
import hashlib
import time
from dataclasses import dataclass
from typing import Protocol


class RateLimiter(Protocol):
    async def allow(self, key: str, limit: int, window_seconds: int = 60) -> bool: ...


@dataclass
class _Bucket:
    count: int
    expires_at: float


class MemoryRateLimiter:
    def __init__(self):
        self._buckets: dict[str, _Bucket] = {}
        self._lock = asyncio.Lock()

    async def allow(self, key: str, limit: int, window_seconds: int = 60) -> bool:
        now = time.monotonic()
        async with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None or bucket.expires_at <= now:
                bucket = _Bucket(count=0, expires_at=now + window_seconds)
                self._buckets[key] = bucket
            bucket.count += 1
            return bucket.count <= limit


class RedisRateLimiter:
    _SCRIPT = """
local n = redis.call('INCR', KEYS[1])
if n == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end
return n
"""

    def __init__(self, url: str):
        try:
            import redis.asyncio as redis
        except ImportError as exc:  # pragma: no cover - environment gate
            raise RuntimeError("redis package is required for production rate limiting") from exc
        self._redis = redis.from_url(url, encoding="utf-8", decode_responses=True)

    async def allow(self, key: str, limit: int, window_seconds: int = 60) -> bool:
        safe_key = "casegraph:rl:" + hashlib.sha256(key.encode("utf-8")).hexdigest()
        count = int(await self._redis.eval(self._SCRIPT, 1, safe_key, window_seconds))
        return count <= limit

    async def ping(self) -> bool:
        return bool(await self._redis.ping())

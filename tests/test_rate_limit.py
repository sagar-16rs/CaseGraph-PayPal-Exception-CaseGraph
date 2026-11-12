from __future__ import annotations

import asyncio

from backend.security.rate_limit import MemoryRateLimiter


def test_memory_rate_limiter_enforces_limit():
    async def run():
        limiter = MemoryRateLimiter()
        assert await limiter.allow("x", 2)
        assert await limiter.allow("x", 2)
        assert not await limiter.allow("x", 2)
    asyncio.run(run())

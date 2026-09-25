"""Sliding-window rate limiting on Redis, without blocking the event loop.

Each check is one EVALSHA of an atomic Lua script (prune, count, add), so
concurrent requests across API replicas can't all slip under the same limit.
"""

import logging
import time
import uuid
from dataclasses import dataclass
from typing import Optional

import redis.asyncio as aioredis

from app.core.config import settings

logger = logging.getLogger(__name__)

_SLIDING_WINDOW = """
local key, now, window, limit, member =
    KEYS[1], tonumber(ARGV[1]), tonumber(ARGV[2]), tonumber(ARGV[3]), ARGV[4]
redis.call('ZREMRANGEBYSCORE', key, 0, now - window)
local current = redis.call('ZCARD', key)
if current < limit then
    redis.call('ZADD', key, now, member)
    redis.call('PEXPIRE', key, window)
    return {1, limit - current - 1, window}
end
local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
local retry = window
if oldest[2] then retry = math.max(0, oldest[2] + window - now) end
return {0, 0, retry}
"""

_UNITS = {"s": 1, "m": 60, "h": 3600}


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    remaining: int
    retry_after_seconds: int


def parse_limit(limit: str) -> tuple[int, int]:
    """"5/15m" -> (5, 900). A bare number of seconds is also accepted."""
    count, period = limit.split("/")
    unit = period[-1]
    seconds = int(period[:-1]) * _UNITS[unit] if unit in _UNITS else int(period)
    return int(count), seconds


class RateLimiter:
    def __init__(self, client: Optional[aioredis.Redis] = None):
        self._client = client
        self._script = None

    def _get_script(self):
        if self._script is None:
            if self._client is None:
                self._client = aioredis.from_url(
                    settings.get_redis_url(), socket_connect_timeout=2, socket_timeout=2
                )
            self._script = self._client.register_script(_SLIDING_WINDOW)
        return self._script

    async def check(self, key: str, limit: str) -> RateLimitResult:
        count, period_seconds = parse_limit(limit)
        now_ms = int(time.time() * 1000)
        try:
            allowed, remaining, reset_ms = await self._get_script()(
                keys=[key],
                args=[now_ms, period_seconds * 1000, count, f"{now_ms}:{uuid.uuid4()}"],
            )
        except Exception as e:
            logger.warning("Rate limit check failed for %s: %s", key, e)
            return self._when_unavailable(key)
        return RateLimitResult(bool(allowed), int(remaining), max(0, (int(reset_ms) + 999) // 1000))

    @staticmethod
    def _when_unavailable(key: str) -> RateLimitResult:
        # Credential endpoints fail closed in production (no unthrottled password
        # guessing during a Redis outage); everything else stays available.
        if settings.ENVIRONMENT == "production" and key.startswith("rate_limit:auth:"):
            return RateLimitResult(False, 0, 5)
        return RateLimitResult(True, 0, 0)


rate_limiter = RateLimiter()

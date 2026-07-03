"""Lightweight per-client sliding-window rate limiter.

Single-instance by design: state lives in process memory, resets on
restart, and is not shared across replicas. That is the documented
limitation and it is appropriate for a personal single-instance
deployment — introducing shared infrastructure for this would be
over-engineering. Local mode does not rate-limit at all by default;
public-demo enables it (see config.py).
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from threading import Lock

from fastapi import Request

from .config import Settings
from .errors import RateLimitedError

_WINDOW_SECONDS = 60.0


class RateLimiter:
    def __init__(self) -> None:
        self._buckets: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def check(self, key: str, limit: int) -> None:
        now = time.monotonic()
        with self._lock:
            bucket = self._buckets[key]
            while bucket and bucket[0] <= now - _WINDOW_SECONDS:
                bucket.popleft()
            if len(bucket) >= limit:
                raise RateLimitedError(
                    f"rate limit exceeded: {limit} requests per "
                    f"{int(_WINDOW_SECONDS)}s window"
                )
            bucket.append(now)


def enforce_rate_limit(request: Request, settings: Settings) -> None:
    limit = settings.rate_limit_per_minute
    if limit is None:
        return
    client = request.client.host if request.client else "unknown"
    limiter: RateLimiter = request.app.state.rate_limiter
    limiter.check(client, limit)

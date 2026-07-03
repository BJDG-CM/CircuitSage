"""Per-client sliding-window rate limiter backed by SQLite.

State lives in the same SQLite file as share links (CIRCUITSAGE_DB), so
the window **survives process restarts** — restarting the demo no longer
resets every bucket. It remains single-instance by design: the database
file is per deployment and is not shared across replicas; that is the
documented limitation and appropriate for a personal single-instance
deployment. Local mode does not rate-limit at all by default;
public-demo enables it (see config.py).

If the database is unavailable the limiter fails open (the request is
allowed and a warning is logged): for a personal demo, availability
beats strictness.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import time
from pathlib import Path

from fastapi import Request

from .config import Settings
from .errors import RateLimitedError

logger = logging.getLogger("circuitsage")

_WINDOW_SECONDS = 60.0


def _db_path() -> Path:
    return Path(os.environ.get("CIRCUITSAGE_DB", "circuitsage.db"))


class RateLimiter:
    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(_db_path())
        connection.execute(
            "CREATE TABLE IF NOT EXISTS rate_events ("
            " client TEXT NOT NULL,"
            " ts REAL NOT NULL)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_rate_events_client_ts"
            " ON rate_events (client, ts)"
        )
        return connection

    def check(self, key: str, limit: int) -> None:
        now = time.time()
        try:
            connection = self._connect()
        except sqlite3.Error:
            logger.warning("rate limiter database unavailable; failing open")
            return
        try:
            with connection:
                connection.execute(
                    "DELETE FROM rate_events WHERE ts < ?", (now - _WINDOW_SECONDS,)
                )
                (count,) = connection.execute(
                    "SELECT COUNT(*) FROM rate_events WHERE client = ?", (key,)
                ).fetchone()
                if count >= limit:
                    raise RateLimitedError(
                        f"rate limit exceeded: {limit} requests per "
                        f"{int(_WINDOW_SECONDS)}s window"
                    )
                connection.execute(
                    "INSERT INTO rate_events (client, ts) VALUES (?, ?)", (key, now)
                )
        except sqlite3.Error:
            logger.warning("rate limiter query failed; failing open")
        finally:
            connection.close()


def enforce_rate_limit(request: Request, settings: Settings) -> None:
    limit = settings.rate_limit_per_minute
    if limit is None:
        return
    client = request.client.host if request.client else "unknown"
    limiter: RateLimiter = request.app.state.rate_limiter
    limiter.check(client, limit)

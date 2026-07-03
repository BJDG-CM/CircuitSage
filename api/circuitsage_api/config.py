"""Operating profiles and configurable limits.

CircuitSage is local-first. Two profiles exist:

* ``local`` (default) — generous limits, everything configurable, the
  solve timeout may be disabled entirely with ``0`` for trusted use.
* ``public-demo`` — strict limits for a shared single-instance demo:
  the solve timeout is mandatory (clamped to [1, 120] s) and rate
  limiting is on by default.

Every limit can be overridden by an environment variable. A limit set to
``0`` means *disabled* (allowed in local mode only for the timeout).
"""

from __future__ import annotations

import os
from dataclasses import dataclass

MODE_LOCAL = "local"
MODE_PUBLIC_DEMO = "public-demo"


@dataclass(frozen=True)
class Limits:
    max_netlist_bytes: int | None
    max_components: int | None
    max_mna_dimension: int | None
    max_symbols: int | None


@dataclass(frozen=True)
class Settings:
    mode: str
    limits: Limits
    solve_timeout: float  # seconds; 0 = disabled (local mode only)
    rate_limit_per_minute: int | None  # None = no rate limiting
    share_max_bytes: int
    share_ttl_seconds: int | None  # None = no expiration
    share_max_rows: int | None  # None = unbounded


def _int_env(name: str, default: int | None) -> int | None:
    """Read an integer limit; explicit 0 disables it (returns None)."""
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    value = int(raw)
    return None if value <= 0 else value


def _float_env(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return float(raw)


def get_settings() -> Settings:
    mode = os.environ.get("CIRCUITSAGE_MODE", MODE_LOCAL).strip().lower()
    demo = mode == MODE_PUBLIC_DEMO

    limits = Limits(
        max_netlist_bytes=_int_env(
            "CIRCUITSAGE_MAX_NETLIST_BYTES", 10_000 if demo else 200_000
        ),
        max_components=_int_env("CIRCUITSAGE_MAX_COMPONENTS", 12 if demo else 15),
        max_mna_dimension=_int_env("CIRCUITSAGE_MAX_MNA_DIMENSION", 24 if demo else 40),
        max_symbols=_int_env("CIRCUITSAGE_MAX_SYMBOLS", 6 if demo else 16),
    )

    timeout = _float_env("CIRCUITSAGE_SOLVE_TIMEOUT_SECONDS", 30.0)
    if demo:
        # public demo: the timeout is mandatory and bounded
        timeout = min(max(timeout, 1.0), 120.0) if timeout > 0 else 30.0
    else:
        timeout = max(timeout, 0.0)

    rate_default = 20 if demo else None
    rate_raw = _int_env("CIRCUITSAGE_RATE_LIMIT_PER_MINUTE", rate_default)

    return Settings(
        mode=MODE_PUBLIC_DEMO if demo else MODE_LOCAL,
        limits=limits,
        solve_timeout=timeout,
        rate_limit_per_minute=rate_raw,
        share_max_bytes=_int_env(
            "CIRCUITSAGE_SHARE_MAX_BYTES", 20_000 if demo else 200_000
        )
        or 200_000,
        share_ttl_seconds=_int_env(
            "CIRCUITSAGE_SHARE_TTL_SECONDS", 7 * 24 * 3600 if demo else None
        ),
        share_max_rows=_int_env("CIRCUITSAGE_SHARE_MAX_ROWS", 2000 if demo else None),
    )

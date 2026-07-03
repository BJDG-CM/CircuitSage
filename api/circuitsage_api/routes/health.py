"""GET /api/health — 런처·Docker HEALTHCHECK·모니터링용 경량 엔드포인트."""

from __future__ import annotations

from fastapi import APIRouter

from ..config import get_settings

router = APIRouter()


@router.get("/health")
def health() -> dict:
    from .. import __version__

    return {"status": "ok", "mode": get_settings().mode, "version": __version__}

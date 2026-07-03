"""FastAPI 앱 팩토리. 실행: uvicorn circuitsage_api.main:app --reload

바인딩: uvicorn 기본값(127.0.0.1)을 그대로 쓰는 것이 로컬 기본 자세다.
외부 노출은 public-demo 프로파일(CIRCUITSAGE_MODE=public-demo)과 함께
의도적으로 --host를 지정할 때만 한다.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import MODE_LOCAL, get_settings
from .errors import register_exception_handlers
from .ratelimit import RateLimiter
from .routes import examples, health, share, solve


def _cors_origins() -> list[str]:
    settings = get_settings()
    if settings.mode == MODE_LOCAL:
        # Vite dev 서버 (Phase 4). 배포에서는 SPA가 동일 출처로 서빙된다.
        return ["http://localhost:5173", "http://127.0.0.1:5173"]
    raw = os.environ.get("CIRCUITSAGE_CORS_ORIGINS", "")
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


def create_app() -> FastAPI:
    app = FastAPI(title="CircuitSage API", version="0.1.0")
    origins = _cors_origins()
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    register_exception_handlers(app)
    app.state.rate_limiter = RateLimiter()
    app.include_router(solve.router, prefix="/api")
    app.include_router(examples.router, prefix="/api")
    app.include_router(share.router, prefix="/api")
    app.include_router(health.router, prefix="/api")

    # Docker 배포에서는 빌드된 SPA를 같은 프로세스가 서빙한다 (라우터 뒤에
    # 마운트하므로 /api/*가 우선한다)
    static_dir = os.environ.get("CIRCUITSAGE_STATIC_DIR")
    if static_dir and Path(static_dir).is_dir():
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
    return app


app = create_app()

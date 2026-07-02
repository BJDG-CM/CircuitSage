"""FastAPI 앱 팩토리. 실행: uvicorn circuitsage_api.main:app --reload"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .errors import register_exception_handlers
from .routes import examples, share, solve


def create_app() -> FastAPI:
    app = FastAPI(title="CircuitSage API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],  # Vite dev server (Phase 4)
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_exception_handlers(app)
    app.include_router(solve.router, prefix="/api")
    app.include_router(examples.router, prefix="/api")
    app.include_router(share.router, prefix="/api")

    # Docker 배포에서는 빌드된 SPA를 같은 프로세스가 서빙한다 (라우터 뒤에
    # 마운트하므로 /api/*가 우선한다)
    static_dir = os.environ.get("CIRCUITSAGE_STATIC_DIR")
    if static_dir and Path(static_dir).is_dir():
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
    return app


app = create_app()

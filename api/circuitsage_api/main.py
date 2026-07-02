"""FastAPI 앱 팩토리. 실행: uvicorn circuitsage_api.main:app --reload"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .errors import register_exception_handlers
from .routes import examples, solve


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
    return app


app = create_app()

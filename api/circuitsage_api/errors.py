"""코어 예외 계층 → HTTP 응답 매핑 (design §5).

코어의 모든 예외가 안정적인 ``code``를 갖고 있으므로 메시지 파싱 없이
상태 코드를 정한다. line_no(파서 오류)와 measured/limit(복잡도 한도)은
프런트가 구체적으로 표시할 수 있도록 함께 내려보낸다.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from circuitsolver.errors import CircuitError

logger = logging.getLogger("circuitsage")

_STATUS_BY_CODE = {
    "PARSE_ERROR": 422,
    "FLOATING_NODE": 422,
    "TOPOLOGY_ERROR": 422,
    "SINGULAR_MATRIX": 422,
    "TOO_MANY_COMPONENTS": 422,
    "TOO_MANY_SYMBOLS": 422,
    "MATRIX_TOO_LARGE": 422,
    "NETLIST_TOO_LARGE": 413,
    "SHARE_TOO_LARGE": 413,
    "RATE_LIMITED": 429,
    "INVERSE_LAPLACE": 500,
    "WORKER_ERROR": 500,
    "VERIFY_ERROR": 502,
    "TIMEOUT": 504,
}


class ComplexityLimitError(CircuitError):
    """A measured complexity value exceeded its configured limit."""

    def __init__(self, code: str, message: str, measured: int, limit: int) -> None:
        super().__init__(message)
        self.code = code
        self.measured = measured
        self.limit = limit


class RateLimitedError(CircuitError):
    code = "RATE_LIMITED"


async def _circuit_error_handler(request: Request, exc: CircuitError) -> JSONResponse:
    payload: dict = {"code": exc.code, "message": str(exc)}
    line_no = getattr(exc, "line_no", None)
    if line_no is not None:
        payload["line_no"] = line_no
    measured = getattr(exc, "measured", None)
    if measured is not None:
        payload["measured"] = measured
        payload["limit"] = getattr(exc, "limit", None)
    status = _STATUS_BY_CODE.get(exc.code, 400)
    return JSONResponse(status_code=status, content={"error": payload})


async def _unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Never leak tracebacks to clients; log server-side instead."""
    logger.exception("unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"error": {"code": "INTERNAL_ERROR", "message": "internal server error"}},
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(CircuitError, _circuit_error_handler)
    app.add_exception_handler(Exception, _unexpected_error_handler)

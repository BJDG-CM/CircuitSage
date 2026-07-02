"""코어 예외 계층 → HTTP 응답 매핑 (design §5).

코어의 모든 예외가 안정적인 ``code``를 갖고 있으므로 메시지 파싱 없이
상태 코드를 정한다. ParseError는 웹 에디터의 라인 하이라이트를 위해
line_no를 함께 내려보낸다.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from circuitsolver.errors import CircuitError, ParseError

_STATUS_BY_CODE = {
    "PARSE_ERROR": 422,
    "FLOATING_NODE": 422,
    "TOPOLOGY_ERROR": 422,
    "SINGULAR_MATRIX": 422,
    "TOO_MANY_COMPONENTS": 422,
    "INVERSE_LAPLACE": 500,
    "VERIFY_ERROR": 502,
    "TIMEOUT": 504,
}


class TooManyComponentsError(CircuitError):
    """API-level guard (design §2.2): symbolic cost is superlinear."""

    code = "TOO_MANY_COMPONENTS"


async def _circuit_error_handler(request: Request, exc: CircuitError) -> JSONResponse:
    payload: dict = {"code": exc.code, "message": str(exc)}
    if isinstance(exc, ParseError):
        payload["line_no"] = exc.line_no
    status = _STATUS_BY_CODE.get(exc.code, 400)
    return JSONResponse(status_code=status, content={"error": payload})


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(CircuitError, _circuit_error_handler)

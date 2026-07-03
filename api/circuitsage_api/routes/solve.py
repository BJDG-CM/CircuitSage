"""POST /api/solve — 얇은 라우터.

빠른 preflight(바이트 한도 → 파싱 → 복잡도 한도)는 요청 프로세스에서
수행하고, 비싼 symbolic 파이프라인은 격리 워커 프로세스에서 실행한다
(isolation.py). CIRCUITSAGE_SOLVE_TIMEOUT_SECONDS=0이면 신뢰된 로컬
모드로 간주해 격리 없이 in-process로 실행한다.
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from circuitsolver import parse
from circuitsolver.complexity import measure_complexity

from ..config import get_settings
from ..guards import enforce_complexity, enforce_netlist_size
from ..isolation import run_isolated
from ..pipeline import run_solve
from ..ratelimit import enforce_rate_limit
from ..schemas import SolveRequest

router = APIRouter()


@router.post("/solve")
def solve(request: SolveRequest, http_request: Request) -> dict:
    settings = get_settings()

    enforce_rate_limit(http_request, settings)
    enforce_netlist_size(request.netlist, settings)
    circuit = parse(request.netlist)
    complexity = measure_complexity(circuit, request.netlist)
    enforce_complexity(complexity, settings)

    options = request.options.model_dump()
    if settings.solve_timeout <= 0:
        return run_solve(request.netlist, options)
    return run_isolated(request.netlist, options, settings.solve_timeout)

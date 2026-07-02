"""POST /api/solve — 전체 해석 파이프라인 (design §5).

파이프라인: parse → 소자 수 상한 → 위상 검증 → MNA(유도 기록 포함) →
H(s) → pole/zero → 안정성 → 시간응답(+수치 샘플) → Bode → (선택) ngspice
검증 → (선택) LaTeX 노트. 실패해도 성립하는 부분(기호 Bode 등)은 결과에서
빼고 warnings로 사유를 알린다.
"""

from __future__ import annotations

import os

import numpy as np
import sympy as sp
from fastapi import APIRouter

from circuitsolver import (
    assemble,
    bode_data,
    expand_initial_conditions,
    find_ngspice,
    impulse_response,
    parse,
    pole_zero,
    stability,
    step_response,
    transfer_function,
    validate_topology,
)
from circuitsolver.analysis import PoleZeroResult, RootSet
from circuitsolver.errors import CircuitError, InverseLaplaceError
from circuitsolver.laplace import t
from circuitsolver.mna import replay_checkpoints
from circuitsolver.report import generate_report, routh_array_latex
from circuitsolver.simplify import simplify_circuit
from circuitsolver.verify import verify_ac, verify_tran

from ..errors import TooManyComponentsError
from ..schemas import SolveRequest

router = APIRouter()

_SAMPLE_POINTS = 200


def _max_components() -> int:
    return int(os.environ.get("CIRCUITSAGE_MAX_COMPONENTS", "15"))


def _serialize_roots(roots: RootSet) -> dict:
    entries = []
    for root, multiplicity in roots.roots:
        entry: dict = {"latex": sp.latex(root), "multiplicity": multiplicity}
        try:
            value = complex(root)
            entry["re"], entry["im"] = value.real, value.imag
        except TypeError:
            pass  # 기호 근은 latex만
        entries.append(entry)
    return {"complete": roots.complete, "roots": entries}


def _time_window(pz: PoleZeroResult) -> float:
    decay_rates, magnitudes = [], []
    for root, _ in pz.poles.roots:
        try:
            value = complex(root)
        except TypeError:
            return 1.0
        if value.real < -1e-12:
            decay_rates.append(-value.real)
        if abs(value) > 1e-12:
            magnitudes.append(abs(value))
    if decay_rates:
        return 8.0 / min(decay_rates)
    if magnitudes:
        return 10.0 / min(magnitudes)
    return 1e-3


def _time_samples(expr: sp.Expr, tstop: float) -> dict | None:
    smooth = expr.replace(lambda e: isinstance(e, sp.DiracDelta), lambda e: sp.Integer(0))
    if smooth.free_symbols - {t}:
        return None  # 기호가 남으면 수식만 제공
    times = np.linspace(0.0, tstop, _SAMPLE_POINTS)
    values = np.asarray(sp.lambdify(t, smooth, modules="numpy")(times), dtype=float)
    if values.ndim == 0:
        values = np.full(times.shape, float(values))
    return {"t": times.tolist(), "y": values.tolist()}


@router.post("/solve")
def solve(request: SolveRequest) -> dict:
    options = request.options
    warnings: list[str] = []

    circuit = parse(request.netlist)
    limit = _max_components()
    if len(circuit.components) > limit:
        raise TooManyComponentsError(
            f"{len(circuit.components)} components exceed the limit of {limit}"
        )
    topology = validate_topology(circuit)

    system = assemble(expand_initial_conditions(circuit).circuit)
    result: dict = {
        "nodes": circuit.nodes,
        "planarity": {"planar": topology.is_planar},
        "mna": {
            "A_latex": sp.latex(system.A),
            "z_latex": sp.latex(system.z),
            "x_latex": sp.latex(sp.Matrix(system.unknowns)),
            "steps": [
                {
                    "component": record.component,
                    "deltas": [
                        {
                            "target": entry.target,
                            "row": entry.row,
                            "col": entry.col,
                            "term_latex": sp.latex(entry.term),
                        }
                        for entry in record.entries
                    ],
                }
                for record in system.records
            ],
            "checkpoints": [
                {"component": name, "A_latex": sp.latex(matrix)}
                for name, matrix in replay_checkpoints(system)
            ],
        },
    }

    tf = transfer_function(circuit)
    result["transfer_function"] = {
        "latex": sp.latex(tf.expr),
        "numerator": sp.latex(tf.numerator),
        "denominator": sp.latex(tf.denominator),
        "output_node": tf.output_node,
        "input_source": tf.input_source,
    }

    pz = pole_zero(tf)
    result["poles"] = _serialize_roots(pz.poles)
    result["zeros"] = _serialize_roots(pz.zeros)
    if not pz.poles.complete:
        warnings.append("기호 계수로 극점 닫힌형 실패 — 수치 값 대입 시 계산 가능")

    stab = stability(tf)
    result["stability"] = {
        "verdict": stab.verdict,
        "method": stab.method,
        "conditions_latex": [sp.latex(cond) for cond in stab.conditions],
        "routh_table_latex": routh_array_latex(stab.routh_table),
        "notes": list(stab.notes),
    }

    if options.responses:
        responses: dict = {}
        tstop = _time_window(pz)
        for kind in options.responses:
            compute = impulse_response if kind == "impulse" else step_response
            try:
                response = compute(tf)
            except InverseLaplaceError as exc:
                warnings.append(f"{kind} 응답 역변환 실패: {exc}")
                continue
            entry = {
                "latex": sp.latex(response.expr),
                "partial_fractions_latex": sp.latex(response.partial_fractions),
                "method": response.method,
            }
            samples = _time_samples(response.expr, tstop)
            if samples is not None:
                entry["samples"] = samples
            responses[kind] = entry
        result["responses"] = responses

    try:
        bode = bode_data(tf, options.numeric_values or None)
        result["bode"] = {
            "freq": list(bode.freq),
            "mag_db": list(bode.mag_db),
            "phase_deg": list(bode.phase_deg),
            "mag_db_asymptotic": list(bode.mag_db_asymptotic),
            "corners": list(bode.corners),
        }
    except CircuitError as exc:
        warnings.append(f"Bode 생략: {exc}")

    simplification = simplify_circuit(circuit)
    result["simplification"] = {
        "steps": [
            {
                "rule": step.rule,
                "description": step.description,
                "latex": step.latex,
                "removed": list(step.removed),
                "created": list(step.created),
            }
            for step in simplification.steps
        ],
        "final_component_count": len(simplification.circuit.components),
        "verified": simplification.verified,
    }

    verification_reports = []
    if options.verify:
        if find_ngspice() is None:
            warnings.append("ngspice 미설치 — SPICE 교차 검증 생략")
        else:
            try:
                verification_reports = [
                    verify_ac(circuit, options.numeric_values or None),
                    verify_tran(circuit, options.numeric_values or None),
                ]
                result["verification"] = {
                    "passed": all(r.passed for r in verification_reports),
                    "reports": [
                        {
                            "kind": r.kind,
                            "passed": r.passed,
                            "max_rel_error": r.max_rel_error,
                            "worst_at": r.worst_at,
                            "points": r.points,
                            "notes": list(r.notes),
                        }
                        for r in verification_reports
                    ],
                }
            except CircuitError as exc:
                warnings.append(f"SPICE 검증 실패: {exc}")

    if options.latex:
        try:
            result["latex_report"] = generate_report(
                circuit, verifications=verification_reports
            )
        except CircuitError as exc:
            warnings.append(f"LaTeX 노트 생성 실패: {exc}")

    result["warnings"] = warnings
    return result

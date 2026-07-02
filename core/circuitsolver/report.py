"""LaTeX 교수 노트 생성 (design §4.10).

Jinja2 템플릿의 구분자를 \\VAR{}/\\BLOCK{}으로 바꿔 LaTeX 중괄호와의 충돌을
피한다(ADR 참조). 노트 구성은 실제 강의 노트의 흐름을 따른다: 문제 설정 →
s-영역 변환(IC 등가) → MNA 유도(스탬프 델타 + 체크포인트, ADR-7) → H(s) →
극점·영점·Routh → 시간응답(부분분수 포함) → Bode 요약 → SPICE 검증 표.

PDF 컴파일은 호출자(API/Docker, texlive + ko.TeX 필요)의 몫이고 이 모듈은
.tex 문자열만 만든다. 한글 본문이므로 kotex 패키지를 사용한다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Mapping, Sequence

import jinja2
import sympy as sp

from .analysis import (
    impulse_response,
    pole_zero,
    stability,
    step_response,
    transfer_function,
)
from .circuit import Circuit, ComponentType
from .errors import InverseLaplaceError
from .graph import GROUND, validate_topology
from .initial import expand_initial_conditions
from .mna import MNASystem, assemble, replay_checkpoints
from .verify import VerificationReport

_KIND_KO = {
    ComponentType.RESISTOR: "저항",
    ComponentType.INDUCTOR: "인덕터",
    ComponentType.CAPACITOR: "커패시터",
    ComponentType.VOLTAGE_SOURCE: "전압원",
    ComponentType.CURRENT_SOURCE: "전류원",
}

_VERDICT_KO = {
    "stable": "안정",
    "unstable": "불안정",
    "marginal": "임계 안정",
    "conditional": "조건부 안정",
}


def _environment() -> jinja2.Environment:
    return jinja2.Environment(
        loader=jinja2.FileSystemLoader(Path(__file__).parent / "templates"),
        block_start_string=r"\BLOCK{",
        block_end_string="}",
        variable_start_string=r"\VAR{",
        variable_end_string="}",
        comment_start_string=r"\#{",
        comment_end_string="}",
        trim_blocks=True,
        autoescape=False,
        undefined=jinja2.StrictUndefined,
    )


def _text(value: str) -> str:
    """Escape for LaTeX text mode (netlist names may contain underscores)."""
    return value.replace("_", r"\_")


def _stamp_lines(system: MNASystem) -> list[dict]:
    records = []
    for record in system.records:
        pieces = []
        for entry in record.entries:
            term = sp.latex(entry.term)
            if entry.target == "A":
                pieces.append(
                    rf"A_{{{entry.row + 1},{entry.col + 1}}} \mathrel{{+}}= {term}"
                )
            else:
                pieces.append(rf"z_{{{entry.row + 1}}} \mathrel{{+}}= {term}")
        records.append({"name": _text(record.component), "entries": r",\;".join(pieces)})
    return records


def _checkpoints(system: MNASystem) -> list[dict]:
    """체크포인트에서만 전체 행렬을 렌더링 (ADR-7): 첫 소자, 중간, 최종."""
    return [
        {"label": f"{_text(name)} 스탬프까지 적용한 뒤:", "matrix": sp.latex(matrix)}
        for name, matrix in replay_checkpoints(system)
    ]


def routh_array_latex(table) -> str | None:
    """Routh 표 → LaTeX array (report와 API 응답이 공용)."""
    if table is None:
        return None
    body = r" \\ ".join(
        " & ".join(sp.latex(entry) for entry in row) for row in table
    )
    columns = "c" * len(table[0])
    return rf"\begin{{array}}{{{columns}}} {body} \end{{array}}"


def generate_report(
    circuit: Circuit,
    title: str = "회로 해석 노트",
    include_responses: bool = True,
    verifications: Sequence[VerificationReport] = (),
    corners: Sequence[float] = (),
) -> str:
    """Render the professor-note .tex for a circuit with an .out directive."""
    report = validate_topology(circuit)
    tf = transfer_function(circuit)
    expansion = expand_initial_conditions(circuit)
    system = assemble(expansion.circuit)
    pz = pole_zero(tf)
    stab = stability(tf)

    components = [
        {
            "name": _text(comp.name),
            "kind": _KIND_KO[comp.ctype],
            "nodes": _text(f"{comp.nodes[0]}, {comp.nodes[1]}"),
            "value": sp.latex(comp.value),
            "ic": sp.latex(comp.ic) if comp.ic is not None else None,
        }
        for comp in circuit.components
    ]

    ic_rows = []
    for comp in circuit.components:
        if comp.ic is None:
            continue
        source = expansion.circuit.component(f"Iic_{comp.name}")
        quantity = "i_L(0^-)" if comp.ctype is ComponentType.INDUCTOR else "v_C(0^-)"
        ic_rows.append(
            {
                "description": rf"{_text(comp.name)} (${quantity} = {sp.latex(comp.ic)}$)",
                "source": _text(source.name),
                "value": sp.latex(source.value),
            }
        )

    impulse_latex = step_latex = impulse_pf = None
    response_note = None
    if include_responses:
        try:
            impulse = impulse_response(tf)
            step = step_response(tf)
            impulse_latex = sp.latex(impulse.expr)
            step_latex = sp.latex(step.expr)
            impulse_pf = sp.latex(impulse.partial_fractions)
            if impulse.method != "table" or step.method != "table":
                response_note = "일부 역변환은 SymPy fallback으로 계산되었다."
        except InverseLaplaceError:
            response_note = (
                "닫힌형 역라플라스를 얻지 못했다 — 수치 시뮬레이션 결과만 제공된다."
            )

    context = {
        "title": _text(title),
        "components": components,
        "nodes": ", ".join(f"${_text(n)}$" for n in circuit.nodes if n != GROUND),
        "planar": report.is_planar,
        "ic_rows": ic_rows,
        "unknowns": sp.latex(sp.Matrix(system.unknowns)),
        "stamps": _stamp_lines(system),
        "checkpoints": _checkpoints(system),
        "z_vector": sp.latex(system.z),
        "output_node": _text(tf.output_node),
        "input_source": _text(tf.input_source),
        "h_latex": sp.latex(tf.expr),
        "den_latex": sp.latex(tf.denominator),
        "pole_rows": [
            {"value": sp.latex(root), "mult": mult} for root, mult in pz.poles.roots
        ],
        "zero_rows": [
            {"value": sp.latex(root), "mult": mult} for root, mult in pz.zeros.roots
        ],
        "poles_complete": pz.poles.complete,
        "routh_latex": routh_array_latex(stab.routh_table),
        "stability_text": _VERDICT_KO.get(stab.verdict, stab.verdict),
        "stability_method": "Routh–Hurwitz" if stab.method == "routh" else "수치 극점",
        "stability_conditions": [sp.latex(cond) for cond in stab.conditions],
        "stability_notes": [_text(note) for note in stab.notes],
        "impulse_latex": impulse_latex,
        "step_latex": step_latex,
        "impulse_pf": impulse_pf,
        "response_note": response_note,
        "corners": [f"{corner:.6g}" for corner in corners],
        "verifications": [
            {
                "kind": v.kind,
                "passed": v.passed,
                "err": f"{v.max_rel_error:.3g}",
                "at": f"{v.worst_at:.6g}",
                "points": v.points,
            }
            for v in verifications
        ],
    }
    template = _environment().get_template("note.tex.j2")
    return template.render(**context)

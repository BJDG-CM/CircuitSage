"""자체 netlist 확장 → 순수 ngspice 방언 변환 계층 (design §4.1, ADR-6).

CircuitSage netlist는 기호 값, 인라인 IC=, `.out` 지시어를 허용하지만
ngspice에는 그대로 넘길 수 없다. 이 모듈은 (1) 기호 값을 수치로 대입하고,
(2) `.out`을 제거하며(검증 대상 노드는 verify가 별도로 안다),
(3) IC는 ngspice가 지원하는 소자 인라인 `ic=` 문법으로 유지해
`.tran ... uic`와 함께 쓸 수 있는 소자 라인들을 만든다.

해석(.ac/.tran) 제어 라인은 verify.py(§4.11)가 조립한다.
"""

from __future__ import annotations

from typing import Mapping, Sequence

import sympy as sp

from .circuit import Circuit
from .errors import CircuitError


def substitute_numeric(expr: sp.Expr, numeric_values: Mapping | None, context: str) -> sp.Expr:
    """Substitute by symbol *name* (assumption-carrying symbols still match)."""
    values = {
        (key if isinstance(key, str) else key.name): sp.nsimplify(value, rational=True)
        for key, value in (numeric_values or {}).items()
    }
    expr = sp.sympify(expr).subs(
        {sym: values[sym.name] for sym in expr.free_symbols if sym.name in values}
    )
    remaining = expr.free_symbols
    if remaining:
        names = ", ".join(sorted(str(sym) for sym in remaining))
        raise CircuitError(
            f"{context}: symbols remain ({names}); "
            "provide numeric_values for SPICE verification"
        )
    return expr


def _format(value: sp.Expr) -> str:
    return f"{float(value):.12g}"


def element_lines(
    circuit: Circuit,
    numeric_values: Mapping | None = None,
    source_specs: Mapping[str, str] | None = None,
) -> list[str]:
    """Pure-ngspice element lines.

    source_specs overrides a source's value field with a raw SPICE spec,
    e.g. {"Vin": "DC 0 AC 1"} for .ac decks — the caller (verify) decides.
    """
    specs = dict(source_specs or {})
    lines: list[str] = []
    for comp in circuit.components:
        fields = [comp.name, comp.nodes[0], comp.nodes[1]]
        override = specs.pop(comp.name, None)
        if override is not None:
            fields.append(override)
        else:
            fields.append(_format(substitute_numeric(comp.value, numeric_values, comp.name)))
        if comp.ic is not None:
            ic_value = substitute_numeric(comp.ic, numeric_values, f"{comp.name} IC")
            fields.append(f"ic={_format(ic_value)}")
        lines.append(" ".join(fields))
    if specs:
        unknown = ", ".join(sorted(specs))
        raise CircuitError(f"source_specs refers to unknown components: {unknown}")
    return lines


def full_netlist(
    circuit: Circuit,
    control_lines: Sequence[str],
    numeric_values: Mapping | None = None,
    source_specs: Mapping[str, str] | None = None,
    title: str = "circuitsage verification deck",
) -> str:
    """Complete ngspice batch deck: title, elements, control block, .end."""
    lines = [f"* {title}"]
    lines += element_lines(circuit, numeric_values, source_specs)
    lines += list(control_lines)
    lines.append(".end")
    return "\n".join(lines) + "\n"

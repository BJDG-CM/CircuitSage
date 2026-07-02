"""Transfer function H(s) = V(out) / input (design §4.5).

Pipeline: topology validation → MNA assembly → LUsolve → cancel.
Per §4.5, only cancel/together are used for cleanup — never simplify(),
which can blow up exponentially on symbolic circuits. A Cramer-based
backend is planned as a benchmark alternative (design §4.5, §12).
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import sympy as sp
from sympy.matrices.exceptions import NonInvertibleMatrixError

from .circuit import SOURCE_TYPES, Circuit
from .errors import CircuitError, SingularMatrixError
from .graph import GROUND, validate_topology
from .mna import assemble


@dataclass(frozen=True)
class TransferFunction:
    expr: sp.Expr
    numerator: sp.Expr
    denominator: sp.Expr  # characteristic polynomial of the circuit
    output_node: str
    input_source: str


def transfer_function(circuit: Circuit) -> TransferFunction:
    """Compute H(s) as specified by the netlist's .out directive.

    H(s) is defined with every other independent source switched off
    (V → short, I → open); zeroing their values achieves both in MNA.
    """
    if circuit.output is None:
        raise CircuitError("netlist has no .out directive; cannot form H(s)")
    validate_topology(circuit)

    source = circuit.component(circuit.output.source)
    if source.value == 0:
        raise CircuitError(f"input source {source.name} has zero value")

    others_zeroed = tuple(
        replace(comp, value=sp.Integer(0))
        if comp.ctype in SOURCE_TYPES and comp.name != source.name
        else comp
        for comp in circuit.components
    )
    system = assemble(Circuit(components=others_zeroed, output=circuit.output))

    try:
        x = system.A.LUsolve(system.z)
    except (NonInvertibleMatrixError, ValueError) as exc:
        raise SingularMatrixError(
            "MNA matrix is singular despite topology checks; likely causes: "
            "degenerate element values or a constraint loop not visible in the graph"
        ) from exc

    if circuit.output.node == GROUND:
        v_out = sp.Integer(0)
    else:
        v_out = x[system.node_index[circuit.output.node], 0]

    expr = sp.cancel(v_out / source.value)
    numerator, denominator = sp.fraction(expr)
    return TransferFunction(
        expr=expr,
        numerator=numerator,
        denominator=denominator,
        output_node=circuit.output.node,
        input_source=source.name,
    )

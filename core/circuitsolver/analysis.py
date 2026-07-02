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
from .initial import expand_initial_conditions
from .laplace import TimeResponse, inverse_laplace
from .mna import MNASystem, assemble, s


def _lusolve(system: MNASystem) -> sp.Matrix:
    try:
        return system.A.LUsolve(system.z)
    except (NonInvertibleMatrixError, ValueError) as exc:
        raise SingularMatrixError(
            "MNA matrix is singular despite topology checks; likely causes: "
            "degenerate element values or a constraint loop not visible in the graph"
        ) from exc


def solve_node_voltages(circuit: Circuit, validate: bool = True) -> dict[str, sp.Expr]:
    """Full s-domain node solve, with ICs expanded first (§4.4).

    Returns {node: V(s)} including the ground node (0). This is the
    complete response; use initial.zero_state_circuit / zero_input_circuit
    to obtain the superposition parts separately.
    """
    if validate:
        validate_topology(circuit)
    expanded = expand_initial_conditions(circuit).circuit
    system = assemble(expanded)
    x = _lusolve(system)
    voltages: dict[str, sp.Expr] = {GROUND: sp.Integer(0)}
    for node, index in system.node_index.items():
        voltages[node] = sp.cancel(x[index, 0])
    return voltages


@dataclass(frozen=True)
class TransferFunction:
    expr: sp.Expr
    numerator: sp.Expr
    denominator: sp.Expr  # characteristic polynomial of the circuit
    output_node: str
    input_source: str


@dataclass(frozen=True)
class RootSet:
    """Roots of one polynomial: ((value, multiplicity), ...).

    complete=False means closed-form extraction failed (symbolic
    coefficients of degree > 4, or no closed form): per design §4.6 the
    caller should report "computable after numeric substitution".
    """

    roots: tuple[tuple[sp.Expr, int], ...]
    complete: bool

    @property
    def values(self) -> tuple[sp.Expr, ...]:
        return tuple(root for root, _ in self.roots)


@dataclass(frozen=True)
class PoleZeroResult:
    poles: RootSet
    zeros: RootSet


def _root_set(expr: sp.Expr) -> RootSet:
    poly = sp.Poly(expr, s)
    degree = poly.degree()
    if degree <= 0:
        return RootSet(roots=(), complete=True)

    symbolic = bool(poly.free_symbols - {s})
    found: dict[sp.Expr, int] = {}
    if not symbolic or degree <= 4:
        try:
            found = sp.roots(poly)
        except (sp.PolynomialError, NotImplementedError):
            found = {}
    if sum(found.values()) == degree:
        return RootSet(roots=tuple(found.items()), complete=True)

    if not symbolic:
        numeric = poly.nroots()
        return RootSet(roots=tuple((root, 1) for root in numeric), complete=True)
    return RootSet(roots=tuple(found.items()), complete=False)


def pole_zero(tf: TransferFunction) -> PoleZeroResult:
    """Poles/zeros of H(s) per design §4.6: exact closed forms where
    feasible (always for numeric coefficients, degree ≤ 4 for symbolic),
    numeric nroots() as the numeric fallback."""
    return PoleZeroResult(
        poles=_root_set(tf.denominator),
        zeros=_root_set(tf.numerator),
    )


# --- Time responses (design §4.7) -------------------------------------------


def impulse_response(tf: TransferFunction) -> TimeResponse:
    """h(t) = L⁻¹{H(s)}, valid for t ≥ 0."""
    return inverse_laplace(tf.expr)


def step_response(tf: TransferFunction) -> TimeResponse:
    """y(t) = L⁻¹{H(s)/s}, valid for t ≥ 0."""
    return inverse_laplace(tf.expr / s)


# --- Routh–Hurwitz stability (design §4.6) ---------------------------------

_EPS = sp.Symbol("epsilon", positive=True)


@dataclass(frozen=True)
class StabilityResult:
    """Two-stage output (design §4.6): a definite verdict when every
    first-column sign is decidable, otherwise verdict="conditional" with
    the positivity conditions as first-class results.

    verdict: "stable" | "unstable" | "marginal" | "conditional"
    method:  "routh" | "numeric"
    conditions: inequalities (entry > 0) whose truth decides stability;
        they assume the characteristic polynomial is normalized to a
        positive leading coefficient.
    """

    verdict: str
    method: str
    conditions: tuple[sp.Rel, ...] = ()
    routh_table: tuple[tuple[sp.Expr, ...], ...] | None = None
    notes: tuple[str, ...] = ()


def _pad(row: list[sp.Expr], width: int) -> list[sp.Expr]:
    return list(row) + [sp.Integer(0)] * (width - len(row))


def _fix_special_rows(rows: list[list[sp.Expr]], index: int, n: int, width: int,
                      notes: list[str]) -> bool:
    """Apply Routh special-case handling to rows[index] in place.

    Returns True if a full zero row was replaced (marginal candidate).
    Zero row → derivative of the auxiliary polynomial built from the row
    above; zero pivot with nonzero row → epsilon (0+) substitution.
    """
    row = rows[index]
    if all(entry.is_zero for entry in row):
        power_above = n - index + 1
        replacement: list[sp.Expr] = []
        for j, coeff in enumerate(rows[index - 1]):
            power = power_above - 2 * j
            if power >= 1:
                replacement.append(coeff * power)
        rows[index] = _pad(replacement, width)
        notes.append(
            f"s^{n - index} 행이 전부 0 — 보조 다항식의 도함수로 대체 (jω축 근 후보)"
        )
        return True
    if row[0].is_zero:
        row[0] = _EPS
        notes.append(f"s^{n - index} 행의 첫 열이 0 — ε(0+) 치환")
    return False


def routh_table(poly: sp.Poly) -> tuple[list[list[sp.Expr]], list[str], bool]:
    """Build the full Routh array for a polynomial in s.

    Returns (rows, notes, had_zero_row); rows[k] corresponds to s^(n-k).
    """
    n = poly.degree()
    coeffs = poly.all_coeffs()
    width = n // 2 + 1
    rows: list[list[sp.Expr]] = [_pad(coeffs[0::2], width)]
    if n >= 1:
        rows.append(_pad(coeffs[1::2], width))
    notes: list[str] = []
    had_zero_row = False

    for k in range(2, n + 1):
        had_zero_row |= _fix_special_rows(rows, k - 1, n, width, notes)
        prev, prev2 = rows[k - 1], rows[k - 2]
        new_row = [
            sp.cancel((prev[0] * prev2[j + 1] - prev2[0] * prev[j + 1]) / prev[0])
            for j in range(width - 1)
        ]
        rows.append(_pad(new_row, width))
    return rows, notes, had_zero_row


def _first_column_sign(entry: sp.Expr) -> int | None:
    """Sign of a first-column entry; None if undecidable symbolically.

    Entries containing ε are evaluated in the limit ε → 0+, scaling by
    powers of ε until the limit resolves.
    """
    if entry.has(_EPS):
        for order in range(3):
            limit = sp.limit(entry / _EPS**order, _EPS, 0, "+")
            # is_extended_* covers ±oo, which plain is_positive/negative excludes
            if limit.is_extended_positive:
                return 1
            if limit.is_extended_negative:
                return -1
            if limit != 0:
                return None
        return None
    factored = sp.factor(entry)
    if factored.is_zero:
        return 0
    if factored.is_positive:
        return 1
    if factored.is_negative:
        return -1
    return None


def routh_stability(poly: sp.Poly) -> StabilityResult:
    """Routh–Hurwitz verdict for an arbitrary polynomial in s."""
    if poly.LC().is_negative:
        poly = sp.Poly(-poly.as_expr(), s)
    rows, notes, had_zero_row = routh_table(poly)
    table = tuple(tuple(row) for row in rows)
    first_column = [row[0] for row in rows]
    signs = [_first_column_sign(entry) for entry in first_column]

    if None in signs:
        conditions = tuple(
            sp.Gt(entry, 0)
            for entry, sign in zip(first_column, signs)
            if sign is None
        )
        notes.append("부호 미확정 원소 존재 — 아래 조건이 모두 성립하면 안정")
        return StabilityResult(
            verdict="conditional", method="routh",
            conditions=conditions, routh_table=table, notes=tuple(notes),
        )

    nonzero = [sign for sign in signs if sign != 0]
    changes = sum(1 for a, b in zip(nonzero, nonzero[1:]) if a != b)
    if changes > 0:
        notes.append(f"첫 열 부호 변화 {changes}회 → 우반평면 근 {changes}개")
        verdict = "unstable"
    elif had_zero_row or 0 in signs:
        verdict = "marginal"
    else:
        verdict = "stable"
    return StabilityResult(
        verdict=verdict, method="routh", routh_table=table, notes=tuple(notes)
    )


def stability(tf: TransferFunction) -> StabilityResult:
    """Stability of H(s) (design §4.6): direct max Re(p) check when the
    denominator is numeric, Routh–Hurwitz otherwise."""
    poly = sp.Poly(tf.denominator, s)
    if poly.degree() <= 0:
        return StabilityResult(
            verdict="stable", method="numeric",
            notes=("분모가 상수 — 동특성 없음",),
        )
    if not (poly.free_symbols - {s}):
        tolerance = 1e-9
        real_parts = [complex(root).real for root in poly.nroots()]
        if max(real_parts) > tolerance:
            verdict = "unstable"
        elif max(real_parts) >= -tolerance:
            verdict = "marginal"
        else:
            verdict = "stable"
        return StabilityResult(
            verdict=verdict, method="numeric",
            notes=(f"max Re(p) = {max(real_parts):.6g}",),
        )
    return routh_stability(poly)


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
    x = _lusolve(system)

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

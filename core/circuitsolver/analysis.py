"""Transfer function H(s) = V(out) / input (design §4.5).

Pipeline: topology validation → MNA assembly → linear solve → cancel.
Per §4.5, only cancel/together are used for cleanup — never simplify(),
which can blow up exponentially on symbolic circuits.

Two solve backends exist (selected by benchmark evidence, see
docs/benchmarks.md; override with CIRCUITSAGE_SOLVER=auto|lusolve|cramer):

* ``lusolve`` — Matrix.LUsolve for the full unknown vector; fast for
  numeric and few-symbol systems, and required when every node voltage
  is needed (solve_node_voltages).
* ``cramer``  — only the requested output as det(A_i)/det(A) via the
  division-free Berkowitz determinant; avoids the nested-fraction
  blow-up of LU pivots when many independent symbols are present.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field, replace

import sympy as sp
from sympy.matrices.exceptions import NonInvertibleMatrixError

from .circuit import REACTIVE_TYPES, SOURCE_TYPES, Circuit
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


def _output_lusolve(system: MNASystem, index: int) -> sp.Expr:
    return _lusolve(system)[index, 0]


def _output_cramer(system: MNASystem, index: int) -> sp.Expr:
    """Cramer's rule for a single output: det(A_i)/det(A), Berkowitz dets."""
    det_a = sp.cancel(sp.together(system.A.det(method="berkowitz")))
    if det_a == 0:
        raise SingularMatrixError(
            "MNA matrix is singular despite topology checks; likely causes: "
            "degenerate element values or a constraint loop not visible in the graph"
        )
    replaced = system.A.copy()
    replaced[:, index] = system.z
    det_i = replaced.det(method="berkowitz")
    return sp.cancel(det_i / det_a)


_BACKENDS = {"lusolve": _output_lusolve, "cramer": _output_cramer}


@dataclass(frozen=True)
class SolverDiagnostics:
    """Internal diagnostics for one transfer-function solve.

    Not shown in the main UI by default; the API exposes it only when
    options.debug is set.
    """

    backend: str
    matrix_dimension: int
    symbol_count: int
    stage_timings: dict[str, float] = field(default_factory=dict)
    fallback_used: bool = False


def _choose_backend(requested: str, symbol_count: int) -> str:
    """Backend selection.

    Evidence (docs/benchmarks.md, ladder/bridge/V-source suite): the cost
    driver is the count of *independent* symbols, because the LU pivot
    fractions make the final rational cancel explode while the
    division-free Cramer/Berkowitz path stays flat. Measured: repeated-
    symbol ladder (3 symbols) LU ~10× faster; RLC (4 symbols) LU ~2×
    faster; three V-source branches (5 symbols) LU catastrophic
    (~20–48 min in the final cancel) vs Cramer ~0.45 s; symbolic bridge
    (6 symbols) Cramer ~38× faster; unique ladder at 11 symbols Cramer
    ~80× faster. LU still wins at 3–4 symbols, and its downside above
    that is unbounded while Cramer's overhead below it is a few
    milliseconds → threshold 5.
    """
    if requested != "auto":
        return requested
    return "cramer" if symbol_count >= 5 else "lusolve"


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
    """H(s) for the selected input/output pair.

    ``denominator`` is the *reduced transfer denominator*: the denominator
    of H(s) after rational cancellation. It determines the poles visible
    in this particular transfer function only — internal modes that
    cancel against the numerator (unobservable/uncontrollable from the
    chosen ports) do not appear here. It is NOT the circuit's
    characteristic polynomial; use system_modes() for internal modes.
    """

    expr: sp.Expr
    numerator: sp.Expr
    denominator: sp.Expr  # reduced transfer denominator (see docstring)
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
    """Transfer poles/zeros of H(s) per design §4.6: exact closed forms
    where feasible (always for numeric coefficients, degree ≤ 4 for
    symbolic), numeric nroots() as the numeric fallback.

    These are the poles of the *reduced* transfer function; internal
    modes cancelled in H(s) are reported by system_modes() instead."""
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


def _stability_of_expr(denominator: sp.Expr) -> StabilityResult:
    """Stability of a polynomial in s (design §4.6): direct max Re(p)
    check when the coefficients are numeric, Routh–Hurwitz otherwise."""
    poly = sp.Poly(denominator, s)
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


def transfer_stability(tf: TransferFunction) -> StabilityResult:
    """Stability judged from the *reduced transfer denominator* only.

    An internal mode cancelled in H(s) is invisible here: a circuit can
    be transfer-stable while an internal mode misbehaves. Internal
    stability comes from system_modes(circuit).stability."""
    return _stability_of_expr(tf.denominator)


# Backward-compatible alias; prefer transfer_stability for clarity.
stability = transfer_stability


# --- System characteristic modes (independent of the chosen H) -------------


@dataclass(frozen=True)
class SystemModes:
    """Internal natural modes of the circuit, from the MNA system itself.

    status:
      "ok"      — characteristic extracted; degree = detected dynamic order
      "static"  — no dynamic modes (characteristic is constant)
      "partial" — extracted, but some factors may not be physical modes
      "unknown" — extraction not reliable for this topology
    """

    characteristic: sp.Expr | None  # polynomial in s, sign-normalized
    modes: RootSet | None
    status: str
    note: str
    stability: StabilityResult | None


def system_modes(circuit: Circuit) -> SystemModes:
    """Natural modes from det A(s) of the MNA system.

    Method: the system is assembled with capacitors as admittances (sC)
    and **inductors as Group-2 branches** (unknown current i_L with the
    row v_p − v_m − sL·i_L = 0), so every entry of A(s) is polynomial in
    s and det A(s) is a polynomial pencil determinant. Its roots are
    exactly the frequencies where the pencil loses rank — the natural
    frequencies of the circuit, *including* inductor-current states that
    the plain 1/(sL) admittance form hides behind ideal-source
    constraints (an inductor directly across an ideal voltage source
    correctly shows its s = 0 integrator mode here). The constant
    scale/sign is normalized away; cancel() is still applied defensively
    before extracting the numerator.

    Honest limits, stated in ``note``:
      * degenerate topologies legitimately reduce the detected order
        (e.g. two parallel capacitors form one mode);
      * if det A(s) is identically zero the pencil is singular and the
        result is status="unknown" instead of a fabricated answer.
    """
    validate_topology(circuit)
    system = assemble(circuit, inductor_branch_currents=True)
    if system.A.shape[0] == 0:
        return SystemModes(None, None, "unknown", "MNA 시스템이 비어 있음", None)

    try:
        determinant = system.A.det(method="berkowitz")
    except Exception as exc:  # noqa: BLE001 — surfaced as a structured result
        return SystemModes(
            None, None, "unknown", f"det A(s) 계산 실패: {type(exc).__name__}", None
        )

    numerator, _ = sp.fraction(sp.cancel(sp.together(determinant)))
    numerator = sp.expand(numerator)
    if numerator == 0:
        return SystemModes(
            None,
            None,
            "unknown",
            "det A(s)가 항등적으로 0 — 이 위상에서는 MNA pencil이 특이해 "
            "내부 모드를 신뢰성 있게 추출할 수 없음",
            None,
        )

    poly = sp.Poly(numerator, s)
    if poly.degree() <= 0:
        return SystemModes(
            sp.Integer(1),
            RootSet(roots=(), complete=True),
            "static",
            "동적 모드 없음 — 특성식이 상수",
            StabilityResult(
                verdict="stable", method="numeric", notes=("동특성 없음",)
            ),
        )

    if poly.LC().is_negative:
        poly = sp.Poly(-poly.as_expr(), s)
    characteristic = poly.as_expr()
    reactive_count = sum(
        1 for comp in circuit.components if comp.ctype in REACTIVE_TYPES
    )
    degree = poly.degree()
    note = (
        f"검출된 동적 차수 {degree} (리액티브 소자 {reactive_count}개). "
        "인덕터는 가지 전류 정식화로 조립되어 이상 전원에 직결된 상태도 "
        "포함된다; 축퇴 위상(예: 병렬 커패시터, 이상 전압원에 직결된 "
        "커패시터)은 독립 상태가 줄어 차수가 정당하게 낮아질 수 있다."
    )
    status = "ok"
    if degree > reactive_count:
        status = "partial"
        note += " — 차수가 리액티브 소자 수를 초과: 일부 인자는 물리 모드가 아닐 수 있음"

    return SystemModes(
        characteristic=characteristic,
        modes=_root_set(characteristic),
        status=status,
        note=note,
        stability=_stability_of_expr(characteristic),
    )


def transfer_function_with_diagnostics(
    circuit: Circuit, backend: str = "auto"
) -> tuple[TransferFunction, SolverDiagnostics]:
    """Compute H(s) as specified by the netlist's .out directive.

    H(s) is defined with every other independent source switched off
    (V → short, I → open); zeroing their values achieves both in MNA.
    ``backend`` is "auto" | "lusolve" | "cramer"; "auto" consults the
    CIRCUITSAGE_SOLVER environment variable first, then the benchmark
    heuristic (_choose_backend). A failing non-default backend falls
    back to lusolve and sets diagnostics.fallback_used.
    """
    if circuit.output is None:
        raise CircuitError("netlist has no .out directive; cannot form H(s)")

    timings: dict[str, float] = {}
    started = time.perf_counter()
    validate_topology(circuit)
    timings["topology"] = time.perf_counter() - started

    source = circuit.component(circuit.output.source)
    if source.value == 0:
        raise CircuitError(f"input source {source.name} has zero value")

    started = time.perf_counter()
    others_zeroed = tuple(
        replace(comp, value=sp.Integer(0))
        if comp.ctype in SOURCE_TYPES and comp.name != source.name
        else comp
        for comp in circuit.components
    )
    system = assemble(Circuit(components=others_zeroed, output=circuit.output))
    timings["assemble"] = time.perf_counter() - started

    symbol_count = len(
        (system.A.free_symbols | system.z.free_symbols | source.value.free_symbols)
        - {s}
    )
    requested = backend
    if requested == "auto":
        requested = os.environ.get("CIRCUITSAGE_SOLVER", "auto").strip().lower()
    if requested not in ("auto", *_BACKENDS):
        raise CircuitError(f"unknown solver backend '{requested}'")
    chosen = _choose_backend(requested, symbol_count)

    started = time.perf_counter()
    fallback_used = False
    if circuit.output.node == GROUND:
        v_out = sp.Integer(0)
    else:
        index = system.node_index[circuit.output.node]
        try:
            v_out = _BACKENDS[chosen](system, index)
        except SingularMatrixError:
            raise
        except Exception:  # noqa: BLE001 — backend bug must not lose the solve
            if chosen == "lusolve":
                raise
            v_out = _output_lusolve(system, index)
            chosen = "lusolve"
            fallback_used = True
    timings["solve"] = time.perf_counter() - started

    started = time.perf_counter()
    expr = sp.cancel(v_out / source.value)
    numerator, denominator = sp.fraction(expr)
    timings["normalize"] = time.perf_counter() - started

    tf = TransferFunction(
        expr=expr,
        numerator=numerator,
        denominator=denominator,
        output_node=circuit.output.node,
        input_source=source.name,
    )
    diagnostics = SolverDiagnostics(
        backend=chosen,
        matrix_dimension=system.A.shape[0],
        symbol_count=symbol_count,
        stage_timings=timings,
        fallback_used=fallback_used,
    )
    return tf, diagnostics


def transfer_function(circuit: Circuit, backend: str = "auto") -> TransferFunction:
    """H(s) only — see transfer_function_with_diagnostics."""
    tf, _ = transfer_function_with_diagnostics(circuit, backend)
    return tf

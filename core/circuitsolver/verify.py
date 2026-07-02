"""ngspice cross-verification (design §4.11, ADR-5).

ngspice runs as a batch-mode subprocess on decks produced by spice_io.
Two axes:
  AC   — |H(jω)| and phase vs. the symbolic H(s) on a log frequency grid
         (compared as complex values: |H_sym − H_spice| / max(|H_sym|, floor));
  TRAN — step response (.tran ... uic, inline ic=) vs. the closed-form
         inverse Laplace of the full response. Every independent source
         value V becomes V/s on the symbolic side, matching ngspice's
         "DC value switched on at t=0 under uic" semantics.

Pass criterion is a mixed tolerance: relative error (default 0.1%) with
an absolute floor scaled to the largest reference sample.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Mapping

import numpy as np
import sympy as sp

from .analysis import _root_set, solve_node_voltages, transfer_function
from .circuit import SOURCE_TYPES, Circuit
from .errors import CircuitError, VerificationError
from .laplace import inverse_laplace, t
from .mna import s
from .spice_io import full_netlist, numeric_circuit, substitute_numeric

_TWO_PI = 2.0 * np.pi


@dataclass(frozen=True)
class VerificationReport:
    passed: bool
    kind: str  # "ac" | "tran"
    max_rel_error: float
    worst_at: float  # Hz for ac, seconds for tran
    points: int
    rtol: float
    notes: tuple[str, ...] = ()


def find_ngspice() -> str | None:
    for name in ("ngspice", "ngspice_con"):
        path = shutil.which(name)
        if path:
            return path
    return None


def _run_deck(deck: str, output_files: list[str]) -> dict[str, np.ndarray]:
    executable = find_ngspice()
    if executable is None:
        raise VerificationError(
            "ngspice executable not found on PATH; install ngspice to verify"
        )
    with tempfile.TemporaryDirectory(prefix="circuitsage_") as tmp:
        tmpdir = Path(tmp)
        deck_path = tmpdir / "deck.cir"
        deck_path.write_text(deck, encoding="utf-8")
        result = subprocess.run(
            [executable, "-b", deck_path.name],
            cwd=tmpdir,
            capture_output=True,
            text=True,
            timeout=120,
        )
        data: dict[str, np.ndarray] = {}
        missing = []
        for name in output_files:
            path = tmpdir / name
            if path.exists():
                data[name] = np.atleast_2d(np.loadtxt(path))
            else:
                missing.append(name)
        if missing:
            tail = (result.stdout + result.stderr)[-2000:]
            raise VerificationError(
                f"ngspice did not produce {', '.join(missing)} "
                f"(exit {result.returncode}); output tail:\n{tail}"
            )
    return data


def _mixed_rel_error(reference: np.ndarray, measured: np.ndarray) -> np.ndarray:
    floor = 1e-6 * float(np.max(np.abs(reference))) + 1e-15
    return np.abs(reference - measured) / np.maximum(np.abs(reference), floor)


def _require_output(circuit: Circuit) -> None:
    if circuit.output is None:
        raise CircuitError("netlist has no .out directive; nothing to verify")


# --- AC verification ---------------------------------------------------------


def ac_deck(circuit: Circuit, numeric_values: Mapping | None,
            fstart: float, fstop: float, points_per_decade: int) -> str:
    _require_output(circuit)
    node = circuit.output.node
    control = [
        ".control",
        f"ac dec {points_per_decade} {fstart:.6g} {fstop:.6g}",
        f"let hre = re(v({node}))",
        f"let him = im(v({node}))",
        "wrdata out_re.txt hre",
        "wrdata out_im.txt him",
        ".endc",
    ]
    return full_netlist(
        circuit,
        control,
        numeric_values=numeric_values,
        source_specs={circuit.output.source: "DC 0 AC 1"},
        title="circuitsage ac verification",
    )


def verify_ac(
    circuit: Circuit,
    numeric_values: Mapping | None = None,
    points_per_decade: int = 20,
    rtol: float = 1e-3,
) -> VerificationReport:
    _require_output(circuit)
    tf = transfer_function(circuit)
    h_expr = substitute_numeric(tf.expr, numeric_values, "H(s)", allow=(s,))

    corners = [
        abs(complex(root))
        for expr in sp.fraction(h_expr)
        for root, _ in _root_set(expr).roots
        if abs(complex(root)) > 1e-12
    ]
    if corners:
        fstart = 10.0 ** (np.floor(np.log10(min(corners) / _TWO_PI)) - 1)
        fstop = 10.0 ** (np.ceil(np.log10(max(corners) / _TWO_PI)) + 1)
    else:
        fstart, fstop = 1.0, 1e4

    deck = ac_deck(circuit, numeric_values, fstart, fstop, points_per_decade)
    data = _run_deck(deck, ["out_re.txt", "out_im.txt"])
    freq = data["out_re.txt"][:, 0]
    h_spice = data["out_re.txt"][:, -1] + 1j * data["out_im.txt"][:, -1]

    h_func = sp.lambdify(s, h_expr, modules="numpy")
    h_sym = np.asarray(h_func(1j * _TWO_PI * freq), dtype=complex)
    if h_sym.ndim == 0:
        h_sym = np.full(freq.shape, complex(h_sym))

    errors = _mixed_rel_error(h_sym, h_spice)
    worst = int(np.argmax(errors))
    return VerificationReport(
        passed=bool(errors[worst] < rtol),
        kind="ac",
        max_rel_error=float(errors[worst]),
        worst_at=float(freq[worst]),
        points=int(freq.size),
        rtol=rtol,
    )


# --- Transient (step) verification ------------------------------------------


def tran_deck(circuit: Circuit, numeric_values: Mapping | None,
              tstep: float, tstop: float) -> str:
    _require_output(circuit)
    node = circuit.output.node
    control = [
        ".control",
        f"tran {tstep:.6g} {tstop:.6g} uic",
        f"wrdata out_tran.txt v({node})",
        ".endc",
    ]
    return full_netlist(
        circuit,
        control,
        numeric_values=numeric_values,
        title="circuitsage tran verification",
    )


def _symbolic_step_output(circuit: Circuit) -> sp.Expr:
    """V_out(s) with every independent DC source treated as a step (V → V/s)."""
    components = tuple(
        replace(comp, value=comp.value / s) if comp.ctype in SOURCE_TYPES else comp
        for comp in circuit.components
    )
    stepped = Circuit(components=components, output=circuit.output)
    return solve_node_voltages(stepped)[circuit.output.node]


def verify_tran(
    circuit: Circuit,
    numeric_values: Mapping | None = None,
    rtol: float = 1e-3,
    points: int = 400,
) -> VerificationReport:
    _require_output(circuit)
    numeric = numeric_circuit(circuit, numeric_values)
    v_out = _symbolic_step_output(numeric)

    poles = [complex(root) for root, _ in _root_set(sp.fraction(v_out)[1]).roots]
    decay_rates = [abs(p.real) for p in poles if p.real < -1e-12]
    notes: list[str] = []
    if decay_rates:
        tstop = 8.0 / min(decay_rates)
    else:
        nonzero = [abs(p) for p in poles if abs(p) > 1e-12]
        tstop = 10.0 / min(nonzero) if nonzero else 1e-3
        notes.append("no decaying poles; comparison window is heuristic")
    tstep = tstop / points

    response = inverse_laplace(v_out)
    y_expr = response.expr.replace(
        lambda e: isinstance(e, sp.DiracDelta), lambda e: sp.Integer(0)
    )
    y_func = sp.lambdify(t, y_expr, modules="numpy")

    deck = tran_deck(numeric, None, tstep, tstop)
    data = _run_deck(deck, ["out_tran.txt"])
    times = data["out_tran.txt"][:, 0]
    y_spice = data["out_tran.txt"][:, -1]

    y_sym = np.asarray(y_func(times), dtype=float)
    if y_sym.ndim == 0:
        y_sym = np.full(times.shape, float(y_sym))

    errors = _mixed_rel_error(y_sym, y_spice)
    worst = int(np.argmax(errors))
    return VerificationReport(
        passed=bool(errors[worst] < rtol),
        kind="tran",
        max_rel_error=float(errors[worst]),
        worst_at=float(times[worst]),
        points=int(times.size),
        rtol=rtol,
        notes=tuple(notes),
    )

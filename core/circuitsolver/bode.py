"""Bode plot data (design §4.8): numbers only, rendering is the client's job.

The core returns {freq, mag_db, phase_deg, corners, asymptote}; the web
frontend (Plotly) and the LaTeX report (matplotlib, Phase 3) draw it.
Frequencies are angular (rad/s) on a log grid; phase is unwrapped.

The asymptotic (꺾은선) magnitude is anchored at the first grid point and
accumulates ±20·m dB/decade per finite pole/zero above its corner, plus
the always-active slope of poles/zeros at the origin.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

import numpy as np
import sympy as sp

from .analysis import TransferFunction, _root_set
from .errors import CircuitError
from .mna import s

_ORIGIN_TOLERANCE = 1e-12


@dataclass(frozen=True)
class BodeData:
    freq: tuple[float, ...]  # rad/s
    mag_db: tuple[float, ...]
    phase_deg: tuple[float, ...]  # unwrapped
    mag_db_asymptotic: tuple[float, ...]
    corners: tuple[float, ...]  # rad/s, |finite pole/zero| ascending


def _substituted(expr: sp.Expr, numeric_values: Mapping | None) -> sp.Expr:
    substitutions = {}
    for key, value in (numeric_values or {}).items():
        symbol = sp.Symbol(key) if isinstance(key, str) else key
        substitutions[symbol.name] = sp.nsimplify(value, rational=True)
    if substitutions:
        # match by name so assumption-carrying symbols (positive=True) hit too
        expr = expr.subs(
            {sym: substitutions[sym.name] for sym in expr.free_symbols
             if sym.name in substitutions}
        )
    remaining = expr.free_symbols - {s}
    if remaining:
        names = ", ".join(sorted(str(sym) for sym in remaining))
        raise CircuitError(
            f"H(s) still contains symbols ({names}); "
            "provide numeric_values to evaluate the frequency response"
        )
    return expr


def _signed_roots(expr: sp.Expr, sign: int) -> list[tuple[float, int, int]]:
    """(corner |r|, multiplicity, ±1) for each root; |r|≈0 marks the origin."""
    return [
        (abs(complex(root)), multiplicity, sign)
        for root, multiplicity in _root_set(expr).roots
    ]


def bode_data(
    tf: TransferFunction,
    numeric_values: Mapping | None = None,
    points: int = 200,
    freq: Sequence[float] | None = None,
) -> BodeData:
    expr = _substituted(sp.cancel(tf.expr), numeric_values)
    numerator, denominator = sp.fraction(expr)
    roots = _signed_roots(numerator, +1) + _signed_roots(denominator, -1)

    corners = tuple(
        sorted({magnitude for magnitude, _, _ in roots if magnitude > _ORIGIN_TOLERANCE})
    )

    if freq is not None:
        omega = np.asarray(sorted(float(f) for f in freq))
        if omega.size == 0 or omega[0] <= 0:
            raise CircuitError("freq must contain positive rad/s values")
    else:
        if corners:
            low = np.floor(np.log10(corners[0])) - 1
            high = np.ceil(np.log10(corners[-1])) + 1
        else:
            low, high = -2.0, 2.0
        omega = np.logspace(low, high, points)

    h_func = sp.lambdify(s, expr, modules="numpy")
    with np.errstate(all="ignore"):
        values = np.asarray(h_func(1j * omega), dtype=complex)
        if values.ndim == 0:  # constant H(s) → lambdify returns a scalar
            values = np.full(omega.shape, complex(values))
        mag_db = 20.0 * np.log10(np.abs(values))
        phase_deg = np.degrees(np.unwrap(np.angle(values)))

    # 꺾은선 근사: 기준점(첫 격자점) + 각 근의 corner 이후 ±20m dB/dec,
    # 원점 근은 전 구간 기울기.
    log_omega = np.log10(omega)
    asymptote = np.full_like(log_omega, float(mag_db[0]))
    for magnitude, multiplicity, sign in roots:
        slope = 20.0 * multiplicity * sign
        if magnitude <= _ORIGIN_TOLERANCE:
            asymptote += slope * (log_omega - log_omega[0])
        else:
            active = np.maximum(0.0, log_omega - np.log10(magnitude))
            asymptote += slope * active

    return BodeData(
        freq=tuple(float(w) for w in omega),
        mag_db=tuple(float(m) for m in mag_db),
        phase_deg=tuple(float(p) for p in phase_deg),
        mag_db_asymptotic=tuple(float(a) for a in asymptote),
        corners=corners,
    )

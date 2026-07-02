"""Table-driven inverse Laplace transform (design §4.7).

Main path: cancel → apart(s) → per-term table lookup → real closed form.
sympy.inverse_laplace_transform is slow or fails even on rational
functions, so it is only the fallback; if that also fails an
InverseLaplaceError is raised and the caller falls back to numeric
simulation (§4.11). Results are one-sided: valid for t ≥ 0.

Table used (per design):
  c/(s-a)^n            ↔  c·t^(n-1)·e^(at)/(n-1)!
  (bs+c)/((s+α)²+ω²)   ↔  e^(-αt)·(b·cos ωt + ((c-bα)/ω)·sin ωt)
  polynomial in s      ↔  impulses: c·s^k ↔ c·δ⁽ᵏ⁾(t)
Quadratics with positive discriminant are split into two real
exponentials in place; unknown-sign discriminants fall back to SymPy.
"""

from __future__ import annotations

from dataclasses import dataclass

import sympy as sp

from .errors import InverseLaplaceError
from .mna import s

t = sp.Symbol("t", nonnegative=True)


@dataclass(frozen=True)
class TimeResponse:
    expr: sp.Expr  # f(t) for t ≥ 0
    partial_fractions: sp.Expr  # apart() result, recorded for the report
    method: str  # "table" | "sympy_ilt"


def inverse_laplace(expr: sp.Expr) -> TimeResponse:
    expr = sp.cancel(sp.together(expr))
    try:
        decomposed = sp.apart(expr, s)
    except (sp.PolynomialError, NotImplementedError, ZeroDivisionError):
        decomposed = expr

    inverted: list[sp.Expr] = []
    for term in sp.Add.make_args(decomposed):
        piece = _invert_term(term)
        if piece is None:
            return _sympy_fallback(expr, decomposed)
        inverted.append(piece)
    return TimeResponse(
        expr=sp.Add(*inverted), partial_fractions=decomposed, method="table"
    )


def _sympy_fallback(expr: sp.Expr, decomposed: sp.Expr) -> TimeResponse:
    try:
        result = sp.inverse_laplace_transform(expr, s, t)
    except Exception as exc:
        raise InverseLaplaceError(
            "inverse Laplace transform failed on both the table path and "
            "SymPy fallback; only numeric simulation is available"
        ) from exc
    result = result.subs(sp.Heaviside(t), sp.Integer(1))  # one-sided convention
    return TimeResponse(expr=result, partial_fractions=decomposed, method="sympy_ilt")


def _invert_term(term: sp.Expr) -> sp.Expr | None:
    """Invert one partial-fraction term via the table; None → fallback."""
    numerator, denominator = sp.fraction(sp.together(term))

    if not denominator.has(s):  # polynomial part → impulse and derivatives
        return _invert_polynomial(sp.cancel(numerator / denominator))

    coeff, factors = sp.factor_list(denominator)
    s_factors = [(base, exp) for base, exp in factors if base.has(s)]
    if len(s_factors) != 1:
        return None  # apart should have split this; let SymPy try
    for base, exp in factors:
        if not base.has(s):
            coeff *= base**exp
    base, multiplicity = s_factors[0]
    numerator = sp.cancel(numerator / coeff)

    base_poly = sp.Poly(base, s)
    if base_poly.degree() == 1:
        return _invert_linear_power(numerator, base_poly, multiplicity)
    if base_poly.degree() == 2 and multiplicity == 1:
        return _invert_quadratic(numerator, base_poly)
    return None


def _invert_polynomial(ratio: sp.Expr) -> sp.Expr | None:
    if not ratio.has(s):
        return ratio * sp.DiracDelta(t)
    try:
        poly = sp.Poly(ratio, s)
    except sp.PolynomialError:
        return None
    result = sp.Integer(0)
    for order, coeff in enumerate(reversed(poly.all_coeffs())):
        if coeff == 0:
            continue
        result += coeff * (sp.DiracDelta(t, order) if order else sp.DiracDelta(t))
    return result


def _invert_linear_power(numerator: sp.Expr, base_poly: sp.Poly, m: int) -> sp.Expr | None:
    """num/(a1·s + a0)^m → shift to powers of (s - a), a = -a0/a1."""
    a1, a0 = base_poly.all_coeffs()
    a = sp.cancel(-a0 / a1)
    numerator = sp.cancel(numerator / a1**m)

    shift = sp.Dummy("u")
    try:
        shifted = sp.Poly(sp.expand(numerator.subs(s, shift + a)), shift)
    except sp.PolynomialError:
        return None
    if shifted.degree() >= m:
        return None  # improper piece — should have gone to the polynomial part

    result = sp.Integer(0)
    for j, coeff in enumerate(reversed(shifted.all_coeffs())):
        if coeff == 0:
            continue
        power = m - j  # this piece is coeff/(s-a)^power
        result += coeff * t ** (power - 1) * sp.exp(a * t) / sp.factorial(power - 1)
    return result


def _invert_quadratic(numerator: sp.Expr, base_poly: sp.Poly) -> sp.Expr | None:
    """(b·s + c)/(s² + βs + γ), split by the sign of the discriminant."""
    lead = base_poly.LC()
    beta = sp.cancel(base_poly.all_coeffs()[1] / lead)
    gamma = sp.cancel(base_poly.all_coeffs()[2] / lead)
    numerator = sp.cancel(numerator / lead)

    try:
        num_poly = sp.Poly(sp.expand(numerator), s)
    except sp.PolynomialError:
        return None
    if num_poly.degree() > 1:
        return None
    coeffs = num_poly.all_coeffs()
    b, c = (coeffs if len(coeffs) == 2 else (sp.Integer(0), coeffs[0]))

    alpha = sp.cancel(beta / 2)
    discriminant = sp.cancel(alpha**2 - gamma)  # roots: -α ± sqrt(disc)

    if discriminant.is_negative:
        omega = sp.sqrt(gamma - alpha**2)
        return sp.exp(-alpha * t) * (
            b * sp.cos(omega * t) + sp.cancel((c - b * alpha) / omega) * sp.sin(omega * t)
        )
    if discriminant.is_zero:  # double real root at -α
        return b * sp.exp(-alpha * t) + (c - b * alpha) * t * sp.exp(-alpha * t)
    if discriminant.is_positive:
        root = sp.sqrt(discriminant)
        r1, r2 = -alpha + root, -alpha - root
        k1 = sp.cancel((b * r1 + c) / (r1 - r2))
        k2 = sp.cancel((b * r2 + c) / (r2 - r1))
        return k1 * sp.exp(r1 * t) + k2 * sp.exp(r2 * t)
    return None  # discriminant sign undecidable → fallback

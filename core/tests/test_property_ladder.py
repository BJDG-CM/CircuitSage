"""Property-based test (design §8): random resistor ladder networks.

The engine's DC gain must equal the gain computed by repeated
voltage-divider reduction — an independent hand-calculation method.
"""

from fractions import Fraction

import sympy as sp
from hypothesis import given, settings
from hypothesis import strategies as st

from circuitsolver import parse, transfer_function


def _parallel(a: Fraction, b: Fraction) -> Fraction:
    return a * b / (a + b)


def _expected_gain(sections: list[tuple[int, int]]) -> Fraction:
    """Backward reduction: Z_k = Rp_k ∥ (Rs_{k+1} + Z_{k+1}),
    gain = Π Z_k / (Z_k + Rs_k)."""
    n = len(sections)
    z = [Fraction(0)] * n
    for k in reversed(range(n)):
        rp = Fraction(sections[k][1])
        if k == n - 1:
            z[k] = rp
        else:
            rs_next = Fraction(sections[k + 1][0])
            z[k] = _parallel(rp, rs_next + z[k + 1])
    gain = Fraction(1)
    for k, (rs, _) in enumerate(sections):
        gain *= z[k] / (z[k] + Fraction(rs))
    return gain


@settings(max_examples=25, deadline=None)
@given(
    st.lists(
        st.tuples(st.integers(1, 10**4), st.integers(1, 10**4)),
        min_size=1,
        max_size=4,
    )
)
def test_ladder_dc_gain_matches_repeated_division(sections):
    lines = ["Vin in 0 Vi"]
    prev = "in"
    for i, (rs, rp) in enumerate(sections):
        lines.append(f"RS{i} {prev} n{i} {rs}")
        lines.append(f"RP{i} n{i} 0 {rp}")
        prev = f"n{i}"
    lines.append(f".out V({prev}) Vin")

    tf = transfer_function(parse("\n".join(lines) + "\n"))
    expected = _expected_gain(sections)
    assert tf.expr == sp.Rational(expected.numerator, expected.denominator)

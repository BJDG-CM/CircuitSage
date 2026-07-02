"""Pole/zero extraction tests (design §4.6)."""

import sympy as sp

from circuitsolver import parse, transfer_function
from circuitsolver.analysis import RootSet, pole_zero
from circuitsolver.mna import s

R, L, C = sp.symbols("R L C", positive=True)


def _tf(netlist: str):
    return transfer_function(parse(netlist))


class TestSymbolic:
    def test_rc_pole(self):
        result = pole_zero(_tf("Vin in 0 Vi\nR1 in out R\nC1 out 0 C\n.out V(out) Vin\n"))
        assert result.poles.complete is True
        assert len(result.poles.roots) == 1
        root, multiplicity = result.poles.roots[0]
        assert multiplicity == 1
        assert sp.simplify(root + 1 / (R * C)) == 0
        assert result.zeros.roots == ()

    def test_rl_zero_at_origin(self):
        result = pole_zero(_tf("Vin in 0 Vi\nR1 in out R\nL1 out 0 L\n.out V(out) Vin\n"))
        assert result.zeros.values == (0,)
        assert sp.simplify(result.poles.values[0] + R / L) == 0

    def test_rlc_vieta(self):
        # 2차 닫힌형 근은 지저분하므로 Vieta 관계로 검증: 합 = -R/L, 곱 = 1/LC
        result = pole_zero(
            _tf("Vin in 0 Vi\nR1 in n1 R\nL1 n1 out L\nC1 out 0 C\n.out V(out) Vin\n")
        )
        assert result.poles.complete is True
        total = sum(root * mult for root, mult in result.poles.roots)
        product = sp.prod(root**mult for root, mult in result.poles.roots)
        assert sp.simplify(total + R / L) == 0
        assert sp.simplify(product - 1 / (L * C)) == 0

    def test_static_circuit_has_no_poles(self):
        result = pole_zero(_tf("Vin in 0 Vi\nR1 in out 1k\nR2 out 0 2k\n.out V(out) Vin\n"))
        assert result.poles == RootSet(roots=(), complete=True)
        assert result.zeros == RootSet(roots=(), complete=True)


class TestNumeric:
    def test_rc_numeric_pole_is_exact(self):
        result = pole_zero(_tf("Vin in 0 Vi\nR1 in out 1k\nC1 out 0 1u\n.out V(out) Vin\n"))
        assert result.poles.roots == ((-1000, 1),)

    def test_critically_damped_double_pole(self):
        # L=1, C=1, R=2 → 분모 s²+2s+1 = (s+1)², 중근 -1
        result = pole_zero(
            _tf("Vin in 0 Vi\nR1 in n1 2\nL1 n1 out 1\nC1 out 0 1\n.out V(out) Vin\n")
        )
        assert result.poles.roots == ((-1, 2),)

    def test_underdamped_conjugate_pair(self):
        # L=1, C=0.5, R=2 → 분모 ∝ s²+2s+2, 극점 -1±j
        result = pole_zero(
            _tf("Vin in 0 Vi\nR1 in n1 2\nL1 n1 out 1\nC1 out 0 0.5\n.out V(out) Vin\n")
        )
        assert set(result.poles.values) == {-1 + sp.I, -1 - sp.I}
        assert all(sp.re(p) < 0 for p in result.poles.values)

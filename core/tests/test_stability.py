"""Routh–Hurwitz stability tests (design §4.6), including special cases."""

import sympy as sp

from circuitsolver import parse, transfer_function
from circuitsolver.analysis import routh_stability, routh_table, stability
from circuitsolver.mna import s

R, L, C = sp.symbols("R L C", positive=True)
K = sp.Symbol("K")  # 부호 가정 없는 이득


def _tf(netlist: str):
    return transfer_function(parse(netlist))


class TestRouthTable:
    def test_rlc_table_structure(self):
        # D = LCs² + RCs + 1 → 행: [LC, 1], [RC, 0], [1, 0]
        rows, notes, had_zero_row = routh_table(sp.Poly(L * C * s**2 + R * C * s + 1, s))
        assert len(rows) == 3
        assert rows[0] == [L * C, sp.Integer(1)]
        assert rows[1] == [R * C, sp.Integer(0)]
        assert rows[2][0] == 1
        assert notes == [] and had_zero_row is False


class TestVerdicts:
    def test_symbolic_rlc_is_stable_under_positivity(self):
        # R, L, C > 0 가정만으로 첫 열 부호가 전부 판정 → verdict "stable"
        result = routh_stability(sp.Poly(L * C * s**2 + R * C * s + 1, s))
        assert result.verdict == "stable"
        assert result.method == "routh"
        assert result.conditions == ()

    def test_sign_changes_mean_unstable(self):
        result = routh_stability(sp.Poly(s**2 - s + 1, s))
        assert result.verdict == "unstable"

    def test_conditional_verdict_with_unknown_gain(self):
        # D = s² + (3-K)s + 2 → 3-K 부호 미확정 → 조건부
        result = routh_stability(sp.Poly(s**2 + (3 - K) * s + 2, s))
        assert result.verdict == "conditional"
        assert len(result.conditions) == 1
        condition = result.conditions[0]
        assert isinstance(condition, sp.Rel)
        assert sp.simplify(condition.lhs - (3 - K)) == 0

    def test_negative_leading_coefficient_normalized(self):
        result = routh_stability(sp.Poly(-(s**2) - 3 * s - 2, s))
        assert result.verdict == "stable"


class TestSpecialCases:
    def test_zero_pivot_epsilon_substitution(self):
        # 교과서 케이스: s⁴+s³+2s²+2s+3 → s² 행 첫 열 0 → ε 치환, 우반평면 근 2개
        result = routh_stability(sp.Poly(s**4 + s**3 + 2 * s**2 + 2 * s + 3, s))
        assert result.verdict == "unstable"
        assert any("ε" in note for note in result.notes)

    def test_zero_row_gives_marginal(self):
        # D = s² + 1 → s¹ 행 전체 0 → 보조 다항식, jω축 근 → marginal
        result = routh_stability(sp.Poly(s**2 + 1, s))
        assert result.verdict == "marginal"
        assert any("보조 다항식" in note for note in result.notes)


class TestStabilityOfTransferFunctions:
    def test_numeric_rc_uses_numeric_method(self):
        result = stability(_tf("Vin in 0 Vi\nR1 in out 1k\nC1 out 0 1u\n.out V(out) Vin\n"))
        assert result.verdict == "stable"
        assert result.method == "numeric"

    def test_symbolic_rlc_uses_routh(self):
        result = stability(
            _tf("Vin in 0 Vi\nR1 in n1 R\nL1 n1 out L\nC1 out 0 C\n.out V(out) Vin\n")
        )
        assert result.verdict == "stable"
        assert result.method == "routh"
        assert result.routh_table is not None

    def test_static_circuit_is_trivially_stable(self):
        result = stability(_tf("Vin in 0 Vi\nR1 in out 1k\nR2 out 0 2k\n.out V(out) Vin\n"))
        assert result.verdict == "stable"

    def test_lc_tank_is_marginal(self):
        # 무손실 LC: D ∝ LCs² + 1 → jω축 극점 (수치 대입)
        result = stability(_tf("Vin in 0 Vi\nL1 in out 1\nC1 out 0 1\n.out V(out) Vin\n"))
        assert result.verdict == "marginal"

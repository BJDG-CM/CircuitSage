"""Golden-circuit H(s) tests (design §8): engine result == hand-derived theory."""

from pathlib import Path

import pytest
import sympy as sp

from circuitsolver import parse, transfer_function
from circuitsolver.errors import CircuitError
from circuitsolver.mna import s

EXAMPLES_DIR = Path(__file__).resolve().parents[2] / "examples"

R, L, C = sp.symbols("R L C", positive=True)
R1, R2 = sp.symbols("R1 R2", positive=True)


def _example(name: str):
    return parse((EXAMPLES_DIR / name).read_text(encoding="utf-8"))


class TestGoldenCircuits:
    def test_voltage_divider(self):
        tf = transfer_function(_example("voltage_divider.cir"))
        assert sp.simplify(tf.expr - R2 / (R1 + R2)) == 0

    def test_rc_lowpass(self):
        tf = transfer_function(_example("rc_lowpass.cir"))
        assert sp.simplify(tf.expr - 1 / (1 + s * R * C)) == 0

    def test_rl_highpass(self):
        circuit = parse("Vin in 0 Vi\nR1 in out R\nL1 out 0 L\n.out V(out) Vin\n")
        tf = transfer_function(circuit)
        assert sp.simplify(tf.expr - s * L / (R + s * L)) == 0

    def test_rlc_series(self):
        circuit = parse(
            "Vin in 0 Vi\nR1 in n1 R\nL1 n1 out L\nC1 out 0 C\n.out V(out) Vin\n"
        )
        tf = transfer_function(circuit)
        assert sp.simplify(tf.expr - 1 / (L * C * s**2 + R * C * s + 1)) == 0

    def test_wheatstone_bridge(self):
        # 손계산: 23·Va − 3·Vb = 15·Vi, 19·Vb − 4·Va = 10·Vi → Va = 63/85 · Vi
        tf = transfer_function(_example("wheatstone_bridge.cir"))
        assert tf.expr == sp.Rational(63, 85)

    def test_denominator_is_characteristic_polynomial(self):
        tf = transfer_function(_example("rc_lowpass.cir"))
        assert sp.Poly(tf.denominator, s).degree() == 1


class TestTransferFunctionSemantics:
    def test_other_sources_are_switched_off(self):
        # H 정의상 다른 독립 전원(I1)은 꺼진 상태여야 함 → 순수 분배기 1/2
        circuit = parse(
            "V1 a 0 Vi\nR1 a b 1k\nR2 b 0 1k\nI1 0 b 2\n.out V(b) V1\n"
        )
        tf = transfer_function(circuit)
        assert tf.expr == sp.Rational(1, 2)

    def test_current_source_input_gives_transimpedance(self):
        circuit = parse("I1 0 a Ii\nR1 a 0 R1\n.out V(a) I1\n")
        tf = transfer_function(circuit)
        assert sp.simplify(tf.expr - R1) == 0

    def test_numeric_input_source(self):
        circuit = parse("V1 a 0 5\nR1 a b 1k\nR2 b 0 1k\n.out V(b) V1\n")
        tf = transfer_function(circuit)
        assert tf.expr == sp.Rational(1, 2)

    def test_output_at_ground_is_zero(self):
        circuit = parse("V1 a 0 Vi\nR1 a 0 1k\n.out V(0) V1\n")
        assert transfer_function(circuit).expr == 0

    def test_metadata(self):
        tf = transfer_function(_example("rc_lowpass.cir"))
        assert tf.output_node == "out"
        assert tf.input_source == "Vin"


class TestAnalysisErrors:
    def test_missing_out_directive(self):
        with pytest.raises(CircuitError, match=r"\.out"):
            transfer_function(parse("V1 a 0 1\nR1 a 0 1k\n"))

    def test_zero_valued_input_source(self):
        with pytest.raises(CircuitError, match="zero value"):
            transfer_function(parse("V1 a 0 0\nR1 a 0 1k\n.out V(a) V1\n"))

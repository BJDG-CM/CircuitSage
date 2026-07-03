"""Transfer poles vs. internal system modes (P0 regression).

The reduced transfer denominator only shows poles visible from the
selected ports; system_modes() extracts internal natural frequencies
from det A(s) of the MNA system, independently of H(s) cancellation.
"""

import sympy as sp

from circuitsolver import (
    parse,
    pole_zero,
    system_modes,
    transfer_function,
    transfer_stability,
)
from circuitsolver.mna import s

R, L, C = sp.symbols("R L C", positive=True)

# 요구된 회귀 케이스: 출력이 입력 노드 그 자체 → H(s) = 1로 완전 소거되지만
# 내부 RC 모드 -1/(RC)는 여전히 존재한다.
CANCELLED_MODE = "Vin in 0 Vi\nR1 in n R\nC1 n 0 C\n.out V(in) Vin\n"


class TestCancelledInternalMode:
    def test_transfer_function_is_unity(self):
        tf = transfer_function(parse(CANCELLED_MODE))
        assert sp.simplify(tf.expr - 1) == 0
        assert tf.denominator == 1

    def test_transfer_poles_are_empty(self):
        result = pole_zero(transfer_function(parse(CANCELLED_MODE)))
        assert result.poles.roots == ()

    def test_internal_rc_mode_survives(self):
        modes = system_modes(parse(CANCELLED_MODE))
        assert modes.status == "ok"
        assert modes.modes is not None and len(modes.modes.roots) == 1
        mode, multiplicity = modes.modes.roots[0]
        assert multiplicity == 1
        assert sp.simplify(mode + 1 / (R * C)) == 0

    def test_characteristic_is_not_the_transfer_denominator(self):
        circuit = parse(CANCELLED_MODE)
        tf = transfer_function(circuit)
        modes = system_modes(circuit)
        assert tf.denominator == 1
        assert sp.Poly(modes.characteristic, s).degree() == 1

    def test_internal_stability_reported(self):
        modes = system_modes(parse(CANCELLED_MODE))
        assert modes.stability is not None
        assert modes.stability.verdict == "stable"
        # 전달함수 쪽은 상수라 자명하게 stable — 서로 다른 근거의 판정
        assert transfer_stability(transfer_function(parse(CANCELLED_MODE))).verdict == "stable"


class TestAgreementWithoutCancellation:
    def test_rc_lowpass_mode_matches_transfer_pole(self):
        circuit = parse("Vin in 0 Vi\nR1 in out R\nC1 out 0 C\n.out V(out) Vin\n")
        pole = pole_zero(transfer_function(circuit)).poles.values[0]
        modes = system_modes(circuit)
        assert len(modes.modes.roots) == 1
        assert sp.simplify(modes.modes.values[0] - pole) == 0

    def test_rlc_series_characteristic_degree_and_roots(self):
        circuit = parse(
            "Vin in 0 Vi\nR1 in n1 R\nL1 n1 out L\nC1 out 0 C\n.out V(out) Vin\n"
        )
        modes = system_modes(circuit)
        assert sp.Poly(modes.characteristic, s).degree() == 2
        # 전달함수 극점이 특성식의 근이어야 한다
        for pole in pole_zero(transfer_function(circuit)).poles.values:
            assert sp.simplify(modes.characteristic.subs(s, pole)) == 0


class TestDegenerateCases:
    def test_static_circuit_has_no_modes(self):
        modes = system_modes(parse("Vin in 0 Vi\nR1 in out 1k\nR2 out 0 2k\n.out V(out) Vin\n"))
        assert modes.status == "static"
        assert modes.modes.roots == ()
        assert modes.stability.verdict == "stable"

    def test_parallel_capacitors_merge_to_one_mode(self):
        # 병렬 C 두 개는 독립 상태가 하나 → 검출 차수 1이 정당하다
        circuit = parse("Vin a 0 Vi\nR1 a b R\nC1 b 0 C\nC2 b 0 C\n.out V(b) Vin\n")
        modes = system_modes(circuit)
        assert modes.status == "ok"
        assert sp.Poly(modes.characteristic, s).degree() == 1

    def test_note_mentions_formulation_limits(self):
        modes = system_modes(parse(CANCELLED_MODE))
        assert "차수" in modes.note

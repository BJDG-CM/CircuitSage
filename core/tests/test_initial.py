"""Initial-condition equivalent source tests (design §4.4)."""

from pathlib import Path

import sympy as sp

from circuitsolver import parse
from circuitsolver.analysis import solve_node_voltages
from circuitsolver.circuit import ComponentType
from circuitsolver.initial import (
    expand_initial_conditions,
    zero_input_circuit,
    zero_state_circuit,
)
from circuitsolver.mna import s

EXAMPLES_DIR = Path(__file__).resolve().parents[2] / "examples"

R, L, C = sp.symbols("R L C", positive=True)
v0, i0 = sp.symbols("v0 i0", real=True)


class TestExpansion:
    def test_capacitor_parallel_equivalent(self):
        expansion = expand_initial_conditions(parse("C1 a 0 C IC=v0\nR1 a 0 R\n"))
        assert [c.name for c in expansion.circuit.components] == ["C1", "Iic_C1", "R1"]
        source = expansion.circuit.component("Iic_C1")
        assert source.ctype is ComponentType.CURRENT_SOURCE
        assert source.nodes == ("0", "a")  # C·v0를 n+ 쪽으로 주입 (n- → n+)
        assert source.value == C * v0
        assert expansion.circuit.component("C1").ic is None
        assert expansion.ic_sources == ("Iic_C1",)

    def test_inductor_parallel_equivalent(self):
        expansion = expand_initial_conditions(parse("L1 a 0 L IC=i0\nR1 a 0 R\n"))
        source = expansion.circuit.component("Iic_L1")
        assert source.nodes == ("a", "0")  # i0/s가 원래 전류 방향(n+ → n-)으로
        assert source.value == i0 / s

    def test_circuit_without_ic_unchanged(self):
        circuit = parse("R1 a 0 R\nV1 a 0 1\n")
        expansion = expand_initial_conditions(circuit)
        assert expansion.circuit == circuit
        assert expansion.ic_sources == ()


class TestGoldenICResponses:
    def test_rc_discharge(self):
        # 이론값: v_a(s) = v0·RC/(RCs + 1)  ↔  v0·e^{-t/RC}
        voltages = solve_node_voltages(parse("C1 a 0 C IC=v0\nR1 a 0 R\n"))
        assert sp.simplify(voltages["a"] - R * C * v0 / (R * C * s + 1)) == 0

    def test_rl_current_decay(self):
        # 이론값: v_a(s) = -i0·LR/(Ls + R)  ↔  -i0·R·e^{-tR/L}
        voltages = solve_node_voltages(parse("L1 a 0 L IC=i0\nR1 a 0 R\n"))
        assert sp.simplify(voltages["a"] + i0 * L * R / (L * s + R)) == 0


class TestSuperposition:
    def _rlc(self):
        text = (EXAMPLES_DIR / "rlc_series_ic.cir").read_text(encoding="utf-8")
        return parse(text)

    def test_full_response_equals_zero_state_plus_zero_input(self):
        circuit = self._rlc()
        full = solve_node_voltages(circuit)["out"]
        zs = solve_node_voltages(zero_state_circuit(circuit))["out"]
        zi = solve_node_voltages(zero_input_circuit(circuit))["out"]
        assert sp.simplify(full - zs - zi) == 0

    def test_zero_input_response_has_no_input_symbol(self):
        circuit = self._rlc()
        zi = solve_node_voltages(zero_input_circuit(circuit))["out"]
        assert sp.Symbol("Vi") not in zi.free_symbols

    def test_zero_state_response_has_no_ic_symbols(self):
        circuit = self._rlc()
        zs = solve_node_voltages(zero_state_circuit(circuit))["out"]
        assert sp.Symbol("Vi") in zs.free_symbols
        # zero-state는 입력에 비례해야 함: zs/Vi에는 s와 소자 기호만 남는다
        assert sp.cancel(zs / sp.Symbol("Vi")).free_symbols <= {s, R, C}

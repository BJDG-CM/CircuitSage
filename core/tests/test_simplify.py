"""단계별 회로 단순화 테스트 (design §4.9)."""

import sympy as sp

from circuitsolver import parse
from circuitsolver.circuit import ComponentType
from circuitsolver.simplify import simplify_circuit

R1, R2 = sp.symbols("R1 R2", positive=True)
C1, C2 = sp.symbols("C1 C2", positive=True)


class TestParallel:
    def test_parallel_resistors_merge(self):
        result = simplify_circuit(parse("Vin a 0 Vi\nR1 a 0 R1\nR2 a 0 R2\n.out V(a) Vin\n"))
        assert len(result.steps) == 1
        assert result.steps[0].rule == "parallel"
        merged = next(c for c in result.circuit.components if c.name == "Req1")
        assert sp.simplify(merged.value - R1 * R2 / (R1 + R2)) == 0
        assert result.verified is True

    def test_parallel_capacitors_add(self):
        result = simplify_circuit(
            parse("Vin a 0 Vi\nRl a 0 1k\nC1 a 0 C1\nC2 a 0 C2\n.out V(a) Vin\n")
        )
        merged = next(c for c in result.circuit.components if c.ctype is ComponentType.CAPACITOR)
        assert sp.simplify(merged.value - (C1 + C2)) == 0


class TestSeries:
    def test_series_resistors_remove_internal_node(self):
        result = simplify_circuit(
            parse("Vin in 0 Vi\nR1 in m R1\nR2 m out R2\nR3 out 0 1k\n.out V(out) Vin\n")
        )
        assert any(step.rule == "series" for step in result.steps)
        assert "m" not in result.circuit.nodes
        merged = next(c for c in result.circuit.components if c.name.startswith("Req"))
        assert sp.simplify(merged.value - (R1 + R2)) == 0
        assert result.verified is True

    def test_series_capacitors_product_over_sum(self):
        result = simplify_circuit(
            parse("Vin in 0 Vi\nC1 in m C1\nC2 m out C2\nR1 out 0 1k\n.out V(out) Vin\n")
        )
        merged = next(c for c in result.circuit.components if c.ctype is ComponentType.CAPACITOR)
        assert sp.simplify(merged.value - C1 * C2 / (C1 + C2)) == 0

    def test_output_node_is_protected(self):
        # in—R1—out—R2—0에서 out이 출력이면 직렬 결합 금지
        result = simplify_circuit(parse("Vin in 0 Vi\nR1 in out R1\nR2 out 0 R2\n.out V(out) Vin\n"))
        assert result.steps == ()

    def test_ic_component_is_protected(self):
        result = simplify_circuit(
            parse("Vin in 0 Vi\nC1 in m 1u IC=5\nC2 m out 1u\nR1 out 0 1k\n.out V(out) Vin\n")
        )
        assert result.steps == ()


class TestSourceTransform:
    def test_auxiliary_source_becomes_norton(self):
        netlist = (
            "Vin in 0 Vi\nR0 in a 1k\n"
            "Vaux x 0 5\nRx x a 100\n"
            ".out V(a) Vin\n"
        )
        result = simplify_circuit(parse(netlist))
        assert any(step.rule == "source_transform" for step in result.steps)
        names = {c.name for c in result.circuit.components}
        assert "Vaux" not in names and any(n.startswith("Ieq") for n in names)
        assert result.verified is True

    def test_input_source_is_never_transformed(self):
        result = simplify_circuit(
            parse("Vin x 0 Vi\nR1 x a 100\nR2 a 0 200\n.out V(a) Vin\n")
        )
        assert all(step.rule != "source_transform" for step in result.steps)
        assert any(c.name == "Vin" for c in result.circuit.components)


class TestFixedPoint:
    def test_wheatstone_bridge_cannot_simplify(self):
        netlist = (
            "Vin top 0 Vi\nR1 top a 100\nR2 top b 200\n"
            "R3 a 0 300\nR4 b 0 400\nR5 a b 500\n.out V(a) Vin\n"
        )
        result = simplify_circuit(parse(netlist))
        assert result.steps == ()
        assert result.verified is None

    def test_ladder_reduces_through_multiple_steps(self):
        # in—R—m1—R—m2—R—out—R—0 : 직렬 3회까지 가능해야 함 (out 보호)
        netlist = (
            "Vin in 0 Vi\nRa in m1 100\nRb m1 m2 200\nRc m2 out 300\nRd out 0 400\n"
            ".out V(out) Vin\n"
        )
        result = simplify_circuit(parse(netlist))
        assert len(result.steps) == 2  # (Ra+Rb)+Rc → Req; Rd는 out-0로 보호적 잔존
        assert result.verified is True

"""Topology validation tests: connectivity, singular patterns, planarity (§4.2)."""

import pytest

from circuitsolver import parse, validate_topology
from circuitsolver.errors import (
    CurrentSourceCutsetError,
    FloatingNodeError,
    GroundMissingError,
    VoltageSourceLoopError,
)

WHEATSTONE_BRIDGE = """\
* 휘트스톤 브리지 — 평면, 직병렬 단순화 불가
Vin top 0 Vi
R1  top a 100
R2  top b 200
R3  a   0 300
R4  b   0 400
R5  a   b 500
.out V(a) Vin
.end
"""

# K5: 5개 노드(접지 포함) 완전 그래프 저항망 — 비평면
K5_NETWORK = "\n".join(
    f"R{i}{j} {i} {j} 1k"
    for idx, (i, j) in enumerate(
        (str(a) if a else "0", str(b) if b else "0")
        for a in range(5)
        for b in range(a + 1, 5)
    )
) + "\nV1 1 0 1\n"


class TestConnectivity:
    def test_ground_required(self):
        with pytest.raises(GroundMissingError):
            validate_topology(parse("R1 a b 1k\nV1 a b 1\n"))

    def test_floating_nodes_detected(self):
        with pytest.raises(FloatingNodeError) as exc_info:
            validate_topology(parse("V1 a 0 1\nR1 a 0 1k\nR2 b c 1k\n"))
        assert exc_info.value.nodes == ["b", "c"]

    def test_connected_circuit_passes(self):
        report = validate_topology(parse(WHEATSTONE_BRIDGE))
        assert report.node_count == 4


class TestSingularTopologies:
    def test_parallel_voltage_sources_form_loop(self):
        with pytest.raises(VoltageSourceLoopError):
            validate_topology(parse("V1 a 0 5\nV2 a 0 5\nR1 a 0 1k\n"))

    def test_series_voltage_source_ring_forms_loop(self):
        netlist = "V1 a 0 1\nV2 b a 2\nV3 0 b 3\nR1 a 0 1k\n"
        with pytest.raises(VoltageSourceLoopError):
            validate_topology(parse(netlist))

    def test_two_voltage_sources_without_loop_ok(self):
        report = validate_topology(parse("V1 a 0 1\nV2 b 0 2\nR1 a b 1k\n"))
        assert report.node_count == 3

    def test_current_source_cutset_detected(self):
        # 노드 m은 전류원으로만 연결 → KCL 과잉 결정
        with pytest.raises(CurrentSourceCutsetError):
            validate_topology(parse("I1 0 m 1\nI2 m 0 2\nR1 0 m2 1k\nR2 m2 0 1k\n"))

    def test_current_source_with_parallel_resistor_ok(self):
        report = validate_topology(parse("I1 0 a 1\nR1 a 0 1k\n"))
        assert report.node_count == 2


class TestPlanarity:
    def test_wheatstone_bridge_is_planar(self):
        assert validate_topology(parse(WHEATSTONE_BRIDGE)).is_planar is True

    def test_k5_resistor_network_is_not_planar(self):
        assert validate_topology(parse(K5_NETWORK)).is_planar is False

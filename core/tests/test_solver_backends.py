"""솔버 백엔드(lusolve/cramer) 정합성·선택·진단 테스트 (P1)."""

import pytest
import sympy as sp

from circuitsolver import parse
from circuitsolver.analysis import (
    transfer_function,
    transfer_function_with_diagnostics,
)
from circuitsolver.errors import CircuitError, SingularMatrixError
from circuitsolver.mna import s

R, L, C = sp.symbols("R L C", positive=True)
R1, R2 = sp.symbols("R1 R2", positive=True)

GOLDEN = [
    ("Vin in 0 Vi\nR1 in out R1\nR2 out 0 R2\n.out V(out) Vin\n", R2 / (R1 + R2)),
    ("Vin in 0 Vi\nR1 in out R\nC1 out 0 C\n.out V(out) Vin\n", 1 / (1 + s * R * C)),
    (
        "Vin in 0 Vi\nR1 in n1 R\nL1 n1 out L\nC1 out 0 C\n.out V(out) Vin\n",
        1 / (L * C * s**2 + R * C * s + 1),
    ),
    (
        "Vin top 0 Vi\nR1 top a 100\nR2 top b 200\nR3 a 0 300\nR4 b 0 400\n"
        "R5 a b 500\n.out V(a) Vin\n",
        sp.Rational(63, 85),
    ),
]

UNIQUE_LADDER = (
    "Vin in 0 Vi\n"
    "RS1 in n1 Rs1\nRP1 n1 0 Rp1\n"
    "RS2 n1 n2 Rs2\nRP2 n2 0 Rp2\n"
    "RS3 n2 n3 Rs3\nRP3 n3 0 Rp3\n"
    "RS4 n3 n4 Rs4\nRP4 n4 0 Rp4\n"
    ".out V(n4) Vin\n"
)


class TestBackendCorrectness:
    @pytest.mark.parametrize("backend", ["lusolve", "cramer"])
    @pytest.mark.parametrize(("netlist", "expected"), GOLDEN)
    def test_backends_match_theory(self, backend, netlist, expected):
        tf = transfer_function(parse(netlist), backend=backend)
        assert sp.simplify(tf.expr - expected) == 0

    def test_cramer_detects_singular_matrix(self):
        from circuitsolver.analysis import _output_cramer
        from circuitsolver.mna import MNASystem

        system = MNASystem(
            A=sp.Matrix([[1, 1], [1, 1]]),  # 특이 행렬
            z=sp.Matrix([[1], [0]]),
            unknowns=(),
            nodes=(),
            node_index={},
            current_index={},
            records=(),
        )
        with pytest.raises(SingularMatrixError):
            _output_cramer(system, 0)


class TestBackendSelection:
    def test_auto_picks_lusolve_for_few_symbols(self):
        circuit = parse("Vin in 0 Vi\nR1 in out R\nC1 out 0 C\n.out V(out) Vin\n")
        _, diagnostics = transfer_function_with_diagnostics(circuit)
        assert diagnostics.symbol_count == 3  # R, C, Vi
        assert diagnostics.backend == "lusolve"

    def test_auto_picks_cramer_for_many_symbols(self):
        _, diagnostics = transfer_function_with_diagnostics(parse(UNIQUE_LADDER))
        assert diagnostics.symbol_count == 9  # Rs1..4, Rp1..4, Vi
        assert diagnostics.backend == "cramer"

    def test_auto_picks_cramer_for_symbolic_bridge(self):
        # 벤치마크의 결정적 케이스: 기호 6개 브리지는 LU 대비 ~38배 빠르다
        bridge = (
            "Vin top 0 Vi\nR1 top a Ra\nR2 top b Rb\nR3 a 0 Rc\nR4 b 0 Rd\n"
            "R5 a b Re\n.out V(a) Vin\n"
        )
        _, diagnostics = transfer_function_with_diagnostics(parse(bridge))
        assert diagnostics.symbol_count == 6
        assert diagnostics.backend == "cramer"

    def test_auto_picks_cramer_for_multi_vsource_symbols(self):
        # 벤치마크의 최악 케이스 회귀: 기호 5개 + 전압원 가지 3개에서 LU의
        # 최종 cancel이 수십 분대로 발산했다 — auto는 cramer를 선택해야 한다
        netlist = (
            "Vin a 0 Vi\nVb b 0 2\nVc c 0 3\n"
            "R1 a m R1\nR2 b m R2\nR3 c m R3\nR4 m 0 R4\n.out V(m) Vin\n"
        )
        _, diagnostics = transfer_function_with_diagnostics(parse(netlist))
        assert diagnostics.symbol_count == 5
        assert diagnostics.backend == "cramer"

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("CIRCUITSAGE_SOLVER", "cramer")
        circuit = parse("Vin in 0 Vi\nR1 in out R\nC1 out 0 C\n.out V(out) Vin\n")
        _, diagnostics = transfer_function_with_diagnostics(circuit)
        assert diagnostics.backend == "cramer"

    def test_explicit_argument_beats_env(self, monkeypatch):
        monkeypatch.setenv("CIRCUITSAGE_SOLVER", "cramer")
        circuit = parse("Vin in 0 Vi\nR1 in out R\nC1 out 0 C\n.out V(out) Vin\n")
        _, diagnostics = transfer_function_with_diagnostics(circuit, backend="lusolve")
        assert diagnostics.backend == "lusolve"

    def test_unknown_backend_rejected(self, monkeypatch):
        monkeypatch.setenv("CIRCUITSAGE_SOLVER", "quantum")
        circuit = parse("Vin in 0 Vi\nR1 in out R\nC1 out 0 C\n.out V(out) Vin\n")
        with pytest.raises(CircuitError, match="unknown solver backend"):
            transfer_function_with_diagnostics(circuit)


class TestDiagnostics:
    def test_diagnostics_shape(self):
        circuit = parse("Vin in 0 Vi\nR1 in out R\nC1 out 0 C\n.out V(out) Vin\n")
        _, diagnostics = transfer_function_with_diagnostics(circuit)
        assert diagnostics.matrix_dimension == 3
        assert set(diagnostics.stage_timings) == {
            "topology",
            "assemble",
            "solve",
            "normalize",
        }
        assert all(value >= 0 for value in diagnostics.stage_timings.values())
        assert diagnostics.fallback_used is False

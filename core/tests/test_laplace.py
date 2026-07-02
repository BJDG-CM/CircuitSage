"""Inverse Laplace and time-response tests (design §4.7, M2 완료 기준).

RLC 직렬 3케이스(과감쇠/임계/부족감쇠)의 step 응답 닫힌형이 손으로 유도한
이론값과 일치해야 한다.
"""

import sympy as sp

from circuitsolver import parse, transfer_function
from circuitsolver.analysis import impulse_response, step_response
from circuitsolver.laplace import inverse_laplace, t
from circuitsolver.mna import s

R, C = sp.symbols("R C", positive=True)
R1, R2 = sp.symbols("R1 R2", positive=True)


def _tf(netlist: str):
    return transfer_function(parse(netlist))


class TestRLCStepResponses:
    """직렬 RLC, 출력은 커패시터 전압. H = 1/(LCs² + RCs + 1)."""

    def test_overdamped(self):
        # L=1, C=1/2, R=3 → H = 2/((s+1)(s+2)),  y = 1 - 2e^-t + e^-2t
        tf = _tf("Vin in 0 Vi\nR1 in n1 3\nL1 n1 out 1\nC1 out 0 0.5\n.out V(out) Vin\n")
        response = step_response(tf)
        expected = 1 - 2 * sp.exp(-t) + sp.exp(-2 * t)
        assert sp.simplify(response.expr - expected) == 0
        assert response.method == "table"

    def test_critically_damped(self):
        # L=1, C=1, R=2 → H = 1/(s+1)²,  y = 1 - e^-t - t·e^-t
        tf = _tf("Vin in 0 Vi\nR1 in n1 2\nL1 n1 out 1\nC1 out 0 1\n.out V(out) Vin\n")
        response = step_response(tf)
        expected = 1 - sp.exp(-t) - t * sp.exp(-t)
        assert sp.simplify(response.expr - expected) == 0

    def test_underdamped(self):
        # L=1, C=1/2, R=2 → H = 2/(s²+2s+2),  y = 1 - e^-t·cos t - e^-t·sin t
        tf = _tf("Vin in 0 Vi\nR1 in n1 2\nL1 n1 out 1\nC1 out 0 0.5\n.out V(out) Vin\n")
        response = step_response(tf)
        expected = 1 - sp.exp(-t) * sp.cos(t) - sp.exp(-t) * sp.sin(t)
        assert sp.simplify(response.expr - expected) == 0

    def test_underdamped_impulse_is_damped_sine(self):
        tf = _tf("Vin in 0 Vi\nR1 in n1 2\nL1 n1 out 1\nC1 out 0 0.5\n.out V(out) Vin\n")
        response = impulse_response(tf)
        assert sp.simplify(response.expr - 2 * sp.exp(-t) * sp.sin(t)) == 0


class TestSymbolicFirstOrder:
    def test_rc_impulse(self):
        tf = _tf("Vin in 0 Vi\nR1 in out R\nC1 out 0 C\n.out V(out) Vin\n")
        response = impulse_response(tf)
        expected = sp.exp(-t / (R * C)) / (R * C)
        assert sp.simplify(response.expr - expected) == 0
        assert response.method == "table"

    def test_rc_step(self):
        tf = _tf("Vin in 0 Vi\nR1 in out R\nC1 out 0 C\n.out V(out) Vin\n")
        response = step_response(tf)
        assert sp.simplify(response.expr - (1 - sp.exp(-t / (R * C)))) == 0

    def test_rl_impulse_has_dirac_delta(self):
        # H = sL/(R+sL)는 improper → h = δ(t) - (R/L)e^{-Rt/L}
        L = sp.Symbol("L", positive=True)
        tf = _tf("Vin in 0 Vi\nR1 in out R\nL1 out 0 L\n.out V(out) Vin\n")
        response = impulse_response(tf)
        expected = sp.DiracDelta(t) - (R / L) * sp.exp(-R * t / L)
        assert sp.simplify(response.expr - expected) == 0


class TestEdgeCases:
    def test_constant_transfer_gives_scaled_impulse(self):
        tf = _tf("Vin in 0 Vi\nR1 in out R1\nR2 out 0 R2\n.out V(out) Vin\n")
        response = impulse_response(tf)
        assert sp.simplify(response.expr - R2 / (R1 + R2) * sp.DiracDelta(t)) == 0

    def test_partial_fractions_are_recorded(self):
        # 노트(FR-3/§4.7)용: apart 결과가 s-domain 그대로 보존되어야 함
        expr = 2 / (s * (s + 1) * (s + 2))
        response = inverse_laplace(expr)
        recorded = response.partial_fractions
        assert sp.simplify(recorded - (1 / s - 2 / (s + 1) + 1 / (s + 2))) == 0

    def test_repeated_pole(self):
        response = inverse_laplace(1 / (s + 3) ** 3)
        assert sp.simplify(response.expr - t**2 * sp.exp(-3 * t) / 2) == 0

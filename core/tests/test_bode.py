"""Bode data tests (design §4.8)."""

import math

import pytest

from circuitsolver import parse, transfer_function
from circuitsolver.bode import bode_data
from circuitsolver.errors import CircuitError

RC_NUMERIC = "Vin in 0 Vi\nR1 in out 1k\nC1 out 0 1u\n.out V(out) Vin\n"
RC_SYMBOLIC = "Vin in 0 Vi\nR1 in out R\nC1 out 0 C\n.out V(out) Vin\n"


def _tf(netlist: str):
    return transfer_function(parse(netlist))


class TestRCLowpass:
    def test_corner_and_landmarks(self):
        # 1k·1u → corner 1000 rad/s; -3 dB, -45° at corner
        data = bode_data(_tf(RC_NUMERIC), freq=(10.0, 1000.0, 100000.0))
        assert data.corners == (1000.0,)
        assert data.mag_db[0] == pytest.approx(0.0, abs=0.01)
        assert data.mag_db[1] == pytest.approx(-3.0103, abs=0.001)
        assert data.phase_deg[1] == pytest.approx(-45.0, abs=0.01)
        assert data.phase_deg[2] == pytest.approx(-89.4, abs=0.2)

    def test_asymptote_slope_minus_20db_per_decade(self):
        data = bode_data(_tf(RC_NUMERIC), freq=(10.0, 1000.0, 100000.0))
        # corner에서 2 decade 위 → 근사 -40 dB (기준점 오차 ≤ 0.1)
        assert data.mag_db_asymptotic[2] == pytest.approx(-40.0, abs=0.1)
        # corner 아래에서는 평탄
        assert data.mag_db_asymptotic[0] == pytest.approx(data.mag_db[0], abs=1e-9)

    def test_auto_grid_spans_corner(self):
        data = bode_data(_tf(RC_NUMERIC), points=50)
        assert len(data.freq) == 50
        assert data.freq[0] < 1000.0 < data.freq[-1]


class TestSymbolicSubstitution:
    def test_symbols_require_numeric_values(self):
        with pytest.raises(CircuitError, match="numeric_values"):
            bode_data(_tf(RC_SYMBOLIC))

    def test_substitution_matches_numeric_circuit(self):
        symbolic = bode_data(
            _tf(RC_SYMBOLIC),
            numeric_values={"R": 1000, "C": 1e-6},
            freq=(10.0, 1000.0, 100000.0),
        )
        numeric = bode_data(_tf(RC_NUMERIC), freq=(10.0, 1000.0, 100000.0))
        for a, b in zip(symbolic.mag_db, numeric.mag_db):
            assert a == pytest.approx(b, abs=1e-9)


class TestEdgeCases:
    def test_constant_transfer_is_flat(self):
        data = bode_data(
            _tf("Vin in 0 Vi\nR1 in out 1k\nR2 out 0 2k\n.out V(out) Vin\n"),
            freq=(1.0, 100.0),
        )
        expected = 20 * math.log10(2 / 3)
        assert data.corners == ()
        assert all(m == pytest.approx(expected, abs=1e-9) for m in data.mag_db)

    def test_rl_highpass_origin_zero(self):
        # H = sL/(R+sL), L=1, R=1000 → corner 1000, 저역 기울기 +20 dB/dec
        data = bode_data(
            _tf("Vin in 0 Vi\nR1 in out 1k\nL1 out 0 1\n.out V(out) Vin\n"),
            freq=(10.0, 100.0, 1000.0),
        )
        assert data.corners == (1000.0,)
        rise = data.mag_db_asymptotic[1] - data.mag_db_asymptotic[0]
        assert rise == pytest.approx(20.0, abs=0.1)

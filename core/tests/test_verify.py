"""ngspice cross-verification tests (design §4.11).

Deck construction is always tested; actual ngspice runs are skipped when
the binary is missing (CI installs ngspice via apt and runs them).
"""

from pathlib import Path

import pytest

from circuitsolver import parse
from circuitsolver.verify import ac_deck, find_ngspice, tran_deck, verify_ac, verify_tran

EXAMPLES_DIR = Path(__file__).resolve().parents[2] / "examples"

RC_NUMERIC = "Vin in 0 5\nR1 in out 1k\nC1 out 0 1u\n.out V(out) Vin\n"
RLC_VALUES = {"R": 100, "C": 1e-6, "Vi": 1}

needs_ngspice = pytest.mark.skipif(
    find_ngspice() is None, reason="ngspice executable not on PATH"
)


def _rlc():
    return parse((EXAMPLES_DIR / "rlc_series_ic.cir").read_text(encoding="utf-8"))


class TestDeckConstruction:
    def test_ac_deck_shape(self):
        deck = ac_deck(parse(RC_NUMERIC), None, 1.0, 1e6, 20)
        assert "Vin in 0 DC 0 AC 1" in deck
        assert "ac dec 20 1 1e+06" in deck
        assert "wrdata out_re.txt hre" in deck
        assert deck.rstrip().endswith(".end")

    def test_tran_deck_keeps_inline_ics(self):
        deck = tran_deck(_rlc(), RLC_VALUES, 1e-6, 1e-3)
        assert "L1 n1 out 0.002 ic=0.1" in deck
        assert "C1 out 0 1e-06 ic=5" in deck
        assert "tran 1e-06 0.001 uic" in deck


@needs_ngspice
class TestAgainstNgspice:
    def test_rc_ac(self):
        report = verify_ac(parse(RC_NUMERIC))
        assert report.passed, f"max rel error {report.max_rel_error} at {report.worst_at} Hz"
        assert report.kind == "ac"

    def test_rc_symbolic_ac_with_values(self):
        circuit = parse("Vin in 0 Vi\nR1 in out R\nC1 out 0 C\n.out V(out) Vin\n")
        report = verify_ac(circuit, numeric_values={"R": 1000, "C": 1e-6, "Vi": 1})
        assert report.passed

    def test_rc_step_tran(self):
        report = verify_tran(parse(RC_NUMERIC))
        assert report.passed, f"max rel error {report.max_rel_error} at t={report.worst_at}"

    def test_rlc_with_ics_tran(self):
        report = verify_tran(_rlc(), numeric_values=RLC_VALUES)
        assert report.passed, f"max rel error {report.max_rel_error} at t={report.worst_at}"

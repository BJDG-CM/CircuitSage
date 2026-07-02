"""ngspice translation layer tests (design §4.1, ADR-6)."""

from pathlib import Path

import pytest

from circuitsolver import parse
from circuitsolver.errors import CircuitError
from circuitsolver.spice_io import element_lines, full_netlist

EXAMPLES_DIR = Path(__file__).resolve().parents[2] / "examples"

RLC_VALUES = {"R": 100, "C": 1e-6, "Vi": 1}


def _rlc():
    return parse((EXAMPLES_DIR / "rlc_series_ic.cir").read_text(encoding="utf-8"))


class TestElementLines:
    def test_symbolic_values_substituted(self):
        lines = element_lines(_rlc(), numeric_values=RLC_VALUES)
        assert lines == [
            "Vin in 0 1",
            "R1 in n1 100",
            "L1 n1 out 0.002 ic=0.1",
            "C1 out 0 1e-06 ic=5",
        ]

    def test_out_directive_is_not_emitted(self):
        deck = full_netlist(_rlc(), [".op"], numeric_values=RLC_VALUES)
        assert ".out" not in deck

    def test_missing_numeric_value_raises(self):
        with pytest.raises(CircuitError, match="numeric_values"):
            element_lines(_rlc(), numeric_values={"R": 100})

    def test_source_spec_override_for_ac(self):
        lines = element_lines(
            _rlc(), numeric_values=RLC_VALUES, source_specs={"Vin": "DC 0 AC 1"}
        )
        assert lines[0] == "Vin in 0 DC 0 AC 1"

    def test_unknown_source_spec_rejected(self):
        with pytest.raises(CircuitError, match="unknown components"):
            element_lines(_rlc(), numeric_values=RLC_VALUES, source_specs={"Vx": "AC 1"})


class TestFullNetlist:
    def test_deck_shape(self):
        deck = full_netlist(
            _rlc(),
            [".ac dec 10 1 1meg", ".print ac v(out)"],
            numeric_values=RLC_VALUES,
        )
        lines = deck.strip().splitlines()
        assert lines[0].startswith("* ")
        assert lines[-1] == ".end"
        assert ".ac dec 10 1 1meg" in lines

    def test_numeric_circuit_needs_no_values(self):
        circuit = parse("Vin a 0 5\nR1 a 0 1k\n.out V(a) Vin\n")
        assert element_lines(circuit) == ["Vin a 0 5", "R1 a 0 1000"]

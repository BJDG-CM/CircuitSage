"""Every netlist under examples/ must parse and pass topology validation."""

from pathlib import Path

import pytest

from circuitsolver import parse, validate_topology

EXAMPLES_DIR = Path(__file__).resolve().parents[2] / "examples"
EXAMPLE_FILES = sorted(EXAMPLES_DIR.glob("*.cir"))


def test_examples_directory_is_not_empty():
    assert EXAMPLE_FILES, f"no .cir files found in {EXAMPLES_DIR}"


@pytest.mark.parametrize("path", EXAMPLE_FILES, ids=lambda p: p.stem)
def test_example_parses_and_validates(path):
    circuit = parse(path.read_text(encoding="utf-8"))
    report = validate_topology(circuit)
    assert report.node_count >= 2

"""Complexity preflight report tests."""

from circuitsolver import measure_complexity, parse

RLC = (
    "Vin in 0 Vi\nR1 in n1 R\nL1 n1 out 2m IC=0.1\nC1 out 0 C IC=5\n"
    ".out V(out) Vin\n"
)


def test_rlc_report_dimensions():
    report = measure_complexity(parse(RLC), RLC)
    assert report.component_count == 4
    assert report.node_count == 3  # in, n1, out
    assert report.vsource_branch_count == 1
    assert report.mna_dimension == 4  # 3 nodes + 1 branch current
    assert report.reactive_count == 2
    assert report.estimated_dynamic_order == 2
    assert report.symbol_count == 3  # R, C, Vi (numeric ICs excluded)
    assert report.netlist_bytes == len(RLC.encode("utf-8"))


def test_numeric_circuit_has_no_symbols():
    netlist = "V1 a 0 5\nR1 a b 1k\nR2 b 0 2k\n"
    report = measure_complexity(parse(netlist), netlist)
    assert report.symbol_count == 0
    assert report.reactive_count == 0
    assert report.estimated_dynamic_order == 0


def test_symbolic_ics_are_counted():
    netlist = "L1 a 0 L IC=i0\nR1 a 0 R\n"
    report = measure_complexity(parse(netlist), netlist)
    assert report.symbol_count == 3  # L, i0, R


def test_as_dict_round_trip():
    netlist = "V1 a 0 1\nR1 a 0 1k\n"
    payload = measure_complexity(parse(netlist), netlist).as_dict()
    assert payload["component_count"] == 2
    assert set(payload) >= {
        "component_count",
        "node_count",
        "mna_dimension",
        "symbol_count",
        "reactive_count",
        "estimated_dynamic_order",
        "vsource_branch_count",
        "netlist_bytes",
    }

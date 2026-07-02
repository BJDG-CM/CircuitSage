"""Parser tests: SPICE subset + symbolic values + IC= + .out (design §4.1)."""

import pytest
import sympy as sp

from circuitsolver import ComponentType, parse
from circuitsolver.errors import ParseError

VOLTAGE_DIVIDER = """\
* 저항 전압분배기
Vin  in  0    Vi
R1   in  out  1k
R2   out 0    2k
.out V(out) Vin
.end
"""

RLC_SERIES_IC = """\
* RLC 직렬 회로, 커패시터 전압이 출력 (설계 문서 §4.1 예제)
Vin  in   0    Vi          ; 기호 입력원
R1   in   n1   R           ; 기호 값
L1   n1   out  2m  IC=0.1  ; 2 mH, i_L(0-) = 0.1 A
C1   out  0    C   IC=5    ; 기호 값, v_C(0-) = 5 V
.out V(out) Vin
.end
"""


class TestElements:
    def test_voltage_divider(self):
        circuit = parse(VOLTAGE_DIVIDER)
        assert [c.name for c in circuit.components] == ["Vin", "R1", "R2"]
        r1 = circuit.component("R1")
        assert r1.ctype is ComponentType.RESISTOR
        assert r1.nodes == ("in", "out")
        assert r1.value == sp.Integer(1000)
        assert circuit.nodes == ["in", "0", "out"]
        assert circuit.output.node == "out"
        assert circuit.output.source == "Vin"

    def test_design_doc_rlc_example(self):
        circuit = parse(RLC_SERIES_IC)
        l1 = circuit.component("L1")
        assert l1.value == sp.Rational(1, 500)  # 2m = 2e-3
        assert l1.ic == sp.Rational(1, 10)
        c1 = circuit.component("C1")
        assert c1.value == sp.Symbol("C", positive=True)
        assert c1.ic == sp.Integer(5)
        vin = circuit.component("Vin")
        assert vin.value == sp.Symbol("Vi")

    def test_component_lookup_is_case_insensitive(self):
        circuit = parse(VOLTAGE_DIVIDER)
        assert circuit.component("r1").name == "R1"

    def test_comments_and_blank_lines_ignored(self):
        circuit = parse(
            "* title comment\n\nR1 a 0 1k ; inline comment\n; full-line comment\nV1 a 0 1\n"
        )
        assert len(circuit.components) == 2

    def test_content_after_end_ignored(self):
        circuit = parse("R1 a 0 1k\nV1 a 0 1\n.end\ngarbage that would not parse\n")
        assert len(circuit.components) == 2


class TestValues:
    @pytest.mark.parametrize(
        ("token", "expected"),
        [
            ("2m", sp.Rational(1, 500)),
            ("2M", sp.Rational(1, 500)),  # SPICE is case-insensitive: M = milli
            ("1.5k", sp.Integer(1500)),
            ("100n", sp.Rational(1, 10**7)),
            ("3Meg", sp.Integer(3 * 10**6)),
            ("3MEG", sp.Integer(3 * 10**6)),
            ("2.2u", sp.Rational(11, 5 * 10**6)),
            ("47p", sp.Rational(47, 10**12)),
            ("4mH", sp.Rational(1, 250)),  # trailing unit letters ignored
            ("1e-3", sp.Rational(1, 1000)),
            (".5", sp.Rational(1, 2)),
            ("10", sp.Integer(10)),
        ],
    )
    def test_numeric_suffixes(self, token, expected):
        circuit = parse(f"R1 a 0 {token}\nV1 a 0 1\n")
        assert circuit.component("R1").value == expected

    def test_symbolic_rlc_values_are_positive_symbols(self):
        circuit = parse("R1 a 0 R\nV1 a 0 1\n")
        value = circuit.component("R1").value
        assert value.is_positive is True

    def test_symbolic_source_value_has_no_assumptions(self):
        circuit = parse("V1 a 0 Vi\nR1 a 0 1k\n")
        value = circuit.component("V1").value
        assert value.is_positive is None

    def test_unknown_suffix_rejected(self):
        with pytest.raises(ParseError, match="suffix"):
            parse("R1 a 0 2x7\nV1 a 0 1\n")


class TestErrors:
    def test_error_carries_line_number(self):
        with pytest.raises(ParseError) as exc_info:
            parse("V1 a 0 1\nR1 a 0 1k\nD1 a 0 1\n")
        assert exc_info.value.line_no == 3
        assert "line 3" in str(exc_info.value)

    def test_unsupported_component_type(self):
        with pytest.raises(ParseError, match="unsupported component type 'D'"):
            parse("D1 a 0 1\n")

    def test_missing_fields(self):
        with pytest.raises(ParseError, match="expected"):
            parse("R1 a 0\n")

    def test_too_many_fields(self):
        with pytest.raises(ParseError, match="too many"):
            parse("R1 a 0 1k extra stuff\n")

    def test_same_node_both_terminals(self):
        with pytest.raises(ParseError, match="both terminals"):
            parse("R1 a a 1k\n")

    def test_duplicate_name_case_insensitive(self):
        with pytest.raises(ParseError, match="duplicate component name"):
            parse("R1 a 0 1k\nr1 a 0 2k\n")

    def test_ic_only_on_reactive_elements(self):
        with pytest.raises(ParseError, match="IC="):
            parse("R1 a 0 1k IC=5\n")

    def test_ic_allowed_on_inductor_and_capacitor(self):
        circuit = parse("L1 a 0 1m IC=0.5\nC1 a 0 1u IC=iv0\nV1 a 0 1\n")
        assert circuit.component("L1").ic == sp.Rational(1, 2)
        assert circuit.component("C1").ic == sp.Symbol("iv0", real=True)

    def test_empty_netlist(self):
        with pytest.raises(ParseError, match="no components"):
            parse("* nothing here\n")

    def test_unknown_directive(self):
        with pytest.raises(ParseError, match="unknown directive"):
            parse("R1 a 0 1k\n.foo bar\n")


class TestOutDirective:
    def test_duplicate_out(self):
        with pytest.raises(ParseError, match="duplicate .out"):
            parse("V1 a 0 1\nR1 a 0 1k\n.out V(a) V1\n.out V(a) V1\n")

    def test_malformed_output_expression(self):
        with pytest.raises(ParseError, match=r"V\(node\)"):
            parse("V1 a 0 1\nR1 a 0 1k\n.out a V1\n")

    def test_unknown_output_node(self):
        with pytest.raises(ParseError, match="output node 'zz'"):
            parse("V1 a 0 1\nR1 a 0 1k\n.out V(zz) V1\n")

    def test_unknown_input_source(self):
        with pytest.raises(ParseError, match="input source 'Vx' not found"):
            parse("V1 a 0 1\nR1 a 0 1k\n.out V(a) Vx\n")

    def test_input_must_be_independent_source(self):
        with pytest.raises(ParseError, match="not an independent source"):
            parse("V1 a 0 1\nR1 a 0 1k\n.out V(a) R1\n")

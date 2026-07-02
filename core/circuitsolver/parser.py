"""Netlist parser: SPICE subset + two extensions (design doc §4.1).

Extensions over plain SPICE:
  * symbolic values — an identifier in a value position becomes a SymPy
    Symbol (positive=True for R/L/C, per §4.6);
  * inline initial conditions — ``IC=`` on L and C lines;
  * ``.out V(node) source`` — transfer-function spec (deliberately not
    ``.tf``, which SPICE reserves for DC transfer functions, ADR-6).

Errors are reported as ParseError with the 1-based line number.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from fractions import Fraction

import sympy as sp

from .circuit import (
    SOURCE_TYPES,
    Circuit,
    Component,
    ComponentType,
    OutputSpec,
)
from .errors import ParseError

_NUMBER_RE = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?")
_IDENT_RE = re.compile(r"[A-Za-z_]\w*\Z")
_IC_RE = re.compile(r"IC=(.+)\Z", re.IGNORECASE)
_OUT_NODE_RE = re.compile(r"[Vv]\((.+)\)\Z")

# SPICE scale suffixes (case-insensitive; "meg" must be matched before "m").
_SUFFIXES: dict[str, sp.Rational] = {
    "k": sp.Rational(10) ** 3,
    "m": sp.Rational(1, 10**3),
    "u": sp.Rational(1, 10**6),
    "n": sp.Rational(1, 10**9),
    "p": sp.Rational(1, 10**12),
}
_MEG = sp.Integer(10) ** 6

_ELEMENT_TYPES = {t.value: t for t in ComponentType}


def _parse_value(token: str, line_no: int, raw: str, kind: str) -> sp.Expr:
    """Parse a value token into an exact SymPy expression.

    ``kind`` selects symbol assumptions: "component" → positive=True,
    "ic" → real=True, "source" → no assumptions (s-domain input signal).
    """
    match = _NUMBER_RE.match(token)
    if match:
        rest = token[match.end():]
        multiplier: sp.Expr = sp.Integer(1)
        if rest:
            rest_lower = rest.lower()
            if rest_lower.startswith("meg"):
                multiplier, trailing = _MEG, rest_lower[3:]
            elif rest_lower[0] in _SUFFIXES:
                multiplier, trailing = _SUFFIXES[rest_lower[0]], rest_lower[1:]
            else:
                raise ParseError(f"unknown value suffix '{rest}'", line_no, raw)
            # SPICE convention: letters after the suffix are a unit, ignored.
            if trailing and not trailing.isalpha():
                raise ParseError(f"malformed value '{token}'", line_no, raw)
        try:
            number = sp.Rational(Fraction(Decimal(match.group(0))))
        except InvalidOperation as exc:  # pragma: no cover - regex guards this
            raise ParseError(f"malformed number '{token}'", line_no, raw) from exc
        return number * multiplier

    if _IDENT_RE.match(token):
        if kind == "component":
            return sp.Symbol(token, positive=True)
        if kind == "ic":
            return sp.Symbol(token, real=True)
        return sp.Symbol(token)

    raise ParseError(f"invalid value '{token}'", line_no, raw)


def _parse_element(tokens: list[str], line_no: int, raw: str) -> Component:
    name = tokens[0]
    type_letter = name[0].upper()
    ctype = _ELEMENT_TYPES.get(type_letter)
    if ctype is None:
        raise ParseError(
            f"unsupported component type '{name[0]}' (supported: R, L, C, V, I)",
            line_no,
            raw,
        )
    if len(tokens) < 4:
        raise ParseError(
            f"expected '{type_letter}name n+ n- value', got {len(tokens)} fields",
            line_no,
            raw,
        )

    n_plus, n_minus = tokens[1], tokens[2]
    if n_plus == n_minus:
        raise ParseError(f"both terminals of {name} on node '{n_plus}'", line_no, raw)

    kind = "source" if ctype in SOURCE_TYPES else "component"
    value = _parse_value(tokens[3], line_no, raw, kind)

    ic: sp.Expr | None = None
    if len(tokens) == 5:
        ic_match = _IC_RE.match(tokens[4])
        if not ic_match:
            raise ParseError(f"unexpected token '{tokens[4]}'", line_no, raw)
        if ctype not in (ComponentType.INDUCTOR, ComponentType.CAPACITOR):
            raise ParseError(
                f"IC= is only valid on inductors and capacitors, not {name}",
                line_no,
                raw,
            )
        ic = _parse_value(ic_match.group(1), line_no, raw, "ic")
    elif len(tokens) > 5:
        raise ParseError(f"too many fields ({len(tokens)})", line_no, raw)

    return Component(name=name, ctype=ctype, nodes=(n_plus, n_minus), value=value, ic=ic)


def parse(text: str) -> Circuit:
    """Parse a netlist string into a Circuit.

    Raises ParseError (with 1-based line number) on the first problem found.
    Topology checks (ground, floating nodes, singular patterns) live in
    graph.validate_topology, not here.
    """
    components: list[Component] = []
    names_seen: set[str] = set()
    output: OutputSpec | None = None
    output_pos: tuple[int, str] | None = None

    for line_no, raw in enumerate(text.splitlines(), start=1):
        line = raw.split(";", 1)[0].strip()
        if not line or line.startswith("*"):
            continue

        tokens = line.split()

        if line.startswith("."):
            directive = tokens[0].lower()
            if directive == ".end":
                break
            if directive == ".out":
                if output is not None:
                    raise ParseError("duplicate .out directive", line_no, raw)
                if len(tokens) != 3:
                    raise ParseError(
                        "expected '.out V(node) source'", line_no, raw
                    )
                node_match = _OUT_NODE_RE.match(tokens[1])
                if not node_match:
                    raise ParseError(
                        f"expected V(node) as output, got '{tokens[1]}'", line_no, raw
                    )
                output = OutputSpec(node=node_match.group(1), source=tokens[2])
                output_pos = (line_no, raw)
                continue
            raise ParseError(f"unknown directive '{tokens[0]}'", line_no, raw)

        component = _parse_element(tokens, line_no, raw)
        key = component.name.upper()
        if key in names_seen:
            raise ParseError(f"duplicate component name '{component.name}'", line_no, raw)
        names_seen.add(key)
        components.append(component)

    if not components:
        raise ParseError("netlist contains no components")

    circuit = Circuit(components=tuple(components), output=output)

    if output is not None:
        assert output_pos is not None
        out_line_no, out_raw = output_pos
        if output.node not in circuit.nodes:
            raise ParseError(
                f"output node '{output.node}' does not appear in the netlist",
                out_line_no,
                out_raw,
            )
        try:
            source = circuit.component(output.source)
        except KeyError:
            raise ParseError(
                f"input source '{output.source}' not found", out_line_no, out_raw
            ) from None
        if source.ctype not in SOURCE_TYPES:
            raise ParseError(
                f"'{output.source}' is not an independent source", out_line_no, out_raw
            )

    return circuit

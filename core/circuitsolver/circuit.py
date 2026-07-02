"""Circuit data model: immutable components and the parsed circuit."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import sympy as sp


class ComponentType(Enum):
    RESISTOR = "R"
    INDUCTOR = "L"
    CAPACITOR = "C"
    VOLTAGE_SOURCE = "V"
    CURRENT_SOURCE = "I"


SOURCE_TYPES = frozenset({ComponentType.VOLTAGE_SOURCE, ComponentType.CURRENT_SOURCE})
REACTIVE_TYPES = frozenset({ComponentType.INDUCTOR, ComponentType.CAPACITOR})


@dataclass(frozen=True)
class Component:
    """A two-terminal element. ``nodes`` is (n+, n-) in netlist order.

    ``value`` is a SymPy expression: an exact Rational for numeric input,
    or a Symbol (positive=True for R/L/C) for symbolic input.
    ``ic`` is the t=0⁻ initial condition (L: current, C: voltage), or None.
    """

    name: str
    ctype: ComponentType
    nodes: tuple[str, str]
    value: sp.Expr
    ic: sp.Expr | None = None


@dataclass(frozen=True)
class OutputSpec:
    """Transfer-function specification from the ``.out`` directive:
    H(s) = V(node) / source."""

    node: str
    source: str


@dataclass(frozen=True)
class Circuit:
    components: tuple[Component, ...]
    output: OutputSpec | None = None

    @property
    def nodes(self) -> list[str]:
        """Node names in order of first appearance in the netlist."""
        seen: list[str] = []
        for comp in self.components:
            for node in comp.nodes:
                if node not in seen:
                    seen.append(node)
        return seen

    def component(self, name: str) -> Component:
        """Case-insensitive lookup by component name."""
        target = name.upper()
        for comp in self.components:
            if comp.name.upper() == target:
                return comp
        raise KeyError(name)

    def by_type(self, ctype: ComponentType) -> list[Component]:
        return [comp for comp in self.components if comp.ctype is ctype]

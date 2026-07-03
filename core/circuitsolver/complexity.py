"""Preflight complexity measurement for symbolic solving.

The report is a *safety guard and diagnostic aid*, not a runtime
prediction: symbolic solve cost depends on expression structure in ways
that no small formula captures honestly. Callers (the API layer) compare
these measured values against configured limits before dispatching the
expensive pipeline.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from .circuit import REACTIVE_TYPES, Circuit, ComponentType
from .graph import GROUND
from .mna import s


@dataclass(frozen=True)
class ComplexityReport:
    component_count: int
    node_count: int  # non-ground nodes
    mna_dimension: int  # node voltages + voltage-source branch currents
    symbol_count: int  # independent symbolic parameters (values + ICs)
    reactive_count: int
    estimated_dynamic_order: int  # upper bound; degenerate topologies can be lower
    vsource_branch_count: int
    netlist_bytes: int

    def as_dict(self) -> dict:
        return asdict(self)


def measure_complexity(circuit: Circuit, netlist_text: str = "") -> ComplexityReport:
    non_ground = [node for node in circuit.nodes if node != GROUND]
    vsources = circuit.by_type(ComponentType.VOLTAGE_SOURCE)
    reactive = [comp for comp in circuit.components if comp.ctype in REACTIVE_TYPES]

    symbols = set()
    for comp in circuit.components:
        symbols |= comp.value.free_symbols
        if comp.ic is not None:
            symbols |= comp.ic.free_symbols
    symbols.discard(s)

    return ComplexityReport(
        component_count=len(circuit.components),
        node_count=len(non_ground),
        mna_dimension=len(non_ground) + len(vsources),
        symbol_count=len(symbols),
        reactive_count=len(reactive),
        estimated_dynamic_order=len(reactive),
        vsource_branch_count=len(vsources),
        netlist_bytes=len(netlist_text.encode("utf-8")),
    )

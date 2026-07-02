"""Symbolic MNA assembly via element stamps (design §4.3).

Builds A(s)·x = z(s) with x = [node voltages | Group-2 branch currents].
Each element contributes locally through its stamp; every contribution is
recorded as a StampEntry delta (ADR-7) so the report layer can replay the
derivation without storing full-matrix snapshots.

This module knows nothing about initial conditions (§4.4): circuits with
IC= must be transformed by initial.py (Phase 2) before assembly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator

import sympy as sp

from .circuit import Circuit, Component, ComponentType
from .graph import GROUND

s = sp.Symbol("s")

_PASSIVE = (ComponentType.RESISTOR, ComponentType.INDUCTOR, ComponentType.CAPACITOR)


@dataclass(frozen=True)
class StampEntry:
    """One additive contribution: A[row, col] += term, or z[row] += term."""

    target: str  # "A" or "z"
    row: int
    col: int | None  # None for z entries
    term: sp.Expr


@dataclass(frozen=True)
class StampRecord:
    """All contributions of a single component, in stamp order."""

    component: str
    entries: tuple[StampEntry, ...]


@dataclass(eq=False)
class MNASystem:
    A: sp.Matrix
    z: sp.Matrix
    unknowns: tuple[sp.Symbol, ...]
    nodes: tuple[str, ...]  # non-ground nodes, in unknown order
    node_index: dict[str, int]
    current_index: dict[str, int]  # Group-2 component name -> row/col
    records: tuple[StampRecord, ...]


def _admittance(comp: Component) -> sp.Expr:
    if comp.ctype is ComponentType.RESISTOR:
        return 1 / comp.value
    if comp.ctype is ComponentType.INDUCTOR:
        return 1 / (s * comp.value)
    return s * comp.value  # capacitor


def _stamp_entries(
    comp: Component,
    node_index: dict[str, int],
    current_index: dict[str, int],
) -> Iterator[tuple[str, int | None, int | None, sp.Expr]]:
    """Yield (target, row, col, term) contributions; ground indices are None."""
    p = node_index.get(comp.nodes[0])
    m = node_index.get(comp.nodes[1])

    if comp.ctype in _PASSIVE:
        y = _admittance(comp)
        yield ("A", p, p, y)
        yield ("A", m, m, y)
        yield ("A", p, m, -y)
        yield ("A", m, p, -y)
    elif comp.ctype is ComponentType.VOLTAGE_SOURCE:
        k = current_index[comp.name]
        yield ("A", p, k, sp.Integer(1))
        yield ("A", m, k, sp.Integer(-1))
        yield ("A", k, p, sp.Integer(1))
        yield ("A", k, m, sp.Integer(-1))
        yield ("z", k, None, comp.value)
    elif comp.ctype is ComponentType.CURRENT_SOURCE:
        # SPICE convention: positive current flows n+ → n- through the source.
        yield ("z", p, None, -comp.value)
        yield ("z", m, None, comp.value)


def assemble(circuit: Circuit) -> MNASystem:
    """Assemble the symbolic MNA system in one pass over the components."""
    nodes = tuple(node for node in circuit.nodes if node != GROUND)
    node_index = {node: i for i, node in enumerate(nodes)}
    group2 = circuit.by_type(ComponentType.VOLTAGE_SOURCE)
    current_index = {comp.name: len(nodes) + i for i, comp in enumerate(group2)}

    size = len(nodes) + len(group2)
    A = sp.zeros(size, size)
    z = sp.zeros(size, 1)
    records: list[StampRecord] = []

    for comp in circuit.components:
        applied: list[StampEntry] = []
        for target, row, col, term in _stamp_entries(comp, node_index, current_index):
            if row is None or (target == "A" and col is None):
                continue  # contribution lands on the grounded reference — dropped
            if target == "A":
                A[row, col] += term
            else:
                z[row, 0] += term
            applied.append(StampEntry(target, row, col if target == "A" else None, term))
        records.append(StampRecord(comp.name, tuple(applied)))

    unknowns = tuple(
        [sp.Symbol(f"v_{node}") for node in nodes]
        + [sp.Symbol(f"i_{comp.name}") for comp in group2]
    )
    return MNASystem(
        A=A,
        z=z,
        unknowns=unknowns,
        nodes=nodes,
        node_index=node_index,
        current_index=current_index,
        records=tuple(records),
    )

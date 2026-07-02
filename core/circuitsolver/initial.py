"""Initial conditions → s-domain equivalent sources (design §4.4).

The MNA module never sees an IC: this module rewrites the circuit so that
every charged L/C becomes the element itself (admittance only) plus an
equivalent source, and MNA assembles the result unchanged.

Default form is the parallel current source — it adds no Group-2 unknowns:
  inductor  i_L(0⁻)=i0 : 1/(sL) in parallel with source i0/s, n+ → n-
  capacitor v_C(0⁻)=v0 : sC     in parallel with source C·v0, n- → n+
(the series voltage-source duals are derived in the report, Phase 3).

Sign check (capacitor): I(s) = C(sV − v0) = sC·V − C·v0, so the branch
draws C·v0 less current from n+ — equivalently a source injecting C·v0
into n+. Inductor: I(s) = V/(sL) + i0/s continues i0 in its own direction.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import sympy as sp

from .circuit import SOURCE_TYPES, Circuit, Component, ComponentType
from .errors import CircuitError
from .mna import s

IC_SOURCE_PREFIX = "Iic_"


@dataclass(frozen=True)
class ICExpansion:
    circuit: Circuit  # ICs stripped, equivalent sources inserted
    ic_sources: tuple[str, ...]  # names of the injected sources


def expand_initial_conditions(circuit: Circuit) -> ICExpansion:
    existing = {comp.name.upper() for comp in circuit.components}
    components: list[Component] = []
    injected: list[str] = []

    for comp in circuit.components:
        if comp.ic is None:
            components.append(comp)
            continue

        components.append(replace(comp, ic=None))
        name = f"{IC_SOURCE_PREFIX}{comp.name}"
        if name.upper() in existing:
            raise CircuitError(
                f"cannot inject IC source '{name}': the name is already taken"
            )
        if comp.ctype is ComponentType.INDUCTOR:
            nodes, value = comp.nodes, comp.ic / s
        else:  # capacitor (parser only allows IC= on L and C)
            nodes, value = (comp.nodes[1], comp.nodes[0]), comp.value * comp.ic
        components.append(
            Component(name=name, ctype=ComponentType.CURRENT_SOURCE, nodes=nodes, value=value)
        )
        injected.append(name)

    return ICExpansion(
        circuit=Circuit(components=tuple(components), output=circuit.output),
        ic_sources=tuple(injected),
    )


def zero_state_circuit(circuit: Circuit) -> Circuit:
    """Inputs on, initial conditions off (ICs simply dropped)."""
    return Circuit(
        components=tuple(replace(comp, ic=None) for comp in circuit.components),
        output=circuit.output,
    )


def zero_input_circuit(circuit: Circuit) -> Circuit:
    """Initial-condition sources on, every original independent source off."""
    expansion = expand_initial_conditions(circuit)
    components = tuple(
        replace(comp, value=sp.Integer(0))
        if comp.ctype in SOURCE_TYPES and comp.name not in expansion.ic_sources
        else comp
        for comp in expansion.circuit.components
    )
    return Circuit(components=components, output=circuit.output)

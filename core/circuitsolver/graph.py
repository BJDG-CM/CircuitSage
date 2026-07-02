"""Circuit graph checks: connectivity, singular topologies, planarity (§4.2).

The circuit is a networkx MultiGraph (parallel elements between the same
node pair are common, so a plain Graph would silently drop them).
"""

from __future__ import annotations

from dataclasses import dataclass

import networkx as nx

from .circuit import Circuit, ComponentType
from .errors import (
    CurrentSourceCutsetError,
    FloatingNodeError,
    GroundMissingError,
    VoltageSourceLoopError,
)

GROUND = "0"


def build_multigraph(circuit: Circuit) -> nx.MultiGraph:
    graph = nx.MultiGraph()
    for comp in circuit.components:
        graph.add_edge(*comp.nodes, key=comp.name, component=comp)
    return graph


@dataclass(frozen=True)
class TopologyReport:
    node_count: int
    is_planar: bool


def validate_topology(circuit: Circuit) -> TopologyReport:
    """Validate the circuit graph, raising TopologyError subclasses.

    Checks, in order: ground presence, reachability from ground,
    voltage-source loops, current-source cut-sets. Returns planarity
    (Boyer–Myrvold via networkx) for the report and mesh-analysis remark.
    """
    graph = build_multigraph(circuit)

    if GROUND not in graph:
        raise GroundMissingError("ground node '0' does not appear in the netlist")

    reachable = nx.node_connected_component(graph, GROUND)
    floating = sorted(set(graph) - reachable)
    if floating:
        raise FloatingNodeError(floating)

    # Voltage-source loop: in the subgraph of voltage-source edges, a cycle
    # exists iff edges > nodes - components (forest bound; holds for
    # parallel sources too since MultiGraph keeps both edges).
    v_sources = circuit.by_type(ComponentType.VOLTAGE_SOURCE)
    v_sub = nx.MultiGraph()
    for comp in v_sources:
        v_sub.add_edge(*comp.nodes, key=comp.name)
    if v_sub.number_of_edges() > v_sub.number_of_nodes() - nx.number_connected_components(v_sub):
        names = ", ".join(comp.name for comp in v_sources)
        raise VoltageSourceLoopError(
            f"voltage sources form a loop (KVL overdetermined): {names}"
        )

    # Current-source cut-set: removing current-source edges must not split
    # the graph; if it does, KCL on the separated part is overdetermined.
    without_i = nx.MultiGraph()
    without_i.add_nodes_from(graph.nodes)
    without_i.add_edges_from(
        comp.nodes for comp in circuit.components
        if comp.ctype is not ComponentType.CURRENT_SOURCE
    )
    if nx.number_connected_components(without_i) > nx.number_connected_components(graph):
        raise CurrentSourceCutsetError(
            "current sources form a cut-set (KCL overdetermined): "
            "some nodes connect to the rest of the circuit only through current sources"
        )

    is_planar, _ = nx.check_planarity(nx.Graph(graph))
    return TopologyReport(node_count=graph.number_of_nodes(), is_planar=is_planar)

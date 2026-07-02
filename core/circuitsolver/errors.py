"""Exception hierarchy for circuitsolver.

Every error carries a stable ``code`` so the API layer (Phase 4) can map
exceptions to HTTP responses without inspecting messages.
"""

from __future__ import annotations


class CircuitError(Exception):
    """Base class for all circuitsolver errors."""

    code = "CIRCUIT_ERROR"


class ParseError(CircuitError):
    """Netlist syntax or semantic error, tied to a source line."""

    code = "PARSE_ERROR"

    def __init__(self, message: str, line_no: int | None = None, line: str = "") -> None:
        prefix = f"line {line_no}: " if line_no is not None else ""
        super().__init__(prefix + message)
        self.line_no = line_no
        self.line = line


class TopologyError(CircuitError):
    """Structural problem detected on the circuit graph."""

    code = "TOPOLOGY_ERROR"


class GroundMissingError(TopologyError):
    code = "FLOATING_NODE"


class FloatingNodeError(TopologyError):
    code = "FLOATING_NODE"

    def __init__(self, nodes: list[str]) -> None:
        super().__init__(f"nodes unreachable from ground: {', '.join(nodes)}")
        self.nodes = list(nodes)


class SingularMatrixError(CircuitError):
    """The assembled MNA matrix is not invertible."""

    code = "SINGULAR_MATRIX"


class VoltageSourceLoopError(TopologyError):
    """A loop made only of voltage sources makes the MNA matrix singular."""

    code = "SINGULAR_MATRIX"


class CurrentSourceCutsetError(TopologyError):
    """A cut-set made only of current sources overdetermines KCL."""

    code = "SINGULAR_MATRIX"

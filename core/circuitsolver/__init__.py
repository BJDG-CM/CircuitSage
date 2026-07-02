"""circuitsolver — symbolic linear circuit analysis core.

Pure-Python package: no web framework dependencies. See the design doc
(Symbolic-Circuit-Solver-설계문서.md) at the repository root.
"""

from .analysis import TransferFunction, transfer_function
from .circuit import Circuit, Component, ComponentType, OutputSpec
from .errors import (
    CircuitError,
    CurrentSourceCutsetError,
    FloatingNodeError,
    GroundMissingError,
    ParseError,
    SingularMatrixError,
    TopologyError,
    VoltageSourceLoopError,
)
from .graph import TopologyReport, build_multigraph, validate_topology
from .mna import MNASystem, StampEntry, StampRecord, assemble, s
from .parser import parse

__version__ = "0.1.0"

__all__ = [
    "Circuit",
    "CircuitError",
    "Component",
    "ComponentType",
    "CurrentSourceCutsetError",
    "FloatingNodeError",
    "GroundMissingError",
    "MNASystem",
    "OutputSpec",
    "ParseError",
    "SingularMatrixError",
    "StampEntry",
    "StampRecord",
    "TopologyError",
    "TopologyReport",
    "TransferFunction",
    "VoltageSourceLoopError",
    "assemble",
    "build_multigraph",
    "parse",
    "s",
    "transfer_function",
    "validate_topology",
]

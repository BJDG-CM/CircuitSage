"""circuitsolver — symbolic linear circuit analysis core.

Pure-Python package: no web framework dependencies. See the design doc
(Symbolic-Circuit-Solver-설계문서.md) at the repository root.
"""

from .circuit import Circuit, Component, ComponentType, OutputSpec
from .errors import (
    CircuitError,
    CurrentSourceCutsetError,
    FloatingNodeError,
    GroundMissingError,
    ParseError,
    TopologyError,
    VoltageSourceLoopError,
)
from .graph import TopologyReport, build_multigraph, validate_topology
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
    "OutputSpec",
    "ParseError",
    "TopologyError",
    "TopologyReport",
    "VoltageSourceLoopError",
    "build_multigraph",
    "parse",
    "validate_topology",
]

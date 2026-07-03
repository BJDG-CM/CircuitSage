"""circuitsolver — symbolic linear circuit analysis core.

Pure-Python package: no web framework dependencies. See the design doc
(Symbolic-Circuit-Solver-설계문서.md) at the repository root.
"""

from .analysis import (
    PoleZeroResult,
    RootSet,
    StabilityResult,
    SystemModes,
    TransferFunction,
    impulse_response,
    pole_zero,
    routh_stability,
    routh_table,
    solve_node_voltages,
    stability,
    step_response,
    system_modes,
    transfer_function,
    transfer_stability,
)
from .bode import BodeData, bode_data
from .circuit import Circuit, Component, ComponentType, OutputSpec
from .complexity import ComplexityReport, measure_complexity
from .errors import (
    CircuitError,
    CurrentSourceCutsetError,
    FloatingNodeError,
    GroundMissingError,
    InverseLaplaceError,
    ParseError,
    SingularMatrixError,
    TopologyError,
    VerificationError,
    VoltageSourceLoopError,
)
from .graph import TopologyReport, build_multigraph, validate_topology
from .initial import (
    ICExpansion,
    expand_initial_conditions,
    zero_input_circuit,
    zero_state_circuit,
)
from .laplace import TimeResponse, inverse_laplace, t
from .mna import MNASystem, StampEntry, StampRecord, assemble, s
from .parser import parse
from .spice_io import element_lines, full_netlist, numeric_circuit, substitute_numeric
from .verify import VerificationReport, find_ngspice, verify_ac, verify_tran

__version__ = "0.1.0"

__all__ = [
    "BodeData",
    "Circuit",
    "CircuitError",
    "ComplexityReport",
    "measure_complexity",
    "Component",
    "ComponentType",
    "CurrentSourceCutsetError",
    "FloatingNodeError",
    "GroundMissingError",
    "ICExpansion",
    "InverseLaplaceError",
    "MNASystem",
    "OutputSpec",
    "ParseError",
    "PoleZeroResult",
    "RootSet",
    "SingularMatrixError",
    "StabilityResult",
    "StampEntry",
    "StampRecord",
    "SystemModes",
    "system_modes",
    "transfer_stability",
    "TimeResponse",
    "TopologyError",
    "TopologyReport",
    "TransferFunction",
    "VerificationError",
    "VerificationReport",
    "VoltageSourceLoopError",
    "assemble",
    "bode_data",
    "build_multigraph",
    "element_lines",
    "expand_initial_conditions",
    "find_ngspice",
    "full_netlist",
    "impulse_response",
    "inverse_laplace",
    "numeric_circuit",
    "parse",
    "pole_zero",
    "routh_stability",
    "routh_table",
    "s",
    "solve_node_voltages",
    "stability",
    "step_response",
    "substitute_numeric",
    "t",
    "transfer_function",
    "validate_topology",
    "verify_ac",
    "verify_tran",
    "zero_input_circuit",
    "zero_state_circuit",
]

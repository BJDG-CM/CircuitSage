"""Complexity preflight: measured values vs configured limits.

Runs *before* the expensive symbolic pipeline. The netlist byte check
runs even before parsing so oversized inputs are rejected cheaply.
"""

from __future__ import annotations

from circuitsolver.complexity import ComplexityReport

from .config import Settings
from .errors import ComplexityLimitError


def enforce_netlist_size(netlist: str, settings: Settings) -> None:
    limit = settings.limits.max_netlist_bytes
    if limit is None:
        return
    size = len(netlist.encode("utf-8"))
    if size > limit:
        raise ComplexityLimitError(
            "NETLIST_TOO_LARGE",
            f"netlist size {size} bytes exceeds the configured limit "
            f"CIRCUITSAGE_MAX_NETLIST_BYTES={limit}",
            measured=size,
            limit=limit,
        )


def enforce_complexity(report: ComplexityReport, settings: Settings) -> None:
    checks = (
        (
            report.component_count,
            settings.limits.max_components,
            "TOO_MANY_COMPONENTS",
            "component count",
            "CIRCUITSAGE_MAX_COMPONENTS",
        ),
        (
            report.mna_dimension,
            settings.limits.max_mna_dimension,
            "MATRIX_TOO_LARGE",
            "MNA matrix dimension",
            "CIRCUITSAGE_MAX_MNA_DIMENSION",
        ),
        (
            report.symbol_count,
            settings.limits.max_symbols,
            "TOO_MANY_SYMBOLS",
            "symbolic parameter count",
            "CIRCUITSAGE_MAX_SYMBOLS",
        ),
    )
    for measured, limit, code, label, env_name in checks:
        if limit is not None and measured > limit:
            raise ComplexityLimitError(
                code,
                f"{label} {measured} exceeds the configured limit {env_name}={limit}",
                measured=measured,
                limit=limit,
            )

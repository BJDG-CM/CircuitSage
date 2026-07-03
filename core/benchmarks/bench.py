"""Reproducible symbolic-solve benchmark.

Usage:
    python core/benchmarks/bench.py            # full table (markdown)
    python core/benchmarks/bench.py --quick    # smaller ladder sizes

Per case it times: parse, topology validation, MNA assembly, the LUsolve
output path, the Cramer/Berkowitz output path, rational normalization
(cancel) for each, pole/zero extraction, inverse Laplace (step) where
meaningful, and the end-to-end auto-backend transfer_function.

Numbers are machine-dependent; a recorded run with interpretation lives
in docs/benchmarks.md. This is a measurement tool, not a performance
guarantee.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import sympy as sp  # noqa: E402

from circuitsolver import assemble, parse, pole_zero, step_response, validate_topology  # noqa: E402
from circuitsolver.analysis import (  # noqa: E402
    TransferFunction,
    _output_cramer,
    _output_lusolve,
    transfer_function_with_diagnostics,
)


def ladder(sections: int, kind: str) -> str:
    lines = ["Vin in 0 Vi"]
    previous = "in"
    for i in range(1, sections + 1):
        series = {"numeric": "1k", "repeated": "Rs", "unique": f"Rs{i}"}[kind]
        shunt = {"numeric": "2k", "repeated": "Rp", "unique": f"Rp{i}"}[kind]
        lines.append(f"RS{i} {previous} n{i} {series}")
        lines.append(f"RP{i} n{i} 0 {shunt}")
        previous = f"n{i}"
    lines.append(f".out V(n{sections}) Vin")
    return "\n".join(lines) + "\n"


RC = "Vin in 0 Vi\nR1 in out R\nC1 out 0 C\n.out V(out) Vin\n"
RLC = "Vin in 0 Vi\nR1 in n1 R\nL1 n1 out L\nC1 out 0 C\n.out V(out) Vin\n"
BRIDGE_NUMERIC = (
    "Vin top 0 Vi\nR1 top a 100\nR2 top b 200\nR3 a 0 300\nR4 b 0 400\n"
    "R5 a b 500\n.out V(a) Vin\n"
)
BRIDGE_SYMBOLIC = (
    "Vin top 0 Vi\nR1 top a Ra\nR2 top b Rb\nR3 a 0 Rc\nR4 b 0 Rd\n"
    "R5 a b Re\n.out V(a) Vin\n"
)
MULTI_VSOURCE = (
    "Vin a 0 Vi\nVb b 0 2\nVc c 0 3\n"
    "R1 a m R1\nR2 b m R2\nR3 c m R3\nR4 m 0 R4\n.out V(m) Vin\n"
)


def _timed(function):
    start = time.perf_counter()
    result = function()
    return result, time.perf_counter() - start


def bench_case(name: str, netlist: str, run_ilt: bool) -> dict:
    row: dict = {"case": name}
    circuit, row["parse"] = _timed(lambda: parse(netlist))
    _, row["topology"] = _timed(lambda: validate_topology(circuit))
    system, row["assemble"] = _timed(lambda: assemble(circuit))
    row["dim"] = system.A.shape[0]
    row["symbols"] = len(
        (system.A.free_symbols | system.z.free_symbols) - {sp.Symbol("s")}
    )

    index = system.node_index[circuit.output.node]
    source = circuit.component(circuit.output.source)

    v_lu, row["lu_solve"] = _timed(lambda: _output_lusolve(system, index))
    h_lu, row["lu_cancel"] = _timed(lambda: sp.cancel(v_lu / source.value))
    v_cr, row["cramer_solve"] = _timed(lambda: _output_cramer(system, index))
    h_cr, row["cramer_cancel"] = _timed(lambda: sp.cancel(v_cr / source.value))
    if sp.cancel(h_lu - h_cr) != 0:
        raise AssertionError(f"backend mismatch in case {name!r}")

    numerator, denominator = sp.fraction(h_lu)
    tf = TransferFunction(
        h_lu, numerator, denominator, circuit.output.node, circuit.output.source
    )
    _, row["pole_zero"] = _timed(lambda: pole_zero(tf))
    if run_ilt:
        _, row["ilt_step"] = _timed(lambda: step_response(tf))
    else:
        row["ilt_step"] = None
    (_, diagnostics), row["total_auto"] = _timed(
        lambda: transfer_function_with_diagnostics(parse(netlist))
    )
    row["auto_backend"] = diagnostics.backend
    return row


def _format(value) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value * 1000:.1f}"
    return str(value)


def bench_auto_only(name: str, netlist: str) -> dict:
    """auto 백엔드 경로만 측정 — 휴리스틱 변경 후 total_auto 재측정용.

    (백엔드별 열은 휴리스틱과 무관하므로 전체 재실행이 필요 없다.)
    """
    row: dict = {"case": name}
    circuit = parse(netlist)
    system = assemble(circuit)
    row["dim"] = system.A.shape[0]
    row["symbols"] = len(
        (system.A.free_symbols | system.z.free_symbols) - {sp.Symbol("s")}
    )
    (_, diagnostics), row["total_auto"] = _timed(
        lambda: transfer_function_with_diagnostics(parse(netlist))
    )
    row["auto_backend"] = diagnostics.backend
    return row


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--quick", action="store_true", help="smaller ladder sizes")
    parser.add_argument(
        "--auto-only",
        action="store_true",
        help="end-to-end auto-backend timings only (skips per-backend columns)",
    )
    arguments = parser.parse_args()

    # unique N=6부터는 LU 경로의 최종 cancel이 수십 분 단위로 발산한다
    # (N=5에서 이미 ~90s). 기본 상한은 5로 두고, 그 너머는 docs/benchmarks.md의
    # 해석을 참고할 것.
    unique_sizes = (3, 4) if arguments.quick else (3, 4, 5)
    cases: list[tuple[str, str, bool]] = [
        ("numeric ladder N=8", ladder(8, "numeric"), False),
        ("repeated-symbol ladder N=6", ladder(6, "repeated"), False),
        *[
            (f"unique-symbol ladder N={n}", ladder(n, "unique"), False)
            for n in unique_sizes
        ],
        ("RC low-pass (symbolic)", RC, True),
        ("RLC series (symbolic)", RLC, False),
        ("bridge (numeric)", BRIDGE_NUMERIC, True),
        ("bridge (unique symbols)", BRIDGE_SYMBOLIC, False),
        ("three V-source branches", MULTI_VSOURCE, False),
    ]

    if arguments.auto_only:
        columns = ["case", "dim", "symbols", "total_auto", "auto_backend"]
        print("| " + " | ".join(columns) + " |")
        print("|" + "---|" * len(columns))
        for name, netlist, _ in cases:
            row = bench_auto_only(name, netlist)
            print(
                "| " + " | ".join(_format(row.get(column)) for column in columns) + " |"
            )
            sys.stdout.flush()
        return

    columns = [
        "case", "dim", "symbols", "parse", "topology", "assemble",
        "lu_solve", "lu_cancel", "cramer_solve", "cramer_cancel",
        "pole_zero", "ilt_step", "total_auto", "auto_backend",
    ]
    print("| " + " | ".join(columns) + " |")
    print("|" + "---|" * len(columns))
    print("(times in milliseconds)", file=sys.stderr)
    for name, netlist, run_ilt in cases:
        row = bench_case(name, netlist, run_ilt)
        print("| " + " | ".join(_format(row.get(column)) for column in columns) + " |")
        sys.stdout.flush()


if __name__ == "__main__":
    main()

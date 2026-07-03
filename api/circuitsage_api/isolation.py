"""Process-level isolation for the symbolic solve pipeline (P0).

SymPy computations cannot be interrupted reliably from inside a process:
Unix signals, thread cancellation, asyncio.wait_for, and request
cancellation all fail to stop a C-level polynomial loop. The only hard
guarantee is a separate process that can be killed.

Design notes
  * ``spawn`` semantics are used on every platform. They are mandatory on
    Windows and also correct on Linux/Docker (no fork-with-threads hazard
    inside the uvicorn process).
  * The worker entry point is a module-level function whose module
    imports only the pipeline (never the FastAPI app), so a Windows child
    cannot recursively start the server.
  * One process per request: a timed-out worker is killed and joined, so
    no orphan survives and repeated timeouts cannot accumulate children.
    The cost is the spawn/import startup per isolated request; local
    trusted use can disable isolation with
    ``CIRCUITSAGE_SOLVE_TIMEOUT_SECONDS=0``.
  * Worker exceptions are serialized to (code, message, line_no) tuples
    and rebuilt as CircuitError subclasses in the parent, preserving the
    existing error → HTTP mapping.

``CIRCUITSAGE_SOLVE_TEST_HOOK`` (``sleep:<seconds>`` | ``crash``) is an
internal deterministic hook used only by the test suite.
"""

from __future__ import annotations

import multiprocessing
import os
import time
from multiprocessing.connection import Connection

from circuitsolver.errors import CircuitError

from . import pipeline

_POLL_INTERVAL = 0.05
_FINAL_DRAIN = 0.2  # last chance to read a result buffered by a dead child


class SolveTimeoutError(CircuitError):
    code = "TIMEOUT"


class WorkerError(CircuitError):
    code = "WORKER_ERROR"


class RemoteCircuitError(CircuitError):
    """A CircuitError raised inside the worker, rebuilt in the parent."""

    def __init__(self, code: str, message: str, line_no: int | None = None) -> None:
        super().__init__(message)
        self.code = code
        if line_no is not None:
            self.line_no = line_no


def _apply_test_hook() -> None:
    hook = os.environ.get("CIRCUITSAGE_SOLVE_TEST_HOOK", "")
    if hook.startswith("sleep:"):
        time.sleep(float(hook.split(":", 1)[1]))
    elif hook == "crash":
        raise RuntimeError("test-hook crash")


def _worker_entry(connection: Connection, netlist: str, options: dict) -> None:
    try:
        _apply_test_hook()
        result = pipeline.run_solve(netlist, options)
        connection.send(("ok", result))
    except CircuitError as exc:
        connection.send(
            (
                "circuit_error",
                {
                    "code": exc.code,
                    "message": str(exc),
                    "line_no": getattr(exc, "line_no", None),
                },
            )
        )
    except BaseException as exc:  # noqa: BLE001 — serialized for the parent
        connection.send(("worker_error", {"message": f"{type(exc).__name__}: {exc}"}))
    finally:
        connection.close()


def run_isolated(netlist: str, options: dict, timeout: float) -> dict:
    """Run the pipeline in a killable spawned process.

    ``timeout`` <= 0 means no deadline (the caller normally runs
    in-process instead; this path still isolates without a time bound).
    """
    context = multiprocessing.get_context("spawn")
    parent_end, child_end = context.Pipe(duplex=False)
    process = context.Process(
        target=_worker_entry, args=(child_end, netlist, options), daemon=True
    )
    process.start()
    child_end.close()
    try:
        kind, payload = _await_result(parent_end, process, timeout)
    finally:
        parent_end.close()
        _reap(process)

    if kind == "ok":
        return payload
    if kind == "circuit_error":
        raise RemoteCircuitError(
            payload["code"], payload["message"], payload.get("line_no")
        )
    raise WorkerError(f"solver worker failed unexpectedly: {payload['message']}")


def _await_result(connection: Connection, process, timeout: float):
    deadline = time.monotonic() + timeout if timeout > 0 else None
    while True:
        if connection.poll(_POLL_INTERVAL):
            try:
                return connection.recv()
            except EOFError:
                raise WorkerError(
                    f"solver worker closed the channel without a result "
                    f"(exit code {process.exitcode})"
                ) from None
        if deadline is not None and time.monotonic() > deadline:
            if process.is_alive():
                process.kill()
            raise SolveTimeoutError(
                f"solve exceeded CIRCUITSAGE_SOLVE_TIMEOUT_SECONDS={timeout:g} "
                "and the worker process was terminated"
            )
        if not process.is_alive():
            if connection.poll(_FINAL_DRAIN):
                return connection.recv()
            raise WorkerError(
                f"solver worker exited without a result (exit code {process.exitcode})"
            )


def _reap(process) -> None:
    """Join (and if necessary kill) the worker so no orphan remains."""
    process.join(5)
    if process.is_alive():
        process.kill()
        process.join(5)
    if not process.is_alive():
        process.close()

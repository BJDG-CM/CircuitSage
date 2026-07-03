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
  * **Pre-warmed persistent worker**: spawn startup (interpreter + SymPy
    import, roughly 1–3 s on Windows) is paid once, not per request. The
    server keeps a single worker alive and reuses it; a timed-out worker
    is killed *and immediately replaced with a fresh pre-warmed one*, so
    no orphan survives and repeated timeouts cannot accumulate children
    (worker count stays ≤ 1). Solves are serialized through that worker —
    appropriate for a local single-user tool; public-demo pairs this with
    rate limiting.
  * Worker exceptions are serialized to (code, message, line_no) tuples
    and rebuilt as CircuitError subclasses in the parent, preserving the
    existing error → HTTP mapping.
  * The test hook travels inside the job payload (read from
    ``CIRCUITSAGE_SOLVE_TEST_HOOK`` in the *parent* per request), so it
    stays deterministic even though the worker process is long-lived.
    Values: ``sleep:<seconds>`` | ``crash`` — used only by the test suite.
"""

from __future__ import annotations

import multiprocessing
import os
import threading
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


def _apply_test_hook(hook: str) -> None:
    if hook.startswith("sleep:"):
        time.sleep(float(hook.split(":", 1)[1]))
    elif hook == "crash":
        raise RuntimeError("test-hook crash")


def _worker_loop(connection: Connection) -> None:
    """Long-lived worker: recv (netlist, options, hook) jobs, send results."""
    while True:
        try:
            job = connection.recv()
        except (EOFError, OSError):
            return
        if job is None:
            return
        netlist, options, hook = job
        try:
            _apply_test_hook(hook)
            message = ("ok", pipeline.run_solve(netlist, options))
        except CircuitError as exc:
            message = (
                "circuit_error",
                {
                    "code": exc.code,
                    "message": str(exc),
                    "line_no": getattr(exc, "line_no", None),
                },
            )
        except BaseException as exc:  # noqa: BLE001 — serialized for the parent
            message = ("worker_error", {"message": f"{type(exc).__name__}: {exc}"})
        try:
            connection.send(message)
        except (OSError, BrokenPipeError):
            return


class _Worker:
    def __init__(self) -> None:
        context = multiprocessing.get_context("spawn")
        self.connection, child_end = context.Pipe(duplex=True)
        self.process = context.Process(
            target=_worker_loop, args=(child_end,), daemon=True
        )
        self.process.start()
        child_end.close()

    def alive(self) -> bool:
        return self.process.is_alive()

    def dispose(self) -> None:
        """Kill and join so no orphan remains, then release resources."""
        try:
            self.connection.close()
        except OSError:
            pass
        if self.process.is_alive():
            self.process.kill()
        self.process.join(5)
        if self.process.is_alive():
            self.process.kill()
            self.process.join(5)
        if not self.process.is_alive():
            self.process.close()


class WorkerPool:
    """One pre-warmed worker, replaced (and re-warmed) after a kill."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._worker: _Worker | None = None

    def warm(self) -> None:
        with self._lock:
            self._ensure()

    def worker_pid(self) -> int | None:
        with self._lock:
            if self._worker is not None and self._worker.alive():
                return self._worker.process.pid
            return None

    def _ensure(self) -> _Worker:
        if self._worker is None or not self._worker.alive():
            if self._worker is not None:
                self._worker.dispose()
            self._worker = _Worker()
        return self._worker

    def _replace(self, worker: _Worker) -> None:
        worker.dispose()
        self._worker = _Worker()  # pre-warm the replacement immediately

    def run(self, netlist: str, options: dict, timeout: float) -> tuple:
        hook = os.environ.get("CIRCUITSAGE_SOLVE_TEST_HOOK", "")
        with self._lock:
            worker = self._ensure()
            try:
                worker.connection.send((netlist, options, hook))
            except OSError:
                self._replace(worker)
                worker = self._worker
                worker.connection.send((netlist, options, hook))

            deadline = time.monotonic() + timeout if timeout > 0 else None
            while True:
                if worker.connection.poll(_POLL_INTERVAL):
                    try:
                        return worker.connection.recv()
                    except EOFError:
                        exit_code = worker.process.exitcode
                        self._replace(worker)
                        raise WorkerError(
                            "solver worker closed the channel without a result "
                            f"(exit code {exit_code})"
                        ) from None
                if deadline is not None and time.monotonic() > deadline:
                    self._replace(worker)
                    raise SolveTimeoutError(
                        "solve exceeded "
                        f"CIRCUITSAGE_SOLVE_TIMEOUT_SECONDS={timeout:g} "
                        "and the worker process was terminated"
                    )
                if not worker.alive():
                    if worker.connection.poll(_FINAL_DRAIN):
                        try:
                            return worker.connection.recv()
                        except EOFError:
                            pass
                    exit_code = worker.process.exitcode
                    self._replace(worker)
                    raise WorkerError(
                        f"solver worker exited without a result (exit code {exit_code})"
                    )


_POOL = WorkerPool()


def warm_pool() -> None:
    """Spawn the worker ahead of the first request (server startup)."""
    _POOL.warm()


def worker_pid() -> int | None:
    return _POOL.worker_pid()


def run_isolated(netlist: str, options: dict, timeout: float) -> dict:
    """Run the pipeline in the killable pre-warmed worker process.

    ``timeout`` <= 0 means no deadline (the caller normally runs
    in-process instead; this path still isolates without a time bound).
    """
    kind, payload = _POOL.run(netlist, options, timeout)
    if kind == "ok":
        return payload
    if kind == "circuit_error":
        raise RemoteCircuitError(
            payload["code"], payload["message"], payload.get("line_no")
        )
    raise WorkerError(f"solver worker failed unexpectedly: {payload['message']}")

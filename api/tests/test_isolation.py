"""Process-isolation tests (P0): spawn worker, hard timeout, error transport.

CIRCUITSAGE_SOLVE_TEST_HOOK is the deterministic internal hook —
"sleep:<s>" simulates an uninterruptible long computation, "crash"
simulates an unexpected worker failure.
"""

import multiprocessing

import pytest
from fastapi.testclient import TestClient

from circuitsage_api.main import create_app

RC_NUMERIC = "Vin in 0 5\nR1 in out 1k\nC1 out 0 1u\n.out V(out) Vin\n"


@pytest.fixture()
def client():
    return TestClient(create_app())


def _solve(client, netlist, **options):
    return client.post("/api/solve", json={"netlist": netlist, "options": options})


def _no_child_processes() -> bool:
    return multiprocessing.active_children() == []


class TestIsolatedExecution:
    def test_normal_solve_through_worker(self, client, monkeypatch):
        monkeypatch.setenv("CIRCUITSAGE_SOLVE_TIMEOUT_SECONDS", "60")
        response = _solve(client, RC_NUMERIC)
        assert response.status_code == 200
        body = response.json()
        assert body["transfer_function"]["latex"]
        assert body["complexity"]["component_count"] == 3
        assert _no_child_processes()

    def test_timeout_terminates_worker(self, client, monkeypatch):
        monkeypatch.setenv("CIRCUITSAGE_SOLVE_TIMEOUT_SECONDS", "1")
        monkeypatch.setenv("CIRCUITSAGE_SOLVE_TEST_HOOK", "sleep:30")
        response = _solve(client, RC_NUMERIC)
        assert response.status_code == 504
        error = response.json()["error"]
        assert error["code"] == "TIMEOUT"
        assert "CIRCUITSAGE_SOLVE_TIMEOUT_SECONDS" in error["message"]
        assert _no_child_processes()

    def test_repeated_timeouts_do_not_leak_children(self, client, monkeypatch):
        monkeypatch.setenv("CIRCUITSAGE_SOLVE_TIMEOUT_SECONDS", "1")
        monkeypatch.setenv("CIRCUITSAGE_SOLVE_TEST_HOOK", "sleep:30")
        for _ in range(3):
            response = _solve(client, RC_NUMERIC)
            assert response.status_code == 504
            assert _no_child_processes()

    def test_parse_error_with_isolation_enabled(self, client, monkeypatch):
        monkeypatch.setenv("CIRCUITSAGE_SOLVE_TIMEOUT_SECONDS", "60")
        response = _solve(client, "V1 a 0 1\nD1 a 0 1\n.out V(a) V1\n")
        assert response.status_code == 422
        error = response.json()["error"]
        assert error["code"] == "PARSE_ERROR"
        assert error["line_no"] == 2

    def test_topology_error_propagates_from_worker(self, client, monkeypatch):
        # floating node는 preflight가 아니라 워커 안에서 검출된다 —
        # 직렬화 → 부모 재구성 → 기존 오류 매핑까지의 전 경로를 검증
        monkeypatch.setenv("CIRCUITSAGE_SOLVE_TIMEOUT_SECONDS", "60")
        response = _solve(client, "V1 a 0 1\nR1 a 0 1k\nR2 b c 1k\n.out V(a) V1\n")
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "FLOATING_NODE"
        assert _no_child_processes()

    def test_circuit_error_from_worker_keeps_message(self, client, monkeypatch):
        monkeypatch.setenv("CIRCUITSAGE_SOLVE_TIMEOUT_SECONDS", "60")
        response = _solve(client, "V1 a 0 1\nR1 a 0 1k\n")  # .out 없음
        assert response.status_code == 400
        assert ".out" in response.json()["error"]["message"]

    def test_worker_crash_maps_to_worker_error(self, client, monkeypatch):
        monkeypatch.setenv("CIRCUITSAGE_SOLVE_TIMEOUT_SECONDS", "60")
        monkeypatch.setenv("CIRCUITSAGE_SOLVE_TEST_HOOK", "crash")
        response = _solve(client, RC_NUMERIC)
        assert response.status_code == 500
        error = response.json()["error"]
        assert error["code"] == "WORKER_ERROR"
        assert "RuntimeError" in error["message"]
        assert _no_child_processes()

    def test_disabled_timeout_runs_in_process(self, client, monkeypatch):
        monkeypatch.setenv("CIRCUITSAGE_SOLVE_TIMEOUT_SECONDS", "0")
        # in-process 경로는 워커 훅을 적용하지 않는다
        monkeypatch.setenv("CIRCUITSAGE_SOLVE_TEST_HOOK", "sleep:30")
        response = _solve(client, RC_NUMERIC)
        assert response.status_code == 200
        assert _no_child_processes()

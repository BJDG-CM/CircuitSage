"""Process-isolation tests (P0): pre-warmed worker pool, hard timeout,
error transport.

The pool keeps at most one worker alive and reuses it between requests;
a timed-out worker is killed and replaced with a fresh one. The test
hook (CIRCUITSAGE_SOLVE_TEST_HOOK = "sleep:<s>" | "crash") is read in
the parent per request and shipped inside the job payload, so it works
with the long-lived worker.
"""

import multiprocessing

import pytest
from fastapi.testclient import TestClient

from circuitsage_api.isolation import worker_pid
from circuitsage_api.main import create_app

RC_NUMERIC = "Vin in 0 5\nR1 in out 1k\nC1 out 0 1u\n.out V(out) Vin\n"


@pytest.fixture()
def client():
    return TestClient(create_app())


def _solve(client, netlist, **options):
    return client.post("/api/solve", json={"netlist": netlist, "options": options})


def _child_count() -> int:
    return len(multiprocessing.active_children())


class TestIsolatedExecution:
    def test_normal_solve_through_worker(self, client, monkeypatch):
        monkeypatch.setenv("CIRCUITSAGE_SOLVE_TIMEOUT_SECONDS", "60")
        response = _solve(client, RC_NUMERIC)
        assert response.status_code == 200
        body = response.json()
        assert body["transfer_function"]["latex"]
        assert body["complexity"]["component_count"] == 3
        assert _child_count() <= 1  # 풀 워커 1개 외에는 없음

    def test_worker_is_reused_between_requests(self, client, monkeypatch):
        monkeypatch.setenv("CIRCUITSAGE_SOLVE_TIMEOUT_SECONDS", "60")
        assert _solve(client, RC_NUMERIC).status_code == 200
        first_pid = worker_pid()
        assert first_pid is not None
        assert _solve(client, RC_NUMERIC).status_code == 200
        assert worker_pid() == first_pid  # 사전 기동 워커 재사용 (요청별 spawn 없음)

    def test_timeout_kills_and_prewarms_replacement(self, client, monkeypatch):
        monkeypatch.setenv("CIRCUITSAGE_SOLVE_TIMEOUT_SECONDS", "60")
        assert _solve(client, RC_NUMERIC).status_code == 200
        pid_before = worker_pid()

        monkeypatch.setenv("CIRCUITSAGE_SOLVE_TIMEOUT_SECONDS", "1")
        monkeypatch.setenv("CIRCUITSAGE_SOLVE_TEST_HOOK", "sleep:30")
        response = _solve(client, RC_NUMERIC)
        assert response.status_code == 504
        error = response.json()["error"]
        assert error["code"] == "TIMEOUT"
        assert "CIRCUITSAGE_SOLVE_TIMEOUT_SECONDS" in error["message"]

        replacement = worker_pid()
        assert replacement is not None and replacement != pid_before  # 대체 워커 예열
        assert _child_count() <= 1  # 죽은 워커는 join 완료, 고아 없음

        # 대체 워커가 즉시 정상 동작해야 한다
        monkeypatch.delenv("CIRCUITSAGE_SOLVE_TEST_HOOK", raising=False)
        monkeypatch.setenv("CIRCUITSAGE_SOLVE_TIMEOUT_SECONDS", "60")
        assert _solve(client, RC_NUMERIC).status_code == 200

    def test_repeated_timeouts_do_not_leak_children(self, client, monkeypatch):
        monkeypatch.setenv("CIRCUITSAGE_SOLVE_TIMEOUT_SECONDS", "1")
        monkeypatch.setenv("CIRCUITSAGE_SOLVE_TEST_HOOK", "sleep:30")
        for _ in range(3):
            response = _solve(client, RC_NUMERIC)
            assert response.status_code == 504
            assert _child_count() <= 1  # 킬+조인 후 대체 1개만

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

    def test_circuit_error_from_worker_keeps_message(self, client, monkeypatch):
        monkeypatch.setenv("CIRCUITSAGE_SOLVE_TIMEOUT_SECONDS", "60")
        response = _solve(client, "V1 a 0 1\nR1 a 0 1k\n")  # .out 없음
        assert response.status_code == 400
        assert ".out" in response.json()["error"]["message"]

    def test_worker_crash_maps_to_worker_error_and_worker_survives(
        self, client, monkeypatch
    ):
        monkeypatch.setenv("CIRCUITSAGE_SOLVE_TIMEOUT_SECONDS", "60")
        monkeypatch.setenv("CIRCUITSAGE_SOLVE_TEST_HOOK", "crash")
        response = _solve(client, RC_NUMERIC)
        assert response.status_code == 500
        error = response.json()["error"]
        assert error["code"] == "WORKER_ERROR"
        assert "RuntimeError" in error["message"]
        # 예외는 잡혀서 직렬화됐으므로 워커는 계속 살아 다음 요청을 처리한다
        monkeypatch.delenv("CIRCUITSAGE_SOLVE_TEST_HOOK", raising=False)
        assert _solve(client, RC_NUMERIC).status_code == 200
        assert _child_count() <= 1

    def test_disabled_timeout_runs_in_process(self, client, monkeypatch):
        monkeypatch.setenv("CIRCUITSAGE_SOLVE_TIMEOUT_SECONDS", "0")
        # in-process 경로는 워커 훅을 적용하지 않는다
        monkeypatch.setenv("CIRCUITSAGE_SOLVE_TEST_HOOK", "sleep:30")
        before = _child_count()
        response = _solve(client, RC_NUMERIC)
        assert response.status_code == 200
        assert _child_count() == before  # 새 프로세스를 만들지 않는다

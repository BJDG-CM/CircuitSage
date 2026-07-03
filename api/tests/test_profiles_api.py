"""운영 프로파일 동작 테스트: 레이트 리밋, 헬스, traceback 비유출."""

import pytest
from fastapi.testclient import TestClient

from circuitsage_api.main import create_app

RC_NUMERIC = "Vin in 0 5\nR1 in out 1k\nC1 out 0 1u\n.out V(out) Vin\n"


def _solve(client, netlist=RC_NUMERIC, **options):
    return client.post("/api/solve", json={"netlist": netlist, "options": options})


class TestRateLimiting:
    @pytest.fixture(autouse=True)
    def _isolated_db(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CIRCUITSAGE_DB", str(tmp_path / "rate.db"))

    def test_limit_returns_429_with_stable_code(self, monkeypatch):
        monkeypatch.setenv("CIRCUITSAGE_RATE_LIMIT_PER_MINUTE", "3")
        client = TestClient(create_app())
        for _ in range(3):
            assert _solve(client).status_code == 200
        response = _solve(client)
        assert response.status_code == 429
        assert response.json()["error"]["code"] == "RATE_LIMITED"

    def test_local_mode_has_no_limit_by_default(self, monkeypatch):
        monkeypatch.delenv("CIRCUITSAGE_RATE_LIMIT_PER_MINUTE", raising=False)
        monkeypatch.delenv("CIRCUITSAGE_MODE", raising=False)
        client = TestClient(create_app())
        for _ in range(5):
            assert _solve(client).status_code == 200

    def test_limiter_state_survives_restart(self, monkeypatch):
        # SQLite 저장이므로 앱(프로세스) 재시작을 시뮬레이션해도 창이 유지된다
        monkeypatch.setenv("CIRCUITSAGE_RATE_LIMIT_PER_MINUTE", "1")
        first = TestClient(create_app())
        assert _solve(first).status_code == 200
        assert _solve(first).status_code == 429
        second = TestClient(create_app())  # "재시작"한 새 앱 인스턴스
        assert _solve(second).status_code == 429

    def test_window_expiry_frees_the_bucket(self, monkeypatch, tmp_path):
        import sqlite3

        monkeypatch.setenv("CIRCUITSAGE_RATE_LIMIT_PER_MINUTE", "1")
        client = TestClient(create_app())
        assert _solve(client).status_code == 200
        assert _solve(client).status_code == 429
        # 이벤트를 창 밖(과거)으로 밀어내면 다시 허용되어야 한다
        with sqlite3.connect(tmp_path / "rate.db") as connection:
            connection.execute("UPDATE rate_events SET ts = ts - 3600")
        assert _solve(client).status_code == 200

    def test_fails_open_when_database_unusable(self, monkeypatch):
        monkeypatch.setenv("CIRCUITSAGE_RATE_LIMIT_PER_MINUTE", "1")
        monkeypatch.setenv("CIRCUITSAGE_DB", "Z:/nonexistent-dir/rate.db")
        client = TestClient(create_app())
        for _ in range(3):
            assert _solve(client).status_code == 200


class TestHealth:
    def test_health_endpoint(self):
        client = TestClient(create_app())
        body = client.get("/api/health").json()
        assert body["status"] == "ok"
        assert body["mode"] == "local"
        assert body["version"]

    def test_health_reports_mode(self, monkeypatch):
        monkeypatch.setenv("CIRCUITSAGE_MODE", "public-demo")
        client = TestClient(create_app())
        assert client.get("/api/health").json()["mode"] == "public-demo"


class TestNoTracebackLeak:
    def test_unexpected_error_returns_generic_500(self, monkeypatch):
        def boom(netlist, options):
            raise ValueError("secret internal detail")

        monkeypatch.setattr("circuitsage_api.routes.solve.run_solve", boom)
        client = TestClient(create_app(), raise_server_exceptions=False)
        response = _solve(client)
        assert response.status_code == 500
        error = response.json()["error"]
        assert error["code"] == "INTERNAL_ERROR"
        assert "secret internal detail" not in error["message"]
        assert "Traceback" not in response.text

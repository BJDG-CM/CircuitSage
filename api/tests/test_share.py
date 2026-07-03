"""공유 링크 보존 정책 테스트 (P1): 크기 제한, TTL, 정리, 손상 행 처리."""

import json
import sqlite3
import time

import pytest
from fastapi.testclient import TestClient

from circuitsage_api.main import create_app

NETLIST = "Vin in 0 5\nR1 in out 1k\nC1 out 0 1u\n.out V(out) Vin\n"


@pytest.fixture()
def db_path(tmp_path, monkeypatch):
    path = tmp_path / "shares.db"
    monkeypatch.setenv("CIRCUITSAGE_DB", str(path))
    return path


@pytest.fixture()
def client(db_path):
    return TestClient(create_app())


def _create(client, netlist=NETLIST, **options):
    return client.post("/api/share", json={"netlist": netlist, "options": options})


class TestPayloadValidation:
    def test_oversized_payload_rejected(self, client, monkeypatch):
        monkeypatch.setenv("CIRCUITSAGE_SHARE_MAX_BYTES", "100")
        response = _create(client, netlist="* " + "x" * 200 + "\n" + NETLIST)
        assert response.status_code == 413
        assert response.json()["error"]["code"] == "SHARE_TOO_LARGE"

    def test_roundtrip_still_works(self, client):
        share_id = _create(client, numeric_values={"R": 1}).json()["id"]
        body = client.get(f"/api/share/{share_id}").json()
        assert body["netlist"] == NETLIST
        assert body["options"]["numeric_values"] == {"R": 1}


class TestExpiration:
    def test_expired_share_is_gone_and_deleted(self, client, db_path, monkeypatch):
        monkeypatch.setenv("CIRCUITSAGE_SHARE_TTL_SECONDS", "3600")
        share_id = _create(client).json()["id"]

        # 만료 시각을 과거로 조작
        with sqlite3.connect(db_path) as connection:
            connection.execute(
                "UPDATE shares SET expires_at = ? WHERE id = ?",
                (time.time() - 10, share_id),
            )
        assert client.get(f"/api/share/{share_id}").status_code == 404
        with sqlite3.connect(db_path) as connection:
            rows = connection.execute(
                "SELECT COUNT(*) FROM shares WHERE id = ?", (share_id,)
            ).fetchone()[0]
        assert rows == 0  # 읽기 시점에 삭제됨

    def test_ttl_recorded_on_creation(self, client, db_path, monkeypatch):
        monkeypatch.setenv("CIRCUITSAGE_SHARE_TTL_SECONDS", "60")
        body = _create(client).json()
        assert body["expires_at"] is not None
        assert body["expires_at"] > time.time()

    def test_local_default_has_no_expiry(self, client):
        assert _create(client).json()["expires_at"] is None

    def test_expired_rows_swept_on_write(self, client, db_path, monkeypatch):
        monkeypatch.setenv("CIRCUITSAGE_SHARE_TTL_SECONDS", "3600")
        first = _create(client).json()["id"]
        with sqlite3.connect(db_path) as connection:
            connection.execute(
                "UPDATE shares SET expires_at = ?", (time.time() - 10,)
            )
        _create(client)  # 쓰기 트리거 정리
        with sqlite3.connect(db_path) as connection:
            remaining = connection.execute(
                "SELECT COUNT(*) FROM shares WHERE id = ?", (first,)
            ).fetchone()[0]
        assert remaining == 0


class TestBoundedRetention:
    def test_row_count_is_bounded(self, client, db_path, monkeypatch):
        monkeypatch.setenv("CIRCUITSAGE_SHARE_MAX_ROWS", "3")
        ids = [_create(client).json()["id"] for _ in range(6)]
        with sqlite3.connect(db_path) as connection:
            count = connection.execute("SELECT COUNT(*) FROM shares").fetchone()[0]
        # 마지막 insert 직전 cleanup이 3개로 줄이므로 최대 4개
        assert count <= 4
        # 가장 최근 것은 항상 살아 있어야 한다
        assert client.get(f"/api/share/{ids[-1]}").status_code == 200


class TestRobustness:
    def test_corrupted_options_still_restores_netlist(self, client, db_path):
        share_id = _create(client).json()["id"]
        with sqlite3.connect(db_path) as connection:
            connection.execute(
                "UPDATE shares SET options = ? WHERE id = ?", ("{not json", share_id)
            )
        body = client.get(f"/api/share/{share_id}").json()
        assert body["netlist"] == NETLIST
        assert body["options"] == {}

    def test_absurd_share_id_is_404(self, client):
        assert client.get("/api/share/" + "x" * 500).status_code == 404
        assert client.get("/api/share/%20").status_code == 404

"""Complexity-limit and profile tests (P0 guards)."""

import pytest
from fastapi.testclient import TestClient

from circuitsage_api.config import get_settings
from circuitsage_api.main import create_app

RC_SYMBOLIC = "Vin in 0 Vi\nR1 in out R\nC1 out 0 C\n.out V(out) Vin\n"
RC_NUMERIC = "Vin in 0 5\nR1 in out 1k\nC1 out 0 1u\n.out V(out) Vin\n"


@pytest.fixture()
def client():
    return TestClient(create_app())


def _solve(client, netlist, **options):
    return client.post("/api/solve", json={"netlist": netlist, "options": options})


def _ladder(sections: int) -> str:
    lines = ["Vin n0 0 1"]
    lines += [f"R{i} n{i - 1} n{i} 1k" for i in range(1, sections + 1)]
    lines.append(f"Rload n{sections} 0 1k")
    lines.append(f".out V(n{sections}) Vin")
    return "\n".join(lines) + "\n"


class TestLimitEnforcement:
    def test_netlist_too_large(self, client, monkeypatch):
        monkeypatch.setenv("CIRCUITSAGE_MAX_NETLIST_BYTES", "50")
        response = _solve(client, RC_SYMBOLIC)
        assert response.status_code == 413
        error = response.json()["error"]
        assert error["code"] == "NETLIST_TOO_LARGE"
        assert error["measured"] > 50
        assert error["limit"] == 50

    def test_too_many_symbols(self, client, monkeypatch):
        monkeypatch.setenv("CIRCUITSAGE_MAX_SYMBOLS", "2")
        response = _solve(client, RC_SYMBOLIC)  # R, C, Vi = 3 symbols
        assert response.status_code == 422
        error = response.json()["error"]
        assert error["code"] == "TOO_MANY_SYMBOLS"
        assert error["measured"] == 3
        assert error["limit"] == 2
        assert "CIRCUITSAGE_MAX_SYMBOLS" in error["message"]

    def test_matrix_too_large(self, client, monkeypatch):
        monkeypatch.setenv("CIRCUITSAGE_MAX_MNA_DIMENSION", "2")
        response = _solve(client, RC_NUMERIC)  # dimension 3 (in, out, i_Vin)
        assert response.status_code == 422
        error = response.json()["error"]
        assert error["code"] == "MATRIX_TOO_LARGE"
        assert error["measured"] == 3

    def test_component_limit_carries_details(self, client, monkeypatch):
        monkeypatch.setenv("CIRCUITSAGE_MAX_COMPONENTS", "2")
        response = _solve(client, RC_NUMERIC)
        assert response.status_code == 422
        error = response.json()["error"]
        assert error["code"] == "TOO_MANY_COMPONENTS"
        assert error["measured"] == 3
        assert error["limit"] == 2

    def test_zero_disables_a_limit(self, client, monkeypatch):
        monkeypatch.setenv("CIRCUITSAGE_MAX_COMPONENTS", "0")
        monkeypatch.setenv("CIRCUITSAGE_MAX_MNA_DIMENSION", "0")
        response = _solve(client, _ladder(18))  # 20 components
        assert response.status_code == 200

    def test_complexity_report_in_response(self, client):
        body = _solve(client, RC_SYMBOLIC).json()
        report = body["complexity"]
        assert report["component_count"] == 3
        assert report["mna_dimension"] == 3
        assert report["symbol_count"] == 3
        assert report["reactive_count"] == 1


class TestProfiles:
    def test_local_defaults(self, monkeypatch):
        monkeypatch.delenv("CIRCUITSAGE_MODE", raising=False)
        settings = get_settings()
        assert settings.mode == "local"
        assert settings.limits.max_components == 15
        assert settings.rate_limit_per_minute is None
        assert settings.share_ttl_seconds is None

    def test_public_demo_defaults(self, monkeypatch):
        monkeypatch.setenv("CIRCUITSAGE_MODE", "public-demo")
        settings = get_settings()
        assert settings.mode == "public-demo"
        assert settings.limits.max_netlist_bytes == 10_000
        assert settings.limits.max_symbols == 6
        assert settings.rate_limit_per_minute == 20
        assert settings.share_ttl_seconds == 7 * 24 * 3600

    def test_public_demo_timeout_is_mandatory(self, monkeypatch):
        monkeypatch.setenv("CIRCUITSAGE_MODE", "public-demo")
        monkeypatch.setenv("CIRCUITSAGE_SOLVE_TIMEOUT_SECONDS", "0")
        assert get_settings().solve_timeout == 30.0

    def test_local_timeout_can_be_disabled(self, monkeypatch):
        monkeypatch.setenv("CIRCUITSAGE_SOLVE_TIMEOUT_SECONDS", "0")
        assert get_settings().solve_timeout == 0.0

    def test_env_overrides_profile(self, monkeypatch):
        monkeypatch.setenv("CIRCUITSAGE_MODE", "public-demo")
        monkeypatch.setenv("CIRCUITSAGE_MAX_COMPONENTS", "5")
        assert get_settings().limits.max_components == 5

    def test_demo_limits_enforced_via_api(self, client, monkeypatch):
        monkeypatch.setenv("CIRCUITSAGE_MODE", "public-demo")
        big_comment = "* " + "x" * 10_100 + "\n"
        response = _solve(client, big_comment + RC_NUMERIC)
        assert response.status_code == 413
        assert response.json()["error"]["code"] == "NETLIST_TOO_LARGE"

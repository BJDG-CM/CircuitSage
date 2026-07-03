"""API 계층 테스트: /api/solve 파이프라인과 오류 매핑 (design §5)."""

import pytest
from fastapi.testclient import TestClient

from circuitsage_api.main import create_app

RC_NUMERIC = "Vin in 0 Vi\nR1 in out 1k\nC1 out 0 1u\n.out V(out) Vin\n"
RC_SYMBOLIC = "Vin in 0 Vi\nR1 in out R\nC1 out 0 C\n.out V(out) Vin\n"


@pytest.fixture()
def client():
    return TestClient(create_app())


def _solve(client, netlist, **options):
    return client.post("/api/solve", json={"netlist": netlist, "options": options})


class TestSolveHappyPath:
    def test_full_numeric_pipeline(self, client):
        response = _solve(client, RC_NUMERIC)
        assert response.status_code == 200
        body = response.json()
        assert body["planarity"]["planar"] is True
        assert body["transfer_function"]["latex"]
        assert body["transfer_stability"]["verdict"] == "stable"
        assert body["system_modes"]["status"] == "ok"
        assert body["poles"]["roots"][0]["re"] == pytest.approx(-1000.0)
        assert "bode" in body
        assert body["bode"]["corners"] == [1000.0]

    def test_mna_derivation_recorded(self, client):
        body = _solve(client, RC_NUMERIC).json()
        mna = body["mna"]
        assert [step["component"] for step in mna["steps"]] == ["Vin", "R1", "C1"]
        assert mna["checkpoints"][-1]["A_latex"] == mna["A_latex"]  # 최종 체크포인트 = A
        assert any(delta["target"] == "z" for delta in mna["steps"][0]["deltas"])

    def test_responses_with_samples(self, client):
        body = _solve(client, RC_NUMERIC, responses=["step"]).json()
        step = body["responses"]["step"]
        assert step["method"] == "table"
        samples = step["samples"]
        assert len(samples["t"]) == len(samples["y"]) == 200
        assert samples["y"][0] == pytest.approx(0.0, abs=1e-9)
        assert samples["y"][-1] == pytest.approx(1.0, abs=1e-3)  # 8τ 후 정상값

    def test_symbolic_circuit_skips_bode_with_warning(self, client):
        body = _solve(client, RC_SYMBOLIC).json()
        assert "bode" not in body
        assert any("Bode" in warning for warning in body["warnings"])

    def test_symbolic_with_numeric_values_gets_bode(self, client):
        body = _solve(
            client, RC_SYMBOLIC, numeric_values={"R": 1000, "C": 1e-6}
        ).json()
        assert body["bode"]["corners"] == [1000.0]

    def test_latex_report_option(self, client):
        body = _solve(client, RC_NUMERIC, latex=True).json()
        assert body["latex_report"].startswith("\\documentclass")

    def test_missing_ngspice_reports_unavailable_status(self, client, monkeypatch):
        monkeypatch.setattr("circuitsage_api.pipeline.find_ngspice", lambda: None)
        body = _solve(client, RC_NUMERIC, verify=True).json()
        assert body["verification"]["status"] == "unavailable"
        assert any("ngspice" in warning for warning in body["warnings"])

    def test_cancelled_internal_mode_is_reported_separately(self, client):
        # H(s)=1로 완전 소거되지만 내부 RC 모드는 system_modes에 남아야 한다
        netlist = "Vin in 0 Vi\nR1 in n R\nC1 n 0 C\n.out V(in) Vin\n"
        body = _solve(client, netlist).json()
        assert body["poles"]["roots"] == []
        modes = body["system_modes"]
        assert modes["status"] == "ok"
        assert len(modes["modes"]["roots"]) == 1
        assert modes["internal_stability"]["verdict"] == "stable"

    def test_simplification_steps_reported(self, client):
        netlist = "Vin a 0 Vi\nR1 a 0 1k\nR2 a 0 1k\n.out V(a) Vin\n"
        body = _solve(client, netlist).json()
        simplification = body["simplification"]
        assert len(simplification["steps"]) == 1
        assert simplification["steps"][0]["rule"] == "parallel"
        assert simplification["verified"] is True

    def test_bridge_has_no_simplification_steps(self, client):
        netlist = (
            "Vin top 0 Vi\nR1 top a 100\nR2 top b 200\n"
            "R3 a 0 300\nR4 b 0 400\nR5 a b 500\n.out V(a) Vin\n"
        )
        body = _solve(client, netlist).json()
        assert body["simplification"]["steps"] == []


class TestErrorMapping:
    def test_parse_error_carries_line_number(self, client):
        response = _solve(client, "V1 a 0 1\nD1 a 0 1\n.out V(a) V1\n")
        assert response.status_code == 422
        error = response.json()["error"]
        assert error["code"] == "PARSE_ERROR"
        assert error["line_no"] == 2

    def test_floating_node(self, client):
        response = _solve(client, "V1 a 0 1\nR1 a 0 1k\nR2 b c 1k\n.out V(a) V1\n")
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "FLOATING_NODE"

    def test_voltage_source_loop_maps_to_singular(self, client):
        response = _solve(client, "V1 a 0 5\nV2 a 0 5\nR1 a 0 1k\n.out V(a) V1\n")
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "SINGULAR_MATRIX"

    def test_component_limit(self, client):
        lines = ["Vin n0 0 1"]
        lines += [f"R{i} n{i - 1} n{i} 1k" for i in range(1, 17)]
        lines.append("Rload n16 0 1k")
        lines.append(".out V(n16) Vin")
        response = _solve(client, "\n".join(lines) + "\n")
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "TOO_MANY_COMPONENTS"

    def test_missing_out_directive_is_client_error(self, client):
        response = _solve(client, "V1 a 0 1\nR1 a 0 1k\n")
        assert response.status_code == 400
        assert ".out" in response.json()["error"]["message"]


class TestShareLinks:
    @pytest.fixture(autouse=True)
    def _isolated_db(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CIRCUITSAGE_DB", str(tmp_path / "shares.db"))

    def test_share_roundtrip(self, client):
        created = client.post(
            "/api/share",
            json={"netlist": RC_NUMERIC, "options": {"numeric_values": {"R": 1}}},
        )
        assert created.status_code == 200
        share_id = created.json()["id"]

        fetched = client.get(f"/api/share/{share_id}")
        assert fetched.status_code == 200
        body = fetched.json()
        assert body["netlist"] == RC_NUMERIC
        assert body["options"]["numeric_values"] == {"R": 1}

    def test_unknown_share_is_404(self, client):
        assert client.get("/api/share/nope").status_code == 404


class TestExamples:
    def test_examples_listed_with_netlists(self, client):
        response = client.get("/api/examples")
        assert response.status_code == 200
        items = response.json()
        names = {item["name"] for item in items}
        assert {"voltage_divider", "rc_lowpass", "rlc_series_ic"} <= names
        divider = next(item for item in items if item["name"] == "voltage_divider")
        assert ".out V(out) Vin" in divider["netlist"]
        assert divider["title"].strip()

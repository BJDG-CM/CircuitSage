"""ngspice 검증의 실행/파싱/오류 경로를 실행 파일 없이 검증하는 모의 테스트.

subprocess.run과 find_ngspice를 대체해 성공(AC/TRAN)·비정상 출력·타임아웃·
비정상 종료 코드·실행 파일 부재를 모두 결정적으로 재현한다. 실제 ngspice를
쓰는 통합 테스트는 test_verify.py에 있고 실행 파일이 없으면 skip된다.
"""

import subprocess
from pathlib import Path

import numpy as np
import pytest

from circuitsolver import parse
from circuitsolver import verify as verify_module
from circuitsolver.errors import VerificationError
from circuitsolver.verify import verify_ac, verify_tran

RC = "Vin in 0 5\nR1 in out 1k\nC1 out 0 1u\n.out V(out) Vin\n"
TAU = 1e-3  # R*C


class _FakeCompleted:
    def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = ""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


@pytest.fixture(autouse=True)
def _fake_executable(monkeypatch):
    monkeypatch.setattr(verify_module, "find_ngspice", lambda: "ngspice-fake")


def _install_runner(monkeypatch, writer, returncode: int = 0, stderr: str = ""):
    def fake_run(command, cwd=None, capture_output=True, text=True, timeout=None):
        assert isinstance(command, list)  # 인자 리스트 — 셸 문자열 금지
        assert timeout is not None  # 타임아웃 항상 적용
        writer(Path(cwd))
        return _FakeCompleted(returncode=returncode, stderr=stderr)

    monkeypatch.setattr(verify_module.subprocess, "run", fake_run)


class TestSuccessfulComparison:
    def test_ac_verification_passes_on_matching_output(self, monkeypatch):
        def writer(cwd: Path):
            freq = np.logspace(1, 4, 60)  # Hz
            h = 1.0 / (1.0 + 1j * 2 * np.pi * freq * TAU)
            np.savetxt(cwd / "out_re.txt", np.column_stack([freq, h.real]))
            np.savetxt(cwd / "out_im.txt", np.column_stack([freq, h.imag]))

        _install_runner(monkeypatch, writer)
        report = verify_ac(parse(RC))
        assert report.kind == "ac"
        assert report.passed, f"max rel error {report.max_rel_error}"

    def test_ac_verification_fails_on_wrong_magnitude(self, monkeypatch):
        def writer(cwd: Path):
            freq = np.logspace(1, 4, 60)
            h = 2.0 / (1.0 + 1j * 2 * np.pi * freq * TAU)  # 2배 오류
            np.savetxt(cwd / "out_re.txt", np.column_stack([freq, h.real]))
            np.savetxt(cwd / "out_im.txt", np.column_stack([freq, h.imag]))

        _install_runner(monkeypatch, writer)
        report = verify_ac(parse(RC))
        assert not report.passed
        assert report.max_rel_error > 0.5

    def test_tran_verification_passes_on_matching_output(self, monkeypatch):
        def writer(cwd: Path):
            times = np.linspace(0.0, 8 * TAU, 200)
            y = 5.0 * (1.0 - np.exp(-times / TAU))
            np.savetxt(cwd / "out_tran.txt", np.column_stack([times, y]))

        _install_runner(monkeypatch, writer)
        report = verify_tran(parse(RC))
        assert report.kind == "tran"
        assert report.passed, f"max rel error {report.max_rel_error}"


class TestFailureDiagnostics:
    def test_malformed_output_is_reported(self, monkeypatch):
        def writer(cwd: Path):
            (cwd / "out_re.txt").write_text("this is not a number table\n")
            (cwd / "out_im.txt").write_text("0 0\n")

        _install_runner(monkeypatch, writer)
        with pytest.raises(VerificationError, match="malformed"):
            verify_ac(parse(RC))

    def test_timeout_is_reported(self, monkeypatch):
        def fake_run(command, cwd=None, capture_output=True, text=True, timeout=None):
            raise subprocess.TimeoutExpired(cmd=command, timeout=timeout)

        monkeypatch.setattr(verify_module.subprocess, "run", fake_run)
        with pytest.raises(VerificationError, match="timed out"):
            verify_ac(parse(RC))

    def test_nonzero_exit_status_is_reported(self, monkeypatch):
        _install_runner(
            monkeypatch, lambda cwd: None, returncode=1, stderr="Error: no such device"
        )
        with pytest.raises(VerificationError, match="status 1") as exc_info:
            verify_ac(parse(RC))
        assert "no such device" in str(exc_info.value)  # 진단 tail 포함

    def test_missing_output_files_are_reported(self, monkeypatch):
        _install_runner(monkeypatch, lambda cwd: None, returncode=0)
        with pytest.raises(VerificationError, match="did not produce"):
            verify_ac(parse(RC))

    def test_nonfinite_output_is_rejected(self, monkeypatch):
        def writer(cwd: Path):
            freq = np.logspace(1, 4, 10)
            values = np.full_like(freq, np.nan)
            np.savetxt(cwd / "out_re.txt", np.column_stack([freq, values]))
            np.savetxt(cwd / "out_im.txt", np.column_stack([freq, values]))

        _install_runner(monkeypatch, writer)
        with pytest.raises(VerificationError, match="unusable"):
            verify_ac(parse(RC))

    def test_missing_executable(self, monkeypatch):
        monkeypatch.setattr(verify_module, "find_ngspice", lambda: None)
        with pytest.raises(VerificationError, match="not found"):
            verify_ac(parse(RC))

"""LaTeX 교수 노트 생성 테스트 (design §4.10)."""

from pathlib import Path

import sympy as sp

from circuitsolver import parse, transfer_function
from circuitsolver.report import generate_report

EXAMPLES_DIR = Path(__file__).resolve().parents[2] / "examples"


def _example(name: str):
    return parse((EXAMPLES_DIR / name).read_text(encoding="utf-8"))


class TestRCLowpassNote:
    def _tex(self):
        return generate_report(_example("rc_lowpass.cir"))

    def test_document_skeleton(self):
        tex = self._tex()
        assert tex.startswith("\\documentclass")
        assert "\\begin{document}" in tex and "\\end{document}" in tex

    def test_transfer_function_included(self):
        circuit = _example("rc_lowpass.cir")
        tex = generate_report(circuit)
        assert sp.latex(transfer_function(circuit).expr) in tex

    def test_stamp_narrative_and_checkpoints(self):
        tex = self._tex()
        assert "MNA 행렬 유도" in tex
        assert "\\mathrel{+}=" in tex  # 스탬프 델타 서사
        assert "스탬프까지 적용한 뒤" in tex  # 체크포인트 행렬

    def test_routh_and_time_response_sections(self):
        tex = self._tex()
        assert "Routh--Hurwitz 표" in tex
        assert "안정" in tex
        assert "임펄스 응답" in tex and "스텝 응답" in tex
        assert "부분분수 분해" in tex


class TestRLCWithICs:
    def test_ic_equivalent_section(self):
        tex = generate_report(_example("rlc_series_ic.cir"), include_responses=False)
        assert "초기조건 등가" in tex
        assert "Iic\\_L1" in tex and "Iic\\_C1" in tex
        assert "zero-state" in tex and "zero-input" in tex

    def test_no_response_section_when_disabled(self):
        tex = generate_report(_example("rlc_series_ic.cir"), include_responses=False)
        assert "임펄스 응답" not in tex


class TestBridgeNote:
    def test_planarity_remark_and_no_poles(self):
        tex = generate_report(_example("wheatstone_bridge.cir"))
        assert "mesh 해석도 적용 가능" in tex
        assert "극점이 없다" in tex

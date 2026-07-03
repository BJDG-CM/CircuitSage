"""요청 스키마 (Pydantic). 응답은 결과 존재 여부가 회로마다 달라
유연한 dict로 내려보낸다 — 형태는 설계 문서 §5를 따른다."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ResponseKind = Literal["impulse", "step"]


class SolveOptions(BaseModel):
    numeric_values: dict[str, float] = Field(default_factory=dict)
    responses: list[ResponseKind] = Field(default_factory=lambda: ["impulse", "step"])
    verify: bool = False
    latex: bool = False
    debug: bool = False  # 솔버 진단(백엔드, 단계별 시간)을 응답에 포함


class SolveRequest(BaseModel):
    netlist: str
    options: SolveOptions = Field(default_factory=SolveOptions)

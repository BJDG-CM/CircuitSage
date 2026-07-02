"""GET /api/examples — 예제 netlist 목록 (design §5)."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter

router = APIRouter()

_DEFAULT_DIR = Path(__file__).resolve().parents[3] / "examples"


def _examples_dir() -> Path:
    return Path(os.environ.get("CIRCUITSAGE_EXAMPLES_DIR", _DEFAULT_DIR))


@router.get("/examples")
def examples() -> list[dict]:
    items = []
    for path in sorted(_examples_dir().glob("*.cir")):
        netlist = path.read_text(encoding="utf-8")
        first_line = netlist.splitlines()[0] if netlist.splitlines() else ""
        title = first_line.lstrip("* ").strip() or path.stem
        items.append({"name": path.stem, "title": title, "netlist": netlist})
    return items

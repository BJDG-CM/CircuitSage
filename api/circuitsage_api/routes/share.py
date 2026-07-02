"""공유 링크 (M6, design §7): 도입 시점에 SQLite 한 파일로 시작한다."""

from __future__ import annotations

import json
import os
import secrets
import sqlite3
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter()


def _db_path() -> Path:
    return Path(os.environ.get("CIRCUITSAGE_DB", "circuitsage.db"))


def _connect() -> sqlite3.Connection:
    connection = sqlite3.connect(_db_path())
    connection.execute(
        "CREATE TABLE IF NOT EXISTS shares ("
        " id TEXT PRIMARY KEY,"
        " netlist TEXT NOT NULL,"
        " options TEXT NOT NULL,"
        " created_at TEXT DEFAULT CURRENT_TIMESTAMP)"
    )
    return connection


class ShareRequest(BaseModel):
    netlist: str
    options: dict = Field(default_factory=dict)


@router.post("/share")
def create_share(request: ShareRequest) -> dict:
    share_id = secrets.token_urlsafe(6)
    with _connect() as connection:
        connection.execute(
            "INSERT INTO shares (id, netlist, options) VALUES (?, ?, ?)",
            (share_id, request.netlist, json.dumps(request.options)),
        )
    return {"id": share_id}


@router.get("/share/{share_id}")
def get_share(share_id: str) -> dict:
    with _connect() as connection:
        row = connection.execute(
            "SELECT netlist, options FROM shares WHERE id = ?", (share_id,)
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="공유 링크를 찾을 수 없습니다")
    return {"netlist": row[0], "options": json.loads(row[1])}

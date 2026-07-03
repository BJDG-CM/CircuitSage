"""공유 링크 (M6, design §7): SQLite 한 파일 + 보존 정책.

로컬 모드는 TTL/보존 상한이 기본적으로 꺼져 있고, public-demo 모드는
payload 크기 제한·TTL·최대 행 수가 기본 적용된다 (config.py). 만료 행
삭제와 초과 행 정리는 쓰기 요청 시점에 수행한다(단일 인스턴스 앱에는
백그라운드 스케줄러가 과하다).
"""

from __future__ import annotations

import json
import os
import secrets
import sqlite3
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from circuitsolver.errors import CircuitError

from ..config import Settings, get_settings

router = APIRouter()

_ID_MAX_LENGTH = 32


class ShareTooLargeError(CircuitError):
    code = "SHARE_TOO_LARGE"


def _db_path() -> Path:
    return Path(os.environ.get("CIRCUITSAGE_DB", "circuitsage.db"))


def _connect() -> sqlite3.Connection:
    connection = sqlite3.connect(_db_path())
    connection.execute(
        "CREATE TABLE IF NOT EXISTS shares ("
        " id TEXT PRIMARY KEY,"
        " netlist TEXT NOT NULL,"
        " options TEXT NOT NULL,"
        " created_at TEXT DEFAULT CURRENT_TIMESTAMP,"
        " created_ts REAL,"
        " expires_at REAL)"
    )
    # 기존 DB 마이그레이션: 새 컬럼이 없으면 추가
    columns = {row[1] for row in connection.execute("PRAGMA table_info(shares)")}
    if "created_ts" not in columns:
        connection.execute("ALTER TABLE shares ADD COLUMN created_ts REAL")
    if "expires_at" not in columns:
        connection.execute("ALTER TABLE shares ADD COLUMN expires_at REAL")
    # cleanup이 사용하는 인덱스
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_shares_expires_at ON shares (expires_at)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_shares_created_ts ON shares (created_ts)"
    )
    return connection


def _cleanup(connection: sqlite3.Connection, settings: Settings) -> None:
    now = time.time()
    connection.execute(
        "DELETE FROM shares WHERE expires_at IS NOT NULL AND expires_at < ?", (now,)
    )
    if settings.share_max_rows is not None:
        connection.execute(
            "DELETE FROM shares WHERE id IN ("
            " SELECT id FROM shares"
            " ORDER BY created_ts DESC"
            " LIMIT -1 OFFSET ?)",
            (settings.share_max_rows,),
        )


class ShareRequest(BaseModel):
    netlist: str
    options: dict = Field(default_factory=dict)


@router.post("/share")
def create_share(request: ShareRequest) -> dict:
    settings = get_settings()
    options_json = json.dumps(request.options)
    payload_bytes = len(request.netlist.encode("utf-8")) + len(
        options_json.encode("utf-8")
    )
    if payload_bytes > settings.share_max_bytes:
        raise ShareTooLargeError(
            f"share payload {payload_bytes} bytes exceeds the configured limit "
            f"CIRCUITSAGE_SHARE_MAX_BYTES={settings.share_max_bytes}"
        )

    now = time.time()
    expires_at = (
        now + settings.share_ttl_seconds
        if settings.share_ttl_seconds is not None
        else None
    )
    share_id = secrets.token_urlsafe(6)
    with _connect() as connection:
        _cleanup(connection, settings)
        connection.execute(
            "INSERT INTO shares (id, netlist, options, created_ts, expires_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (share_id, request.netlist, options_json, now, expires_at),
        )
    return {"id": share_id, "expires_at": expires_at}


@router.get("/share/{share_id}")
def get_share(share_id: str) -> dict:
    if not share_id or len(share_id) > _ID_MAX_LENGTH:
        raise HTTPException(status_code=404, detail="공유 링크를 찾을 수 없습니다")
    with _connect() as connection:
        row = connection.execute(
            "SELECT netlist, options, expires_at FROM shares WHERE id = ?",
            (share_id,),
        ).fetchone()
        if row is not None and row[2] is not None and row[2] < time.time():
            connection.execute("DELETE FROM shares WHERE id = ?", (share_id,))
            row = None
    if row is None:
        raise HTTPException(status_code=404, detail="공유 링크를 찾을 수 없습니다")
    try:
        options = json.loads(row[1])
        if not isinstance(options, dict):
            options = {}
    except (json.JSONDecodeError, TypeError):
        options = {}  # 손상된 행이라도 netlist는 복원한다
    return {"netlist": row[0], "options": options}

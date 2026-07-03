#!/usr/bin/env bash
# CircuitSage 로컬 개발 실행 (Linux/macOS)
#   ./scripts/dev.sh    # 의존성 점검 후 API(8000) + Vite(5173) 실행
set -euo pipefail
cd "$(dirname "$0")/.."

need() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "[missing] $1 — $2" >&2
    exit 1
  fi
}

need python3 "install Python 3.10+ (https://www.python.org/downloads/)"
need node "install Node.js 22+ (https://nodejs.org)"
need npm "bundled with Node.js"

if ! command -v ngspice >/dev/null 2>&1; then
  echo "[optional] ngspice not on PATH — numerical cross-verification is disabled; symbolic analysis works without it." >&2
fi

if [ ! -d .venv ]; then
  echo "creating virtualenv and installing packages..."
  python3 -m venv .venv
  ./.venv/bin/python -m pip install -q -e "core[dev]" -e "api[dev]"
fi

if [ ! -d web/node_modules ]; then
  echo "installing frontend dependencies..."
  (cd web && npm ci --no-fund --no-audit)
fi

echo "API:  http://127.0.0.1:8000  /  Web: http://localhost:5173"
./.venv/bin/python -m uvicorn circuitsage_api.main:app --port 8000 &
API_PID=$!
trap 'kill "$API_PID" 2>/dev/null || true' EXIT
(cd web && npm run dev)

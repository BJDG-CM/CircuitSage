"""CircuitSage 로컬 런처.

    python scripts/launch.py [--port 8000]

백엔드를 127.0.0.1에 띄우고, /api/health가 응답할 때까지 기다린 뒤
브라우저를 연다. Ctrl+C로 종료하면 백엔드도 함께 정리된다.
web/dist가 있으면 빌드된 SPA를 같은 포트에서 서빙한다 (없으면 API만).
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _python() -> str:
    for candidate in (
        ROOT / ".venv" / "Scripts" / "python.exe",  # Windows
        ROOT / ".venv" / "bin" / "python",  # Unix
    ):
        if candidate.exists():
            return str(candidate)
    return sys.executable


def _check_backend_installed(python: str) -> None:
    probe = subprocess.run(
        [python, "-c", "import circuitsage_api"], capture_output=True
    )
    if probe.returncode != 0:
        print(
            "circuitsage_api가 설치되어 있지 않습니다. 먼저 실행:\n"
            "  python -m venv .venv\n"
            '  <venv>/python -m pip install -e "core[dev]" -e "api[dev]"',
            file=sys.stderr,
        )
        sys.exit(1)


def _wait_for_health(url: str, timeout_seconds: float, process) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if process.poll() is not None:
            return False  # 서버가 먼저 죽음
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return True
        except OSError:
            time.sleep(0.3)
    return False


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-browser", action="store_true")
    arguments = parser.parse_args()

    python = _python()
    _check_backend_installed(python)

    environment = dict(os.environ)
    static_dir = ROOT / "web" / "dist"
    if static_dir.is_dir():
        environment.setdefault("CIRCUITSAGE_STATIC_DIR", str(static_dir))
    else:
        print("web/dist 없음 — API만 서빙합니다 (cd web && npm run build로 SPA 포함 가능)")

    server = subprocess.Popen(
        [
            python, "-m", "uvicorn", "circuitsage_api.main:app",
            "--host", "127.0.0.1", "--port", str(arguments.port),
        ],
        cwd=ROOT,
        env=environment,
    )
    base = f"http://127.0.0.1:{arguments.port}"
    try:
        if not _wait_for_health(f"{base}/api/health", 30.0, server):
            print("백엔드가 30초 안에 준비되지 않았습니다.", file=sys.stderr)
            server.terminate()
            sys.exit(1)
        print(f"CircuitSage 실행 중: {base} (종료: Ctrl+C)")
        if not arguments.no_browser:
            webbrowser.open(base)
        server.wait()
    except KeyboardInterrupt:
        pass
    finally:
        if server.poll() is None:
            server.terminate()
            try:
                server.wait(10)
            except subprocess.TimeoutExpired:
                server.kill()
        print("백엔드를 정리했습니다.")


if __name__ == "__main__":
    main()

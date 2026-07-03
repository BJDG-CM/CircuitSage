import pytest


@pytest.fixture(autouse=True)
def _fast_in_process_solve(monkeypatch):
    """기본 API 테스트는 in-process로 실행해 스위트를 빠르게 유지한다.

    (spawn 워커는 요청마다 인터프리터 기동 + sympy import 비용을 낸다.)
    격리 경로 자체는 test_isolation.py가 명시적으로 켜서 검증한다.
    """
    monkeypatch.setenv("CIRCUITSAGE_SOLVE_TIMEOUT_SECONDS", "0")
    monkeypatch.delenv("CIRCUITSAGE_SOLVE_TEST_HOOK", raising=False)

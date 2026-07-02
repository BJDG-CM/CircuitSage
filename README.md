# CircuitSage — Symbolic Circuit Solver

선형 회로 netlist를 입력받아 Modified Nodal Analysis(MNA)를 **기호(symbolic)** 로 수행하고,
전달함수 H(s)·pole/zero·안정성·시간응답·Bode plot을 계산해 교수 노트 형식의 LaTeX 문서로
출력하는 웹 애플리케이션. 결과는 ngspice 수치 시뮬레이션과 교차 검증한다.

설계 전문: [Symbolic-Circuit-Solver-설계문서.md](Symbolic-Circuit-Solver-설계문서.md)

## 구조

```
core/       # 순수 Python 패키지 circuitsolver (웹 프레임워크 의존 없음)
api/        # FastAPI 앱 (Phase 4)
web/        # Vite + React + TS (Phase 4)
examples/   # 예제 netlist
docker/     # 배포 이미지 (Phase 5)
```

## 개발 환경

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e "core[dev]"
.\.venv\Scripts\python -m pytest core/tests
```

## 진행 상황 (로드맵 §9)

- [x] **M1 엔진 코어** — 파서 ✅ · 그래프/평면성 ✅ · MNA 스탬프 ✅ · H(s) ✅
- [x] **M2 동역학** — IC 등가 ✅ · pole/zero ✅ · Routh ✅ · 자체 역라플라스 ✅
- [x] **M3 출력물** — Bode 데이터 ✅ · LaTeX 노트(.tex) ✅ · ngspice 검증 ✅(CI에서 실행)
- [ ] M4 웹 — FastAPI + React UI
- [ ] M5 마감 — 단순화 스텝, Docker 배포
- [ ] M6 선택 — 회로 그리기 에디터, 공유 링크

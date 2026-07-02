# CircuitSage — Symbolic Circuit Solver

[![CI](https://github.com/BJDG-CM/CircuitSage/actions/workflows/ci.yml/badge.svg)](https://github.com/BJDG-CM/CircuitSage/actions/workflows/ci.yml)

선형 회로 netlist를 입력받아 Modified Nodal Analysis(MNA)를 **기호(symbolic)** 로 수행하고,
전달함수 H(s) · pole/zero · Routh–Hurwitz 안정성 · impulse/step 응답 닫힌형 · Bode plot을
계산해 교수 노트 형식의 LaTeX 문서로 출력하는 웹 애플리케이션입니다.
모든 결과는 **ngspice 수치 시뮬레이션과 자동 교차 검증**됩니다.

설계 전문: [Symbolic-Circuit-Solver-설계문서.md](Symbolic-Circuit-Solver-설계문서.md)

## 핵심 스토리 — 3중 검증

핵심 수학을 라이브러리 호출로 때우지 않고 직접 구현했습니다(ADR-1, lcapy는 테스트
오라클로만 사용). 정확성은 세 겹으로 방어합니다:

> 손으로 유도한 이론값 == 자체 엔진의 symbolic 결과 == ngspice 수치 결과 (오차 < 0.1%)

직접 구현한 것들:

- **MNA 스탬프 조립** — 소자별 (행, 열, 항) 델타 기록으로 유도 과정 전체를 재생 (ADR-7)
- **초기조건 등가 전원** — IC를 병렬 전류원으로 치환, zero-state/zero-input 분해
- **Routh–Hurwitz 표** — 0 피벗(ε 치환)·전행 0(보조 다항식) 특수 케이스 포함,
  기호 계수는 "μ < 1 + R₂/R₁이면 안정" 식의 **조건부 판정** 출력
- **부분분수 역라플라스** — 변환표 기반(중복 극점·감쇠 정현파), SymPy는 fallback
- **단계별 회로 단순화** — 직렬/병렬/Norton 변환을 기록하고 H(s) 보존을 자체 검증

## 빠른 시작

### Docker (ngspice 포함, 권장)

```bash
docker build -f docker/Dockerfile -t circuitsage .
docker run -p 8000:8000 -v circuitsage-data:/data circuitsage
# → http://localhost:8000
```

### 로컬 개발

```powershell
# 백엔드 (테스트 158개)
python -m venv .venv
.\.venv\Scripts\python -m pip install -e "core[dev]" -e "api[dev]"
.\.venv\Scripts\python -m pytest core/tests api/tests
.\.venv\Scripts\python -m uvicorn circuitsage_api.main:app --port 8000

# 프런트엔드 (별도 터미널)
cd web && npm install && npm run dev   # → http://localhost:5173
```

ngspice 검증을 로컬에서 돌리려면 [ngspice](https://ngspice.sourceforge.io)를 PATH에
설치하세요(없으면 해당 테스트는 자동 skip, CI에서는 항상 실행).

## Netlist 문법 (SPICE 서브셋 + 확장)

```
* RLC 직렬 회로 — 값 자리에 식별자를 쓰면 기호로 처리
Vin  in   0    Vi          ; 기호 입력원
R1   in   n1   R
L1   n1   out  2m  IC=0.1  ; 초기 전류 0.1 A
C1   out  0    C   IC=5    ; 초기 전압 5 V
.out V(out) Vin            ; H(s) = V(out)/Vin
.end
```

지원 소자: R, L, C, 독립 V/I 전원. SPICE 접미사(`k m u n p Meg`) 지원.
`.out`은 SPICE 예약어와 충돌하지 않는 자체 지시어입니다(ADR-6).

## 구조

```
core/       # 순수 Python 패키지 circuitsolver — 웹 의존성 0
api/        # FastAPI: /api/solve, /api/examples, /api/share
web/        # Vite + React + TS: netlist/회로도 에디터, KaTeX·Plotly 결과 뷰
examples/   # golden 예제 netlist
docker/     # 단일 배포 이미지 (ngspice 포함)
```

의존성 방향은 `web → api → core` 단방향입니다. 코어는 CLI·노트북·pytest에서
독립적으로 실행됩니다.

## 로드맵 현황 (설계 §9)

- [x] **M1 엔진 코어** — 파서 · 그래프/평면성 · MNA 스탬프 · H(s)
- [x] **M2 동역학** — IC 등가 · pole/zero · Routh(조건부 판정) · 자체 역라플라스
- [x] **M3 출력물** — Bode 데이터 · LaTeX 교수 노트(.tex) · ngspice 교차 검증
- [x] **M4 웹** — FastAPI + React UI (7개 결과 탭)
- [x] **M5 마감** — 단순화 스텝 · Docker 이미지 · README
- [x] **M6 선택** — SVG 회로 그리기 에디터 → netlist 컴파일 · 공유 링크(SQLite)
- [ ] 공개 URL 배포 — Docker 이미지 준비 완료, 호스팅(Fly.io/Railway 등)만 남음

## 테스트

| 계층 | 내용 |
|---|---|
| core (146) | golden 회로 이론값 대조, Routh 특수 케이스, property-based 사다리망(hypothesis), ngspice 검증 4건(CI) |
| api (16) | 전체 파이프라인, 오류 코드 매핑(라인 번호 포함), 공유 링크 |
| web (6) | 회로도→netlist 컴파일러 (vitest), 타입체크 + 프로덕션 빌드 |
| docker | 컨테이너 내부에서 ngspice 검증 포함 solve 스모크 테스트 |

# Symbolic Circuit Solver — 설계 문서

| 항목 | 내용 |
|---|---|
| 버전 | v0.2 |
| 날짜 | 2026-07-02 |
| 상태 | Accepted |
| 형태 | 웹앱 — FastAPI 백엔드 + React 프런트엔드, 코어는 순수 Python 패키지 |

---

## 1. 개요

회로이론에서 다루는 선형 회로를 netlist로 입력받아, Modified Nodal Analysis(MNA)를 **기호(symbolic)** 로 수행하고 전달함수 H(s) = V_o(s)/V_i(s), pole·zero·안정성, impulse/step 응답, Bode plot을 계산한 뒤 전 과정을 교수 노트 형식의 LaTeX 문서로 출력하는 웹 애플리케이션. 결과는 SPICE(ngspice) 수치 시뮬레이션과 교차 검증한다.

이 프로젝트의 두 가지 목적은 명확히 구분된다. 첫째는 학습 도구로서 회로이론 문제 풀이 과정을 기계가 검증 가능한 형태로 재현하는 것이고, 둘째는 포트폴리오로서 "MNA를 라이브러리에 의존하지 않고 직접 구현하고, 수치 시뮬레이터로 정합성을 검증했다"는 스토리를 만드는 것이다. 따라서 핵심 수학(MNA 스탬프, 초기조건 등가, Routh–Hurwitz, 부분분수 역라플라스)은 직접 구현하고, 기존 라이브러리(lcapy)는 **테스트 오라클**로만 사용한다.

### 비목표 (Non-goals)

범위 폭주를 막기 위해 다음은 명시적으로 하지 않는다. 비선형 소자(다이오드, 트랜지스터 대신호), 트랜지스터 소신호 등가회로의 자동 추출(사용자가 등가회로를 직접 netlist로 입력하는 것은 가능), **결합 인덕터(상호 인덕턴스 `K` 문법)** — 구조적으로는 branch-current 스탬프 하나로 추가 가능하므로 Phase 5 이후 후보로만 남긴다 —, 수백 노드 규모의 대형 회로, 실시간 협업 편집, 사용자 계정 시스템. 회로를 마우스로 그리는 schematic 에디터는 비목표는 아니지만 마지막 Phase로 미룬다 — netlist 입력만으로도 모든 핵심 기능이 성립하기 때문이다.

---

## 2. 요구사항

### 2.1 기능 요구사항

| ID | 요구사항 | Phase |
|---|---|---|
| FR-1 | SPICE 서브셋 netlist 입력 (숫자 값 + 기호 값 모두 지원) | 1 |
| FR-2 | 노드 자동 판별(접지·floating node 검출) 및 평면성 판정 | 1 |
| FR-3 | Symbolic MNA 방정식 A(s)x = z(s) 생성 및 유도 과정 기록 | 1 |
| FR-4 | H(s) = V_o(s)/V_i(s) 계산 | 1 |
| FR-5 | 초기조건(i_L(0⁻), v_C(0⁻))을 s-domain 등가 전원으로 변환, 완전응답 = zero-state + zero-input 분리 | 2 |
| FR-6 | Pole/zero 계산, Routh–Hurwitz 표 기반 안정성 판정 (판정 불가 시 기호 조건 목록 출력) | 2 |
| FR-7 | Impulse/step response의 닫힌형 해 (부분분수 → 역라플라스) | 2 |
| FR-8 | Bode plot (크기 dB, 위상 deg) 데이터 생성 | 3 |
| FR-9 | 직렬/병렬 결합·전원 변환 기반 회로 단순화 과정의 단계별 표시 | 5 |
| FR-10 | 전체 풀이의 LaTeX 교수 노트 출력 (.tex, 가능하면 PDF) | 3 |
| FR-11 | ngspice 수치 결과와 symbolic 결과의 자동 교차 검증 | 3 |
| FR-12 | 웹 UI: netlist 에디터, 결과 뷰(수식·그래프), 예제 라이브러리 | 4 |
| FR-13 | SVG 기반 회로 그리기 에디터 → netlist 컴파일 | 6 (선택) |

### 2.2 비기능 요구사항

**정확성이 최우선이다.** 교육 도구가 틀린 답을 내는 것은 존재 이유를 부정하므로, 모든 릴리즈는 golden circuit 테스트(§8)를 100% 통과해야 한다. **응답 시간**은 symbolic 연산 특성상 보장이 어려우므로 소자 수 상한(기본 15개)과 연산 timeout(기본 30초)으로 통제한다. **규모**는 동시 사용자 수십 명 수준이면 충분하다(개인 프로젝트 + 시연). **배포 용이성**을 위해 전체를 Docker 이미지 하나(ngspice 포함)로 패키징한다. **유지보수성**을 위해 코어 엔진은 웹 프레임워크에 대한 의존이 전혀 없는 순수 Python 패키지로 만들고, 타입 힌트와 pytest 커버리지를 유지한다.

### 2.3 제약

1인 개발, 학기와 병행. 개발자는 TypeScript/NestJS 백엔드 경험이 있으나 Python 웹(FastAPI)과 React는 학습을 겸한다. Symbolic 연산은 사실상 Python(SymPy) 생태계가 유일한 선택지다. **로컬 개발 환경은 Windows, 배포는 Docker(리눅스)** — 이 차이가 영향을 주는 지점(§4.5 timeout 격리)은 해당 절에 명시한다.

---

## 3. 전체 아키텍처

```
┌──────────────────────┐        ┌───────────────────────────────────────┐
│  React SPA (Vite+TS) │  HTTP  │  FastAPI (api/)                       │
│  · netlist 에디터     │ ─JSON─▶│  · 요청 검증(Pydantic)                 │
│  · KaTeX 수식 렌더    │◀────── │  · timeout / 에러 매핑                 │
│  · Plotly Bode/응답   │        │  · (Phase 3+) 비동기 job 관리          │
└──────────────────────┘        └───────────────┬───────────────────────┘
                                                │ 함수 호출 (동일 프로세스)
                                ┌───────────────▼───────────────────────┐
                                │  circuitsolver-core (순수 Python)      │
                                │  parser → graph → mna → analysis      │
                                │  simplify / report(LaTeX) / verify    │
                                └───────────────┬───────────────────────┘
                                                │ subprocess
                                        ┌───────▼────────┐
                                        │    ngspice     │
                                        └────────────────┘
```

의존성 방향은 단방향이다: `api → core`, core는 FastAPI의 존재를 모른다. 이 분리 덕분에 코어는 CLI·노트북·테스트에서 독립적으로 실행 가능하고, 나중에 껍데기를 바꾸는 비용이 0에 가깝다.

### 모노레포 구조

```
circuit-solver/
├── core/                        # pip 패키지 circuitsolver
│   ├── circuitsolver/
│   │   ├── parser.py            # netlist → Circuit 모델
│   │   ├── circuit.py           # Component, Circuit 데이터클래스
│   │   ├── graph.py             # 노드 판별, 연결성, 평면성 (networkx)
│   │   ├── mna.py               # symbolic MNA 스탬프 & 조립
│   │   ├── initial.py           # IC → s-domain 등가 전원 변환
│   │   ├── analysis.py          # H(s), pole/zero, Routh, 시간응답
│   │   ├── laplace.py           # 부분분수 기반 역라플라스 (자체 구현)
│   │   ├── bode.py              # 주파수 응답 수치 데이터
│   │   ├── simplify.py          # 단계별 회로 단순화 (Phase 5)
│   │   ├── report.py            # Jinja2 → LaTeX 교수 노트
│   │   ├── spice_io.py          # 자체 확장 → ngspice 문법 변환 계층
│   │   └── verify.py            # ngspice 교차 검증
│   └── tests/                   # golden circuits + property tests
├── api/                         # FastAPI 앱
│   ├── main.py, routes/, schemas/
│   └── tests/
├── web/                         # Vite + React + TS
│   └── src/ (pages, components, api client)
├── examples/                    # 예제 netlist 모음
├── docker/                      # Dockerfile (ngspice 포함)
└── .github/workflows/ci.yml
```

---

## 4. 코어 엔진 딥다이브

### 4.1 Netlist 문법 (parser.py)

SPICE 문법의 서브셋에 두 가지 확장을 더한다: **기호 값**(값 자리에 숫자 대신 식별자를 쓰면 SymPy 심볼로 처리)과 **초기조건 인라인 표기**(`IC=`). 첫 글자가 소자 종류를 결정하는 SPICE 관례를 따른다.

자체 확장 지시어는 SPICE와 이름이 충돌하지 않게 짓는다. 전달함수 지정은 `.out`을 쓴다 — SPICE의 `.tf`는 이미 "DC small-signal transfer function"이라는 다른 의미로 예약되어 있어, 같은 이름의 재정의는 SPICE 경험자와 검증 경로(§4.11) 양쪽에 혼란을 만든다.

```
* RLC 직렬 회로, 커패시터 전압이 출력
Vin  in   0    Vi          ; 기호 입력원 (라플라스 영역에서 V_i(s))
R1   in   n1   R           ; 기호 값
L1   n1   out  2m  IC=0.1  ; 2 mH, i_L(0-) = 0.1 A
C1   out  0    C   IC=5    ; 기호 값, v_C(0-) = 5 V
.out V(out) Vin            ; 전달함수 지정: 출력 / 입력
.end
```

| 지원 소자 | 문법 | 비고 |
|---|---|---|
| 저항 | `Rxx n+ n- value` | |
| 인덕터 | `Lxx n+ n- value [IC=i0]` | i0: t=0⁻ 전류 |
| 커패시터 | `Cxx n+ n- value [IC=v0]` | v0: t=0⁻ 전압 |
| 독립 전압원/전류원 | `Vxx n+ n- value`, `Ixx …` | 값이 기호면 입력 신호로 취급 가능 |
| 종속 전원 4종 | `Exx`(VCVS) `Gxx`(VCCS) `Fxx`(CCCS) `Hxx`(CCVS) | Phase 2 |
| 이상 연산증폭기 | `Oxx n+ n- nout` | Phase 5, nullor 모델 |

값에는 SPICE 접미사(`k, m, u, n, p, Meg`)를 허용한다. 파서는 라인 단위 정규식 + 소자별 검증으로 구현하고, 오류 시 **라인 번호와 원인**을 담은 `ParseError`를 낸다(웹 에디터에서 해당 라인 하이라이트에 사용).

**ngspice 변환 계층 (spice_io.py).** 자체 확장(`.out`, 인라인 `IC=`, 기호 값)이 있는 netlist는 ngspice에 그대로 넘길 수 없다. 검증 경로로 나가는 netlist는 별도 모듈에서 (1) 자체 지시어 제거, (2) `IC=` → ngspice `.ic V(node)=v0` / `L… ic=i0` 문법으로 변환, (3) 기호 값 → 사용자 제공 수치 대입을 수행해 **순수 ngspice 방언**으로 재작성한다. 이 변환 계층을 파서와 분리해 두면 자체 문법 확장이 검증 경로를 오염시키지 않는다.

### 4.2 노드 판별과 평면성 (graph.py)

노드는 netlist에 등장한 단자 이름의 집합으로 자동 수집하며 `0`(접지)은 필수다. 회로를 networkx `MultiGraph`(같은 노드쌍에 병렬 소자가 가능하므로 MultiGraph여야 함)로 만들고 세 가지를 검사한다.

1. **연결성** — 접지에서 도달 불가능한 노드가 있으면 floating node 오류.
2. **자명한 오류** — MNA 행렬을 특이하게 만드는 두 위상을 사전에 감지해 친절한 오류를 낸다. 구현은 각각 networkx 기본 연산으로 끝난다:
   - *전압원 루프*: 전압원(과 VCVS·CCVS 등 전압 구속 소자) 간선만으로 만든 서브그래프에서 `nx.cycle_basis`(또는 간선 수 ≥ 노드 수 − 성분 수 체크)로 사이클 존재를 검사.
   - *전류원 cut-set*: 전류원 간선을 모두 제거한 그래프에서 연결 성분 수가 늘어나면(어떤 노드 집합이 전류원으로만 연결되어 있으면) KCL이 과잉 결정된다.
3. **평면성** — `networkx.check_planarity`(Boyer–Myrvold, O(n))로 판정하고, 평면이면 embedding을 함께 반환한다. 평면성 결과는 교수 노트에서 "mesh analysis 적용 가능 여부" 언급과, Phase 6의 자동 배치에 쓰인다.

### 4.3 Symbolic MNA (mna.py)

s-domain에서 각 수동 소자는 임피던스 Z_R = R, Z_L = sL, Z_C = 1/(sC)로 통일된다. 미지수 벡터는 표준 MNA를 따라 x = [v₁ … v_{n-1} | i_{V1} … i_{Vm}]ᵀ — 접지를 제외한 노드 전압에, 전류가 변수로 필요한 소자(Group 2: 전압원, VCVS, CCVS, 그리고 CCCS/CCVS가 참조하는 가지)의 가지 전류를 덧붙인다.

조립은 **스탬프(stamp) 방식**으로 한다. 소자마다 자신이 행렬 A와 우변 z의 어느 위치에 무엇을 더하는지가 지역적으로 정의되므로, 소자 목록을 한 번 순회하면 전체 시스템이 완성된다. 대표 스탬프:

| 소자 | 스탬프 |
|---|---|
| 어드미턴스 y (R, L, C) | A[p,p]+=y, A[m,m]+=y, A[p,m]−=y, A[m,p]−=y |
| 전압원 V (전류 변수 k) | A[p,k]+=1, A[m,k]−=1, A[k,p]+=1, A[k,m]−=1, z[k]+=V(s) |
| 전류원 I | z[p]−=I(s), z[m]+=I(s) |
| VCVS (이득 μ) | 전압원 행에 제어 노드 항 −μ 추가 |

구현 포인트: A는 `sympy.zeros(n,n)`에서 시작하는 `Matrix`다. 유도 과정 기록(FR-3)은 **스탬프 델타 방식**으로 한다 — 소자마다 "(소자, 기여 위치 목록 [(행, 열, 더한 항)])"만 기록하고, 전체 행렬의 LaTeX 렌더링은 노트 생성 시점에 체크포인트(첫 소자 적용 직후, 수동 소자 완료 시, Group 2 완료 = 최종)에서만 수행한다. 소자마다 n×n 행렬 전체를 LaTeX로 스냅숏하면 노드 10개 회로에서 기록량이 소자 수 × 100항으로 폭발하고 노트 가독성도 오히려 떨어지기 때문이다. 델타 기록만으로도 "이 소자가 행렬 어디에 무엇을 더했는가"라는 교육적 서사는 온전히 재구성된다.

### 4.4 초기조건 처리 (initial.py)

핵심 설계 결정: **MNA 모듈은 초기조건의 존재를 모른다.** 파서가 `IC=`를 읽으면 회로 변환 단계에서 등가 전원을 자동 삽입한 새 `Circuit`을 만들고, MNA는 그 결과만 본다(관심사 분리).

인덕터는 임피던스 sL에 직렬 전압원 L·i_L(0⁻)(전류 방향으로 전압 상승) 또는 병렬 전류원 i_L(0⁻)/s로, 커패시터는 임피던스 1/(sC)에 직렬 전압원 v_C(0⁻)/s 또는 병렬 전류원 C·v_C(0⁻)로 치환한다. 기본은 **병렬 전류원 형태**를 쓴다 — Group 2 변수(전압원 전류)가 늘어나지 않아 행렬이 작게 유지되기 때문이다. 교수 노트에는 두 등가가 모두 유도와 함께 실린다.

완전응답은 선형성에 따라 두 번의 풀이로 분해한다: 입력원만 켠 zero-state 응답과 초기조건 전원만 켠 zero-input 응답. 이 분해 자체가 회로이론 교과의 핵심 개념이므로 노트에도 그대로 반영한다.

### 4.5 H(s) 풀이 (analysis.py)

A(s)x = z(s)를 `A.LUsolve(z)`로 풀고 각 성분에 `sympy.cancel`을 적용해 유리식으로 정리한다. H(s)는 입력원 심볼로 출력을 나눈 뒤 cancel한 결과다.

**Cramer 경로.** H(s)만 필요할 때는 전체 x 벡터가 불필요하므로, 출력 성분 하나를 H = det(Aᵢ)/det(A) (Aᵢ는 i열을 z로 치환한 행렬)로 구하는 Cramer 방식이 더 가벼울 수 있고, 분모 det(A)가 곧 특성다항식이라는 사실이 교수 노트의 유도 서사와도 자연스럽게 이어진다. M1에서 LUsolve를 기본 경로로 구현하되, Cramer 경로를 같은 인터페이스의 대안 백엔드로 만들어 golden 회로에서 벤치마크한 뒤 기본값을 결정한다.

**symbolic 폭발 대응 전략**: `simplify()`는 지수적으로 느려질 수 있어 기본적으로 쓰지 않고 `cancel`/`together`만 사용, 소자 수 상한(15개)과 전체 timeout(30초, `multiprocessing` 기반 — SymPy는 시그널로 중단이 안 되는 C 루프가 있어 별도 프로세스 격리가 안전)을 둔다. 행렬식이 0이면(특이) §4.2에서 못 잡은 위상 오류이므로 원인 후보와 함께 오류를 낸다.

**Windows 개발 환경 주의.** 배포(Docker/리눅스)에서는 fork로 격리 비용이 작지만, 로컬 Windows에서는 multiprocessing이 spawn 방식이라 SymPy 식의 pickle 왕복 + 인터프리터 기동 비용이 매 호출에 붙는다. timeout 래퍼는 설정(`CIRCUITSOLVER_TIMEOUT=0`이면 비활성)으로 끌 수 있게 만들어, 로컬 pytest가 불필요하게 느려지지 않도록 한다. CI(리눅스)에서는 항상 켠다.

### 4.6 Pole/Zero와 안정성

H(s) = N(s)/D(s)로 분자·분모를 분리(`fraction`)한 뒤, 계수가 전부 수치면 `Poly.nroots()`로 근을 구하고, 기호 계수면 4차 이하에서 `roots()`로 닫힌형을 시도하되 실패하면 "수치 값 대입 시 계산 가능"으로 표시한다.

안정성은 두 갈래로 판정한다. 수치 pole이 있으면 max Re(p) < 0 직접 확인. 기호 계수면 **Routh–Hurwitz 표를 직접 구현**해 첫 열 부호 조건으로 판정한다. Routh 표는 0 피벗·전행 0 같은 특수 케이스 처리를 포함해 구현하고 표 전체를 노트에 출력한다 — 이 부분이 교육적으로나 포트폴리오로나 가장 차별화되는 지점이다.

**기호 부호 판정의 한계와 2단계 출력.** 기호 식의 부호 판정은 일반적으로 결정 불가능하므로, "판정"과 "조건 제시"를 처음부터 별개 결과로 설계한다:

1. 소자 심볼은 파서 단계에서 물리적 타당성 가정과 함께 생성한다 — `sympy.symbols('R L C', positive=True)`. 이 가정만으로 SymPy가 첫 열 원소들의 부호를 판정할 수 있으면(예: RLC 직렬은 전 원소가 양) `verdict: "stable" | "unstable" | "marginal"`을 낸다.
2. 부호가 판정되지 않는 원소가 하나라도 있으면 `verdict: "conditional"`로 두고, **첫 열 원소 > 0 부등식 목록 자체를 결과로** 반환한다(예: 이득 μ가 있는 회로에서 "μ < 1 + R₂/R₁이면 안정"). 노트에는 Routh 표와 함께 이 조건들이 실린다.

이 2단계 구조는 API 스키마(§5)의 `stability` 객체에 그대로 반영한다.

### 4.7 시간응답 (laplace.py)

`sympy.inverse_laplace_transform`은 유리식에서도 느리거나 실패하는 경우가 많아 **주 경로는 자체 구현**으로 한다: `apart(s)`로 부분분수 분해 → 각 항을 변환표(1/(s−a)ⁿ ↔ tⁿ⁻¹e^{at}/(n−1)!, 복소 켤레쌍 ↔ 감쇠 정현파)로 역변환 → 실수형으로 정리. impulse는 L⁻¹{H(s)}, step은 L⁻¹{H(s)/s}, 초기조건 포함 완전응답은 §4.4의 분해 결과를 각각 역변환한다. 부분분수 분해 과정 자체를 단계별로 기록해 노트에 싣는다. 자체 구현이 실패하면 SymPy ILT로 fallback, 그마저 실패하면 수치 응답(§4.11의 시뮬레이션)만 제공하고 노트에 사유를 명시한다. 기호 계수 회로의 닫힌형 시간응답은 분모 인수분해가 가능한 범위(실질적으로 2차, 닫힌형 근이 나오면 4차까지)에서만 시도하고, 그 밖에는 수치 대입을 안내한다.

### 4.8 Bode 데이터 (bode.py)

H(s)에 기호가 남아 있으면 사용자가 준 수치를 대입한 뒤, `lambdify`로 numpy 함수화해 s = jω (로그 스케일 주파수 벡터)에서 평가한다. 코어는 `{freq[], mag_db[], phase_deg[]}` **데이터만** 반환하고 렌더링은 프런트(Plotly)가 맡는다 — 서버에서 이미지를 만들지 않으므로 API가 가볍고 그래프가 인터랙티브해진다. LaTeX 노트용으로만 matplotlib PNG를 선택적으로 생성한다. 위상은 unwrap 처리, 꺾은선 근사(asymptotic Bode)도 corner frequency 목록과 함께 계산해 교육용으로 겹쳐 그린다(복소 켤레 pole 쌍은 표준 2차형 ω_n, ζ로 묶어 처리).

### 4.9 회로 단순화 (simplify.py, Phase 5)

직렬 결합(차수 2 내부 노드 제거), 병렬 결합(MultiGraph의 다중 간선 병합), 전원 변환(Thévenin↔Norton)의 세 규칙을 고정점까지 반복 적용하고, 각 적용을 `SimplificationStep(rule, before, after, latex설명)`으로 기록한다. 중요한 원칙: **H(s) 계산은 항상 MNA로 하고, 단순화는 설명용 병렬 트랙이다.** 단순화가 끝까지 되지 않는 회로(브리지 등)가 많으므로 결과 산출을 단순화에 의존시키면 안 된다. 단순화가 단일 등가 임피던스까지 도달한 경우에 한해 MNA 결과와 일치하는지 자체 검증한다.

### 4.10 LaTeX 교수 노트 (report.py)

Jinja2 템플릿(LaTeX 충돌을 피하기 위해 구분자를 `\VAR{}`/`\BLOCK{}`로 변경)으로 .tex를 생성한다. 노트 구성은 실제 강의 노트의 흐름을 따른다: 문제 설정(회로 표, 노드 정의) → s-domain 변환(초기조건 등가 유도 포함) → MNA 행렬 유도(스탬프 델타 서사 + 체크포인트 행렬) → 풀이와 H(s) → pole-zero 지도와 Routh 표(조건부 판정이면 안정 조건 부등식 포함) → 부분분수 분해와 시간응답 → Bode 요약(corner frequency 표) → SPICE 검증 결과 표. 서버 Docker 이미지에 texlive-small을 포함해 PDF 컴파일을 제공하되, 실패해도 .tex 다운로드는 항상 가능하게 한다. 웹 미리보기는 KaTeX로 수식 조각만 렌더링한다(전체 PDF 미리보기는 요구하지 않음).

### 4.11 SPICE 교차 검증 (verify.py)

ngspice를 **subprocess 배치 모드**로 실행한다(PySpice의 공유 라이브러리 의존을 피해 배포를 단순화). 입력은 §4.1의 변환 계층(spice_io.py)이 만든 순수 ngspice 방언 netlist다. 두 축으로 검증한다. (1) 주파수 영역 — `.ac` 해석 결과 |H(jω)|, ∠H(jω)를 symbolic H(s)의 수치 평가와 주파수 격자에서 비교. (2) 시간 영역 — `.tran` + `.ic`로 step 응답을 얻어 닫힌형 해의 샘플과 비교. 판정은 상대오차(기본 0.1%) + 절대오차 바닥값의 혼합 허용치로 하고, 결과를 (최대 오차, 위치, pass/fail) 표로 반환한다. 기호 값 회로는 사용자가 검증용 수치 세트를 제공한 경우에만 검증한다.

---

## 5. API 설계 (api/)

Symbolic 연산은 수 초에서 수십 초가 걸릴 수 있다. Phase 4에서는 **동기 엔드포인트 + 서버측 timeout**으로 시작하고, 사용성 문제가 확인되면 in-process 비동기 job(asyncio + 메모리 job store)으로 확장한다. Celery/Redis급 인프라는 이 규모에서 오버엔지니어링이므로 도입하지 않는다.

```
POST /api/solve
  요청: { netlist: string,
          options: { numeric_values?: {심볼: 수치},   // Bode·검증용 대입값
                     responses?: ["impulse","step","full"],
                     verify?: bool, latex?: bool } }
  응답: {
    nodes: [...], planarity: { planar: bool },
    mna: { A_latex, z_latex, x_latex,
           steps: [ { component, deltas: [[row, col, term_latex]] } ],
           checkpoints: [ { label, A_latex } ] },
    transfer_function: { latex, numerator, denominator },
    poles: [...], zeros: [...],
    stability: { verdict: "stable"|"unstable"|"marginal"|"conditional"|"unknown",
                 method: "routh"|"numeric",
                 conditions_latex?: [...],       // verdict=conditional일 때 안정 조건 부등식
                 routh_table_latex? },
    responses: { impulse?: {latex, samples}, step?: {...},
                 zero_input?: {...}, zero_state?: {...} },
    bode?: { freq, mag_db, phase_deg, corners },
    verification?: { passed, max_rel_error, details },
    latex_report?: string,
    warnings: [...]
  }

GET  /api/examples            # 예제 netlist 목록
POST /api/report/pdf          # .tex → PDF 컴파일 (선택)
```

오류 모델은 사용자 실수를 정확히 짚는 것이 목표다: `PARSE_ERROR`(라인 번호 포함), `FLOATING_NODE`, `SINGULAR_MATRIX`(전압원 루프 등 원인 후보 포함), `TIMEOUT`, `TOO_MANY_COMPONENTS`. FastAPI 예외 핸들러에서 코어의 예외 계층을 HTTP 422/400/504로 매핑한다.

---

## 6. 프런트엔드 설계 (web/)

Vite + React + TypeScript 단일 페이지. 좌측은 CodeMirror 기반 netlist 에디터(문법 하이라이트, 파싱 오류 라인 표시, 예제 드롭다운), 우측은 결과 탭 — 요약(H(s), pole-zero, 안정성 한눈에) / MNA 유도 과정 / 시간응답(닫힌형 수식 + Plotly 그래프) / Bode(Plotly, asymptote 토글) / LaTeX 노트(.tex 다운로드, PDF 버튼) / 검증 리포트. 수식은 KaTeX로 렌더링한다. 상태 관리는 서버 응답 캐시 수준이므로 TanStack Query면 충분하고 전역 상태 라이브러리는 두지 않는다. Phase 6의 회로 에디터는 SVG 위 소자 배치 → 내부적으로 netlist로 컴파일하는 구조로, 엔진 입장에서는 입력 경로가 하나 늘어날 뿐이다.

---

## 7. 데이터와 상태

Phase 1–5에는 DB가 없다. 모든 요청은 무상태이며 회로는 요청 본문에 담겨 온다. 공유 링크(회로를 URL로 공유) 기능을 넣는 시점에 SQLite 한 파일로 시작한다. 이 결정으로 배포·백업·마이그레이션 부담이 사라진다.

---

## 8. 테스트 전략

**3중 검증** 원칙: 손으로 계산한 이론값 == 자체 엔진의 symbolic 결과 == ngspice 수치 결과. 이론값은 테스트 코드에 하드코딩된 정답이고, lcapy를 보조 오라클로 CI에서만 추가 비교한다.

| Golden circuit | 검증 포인트 |
|---|---|
| 저항 전압분배기 | 최소 MNA, H = R2/(R1+R2) |
| RC 1차 저역통과 | H = 1/(1+sRC), pole = −1/RC, step 응답 지수함수 |
| RL 1차 | 시정수 L/R |
| RLC 직렬 (과감쇠/임계/부족감쇠 3케이스) | 표준 2차형, 켤레 pole, 감쇠 정현파 역변환 |
| C에 IC 있는 RC 방전 | zero-input 응답, s-domain 등가 전원 |
| 휘트스톤 브리지 | 평면성 true, 직병렬 단순화 불가 케이스 |
| K₅ 유사 저항망 | 평면성 false 판정 |
| 전압원 2개 루프 | SINGULAR/사전 검출 오류 경로 |
| VCVS 비반전 증폭기 | Group 2 스탬프, 조건부 안정성(이득 조건) 출력 경로 |

Property-based 테스트를 한 가지 추가한다: 무작위 저항 사다리망에서 DC 이득이 반복 전압분배 계산과 일치하는지(hypothesis 라이브러리). CI는 GitHub Actions에서 core 테스트 → api 테스트 → 프런트 빌드 순으로 돌리고, ngspice는 CI 러너에 apt로 설치한다.

---

## 9. 로드맵 — 마일스톤과 완료 기준

| 마일스톤 | 내용 | 검증 가능한 완료 기준 |
|---|---|---|
| M1 엔진 코어 | 파서, 그래프/평면성, MNA, H(s) | golden 회로 중 IC 없는 6종의 H(s)가 이론값과 `simplify(차)==0`으로 일치 |
| M2 동역학 | IC 등가, pole/zero, Routh, 자체 역라플라스 | RLC 3케이스의 step 응답 닫힌형이 이론값과 일치, Routh 표가 기호 조건을 출력 |
| M3 출력물 | Bode 데이터, LaTeX 노트, ngspice 검증 | 예제 회로의 .tex가 오류 없이 PDF 컴파일, ngspice 대비 오차 < 0.1% |
| M4 웹 | FastAPI + React UI | 브라우저에서 netlist 입력 → 전 결과 확인 및 .tex 다운로드 |
| M5 마감 | 단순화 스텝, Docker 배포, README | 공개 URL에서 동작, 단순화 가능한 회로에서 단계 표시 |
| M6 선택 | 회로 그리기 에디터, 공유 링크 | 그린 회로가 netlist 경로와 동일 결과 |

M1–M2가 프로젝트의 심장이고 UI 없이도 pytest만으로 완결된다. 학기 중이라도 M1을 잘게(파서 → 그래프 → 스탬프 1종씩) 진행할 수 있게 커밋 단위를 소자 스탬프 하나 수준으로 잡는다.

---

## 10. 리스크와 대응

| 리스크 | 대응 |
|---|---|
| Symbolic 식 폭발로 응답 불능 | 소자 수 상한, `simplify` 대신 `cancel`, 프로세스 격리 timeout |
| SymPy 역라플라스 실패/저속 | 자체 부분분수 역변환을 주 경로로, SymPy는 fallback |
| Routh 기호 부호 판정 불가 | positive 가정 + 조건부 판정(부등식 목록 출력)을 1급 결과로 설계 (§4.6) |
| ngspice 설치·배포 편차 | Docker 이미지에 고정 버전 포함, subprocess 호출로 라이브러리 의존 제거 |
| 범위 폭주 (op-amp, 비선형…) | §1 비목표 명문화, 새 소자는 스탬프 1개 추가로 국한되는 구조 유지 |
| React 학습 곡선으로 M4 지연 | M1–M3는 프런트 없이 완결되므로 일정 리스크가 엔진에 전파되지 않음 |
| Windows 로컬에서 timeout 격리 오버헤드 | timeout 래퍼를 설정으로 비활성 가능하게, CI에서는 항상 활성 (§4.5) |

---

## 11. 주요 결정 기록 (ADR 요약)

**ADR-1 · Symbolic 엔진은 SymPy 위에 직접 구현, lcapy는 테스트 오라클로만.** lcapy를 그대로 쓰면 M1–M2가 일주일로 줄지만 프로젝트의 학습·포트폴리오 가치가 "라이브러리 호출"로 격하된다. 직접 구현의 정확성 리스크는 3중 검증(§8)으로 상쇄한다. 결과: 구현량 증가를 감수하고 채택.

**ADR-2 · 웹앱 = FastAPI + React, 코어는 프레임워크 무관 패키지.** Streamlit(가장 빠름, 확장성 낮음), Tauri 데스크톱(공유 어려움) 대비, 링크 하나로 시연 가능하고 개발자의 백엔드 경력 서사와 맞는 웹을 선택. 코어 분리로 이 결정이 틀렸어도 회귀 비용이 낮다.

**ADR-3 · 그래프 렌더링은 클라이언트(Plotly), 서버는 데이터만.** 서버 이미지 생성 대비 API가 단순하고 그래프가 인터랙티브. LaTeX 노트에 들어갈 정적 이미지만 예외적으로 서버에서 생성.

**ADR-4 · 동기 API 우선, job queue는 필요가 증명되면.** timeout 30초 내 동기 응답으로 시작. Celery급 인프라는 현 규모에서 복잡도만 추가.

**ADR-5 · ngspice는 subprocess, PySpice 미사용.** 공유 라이브러리 바인딩의 플랫폼별 설치 문제를 회피하고 Docker에서 버전 고정.

**ADR-6 · 자체 netlist 확장은 SPICE와 이름 충돌 없이 짓고, 변환 계층으로 격리.** `.tf` 재정의 대신 `.out` 채택. 자체 확장(기호 값, 인라인 `IC=`, `.out`)은 spice_io.py에서 순수 ngspice 방언으로 변환해 검증 경로에 넘긴다. 파서·엔진의 표현력과 SPICE 호환성을 서로 독립적으로 진화시키기 위함.

**ADR-7 · MNA 유도 기록은 스탬프 델타 + 체크포인트 렌더링.** 소자별 전체 행렬 LaTeX 스냅숏은 기록량이 소자 수 × n²으로 폭발. 델타(위치·항)만 기록해도 교육적 서사는 재구성 가능하고, 전체 행렬은 노트 생성 시 체크포인트에서만 렌더링한다.

---

## 12. 성장 시 재검토 항목

사용자가 늘거나 기능이 확장되면 다음을 재검토한다: 동기 API → 비동기 job(응답 지연 불만 발생 시), 무상태 → SQLite(공유 링크 도입 시), 소자 상한 15 → 수치-우선 하이브리드 모드(대형 회로 요구 시), KaTeX 조각 렌더 → 서버측 PDF 미리보기(노트 활용도가 높아질 시), 결합 인덕터 `K` 스탬프 추가(변압기·공진 회로 예제 수요 발생 시), H(s) 기본 풀이 경로 LUsolve ↔ Cramer(M1 벤치마크 결과에 따라, §4.5).

---

## 부록 A. 변경 이력

| 버전 | 날짜 | 변경 |
|---|---|---|
| v0.1 | 2026-07-02 | 초안 |
| v0.2 | 2026-07-02 | 리뷰 반영: `.tf`→`.out` 및 ngspice 변환 계층 spice_io.py 신설(ADR-6), MNA 기록을 스탬프 델타+체크포인트로 변경(ADR-7), Routh 조건부 판정 2단계 출력 및 API `stability` 스키마 확장, positive 가정 심볼 생성, Cramer 대안 경로 벤치마크 계획, 전압원 루프·전류원 cut-set 검출 구현 힌트 명시, Windows multiprocessing 오버헤드 대응(설정형 timeout), 결합 인덕터를 비목표로 명문화 |

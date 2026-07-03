# CircuitSage 로컬 개발 실행 (Windows PowerShell)
#   .\scripts\dev.ps1          # 의존성 점검 후 API(8000) + Vite(5173) 실행
# 처음 한 번은 저장소 루트에서 실행하세요.

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

function Assert-Command($name, $hint) {
    if (-not (Get-Command $name -ErrorAction SilentlyContinue)) {
        Write-Host "[미설치] $name — $hint" -ForegroundColor Red
        exit 1
    }
}

Assert-Command python "https://www.python.org/downloads/ 에서 Python 3.10+를 설치하세요."
Assert-Command node "https://nodejs.org 에서 Node.js 22+를 설치하세요."
Assert-Command npm "Node.js 설치에 포함됩니다."

if (-not (Get-Command ngspice -ErrorAction SilentlyContinue) -and
    -not (Get-Command ngspice_con -ErrorAction SilentlyContinue)) {
    Write-Host "[선택] ngspice가 PATH에 없습니다 — 수치 교차 검증만 비활성화되고, 심볼릭 해석은 정상 동작합니다." -ForegroundColor Yellow
}

if (-not (Test-Path ".venv")) {
    Write-Host "가상환경 생성 및 패키지 설치 중..."
    python -m venv .venv
    & .\.venv\Scripts\python -m pip install -q -e "core[dev]" -e "api[dev]"
}

if (-not (Test-Path "web\node_modules")) {
    Write-Host "프런트엔드 의존성 설치 중..."
    Push-Location web; npm ci --no-fund --no-audit; Pop-Location
}

Write-Host "API:  http://127.0.0.1:8000  /  Web: http://localhost:5173" -ForegroundColor Green
$api = Start-Process -PassThru -NoNewWindow .\.venv\Scripts\python -ArgumentList "-m","uvicorn","circuitsage_api.main:app","--port","8000"
try {
    Push-Location web
    npm run dev
} finally {
    Pop-Location
    if ($api -and -not $api.HasExited) { Stop-Process -Id $api.Id -Force }
}

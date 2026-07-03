# Contributing to CircuitSage

## Development setup

```bash
# Backend (Python 3.10+)
python -m venv .venv
# Windows: .\.venv\Scripts\Activate.ps1   Unix: source .venv/bin/activate
python -m pip install -e "core[dev]" -e "api[dev]"

# Frontend (Node 22+)
cd web && npm ci
```

Or run the helper scripts, which check dependencies and start both servers:
`./scripts/dev.sh` (Unix) / `.\scripts\dev.ps1` (Windows PowerShell).

ngspice is optional; without it the cross-verification tests skip and the
verification API reports `unavailable`.

## Before opening a pull request

```bash
python -m pytest core/tests api/tests   # backend suites
cd web
npm run lint                            # oxlint
npm test                                # vitest (unit + jsdom)
npm run build                           # TypeScript strict + production build
```

Benchmarks (`python core/benchmarks/bench.py`) are not part of CI; run them
when touching the solver and update `docs/benchmarks.md` if the numbers or
backend-selection evidence change.

## Known pitfall: npm lockfile on Windows

Installing a new package on Windows with an existing `node_modules` can drop
Linux-only optional entries (e.g. `@emnapi/*`) from `package-lock.json`, which
breaks `npm ci` in CI and Docker. After adding web dependencies, verify:

```powershell
Select-String -Path web/package-lock.json -Pattern "@emnapi/core" -Quiet
```

If it returns `False`, delete `web/node_modules` and `web/package-lock.json`
and run a clean `npm install`.

## Guidelines

- Keep the dependency direction one-way: `web → api → core`. The `core`
  package must not import anything from the API layer.
- Correctness first: every new analysis feature needs a hand-derived golden
  test, and bug fixes need a regression test.
- Symbolic performance claims belong in `docs/benchmarks.md` with measured
  numbers, not in prose.
- Commit messages follow the conventional style used in the history
  (`feat(core): …`, `fix(api): …`, `docs: …`).

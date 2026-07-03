# Symbolic solve benchmarks

Reproduce with:

```bash
python core/benchmarks/bench.py             # full table (per-backend columns)
python core/benchmarks/bench.py --quick     # smaller ladder sizes
python core/benchmarks/bench.py --auto-only # end-to-end auto path only
```

All numbers below were measured on the development machine
(Windows 11, Python 3.13, SymPy 1.14). They are **machine-dependent
measurements, not performance guarantees** — symbolic cost depends on
expression structure, and circuits outside this suite can behave
differently. That is exactly why the API keeps the process-level
timeout and complexity guards regardless of backend choice.

## Recorded full run

Times in milliseconds. `lu_*` = `Matrix.LUsolve` path, `cramer_*` =
single-output Cramer via division-free Berkowitz determinants.
`*_solve` is the linear solve, `*_cancel` the final rational
normalization of H(s). `total_auto` is the end-to-end
`transfer_function` with automatic backend selection **as recorded at
the time of this run (threshold 6)** — see the corrected table below.

| case | dim | symbols | parse | topology | assemble | lu_solve | lu_cancel | cramer_solve | cramer_cancel | pole_zero | ilt_step | total_auto | auto_backend |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| numeric ladder N=8 | 10 | 1 | 2.5 | 1.8 | 0.7 | 61.3 | 0.1 | 20.6 | 0.0 | 0.2 | - | 6.2 | lusolve |
| repeated-symbol ladder N=6 | 8 | 3 | 0.1 | 0.5 | 0.6 | 44.7 | 156.5 | 867.7 | 2.5 | 1.2 | - | 85.4 | lusolve |
| unique-symbol ladder N=3 | 5 | 7 | 0.1 | 0.5 | 0.8 | 35.3 | 196.0 | 236.7 | 5.3 | 2.5 | - | 100.3 | cramer |
| unique-symbol ladder N=4 | 6 | 9 | 0.2 | 0.8 | 0.8 | 49.0 | 1277.6 | 610.8 | 17.2 | 6.3 | - | 298.0 | cramer |
| unique-symbol ladder N=5 | 7 | 11 | 0.1 | 0.6 | 0.9 | 33.6 | 80182.8 | 1667.1 | 42.7 | 28.8 | - | 722.4 | cramer |
| RC low-pass (symbolic) | 3 | 3 | 0.1 | 0.4 | 0.4 | 2.5 | 3.0 | 6.3 | 0.7 | 2.4 | 16.3 | 2.0 | lusolve |
| RLC series (symbolic) | 4 | 4 | 0.0 | 0.2 | 0.3 | 5.7 | 13.4 | 51.5 | 1.4 | 10.5 | - | 8.5 | lusolve |
| bridge (numeric) | 4 | 1 | 0.2 | 0.4 | 0.5 | 2.7 | 0.1 | 7.0 | 0.0 | 0.2 | 1.9 | 2.1 | lusolve |
| bridge (unique symbols) | 4 | 6 | 0.1 | 0.3 | 0.6 | 36.5 | 4475.7 | 100.5 | 4.3 | 0.9 | - | 74.8 | cramer |
| three V-source branches | 7 | 5 | 0.2 | 0.5 | 0.7 | 28.1 | 1239201.9 | 377.5 | 5.6 | 1.6 | - | 501459.3 | lusolve |

A second independent full run reproduced the same shape, including
`lu_cancel` ≈ 2 876 s for the three-V-source case.

## Where the time actually goes

Parsing, topology validation, and MNA assembly are negligible (< 2 ms)
in every case. The linear solve itself is cheap on both backends. **The
bottleneck is the final rational normalization (`cancel`) of the LU
output**: `LUsolve` produces nested pivot fractions whose size explodes
combinatorially with the number of *independent* symbols —
`lu_cancel` goes 0.1 ms → 156 ms → 4.5 s → 80 s → 1 239 s as symbols
grow, while the same normalization after the division-free
Cramer/Berkowitz path stays in single-digit milliseconds because the
determinants are already polynomial-form.

Repeated symbolic values (the repeated-symbol ladder) behave like a
small symbol count: what matters is independent parameters, not
component count. This is why the complexity guard counts symbols, and
why a component-count limit alone was insufficient.

## Backend selection (implemented in `_choose_backend`)

| symbols | evidence | chosen |
|---|---|---|
| 0–2 (numeric) | LU always wins (ladder N=8: 6 ms vs 21 ms solve) | `lusolve` |
| 3–4 | LU wins by 2–10× (repeated ladder, RLC) | `lusolve` |
| ≥ 5 | LU downside is unbounded (5 symbols + 3 V-source branches: 20–48 **minutes** in `lu_cancel`; Cramer 0.45 s). Cramer's overhead when it "loses" is only a few ms. | `cramer` |

The threshold was initially set to 6 from the ladder/bridge data; the
three-V-source case showed a catastrophic LU blow-up at 5 symbols, so
the threshold is 5. End-to-end auto timings after that correction:

| case | dim | symbols | total_auto (ms) | auto_backend |
|---|---|---|---|---|
| numeric ladder N=8 | 10 | 1 | 34.0 | lusolve |
| repeated-symbol ladder N=6 | 8 | 3 | 153.1 | lusolve |
| unique-symbol ladder N=3 | 5 | 7 | 161.7 | cramer |
| unique-symbol ladder N=4 | 6 | 9 | 429.5 | cramer |
| unique-symbol ladder N=5 | 7 | 11 | 1748.0 | cramer |
| RC low-pass (symbolic) | 3 | 3 | 7.0 | lusolve |
| RLC series (symbolic) | 4 | 4 | 31.2 | lusolve |
| bridge (numeric) | 4 | 1 | 3.1 | lusolve |
| bridge (unique symbols) | 4 | 6 | 120.2 | cramer |
| three V-source branches | 7 | 5 | **552.3** | cramer |

(The per-backend columns are independent of the heuristic, so only the
auto column needed re-measurement; before the correction the last row's
auto path took ~490 s.)

`CIRCUITSAGE_SOLVER=lusolve|cramer` overrides the automatic choice, and
an explicit `backend=` argument to `transfer_function` overrides both.
If a non-default backend fails unexpectedly, the solve falls back to
`lusolve` and marks `fallback_used` in the solver diagnostics
(available through the API `options.debug` flag).

## Paths that were evaluated and not adopted

* **Full-vector solve for H(s)** — `transfer_function` needs one output
  component; Cramer computes exactly that. The full LU vector is still
  used by `solve_node_voltages`, which genuinely needs every node.
* **Skipping normalization** — deferring `cancel` just moves the blow-up
  into pole/zero extraction and the report; normalizing once directly
  after the solve remains the cheapest point (and the Cramer path makes
  that normalization trivial).
* **`simplify()`/`factor()` cleanups** — rejected long ago in the design
  (§4.5): exponential worst case, no benefit over `cancel` here.

## Known limits

Beyond ~11 unique symbols even the Cramer path grows quickly (1.7 s at
the N=5 unique ladder). The complexity guard (`CIRCUITSAGE_MAX_SYMBOLS`,
default 16 local / 6 public-demo) and the solve timeout remain the
actual safety net; nothing in this document promises that an arbitrary
circuit finishes within any particular time.

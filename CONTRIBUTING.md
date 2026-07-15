# Contributing

## Testing

### Time budget

The test suite is kept fast so PR feedback stays tight. The rule:

- **An individual test should finish in ~2 s, with a 5 s hard ceiling** on CI
  hardware.
- The **PR fast lane** (`.github/workflows/test.yml`) should complete its
  `pytest` step in about **2 minutes**.

If a test is legitimately heavier than the ceiling, don't leave it in the fast
lane — give it one of two markers:

| marker | when | runs |
|---|---|---|
| `antenna_computation_check` | a per-design solve that's part of broad catalog coverage (the same solve path repeated design after design) | main only, not per-PR |
| `heavy_mesh` | a benchmark-sized solve (thousands of segments, GBs of RSS, ≫5 s) — not a unit test | never in CI; run manually with `pytest -m heavy_mesh` |

So a test over the ceiling gets **made faster**, **demoted to
`antenna_computation_check`**, or **demoted to `heavy_mesh`**. Prefer making it
faster (smaller mesh, coarser far-field grid, fewer solver calls) when the test
still discriminates the behavior it guards — e.g. a peak-gain comparison across
two backends is invariant to far-field grid step, so a coarse grid keeps the
check while cutting the cost.

### The guardrail

`tests/conftest.py` surfaces any **unmarked** test whose call phase exceeds the
ceiling: a loud terminal section lists the offenders at the end of the run. CI
also prints `--durations=15`. Two env vars tune it:

- `ANTENNAKNOBS_TIME_BUDGET_CEILING_S` — override the 5 s ceiling.
- `ANTENNAKNOBS_ENFORCE_TIME_BUDGET=1` — turn the report into a hard failure
  (off by default, since absolute call times drift with hardware; CI can enable
  it once the numbers are calibrated).

### Lanes

- **Fast lane (PRs):** `pytest -m "not antenna_computation_check and not heavy_mesh" tests/`
- **Full lane (push to main):** `pytest -m "not heavy_mesh" tests/` (adds the
  per-design catalog + coverage)
- **Benchmarks (manual):** `pytest -m heavy_mesh`

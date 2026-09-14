# The AK suite against momwire main, before momwire 0.55.0 is released

Registered before any run.
- **Branch:** local `pin/momwire-0.55.0`, off AK origin/main 55552f4b4.
- **Pushing:** it stays unpushed until 0.55.0 is on PyPI. At that point it
  becomes the pin PR.

## Environment

- **momwire:** a detached worktree at momwire origin/main **925678d48**, built
  with `make build` (18 compile lines).
  - It is imported through `PYTHONPATH`, ahead of the venv's editable momwire.
  - `momwire.__file__` was confirmed to resolve into that worktree.
- **antennaknobs:** a worktree at AK origin/main **55552f4b4**. Its momwire
  submodule sits at the recorded pointer **495b6c951**, which declares 0.54.0.
  - The root checkout's submodule, which Steve's dev server imports, is neither
    used nor moved.
- **Python:** the root `.venv` (3.14.4), with `PYTHONPATH=<mw>/src:<ak>/src`.
- **What momwire main adds over the pointer:** U4 (momwire#1058: 3030630,
  aba353c, dc908ba), plus scratch records only.

## Lanes

- **L1, the PR fast lane as CI runs it.**
  - Command: `python -m pytest -m "not antenna_computation_check and not heavy_mesh" -n 4 tests/`
  - This is `test.yml`'s fast-lane filter, run with `-n 4`.
- **L2, the buried subset of the heavier lane.**
  - Command: `python -m pytest -m antenna_computation_check -k "buried or below or sommerfeld or crossing or radial" -n 4 tests/`
  - **Why not `-m slow`.** AK defines no `slow` marker, so
    `-m slow -k "buried or below or sommerfeld or crossing or radial"` collects
    0 of 5231 tests and would pass vacuously.
  - **What stands in for it.** AK's heavier lane is `antenna_computation_check`,
    which CI's push-to-main full suite includes. With the same `-k` it collects
    36 tests.
- **Neither lane runs `heavy_mesh`.** A bare `pytest tests` would also run
  `heavy_mesh`, the benchmark-sized solves that CI never runs.

## Predictions

| id | prediction |
|---|---|
| Q1 | **L1 fails exactly two tests,** both in `tests/test_below_reach_preflight_1135.py`, and both because U4 now serves past the cap. `test_the_issues_own_case_refuses_by_name` asserts that soil B at length 1.2 and radial 1.5 refuses. `test_the_threshold_sits_where_the_issue_measured_it` asserts that radial 0.95 refuses. |
| Q2 | **`test_the_preflight_agrees_with_the_solve` passes all 10 parametrizations.** #1058's notes counted it as a third re-pin. But its body only asserts that the preflight and momwire's own check agree, and under U4 both serve past the cap. |
| Q3 | **Nothing else in L1 fails.** Skips come only from environment gates: no NEC-5 binary, and no xnec2c checkout. |
| Q4 | **L2 passes all 36** (blind). |

**Reading rule.** Any failure that Q1 does not name counts as unexpected. Step 2
(the release preconditions) does not start until it has been diagnosed and
reported.

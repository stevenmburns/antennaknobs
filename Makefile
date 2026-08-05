# Named development lanes (issue #733). The point is that each lane is a
# command you can type, not an incantation you must remember — and that the
# fast lane is EXACTLY the PR CI gate's pytest invocation, so "make test
# passed" and "CI will pass" mean the same thing.
#
# Lane economics (measured 2026-08-05, 4-core box):
#   make test    ~59 s  — what the PR gate runs: skips the per-design solver
#                          catalogs (antenna_computation_check) and the
#                          benchmark-class heavy_mesh solves. 66% of the full
#                          suite's wall time is in those 172 deselected tests.
#   make gates   ~3 min — ruff + the FULL suite (what a merge to main runs,
#                          minus coverage instrumentation). Run once before
#                          /create-pr, not per edit.
#   make frontend ~15 s — tsc --noEmit + vitest, the frontend half of CI.

PY = python -m
FRONTEND = src/antennaknobs/web/frontend

.PHONY: test gates frontend test-all lint

# The PR fast lane, verbatim from .github/workflows/test.yml.
test:
	$(PY) pytest -m "not antenna_computation_check and not heavy_mesh" --durations=15 tests/

# Everything a merge to main will check, locally: lint + the full suite.
gates: lint test-all frontend

# The full suite (still excludes heavy_mesh, same as CI's push lane — those
# are benchmark-class runs invoked manually after nec-import/engine changes).
test-all:
	$(PY) pytest -m "not heavy_mesh" --durations=15 tests/

lint:
	ruff check .
	ruff format --check .

frontend:
	cd $(FRONTEND) && npx tsc --noEmit && npx eslint . --max-warnings=9999 && npx vitest run

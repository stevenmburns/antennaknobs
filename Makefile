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
#   make hooks    installs a pre-push hook (ruff check + format --check,
#                          issue #738) — opt-in per checkout, not run by
#                          anything above automatically.

# Interpreter resolution (issue #1146). Bare `python` is NOT assumed on PATH.
# On a box without it `PY = python -m` died with exit 127 having run ZERO
# tests, and as the non-final command of a compound shell line (one ending in
# `tail`) the wrapper reported exit 0 — a "suite green" claim built on nothing,
# caught only because the run summary had no test count.
#
# Order: an activated venv (existence-CHECKED, so a stale exported VIRTUAL_ENV
# from a dead shell falls through instead of breaking every lane), this repo's
# .venv, then python3. Absolute paths deliberately — invoking `.venv/bin/python`
# relatively emits a sys.prefix RuntimeWarning on every call. An exported or
# command-line PYTHON wins (`?=`), which is the supported override:
# `make PYTHON=/path/to/python <target>`. This mirrors momwire's Makefile,
# whose lanes already worked without activation; the point of #1146 was that
# `make <lane>` was safe in one repo and not the other.
PYTHON ?= $(firstword     $(if $(VIRTUAL_ENV),$(wildcard $(VIRTUAL_ENV)/bin/python))     $(wildcard $(abspath .venv/bin/python))     python3)
PY = $(PYTHON) -m
FRONTEND = src/antennaknobs/web/frontend

# Same resolution for ruff, and for the same reason: `make lint` died with
# "ruff: command not found" on an unactivated shell. It also happens to fix a
# second drift — the venv's ruff is the version ruff.yml pins (0.16.5 today),
# where bare `ruff` was whatever the PATH offered, and CLAUDE.md is explicit
# that the pinned version is the one that means anything here.
RUFF ?= $(firstword \
    $(if $(VIRTUAL_ENV),$(wildcard $(VIRTUAL_ENV)/bin/ruff)) \
    $(wildcard $(abspath .venv/bin/ruff)) \
    ruff)

# A recipe pipeline's exit status is its LAST command's, so a failing pytest
# piped into anything reports success. That is the same shape of lie as the
# 127-with-no-tests above, so the lanes run under pipefail.
SHELL = /bin/bash
.SHELLFLAGS = -o pipefail -c

# Fail with the interpreter NAMED rather than with a bare ImportError or a 127
# from a missing `python`. The message says which interpreter was resolved,
# because "python: command not found" does not tell you that a .venv exists
# three lines up in this file.
define REQUIRE_PY
@$(PYTHON) -c 'import antennaknobs' >/dev/null 2>&1 || { \
	echo "make: '$(PYTHON)' cannot import antennaknobs."; \
	echo "  install it editable:   $(PYTHON) -m pip install -e '.[test]'"; \
	echo "  or name one yourself:  make PYTHON=/path/to/python $@"; \
	exit 1; }
endef

.PHONY: test gates frontend test-all lint hooks

# The PR fast lane, verbatim from .github/workflows/test.yml.
test:
	$(REQUIRE_PY)
	$(PY) pytest -m "not antenna_computation_check and not heavy_mesh" --durations=15 tests/

# Everything a merge to main will check, locally: lint + the full suite.
gates: lint test-all frontend

# The full suite (still excludes heavy_mesh, same as CI's push lane — those
# are benchmark-class runs invoked manually after nec-import/engine changes).
test-all:
	$(REQUIRE_PY)
	$(PY) pytest -m "not heavy_mesh" --durations=15 tests/

lint:
	$(RUFF) check .
	$(RUFF) format --check .

frontend:
	cd $(FRONTEND) && npx tsc --noEmit && npx eslint . --max-warnings=9999 && npx vitest run

# Opt-in: installs a pre-push hook running the lint gate locally (issue
# #738). Not run by any other target — no checkout gets this without asking.
hooks:
	bash scripts/install-hooks.sh

"""Shared pytest setup.

- Force a headless matplotlib backend so plot tests run without a display.
- Expose `needs_pynec`, a skip marker for tests that require the optional
  PyNEC engine (unavailable e.g. on Windows).
- Point the user-design folder at a throwaway temp dir for the whole test
  session, set *before* any `import antennaknobs.web.server` (which scaffolds the folder
  at import time). Keeps the suite from writing TEMPLATE.py / CLAUDE.md into
  the developer's real ~/.antennaknobs. Individual tests can still
  override ANTENNAKNOBS_USER_DIR via monkeypatch — user_designs reads it
  fresh on every refresh().
"""

import importlib.util
import os
import tempfile
import warnings

os.environ.setdefault("MPLBACKEND", "Agg")


def pytest_collection(session):
    """Fail fast when the collected tests and the imported packages come from
    different checkouts (issue #733).

    The editable installs' `__editable__*.pth` files hard-code the MAIN
    checkout's absolute path, so running this venv's pytest from a git
    worktree collects the WORKTREE's tests while importing the main
    checkout's code — every assertion then exercises the wrong source, and
    nothing says so. Comparing each package's resolved location against
    pytest's rootdir turns that silent wrong-code run into an immediate,
    self-explanatory collection error. (Worktree escape hatch:
    `PYTHONPATH=$PWD/src:$PWD/momwire/src` outranks the .pth entries.)
    """
    import pathlib

    import antennaknobs
    import momwire

    root = pathlib.Path(str(session.config.rootpath)).resolve()
    ak_file = pathlib.Path(antennaknobs.__file__).resolve()
    if root not in ak_file.parents:
        raise pytest.UsageError(
            f"antennaknobs imports from {ak_file}, which is outside this "
            f"checkout ({root}). You are almost certainly running from a git "
            "worktree against the main checkout's editable install — the "
            "tests here would silently exercise the OTHER checkout's code. "
            "Fix: PYTHONPATH=$PWD/src (outranks the .pth entries), or a "
            "per-worktree venv (issue #733)."
        )
    # momwire is an exact-pinned dependency, not this repo's own code: a
    # worktree that never touches it can legitimately import the main
    # checkout's copy (worktrees do not populate submodules). Warn — so a
    # deliberate momwire-editing worktree isn't silently wrong — instead of
    # failing the overwhelmingly common momwire-untouched case.
    mw_file = pathlib.Path(momwire.__file__).resolve()
    if root not in mw_file.parents:
        warnings.warn(
            f"momwire imports from {mw_file} (outside {root}); fine unless "
            "this worktree modifies momwire — then run "
            "`git submodule update --init` here and set "
            "PYTHONPATH=$PWD/momwire/src (issue #733).",
            stacklevel=1,
        )


import matplotlib  # noqa: E402

matplotlib.use("Agg", force=True)

import pytest  # noqa: E402

os.environ.setdefault(
    "ANTENNAKNOBS_USER_DIR",
    tempfile.mkdtemp(prefix="antennaknobs_userdesigns_test_"),
)

# Blanket-trust user designs for the suite so tests that load them don't each
# have to grant trust (the trust gate is exercised specifically in
# test_design_trust.py, which turns this flag off per-test).
os.environ.setdefault("ANTENNAKNOBS_TRUST_USER_DESIGNS", "1")

HAS_PYNEC = importlib.util.find_spec("PyNEC") is not None

needs_pynec = pytest.mark.skipif(
    not HAS_PYNEC, reason="PyNEC not installed (engine unavailable on this platform)"
)


# --------------------------------------------------------------------------
# Test time-budget guardrail (issue #393)
# --------------------------------------------------------------------------
# Suite rule: an individual *unmarked* test finishes in ~2 s, 5 s hard
# ceiling. Per-design catalog solves live behind `antenna_computation_check`
# (main-only lane); benchmark-sized solves behind `heavy_mesh` (manual-only).
# This hook surfaces any unmarked test whose call phase breaches the ceiling,
# so a slow test can't drift into the PR fast lane unnoticed. It reports by
# default (a loud terminal section); set ANTENNAKNOBS_ENFORCE_TIME_BUDGET=1 to
# also fail the run. Kept opt-in for hard-fail because absolute call times
# drift with hardware — CI can enable it once the numbers are calibrated.
TIME_BUDGET_CEILING_S = float(
    os.environ.get("ANTENNAKNOBS_TIME_BUDGET_CEILING_S", "5.0")
)
_TIME_BUDGET_EXEMPT_MARKERS = ("antenna_computation_check", "heavy_mesh")
_time_budget_offenders: list[tuple[str, float]] = []


def pytest_runtest_logreport(report):
    if report.when != "call" or report.duration <= TIME_BUDGET_CEILING_S:
        return
    if any(m in report.keywords for m in _TIME_BUDGET_EXEMPT_MARKERS):
        return
    _time_budget_offenders.append((report.nodeid, report.duration))


def pytest_terminal_summary(terminalreporter):
    if not _time_budget_offenders:
        return
    tr = terminalreporter
    tr.section("test time-budget guardrail (issue #393)", sep="!", red=True, bold=True)
    tr.line(
        f"{len(_time_budget_offenders)} unmarked test(s) over the "
        f"{TIME_BUDGET_CEILING_S:.0f}s ceiling:"
    )
    for nodeid, dur in sorted(_time_budget_offenders, key=lambda x: -x[1]):
        tr.line(f"  {dur:6.2f}s  {nodeid}")
    tr.line(
        "Fix: make it faster, or mark it 'antenna_computation_check' "
        "(main-only) / 'heavy_mesh' (manual-only). See the pyproject markers."
    )


def pytest_sessionfinish(session, exitstatus):
    if _time_budget_offenders and os.environ.get("ANTENNAKNOBS_ENFORCE_TIME_BUDGET"):
        session.exitstatus = pytest.ExitCode.TESTS_FAILED

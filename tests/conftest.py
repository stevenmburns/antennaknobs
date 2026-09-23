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

# AK#1492: the library reads ~/.antennaknobs/settings.toml for engine paths and
# the capture folder. Point the whole suite at a file that does not exist, so a
# developer's own settings never reach a test; a test that needs one sets it.
os.environ["ANTENNAKNOBS_SETTINGS"] = os.path.join(
    tempfile.gettempdir(),
    f"antennaknobs-tests-{os.getpid()}-no-such-settings.toml",
)

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

# NEC-5 is licensed, user-supplied software (issue #825): live-engine tests
# run only where $NEC5_EXE points at a binary; parser tests run everywhere
# off the committed fixtures.
from antennaknobs.engines import find_nec5  # noqa: E402


def pair_pynec(builder, *, lossy, ground=None):
    """PyNEC given momwire's coated-wire model by a SECOND, independent
    spelling (momwire#874).

    momwire models a jacket as the Popovic-Nesic PAIR: kernel radius
    a' = a*(b/a)**((eps_r-1)/eps_r) plus the series inductance
    L = (mu0/2pi)*ln(a'/a). Since #1523 PyNECEngine writes the pair itself,
    rescaling LD 5's conductivity for the larger GW radius. This spelling
    folds the conductor into LD 2 instead, so the two can be held equal.

    THREE COUPLED DETAILS, and getting any one wrong reproduces a ~5 % gap
    that reads like a momwire defect:

      1. GW radius = a', not the conductor's a
      2. LD 2 carries L PLUS the conductor's internal REACTANCE X_int/omega
      3. LD 5 dropped, the conductor's R folded into that same LD 2 card,
         because LD 5 derives R from the GW radius which is no longer the
         conductor's

    Details 2 and 3 are exact at the design frequency only: this is a
    single-frequency oracle. Detail 2 bites hardest: momwire's skin loading is
    the exact Bessel internal impedance, so deep in the skin regime X_int ~= R
    (measured 1.4399 and 1.3830 ohm/m on 28 AWG at 14.1 MHz, X/R = 0.961).
    Omitting it turns a 0.1 % agreement into 5.6 %.

    Lives in conftest because two oracle modules need one spelling of it;
    duplicating it is how the three details drift apart.
    """
    import numpy as np

    from antennaknobs.engines import PyNECEngine
    from momwire._wire_loading import (
        equivalent_radius,
        insulation_inductance,
        wire_internal_impedance,
    )

    class _Pair(PyNECEngine):
        def _gw_radius_for(self, t):
            spec = self._wire_spec
            r = self._radius_for(t)
            if spec is not None and spec.insulation_radius:
                return equivalent_radius(
                    r, spec.insulation_radius, spec.insulation_eps_r
                )
            return r

        def _emit_wire_material_cards(self, c):
            spec = self._wire_spec
            if spec is None or not spec.insulation_radius:
                return super()._emit_wire_material_cards(c)
            a = spec.radius if spec.radius else self._wire_radius
            ind = insulation_inductance(
                a, spec.insulation_radius, spec.insulation_eps_r
            )
            if not lossy or spec.conductivity is None:
                return c.ld_card(2, 0, 0, 0, 0.0, ind, 0.0)
            omega = 2.0 * np.pi * self.builder.freq * 1e6
            zint = wire_internal_impedance(omega, a, spec.conductivity)
            c.ld_card(2, 0, 0, 0, zint.real, ind + zint.imag / omega, 0.0)

    return _Pair(builder, ground=ground)


needs_nec5 = pytest.mark.skipif(
    find_nec5() is None, reason="no licensed NEC-5 binary ($NEC5_EXE unset)"
)


def nec5_source_rows(deck, current):
    """A NEC-5 printout holding one ANTENNA INPUT PARAMETERS section for
    `deck`'s EX cards, in card order, as the licensed binary prints it
    (AK#1629) — enough for NEC5Engine's source-row readers, with no binary.

    ``current(k, volts)`` is the k-th card's current. SEG. NO. is the
    ABSOLUTE segment, the tag's offset plus the card's own; the column after
    it is printed as 1 and read by nothing."""
    offsets, total = {}, 0
    for f in (ln.split() for ln in deck.splitlines() if ln.startswith("GW ")):
        offsets[int(f[1])] = total
        total += int(f[2])
    rows = []
    cards = (ln.split() for ln in deck.splitlines() if ln.startswith("EX "))
    for k, f in enumerate(cards):
        tag, seg = int(f[2]), int(f[3])
        v = complex(float(f[5]), float(f[6]))
        i = complex(current(k, v))
        z = v / i
        cells = (v.real, v.imag, i.real, i.imag, z.real, z.imag)
        cells += ((1 / z).real, (1 / z).imag, 0.5 * (v * i.conjugate()).real)
        rows.append(
            f"{tag:4d} {offsets[tag] + seg:5d} 1 "
            + " ".join(f"{x: .4E}" for x in cells)
        )
    return (
        "\n - - - ANTENNA INPUT PARAMETERS - - -\n\n"
        "   TAG   SEG.    VOLTAGE (VOLTS)    CURRENT (AMPS)    IMPEDANCE (OHMS)\n"
        + "\n".join(rows)
        + "\n\n"
    )


def nec5_fake_y_runs(eng, Y, *, reverse=False):
    """Point NEC5Engine `eng`'s `_run` at a fake binary that answers each
    multiport-Y deck as NEC-5 would if `Y` were the structure's admittance: the
    card at 1 V is port j, and every card's current is Y[k, j] (AK#1629).
    ``reverse`` prints the rows backwards, as a printout matched to the wrong
    cards would read. Returns the list the decks it is given are appended to."""
    import numpy as np

    Y = np.asarray(Y)
    decks = []

    def run(deck):
        decks.append(deck)
        cards = [ln.split() for ln in deck.splitlines() if ln.startswith("EX ")]
        volts = [complex(float(f[5]), float(f[6])) for f in cards]
        (j,) = [k for k, v in enumerate(volts) if v == 1.0]
        text = nec5_source_rows(deck, lambda k, _v: Y[k, j])
        if reverse:
            head, _, body = text.partition("(OHMS)\n")
            rows = body.strip("\n").split("\n")
            text = head + "(OHMS)\n" + "\n".join(reversed(rows)) + "\n\n"
        return text

    eng._run = run
    return decks


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


# --------------------------------------------------------------------------
# UTF-8 write-site regression guard (issue #772)
# --------------------------------------------------------------------------
@pytest.fixture
def cp1252_default_open(monkeypatch):
    """Make unpinned text-mode ``open()`` calls land on cp1252 — the stock
    Windows default — for the duration of a test.

    ``monkeypatch.setattr(locale, "getencoding", lambda: "cp1252")`` looks
    like it should work and does not: CPython's ``open()`` resolves its
    default text encoding in C (``io.TextIOWrapper`` calls
    ``_Py_GetLocaleEncoding``/``PyUnicode_GetLocaleEncoding`` internally)
    without consulting the Python-level ``locale`` module, so patching
    ``locale.getencoding`` leaves ``open()`` writing UTF-8 regardless and a
    "regression" test built on it would pass even against unfixed code.
    ``locale.setlocale(locale.LC_CTYPE, "C")`` does reproduce the bug, but it
    mutates global process (not test) state.

    Wrapping ``builtins.open`` itself is the one mechanism that actually
    forces the codec an unpinned write site would get on Windows: any
    ``open(path, "w")`` without an explicit ``encoding=`` — anywhere in the
    call stack, not just at the immediate write site — falls back to cp1252
    for the fixture's lifetime, so a write site missing
    ``encoding="utf-8"`` raises ``UnicodeEncodeError`` here on Linux too.
    Do not "simplify" this back to a ``locale`` patch — see above.
    """
    import builtins

    real_open = builtins.open

    def cp1252_default(file, mode="r", *args, encoding=None, **kwargs):
        if "b" not in mode and encoding is None:
            encoding = "cp1252"
        return real_open(file, mode, *args, encoding=encoding, **kwargs)

    monkeypatch.setattr(builtins, "open", cp1252_default)


def nec2c_printout(deck: str, *, timeout: float = 300) -> str:
    """nec2c's printout for `deck`, run the way `engines.nec2` runs it: from
    the deck's own directory with SHORT relative names. nec2c silently writes
    nothing (and still exits 0) when a file path reaches 80 characters, which
    pytest's per-worker tmp paths under xdist do (`.../popen-gw0/<test>/...`),
    so an absolute path made the NEC-2 gates fail only in parallel runs."""
    import subprocess

    with tempfile.TemporaryDirectory(prefix="n2c") as d:
        with open(os.path.join(d, "g.nec"), "w") as f:
            f.write(deck)
        r = subprocess.run(
            ["nec2c", "-i", "g.nec", "-o", "g.out"],
            cwd=d,
            capture_output=True,
            timeout=timeout,
        )
        out = os.path.join(d, "g.out")
        if r.returncode != 0 or not os.path.exists(out):
            raise AssertionError(
                f"nec2c wrote no printout (rc {r.returncode}): "
                f"{r.stderr.decode(errors='replace')[:400]}"
            )
        with open(out, errors="replace") as f:
            return f.read()

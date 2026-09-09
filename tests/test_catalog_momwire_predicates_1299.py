"""Whole-catalog censuses behind two momwire advisories — antennaknobs#1299.

These two tests came from momwire (`test_arrayblock_no_repeats_972.py` and
`test_fragmentation_fallback_972.py`). Their subject is THIS catalog: each
walks `antennaknobs.designs` with pkgutil and asserts a property over every
design, using a momwire predicate as the instrument. Banking a subset as a
fixture — the fix momwire#988 applied to its own behavioural tests — would
change what they measure, because the catalog IS the measurement.

WHY THEY MOVED. In momwire they ran in no lane and no default local run, and
the second half of that is worse than the first. momwire#988 established that
`importorskip("antennaknobs")` means no CI lane executes a test: no momwire
workflow installs antennaknobs, and antennaknobs' CI does not run momwire's
suite. But these two carried `@pytest.mark.slow` as well, and momwire's
`addopts` deselect `slow` by default — so locally they were DESELECTED, which
does not even print under `-rs`. A skip is at least visible when you ask; a
deselection is not. Measured 2026-09-09 at momwire 020f3bf: `pytest` on those
two files reported "15 passed" with the two censuses silently absent.

Here both packages are installed and the suite runs them on every PR.

UNMARKED ON PURPOSE. `antenna_computation_check` quarantines per-design SOLVE
repetition to the main-only lane. These are geometry only — no solve — and
measured 2.35 s and 3.10 s on the development box, inside the 5 s advisory
ceiling. The ceiling is advisory in CI (nothing sets
ANTENNAKNOBS_ENFORCE_TIME_BUDGET), so a slower runner surfaces them in the
durations section rather than failing, and adding the marker is a one-line
reversal if that becomes noise. Running on every PR is worth more than the
quiet: the whole point of the move is that something executes them.
"""

from __future__ import annotations

import importlib
import pkgutil
import warnings


import antennaknobs.designs as designs_pkg
from antennaknobs.engines.momwire import MomwireEngine


def _catalog_builders():
    """Every importable design module's `Builder`, with its short name.

    A design that will not import is not these tests' business — the catalog's
    own coverage gates that.
    """
    for m in pkgutil.walk_packages(designs_pkg.__path__, designs_pkg.__name__ + "."):
        if m.ispkg:
            continue
        try:
            builder = importlib.import_module(m.name).Builder
        except Exception:  # noqa: BLE001 — an unimportable design is gated elsewhere
            continue
        yield m.name.split("antennaknobs.designs.")[-1], builder


def test_the_catalog_split_is_what_the_arrayblock_advisory_was_argued_from():
    """The census the refuse-vs-advise decision rested on, kept honest.

    If a future change made repeats the common case, refusing would become
    reasonable and this number is the thing that would have to move first.
    Geometry only — no solves.
    """
    from momwire.array_block import ArrayBlockSolver, element_groups

    repeats, no_repeats, errors = [], [], []
    for name, builder in _catalog_builders():
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                eng = MomwireEngine(
                    builder(),
                    solver=ArrayBlockSolver,
                    solver_kwargs={"degree": 2},
                    ground=("finite", 13.0, 0.005),
                )
                part = element_groups(
                    eng._make_solver(wavelength=eng._wavelength_for(builder().freq))
                )
        except Exception:  # noqa: BLE001 — buried decks refuse before the question arises
            errors.append(name)
            continue
        (repeats if part.n_shapes < part.n_elem else no_repeats).append(name)

    assert len(repeats) == 27, sorted(repeats)
    assert len(no_repeats) == 72, len(no_repeats)
    assert len(errors) == 4, sorted(errors)
    # The Yagi class is the reason this advises: multi-element, all distinct.
    for yagi in ("beams.owa_yagi", "beams.moxon", "broadband.lpda"):
        assert yagi in no_repeats


def test_no_catalog_deck_but_the_timing_out_one_trips_the_fragmentation_threshold():
    """The strong version of "a threshold that catches a winner fails".

    Rather than a list of ladder rows, this asserts the predicate over EVERY
    catalog deck that builds a partition: exactly one trips it, and it is the
    one that timed out. Structure only — no solves.
    """
    from momwire.hmatrix import HMatrixSolver

    tripped, clear = [], 0
    for _name, builder in _catalog_builders():
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                b = builder()
                eng = MomwireEngine(
                    b,
                    solver=HMatrixSolver,
                    solver_kwargs={"degree": 2},
                    ground=("finite", 13.0, 0.005),
                )
                sim = eng._make_solver(wavelength=eng._wavelength_for(b.freq))
                frag = sim._fragmentation()
        except Exception:  # noqa: BLE001 — buried decks refuse before the question arises
            continue
        if frag is None:
            clear += 1
        else:
            tripped.append((_name, frag))

    assert clear >= 90, clear
    assert [t[0] for t in tripped] == ["verticals.elt_whip"], tripped
    _far, _n, ratio = tripped[0][1]
    # The margin the threshold rests on, pinned: the runner-up is 0.68.
    assert ratio > 1.4, ratio


def test_the_catalog_is_big_enough_for_these_to_be_censuses():
    """A census over three designs is not a census. If the walk stops finding
    the catalog — a renamed package, a broken `__path__` — both tests above
    would pass vacuously on a handful of designs, which is the shape momwire's
    own gates were caught in twice (#936, #988)."""
    assert sum(1 for _ in _catalog_builders()) >= 100

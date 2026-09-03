"""The buried capability, read rather than guessed — issue #1108, momwire#814.

momwire#814 turns razor's `buried` capability cell True. Before this, nothing
on the antennaknobs side read that cell at all: `MomwireEngine` asked the row
about `extended_kernel`, `singular_enrichment` and `wire_loading` and nothing
else, and the web roster had no buried field. A buried deck on razor therefore
CONSTRUCTED cleanly and failed at solve time with a bare `ValueError` from
inside momwire — and the flip, when it comes, would have changed nothing here
because nothing was asking.

Two things are gated. First the refusal, raised at construction with the
sentence the solver's own row declares. Second, and more important, the PIN
RULE: a momwire that predates the cell answers `refusal("buried")` with
`None` — "served" — and that answer must never be believed. Where the row
cannot be asked, the gate skips and says so (issue #1103), which is the same
shape as issue #966's deleted permissive fallback in the engine.
"""

from __future__ import annotations

from typing import NamedTuple

import pytest

from antennaknobs.designs.verticals.buried_radial_vertical import (
    Builder as BuriedRadialVertical,
)
from antennaknobs.engines.momwire import (
    MomwireEngine,
    _buried_cell_is_declared,
    _buried_refusal,
)
from momwire.bspline import BSplineSolver
from momwire.razor import RazorSolver

SOIL_A = ("finite", 13.0, 0.005)

needs_the_cell = pytest.mark.skipif(
    not _buried_cell_is_declared(RazorSolver),
    reason=(
        "the installed momwire predates the buried capability cell "
        "(momwire#814) — skipped rather than assumed served, issue #1103"
    ),
)


def _engine(solver):
    return MomwireEngine(
        BuriedRadialVertical(), solver=solver, ground=SOIL_A, ground_z=0.0
    )


# ---------------------------------------------------------------------------
# the pin rule — gated on ANY momwire, because it is about the absence
# ---------------------------------------------------------------------------


class _RowWithoutTheCell(NamedTuple):
    """A capability row from a momwire that predates the cell.

    Its `refusal` answers `None` for an unknown cell, which is momwire's real
    behaviour and the trap: `None` is how the row spells SERVED.
    """

    refusals: dict = {}

    def refusal(self, *cells):
        return None


class _OldSolver:
    capabilities = _RowWithoutTheCell()


def test_a_row_without_the_cell_really_does_answer_served():
    """The trap this whole file exists for, pinned so it cannot be forgotten:
    asking an old row about `buried` does not raise and does not say no."""
    assert _OldSolver.capabilities.refusal("buried") is None
    assert _OldSolver.capabilities.refusal("buried", "crossing_junction") is None


def test_the_gate_declines_to_answer_rather_than_answering_served():
    """So the engine must not take that `None` as permission. On a row it
    cannot ask, `_buried_refusal` returns None — the same value it returns for
    a served deck — but `_buried_cell_is_declared` is what separates the two,
    and it is False here."""
    assert _buried_cell_is_declared(_OldSolver) is False
    buried_polyline = [[(0.0, 0.0, -0.15), (5.0, 0.0, -0.15)]]
    assert _buried_refusal(_OldSolver, buried_polyline, [], 0.0) is None


def test_free_space_never_asks_the_question():
    assert (
        _buried_refusal(RazorSolver, [[(0.0, 0.0, 1.0), (0.0, 0.0, 9.0)]], [], None)
        is None
    )


# ---------------------------------------------------------------------------
# the refusal itself
# ---------------------------------------------------------------------------


@needs_the_cell
def test_razor_refuses_the_buried_catalog_deck_at_construction():
    """Before this it constructed and failed mid-solve with an internal
    message. The sentence must be the ROW's, not a copy."""
    declared = RazorSolver.capabilities.refusal("buried", "crossing_junction")
    assert declared is not None, "this gate is about the pre-flip row"
    with pytest.raises(ValueError) as exc:
        _engine(RazorSolver)
    assert str(exc.value).endswith(declared)
    assert "cannot solve this design's buried geometry" in str(exc.value)


@needs_the_cell
def test_bspline_is_untouched():
    """The family that has served buried decks since momwire#553 must not be
    caught by a check written for the one that has not."""
    engine = _engine(BSplineSolver)
    assert engine._polylines


@needs_the_cell
def test_the_flip_makes_the_engine_construct_with_no_second_edit(monkeypatch):
    """The flipped arm, patched on the ROW because the row is what the engine
    reads — `_SERVE_BURIED` is consumed at import to build a class attribute,
    so monkeypatching the constant cannot reach it."""
    caps = RazorSolver.capabilities
    monkeypatch.setattr(
        RazorSolver,
        "capabilities",
        caps._replace(
            buried=True,
            refusals={
                k: v
                for k, v in caps.refusals.items()
                if k not in ("buried", "buried+crossing_junction")
            },
        ),
    )
    engine = _engine(RazorSolver)
    assert engine._polylines


@needs_the_cell
def test_the_deck_decides_which_cell_is_asked():
    """momwire#850's separate cell, reached through this engine: the catalog's
    bonded screen has a declared crossing junction, so it earns the crossing
    sentence and not the base one."""
    with pytest.raises(ValueError) as exc:
        _engine(RazorSolver)
    assert "cross the interface at a junction" in str(exc.value)
    assert "has no buried fill" not in str(exc.value)


# ---------------------------------------------------------------------------
# the roster
# ---------------------------------------------------------------------------


def _roster():
    import antennaknobs.web.examples  # noqa: F401 - breaks the adapter's cycle
    from antennaknobs.web.adapter import backend_roster

    return {b["name"]: b for b in backend_roster(have_pynec=True, have_nec5=False)}


def test_every_backend_carries_a_buried_field():
    for name, entry in _roster().items():
        assert "buried" in entry, name
        assert entry["buried"] in (True, False, None), (name, entry["buried"])


def test_a_non_momwire_backend_answers_none():
    """PyNEC's buried scope is its own wrapper's (it refuses a wire below
    z = 0 outright); it is not a momwire capability row, and the roster says
    so rather than inventing an answer."""
    assert _roster()["pynec"]["buried"] is None


@needs_the_cell
def test_the_roster_reports_what_the_rows_declare():
    r = _roster()
    assert r["bspline"]["buried"] is True
    assert r["razor-2p"]["buried"] is RazorSolver.capabilities.buried


def test_an_unaskable_row_reports_none_and_not_false():
    """Three states, not two. `False` means "this backend cannot"; `None`
    means "nobody here knows yet" — and on a momwire without the cell every
    momwire backend must be None, never False, or the frontend would render a
    confident wrong answer."""
    if _buried_cell_is_declared(RazorSolver):
        pytest.skip("the installed momwire declares the cell; nothing to infer")
    r = _roster()
    assert all(
        entry["buried"] is None for entry in r.values() if entry["kind"] == "momwire"
    )

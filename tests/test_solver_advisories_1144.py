"""The solver advisory channel (antennaknobs#1144).

momwire raises `UserWarning` subclasses during a solve, composed from measured
rows and carrying real numbers about THIS deck. Nothing caught them, so the UI
showed none and antennaknobs#1143 shipped a static note as a stand-in.

Two things make these tests fussier than they look.

CACHE STATE. momwire emits `SurfaceRadialHeight` inside `_build_basis_
polynomials`, PAST its module-level `_BASIS_POLY_CACHE` hit return — so a
repeat solve of one deck emits nothing at all, and a test that ran second
would pass on an empty channel (momwire#927). Every gate here that expects an
advisory clears momwire's caches first. That is the empty-result-satisfies-
the-check trap: the absence of a bad row is not the presence of a good one.

THE NO-NOISE HALF. A channel that shows something on every solve becomes noise
and gets ignored, which is worse than not having one. So the clean-deck gate
is not a formality — it is half the contract, and it is asserted on the same
decks the app actually ships.

Gates:

- G-1144-1  the engine captures momwire's advisories, keyed by MODULE so no
            list of classes can rot, and dedupes them.
- G-1144-2  it captures nothing on a clean deck — the no-noise gate.
- G-1144-3  non-momwire warnings raised inside the capture still escape it.
- G-1144-4  the solve response carries the field, on every backend.
- G-1144-5  the #1143 static note no longer claims advisories are unsurfaced.
"""

from __future__ import annotations

import warnings

import pytest

import antennaknobs.web.server as server  # noqa: F401 — resolves the cycle
import momwire.bspline as _bs
from antennaknobs.designs.dipoles.invvee import Builder as InvVee
from antennaknobs.designs.verticals.buried_radial_vertical import (
    Builder as BuriedRadialVertical,
)
from antennaknobs.engines.momwire import (
    MomwireEngine,
    _is_momwire_advisory,
)

GROUND = ("finite", 10.0, 0.002)


def _cold():
    """momwire's caches, emptied.

    `_BASIS_POLY_CACHE` is the one that matters — it short-circuits the code
    path that emits the advisory, and it deliberately survives across solver
    instances, so a fresh engine is NOT a fresh measurement.
    """
    _bs._GEOMETRY_CACHE.clear()
    _bs._BASIS_POLY_CACHE.clear()


# The advisory is a statement about h and h/a — geometry, not mesh — so the
# gates run the surface variant at a coarse mesh: 0.18 s against 5.1 s at the
# shipped density, and it fires identically (measured, #1144). Anything that
# depended on the mesh would be testing the wrong thing here anyway.
_COARSE = 4


def _surface_deck(nsegs=_COARSE):
    b = BuriedRadialVertical()
    for k, v in BuriedRadialVertical.surface_params.items():
        if k != "ui_params":
            setattr(b, k, v)
    b.nominal_nsegs = nsegs
    return b


def _clean_deck(nsegs=_COARSE):
    b = InvVee()
    b.nominal_nsegs = nsegs
    return b


# --- G-1144-1: the engine captures --------------------------------------


def test_g1144_1_the_engine_captures_the_surface_advisory():
    _cold()
    eng = MomwireEngine(_surface_deck(), ground=GROUND, ground_z=0.0)
    eng.impedance()
    cats = [a["category"] for a in eng.advisories]
    assert "SurfaceRadialHeight" in cats, eng.advisories


def test_g1144_1_the_text_carries_this_decks_own_numbers():
    """The whole point over #1143's static note: the class figures were
    already written down, the deck's own h/a was not."""
    _cold()
    eng = MomwireEngine(_surface_deck(), ground=GROUND, ground_z=0.0)
    eng.impedance()
    text = next(
        a["text"] for a in eng.advisories if a["category"] == "SurfaceRadialHeight"
    )
    assert "h/a" in text
    assert "mm" in text


def test_g1144_1_advisories_are_recognised_by_module_not_by_a_list():
    """The identity test is `category.__module__` rooted at momwire.

    A hardcoded tuple would have been wrong the day it was written: the issue
    names three classes and momwire 0.49.0 defines four.
    """
    from momwire._crossing_fill import CoarseCrossingNode
    from momwire._feed_snap import AmbiguousSite
    from momwire._razor_class import RazorFarMeshClass
    from momwire._surface_height import SurfaceRadialHeight

    for cls in (
        SurfaceRadialHeight,
        CoarseCrossingNode,
        RazorFarMeshClass,
        AmbiguousSite,
    ):
        assert _is_momwire_advisory(cls), cls

    class _Local(UserWarning):
        pass

    assert not _is_momwire_advisory(_Local)
    assert not _is_momwire_advisory(UserWarning)
    assert not _is_momwire_advisory(RuntimeWarning)


def test_g1144_1_the_same_advisory_is_not_served_twice():
    """A request drives several engine calls and a sweep drives one per
    frequency. Without deduping, a 30-point sweep ships 30 copies.

    This reads as a no-op against momwire 0.49.0 and is not: the advisory is
    currently emitted once per cache entry (momwire#927), so the duplication
    this prevents appears the moment that is fixed.
    """
    _cold()
    eng = MomwireEngine(_surface_deck(), ground=GROUND, ground_z=0.0)
    eng.impedance()
    eng.current_distribution()
    eng.impedance()
    keys = [(a["category"], a["text"]) for a in eng.advisories]
    assert len(keys) == len(set(keys)), keys


# --- G-1144-2: the no-noise gate -----------------------------------------


@pytest.mark.parametrize("ground", [None, GROUND])
def test_g1144_2_a_clean_deck_raises_nothing(ground):
    """Half the contract. A channel that speaks on every solve is noise, and
    noise gets ignored — taking the deck-specific advisories with it."""
    _cold()
    kw = {"ground": ground, "ground_z": 0.0} if ground else {}
    eng = MomwireEngine(_clean_deck(), **kw)
    eng.impedance()
    assert eng.advisories == []


def test_g1144_2_an_engine_that_never_solved_has_an_empty_channel():
    eng = MomwireEngine(_clean_deck())
    assert eng.advisories == []


# --- G-1144-3: the capture does not swallow anything else ----------------


def test_g1144_3_non_momwire_warnings_escape_the_capture():
    """`catch_warnings(record=True)` swallows EVERYTHING in its scope. A
    warnings channel whose own construction suppresses warnings would be a
    poor joke, and the failure would be invisible."""
    from antennaknobs.engines.momwire import _captures_advisories

    class _Probe:
        @_captures_advisories
        def run(self):
            warnings.warn("not from momwire", RuntimeWarning, stacklevel=1)
            return 1

    with warnings.catch_warnings(record=True) as rec:
        warnings.simplefilter("always")
        _Probe().run()
    assert [w.category.__name__ for w in rec] == ["RuntimeWarning"]


def test_g1144_3_a_momwire_advisory_is_absorbed_not_re_raised():
    """The other side: the channel exists so the user reads these in the UI,
    not so they also land in the server log on every solve."""
    from antennaknobs.engines.momwire import _captures_advisories
    from momwire._surface_height import SurfaceRadialHeight

    class _Probe:
        @_captures_advisories
        def run(self):
            warnings.warn("surface-ish", SurfaceRadialHeight, stacklevel=1)

    p = _Probe()
    with warnings.catch_warnings(record=True) as rec:
        warnings.simplefilter("always")
        p.run()
    assert [w.category.__name__ for w in rec] == []
    assert p._advisory_recorder.items == [
        {"category": "SurfaceRadialHeight", "text": "surface-ish"}
    ]


# --- G-1144-4: the response shape ----------------------------------------


def test_g1144_4_the_response_carries_the_advisory():
    _cold()
    out = server.solve(
        {
            "geometry": "verticals.buried_radial_vertical",
            "backend": "bspline",
            "ground": True,
            "ground_model": "sommerfeld",
            "n_per_wire": _COARSE,
            "params": {"convention": "surface", "wire_type": "18-awg-pvc"},
        }
    )
    cats = [a["category"] for a in out.get("advisories", [])]
    assert "SurfaceRadialHeight" in cats, out.get("advisories")


def test_g1144_4_the_field_is_present_and_empty_on_a_clean_solve():
    """Served always, `[]` when there are none — so the client never has to
    tell "this backend cannot say" from "this deck raised none"."""
    _cold()
    out = server.solve(
        {
            "geometry": "dipoles.invvee",
            "measurement_freq_mhz": 28.47,
            "design_freq_mhz": 28.47,
            "momwire_model": "bspline",
            "n_per_wire": _COARSE,
        }
    )
    assert out["advisories"] == []


# --- G-1144-5: the #1143 stand-in ----------------------------------------


def test_g1144_5_the_static_note_no_longer_says_advisories_are_unsurfaced():
    note = BuriedRadialVertical._SURFACE_NOTE
    assert "does not surface" not in note
    assert "stand-in" not in note
    assert "advisory" in note.lower(), "the note should point at the live one"
    # The class figures are NOT duplication of the live advisory and must
    # survive: 41/10 is the swing for +-1 mm, the advisory quotes |dR/dh|.
    assert "41" in note and "10" in note

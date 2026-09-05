"""The advisory channel survives a repeat solve (antennaknobs#1144, momwire#927).

The #1144 channel was built against a momwire that emitted `SurfaceRadialHeight`
only on a `_BASIS_POLY_CACHE` MISS, so a repeat solve of one deck carried
nothing. momwire#927 fixed that and AK's pointer moved to it; these are the
gates that hold the fixed behaviour in place from this side, where a user
actually meets it.

TWO CACHES SIT BETWEEN THE SOLVER AND THE RESPONSE, and each can make a naive
gate here worthless in the opposite direction:

  momwire's `_BASIS_POLY_CACHE`  a gate that clears it tests the COLD path and
                                 says nothing about the re-emit — this is the
                                 bug's own shape.
  AK's `_SOLVE_CACHE`            a gate that leaves it warm gets the advisory
                                 out of a cached RESPONSE dict, and passes
                                 identically with momwire#927 unfixed.

So the shape below is deliberate and neither cache is left to chance: the
solve cache is CLEARED before every call (so every call is a real solve) while
momwire's basis cache is left WARM (so calls after the first take the hit
path), and the basis-cache entry count is asserted, because without that this
would quietly degrade into a cold-path test the first time something else
cleared it.

Gates:

- G-1144-6  the surface variant solved repeatedly through the adapter delivers
            the advisory in EVERY response, with `cache_hit` False throughout
            and momwire's basis cache proven warm.
- G-1144-7  the dedupe is load-bearing and is asserted where it actually
            fires, with the raw emission count beside the deduped one.
"""

from __future__ import annotations

import pytest

import antennaknobs.web.server as server
import momwire.bspline as _bs
from antennaknobs.designs.verticals.buried_radial_vertical import Builder
from antennaknobs.engines.momwire import MomwireEngine, _AdvisoryRecorder

GROUND = ("finite", 10.0, 0.002)
COARSE = 4  # the advisory is about h and h/a, not mesh: 0.18 s against 5.1 s

REQ = {
    "geometry": "verticals.buried_radial_vertical",
    "backend": "bspline",
    "ground": True,
    "ground_model": "sommerfeld",
    "n_per_wire": COARSE,
    "params": {"convention": "surface", "wire_type": "18-awg-pvc"},
}


def _surface_builder(nsegs=COARSE):
    b = Builder()
    for k, v in Builder.surface_params.items():
        if k != "ui_params":
            setattr(b, k, v)
    b.nominal_nsegs = nsegs
    return b


def _cats(out):
    return [a["category"] for a in out.get("advisories", [])]


# --- G-1144-6: every repeat carries it ------------------------------------


def test_g1144_6_every_repeat_solve_delivers_the_advisory():
    """Three real solves of one deck. Before momwire#927 only the first
    carried the advisory."""
    _bs._GEOMETRY_CACHE.clear()
    _bs._BASIS_POLY_CACHE.clear()

    for call in range(1, 4):
        server._SOLVE_CACHE.clear()  # force a REAL solve, not a cached response
        out = server.solve(dict(REQ))
        assert out["cache_hit"] is False, (call, "the response came from AK's cache")
        assert "SurfaceRadialHeight" in _cats(out), (call, out.get("advisories"))


def test_g1144_6_the_repeats_really_took_momwires_cache_hit_path():
    """Without this the gate above is a cold-path test wearing a disguise.

    One basis-cache entry after several solves of one deck means calls 2 and 3
    HIT it — so the advisory they carried was re-emitted from the stored
    summary (momwire#927) rather than composed fresh. If something clears that
    cache between calls, this fails loudly instead of passing quietly.
    """
    _bs._GEOMETRY_CACHE.clear()
    _bs._BASIS_POLY_CACHE.clear()

    server._SOLVE_CACHE.clear()
    server.solve(dict(REQ))
    entries_after_first = len(_bs._BASIS_POLY_CACHE)
    assert entries_after_first >= 1, "nothing was cached; this proves nothing"

    for _ in range(2):
        server._SOLVE_CACHE.clear()
        out = server.solve(dict(REQ))
        assert "SurfaceRadialHeight" in _cats(out)

    assert len(_bs._BASIS_POLY_CACHE) == entries_after_first, (
        "the later solves added cache entries, so they took the COLD path and "
        "this gate said nothing about momwire#927's re-emit"
    )


def test_g1144_6_a_clean_deck_stays_clean_across_repeats():
    """The no-noise half, repeated: the re-emit must not start inventing
    advisories for decks that never had one."""
    _bs._GEOMETRY_CACHE.clear()
    _bs._BASIS_POLY_CACHE.clear()
    clean = {
        "geometry": "dipoles.invvee",
        "momwire_model": "bspline",
        "design_freq_mhz": 28.47,
        "measurement_freq_mhz": 28.47,
        "n_per_wire": COARSE,
    }
    for _ in range(3):
        server._SOLVE_CACHE.clear()
        assert server.solve(dict(clean))["advisories"] == []


# --- G-1144-7: the dedupe, where it actually fires -------------------------


class _CountingRecorder(_AdvisoryRecorder):
    """Records the RAW emission count beside the deduped list.

    The raw count is what makes the assertion below falsifiable. Asserting
    only "one advisory" would pass on a path that emitted once anyway, which
    is exactly the situation in a single-frequency request — see the note in
    the test.
    """

    def __init__(self):
        super().__init__()
        self.raw = 0

    def absorb(self, recorded):
        self.raw += sum(
            1 for w in recorded if w.category.__module__.split(".")[0] == "momwire"
        )
        super().absorb(recorded)


def test_g1144_7_the_dedupe_collapses_repeated_emissions():
    """Measured (#1144): one engine at three frequencies emits three times and
    serves one.

    Asserted at three FREQUENCIES rather than across engine methods, because
    `_solved_excited` caches its solve on the engine — so impedance(),
    current_distribution() and far_field() in one request share a single MoM
    solve and emit ONCE between them. In that path the dedupe is defensive
    and a gate there would pass with the dedupe deleted. Changing frequency
    misses that cache, which is where the dedupe is load-bearing and where
    removing it turns 1 into 3.
    """
    _bs._GEOMETRY_CACHE.clear()
    _bs._BASIS_POLY_CACHE.clear()
    b = _surface_builder()
    eng = MomwireEngine(b, ground=GROUND, ground_z=0.0)
    eng._advisory_recorder = _CountingRecorder()

    for freq in (7.0, 7.1, 7.2):
        b.freq = freq
        eng.impedance()

    raw = eng._advisory_recorder.raw
    assert raw > 1, (
        f"only {raw} raw emission(s): the engine no longer re-emits per "
        f"frequency, so this test cannot see the dedupe at all"
    )
    assert len(eng.advisories) == 1, eng.advisories


def test_g1144_7_different_text_is_not_deduped_away():
    """The other half. Deduping on (category, text) must not collapse two
    genuinely different sentences of the same class — a user with two decks
    in a session would lose one."""
    from momwire._surface_height import SurfaceRadialHeight

    rec = _AdvisoryRecorder()

    class _W:
        def __init__(self, msg):
            self.message = msg
            self.category = SurfaceRadialHeight
            self.filename = __file__
            self.lineno = 1

    rec.absorb([_W("h/a = 2.1 on this deck"), _W("h/a = 2.1 on this deck")])
    assert len(rec.items) == 1
    rec.absorb([_W("h/a = 3.4 on another deck")])
    assert len(rec.items) == 2, rec.items


def test_g1144_7_a_sweep_carries_the_advisory_once():
    """A 30-point sweep must not ship 30 copies.

    Honest about what this does and does not prove: `impedance_sweep` builds
    ONE solver for the whole sweep, so it emits once whether or not the
    dedupe exists. This pins the served count; the test above is the one that
    fails when the dedupe is removed.
    """
    _bs._GEOMETRY_CACHE.clear()
    _bs._BASIS_POLY_CACHE.clear()
    eng = MomwireEngine(_surface_builder(), ground=GROUND, ground_z=0.0)
    zs = eng.impedance_sweep([7.0, 7.05, 7.1, 7.15, 7.2])
    assert len(zs) == 5
    cats = [a["category"] for a in eng.advisories]
    assert cats.count("SurfaceRadialHeight") == 1, cats


@pytest.mark.parametrize("n", [1, 3])
def test_g1144_7_the_count_does_not_grow_with_repeats(n):
    _bs._GEOMETRY_CACHE.clear()
    _bs._BASIS_POLY_CACHE.clear()
    eng = MomwireEngine(_surface_builder(), ground=GROUND, ground_z=0.0)
    for _ in range(n):
        eng.impedance()
    assert len(eng.advisories) == 1

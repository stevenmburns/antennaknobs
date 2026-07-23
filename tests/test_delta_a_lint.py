"""Catalog-wide Δ/a headroom lint (issue #484): every design must be able
to SCALE to the census top rung (N=641) without any wire's segment length
falling under ~2× its radius — the reduced-kernel thin-wire floor (NEC-2
guideline: Δ/a > 8 for <1 % error, "reasonable solutions" down to ~2;
below ~1 the discretized equation is ill-posed and the sin/pulse/pynec
family produces garbage).

The check computes each design's actual headroom N_max by bisection over
geometry-only builds (scripts/bench_delta_a_headroom.py) — the folded
family shipped exactly this defect class: a 0.1 m link carrying the full
nominal count hit Δ/a = 0.62 at N=321 and the folded element's stub
antiresonance amplified the localized breakdown into 280−1188j (vs the
true 223−30j). See the #484 mechanism comments.

Fat-conductor designs (tube whips, fat elements) legitimately cap early —
their measured headroom is recorded below so a *regression* (a builder
change shrinking it further) still fails, without demanding physics they
cannot deliver.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import bench_delta_a_headroom as hd  # noqa: E402

from antennaknobs.cli import list_builtin_designs  # noqa: E402

CENSUS_TOP_RUNG = 641

# Deck-faithful designs whose wire list reproduces an external model
# verbatim (mixed hand-chosen counts are the point). Everything else
# must mesh at uniform density.
DECK_FAITHFUL = {"verticals.elt_whip"}


def _seg_ratio(builder_cls, n):
    """Max/min segment length over the refining (ns > 1) wires at nominal
    ``n``, or None if fewer than two such wires. 1-segment wires stay out
    of the ratio: density rounding legitimately produces them on short
    wires (max(1, ...)), and a geometry-only scan cannot tell those from
    legacy fixed counts — the solve-level census polices the latter (cf.
    the trap-wire study under #521: even a 1-seg load wire left behind
    by a refining mesh biases the answer, so legacy 1-seg counts are
    being retired, not blessed)."""
    import math

    b = builder_cls()
    b.nominal_nsegs = n
    segs = [
        math.dist(w[0], w[1]) / int(w[2])
        for w in b.build_wires()
        if int(w[2]) > 1 and math.dist(w[0], w[1]) > 0
    ]
    if len(segs) < 2:
        return None
    return max(segs) / min(segs)


# Fat/short-conductor designs whose radius bounds refinement before the
# census top rung — physics, not builder defects. Values are the measured
# headroom (2026-07-22, floor 2.0) rounded DOWN a little so ordinary
# geometry jitter doesn't flap the test; a real regression (density
# defect reintroduced) craters headroom by ~an order of magnitude and
# fails regardless. Rebalance deliberately if a design's conductors
# change.
FAT_CONDUCTOR_HEADROOM = {
    "beams.owa_yagi": 85,  # measured 92 — fat tube driven element
    "beams.owa_yagi_6el": 100,  # measured 107 — 3/16"-equivalent tube (2m)
    "verticals.elt_whip": 155,  # measured 169 — deck-faithful whip (#435)
    # The KJ6ER whips re-measured 2026-07-23 after the auto-mesh conversion
    # (#525 stage 2): the halfwave whips now carry their density-correct
    # count (~1.5-2 quarter-waves' worth instead of one nominal), so the
    # same physical Δ/a floor is reached at a proportionally lower nominal
    # N. The conductors are unchanged.
    "verticals.pota_performer": 330,  # measured 350 — stainless whip
    "verticals.challenger": 270,  # measured 292 — aluminum tube
    # moxon / moxonarray were listed here at 515 ("fat elements") until the
    # #522 density fix revealed the low headroom was the DEFECT, not the
    # conductors: with every wire at driver-arm density they measure ~1840.
    "verticals.dominator": 270,  # measured 292 — one aluminum tube
    "specialty.hourglass": 545,  # measured 593 — short crossing rails
}


@pytest.mark.parametrize("name", sorted(list_builtin_designs()))
def test_design_scales_to_census_top_rung(name):
    import importlib

    mod = importlib.import_module(f"antennaknobs.designs.{name}")
    target = FAT_CONDUCTOR_HEADROOM.get(name, CENSUS_TOP_RUNG)
    got = hd.n_max(mod.Builder)
    assert got >= target, (
        f"{name} Δ/a headroom is N_max={got}, below its floor {target}: "
        f"some wire's segment length falls under {hd.FLOOR}× its radius "
        "before that mesh. If a short wire carries a long wire's segment "
        "count, derive it with segs_for (issue #484); if the design's "
        "conductors legitimately got fatter, update "
        "FAT_CONDUCTOR_HEADROOM deliberately."
    )


def test_twoband_fan_sin_ladder_stays_flat():
    """The #484 "4b" repro rung: with the feed-split links at a fixed 5
    segments the sin basis drifted monotonically off the Galerkin value as
    the arms refined past them (63.4 Ω at N=321, 67.0 at 641, vs the
    bs1/bs2-agreed ~56 Ω). With the links refining at arm density the
    ladder holds ~55.8−7.4j at N=321."""
    from momwire import SinusoidalSolver

    from antennaknobs.designs.multiband.twoband_fan_dipole import Builder
    from antennaknobs.engines.momwire import MomwireEngine

    b = Builder()
    b.nominal_nsegs = 321
    z = MomwireEngine(b, solver=SinusoidalSolver).impedance()[0]
    assert abs(z - (55.8 - 7.4j)) < 3.0, z


@pytest.mark.parametrize("name", sorted(list_builtin_designs()))
def test_segment_density_is_uniform(name):
    """Every refining wire in a design must carry roughly the same segment
    length (issue #521/#522): a wire meshed out of step with its junction
    partners is the catalog's most-recurring defect class — over-dense
    short wires (folded links, fan risers, moxon tails) or fixed counts
    the rest of the mesh refines past (twoband links, hexbeam spacers).
    Builders get this by construction via ``AntennaBuilder.auto_mesh``
    (return None counts); a builder that hand-assigns counts must still
    land within the bound. The 3.0 tolerance passes benign rounding
    (short wires quantize to few segments, ~2x worst) and fails every
    defect this class has produced (4.3-10.7x). Explicit integer counts
    are legacy — allowed, not recommended — and get no special
    treatment here: the mesh they produce must satisfy the same
    bound."""
    import importlib

    if name in DECK_FAITHFUL:
        pytest.skip("deck-faithful wire list")
    mod = importlib.import_module(f"antennaknobs.designs.{name}")
    r = _seg_ratio(mod.Builder, 321)
    if r is not None:
        assert r <= 3.0, (
            f"{name}: segment lengths differ {r:.1f}x across wires at "
            "N=321. Mesh every wire at one density — return None counts "
            "and finish build_wires with self.auto_mesh (issues "
            "#521/#522)."
        )


@pytest.mark.parametrize("name", sorted(list_builtin_designs()))
def test_segment_density_ratio_does_not_grow(name):
    """A fixed segment count next to refining wires leaves the junction
    ever more graded as N climbs — invisible at N=321's snapshot if the
    count is generous (twoband_fan's 5-seg links passed 6.7x there but
    hit the census as a 55.7->67.0 ohm drift). The tell is the ratio
    GROWING with N; a healthy mesh's ratio is flat in N. (auto_mesh
    designs pass by construction; only legacy explicit counts can trip
    this.)"""
    import importlib

    if name in DECK_FAITHFUL:
        pytest.skip("deck-faithful wire list")
    mod = importlib.import_module(f"antennaknobs.designs.{name}")
    r61, r641 = _seg_ratio(mod.Builder, 61), _seg_ratio(mod.Builder, 641)
    if r61 is not None and r641 is not None:
        assert r641 <= r61 * 1.5, (
            f"{name}: segment-length ratio grows {r61:.2f} -> {r641:.2f} "
            "from N=61 to N=641 — some wire carries a fixed count while "
            "its junction partners refine (issue #484/#521 class). Mark "
            "the count None and let auto_mesh assign it."
        )


def test_moxon_sin_ladder_stays_flat():
    """The #522 repro rung: with every wire carrying the full nominal count
    the short folded tails ran 6.7x over-dense (right at the critical tip
    gap) and sin walked off the Galerkin value (39.2−21.2j at N=321 vs the
    bs1/bs2-agreed 43.5−16.4j). At uniform driver-arm density sin lands on
    bs2 to 0.0% there."""
    from momwire import SinusoidalSolver

    from antennaknobs.designs.beams.moxon import Builder
    from antennaknobs.engines.momwire import MomwireEngine

    b = Builder()
    b.nominal_nsegs = 321
    z = MomwireEngine(b, solver=SinusoidalSolver).impedance()[0]
    assert abs(z - (43.5 - 16.4j)) < 2.0, z


def test_folded_invvee_sin_ladder_stays_flat():
    """The #484 repro rung: before the density fix the sin basis broke to
    232.9−230.2j at N=161 (and −1188j at 321). With wire 3 at arm density
    the ladder holds the basis-agreed 223−30j."""
    from antennaknobs.engines.momwire import MomwireEngine
    from momwire import SinusoidalSolver

    from antennaknobs.designs.dipoles.folded_invvee import Builder

    b = Builder()
    b.nominal_nsegs = 161
    z = MomwireEngine(b, solver=SinusoidalSolver).impedance()[0]
    assert abs(z - (223 - 30j)) < 5.0, z

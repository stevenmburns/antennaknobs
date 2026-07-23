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
    "verticals.pota_performer": 330,  # measured 360 — stainless whip
    "verticals.challenger": 380,  # measured 413 — aluminum tube
    "arrays.moxonarray": 515,  # measured 561 — fat moxon elements
    "beams.moxon": 515,  # measured 563
    "verticals.dominator": 525,  # measured 571 — one aluminum tube
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

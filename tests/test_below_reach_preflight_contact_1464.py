"""AK#1464: a deck with nothing strictly below the plane is never pre-flighted.

momwire's `below_reach_refusal` keeps every point AT or below the plane, so a
ground-contact end reads as buried there. Two contact ends at different places
then pair at depth sum 0, which gives theta = 0 at any spacing and R1 equal to
their distance. The engine used to hand it every vertex, so a deck with no
buried wire at all was refused on a below/below limit that the fill never
applies to it:
- `wire.terminated_longwire` (two ground terminations) was refused on range;
- two ground-mounted verticals were refused on the grazing floor.

momwire's fill serves both under finite ground: 450.06-21.37j and
26.80-32.82j Ohm on the laptop, 2026-09-13.
"""

import numpy as np
import pytest

from antennaknobs.cli import get_builder
from antennaknobs.engines.momwire import MomwireEngine, _below_reach_refusal

pytest.importorskip("momwire")

SOIL_A = ("finite", 13.0, 0.005)

TWO_CONTACT_VERTICALS = [
    np.array([(0.0, 0.0, 20.0), (0.0, 0.0, 0.0)]),
    np.array([(0.0, 12.0, 20.0), (0.0, 12.0, 0.0)]),
]


def _builder(name):
    b = get_builder(name)
    return b() if isinstance(b, type) else b


def test_two_contact_ends_are_not_a_below_below_pair():
    """The vertex helper alone reads this pair as theta = 0. Nothing is
    buried, so the engine must not ask it."""
    from momwire import below_reach_refusal

    pts = np.concatenate(TWO_CONTACT_VERTICALS)
    assert "theta = 0 deg" in below_reach_refusal(pts, 0.0, (13.0, 0.005), 3.5e6)
    assert (
        _below_reach_refusal(
            TWO_CONTACT_VERTICALS, 0.0, (13.0, 0.005), "sommerfeld", 3.5
        )
        is None
    )


def test_the_terminated_longwire_constructs_over_finite_ground():
    """Its two terminations are in-plane vertices 180 m apart. The old
    pre-flight refused the design on the below/below range."""
    MomwireEngine(_builder("wire.terminated_longwire"), ground=SOIL_A)


def test_a_wire_strictly_below_is_still_asked():
    """The guard is 'strictly below', not 'no crossing': a catalog BRV corner
    momwire still refuses is refused by momwire's own sentence.

    Until momwire 0.55.0 this used the #1135 corner at spade depth, which
    refused on the below/below range. 0.55.0 serves that range (momwire#1058),
    so the corner here is one the grazing floor still refuses: radials twice
    the UI's longest (`radial_factor` 3.0) buried 20 mm deep. Their widest
    pairs sit at 0.030 deg, under the 0.05 deg floor with margin, as measured
    on momwire main (925678d48). A shallower rise cannot be spelled at all: the
    design's graded rise needs more than its 12.5 mm node panel."""
    from antennaknobs.designs.verticals.buried_radial_vertical import Builder

    b = Builder()
    b.length_factor, b.radial_factor, b.depth = 1.2, 3.0, 0.02
    with pytest.raises(ValueError, match="below/below pair elevation"):
        MomwireEngine(b, ground=("finite", 20.0, 0.03))

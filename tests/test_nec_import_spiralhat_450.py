"""Regression for issue #450: a spiral capacity-hat vertical imported from a
NEC deck must reproduce the NEC-2 driving-point impedance.

The hats are dense stacks of short, tightly-coupled wires the deck meshes with
EVEN segment counts (2, 4). The engines used to blanket-coerce every wire to
their basis parity (odd for PyNEC / Sinusoidal), bumping those hat wires 2→3 and
4→5; on this tightly-coupled structure that shifted the modelled capacitance
enough to flip the driving-point reactance sign (nec2c 25.0 − 64.5j vs a buggy
33.9 + 116.0j). Coercion now touches only the fed wire, so the imported geometry
tracks NEC again.

nec2c reference (run on the original deck): 25.02 − 64.50j.
"""

from __future__ import annotations

import pytest

from antennaknobs import AntennaBuilder, WireSpec
from antennaknobs.nec_import import parse_nec

pytest.importorskip("PyNEC")
from antennaknobs.engines.pynec import PyNECEngine  # noqa: E402

# The 10 MHz spiral-hat vertical dipole (Cebik). Fed at the base segment of a
# fat central mast (tag 12), with square capacity hats above and below built
# from even-segment wires — the trigger for the coercion bug.
_SPIRALHAT_10 = """\
CM vert dpl w/spiral hat: 10 MHz
CE
GW 1,2,.2638504,.2638504,1.066679,.4221607,.4221607,1.066679,.0010262
GW 2,4,.4221607,.4221607,1.066679,.4221607,-.4221607,1.013909,.0010262
GW 3,4,.4221607,-.4221607,1.013909,-.4221607,-.4221607,1.013909,.0010262
GW 4,4,-.4221607,-.4221607,1.013909,-.4221607,.4221607,1.013909,.0010262
GW 5,4,-.4221607,.4221607,1.013909,.4221607,.4221607,1.013909,.0010262
GW 6,4,.4221607,.4221607,1.013909,.4221607,-.4221607,.9611391,.0010262
GW 7,4,.4221607,-.4221607,.9611391,-.4221607,-.4221607,.9611391,.0010262
GW 8,4,-.4221607,-.4221607,.9611391,-.4221607,.4221607,.9611391,.0010262
GW 9,4,-.4221607,.4221607,.9611391,.4221607,.4221607,.9611391,.0010262
GW 10,2,.4221607,.4221607,.9611391,.4221607,0.,.9611391,.0010262
GW 11,2,.4221607,0.,.9611391,0.,0.,.9611391,.0010262
GW 12,21,0.,0.,.9611391,0.,0.,4.7244,.0111125
GW 13,2,0.,0.,4.7244,.4221607,0.,4.724539,.0010262
GW 14,2,.4221607,0.,4.724539,.4221607,.4221607,4.724539,.0010262
GW 15,4,.4221607,.4221607,4.724539,-.4221607,.4221607,4.724539,.0010262
GW 16,4,-.4221607,.4221607,4.724539,-.4221607,-.4221607,4.724539,.0010262
GW 17,4,-.4221607,-.4221607,4.724539,.4221607,-.4221607,4.724539,.0010262
GW 18,4,.4221607,-.4221607,4.724539,.4221607,.4221607,4.671769,.0010262
GW 19,4,.4221607,.4221607,4.671769,-.4221607,.4221607,4.671769,.0010262
GW 20,4,-.4221607,.4221607,4.671769,-.4221607,-.4221607,4.671769,.0010262
GW 21,4,-.4221607,-.4221607,4.671769,.4221607,-.4221607,4.671769,.0010262
GW 22,4,.4221607,-.4221607,4.671769,.4221607,.4221607,4.618999,.0010262
GW 23,2,.4221607,.4221607,4.618999,.2638504,.2638504,4.588519,.0010262
GE 1
FR 0,1,0,0,10.125
GN 2,0,0,0,13.,.005
EX 0,12,1,0,1.414214,0.
EN
"""


def _import_builder(deck):
    tups = deck.wire_tuples(specs=True)
    net = deck.network()

    class B(AntennaBuilder):
        default_params = {"freq": 10.125}

        def build_wires(self):
            return tups

        def build_network(self):
            return net

        def build_wire_material(self):
            return WireSpec(radius=deck.dominant_radius())

    return B()


def test_spiralhat_import_matches_nec2c_reactance_sign():
    """The imported vertical must land near nec2c's 25.0 − 64.5j — capacitive
    (X < 0), not the pre-fix inductive 33.9 + 116j."""
    deck = parse_nec(_SPIRALHAT_10, name="spiralhat10", network=True)
    z = PyNECEngine(_import_builder(deck), ground=("finite", 13.0, 0.005)).impedance()[
        0
    ]
    assert z.imag < 0, f"reactance sign flipped (issue #450): Z={z:.2f}"
    assert z.real == pytest.approx(25.0, abs=2.0), f"R off nec2c: Z={z:.2f}"
    assert z.imag == pytest.approx(-64.5, abs=3.0), f"X off nec2c: Z={z:.2f}"


def test_spiralhat_hat_wires_keep_even_segment_count():
    """The even-segment hat wires (unfed) survive import+coercion unchanged —
    the fix is preserving their count, not re-meshing them (issue #450)."""
    deck = parse_nec(_SPIRALHAT_10, name="spiralhat10", network=True)
    eng = PyNECEngine(_import_builder(deck), ground=("finite", 13.0, 0.005))
    # Hat wires were authored with 2 or 4 segments; none should have been
    # bumped to an odd count. The only odd-forced wire is the 1-seg fed base.
    counts = sorted({t[2] for t in eng.tups})
    assert 4 in counts and 2 in counts, f"hat segment counts altered: {counts}"

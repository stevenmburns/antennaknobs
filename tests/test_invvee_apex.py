"""dipoles.invvee_apex — the apex-fed vee, and what the bridge idiom
is worth (issue #898 piece 5).

Values measured 2026-08-12 at the stock 10 m defaults in free space;
pins sit just above measurement. The POINT of the pair of pins is the
gap between them: the bridge-feed reading and the true-vertex reading
are both right for their own model, and this file keeps their distance
a measured number instead of folklore.
"""

import numpy as np
import pytest

from antennaknobs.designs.dipoles.invvee import Builder as Bridge
from antennaknobs.designs.dipoles.invvee_apex import Builder as Apex
from antennaknobs.engines.momwire import MomwireEngine

# Stock defaults, free space, momwire d=2 (2026-08-12).
Z_BRIDGE = 55.107 - 10.284j
Z_APEX = 54.458 - 12.376j


def _z(builder_cls):
    return complex(MomwireEngine(builder_cls(), ground=None).impedance()[0])


@pytest.mark.antenna_computation_check
def test_apex_and_bridge_readings_are_pinned():
    zb, za = _z(Bridge), _z(Apex)
    assert abs(zb - Z_BRIDGE) < 0.5, f"bridge moved: {zb:.3f}"
    assert abs(za - Z_APEX) < 0.5, f"apex moved: {za:.3f}"


@pytest.mark.antenna_computation_check
def test_bridge_idiom_cost_stays_measured():
    """~2.2 Ω at the stock geometry, nearly all reactance (the bridge's
    two extra junctions + 0.1 m of horizontal wire). If this drifts,
    either a feed model changed or the geometry did — both worth seeing."""
    dz = _z(Apex) - _z(Bridge)
    assert 1.0 < abs(dz) < 4.0, f"bridge-vs-apex delta now {dz:.3f}"
    assert abs(dz.imag) > abs(dz.real)  # the cost is reactive


@pytest.mark.antenna_computation_check
def test_apex_vee_solves_end_to_end():
    """The excited path (current distribution + far field) through a
    design driven ONLY by a vertex port — no gap feed anywhere."""
    eng = MomwireEngine(Apex(), ground=None)
    ff = eng.far_field()
    assert np.isfinite(ff.max_gain)
    wires = eng.current_distribution()
    peak = max(np.abs(np.asarray(w.knot_currents)).max() for w in wires)
    assert peak > 0

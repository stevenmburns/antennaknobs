"""`verticals.elevated_buried_counterpoise` drives its radiator against a
real counterpoise.

Until 2026-09-25 the design's feed gap had nothing on its lower end: the
buried screen is detached, so it is connected to neither terminal, and the
source drove a quarter-wave against the gap's own 25 mm half. The driving
point read ~40 - j68,000 ohm on momwire and NEC-5 alike. The fix puts flat
elevated radials on the gap's lower node. These tests pin both halves of
that: the topology (default lane, no solve) and the impedance it buys.
"""

from __future__ import annotations

import pytest

from antennaknobs.designs.verticals.elevated_buried_counterpoise import Builder
from antennaknobs.engines.momwire import MomwireEngine
from antennaknobs.network import as_wire

C_LIGHT = 299792458.0
# The app's ground for a `ground_requirement: "sommerfeld"` design: finite,
# Sommerfeld, at the served soil default (web/adapter.py DEFAULT_GROUND).
SOIL = ("finite", 13.0, 0.005)


def _nodes_touching(wires, point, skip):
    return [
        k
        for k, w in enumerate(wires)
        if k != skip and point in (tuple(w.p0), tuple(w.p1))
    ]


@pytest.mark.parametrize("n_elevated", [1, 2, 4, 8])
def test_both_ends_of_the_gap_reach_a_conductor(n_elevated):
    """A source needs a return path: each terminal of the fed wire must
    touch some other wire. On the pre-fix design the lower end touched
    nothing."""
    b = Builder()
    b.n_elevated = n_elevated
    ws = [as_wire(w) for w in b.build_wires()]
    (fed,) = [k for k, w in enumerate(ws) if w.ex is not None]
    gap = ws[fed]
    top = _nodes_touching(ws, tuple(gap.p1), fed)
    bottom = _nodes_touching(ws, tuple(gap.p0), fed)
    assert top, "nothing on the gap's upper end"
    assert len(bottom) == n_elevated, "the gap's lower end has no counterpoise"
    for k in bottom:
        # Every counterpoise wire stays above the interface, flat at `base`.
        assert ws[k].p0[2] == ws[k].p1[2] == b.base > 0.0


def test_the_gap_foot_is_a_junction_momwire_sees():
    """Through the adapter: the fed polyline starts at a junction with the
    four elevated radials, all above the interface, and there is no crossing
    junction (the deck stays `split`)."""
    from momwire import _medium_spec

    b = Builder()
    engine = MomwireEngine(b, ground=SOIL, ground_z=0.0)
    s = engine._make_solver(wavelength=C_LIGHT / (b.freq * 1e6))
    (feed,) = engine._feeds
    fed_poly = feed[0]
    assert engine._polylines[fed_poly][0].tolist() == [0.0, 0.0, b.base]
    (foot,) = [j for j in engine._junctions if (fed_poly, "start") in j]
    assert len(foot) == 1 + b.n_elevated
    media = s._wire_media()
    assert {media[p] for p, _end in foot} == {_medium_spec.ABOVE}
    assert s._crossing_junctions() == ()


@pytest.mark.antenna_computation_check
def test_default_impedance_is_a_resonant_ground_plane():
    """The app's view of the default (momwire B-spline at its nominal 15,
    finite Sommerfeld soil). A quarter-wave over four elevated radials cut
    to resonance is a few tens of ohms and near-zero reactance; the pre-fix
    feed read |X| ~ 68 kohm. The reactance bound is +/-25 ohm: the measured
    slope is ~19 ohm per 0.1 of `elevated_factor`, so it holds while the
    default stays within ~0.13 of the resonant length."""
    b = Builder()
    b.nominal_nsegs = 15
    z = complex(MomwireEngine(b, ground=SOIL).impedance()[0])
    assert 25.0 < z.real < 60.0, z
    assert abs(z.imag) < 25.0, z

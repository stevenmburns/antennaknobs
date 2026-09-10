"""Issue #1346: a straight wire crossing the ground plane mid-span is split
where its line meets the plane — the app's twin of momwire#667.

momwire serves current across the interface only through a declared
crossing junction and refuses one polyline with points on both sides by
name. The app already ends polylines at every wire end lying in the plane
(#1108), so a design written as two wires meeting at z = 0 has been served
since then; what it lacked was the one-wire spelling, which an imported deck
or a hand-written design produces naturally. Now `split_wires_at_plane`
turns that wire into two meeting in the plane, in the engine and in the tab's
coverage derivation alike, so the tab's sentence and the solve agree.
"""

from __future__ import annotations

import numpy as np
import pytest

from antennaknobs import nec_import
from antennaknobs.builder import AntennaBuilder
from antennaknobs.engines.momwire import MomwireEngine, split_wires_at_plane
from antennaknobs.wire_catalog import GradedSegments, Wire, WireSpec, graded_wire

SOIL = ("finite", 13.0, 0.005)


# --- the splitter --------------------------------------------------------------


def test_free_space_and_non_crossing_tuples_come_back_unchanged():
    tups = [((0, 0, -1.0), (0, 0, 2.0), 6, None)]
    assert split_wires_at_plane(tups, None) is tups
    tups = [((0, 0, 0.5), (0, 0, 2.0), 6, None), ((0, 0, -1.0), (0, 0, 0.0), 3, None)]
    assert split_wires_at_plane(tups, 0.0) is tups


def test_a_crossing_wire_splits_at_the_exact_point_with_the_count_shared():
    out = split_wires_at_plane([((0, 0, -1.0), (0, 0, 3.0), 8, None)], 0.0)
    assert len(out) == 2
    first, second = (Wire(*t) if not isinstance(t, Wire) else t for t in out)
    assert first.p0 == (0, 0, -1.0) and first.p1 == (0.0, 0.0, 0.0) and first.n_seg == 2
    assert (
        second.p0 == (0.0, 0.0, 0.0) and second.p1 == (0, 0, 3.0) and second.n_seg == 6
    )
    # a slanted wire meets the plane where its LINE does
    out = split_wires_at_plane([((0, 0, -1.0), (4.0, 0, 1.0), 1, None)], 0.0)
    assert Wire(*out[0]).p1 == pytest.approx((2.0, 0.0, 0.0))
    assert Wire(*out[0]).n_seg == 1 and Wire(*out[1]).n_seg == 1


def test_indices_stay_stable_and_specs_are_carried():
    spec = WireSpec(radius=0.002)
    tups = [
        Wire((0, 0, 1.0), (1, 0, 1.0), 4, None, "port_a"),
        Wire((0, 0, -1.0), (0, 0, 3.0), 8, None, None, spec),
        Wire((0, 0, 3.0), (0, 0, 5.0), 4, 1 + 0j),
    ]
    out = split_wires_at_plane(tups, 0.0)
    assert [Wire(*t).name for t in out[:3]] == ["port_a", None, None]
    assert Wire(*out[2]).ex == 1 + 0j  # the feed wire kept its index and its ex
    assert Wire(*out[1]).spec is spec and Wire(*out[3]).spec is spec


def test_fed_named_and_graded_wires_are_never_split():
    tups = [
        Wire((0, 0, -1.0), (0, 0, 3.0), 8, 1 + 0j),
        Wire((0, 0, -1.0), (0, 0, 3.0), 8, None, "port"),
        graded_wire((0, 0, -1.0), (0, 0, 3.0), toward="p1", rest_h=0.5),
    ]
    assert isinstance(Wire(*tups[2]).n_seg, GradedSegments)
    assert split_wires_at_plane(tups, 0.0) is tups


# --- through the importer and the engine ----------------------------------------


RISE, MAST, RADIAL = 0.3, 1.5, 6.334
N_RISE, N_MAST, N_RADIAL = 2, 10, 6


def _deck(single: bool) -> str:
    if single:
        wires = f"GW 1 {N_RISE + N_MAST} 0. 0. -{RISE} 0. 0. {MAST} 0.001\n"
        feed = f"EX 0 1 {N_RISE + 1} 0 1. 0.\n"
    else:
        wires = (
            f"GW 1 {N_RISE} 0. 0. -{RISE} 0. 0. 0. 0.001\n"
            f"GW 2 {N_MAST} 0. 0. 0. 0. 0. {MAST} 0.001\n"
        )
        feed = "EX 0 2 1 0 1. 0.\n"
    return (
        "CE crossing\n"
        + wires
        + f"GW 3 {N_RADIAL} 0. 0. -{RISE} {RADIAL} 0. -{RISE} 0.001\n"
        + f"GW 4 {N_RADIAL} 0. 0. -{RISE} -{RADIAL} 0. -{RISE} 0.001\n"
        + "GE 1\nGN 2 0 0 0 13. 0.005\nFR 0 1 0 0 7.1 0.\n"
        + feed
        + "XQ 0\nEN\n"
    )


def _builder(text: str) -> AntennaBuilder:
    deck = nec_import.parse_nec(text, name="crossing")

    class B(AntennaBuilder):
        default_params = {"freq": deck.freq_mhz[0]}

        def build_wires(self):
            return deck.wire_tuples()

        def build_wire_material(self):
            return WireSpec(radius=deck.dominant_radius())

    return B()


@pytest.mark.antenna_computation_check
def test_one_wire_through_the_plane_imports_and_solves_like_two():
    """The one-GW deck splits into the SAME mesh the two-GW deck is written
    with (2 + 10 over 0.3 + 1.5 m), so the two solve to the same Z."""
    two = MomwireEngine(_builder(_deck(single=False)), ground=SOIL).impedance()[0]
    one = MomwireEngine(_builder(_deck(single=True)), ground=SOIL).impedance()[0]
    assert np.isfinite(two) and two.real > 0
    assert abs(one - two) <= 1e-9 * abs(two)


@pytest.mark.antenna_computation_check
def test_the_tab_and_the_engine_agree_on_a_crossing_design():
    """The coverage derivation splits the same way the engine does, so a
    crossing design is reported as needing the crossing junction — served
    on bspline — rather than refused as a mid-span crossing."""
    from antennaknobs.web import server  # noqa: F401  (breaks the adapter import cycle)
    from antennaknobs.web.adapter import _CROSSING_NEED, _design_capability_needs

    class B(AntennaBuilder):
        default_params = {"freq": 7.1}

        def build_wires(self):
            deck = nec_import.parse_nec(_deck(single=True), name="crossing")
            return deck.wire_tuples()

        def build_wire_material(self):
            return WireSpec(radius=0.001)

    needs = _design_capability_needs(B)
    assert "buried" in needs and _CROSSING_NEED in needs

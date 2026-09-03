"""Forced polyline boundaries at the interface — issue #1108.

A conductor that reaches the ground plane and continues above it is ONE
polyline to `flat_wires_to_polylines` (degree 2 at the node) and a refused
mid-span interface crossing to momwire. That mismatch is why the buried
designs spell their radial screens as N COINCIDENT rises: not because anyone
builds a bundle, but because N rises raise the node's degree to N+1 and make
it a junction. The bundle is what NEC-5 refuses outright and what gives
razor's tent basis N identical columns and a singular matrix (momwire#846).

`boundary_ends=` ends a polyline at a named wire END without registering any
port. The split node becomes an ordinary 2-entry junction group, exactly as a
wire-spec change (issue #388) or a cycle cut already does, so KCL still
carries the current through it.

The seam is deliberate and is the point of the two halves being in two files:
the WALK takes an explicit list of ends and knows nothing about grounds;
`MomwireEngine._ends_in_the_plane` is where `ground_z` is known and supplies
that list as a pure geometric rule. No media logic in this package — which
side of the interface a wire is on, and whether a junction actually crosses
it, stay momwire's questions.
"""

from __future__ import annotations

import numpy as np
import pytest

from antennaknobs import resolve_variant_params
from antennaknobs.designs.verticals.buried_radial_vertical import (
    Builder as BuriedRadialVertical,
)
from antennaknobs.engines.momwire import MomwireEngine, _ends_in_the_plane
from antennaknobs.geometry import flat_wires_to_polylines
from antennaknobs.network import Wire

C_LIGHT = 299792458.0
SOIL_A = (13.0, 0.005)


def _chain():
    """Two collinear wires meeting at (0,0,0) — the shape the interface makes:
    one below the plane, one above, sharing a degree-2 node in it."""
    return [
        Wire((0.0, 0.0, -2.0), (0.0, 0.0, 0.0), n_seg=6),
        Wire((0.0, 0.0, 0.0), (0.0, 0.0, 10.0), n_seg=10, ex=1 + 0j),
    ]


# ---------------------------------------------------------------------------
# the walk
# ---------------------------------------------------------------------------


def test_without_it_the_shared_node_is_threaded_through():
    """The behaviour the buried designs had to work around."""
    out = flat_wires_to_polylines(_chain())
    assert len(out["polylines"]) == 1
    assert out["junctions"] == []
    assert out["polylines"][0][0].tolist() == [0.0, 0.0, -2.0]
    assert out["polylines"][0][-1].tolist() == [0.0, 0.0, 10.0]


def test_a_forced_boundary_splits_it_into_a_two_member_junction():
    out = flat_wires_to_polylines(_chain(), boundary_ends=[(0, "p1")])
    assert len(out["polylines"]) == 2
    assert out["junctions"] == [[(0, "end"), (1, "start")]]
    # both halves keep their own mesh, and the node is an endpoint of each
    assert out["polylines"][0][-1].tolist() == [0.0, 0.0, 0.0]
    assert out["polylines"][1][0].tolist() == [0.0, 0.0, 0.0]
    assert out["edge_segments"] == [[6], [10]]


def test_either_end_of_the_shared_node_names_the_same_node():
    """`(0,"p1")` and `(1,"p0")` are the same point, so they must do the same
    thing — the caller should not have to know which wire "owns" the node."""
    a = flat_wires_to_polylines(_chain(), boundary_ends=[(0, "p1")])
    b = flat_wires_to_polylines(_chain(), boundary_ends=[(1, "p0")])
    assert a["junctions"] == b["junctions"]
    assert [p.tolist() for p in a["polylines"]] == [p.tolist() for p in b["polylines"]]


def test_an_already_boundary_node_is_unaffected():
    """Naming a degree-1 end (a plain ground CONTACT) or a degree>=3 node
    changes nothing — which is what keeps every existing design walking
    byte-identically once the engine starts passing plane-lying ends."""
    wires = _chain() + [Wire((0.0, 0.0, 0.0), (5.0, 0.0, 0.0), n_seg=4)]
    plain = flat_wires_to_polylines(wires)
    forced = flat_wires_to_polylines(
        wires, boundary_ends=[(0, "p0"), (0, "p1"), (1, "p0"), (2, "p0"), (2, "p1")]
    )
    assert plain["junctions"] == forced["junctions"]
    assert [p.tolist() for p in plain["polylines"]] == [
        p.tolist() for p in forced["polylines"]
    ]


def test_an_unnamed_node_is_left_alone():
    """A three-wire chain with only its FIRST interior node forced: the second
    stays threaded, so the split is per-node and not a global mode."""
    wires = [
        Wire((0.0, 0.0, -2.0), (0.0, 0.0, 0.0), n_seg=6),
        Wire((0.0, 0.0, 0.0), (0.0, 0.0, 1.0), n_seg=3),
        Wire((0.0, 0.0, 1.0), (0.0, 0.0, 10.0), n_seg=9, ex=1 + 0j),
    ]
    out = flat_wires_to_polylines(wires, boundary_ends=[(0, "p1")])
    assert len(out["polylines"]) == 2
    assert out["junctions"] == [[(0, "end"), (1, "start")]]
    assert out["edge_segments"] == [[6], [3, 9]]


@pytest.mark.parametrize(
    "bad, match",
    [
        ((0, "start"), "must be 'p0' or 'p1'"),
        ((7, "p0"), "produced 2 tuples"),
        ((-1, "p0"), "produced 2 tuples"),
    ],
)
def test_a_bad_boundary_end_names_itself(bad, match):
    with pytest.raises(ValueError, match=match):
        flat_wires_to_polylines(_chain(), boundary_ends=[bad])


# ---------------------------------------------------------------------------
# the engine's geometric rule
# ---------------------------------------------------------------------------


def test_no_ground_means_no_forced_boundaries():
    """Over free space there is no interface, so the walk is untouched — the
    whole free-space catalog walks exactly as it did."""
    assert _ends_in_the_plane(_chain(), None) == ()


def test_every_end_in_the_plane_is_named_and_nothing_else():
    assert _ends_in_the_plane(_chain(), 0.0) == ((0, "p1"), (1, "p0"))
    # a shifted plane names the ends that are in THAT plane
    assert _ends_in_the_plane(_chain(), 10.0) == ((1, "p1"),)
    assert _ends_in_the_plane(_chain(), 3.0) == ()


def test_the_tolerance_is_absolute_metres():
    """It asks "is this endpoint in the plane" — a question about a
    coordinate, not about a wire's length, so a 10 m wire and a 10 mm one get
    the same window."""
    short = [Wire((0.0, 0.0, -0.01), (0.0, 0.0, 1e-7), n_seg=2)]
    assert _ends_in_the_plane(short, 0.0) == ((0, "p1"),)
    off = [Wire((0.0, 0.0, -0.01), (0.0, 0.0, 1e-4), n_seg=2)]
    assert _ends_in_the_plane(off, 0.0) == ()


# ---------------------------------------------------------------------------
# through the engine, on the decks this was built for
# ---------------------------------------------------------------------------


def _solver(builder, **kw):
    engine = MomwireEngine(builder, ground=("finite",) + SOIL_A, ground_z=0.0, **kw)
    return engine, engine._make_solver(wavelength=C_LIGHT / (builder.freq * 1e6))


def test_the_existing_buried_decks_walk_exactly_as_they_did():
    """The coincident-rise default and the detached variant both have their
    plane node at a degree the walk already broke on, so the new rule is a
    no-op for them. Values are the ones they produced before #1108."""
    engine, _ = _solver(BuriedRadialVertical())
    assert len(engine._polylines) == 9
    assert engine._junctions == [
        [(i, "start") for i in range(8)],
        [(1, "end"), (3, "end"), (5, "end"), (7, "end"), (8, "start")],
    ]

    detached, _ = _solver(
        BuriedRadialVertical(
            params=resolve_variant_params(BuriedRadialVertical, "detached")
        )
    )
    assert len(detached._polylines) == 5
    assert detached._junctions == [[(i, "start") for i in range(4)]]


def test_a_single_rise_hub_now_reaches_momwire_as_a_crossing_junction():
    """The deck #1108 exists for, built here rather than in the catalog so
    this gate stands on the WALK alone: one rise from a buried hub to the
    node, the ordinary eps-gap feed above it, no port anywhere near the
    interface. Before #1108 the rise and the radiator were one polyline and
    momwire refused it as a mid-span crossing."""
    from momwire import _medium_spec

    depth, height = 0.15, 10.0
    wires = [
        Wire((0.0, 0.0, -depth), (5.0 * dx, 5.0 * dy, -depth), n_seg=10)
        for dx, dy in ((1, 0), (0, 1), (-1, 0), (0, -1))
    ]
    wires += [
        Wire((0.0, 0.0, -depth), (0.0, 0.0, 0.0), n_seg=4),
        Wire((0.0, 0.0, 0.0), (0.0, 0.0, 0.05), n_seg=1, ex=1 + 0j),
        Wire((0.0, 0.0, 0.05), (0.0, 0.0, height), n_seg=20),
    ]

    class OneRise(BuriedRadialVertical):
        def build_wires(self):
            return wires

    _engine, s = _solver(OneRise())
    assert s._wire_media() == (_medium_spec.BELOW,) * 5 + (_medium_spec.ABOVE,)
    crossing = s._crossing_junctions()
    assert crossing == (1,)
    members = s.junctions[crossing[0]]
    media = s._wire_media()
    assert sum(1 for w, _e in members if media[w] == _medium_spec.ABOVE) == 1
    assert sum(1 for w, _e in members if media[w] == _medium_spec.BELOW) == 1
    # ...and no coincident wires anywhere: exactly one rise
    rises = [w for w in wires if w.p0[2] == -depth and w.p1[2] == 0.0]
    assert len(rises) == 1


def test_without_the_forced_boundary_that_same_deck_is_refused():
    """The negative half, so the gate above cannot pass for the wrong reason:
    hand the same tuples to the walk with no boundary ends and momwire says
    mid-span crossing."""
    depth = 0.15
    wires = [
        Wire((0.0, 0.0, -depth), (5.0, 0.0, -depth), n_seg=10),
        Wire((0.0, 0.0, -depth), (0.0, 5.0, -depth), n_seg=10),
        Wire((0.0, 0.0, -depth), (0.0, 0.0, 0.0), n_seg=4),
        Wire((0.0, 0.0, 0.0), (0.0, 0.0, 10.0), n_seg=20, ex=1 + 0j),
    ]
    from momwire.bspline import BSplineSolver

    out = flat_wires_to_polylines(wires)
    assert len(out["polylines"]) == 3  # the rise and the radiator are ONE
    s = BSplineSolver(
        wires=out["polylines"],
        n_per_edge_per_wire=out["edge_segments"],
        junctions=out["junctions"],
        feeds=out["feeds"],
        wavelength=C_LIGHT / 7.1e6,
        wire_radius=5e-4,
        ground_z=0.0,
        ground_eps=SOIL_A,
        ground_model="sommerfeld",
    )
    with pytest.raises(ValueError, match="crosses the ground interface mid-span"):
        s._wire_media()


def test_the_split_conserves_the_mesh():
    """A forced boundary must not change how finely anything is meshed — it
    moves a polyline edge from one list to another and nothing else."""
    plain = flat_wires_to_polylines(_chain())
    split = flat_wires_to_polylines(_chain(), boundary_ends=[(0, "p1")])
    assert sum(sum(c) for c in plain["edge_segments"]) == sum(
        sum(c) for c in split["edge_segments"]
    )
    assert np.allclose(
        np.concatenate([p for p in plain["polylines"]])[[0, -1]],
        np.array([[0.0, 0.0, -2.0], [0.0, 0.0, 10.0]]),
    )

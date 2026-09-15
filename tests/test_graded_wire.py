"""The graded-wire spelling (momwire#674's node grading as a first-class
``n_seg``): panel math, walk expansion inside ONE polyline, topology
invariance on coincident bundles, direction handling, and the refusals.

Born from the buried-radial default-mesh fix: hand-splitting a graded
rise into separate wires minted spurious 8-member junctions at every
shared split point of the coincident bundle — the spelling exists so
grading can never touch topology.
"""

import itertools
import math

import numpy as np
import pytest

from antennaknobs.engine import refuse_graded_wires
from antennaknobs.geometry import flat_wires_to_polylines
from antennaknobs.network import (
    GradedSegments,
    Wire,
    doubling_graded_wire,
    graded_wire,
)


def test_graded_wire_panel_math_toward_p1():
    """The rise case: 0.15 m toward p1 reproduces the #674 recipe —
    boundaries 12.5 mm and 50 mm from the node, two segments per panel
    (h_node 6.25 mm)."""
    w = graded_wire((0, 0, -0.15), (0, 0, 0), toward="p1")
    assert isinstance(w.n_seg, GradedSegments)
    np.testing.assert_allclose(w.n_seg.fracs, (1 - 0.05 / 0.15, 1 - 0.0125 / 0.15))
    assert w.n_seg.counts == (2, 2, 2)


def test_graded_wire_panel_math_toward_p0_with_rest_h():
    """The radiator case: a long wire graded at p0 keeps its far panel at
    the design segment length via rest_h."""
    w = graded_wire((0, 0, 0.05), (0, 0, 10.05), toward="p0", rest_h=0.5)
    b = [0.0125 * 4**k for k in range(5)]  # 0.0125 .. 3.2, 12.8 > L stops
    np.testing.assert_allclose(w.n_seg.fracs, [x / 10.0 for x in b])
    assert w.n_seg.counts[:-1] == (2,) * 5
    assert w.n_seg.counts[-1] == round((10.0 - 3.2) / 0.5)


def test_graded_wire_rejects_bad_args():
    with pytest.raises(ValueError, match="toward"):
        graded_wire((0, 0, 0), (0, 0, 1), toward="middle")
    with pytest.raises(ValueError, match="h_node"):
        graded_wire((0, 0, 0), (0, 0, 0.01), toward="p1", h_node=0.02)


def _bundle_deck(n=4):
    """A miniature of the buried screen: n radial runs to a hub, n
    COINCIDENT graded rises hub -> node, a fed gap wire + mast above."""
    tups = []
    for k in range(n):
        th = 2 * np.pi * k / n
        tip = (5 * np.cos(th), 5 * np.sin(th), -0.15)
        tups.append(Wire((0, 0, -0.15), tip, 5))
        tups.append(graded_wire((0, 0, -0.15), (0, 0, 0), toward="p1"))
    tups.append(Wire((0, 0, 0), (0, 0, 0.05), 1, ex=1 + 0j))
    tups.append(Wire((0, 0, 0.05), (0, 0, 10.0), 10))
    return tups


def test_bundle_expansion_is_topology_invariant():
    """The load-bearing property: graded rises on a coincident bundle
    expand INSIDE their polylines — same junction set as ungraded single
    rises (hub + node), no junctions at the shared graded vertices."""
    out = flat_wires_to_polylines(_bundle_deck())
    assert len(out["junctions"]) == 2
    sizes = sorted(len(j) for j in out["junctions"])
    assert sizes == [5, 8]  # node: 4 rises + gap; hub: 4 runs + 4 rises
    rises = [
        (pl, segs)
        for pl, segs in zip(out["polylines"], out["edge_segments"], strict=True)
        if len(segs) == 3 and segs == [2, 2, 2]
    ]
    assert len(rises) == 4
    for pl, _ in rises:
        np.testing.assert_allclose(pl[:, 2], [-0.15, -0.05, -0.0125, 0.0])


def test_reversed_walk_reverses_panels():
    """A graded wire the walk traverses p1 -> p0 gets its vertices and
    counts reversed so the fine panels stay at the graded end."""
    tups = [
        Wire((0, 0, 10.0), (0, 0, 0.05), 10, ex=1 + 0j),
        # authored node -> gap-top: p0 is the graded end, and the walk
        # (starting at the degree-1 mast top) reaches it REVERSED
        graded_wire((0, 0, 0), (0, 0, 0.05), toward="p0", h_node=0.01),
    ]
    out = flat_wires_to_polylines(tups)
    (pl,) = out["polylines"]
    (segs,) = out["edge_segments"]
    np.testing.assert_allclose(pl[:, 2], [10.0, 0.05, 0.04, 0.01, 0.0])
    assert segs == [10, 2, 2, 2]


def test_feed_arclength_unmoved_by_expansion():
    """A fed edge later in a polyline than a graded edge keeps its
    arclength (sub-edge lengths sum to the original edge)."""
    graded = [
        graded_wire((0, 0, 0), (0, 0, 1.0), toward="p0", h_node=0.01),
        Wire((0, 0, 1.0), (0, 0, 2.0), 4, ex=1 + 0j),
    ]
    plain = [
        Wire((0, 0, 0), (0, 0, 1.0), 6),
        Wire((0, 0, 1.0), (0, 0, 2.0), 4, ex=1 + 0j),
    ]
    fg = flat_wires_to_polylines(graded)["feeds"]
    fp = flat_wires_to_polylines(plain)["feeds"]
    assert fg[0][1] == pytest.approx(fp[0][1])  # arclength 1.5


def test_graded_wire_cannot_carry_a_feed_or_name():
    fed = graded_wire((0, 0, 0), (0, 0, 1.0), toward="p0")._replace(ex=1 + 0j)
    with pytest.raises(ValueError, match="graded wire"):
        flat_wires_to_polylines([fed, Wire((0, 0, 1.0), (0, 0, 2.0), 4)])
    named = graded_wire((0, 0, 0), (0, 0, 1.0), toward="p0", name="feed")
    with pytest.raises(ValueError, match="graded wire"):
        flat_wires_to_polylines([named, Wire((0, 0, 1.0), (0, 0, 2.0), 4)])


def test_the_remaining_card_engine_refuses_by_name():
    """PyNEC is the only caller left (issue #1108): NEC-5 now EXPANDS a graded
    wire into consecutive GW cards instead of refusing it, so the same deck
    meshes identically on all three engines. The helper's sentence is still
    the right answer for a NEC-2 deck, whose EX/LD/NT tags this package does
    not renumber."""
    with pytest.raises(NotImplementedError, match="graded-mesh spelling"):
        refuse_graded_wires([graded_wire((0, 0, 0), (0, 0, 1.0), toward="p0")], "PyNEC")


# ---------------------------------------------------------------------------
# doubling_graded_wire (AK#1455): neighbours within 2x, capped far panels
# ---------------------------------------------------------------------------


def _segment_lengths(w):
    """A graded wire's segment lengths, p0 first."""
    length = math.dist(w.p0, w.p1)
    edges = [0.0, *w.n_seg.fracs, 1.0]
    out = []
    for k, n in enumerate(w.n_seg.counts):
        out += [(edges[k + 1] - edges[k]) * length / n] * n
    return np.array(out)


def _ak1454_schedule(length, h0, rest):
    """AK#1454's measured schedule as it was run
    (`scratch/1443-counterpoise/step2_source.graded_schedule`), without the
    tail guard, so the promoted helper can be held to it."""
    bounds = []
    b = 2.0 * h0
    while b < length * (1 - 1e-9):
        bounds.append(b)
        b *= 2.0
    edges = [0.0, *bounds, length]
    counts = [
        max(2, math.ceil((hi - lo) / min(rest, max(h0, lo / 2.0)) - 1e-9))
        for lo, hi in itertools.pairwise(edges)
    ]
    return tuple(x / length for x in bounds), tuple(counts)


@pytest.mark.parametrize("length", [0.3, 1.0, 2.5, 6.45, 6.5, 10.507, 12.85, 15.0])
@pytest.mark.parametrize("max_h", [0.06, 0.125, 0.25, 0.5, 1.0])
def test_doubling_graded_wire_steps_within_2x_under_the_cap(length, max_h):
    """Every neighbouring pair within 2x, nothing above the cap, the first
    segment at h0, and the lengths summing to the wire. 6.45 m puts a 5 cm
    tail past the 6.4 m boundary, which the guard must merge."""
    h0 = 0.025
    segs = _segment_lengths(
        doubling_graded_wire((0, 0, 0), (0, 0, length), h0=h0, max_h=max_h)
    )
    assert segs.sum() == pytest.approx(length)
    assert segs[0] == pytest.approx(h0)
    assert segs.max() <= max_h * (1 + 1e-12)
    steps = segs[1:] / segs[:-1]
    assert steps.max() <= 2.0 + 1e-9, steps.max()
    assert steps.min() >= 0.5 - 1e-9, steps.min()


@pytest.mark.parametrize("nominal_nsegs", [21, 42, 84])
def test_doubling_graded_wire_is_ak1454s_schedule_on_the_counterpoise(nominal_nsegs):
    """At `elevated_buried_counterpoise`'s default radiator the helper is the
    schedule AK#1454 measured, count for count: the tail guard does not engage."""
    from antennaknobs.designs.verticals.elevated_buried_counterpoise import Builder

    b = Builder()
    b.nominal_nsegs = nominal_nsegs
    quarter = 0.25 * b.design_wavelength
    length = quarter - 0.05
    max_h = length / b.segs_for(length, quarter)
    assert max_h == pytest.approx(length / nominal_nsegs)  # AK#1454's own cap
    w = doubling_graded_wire((0, 0, 0), (0, 0, length), h0=0.025, max_h=max_h)
    fracs, counts = _ak1454_schedule(length, 0.025, length / nominal_nsegs)
    np.testing.assert_allclose(w.n_seg.fracs, fracs)
    assert w.n_seg.counts == counts


def test_doubling_graded_wire_rejects_bad_args():
    with pytest.raises(ValueError, match="h0"):
        doubling_graded_wire((0, 0, 0), (0, 0, 0.02), h0=0.025, max_h=0.5)
    with pytest.raises(ValueError, match="max_h"):
        doubling_graded_wire((0, 0, 0), (0, 0, 1.0), h0=0.025, max_h=0.01)

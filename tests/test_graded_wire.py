"""The graded-wire spelling (momwire#674's node grading as a first-class
``n_seg``): panel math, walk expansion inside ONE polyline, topology
invariance on coincident bundles, direction handling, and the refusals.

Born from the buried-radial default-mesh fix: hand-splitting a graded
rise into separate wires minted spurious 8-member junctions at every
shared split point of the coincident bundle — the spelling exists so
grading can never touch topology.
"""

import numpy as np
import pytest

from antennaknobs.engine import refuse_graded_wires
from antennaknobs.geometry import flat_wires_to_polylines
from antennaknobs.network import GradedSegments, Wire, graded_wire


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
        for pl, segs in zip(out["polylines"], out["edge_segments"])
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


def test_card_engines_refuse_by_name():
    with pytest.raises(NotImplementedError, match="graded-mesh spelling"):
        refuse_graded_wires(
            [graded_wire((0, 0, 0), (0, 0, 1.0), toward="p0")], "NEC-5"
        )

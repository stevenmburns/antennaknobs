"""A design's repeated geometry, as the fill sees it (AK#2165, momwire#1555).

The counts are pinned to momwire#1555's own table: an aligned Yagi (one
segment length on every element) has 166 distinct segment pairs with three
directors. The rest checks what the report claims: mirror planes found and not
invented, a straight uniform wire with one distinct pair per offset, edge-pair
isometries that really carry the representative onto each member, and the
ground keeping only height-preserving moves.
"""

from __future__ import annotations

import numpy as np

from antennaknobs import AntennaBuilder, Wire
from antennaknobs.structure import (
    analyze,
    edge_pair_classes,
    edges_from_wires,
    edges_of,
    mirror_planes,
    report,
    segment_pair_counts,
)
from antennaknobs.wire_catalog import graded_wire

LAM = 299.792458 / 14.2


def design(wires):
    class B(AntennaBuilder):
        default_params = {"freq": 14.2, "design_freq": 14.2}

        def build_wires(self):
            return wires

    return B()


def yagi(D, aligned=True, h=15.0):
    """momwire#1555's Yagi: reflector, driver and D directors 0.2 wavelength
    apart, 22 / 21 / 20 segments; aligned means one segment length."""
    Ld = 0.47 * LAM
    k = (22 / 21, 1.0, 20 / 21) if aligned else (1.05, 1.0, 0.95)
    elems = [(k[0] * Ld, 22), (Ld, 21)] + [(k[2] * Ld, 20)] * D
    return [
        Wire((0.2 * LAM * i, -L / 2, h), (0.2 * LAM * i, L / 2, h), n_seg=n)
        for i, (L, n) in enumerate(elems)
    ]


def test_an_aligned_yagi_has_momwire_1555s_count():
    edges = edges_from_wires(design(yagi(3)))
    c = segment_pair_counts(edges, mirror_planes(edges))
    assert c["segments"] == 103 and c["pairs"] == 5356
    assert c["repeat"] == 166
    # A horizontal Yagi keeps every element at one height: the same over ground.
    assert segment_pair_counts(edges, (), over_ground=True)["repeat"] == 166


def test_the_boom_plane_is_found_and_no_plane_is_invented():
    planes = mirror_planes(edges_from_wires(design(yagi(3))))
    assert [p.describe() for p in planes] == ["y = 0 m"]
    lopsided = yagi(3) + [Wire((1.0, 0.0, 15.0), (1.0, 3.0, 15.0), n_seg=5)]
    assert mirror_planes(edges_from_wires(design(lopsided))) == []


def test_two_vertical_mirrors_are_both_found():
    """A CED-like cross: arms in +x/-x and +y/-y, each mirrored in both planes."""
    arms = [
        Wire((0, 0.24, 10), (0, 5.7, 10.1), n_seg=27),
        Wire((0.0, 0.24, 10), (1.0, 0.24, 10), n_seg=5),
    ]
    ws = []
    for sx in (1, -1):
        for sy in (1, -1):
            ws += [
                Wire(
                    (sx * a.p0[0], sy * a.p0[1], a.p0[2]),
                    (sx * a.p1[0], sy * a.p1[1], a.p1[2]),
                    n_seg=a.n_seg,
                )
                for a in arms
            ]
    names = sorted(p.describe() for p in mirror_planes(edges_from_wires(design(ws))))
    assert names == ["x = 0 m", "y = 0 m"]
    assert all(p.vertical for p in mirror_planes(edges_from_wires(design(ws))))


def test_a_straight_uniform_wire_has_one_distinct_pair_per_offset():
    edges = edges_from_wires(design([Wire((0, 0, 10), (4 * LAM, 0, 10), n_seg=40)]))
    c = segment_pair_counts(edges)
    assert c["pairs"] == 820 and c["repeat"] == 40


def test_every_member_isometry_carries_the_representative_onto_it():
    edges = edges_from_wires(design(yagi(4, aligned=False)))
    for over_ground in (False, True):
        for cls in edge_pair_classes(edges, over_ground):
            r1, r2 = cls.rep
            for i, j, iso, fi, fj in cls.members:
                for rep, mem, flip in ((r1, i, fi), (r2, j, fj)):
                    a, b = np.asarray(edges[rep].p0), np.asarray(edges[rep].p1)
                    want = (
                        (edges[mem].p1, edges[mem].p0)
                        if flip
                        else (edges[mem].p0, edges[mem].p1)
                    )
                    assert np.allclose([iso(a), iso(b)], want, atol=1e-6)
                if over_ground:
                    assert iso.keeps_heights


def test_identical_directors_share_their_blocks():
    """As meshed, the directors are copies of one another, so a director pair
    at one spacing is one pose however many times it appears: momwire#1555's
    whole-block count, 55 blocks in 3D + 3 = 27 poses at D = 8."""
    s = analyze(design(yagi(8, aligned=False)))
    assert sum(len(c.members) for c in s.classes_free) == 55
    assert len(s.classes_free) == 27
    total, needed = s.block_entries()
    assert total == 203 * 204 // 2 and needed == 10836


def test_the_ground_keeps_only_moves_that_keep_heights():
    """Two equal wires, one flat and one tilted: congruent in free space,
    different over ground."""
    flat = Wire((0, 0, 10), (5, 0, 10), n_seg=10)
    tilted = Wire((0, 3, 10), (4, 3, 13), n_seg=10)
    edges = edges_from_wires(design([flat, tilted]))
    free = {
        len(c.members) for c in edge_pair_classes(edges, False) if c.rep[0] == c.rep[1]
    }
    gnd = [c for c in edge_pair_classes(edges, True) if c.rep[0] == c.rep[1]]
    assert free == {2}  # the two self blocks share
    assert len(gnd) == 2  # over ground they do not


def test_a_graded_wire_is_its_uniform_pieces():
    w = graded_wire((0, 0, 0), (0, 0, -3), toward="p0")
    edges = edges_from_wires(design([Wire((0, 0, 0), (5, 0, 0), n_seg=10), w]))
    pieces = [e for e in edges if e.wire == 1]
    assert len(pieces) == len(w.n_seg.counts) > 1
    assert [e.n for e in pieces] == list(w.n_seg.counts)
    assert np.allclose(pieces[0].p0, (0, 0, 0)) and np.allclose(
        pieces[-1].p1, (0, 0, -3)
    )


def test_the_report_names_what_it_found_and_changes_nothing():
    text = report(analyze(design(yagi(3)), pairs=True))
    assert "mirror planes: y = 0 m" in text
    assert "166 under any repeat" in text
    assert "Read-only" in text


def test_tilted_legs_mirrored_in_a_vertical_plane_share_over_ground():
    """An inverted vee: each leg's self block, and the legs mirrored in the
    vertical plane through the apex, keep sharing over ground. (A fit in 3-D
    turns a tilted line's self pair about itself and tips its heights.)"""
    legs = [
        Wire((0, 0, 7), (0, 2.2, 5.7), n_seg=20),
        Wire((0, 0, 7), (0, -2.2, 5.7), n_seg=20),
    ]
    edges = edges_from_wires(design(legs))
    for over_ground in (False, True):
        selfs = [
            c for c in edge_pair_classes(edges, over_ground) if c.rep[0] == c.rep[1]
        ]
        assert len(selfs) == 1 and len(selfs[0].members) == 2, over_ground


def test_coordinates_at_nec_precision_still_share_over_ground():
    """Three radials at 120 degrees written to 6 significant digits, as a NEC
    deck carries them: the rotation between radials is not exact to 1e-9."""
    ws = []
    for k in range(3):
        a = 2 * np.pi * k / 3
        tip = tuple(float(f"{v:.6g}") for v in (10 * np.cos(a), 10 * np.sin(a), 0.5))
        ws.append(Wire((0.0, 0.0, 0.5), tip, n_seg=20))
    gnd = edge_pair_classes(edges_from_wires(design(ws)), True)
    assert sorted(len(c.members) for c in gnd) == [
        3,
        3,
    ]  # 3 self blocks, 3 radial pairs


def test_every_radial_plane_is_found():
    """A vertical over N radials has N vertical mirror planes; the principal
    axes of an N-fold arrangement are arbitrary, so they alone miss most."""
    for N in (3, 4, 8):
        ws = [Wire((0, 0, 0), (0, 0, 10), n_seg=20)]
        for k in range(N):
            a = 2 * np.pi * k / N
            ws.append(Wire((0, 0, 0), (10 * np.cos(a), 10 * np.sin(a), 0), n_seg=20))
        planes = mirror_planes(edges_from_wires(design(ws)))
        assert len(planes) == N and all(p.vertical for p in planes), (
            N,
            [p.describe() for p in planes],
        )


def test_a_plane_survives_a_half_grid_coordinate():
    """Segment ends at k·L/n can sit exactly on a rounding boundary; a 1-ulp
    difference between the two sides must not lose the plane."""
    for eps in (0.0, 1e-16, -1e-16):
        ws = [
            Wire((0, 0, 5), (0.75, 1, 5), n_seg=8),
            Wire((0, 0, 5), (-0.75 + eps, 1, 5), n_seg=8),
        ]
        assert [p.describe() for p in mirror_planes(edges_from_wires(design(ws)))] == [
            "x = 0 m"
        ], eps


def test_coincident_wires_count_as_a_full_block():
    w = Wire((0, 0, 5), (5, 0, 5), n_seg=10)
    edges = edges_from_wires(design([w, w]))
    assert (
        sum(c.entries * len(c.members) for c in edge_pair_classes(edges))
        == 20 * 21 // 2
    )


def test_the_mesh_is_the_engines():
    """`edges_of` reads the momwire engine's own translation of a fed design,
    and the inverted vee's two legs share over ground there too."""
    import importlib

    b = importlib.import_module("antennaknobs.designs.dipoles.invvee").Builder()
    edges, note = edges_of(b)
    assert note is None and sum(e.n for e in edges) == 41
    legs = [
        c
        for c in edge_pair_classes(edges, True)
        if c.rep[0] == c.rep[1] and edges[c.rep[0]].n == 20
    ]
    assert len(legs) == 1 and len(legs[0].members) == 2

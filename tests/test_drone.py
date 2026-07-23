"""Tests for the 3D-turtle Drone and the delta_loop twins built with it."""

import math

import numpy as np
import pytest

from antennaknobs import Drone, resolve_variant_params
from antennaknobs.designs.loops.delta_loop import Builder as DeltaLoop
from antennaknobs.designs.loops.delta_loop_flyby import Builder as DeltaLoopFlyby
from antennaknobs.designs.loops.delta_loop_reflected import (
    Builder as DeltaLoopReflected,
)
from antennaknobs.designs.loops.delta_loop_topdown import Builder as DeltaLoopTopdown
from antennaknobs.designs.loops.horizontal_loop_drone import Builder as HLoopDrone


def test_starts_facing_world_x():
    d = Drone(position=(1.0, 2.0, 3.0))
    assert d.position == pytest.approx((1.0, 2.0, 3.0))
    assert d.heading == pytest.approx((1.0, 0.0, 0.0))


def test_forward_pays_out_one_edge_when_pen_down():
    d = Drone(ref=1.0)
    d.forward(2.0)  # pen up -> moves (turtle penup) but lays no wire
    assert d.wires() == []
    assert d.position == pytest.approx((2.0, 0.0, 0.0))
    d.pay_out().forward(2.0)
    assert len(d.wires()) == 1
    p0, p1, nsegs, ex = d.wires()[0]
    assert p0 == pytest.approx((2.0, 0.0, 0.0))
    assert p1 == pytest.approx((4.0, 0.0, 0.0))
    assert ex is None  # structural


def test_cut_stops_paying_out():
    d = Drone()
    d.pay_out().forward(1.0).cut().forward(1.0)
    assert len(d.wires()) == 1


def test_jump_and_move_to_lay_no_wire():
    d = Drone()
    d.pay_out().jump(5.0)
    d.move_to((0.0, 1.0, 0.0))
    assert d.wires() == []
    assert d.position == pytest.approx((0.0, 1.0, 0.0))


def test_feed_marks_driven_segment():
    d = Drone()
    d.feed(1 + 0j).forward(0.1)
    _, _, _, ex = d.wires()[0]
    assert ex == 1 + 0j


def test_yaw_is_body_relative():
    d = Drone()
    d.yaw(90)
    assert d.heading == pytest.approx((0.0, 1.0, 0.0))  # +x turned to +y
    d.yaw(90)
    assert d.heading == pytest.approx((-1.0, 0.0, 0.0))


def test_equilateral_triangle_closes_to_machine_eps():
    d = Drone(ref=3.0).pay_out()
    for _ in range(3):
        d.forward(3.0)
        d.yaw(120)
    start = np.array(d.wires()[0][0])
    end = np.array(d.wires()[-1][1])
    assert np.abs(start - end).max() < 1e-9


def test_close_flies_home_with_current_pen():
    d = Drone(ref=1.0).pay_out()
    d.forward(1.0).yaw(120).forward(1.0).yaw(120)
    d.feed(1 + 0j).close(nsegs=3)
    last = d.wires()[-1]
    assert last[1] == pytest.approx(d.wires()[0][0])  # back to the origin
    assert last[2] == 3 and last[3] == 1 + 0j


def test_face_sets_heading_and_keeps_position():
    d = Drone(position=(0.0, 0.5, 7.0))
    d.face(heading=(0.0, 1.0, 1.0), up=(1.0, 0.0, 0.0))
    h = np.array(d.heading)
    assert h == pytest.approx(np.array([0.0, 1.0, 1.0]) / math.sqrt(2.0))
    assert d.position == pytest.approx((0.0, 0.5, 7.0))


def test_face_rejects_parallel_up():
    with pytest.raises(ValueError):
        Drone().face(heading=(1.0, 0.0, 0.0), up=(2.0, 0.0, 0.0))


def test_forward_to_plane_extends_to_axis_aligned_plane():
    # Nose along +x at the origin; fly to the plane x = 3.
    d = Drone(ref=1.0).pay_out()
    d.forward_to_plane((1.0, 0.0, 0.0, 3.0))
    p0, p1, _ns, ex = d.wires()[0]
    assert p0 == pytest.approx((0.0, 0.0, 0.0))
    assert p1 == pytest.approx((3.0, 0.0, 0.0))
    assert ex is None
    assert d.position == pytest.approx((3.0, 0.0, 0.0))


def test_forward_to_plane_solves_the_oblique_distance():
    # Heading +x toward a plane tilted 45 deg (normal (1,1,0)) at distance
    # d = sqrt(2): n_hat . x = 1 => x = 2 on the x axis. The leg length is the
    # solved 2.0, not d.
    d = Drone(ref=1.0).pay_out()
    d.forward_to_plane((1.0, 1.0, 0.0, math.sqrt(2.0)))
    assert d.position == pytest.approx((2.0, 0.0, 0.0))
    assert math.dist(*d.wires()[0][:2]) == pytest.approx(2.0)


def test_forward_to_plane_d_is_a_true_distance_not_scaled_by_normal():
    # (0,0,2,5) and (0,0,1,5) name the SAME plane z = 5 (d is the distance
    # along the unit normal, independent of the passed normal's length).
    for normal_z in (1.0, 2.0):
        d = Drone(ref=1.0).face(heading=(0.0, 0.0, 1.0), up=(1.0, 0.0, 0.0))
        d.pay_out().forward_to_plane((0.0, 0.0, normal_z, 5.0))
        assert d.position == pytest.approx((0.0, 0.0, 5.0))


def test_forward_to_plane_respects_the_pen():
    # Pen up: move to the plane but lay no wire.
    d = Drone(ref=1.0).forward_to_plane((1.0, 0.0, 0.0, 4.0))
    assert d.wires() == []
    assert d.position == pytest.approx((4.0, 0.0, 0.0))


def test_forward_to_plane_already_on_plane_is_a_no_op():
    d = Drone(position=(3.0, 0.0, 0.0), ref=1.0).pay_out()
    d.forward_to_plane((1.0, 0.0, 0.0, 3.0))
    assert d.wires() == []  # no zero-length edge
    assert d.position == pytest.approx((3.0, 0.0, 0.0))


def test_forward_to_plane_rejects_parallel_nose():
    # Nose +x, plane normal +z: never intersects.
    with pytest.raises(ValueError):
        Drone().pay_out().forward_to_plane((0.0, 0.0, 1.0, 5.0))


def test_forward_to_plane_rejects_plane_behind_nose():
    # Nose +x at origin; plane x = -3 is behind: cannot extend forward to it.
    with pytest.raises(ValueError):
        Drone().pay_out().forward_to_plane((1.0, 0.0, 0.0, -3.0))


def test_forward_to_plane_rejects_zero_normal():
    with pytest.raises(ValueError):
        Drone().pay_out().forward_to_plane((0.0, 0.0, 0.0, 1.0))


def test_forward_through_plane_reaches_the_mirror_when_perpendicular():
    # Nose +x at the origin, plane x = 3. The default factor=1.0 flies to the
    # plane and an equal distance past it -- squarely, so it lands on the mirror
    # image (6, 0, 0), laying one edge the full length.
    d = Drone(ref=1.0).pay_out()
    d.forward_through_plane((1.0, 0.0, 0.0, 3.0))
    assert d.position == pytest.approx((6.0, 0.0, 0.0))
    p0, p1, _ns, _ex = d.wires()[0]
    assert p0 == pytest.approx((0.0, 0.0, 0.0))
    assert p1 == pytest.approx((6.0, 0.0, 0.0))


def test_forward_through_plane_factor_scales_the_distance_past():
    # factor is the distance past the plane, in multiples of the approach: from
    # the origin to plane x = 3, factor=2 flies 3 + 2*3 = 9 to (9, 0, 0).
    d = Drone(ref=1.0).pay_out()
    d.forward_through_plane((1.0, 0.0, 0.0, 3.0), factor=2.0)
    assert d.position == pytest.approx((9.0, 0.0, 0.0))


def test_forward_through_plane_is_proportional_overshoot_when_oblique():
    # Heading +x toward the tilted plane whose x-intercept is 2 (normal (1,1,0),
    # d = sqrt(2)). Default factor=1 flies 2 * 2 = 4 ALONG THE NOSE to (4, 0, 0)
    # -- not the geometric mirror of the origin across it (which is (2, 2, 0)).
    d = Drone(ref=1.0).pay_out()
    d.forward_through_plane((1.0, 1.0, 0.0, math.sqrt(2.0)))
    assert d.position == pytest.approx((4.0, 0.0, 0.0))


def test_horizontal_loop_drone_is_a_closed_planar_square():
    b = HLoopDrone()
    wires = b.build_wires()
    # 5 edges: three full sides, two corner-inset stubs, joined by the
    # diagonal feed across corner A (the last edge, via close()).
    assert len(wires) == 5

    # Flat in the z = base plane.
    base = b.default_params["base"]
    zs = {round(p[2], 9) for e in wires for p in (e[0], e[1])}
    assert zs == {base}

    # Exactly one driven segment, one NEC segment long.
    driven = [e for e in wires if e[3] is not None]
    assert len(driven) == 1
    assert driven[0][2] == 1 and driven[0][3] == 1 + 0j

    # The loop closes exactly, and is a connected walk.
    assert wires[0][0] == pytest.approx(wires[-1][1])
    for prev, nxt in zip(wires, wires[1:]):
        assert prev[1] == pytest.approx(nxt[0])


def test_horizontal_loop_drone_feed_is_symmetric():
    # The feed must sit on a mirror plane of the loop or the pattern skews.
    # Corner A is at (-h, -h); the mirror plane is the A-C diagonal x = y.
    b = HLoopDrone()
    wires = b.build_wires()
    (fx0, fy0, _), (fx1, fy1, _), _, _ = next(e for e in wires if e[3] is not None)

    # The driven segment's two ends are mirror images across x = y...
    assert (fx0, fy0) == pytest.approx((fy1, fx1))
    # ...so its midpoint lies on the diagonal (x == y).
    assert (fx0 + fx1) / 2 == pytest.approx((fy0 + fy1) / 2)

    # And the whole loop is invariant under that reflection (x, y) -> (y, x).
    pts = {(round(p[0], 6), round(p[1], 6)) for e in wires for p in (e[0], e[1])}
    assert {(y, x) for (x, y) in pts} == pts


def test_mark_and_line_to_connects_to_a_pinned_node():
    d = Drone(ref=1.0)
    d.pay_out().mark("a")  # pin the origin
    d.forward(2.0)  # -> (2, 0, 0)
    d.yaw(90).forward(2.0)  # -> (2, 2, 0)
    d.line_to("a")  # lay (2,2,0) -> (0,0,0) and move there
    last = d.wires()[-1]
    assert last[0] == pytest.approx((2.0, 2.0, 0.0))
    assert last[1] == pytest.approx((0.0, 0.0, 0.0))
    assert d.position == pytest.approx((0.0, 0.0, 0.0))


def _undirected(builder):
    """{(sorted endpoint pair, is_driven)} for a design's wires, ignoring
    edge order, direction, and segment count."""
    out = set()
    for p0, p1, _ns, ex, *_rest in builder.build_wires():
        a = tuple(round(c, 9) for c in p0)
        b = tuple(round(c, 9) for c in p1)
        out.add((tuple(sorted([a, b])), ex is not None))
    return out


# -- the four same-parameterization delta loops --------------------------------
#
# delta_loop (coordinates), delta_loop_flyby (drone flyby), delta_loop_reflected
# (point-finder + reflection) and delta_loop_topdown (top-down flight) all take
# the same knobs -- base, length_factor, angle_deg -- and must produce
# byte-identical wires. They differ only in how the geometry is specified.


def test_delta_loop_flyby_matches_shipped():
    assert _undirected(DeltaLoopFlyby()) == _undirected(DeltaLoop())


def test_delta_loop_reflected_matches_shipped():
    assert _undirected(DeltaLoopReflected()) == _undirected(DeltaLoop())


def test_delta_loop_topdown_matches_shipped():
    assert _undirected(DeltaLoopTopdown()) == _undirected(DeltaLoop())


def test_four_delta_loops_identical_across_a_second_param_set():
    # The payoff: the same knob set produces identical geometry from every
    # construction, at a different operating point too (z200, not the default).
    p = resolve_variant_params(DeltaLoop, "z200")
    shipped = _undirected(DeltaLoop(p))
    assert _undirected(DeltaLoopFlyby(p)) == shipped
    assert _undirected(DeltaLoopReflected(p)) == shipped
    assert _undirected(DeltaLoopTopdown(p)) == shipped


def test_delta_loop_flyby_seats_the_top_at_base():
    # Flown with the feed at z = 0, then a z-offset pass lifts the loop so the
    # top edge lands at `base` -- the feed follows below, not given.
    b = DeltaLoopFlyby()
    ws = b.build_wires()

    assert len(ws) == 4
    driven = [e for e in ws if e[3] is not None]
    assert len(driven) == 1 and driven[0][3] == 1 + 0j

    # Vertical loop, planar in x = 0.
    assert {round(p[0], 9) for e in ws for p in (e[0], e[1])} == {0.0}

    # The lifted top edge sits exactly at `base`; the feed is below it.
    top_z = max(p[2] for e in ws for p in (e[0], e[1]))
    feed_z = driven[0][0][2]
    assert top_z == pytest.approx(b.default_params["base"])
    assert feed_z < top_z

    # Symmetric about y = 0, and a connected closed loop.
    _assert_symmetric_closed_loop(ws)


def test_delta_loop_reflected_uses_build_path_topology():
    ws = DeltaLoopReflected().build_wires()
    # build_path([S, A, B, T]) -> 3 perimeter edges; build_path([T, S]) -> feed.
    assert len(ws) == 4
    driven = [e for e in ws if e[3] is not None]
    assert len(driven) == 1 and driven[0][3] == 1 + 0j
    # The feed bridge meshes proportionally to its length via segs_for
    # (issue #457): a 0.1 m bridge against a metres-long slant is 1 segment.
    assert driven[0][2] == 1

    # Built with the feed at z = 0, then lifted so the top seats at `base`.
    top_z = max(p[2] for e in ws for p in (e[0], e[1]))
    assert top_z == pytest.approx(DeltaLoopReflected.default_params["base"])
    _assert_symmetric_closed_loop(ws)


def test_delta_loop_topdown_lands_the_feed_on_the_plane():
    eps = 0.05
    b = DeltaLoopTopdown()
    ws = b.build_wires()

    # Same four-edge topology: three structural perimeter edges + one feed gap.
    assert len(ws) == 4
    driven = [e for e in ws if e[3] is not None]
    assert len(driven) == 1 and driven[0][3] == 1 + 0j

    # Vertical loop, planar in x = 0.
    assert {round(p[0], 9) for e in ws for p in (e[0], e[1])} == {0.0}

    # The top edge sits at `base` (the flight starts there -- no z-offset pass).
    top_z = max(p[2] for e in ws for p in (e[0], e[1]))
    assert top_z == pytest.approx(b.default_params["base"])

    # forward_to_plane landed the feed on the plane y = eps: the two driven-gap
    # ends straddle the centre line at +/- eps.
    (fy0, fy1) = (driven[0][0][1], driven[0][1][1])
    assert sorted([round(fy0, 9), round(fy1, 9)]) == [-eps, eps]

    _assert_symmetric_closed_loop(ws)


def test_delta_loop_topdown_size_tracks_length_factor():
    # length_factor is the total wire length, solved for; a bigger perimeter
    # makes a bigger loop, so the top widens with it.
    def top_width(lf):
        ws = DeltaLoopTopdown(
            dict(DeltaLoopTopdown.default_params, length_factor=lf)
        ).build_wires()
        ys = [p[1] for e in ws for p in (e[0], e[1])]
        return max(ys) - min(ys)

    assert top_width(1.1) > top_width(1.0) > top_width(0.9)


def test_delta_loop_side_follows_total_wire_length_in_closed_form():
    # The shipped closed form is just the total-wire-length parameterization
    # solved for a top-anchored corner: the slant length equals
    # (length_factor*wavelength - 4*eps) / (2*(1 + cos θ)) in closed form, no
    # numerical solve needed. Keep that claim honest.
    eps = 0.05
    for variant in ("default", "z200"):
        p = resolve_variant_params(DeltaLoop, variant)
        wl = 299.792458 / p["design_freq"]
        theta = math.radians(p["angle_deg"])
        expected = (p["length_factor"] * wl - 4 * eps) / (2 * (1 + math.cos(theta)))

        ws = DeltaLoop(p).build_wires()
        top_z = max(pt[2] for e in ws for pt in (e[0], e[1]))
        structural = [e for e in ws if e[3] is None]
        slant = next(
            e for e in structural if not (e[0][2] == top_z and e[1][2] == top_z)
        )
        assert math.dist(slant[0], slant[1]) == pytest.approx(expected)


def _assert_symmetric_closed_loop(ws):
    """The loop is symmetric about the y = 0 plane and every node is shared by
    exactly two edges (a connected closed walk)."""
    from collections import Counter

    yz = {(round(p[1], 6), round(p[2], 6)) for e in ws for p in (e[0], e[1])}
    assert {(-y, z) for (y, z) in yz} == yz
    counts = Counter((round(p[1], 6), round(p[2], 6)) for e in ws for p in (e[0], e[1]))
    assert set(counts.values()) == {2}

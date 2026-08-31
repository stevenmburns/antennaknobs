"""Tests for the hierarchical geometry authoring layer (``cell.py``) — the
geometry-side mirror of the ``Composite``/``Instance`` circuit hierarchy.

The headline guarantees:
  * a ``Transform`` placement reproduces the hand-rolled ``_shift_entry`` offset
    math the shipped array builders use (so migrating loses no geometry),
  * feed wires are renamed by a formal/actual map (one source of truth for the
    name the network layer later binds to), and
  * nesting compounds the namespace prefix exactly like ``"sta.un."`` does on
    the circuit side.
"""

import math

import numpy as np
import pytest

from antennaknobs import Cell, Placement, Transform, flatten_placements
from antennaknobs.builder import _shift_entry
from antennaknobs.network import Wire


def _names(wires):
    return {w.name for w in wires} - {None}


def _by_name(wires, name):
    (w,) = [w for w in wires if w.name == name]
    return w


# --------------------------------------------------------------------------
# formal/actual feed rename — the core feature
# --------------------------------------------------------------------------
def test_feed_is_renamed_by_the_formal_actual_map():
    """A cell authors the FORMAL name ``feed``; each placement renames it to a
    distinct ACTUAL, exactly like an ``Instance`` port map."""
    elem = Cell(
        feeds=("feed",),
        wires=[Wire((0, 0, 0), (0, 1, 0), name="feed")],
    )
    out = flatten_placements(
        [
            Placement("e0", elem, Transform.translate(0, 0, 0), feed="left"),
            Placement("e1", elem, Transform.translate(0, 5, 0), feed="right"),
        ]
    )
    assert _names(out) == {"left", "right"}
    # the actual carries the placement's pose
    assert _by_name(out, "right").p0 == pytest.approx((0, 5, 0))


def test_unbound_feed_defaults_to_namespaced_name():
    """A feed left out of the map keeps the dotted default ``<instance>.<feed>``
    — the geometry analog of an unbound internal node, and a legal state here
    (a feed wire exists whether or not it is renamed)."""
    elem = Cell(feeds=("feed",), wires=[Wire((0, 0, 0), (0, 1, 0), name="feed")])
    out = flatten_placements([Placement("e7", elem)])
    assert _names(out) == {"e7.feed"}


def test_internal_named_wire_is_namespaced_not_surfaced():
    """A named wire that is NOT a feed is private: it gets the instance prefix
    and never collides across placements of the same cell."""
    elem = Cell(
        feeds=("feed",),
        wires=[
            Wire((0, 0, 0), (0, 1, 0), name="feed"),
            Wire((0, 1, 0), (0, 2, 0), name="stub"),  # internal
        ],
    )
    out = flatten_placements(
        [Placement("a", elem, feed="fa"), Placement("b", elem, feed="fb")]
    )
    assert _names(out) == {"fa", "a.stub", "fb", "b.stub"}


def test_structural_unnamed_wires_stay_anonymous():
    elem = Cell(
        feeds=("feed",),
        wires=[Wire((0, 0, 0), (0, 1, 0), name="feed"), Wire((0, 1, 0), (0, 2, 0))],
    )
    out = flatten_placements([Placement("e0", elem, feed="f")])
    assert sum(w.name is None for w in out) == 1


# --------------------------------------------------------------------------
# Transform placement — the geometry axis
# --------------------------------------------------------------------------
def test_translate_matches_shift_entry_on_a_bowtie_element():
    """The prototype's whole premise: a translate ``Transform`` reproduces the
    literal offset math (`_shift_entry`) the shipped array builders hand-roll,
    endpoint-for-endpoint, on a real element."""
    from antennaknobs.designs.specialty import bowtie

    element_wires = bowtie.Builder().build_wires()
    cell = Cell(wires=element_wires)  # no feeds: pure geometry equivalence

    for yoff, zoff in [(-6.0, -6.0), (0.0, 2.0), (4.0, -2.0)]:
        placed = flatten_placements(
            [Placement("e", cell, Transform.translate(0, yoff, zoff))]
        )
        manual = [_shift_entry(w, yoff, zoff, lambda ex: ex) for w in element_wires]
        assert len(placed) == len(manual)
        for p, m in zip(placed, manual, strict=True):
            assert p.p0 == pytest.approx(m.p0)
            assert p.p1 == pytest.approx(m.p1)
            assert p.ex == m.ex  # excitation passes through the placement untouched


def test_rotation_places_endpoints_like_transform_hit():
    tr = Transform.rotZ(90.0)
    cell = Cell(wires=[Wire((1.0, 0.0, 0.0), (2.0, 0.0, 0.0))])
    (w,) = flatten_placements([Placement("e", cell, tr)])
    # rotZ(90) sends (x,0,0) -> (0,x,0)
    assert w.p0 == pytest.approx((0.0, 1.0, 0.0))
    assert w.p1 == pytest.approx((0.0, 2.0, 0.0))


def test_mirror_transform_reflects_like_the_delta_looparray_ry():
    """A reflecting matrix expresses the y-mirror the delta_looparray design
    does by hand (``ry``), so a mirrored element is a Placement, not a second
    hand-written wire list."""
    mirror_y = Transform(np.diag([1.0, -1.0, 1.0, 1.0]))
    cell = Cell(feeds=("loop",), wires=[Wire((0, 1, 3), (0, 2, 4), name="loop")])
    out = flatten_placements(
        [
            Placement("loop1", cell, loop="loop1"),
            Placement("loop2", cell, mirror_y, loop="loop2"),
        ]
    )
    assert _by_name(out, "loop1").p0 == pytest.approx((0, 1, 3))
    assert _by_name(out, "loop2").p0 == pytest.approx((0, -1, 3))


# --------------------------------------------------------------------------
# nesting — real hierarchy
# --------------------------------------------------------------------------
def test_nested_cell_compounds_prefix_and_surfaces_child_feed():
    inner = Cell(
        feeds=("tip",),
        wires=[
            Wire((0, 0, 0), (0, 1, 0), name="tip"),
            Wire((0, 1, 0), (0, 2, 0), name="stub"),  # internal, deep
        ],
    )
    outer = Cell(
        feeds=("out_tip",),
        wires=[Wire((0, 0, 0), (1, 0, 0), name="spine")],
        children=[
            Placement("inner", inner, Transform.translate(0, 0, 5), tip="out_tip")
        ],
    )
    out = flatten_placements(
        [Placement("o", outer, Transform.translate(10, 0, 0), out_tip="feedX")]
    )

    assert _names(out) == {"o.spine", "feedX", "o.inner.stub"}
    # child feed surfaced all the way to the top-level actual…
    assert _by_name(out, "feedX").p0 == pytest.approx((10, 0, 5))
    # …and the deep internal carries the compounded "o.inner." path
    assert _by_name(out, "o.inner.stub").p1 == pytest.approx((10, 2, 5))


def test_nested_transforms_compose_parent_then_child():
    inner = Cell(wires=[Wire((1, 0, 0), (1, 0, 0))])
    outer = Cell(children=[Placement("i", inner, Transform.translate(0, 0, 5))])
    (w,) = flatten_placements([Placement("o", outer, Transform.translate(0, 10, 0))])
    # child local (1,0,0) -> +z5 -> +y10  == (1,10,5)
    assert w.p0 == pytest.approx((1, 10, 5))


# --------------------------------------------------------------------------
# by-construction guards the current f-string convention lacks
# --------------------------------------------------------------------------
def test_duplicate_actual_across_placements_raises():
    elem = Cell(feeds=("feed",), wires=[Wire((0, 0, 0), (0, 1, 0), name="feed")])
    with pytest.raises(ValueError, match="duplicate wire name"):
        flatten_placements(
            [Placement("a", elem, feed="dup"), Placement("b", elem, feed="dup")]
        )


def test_unknown_formal_in_map_raises():
    elem = Cell(feeds=("feed",), wires=[Wire((0, 0, 0), (0, 1, 0), name="feed")])
    with pytest.raises(ValueError, match="unknown feed"):
        Placement("e0", elem, feed="f", bogus="x")


def test_dangling_feed_raises():
    with pytest.raises(ValueError, match="name no local wire"):
        Cell(feeds=("feed",), wires=[Wire((0, 0, 0), (0, 1, 0), name="other")])


def test_placement_name_with_dot_raises():
    elem = Cell(feeds=("feed",), wires=[Wire((0, 0, 0), (0, 1, 0), name="feed")])
    with pytest.raises(ValueError, match="no '\\.'"):
        Placement("a.b", elem, feed="f")


def test_duplicate_formal_feed_raises():
    with pytest.raises(ValueError, match="duplicate formal feed"):
        Cell(feeds=("feed", "feed"), wires=[Wire((0, 0, 0), (0, 1, 0), name="feed")])


# --------------------------------------------------------------------------
# headline consumer: a 4x4 grid, authored once + stamped, matches the manual
# hand-unrolled builder the 4x4 lattice test currently uses.
# --------------------------------------------------------------------------
def test_4x4_grid_reproduces_manual_builder_and_names_every_feed():
    from antennaknobs.designs.specialty import bowtie

    element_wires = bowtie.Builder().build_wires()
    nx = nz = 4
    del_y = del_z = 4.0

    # Author the element ONCE; name its feed edge (the ex-carrying wire).
    cell_wires = [
        w._replace(name="feed") if w.ex is not None else w for w in element_wires
    ]
    elem = Cell(feeds=("feed",), wires=cell_wires)

    placements = [
        Placement(
            f"e{i}_{j}",
            elem,
            Transform.translate(
                0,
                (i - (nx - 1) / 2) * del_y,
                (j - (nz - 1) / 2) * del_z,
            ),
            feed=f"e{i}_{j}.feed",
        )
        for i in range(nx)
        for j in range(nz)
    ]
    placed = flatten_placements(placements)

    # 16 distinct, addressable feed names — the thing Style A can't give you.
    feed_names = sorted(n for n in _names(placed) if n.endswith(".feed"))
    assert len(feed_names) == 16
    assert len(set(feed_names)) == 16

    # Geometry equals the manual _shift_entry grid the current 4x4 test uses.
    manual = []
    for i in range(nx):
        for j in range(nz):
            yoff = (i - (nx - 1) / 2) * del_y
            zoff = (j - (nz - 1) / 2) * del_z
            manual.extend(
                _shift_entry(w, yoff, zoff, lambda ex: ex) for w in element_wires
            )

    # Same wire count; endpoints agree element-for-element.
    assert len(placed) == len(manual) == 16 * len(element_wires)
    for p, m in zip(placed, manual, strict=True):
        assert p.p0 == pytest.approx(m.p0)
        assert p.p1 == pytest.approx(m.p1)


def test_module_docstring_example_shape():
    """Sanity: a bare identity placement of a one-wire cell round-trips."""
    cell = Cell(feeds=("f",), wires=[Wire((0, 0, 0), (0, math.pi, 0), name="f")])
    (w,) = flatten_placements([Placement("only", cell, f="only_f")])
    assert w.name == "only_f"
    assert w.p1 == pytest.approx((0, math.pi, 0))

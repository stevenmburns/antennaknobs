"""Phase-1 tests for issue #388: the `Wire` named tuple, the `as_wire`
normalizer choke point, spec-aware polyline translation, and spec/name
passthrough in the array builders and parity coercion.

Engine *consumption* of per-wire specs (radius per wire on PyNEC/momwire)
is a later phase; these tests pin the contract that makes it possible:
plain 4/5-tuples remain valid forever, may be mixed with `Wire` entries,
and a `Wire` rides through every transform with `name`/`spec` intact.
"""

from types import MappingProxyType

import numpy as np
import pytest

from antennaknobs import AntennaBuilder, Wire, WireSpec, as_wire
from antennaknobs.builder import Array1x2Builder, _shift_entry
from antennaknobs.geometry import flat_wires_to_polylines

THICK = WireSpec(radius=5e-3)
THIN = WireSpec(radius=0.5e-3)


# ---------------------------------------------------------------- as_wire


def test_as_wire_accepts_all_shapes():
    p0, p1 = (0.0, 0.0, 0.0), (0.0, 0.0, 1.0)
    assert as_wire((p0, p1, 3, None)) == Wire(p0, p1, 3)
    assert as_wire((p0, p1, 3, 1 + 0j, "feed")) == Wire(p0, p1, 3, 1 + 0j, "feed")
    assert as_wire((p0, p1, 3, None, None, THIN)) == Wire(p0, p1, 3, spec=THIN)
    w = Wire(p0, p1, 3, spec=THICK)
    assert as_wire(w) is w


def test_as_wire_rejects_bad_arity():
    with pytest.raises(ValueError, match="4-6 fields"):
        as_wire(((0, 0, 0), (0, 0, 1), 3))
    with pytest.raises(ValueError, match="4-6 fields"):
        as_wire(((0, 0, 0), (0, 0, 1), 3, None, None, None, "extra"))


def test_wire_is_tuple_compatible():
    """The compatibility contract: a Wire behaves as the 4/5-tuple code
    expects — indexing, unpacking the first four, and name at index 4."""
    w = Wire((0, 0, 0), (0, 0, 1), 7, 1 + 0j, "port", THICK)
    assert isinstance(w, tuple)
    p0, p1, n, ev = w[0], w[1], w[2], w[3]
    assert (p0, p1, n, ev) == ((0, 0, 0), (0, 0, 1), 7, 1 + 0j)
    assert (w[4] if len(w) >= 5 else None) == "port"
    assert w.spec is THICK


# ------------------------------------------------- polyline translation


def _dipole_tups(spec_mid=None, as_named=False):
    """Three colinear edges along z with the feed in the middle; optionally
    a different spec on the middle edge, optionally as Wire entries."""
    a, b, c, d = (0, 0, 0.0), (0, 0, 1.0), (0, 0, 2.0), (0, 0, 3.0)
    tups = [
        (a, b, 5, None),
        (b, c, 5, 1 + 0j),
        (c, d, 5, None),
    ]
    if as_named:
        tups = [Wire(*t) for t in tups]
    if spec_mid is not None:
        tups[1] = Wire(b, c, 5, 1 + 0j, spec=spec_mid)
    return tups


def test_plain_and_named_translate_identically():
    plain = flat_wires_to_polylines(_dipole_tups())
    named = flat_wires_to_polylines(_dipole_tups(as_named=True))
    assert len(plain["polylines"]) == len(named["polylines"]) == 1
    np.testing.assert_array_equal(plain["polylines"][0], named["polylines"][0])
    assert plain["edge_segments"] == named["edge_segments"]
    assert plain["feeds"] == named["feeds"]
    assert plain["junctions"] == named["junctions"]
    assert plain["polyline_specs"] == [None]
    assert named["polyline_specs"] == [None]


def test_spec_change_splits_polyline_with_junctions():
    """A spec change at a degree-2 node becomes a polyline boundary and a
    KCL junction, so momwire can carry one spec per wire."""
    out = flat_wires_to_polylines(_dipole_tups(spec_mid=THICK))
    assert len(out["polylines"]) == 3
    # Each polyline carries exactly its edge's spec.
    from collections import Counter

    assert Counter(out["polyline_specs"]) == Counter([None, None, THICK])
    # The two spec-change nodes are 2-entry junctions (current continuity).
    assert len(out["junctions"]) == 2
    assert all(len(j) == 2 for j in out["junctions"])


def test_equal_specs_do_not_split():
    """Specs compare by value (frozen dataclass): two separately built but
    equal specs must NOT fragment the polyline."""
    a, b, c = (0, 0, 0.0), (0, 0, 1.0), (0, 0, 2.0)
    tups = [
        Wire(a, b, 5, 1 + 0j, spec=WireSpec(radius=1e-3)),
        Wire(b, c, 5, None, spec=WireSpec(radius=1e-3)),
    ]
    out = flat_wires_to_polylines(tups)
    assert len(out["polylines"]) == 1
    assert out["polyline_specs"] == [WireSpec(radius=1e-3)]


def test_mixed_spec_loop_still_translates():
    """A closed loop whose edges differ in spec: the spec boundaries open
    the cycle before the pure-cycle handler ever sees it."""
    pts = [(0, 0, 0.0), (1, 0, 0.0), (1, 1, 0.0), (0, 1, 0.0)]
    tups = [
        Wire(pts[0], pts[1], 3, 1 + 0j, spec=THICK),
        Wire(pts[1], pts[2], 3, None, spec=THIN),
        Wire(pts[2], pts[3], 3, None, spec=THIN),
        Wire(pts[3], pts[0], 3, None, spec=THICK),
    ]
    out = flat_wires_to_polylines(tups)
    # Two spec-uniform chains (THICK pair split by the feed edge is allowed
    # to be more pieces; what matters is uniformity per polyline).
    for pl_spec, segs in zip(out["polyline_specs"], out["edge_segments"]):
        assert pl_spec in (THICK, THIN)
    total_edges = sum(len(s) for s in out["edge_segments"])
    assert total_edges == 4


def test_uniform_loop_unchanged_by_spec_field():
    """A uniform-spec loop takes the pure-cycle path exactly as before."""
    pts = [(0, 0, 0.0), (1, 0, 0.0), (1, 1, 0.0), (0, 1, 0.0)]
    plain = [
        (pts[0], pts[1], 3, 1 + 0j),
        (pts[1], pts[2], 3, None),
        (pts[2], pts[3], 3, None),
        (pts[3], pts[0], 3, None),
    ]
    named = [Wire(*t, spec=THIN) for t in plain]
    out_p = flat_wires_to_polylines(plain)
    out_n = flat_wires_to_polylines(named)
    assert len(out_p["polylines"]) == len(out_n["polylines"]) == 2
    for a, b in zip(out_p["polylines"], out_n["polylines"]):
        np.testing.assert_array_equal(a, b)
    assert out_n["polyline_specs"] == [THIN, THIN]


# ------------------------------------------------------- parity coercion


def test_coerce_preserves_shape_and_spec():
    class _Stub:
        segment_parity = "odd"

        # borrow the real implementations
        from antennaknobs.engine import SimulationEngine as _S

        coerce_n_seg = staticmethod(_S.coerce_n_seg)
        _coerce_wire_tuples = _S._coerce_wire_tuples

    eng = _Stub()
    p0, p1 = (0, 0, 0.0), (0, 0, 1.0)
    out = eng._coerce_wire_tuples(
        [
            (p0, p1, 4, None),  # unmarked plain 4-tuple
            (p0, p1, 4, 1 + 0j, "feed"),  # marked (ex + name)
            Wire(p0, p1, 4, None, spec=THICK),  # unmarked Wire
            Wire(p0, p1, 4, 2 + 0j, "feed2", THICK),  # marked Wire
        ]
    )
    # Only marked wires (a feed EX or a named network port) are coerced to the
    # engine's parity, so the attachment lands on the middle segment; an
    # unmarked wire keeps its exact segment count (issue #450). Shape and spec
    # are preserved either way: a plain tuple stays plain, a Wire stays a Wire.
    assert out[0] == (p0, p1, 4, None) and type(out[0]) is tuple
    assert out[1] == (p0, p1, 5, 1 + 0j, "feed") and type(out[1]) is tuple
    assert isinstance(out[2], Wire) and out[2].n_seg == 4 and out[2].spec is THICK
    assert isinstance(out[3], Wire) and out[3].n_seg == 5 and out[3].spec is THICK


# --------------------------------------------------------- array builders


class _Elem(AntennaBuilder):
    default_params = MappingProxyType({"freq": 14.1})

    def build_wires(self):
        return [
            Wire((0, 0, 10.0), (0, 0, 11.0), 5, 1 + 0j, "feed", THICK),
            ((0, 0, 11.0), (0, 0, 12.0), 5, None),
        ]


class _Pair(Array1x2Builder):
    default_params = MappingProxyType({"freq": 14.1, "del_y": 2.0, "phase_lr": 180.0})

    def __init__(self, params=None):
        super().__init__(_Elem, params)


def test_array_builder_passes_name_and_spec_through():
    tups = _Pair().build_wires()
    assert len(tups) == 4
    named = [t for t in tups if isinstance(t, Wire)]
    plain = [t for t in tups if not isinstance(t, Wire)]
    assert len(named) == 2 and len(plain) == 2
    for w in named:
        assert w.spec is THICK
        assert w.name == "feed"
        assert w.ex is not None  # replaced by the array phasor
    for t in plain:
        assert len(t) == 4  # plain entries stay plain 4-tuples


def test_shift_entry_conventions():
    w = Wire((0, 1, 2.0), (0, 3, 4.0), 5, 2 + 0j, "p", THIN)
    replaced = _shift_entry(w, 1.0, -1.0, lambda ex: 9j)
    assert replaced.p0 == (0, 2, 1.0) and replaced.p1 == (0, 4, 3.0)
    assert replaced.ex == 9j and replaced.spec is THIN and replaced.name == "p"
    # None excitation is never passed to the policy callable
    passive = _shift_entry(
        ((0, 0, 0), (0, 0, 1.0), 3, None), 0.0, 0.0, lambda ex: 1 / 0
    )
    assert passive == ((0, 0, 0), (0, 0, 1.0), 3, None) and len(passive) == 4

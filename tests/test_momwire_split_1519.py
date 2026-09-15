"""AK#1519: the momwire engine feeds every positioned port exactly, split the
way its reference engines split, and a wire whose only attachment is a vertex
port keeps its authored count on every solver.

A solver with a grid parity splits a wire whose ports are not all sites of its
own count (AK#1511's rule, split-always):

- the centre family (odd parity: BSplineSolver degree 2 and its HMatrix and
  ArrayBlock subclasses, SinusoidalSolver, SinusoidalGalerkinSolver under
  either feed model) gives each port the middle of a short piece of its own,
  as PyNEC and NEC-2 do;
- the knot family (even parity: RazorSolver, BSplineSolver degree 1) cuts the
  wire at every port and feeds the knot the pieces share through a series node
  gap, as NEC-5 does.

The geometry is `test_multi_port_split_1511`'s: a 10.5 m dipole at 10 m, 1 mm
radius, 14.2 MHz, fed at 0.31 with 50 ohm loads at 0.77 and 0.04.

Physics bars, registered before any gate below was run (2026-09-15):

- razor-2p against live NEC-5 on the same split geometry, authored 41 and 81
  segments, two and three ports: |Z_razor - Z_nec5| <= 2 D5, where D5 is
  |Z_razor - Z_nec5| on the centre-fed dipole at the same authored count.
- SinusoidalSolver against PyNEC on the same split geometry, authored 41 and
  101 segments, one, two and three ports: |Z_sin - Z_pynec| <= 2 D, where D is
  |Z_sin - Z_pynec| on the centre-fed dipole at the same authored count.
- bs2 split (authored 61 and 101) against bs2's whole wire at 150 segments,
  where both ports of the two-port case are segment centres:
  |Z_split - Z_w(150)| <= |Z_w(150) - Z_w(50)|, bs2's own refinement step.
- The vertex-only exemption: a dipole cut at 0.3 into 3 + 7 segments, with a
  vertex port at the cut, meshes 3 + 7 on razor-2p, d = 1 and bs2, and razor-2p
  agrees with NEC-5 on that deck within 0.1 ohm.

Measured once the bars were in (2026-09-15):

- razor-2p against NEC-5: 0.053 ohm (1.39 D5) and 0.053 ohm (1.40 D5) at 41,
  0.056 ohm (1.49 D5) and 0.054 ohm (1.44 D5) at 81, two and three ports; about
  0.035 % of |Z| each, with 2 D5 = 0.076 and 0.075 ohm.
- SinusoidalSolver against PyNEC: 1.32, 1.41 and 1.42 D at 41 (2 D = 0.225
  ohm), 1.32, 1.41 and 1.41 D at 101 (2 D = 0.216 ohm).
- bs2 split against its whole wire at 150: 0.192 ohm at 61 and 0.074 ohm at
  101, against a step of 0.253 ohm.
- The cut deck: razor-2p 112.671+j20.101, NEC-5 112.660+j20.046, 0.056 ohm
  apart. Before the exemption razor meshed it 4 + 7 and read 113.056+j24.244.
"""

from __future__ import annotations

import itertools
from types import MappingProxyType

import numpy as np
import pytest
from conftest import needs_nec5
from momwire import (
    BSplineSolver,
    HMatrixSolver,
    RazorSolver,
    SinusoidalGalerkinSolver,
    SinusoidalSolver,
)
from test_multi_port_split_1511 import LENGTH, P0, P1, _b, _targets, _z

from antennaknobs import AntennaBuilder, WireSpec
from antennaknobs.engines.momwire import MomwireEngine
from antennaknobs.network import (
    Driven,
    Network,
    PortAtVertex,
    PortOnWire,
    Wire,
    as_wire,
)

pytestmark = pytest.mark.skipif(
    not hasattr(PortOnWire("x"), "at"),
    reason="the installed momwire's PortOnWire has no wire/at (momwire#1059)",
)

CENTRE = {
    "bs2": (BSplineSolver, {}),
    "hmatrix": (HMatrixSolver, {}),
    "sinusoidal": (SinusoidalSolver, {}),
    "sg-point": (SinusoidalGalerkinSolver, {}),
    "sg-segment": (SinusoidalGalerkinSolver, {"feed_model": "segment"}),
}
KNOT = {
    "razor-2p": (RazorSolver, {"nec5_quadrature": True}),
    "bs1": (BSplineSolver, {"degree": 1}),
}
CASES = {
    "k1": dict(feed_at=1 / 3),
    "k2": dict(feed_at=0.31, load_ats=(0.77,)),
    "k3": dict(feed_at=0.31, load_ats=(0.04, 0.77)),
}


def _momwire(builder, solver):
    cls, kwargs = {**CENTRE, **KNOT}[solver]
    return MomwireEngine(builder, solver=cls, solver_kwargs=kwargs, ground=None)


def _point_at(polyline, arc):
    poly = np.asarray(polyline, dtype=float)
    seg = np.linalg.norm(np.diff(poly, axis=0), axis=1)
    cum = np.concatenate([[0.0], np.cumsum(seg)])
    k = min(max(int(np.searchsorted(cum, arc, side="right")) - 1, 0), len(seg) - 1)
    return poly[k] + (arc - cum[k]) / seg[k] * (poly[k + 1] - poly[k])


def _fed_point(eng, port):
    """Where the engine feeds `port`: its gap's arclength on the polyline, or
    the polyline end its node gap sits at."""
    if port in eng._feed_names:
        pl, arc, _v = eng._feeds[eng._feed_names.index(port)]
        return _point_at(eng._polylines[pl], arc)
    i = [name for name, _w, _e in eng._vertex_ports].index(port)
    pl, end = eng._vertex_port_members[i]
    return np.asarray(eng._polylines[pl], dtype=float)[-1 if end == "end" else 0]


def _offset_notes(eng):
    return [
        a
        for a in eng.advisories
        if a.get("category") == "FeedPlacement" and "mm away" in a["text"]
    ]


# ---------------------------------------------------------------------------
# (a) exactness
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("case", CASES)
@pytest.mark.parametrize("solver", [*CENTRE, *KNOT])
def test_every_port_is_fed_at_its_position(solver, case):
    b = _b(**CASES[case])
    eng = _momwire(b, solver)
    assert set(eng._split_wires) == {"w"}
    for port, target in _targets(b).items():
        assert np.linalg.norm(_fed_point(eng, port) - target) <= 1e-9 * LENGTH
    eng.impedance()
    assert _offset_notes(eng) == []


@pytest.mark.parametrize("case", CASES)
@pytest.mark.parametrize("solver", CENTRE)
def test_a_centre_solver_places_each_split_port_with_no_offset(solver, case):
    """The solver's own report (momwire#1059): every gap feed lands where it
    was asked, so a snapping basis has nothing to snap."""
    eng = _momwire(_b(**CASES[case]), solver)
    placements = eng._make_solver(wavelength=299.792458 / 14.2).feed_placements()
    assert len(placements) == len(CASES[case].get("load_ats", ())) + 1
    for p in placements:
        assert abs(float(p.offset)) <= 1e-9 * LENGTH


@pytest.mark.parametrize("case", CASES)
@pytest.mark.parametrize("solver", CENTRE)
def test_a_centre_solver_meshes_as_pynec_and_nec2_do(solver, case):
    """Each port at the middle of an odd piece of its own; the pieces stay one
    polyline, so the currents are the authored wire's."""
    eng = _momwire(_b(**CASES[case]), solver)
    split = eng._split_wires["w"]
    assert eng._edge_segments == [[s.n_seg for s in split.plan.spans]]
    for span in split.plan.spans:
        if span.port is not None:
            assert span.n_seg % 2 == 1
    assert eng._vertex_ports == []
    (wc,) = eng.geometry_distribution()
    np.testing.assert_allclose(wc.knot_positions[[0, -1]], [P0, P1], atol=1e-12)


@pytest.mark.parametrize("case", CASES)
@pytest.mark.parametrize("solver", KNOT)
def test_a_knot_solver_cuts_at_every_port_as_nec5_does(solver, case):
    """The pieces are NEC-5's, and each port is a series node gap at the p1 end
    of the piece named for it."""
    from antennaknobs.engines.nec5 import NEC5Engine

    b = _b(**CASES[case])
    eng = _momwire(b, solver)
    nec5 = NEC5Engine(b, require_exe=False)
    assert eng._edge_segments == [[as_wire(t).n_seg] for t in nec5.tups]
    assert eng._feeds == []
    assert {(n, w, e) for n, w, e in eng._vertex_ports} == {
        (port, piece, "p1") for port, piece in nec5._split_ports.items()
    }


def test_a_port_on_a_site_of_the_wires_own_count_keeps_it_whole():
    """0.35 is a segment centre of 10 and 0.3 a knot: no split on either
    family, and no note."""
    centre = _momwire(_b(feed_at=0.35), "sinusoidal")
    knot = _momwire(_b(feed_at=0.3), "razor-2p")
    for eng in (centre, knot):
        assert eng._split_wires == {} and eng._edge_segments == [[10]]
        eng.impedance()
        assert [a for a in eng.advisories if a.get("category") == "FeedPlacement"] == []


def test_a_parity_free_solver_keeps_the_wire_whole():
    from momwire import PulseSolver

    eng = MomwireEngine(_b(**CASES["k3"]), solver=PulseSolver, ground=None)
    assert eng.segment_parity == "any"
    assert not getattr(eng, "_split_wires", None)
    assert eng._edge_segments == [[10]]


def test_one_note_per_split_wire_and_no_offset():
    eng = _momwire(_b(**CASES["k2"]), "razor-2p")
    eng.impedance()
    (note,) = [a for a in eng.advisories if a.get("category") == "FeedPlacement"]
    assert "'feed' at 0.31 and 'load0' at 0.77" in note["text"]
    assert "knot the pieces on either side share" in note["text"]


# ---------------------------------------------------------------------------
# every reader of a port sees its piece
# ---------------------------------------------------------------------------


def test_a_knot_solver_reports_each_port_at_the_knot_of_its_own_cut():
    eng = _momwire(_b(**CASES["k2"]), "razor-2p")
    records = {r["port"]: r for r in eng.fed_segments()}
    assert set(records) == {"feed", "load0"}
    lengths = [0.31, 0.46, 0.23]
    counts = [c for (c,) in eng._edge_segments]
    for port, index in (("feed", 0), ("load0", 1)):
        rec = records[port]
        assert rec["site"] == "knot"
        assert rec["segments"] == counts[index]
        assert rec["length_m"] == pytest.approx(lengths[index] * LENGTH / counts[index])
        assert rec["length_after_m"] == pytest.approx(
            lengths[index + 1] * LENGTH / counts[index + 1]
        )


def test_a_centre_solver_reports_each_ports_own_piece():
    eng = _momwire(_b(**CASES["k2"]), "bs2")
    split = eng._split_wires["w"]
    fed = {s.port: s for s in split.plan.spans if s.port is not None}
    names = [port for port, _at in split.ports]
    records = {r["port"]: r for r in eng.fed_segments()}
    for i, port in enumerate(names):
        span = fed[i]
        rec = records[port]
        assert (rec["site"], rec["segments"]) == ("centre", span.n_seg)
        assert rec["length_m"] == pytest.approx(
            (span.hi - span.lo) * LENGTH / span.n_seg
        )


@pytest.mark.parametrize("solver", ["bs2", "razor-2p"])
def test_the_workbench_marker_sits_on_the_driven_port(solver):
    import antennaknobs.web.examples  # noqa: F401  registration order
    from antennaknobs.web import adapter

    b = _b(**CASES["k3"])
    eng = _momwire(b, solver)
    currents = eng.current_distribution()
    pos = adapter._feed_position(eng, currents)
    assert np.linalg.norm(np.asarray(pos) - _targets(b)["feed"]) <= 1e-9 * LENGTH
    pl, k = adapter._feed_indices(eng, currents)
    knot = currents[pl].knot_positions[k]
    # The knot the readout takes the feed current from: the port itself on a
    # knot solver, the nearest knot to the gap on a centre solver.
    segment = LENGTH * 0.27 / 2  # the k3 feed piece is one segment of 0.135 L
    assert np.linalg.norm(knot - _targets(b)["feed"]) <= (
        1e-9 * LENGTH if solver == "razor-2p" else 0.5 * segment + 1e-9
    )


def test_the_knot_solvers_currents_meet_at_every_cut():
    """A node gap sits at a polyline end, so each piece is its own polyline;
    they chain end to end along the wire and carry one current through each
    cut."""
    eng = _momwire(_b(**CASES["k3"]), "razor-2p")
    currents = eng.current_distribution()
    assert len(currents) == 4
    np.testing.assert_allclose(currents[0].knot_positions[0], P0, atol=1e-12)
    np.testing.assert_allclose(currents[-1].knot_positions[-1], P1, atol=1e-12)
    for a, b in itertools.pairwise(currents):
        np.testing.assert_allclose(
            a.knot_positions[-1], b.knot_positions[0], atol=1e-12
        )
        assert abs(a.knot_currents[-1] - b.knot_currents[0]) <= 1e-6 * abs(
            a.knot_currents[-1]
        )


# ---------------------------------------------------------------------------
# (b) like-for-like physics
# ---------------------------------------------------------------------------


def _nec5_engine(builder):
    from antennaknobs.engines.nec5 import NEC5Engine

    return NEC5Engine(builder, ground=None)


def _pynec_engine(builder):
    pytest.importorskip("PyNEC")
    from antennaknobs.engines.pynec import PyNECEngine

    return PyNECEngine(builder, ground=None)


def _same_mesh(mom, ref):
    """The momwire engine's edges are the reference engine's wires."""
    counts = [as_wire(t).n_seg for t in ref.tups]
    flat = [c for edges in mom._edge_segments for c in edges]
    assert flat == counts


@needs_nec5
@pytest.mark.parametrize("n", [41, 81])
@pytest.mark.parametrize("case", ["k2", "k3"])
def test_razor_2p_agrees_with_nec5_on_the_same_split(case, n):
    """|Z_razor - Z_nec5| <= 2 D5, as registered above."""
    centre = _b(n_seg=n, feed_at=None)
    d5 = abs(_z(_momwire(centre, "razor-2p")) - _z(_nec5_engine(centre)))
    b = _b(n_seg=n, **CASES[case])
    razor, nec5 = _momwire(b, "razor-2p"), _nec5_engine(b)
    _same_mesh(razor, nec5)
    assert abs(_z(razor) - _z(nec5)) <= 2 * d5


@pytest.mark.parametrize("n", [41, 101])
@pytest.mark.parametrize("case", CASES)
def test_sinusoidal_agrees_with_pynec_on_the_same_split(case, n):
    """|Z_sin - Z_pynec| <= 2 D, as registered above."""
    centre = _b(n_seg=n, feed_at=None)
    d = abs(_z(_momwire(centre, "sinusoidal")) - _z(_pynec_engine(centre)))
    b = _b(n_seg=n, **CASES[case])
    sin, pynec = _momwire(b, "sinusoidal"), _pynec_engine(b)
    _same_mesh(sin, pynec)
    assert abs(_z(sin) - _z(pynec)) <= 2 * d


@pytest.fixture(scope="module")
def bs2_whole():
    """bs2's whole wire at 50 and 150 segments, where 0.31 and 0.77 are both
    segment centres, so neither count splits."""
    out = {}
    for n in (50, 150):
        eng = _momwire(_b(n_seg=n, **CASES["k2"]), "bs2")
        assert eng._split_wires == {} and eng._edge_segments == [[n]]
        out[n] = _z(eng)
    return out


@pytest.mark.parametrize("n", [61, 101])
def test_bs2_split_agrees_with_its_own_whole_wire(bs2_whole, n):
    """|Z_split - Z_w(150)| <= |Z_w(150) - Z_w(50)|, as registered above."""
    eng = _momwire(_b(n_seg=n, **CASES["k2"]), "bs2")
    assert set(eng._split_wires) == {"w"}
    step = abs(bs2_whole[150] - bs2_whole[50])
    assert abs(_z(eng) - bs2_whole[150]) <= step


# ---------------------------------------------------------------------------
# (c) a vertex-only wire keeps its count
# ---------------------------------------------------------------------------

CUT = tuple(float(v) for v in P0 + 0.3 * (P1 - P0))


class _Cut(AntennaBuilder):
    """The dipole cut at 0.3 into 3 + 7 segments, fed at the cut by a vertex
    port on the first piece's p1 end."""

    default_params = MappingProxyType({"freq": 14.2, "design_freq": 14.2})

    def build_wires(self):
        return [
            Wire(tuple(P0), CUT, n_seg=3, name="w"),
            Wire(CUT, tuple(P1), n_seg=7),
        ]

    def build_wire_material(self):
        return WireSpec(radius=1e-3)

    def build_network(self):
        return Network(
            ports={"feed": PortAtVertex(wire="w", end="p1")},
            sources=[Driven(port="feed")],
        )


@pytest.mark.parametrize("solver", ["razor-2p", "bs1", "bs2"])
def test_a_vertex_only_wire_keeps_its_authored_count(solver):
    assert _momwire(_Cut(), solver)._edge_segments == [[3], [7]]


def test_a_vertex_wire_with_a_gap_port_too_keeps_the_parity_rule():
    """The exemption is for a wire whose ONLY attachment is a vertex port."""

    class _Both(_Cut):
        def build_network(self):
            return Network(
                ports={
                    "feed": PortAtVertex(wire="w", end="p1"),
                    "gap": PortOnWire("gap", wire="w"),
                },
                sources=[Driven(port="feed")],
            )

    from antennaknobs.engine import vertex_only_names

    assert vertex_only_names(_Cut().build_network()) == {"w"}
    assert vertex_only_names(_Both().build_network()) == frozenset()


@needs_nec5
def test_razor_2p_agrees_with_nec5_on_the_cut_deck():
    razor = _momwire(_Cut(), "razor-2p")
    nec5 = _nec5_engine(_Cut())
    _same_mesh(razor, nec5)
    assert abs(_z(razor) - _z(nec5)) <= 0.1

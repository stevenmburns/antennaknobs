"""AK#1510 unit 2: a positioned port that no segment count up to the cap can
carry is fed exactly, through a split wire.

On a grid engine (segment centres on PyNEC and NEC-2, knots on NEC-5), a wire
carrying ONE positioned port that no count up to twice its own puts on a site is
cut in two so the port sits at the exact middle of one piece. That piece keeps
the wire's name, and every reader of the port's position (segment, knot, card,
drive point) sees the port at its middle. The momwire engine feeds the exact
arclength and never splits. A wire carrying several such ports keeps its count
and the nearest-site advisory.
"""

from __future__ import annotations

import itertools
from types import MappingProxyType

import numpy as np
import pytest

from antennaknobs import AntennaBuilder, WireSpec
from antennaknobs.engines.nec5 import NEC5Engine
from antennaknobs.network import Driven, Load, Network, PortOnWire, Wire, as_wire

pytestmark = pytest.mark.skipif(
    not hasattr(PortOnWire("x"), "at"),
    reason="the installed momwire's PortOnWire has no wire/at (momwire#1059)",
)

FREQ = 28.47
ARM = 0.25 * 299.792458 / FREQ
P0 = np.array((0.0, -ARM, 10.0))
P1 = np.array((0.0, ARM, 10.0))
LENGTH = 2 * ARM
THICK = WireSpec(radius=1e-3)


class _Dipole(AntennaBuilder):
    default_params = MappingProxyType(
        {
            "freq": FREQ,
            "design_freq": FREQ,
            "n_seg": 10,
            "feed_at": None,
            "load_at": None,
        }
    )
    spec = None

    def build_wires(self):
        return [Wire(tuple(P0), tuple(P1), n_seg=self.n_seg, name="w", spec=self.spec)]

    def build_network(self):
        ports = {"feed": PortOnWire("feed", wire="w", at=self.feed_at)}
        branches = []
        if self.load_at is not None:
            ports["load"] = PortOnWire("load", wire="w", at=self.load_at)
            branches.append(Load(port="load", r=50.0))
        return Network(ports=ports, branches=branches, sources=[Driven(port="feed")])


class _ThickDipole(_Dipole):
    spec = THICK


def _b(cls=_Dipole, **params):
    return cls(dict(cls.default_params, **params))


def _target(at):
    return P0 + at * (P1 - P0)


def _pynec(**params):
    pytest.importorskip("PyNEC")
    from antennaknobs.engines.pynec import PyNECEngine

    return PyNECEngine(_b(**params), ground=None)


def _z(eng):
    return complex(np.atleast_1d(eng.impedance())[0])


# In two pieces the free one would be |1 - 2 at| of the wire, under half of one
# of its ten segments, so these split in three.
NEAR_MIDDLE = [0.49, 0.499, 0.5001]


# ---------------------------------------------------------------------------
# the fed site is the stated position
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("at", "wires"),
    [(1 / 3, 2), (2 / 3, 2), (0.31, 2), (0.02, 2)] + [(a, 3) for a in NEAR_MIDDLE],
)
def test_pynec_feeds_a_centre_at_the_position_through_a_split(at, wires):
    eng = _pynec(feed_at=at)
    eng.impedance()
    assert len(eng.tups) == wires
    tag, seg = eng._network_port_loc["feed"]
    p0, p1, n = (
        np.asarray(eng.tups[tag - 1][0]),
        eng.tups[tag - 1][1],
        eng.tups[tag - 1][2],
    )
    centre = p0 + (seg - 0.5) / n * (np.asarray(p1) - p0)
    assert np.linalg.norm(centre - _target(at)) <= 1e-9 * LENGTH


@pytest.mark.parametrize(
    ("at", "wires"),
    [(1 / 3, 1), (0.31, 2), (0.69, 2), (0.123, 2)] + [(a, 3) for a in NEAR_MIDDLE],
)
def test_nec5_feeds_a_knot_at_the_position(at, wires):
    """A third of ten segments is a knot of twelve, so that wire only re-meshes;
    the others fit no knot count up to twenty and split."""
    eng = NEC5Engine(_b(feed_at=at), require_exe=False)
    assert len(eng._wires) == wires
    ((idx, _type, _v, knot),) = eng._sources
    seg, end = eng._source_address(idx, knot)
    w = eng._wires[idx]
    point = np.asarray(w.p0) + seg / w.n_seg * (np.subtract(w.p1, w.p0))
    assert end == 2
    assert np.linalg.norm(point - _target(at)) <= 1e-9 * LENGTH


def _cards(deck, mnemonic):
    return [line.split() for line in deck.splitlines() if line[:2] == mnemonic]


def _deck_site(deck, knot):
    """The point the deck's one EX card names, from its GW cards: a segment's
    centre, or (``knot``) the end-2 knot of that segment."""
    gw = {
        int(c[1]): (int(c[2]), np.array(c[3:6], float), np.array(c[6:9], float))
        for c in _cards(deck, "GW")
    }
    ((_ex, _type, tag, seg, *_),) = _cards(deck, "EX")
    n, a, b = gw[int(tag)]
    frac = int(seg) / n if knot else (int(seg) - 0.5) / n
    return len(gw), int(tag), int(seg), n, a + frac * (b - a)


@pytest.mark.parametrize(
    ("at", "pieces"),
    [(1 / 3, 2), (2 / 3, 2), (0.31, 2)] + [(a, 3) for a in NEAR_MIDDLE],
)
def test_the_nec2_export_writes_the_pieces_and_the_source_mid_piece(at, pieces):
    pytest.importorskip("PyNEC")
    from antennaknobs.nec_export import export_nec

    deck = export_nec(_b(feed_at=at), ground=None, include_rp=False)
    wires, _tag, seg, n, point = _deck_site(deck, knot=False)
    assert wires == pieces
    assert seg == (n + 1) // 2 and n % 2 == 1
    # the deck prints seven significant figures
    assert np.linalg.norm(point - _target(at)) <= 1e-6 * LENGTH


@pytest.mark.parametrize(
    ("at", "pieces"), [(0.31, 2), (0.69, 2)] + [(a, 3) for a in NEAR_MIDDLE]
)
def test_the_nec5_export_writes_the_pieces_and_the_source_mid_piece(at, pieces):
    from antennaknobs.nec5_export import export_nec5

    deck = export_nec5(
        _b(feed_at=at), design="test.split", rung="n=10", ground_name="free space"
    )
    wires, _tag, seg, n, point = _deck_site(deck, knot=True)
    assert wires == pieces
    assert seg == n // 2 and n % 2 == 0
    assert np.linalg.norm(point - _target(at)) <= 1e-6 * LENGTH


# ---------------------------------------------------------------------------
# the split itself
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("at", "cut", "counts", "names"),
    [(0.31, 0.62, [6, 4], ["w", None]), (0.69, 0.38, [4, 6], [None, "w"])],
)
def test_the_pieces_meet_at_the_cut_in_the_wires_direction_with_its_spec(
    at, cut, counts, names
):
    eng = NEC5Engine(_b(_ThickDipole, feed_at=at), require_exe=False)
    a, b = (as_wire(t) for t in eng.tups)
    point = _target(cut)
    np.testing.assert_allclose(
        [a.p0, a.p1, b.p0, b.p1], [P0, point, point, P1], rtol=0, atol=1e-12
    )
    assert [a.n_seg, b.n_seg] == counts
    assert [a.name, b.name] == names
    assert a.spec == b.spec == THICK
    assert eng._split_feeds == {"feed": ("w", at, (pytest.approx(cut),))}


@pytest.mark.parametrize("at", NEAR_MIDDLE)
@pytest.mark.parametrize("engine", ["pynec", "nec5"])
def test_a_feed_near_the_middle_splits_in_three_and_leaves_no_sliver(engine, at):
    """A filler at each end: the nearer one authored segment long, the far one
    the rest, and the carrying piece centred on the port between them."""
    eng = (
        _pynec(feed_at=at)
        if engine == "pynec"
        else NEC5Engine(_b(_ThickDipole, feed_at=at), require_exe=False)
    )
    ws = [as_wire(t) for t in eng.tups]
    assert [w.name for w in ws] == [None, "w", None]
    ends = [P0] + [np.asarray(w.p1) for w in ws[:-1]] + [P1]
    np.testing.assert_allclose(
        [e for w in ws for e in (w.p0, w.p1)],
        [e for pair in itertools.pairwise(ends) for e in pair],
        rtol=0,
        atol=1e-12,
    )
    middle = 0.5 * (np.asarray(ws[1].p0) + np.asarray(ws[1].p1))
    assert np.linalg.norm(middle - _target(at)) <= 1e-9 * LENGTH
    h = LENGTH / 10
    lengths = [float(np.linalg.norm(np.subtract(w.p1, w.p0))) for w in ws]
    assert min(lengths) >= h / 2
    segment = [length / w.n_seg for length, w in zip(lengths, ws, strict=True)]
    assert max(segment) / min(segment) <= 2
    (note,) = eng.advisories
    lo, hi = eng._split_feeds["feed"][2]
    assert f"split in three at {lo:.4g} and {hi:.4g} of its length" in note["text"]
    if engine == "nec5":
        assert {w.spec for w in ws} == {THICK}


def test_a_wire_of_two_segments_keeps_the_two_piece_split():
    """Two segments leave no room for a filler: at 0.49 the nearer filler would
    need half a segment and still leave the carrying piece under half of one."""
    eng = NEC5Engine(_b(n_seg=2, feed_at=0.49), require_exe=False)
    assert len(eng.tups) == 2


def test_one_note_says_where_the_port_asked_to_be_and_where_the_wire_was_cut():
    (note,) = NEC5Engine(_b(feed_at=0.31), require_exe=False).advisories
    assert note == {
        "category": "FeedPlacement",
        "text": (
            "Port 'feed' asks for 0.31 of the way along wire 'w'. No segment count "
            "up to 2× the wire's own puts a knot there, so the wire is split in two "
            "at 0.62 of its length and the port is fed exactly, at the middle of its "
            "piece (AK#1510)."
        ),
    }


def test_pynec_says_segment_centre():
    (note,) = _pynec(feed_at=1 / 3).advisories
    assert "puts a segment centre there" in note["text"]
    assert "split in two at 0.6667" in note["text"]


def test_two_unreachable_ports_on_one_wire_keep_the_count_and_the_nearest_site():
    eng = NEC5Engine(_b(feed_at=0.31, load_at=0.77), require_exe=False)
    assert [as_wire(t).n_seg for t in eng.tups] == [10]
    notes = eng.advisories
    assert len(notes) == 2 and all("mm away" in n["text"] for n in notes)


def test_momwire_feeds_the_exact_arclength_and_never_splits():
    from antennaknobs.engines.momwire import MomwireEngine

    eng = MomwireEngine(_b(feed_at=1 / 3))
    assert eng._split_feeds == {}
    assert len(eng._edge_segments) == 1


def test_the_builders_network_keeps_its_position():
    b = _b(feed_at=0.31)
    eng = NEC5Engine(b, require_exe=False)
    assert b.build_network().ports["feed"].at == 0.31
    assert eng._network_as_meshed(b.build_network()).ports["feed"] == PortOnWire(
        "feed", wire="w"
    )


# ---------------------------------------------------------------------------
# readers that index by the design's own wires
# ---------------------------------------------------------------------------


def test_nec5_joins_the_pieces_currents_back_into_the_wire():
    eng = NEC5Engine(_b(feed_at=0.31), require_exe=False)
    (wc,) = eng._currents_from({1: [1.0] * 6, 2: [2.0] * 4})
    np.testing.assert_allclose(wc.knot_positions[[0, 6, -1]], [P0, _target(0.62), P1])
    assert wc.knot_positions.shape == (11, 3)
    # the knot at the cut: the mean of the two pieces' neighbouring currents
    assert wc.knot_currents[6] == 1.5


def test_nec2_meshes_as_its_deck_does_and_joins_the_currents(monkeypatch):
    pytest.importorskip("PyNEC")
    from antennaknobs.engines import nec2

    monkeypatch.setattr(nec2, "find_nec2", lambda explicit=None: "/bin/true")
    eng = nec2.NEC2Engine(_b(feed_at=1 / 3))
    assert [t[2] for t in eng.tups] == [t[2] for t in _pynec(feed_at=1 / 3).tups]
    (wc,) = eng._currents_from({1: [1.0] * 7, 2: [3.0] * 3})
    assert wc.knot_positions.shape == (11, 3) and wc.knot_currents[7] == 2.0


def test_nec5_joins_three_pieces_back_into_the_wire():
    eng = NEC5Engine(_b(feed_at=0.499), require_exe=False)
    counts = [as_wire(t).n_seg for t in eng.tups]
    (wc,) = eng._currents_from({i + 1: [float(i)] * c for i, c in enumerate(counts)})
    assert wc.knot_positions.shape == (sum(counts) + 1, 3)
    np.testing.assert_allclose(wc.knot_positions[[0, -1]], [P0, P1])


def test_the_workbench_marker_sits_at_the_position_on_the_joined_wire():
    import antennaknobs.web.examples  # noqa: F401  registration order
    from antennaknobs.web import adapter

    b = _b(feed_at=1 / 3)
    eng = _pynec(feed_at=1 / 3)
    eng.impedance()
    (wc,) = eng.current_distribution()
    assert wc.knot_positions.shape == (11, 3)
    pos = adapter._pynec_feed_position(b, [wc])
    assert np.linalg.norm(np.asarray(pos) - _target(1 / 3)) <= 1e-9 * LENGTH


def test_simnec_station_cards_feed_the_middle_of_the_piece():
    from antennaknobs.simnec_export import _station_cards

    eng = _pynec(feed_at=1 / 3)
    cards = _station_cards(eng, "feed", [], FREQ)
    assert [" ".join(c.split()[:4]) for c in cards if c.startswith("EX")] == [
        "EX 0 1 4"
    ]


# ---------------------------------------------------------------------------
# the physics
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def centre_fed_d():
    """D: PyNEC against momwire on the centre-fed dipole at 101 segments."""
    from antennaknobs.engines.momwire import MomwireEngine

    return abs(_z(_pynec(n_seg=101)) - _z(MomwireEngine(_b(n_seg=101))))


@pytest.mark.parametrize(("at", "pieces"), [(1 / 3, 2), (0.499, 3)])
def test_the_split_feed_agrees_with_the_exact_arclength_as_a_centre_feed_does(
    centre_fed_d, at, pieces
):
    """Self-calibrating: PyNEC split-fed must agree with momwire fed at the
    exact arclength within 2 D, at the same 101 segments. Measured: D = 0.049
    ohm; a third, in two pieces, 0.061 ohm (1.23 D), where the nearest centre
    of the parity count was 0.682 ohm."""
    from antennaknobs.engines.momwire import MomwireEngine

    split = _pynec(n_seg=101, feed_at=at)
    assert len(split.tups) == pieces
    exact = _z(MomwireEngine(_b(n_seg=101, feed_at=at)))
    assert abs(_z(split) - exact) <= 2 * centre_fed_d

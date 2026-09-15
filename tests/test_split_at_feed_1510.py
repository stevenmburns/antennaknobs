"""AK#1510 unit 2: a positioned port that no segment count up to the cap can
carry is fed exactly, through a split wire.

On a grid engine, a wire whose positioned port is not a site of the wire's own
segment count is split so the port sits exactly on one; the count is never
changed to reach a site (AK#1511, split-always). PyNEC and NEC-2 need a segment
centre, so the port gets a short piece centred on it, with plain wire at each
end, or running to a wire end within one segment of it (AK#1511's rule, which
replaced the two- and three-piece split first built here). NEC-5 feeds a
knot, so the wire breaks at the port itself and the source sits at the knot the
two pieces share. Every reader of the port's position (segment, knot, card,
drive point, port current) sees that site. The momwire engine never splits.
Several ports on one wire are `test_multi_port_split_1511`'s.
"""

from __future__ import annotations

import itertools
from types import MappingProxyType

import numpy as np
import pytest
from conftest import needs_nec5

from antennaknobs import AntennaBuilder, WireSpec
from antennaknobs.engines.nec5 import NEC5Engine
from antennaknobs.network import (
    TL,
    Driven,
    Load,
    Network,
    PortAtVertex,
    PortOnWire,
    PortVirtual,
    Wire,
    as_wire,
)

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


# Near the middle, where #1510's two-piece split left a sliver.
NEAR_MIDDLE = [0.49, 0.499, 0.5001]
# None of these is a knot of ten segments, so NEC-5 breaks the wire.
KNOT_BREAKS = [0.31, 0.69, 0.123, 0.499, 0.02, 0.49, 0.5001]


# ---------------------------------------------------------------------------
# the fed site is the stated position
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("at", "wires"),
    # 0.02 is within a segment of the p0 end with nothing tighter, so its piece
    # runs to that end and there is no filler there.
    [(1 / 3, 3), (2 / 3, 3), (0.31, 3), (0.02, 2)] + [(a, 3) for a in NEAR_MIDDLE],
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


@pytest.mark.parametrize("at", [1 / 3, *KNOT_BREAKS])
def test_nec5_feeds_a_knot_at_the_position(at):
    """No knot of ten segments sits at any of these, a third included, so the
    wire breaks at the port, fed at the end knot of the first piece."""
    eng = NEC5Engine(_b(feed_at=at), require_exe=False)
    assert len(eng._wires) == 2
    ((idx, _type, _v, knot),) = eng._sources
    assert (idx, knot) == (0, "p1")
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


@pytest.mark.parametrize("at", [1 / 3, 2 / 3, 0.31, *NEAR_MIDDLE])
def test_the_nec2_export_writes_the_pieces_and_the_source_mid_piece(at):
    pytest.importorskip("PyNEC")
    from antennaknobs.nec_export import export_nec

    deck = export_nec(_b(feed_at=at), ground=None, include_rp=False)
    wires, _tag, seg, n, point = _deck_site(deck, knot=False)
    assert wires == 3
    assert seg == (n + 1) // 2 and n % 2 == 1
    # the deck prints seven significant figures
    assert np.linalg.norm(point - _target(at)) <= 1e-6 * LENGTH


@pytest.mark.parametrize("at", KNOT_BREAKS)
def test_the_nec5_export_writes_two_wires_and_the_source_at_the_shared_knot(at):
    from antennaknobs.nec5_export import export_nec5

    deck = export_nec5(
        _b(feed_at=at), design="test.split", rung="n=10", ground_name="free space"
    )
    wires, tag, seg, n, point = _deck_site(deck, knot=True)
    ((*_, end, _re, _im),) = _cards(deck, "EX")
    assert wires == 2
    # the last segment of the first piece, end 2: the knot the pieces share
    assert (tag, seg, end) == (1, n, "2")
    assert np.linalg.norm(point - _target(at)) <= 1e-6 * LENGTH


# ---------------------------------------------------------------------------
# the split itself
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("engine", "at", "cuts", "counts", "names"),
    [
        ("nec5", 0.31, [0.31], [3, 7], ["w@feed", None]),
        ("nec5", 0.69, [0.69], [7, 3], ["w@feed", None]),
        # a third of the distance to the nearer end either side of the port
        (
            "pynec",
            0.31,
            [0.31 - 0.31 / 3, 0.31 + 0.31 / 3],
            [2, 3, 6],
            [None, "w@feed", None],
        ),
        (
            "pynec",
            0.69,
            [0.69 - 0.31 / 3, 0.69 + 0.31 / 3],
            [6, 3, 2],
            [None, "w@feed", None],
        ),
    ],
)
def test_the_pieces_meet_at_the_cuts_in_the_wires_direction_with_its_spec(
    engine, at, cuts, counts, names
):
    if engine == "nec5":
        eng = NEC5Engine(_b(_ThickDipole, feed_at=at), require_exe=False)
    else:
        pytest.importorskip("PyNEC")
        from antennaknobs.engines.pynec import PyNECEngine

        eng = PyNECEngine(_b(_ThickDipole, feed_at=at), ground=None)
    ws = [as_wire(t) for t in eng.tups]
    ends = [P0, *(_target(c) for c in cuts), P1]
    np.testing.assert_allclose(
        [e for w in ws for e in (w.p0, w.p1)],
        [e for pair in itertools.pairwise(ends) for e in pair],
        rtol=0,
        atol=1e-12,
    )
    assert [w.n_seg for w in ws] == counts
    assert [w.name for w in ws] == names
    assert all(w.spec == THICK for w in ws)
    split = eng._split_wires["w"]
    assert split.ports == (("feed", at),) and split.pieces == ("w@feed",)


@pytest.mark.parametrize("at", KNOT_BREAKS)
def test_nec5_breaks_at_the_port_with_no_parity_and_no_sliver_rule(at):
    """Each piece takes its own share of the ten segments, at least one: at
    0.02 that is one segment a fifth as long as the rest, measured and kept."""
    eng = NEC5Engine(_b(feed_at=at), require_exe=False)
    ws = [as_wire(t) for t in eng.tups]
    assert [w.n_seg for w in ws] == [
        max(1, round(10 * at)),
        max(1, round(10 * (1 - at))),
    ]
    np.testing.assert_allclose(
        [ws[0].p1, ws[1].p0], [_target(at), _target(at)], rtol=0, atol=1e-12
    )


@pytest.mark.parametrize("at", [1 / 3, 0.31, *NEAR_MIDDLE])
def test_a_lone_port_gets_a_centred_piece_between_two_fillers(at):
    """A third of the distance to the nearer end either side of the port, and a
    filler at each end at least two thirds of its end distance: no sliver, even
    next to the middle where #1510's two-piece split left one."""
    eng = _pynec(feed_at=at)
    ws = [as_wire(t) for t in eng.tups]
    assert [w.name for w in ws] == [None, "w@feed", None]
    ends = [P0] + [np.asarray(w.p1) for w in ws[:-1]] + [P1]
    np.testing.assert_allclose(
        [e for w in ws for e in (w.p0, w.p1)],
        [e for pair in itertools.pairwise(ends) for e in pair],
        rtol=0,
        atol=1e-12,
    )
    middle = 0.5 * (np.asarray(ws[1].p0) + np.asarray(ws[1].p1))
    assert np.linalg.norm(middle - _target(at)) <= 1e-9 * LENGTH
    lengths = [float(np.linalg.norm(np.subtract(w.p1, w.p0))) for w in ws]
    near = min(at, 1 - at) * LENGTH
    assert lengths[1] == pytest.approx(2 * near / 3, rel=1e-12)
    assert lengths[0] >= 2 * at * LENGTH / 3 * (1 - 1e-12)
    assert lengths[2] >= 2 * (1 - at) * LENGTH / 3 * (1 - 1e-12)
    segment = [length / w.n_seg for length, w in zip(lengths, ws, strict=True)]
    assert max(segment) / min(segment) <= 2
    (note,) = eng.advisories
    assert "at the middle of a short piece of its own" in note["text"]


def test_a_wire_of_two_segments_splits_by_the_same_rule():
    """No special case for a short wire: 0.49 on two segments is more than a
    segment's half from either end's limit, so it gets three one-segment
    pieces, the middle one centred on the port."""
    eng = _pynec(n_seg=2, feed_at=0.49)
    ws = [as_wire(t) for t in eng.tups]
    assert [(w.n_seg, w.name) for w in ws] == [(1, None), (1, "w@feed"), (1, None)]
    middle = 0.5 * (np.asarray(ws[1].p0) + np.asarray(ws[1].p1))
    assert np.linalg.norm(middle - _target(0.49)) <= 1e-9 * LENGTH


def test_one_note_says_where_the_port_asked_to_be_and_how_it_is_fed():
    (note,) = NEC5Engine(_b(feed_at=0.31), require_exe=False).advisories
    assert note == {
        "category": "FeedPlacement",
        "text": (
            "Wire 'w' carries port 'feed' at 0.31 of its length, which is not a "
            "knot of its 10 segments, so the wire is split there and the port is "
            "fed exactly, at the knot the two pieces share (AK#1511)."
        ),
    }


def test_pynec_says_segment_centre():
    (note,) = _pynec(feed_at=1 / 3).advisories
    assert "which is not a segment centre of its 10 segments" in note["text"]
    assert "at the middle of a short piece of its own" in note["text"]


def test_two_unreachable_ports_on_one_wire_split_it_at_both():
    eng = NEC5Engine(_b(feed_at=0.31, load_at=0.77), require_exe=False)
    assert [(as_wire(t).n_seg, as_wire(t).name) for t in eng.tups] == [
        (3, "w@feed"),
        (5, "w@load"),
        (2, None),
    ]
    (note,) = eng.advisories
    assert "'feed' at 0.31 and 'load' at 0.77" in note["text"]
    assert "mm away" not in note["text"]


def test_momwire_feeds_the_exact_arclength_and_never_splits():
    from antennaknobs.engines.momwire import MomwireEngine

    eng = MomwireEngine(_b(feed_at=1 / 3))
    assert eng._split_wires == {}
    assert len(eng._edge_segments) == 1


def test_the_builders_network_keeps_its_position():
    b = _b(feed_at=0.31)
    nec5 = NEC5Engine(b, require_exe=False)
    assert b.build_network().ports["feed"].at == 0.31
    # a knot engine: the series source at the end the two pieces share
    assert nec5._network_as_meshed(b.build_network()).ports["feed"] == PortAtVertex(
        wire="w@feed", end="p1"
    )
    # a segment-centre engine: the middle of the port's own piece
    pynec = _pynec(feed_at=0.31)
    assert pynec._network_as_meshed(b.build_network()).ports["feed"] == PortOnWire(
        "feed", wire="w@feed"
    )


# ---------------------------------------------------------------------------
# readers that index by the design's own wires
# ---------------------------------------------------------------------------


def test_nec5_joins_the_pieces_currents_back_into_the_wire():
    import antennaknobs.web.examples  # noqa: F401  registration order
    from antennaknobs.web import adapter

    b = _b(feed_at=0.31)
    eng = NEC5Engine(b, require_exe=False)
    (wc,) = eng._currents_from({1: [1.0] * 3, 2: [2.0] * 7})
    np.testing.assert_allclose(wc.knot_positions[[0, 3, -1]], [P0, _target(0.31), P1])
    assert wc.knot_positions.shape == (11, 3)
    # the knot at the cut: the mean of the two pieces' neighbouring currents
    assert wc.knot_currents[3] == 1.5
    # the workbench marker lands on the fed knot
    pos = adapter._pynec_feed_position(b, [wc])
    assert np.linalg.norm(np.asarray(pos) - _target(0.31)) <= 1e-9 * LENGTH


class _LineFedDipole(_Dipole):
    """The feed reached through a line from a virtual source: the reducer
    route, which reads each undriven port's current from the wire currents."""

    def build_network(self):
        return Network(
            ports={
                "src": PortVirtual("src"),
                "feed": PortOnWire("feed", wire="w", at=self.feed_at),
            },
            branches=[TL(a="src", b="feed", z0=50.0, length=1.0)],
            sources=[Driven(port="src")],
        )


class _ApexDipole(AntennaBuilder):
    """Two wires meeting at a vertex source, the same geometry authored whole
    as a split would make it: a real junction, not a split."""

    default_params = MappingProxyType({"freq": FREQ, "design_freq": FREQ})

    def build_wires(self):
        cut = tuple(_target(0.31))
        return [Wire(tuple(P0), cut, n_seg=3, name="w"), Wire(cut, tuple(P1), n_seg=7)]

    def build_network(self):
        return Network(
            ports={"src": PortVirtual("src"), "feed": PortAtVertex(wire="w")},
            branches=[TL(a="src", b="feed", z0=50.0, length=1.0)],
            sources=[Driven(port="src")],
        )


def test_nec5_reads_a_split_ports_current_across_the_cut():
    """An undriven port's current interpolates the two neighbouring segment
    centres, weighted by the other's length, as at any interior knot. A vertex
    where two authored wires meet keeps its named arm's own current."""
    per_tag = {1: [1.0] * 3, 2: [3.0] * 7}
    eng = NEC5Engine(_b(_LineFedDipole, feed_at=0.31), require_exe=False)
    assert eng._use_reducer and eng._port_attach["feed"] == (0, "p1")
    h_a, h_b = 0.31 * LENGTH / 3, 0.69 * LENGTH / 7
    assert eng._port_knot_current(per_tag, 0, "p1") == pytest.approx(
        (1.0 * h_b + 3.0 * h_a) / (h_a + h_b), rel=1e-12
    )
    apex = NEC5Engine(_ApexDipole(), require_exe=False)
    assert apex._port_knot_current(per_tag, 0, "p1") == 1.0


def test_nec2_meshes_as_its_deck_does_and_joins_the_currents(monkeypatch):
    pytest.importorskip("PyNEC")
    from antennaknobs.engines import nec2

    monkeypatch.setattr(nec2, "find_nec2", lambda explicit=None: "/bin/true")
    eng = nec2.NEC2Engine(_b(feed_at=1 / 3))
    counts = [t[2] for t in eng.tups]
    assert counts == [t[2] for t in _pynec(feed_at=1 / 3).tups] == [2, 3, 6]
    (wc,) = eng._currents_from({1: [1.0] * 2, 2: [2.0] * 3, 3: [3.0] * 6})
    assert wc.knot_positions.shape == (12, 3)
    assert wc.knot_currents[2] == 1.5 and wc.knot_currents[5] == 2.5


def test_nec2_joins_three_pieces_back_into_the_wire(monkeypatch):
    pytest.importorskip("PyNEC")
    from antennaknobs.engines import nec2

    monkeypatch.setattr(nec2, "find_nec2", lambda explicit=None: "/bin/true")
    eng = nec2.NEC2Engine(_b(feed_at=0.499))
    counts = [as_wire(t).n_seg for t in eng.tups]
    assert len(counts) == 3
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
    assert wc.knot_positions.shape == (12, 3)
    pos = adapter._pynec_feed_position(b, [wc])
    assert np.linalg.norm(np.asarray(pos) - _target(1 / 3)) <= 1e-9 * LENGTH


def test_simnec_station_cards_feed_the_middle_of_the_piece():
    from antennaknobs.simnec_export import _station_cards

    eng = _pynec(feed_at=1 / 3)
    cards = _station_cards(eng, "feed", [], FREQ)
    # the port's own piece is wire 2, three segments long
    assert [" ".join(c.split()[:4]) for c in cards if c.startswith("EX")] == [
        "EX 0 2 2"
    ]


# ---------------------------------------------------------------------------
# the physics
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def centre_fed_d():
    """D: PyNEC against momwire on the centre-fed dipole at 101 segments."""
    from antennaknobs.engines.momwire import MomwireEngine

    return abs(_z(_pynec(n_seg=101)) - _z(MomwireEngine(_b(n_seg=101))))


@pytest.mark.parametrize("at", [1 / 3, 0.499])
def test_the_split_feed_agrees_with_the_exact_arclength_as_a_centre_feed_does(
    centre_fed_d, at
):
    """Self-calibrating: PyNEC split-fed must agree with momwire fed at the
    exact arclength within 2 D, at the same 101 segments. Measured: D = 0.049
    ohm, where the nearest centre of the parity count was 0.682 ohm off at a
    third."""
    from antennaknobs.engines.momwire import MomwireEngine

    split = _pynec(n_seg=101, feed_at=at)
    assert len(split.tups) == 3
    exact = _z(MomwireEngine(_b(n_seg=101, feed_at=at)))
    assert abs(_z(split) - exact) <= 2 * centre_fed_d


# ---------------------------------------------------------------------------
# live NEC-5
# ---------------------------------------------------------------------------


class _LoadedWhole(AntennaBuilder):
    default_params = MappingProxyType({"freq": FREQ, "design_freq": FREQ})

    def build_wires(self):
        return [Wire(tuple(P0), tuple(P1), n_seg=10, name="w")]

    def build_network(self):
        return Network(
            ports={"feed": PortOnWire("feed", wire="w", at=0.3)},
            branches=[Load(port="feed", r=10.0)],
            sources=[Driven(port="feed")],
        )


class _LoadedPieces(_LoadedWhole):
    def build_wires(self):
        cut = tuple(_target(0.3))
        return [Wire(tuple(P0), cut, n_seg=3, name="w"), Wire(cut, tuple(P1), n_seg=7)]

    def build_network(self):
        return Network(
            ports={"feed": PortAtVertex(wire="w")},
            branches=[Load(port="feed", r=10.0)],
            sources=[Driven(port="feed")],
        )


@needs_nec5
def test_nec5_feeds_the_shared_knot_as_it_feeds_that_knot_of_the_whole_wire():
    """The vertex source a break makes, with a series load on it, against the
    interior knot source at the same point of the same ten segments. Measured:
    125.59+j31.839 both."""
    whole = _z(NEC5Engine(_LoadedWhole(), ground=None))
    pieces = _z(NEC5Engine(_LoadedPieces(), ground=None))
    assert abs(pieces - whole) <= 1e-9 * abs(whole)


@pytest.fixture(scope="module")
def nec5_centre_fed_d():
    """D5 on the centre-fed dipole at 100 segments: |Z_NEC-5 - Z_momwire|, and
    that as a fraction of |Z|."""
    from antennaknobs.engines.momwire import MomwireEngine

    nec5 = _z(NEC5Engine(_b(n_seg=100), ground=None))
    mom = _z(MomwireEngine(_b(n_seg=100)))
    return abs(nec5 - mom), abs(nec5 - mom) / abs(mom)


@needs_nec5
def test_nec5_split_feed_agrees_with_the_exact_arclength_as_a_centre_feed_does(
    nec5_centre_fed_d,
):
    """Self-calibrating at 100 segments. Measured: D5 = 1.626 ohm (1.78 % of
    |Z|). A break at 0.333, |Z| near 108 ohm, is 2.197 ohm from momwire's exact
    arclength (1.35 D5).

    At 0.123 |Z| is near 640 ohm and the two engines disagree in proportion,
    whole wire or split: 0.12, a knot of the whole wire, is 16.35 ohm off
    (2.41 %), and 0.125, re-meshed to 104 segments, 12.25 ohm (1.95 %). So the
    gate there is relative, and the break's 13.14 ohm is 2.03 %."""
    from antennaknobs.engines.momwire import MomwireEngine

    d5, d5_rel = nec5_centre_fed_d
    for at, bound in [(0.333, 2 * d5), (0.123, None)]:
        split = NEC5Engine(_b(n_seg=100, feed_at=at), ground=None)
        assert len(split.tups) == 2
        exact = _z(MomwireEngine(_b(n_seg=100, feed_at=at)))
        miss = abs(_z(split) - exact)
        if bound is None:
            assert miss / abs(exact) <= 2 * d5_rel
        else:
            assert miss <= bound

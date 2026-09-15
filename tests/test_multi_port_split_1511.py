"""AK#1511: every positioned port on a wire is fed exactly, however many share it.

When no segment count up to twice a wire's own puts every port on it on a site
of the engine's grid, a grid engine splits the wire. PyNEC and NEC-2 give each
port a short piece centred on it, reaching a quarter of the way to its
neighbours or a third of the way to a wire end, with plain wire in between; a
port within a segment of an end, with nothing tighter nearby, runs its piece to
that end. NEC-5 cuts the wire at every port and feeds the knot the pieces on
either side share. The momwire engine's solvers split the same way, each like
the engines of its family (AK#1519).

The k = 2 and k = 3 designs are the demo decks' geometry: a 10.5 m dipole at
10 m, 1 mm radius, ten segments, at 14.2 MHz, fed at 0.31 with 50 ohm loads.
"""

from __future__ import annotations

import itertools
import random
from types import MappingProxyType

import numpy as np
import pytest
from conftest import needs_nec5

from antennaknobs import AntennaBuilder, WireSpec
from antennaknobs.engine import _nearest_count, _nearest_odd_count, split_spans
from antennaknobs.engines.nec5 import NEC5Engine
from antennaknobs.network import (
    TL,
    Driven,
    Load,
    Network,
    PortOnWire,
    PortVirtual,
    Wire,
    as_wire,
)
from antennaknobs.wire_catalog import on_site

pytestmark = pytest.mark.skipif(
    not hasattr(PortOnWire("x"), "at"),
    reason="the installed momwire's PortOnWire has no wire/at (momwire#1059)",
)

FREQ = 14.2
P0 = np.array((0.0, -5.25, 10.0))
P1 = np.array((0.0, 5.25, 10.0))
LENGTH = 10.5


class _Demo(AntennaBuilder):
    """A feed at `feed_at` (None: the middle) and a 50 ohm load at each of
    `load_ats`, all on the one wire."""

    default_params = MappingProxyType(
        {
            "freq": FREQ,
            "design_freq": FREQ,
            "n_seg": 10,
            "feed_at": 0.31,
            "load_ats": (),
        }
    )

    def build_wires(self):
        return [Wire(tuple(P0), tuple(P1), n_seg=self.n_seg, name="w")]

    def build_wire_material(self):
        return WireSpec(radius=1e-3)

    def _ports(self):
        ports = {"feed": PortOnWire("feed", wire="w", at=self.feed_at)}
        loads = []
        for i, at in enumerate(self.load_ats):
            ports[f"load{i}"] = PortOnWire(f"load{i}", wire="w", at=at)
            loads.append(Load(port=f"load{i}", r=50.0))
        return ports, loads

    def build_network(self):
        ports, loads = self._ports()
        return Network(ports=ports, branches=loads, sources=[Driven(port="feed")])


class _LineFed(_Demo):
    """The same ports with the feed reached through a line from a virtual
    source: the reducer route on PyNEC and NEC-5."""

    def build_network(self):
        ports, loads = self._ports()
        ports["src"] = PortVirtual("src")
        return Network(
            ports=ports,
            branches=[TL(a="src", b="feed", z0=50.0, length=1.0), *loads],
            sources=[Driven(port="src")],
        )


def _b(cls=_Demo, **params):
    return cls(dict(cls.default_params, **params))


def _targets(builder):
    """{port: the point it asks for}."""
    out = {}
    for name, port in builder.build_network().ports.items():
        if isinstance(port, PortOnWire):
            at = 0.5 if port.at is None else port.at
            out[name] = P0 + at * (P1 - P0)
    return out


def _z(eng):
    return complex(np.atleast_1d(eng.impedance())[0])


def _pynec(builder):
    pytest.importorskip("PyNEC")
    from antennaknobs.engines.pynec import PyNECEngine

    return PyNECEngine(builder, ground=None)


CASES = {
    "k1-third": dict(feed_at=1 / 3),
    "k1-0.31": dict(feed_at=0.31),
    "k1-0.499": dict(feed_at=0.499),
    "k1-0.02": dict(feed_at=0.02),
    "k2": dict(feed_at=0.31, load_ats=(0.77,)),
    "k3": dict(feed_at=0.31, load_ats=(0.04, 0.77)),
    # 0.04 apart on segments of 0.1: closer than one segment
    "k2-close": dict(feed_at=0.31, load_ats=(0.35,)),
}


def _cards(deck, mnemonic):
    return [line.split() for line in deck.splitlines() if line[:2] == mnemonic]


def _gw(deck):
    return {
        int(c[1]): (int(c[2]), np.array(c[3:6], float), np.array(c[6:9], float))
        for c in _cards(deck, "GW")
    }


def _assert_sites(sites, targets, tol):
    """`sites` {"EX": [points], "LD": [points]} name exactly the feed and the
    loads' targets, each within `tol`."""
    feed = [targets["feed"]]
    loads = [p for name, p in targets.items() if name != "feed"]
    for got, want in ((sites["EX"], feed), (sites["LD"], loads)):
        assert len(got) == len(want)
        for g, w in zip(
            sorted(got, key=lambda p: p[1]),
            sorted(want, key=lambda p: p[1]),
            strict=True,
        ):
            assert np.linalg.norm(g - w) <= tol


# ---------------------------------------------------------------------------
# (a) exactness: every fed centre or knot is its port
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("case", CASES)
def test_pynec_feeds_every_port_at_a_segment_centre_on_its_position(case):
    b = _b(**CASES[case])
    eng = _pynec(b)
    eng.impedance()
    assert "w" in eng._split_wires
    targets = _targets(b)
    assert set(eng._network_port_loc) == set(targets)
    for port, (tag, seg) in eng._network_port_loc.items():
        w = as_wire(eng.tups[tag - 1])
        assert w.name == f"w@{port}" and seg == (w.n_seg + 1) // 2
        centre = np.asarray(w.p0) + (seg - 0.5) / w.n_seg * np.subtract(w.p1, w.p0)
        assert np.linalg.norm(centre - targets[port]) <= 1e-9 * LENGTH


@pytest.mark.parametrize("case", CASES)
def test_nec2_feeds_every_port_at_the_middle_of_its_piece_and_its_deck_says_so(
    case, monkeypatch
):
    pytest.importorskip("PyNEC")
    from antennaknobs.engines import nec2

    monkeypatch.setattr(nec2, "find_nec2", lambda explicit=None: "/bin/true")
    b = _b(**CASES[case])
    eng = nec2.NEC2Engine(b)
    targets = _targets(b)
    by_name = {as_wire(t).name: as_wire(t) for t in eng.tups}
    assert set(eng._split_ports) == set(targets)
    for port, piece in eng._split_ports.items():
        w = by_name[piece]
        seg = (w.n_seg + 1) // 2
        assert w.n_seg % 2 == 1
        centre = np.asarray(w.p0) + (seg - 0.5) / w.n_seg * np.subtract(w.p1, w.p0)
        assert np.linalg.norm(centre - targets[port]) <= 1e-9 * LENGTH
    _assert_sites(_nec2_deck_sites(eng.deck(FREQ)), targets, 1e-6 * LENGTH)


def _nec2_deck_sites(deck):
    """EX and load LD sites of a NEC-2 deck: the centre of the named segment."""
    gw = _gw(deck)

    def centre(tag, seg):
        n, a, b = gw[int(tag)]
        return a + (int(seg) - 0.5) / n * (b - a)

    return {
        "EX": [centre(c[2], c[3]) for c in _cards(deck, "EX")],
        "LD": [centre(c[2], c[3]) for c in _cards(deck, "LD") if int(c[3]) > 0],
    }


@pytest.mark.parametrize("case", CASES)
def test_the_nec2_export_writes_every_port_at_its_position(case):
    pytest.importorskip("PyNEC")
    from antennaknobs.nec_export import export_nec

    b = _b(**CASES[case])
    deck = export_nec(b, ground=None, include_rp=False)
    # the deck prints seven significant figures
    _assert_sites(_nec2_deck_sites(deck), _targets(b), 1e-6 * LENGTH)


@pytest.mark.parametrize("case", CASES)
def test_nec5_feeds_every_port_at_a_knot_on_its_position(case):
    """No case's ports are all knots of the wire's own ten segments, so every
    one is cut."""
    b = _b(**CASES[case])
    eng = NEC5Engine(b, require_exe=False)
    assert "w" in eng._split_wires
    targets = _targets(b)
    ((idx, _type, _v, knot),) = eng._sources
    attach = {"feed": (idx, knot), **{br.port: (i, k) for i, k, br in eng._loads}}
    assert set(attach) == set(targets)
    for port, (idx, knot) in attach.items():
        seg, end = eng._source_address(idx, knot)
        w = eng._wires[idx]
        frac = (seg if end == 2 else seg - 1) / w.n_seg
        point = np.asarray(w.p0) + frac * np.subtract(w.p1, w.p0)
        assert np.linalg.norm(point - targets[port]) <= 1e-9 * LENGTH


@pytest.mark.parametrize("case", CASES)
def test_the_nec5_export_writes_every_port_at_its_knot(case):
    from antennaknobs.nec5_export import export_nec5

    b = _b(**CASES[case])
    deck = export_nec5(b, design="test.split", rung="n=10", ground_name="free space")
    gw = _gw(deck)

    def knot(c):
        n, a, b_ = gw[int(c[2])]
        seg, end = int(c[3]), int(c[4])
        return a + (seg if end == 2 else seg - 1) / n * (b_ - a)

    sites = {
        "EX": [knot(c) for c in _cards(deck, "EX")],
        "LD": [knot(c) for c in _cards(deck, "LD") if float(c[5]) == 50.0],
    }
    _assert_sites(sites, _targets(b), 1e-6 * LENGTH)


# ---------------------------------------------------------------------------
# (b) the rule's bounds, over a random population
# ---------------------------------------------------------------------------


def _population(seed=1511, per_k=300):
    """(n, positions) with 9-40 segments, 1-8 ports in [0.02, 0.98] at least a
    segment apart: uniform over such placements (points drawn in the room left
    after reserving the minimum gaps, then spread back out)."""
    rng = random.Random(seed)
    out = []
    for k in range(1, 9):
        made = 0
        while made < per_k:
            n = rng.randint(9, 40)
            h = 1 / n
            room = 0.96 - (k - 1) * h
            if room < 0:
                continue
            draws = sorted(rng.uniform(0, room) for _ in range(k))
            out.append((n, [0.02 + d + i * h for i, d in enumerate(draws)]))
            made += 1
    return out


def _guard_expected(n, u, side):
    """The guard's condition, derived here from the issue's rule: the end is
    within one segment and no other limit on that port is tighter."""
    h = 1 / n
    k = len(u)
    port = 0 if side == 0 else k - 1
    b = u[0] if side == 0 else 1 - u[-1]
    other = []
    if port > 0:
        other.append((u[port] - u[port - 1]) / 4)
    if port < k - 1:
        other.append((u[port + 1] - u[port]) / 4)
    if k == 1:
        other.append((1 - u[0] if side == 0 else u[0]) / 3)
    return b <= h and b <= min(other)


def _bound_failures(n, u):
    """Every way the centre-engine split of (n, u) breaks the decided bounds."""
    plan = split_spans(n, u, "odd")
    spans, k = plan.spans, len(u)
    bad = []
    if spans[0].lo != 0.0 or spans[-1].hi != 1.0:
        bad.append("does not span the wire")
    if any(a.hi != b.lo for a, b in itertools.pairwise(spans)):
        bad.append("pieces do not meet")
    fed = {s.port: j for j, s in enumerate(spans) if s.port is not None}
    if sorted(fed) != list(range(k)):
        bad.append("not one fed piece per port")
        return bad
    for i, j in fed.items():
        s = spans[j]
        if abs(0.5 * (s.lo + s.hi) - u[i]) > 1e-12:
            bad.append(f"port {i} not centred")
        if s.n_seg % 2 != 1:
            bad.append(f"port {i} piece has an even count")
    for i in range(k - 1):
        between = spans[fed[i] + 1 : fed[i + 1]]
        g = u[i + 1] - u[i]
        if len(between) != 1 or between[0].port is not None:
            bad.append(f"no single filler between ports {i} and {i + 1}")
        elif between[0].hi - between[0].lo < g / 2 - 1e-12:
            bad.append(f"filler between ports {i} and {i + 1} under g/2")
    for side in (0, 1):
        expected = _guard_expected(n, u, side)
        if plan.guard[side] != expected:
            bad.append(f"guard at end {side} is {plan.guard[side]}, rule {expected}")
        end = spans[0] if side == 0 else spans[-1]
        b = u[0] if side == 0 else 1 - u[-1]
        if plan.guard[side]:
            if end.port is None:
                bad.append(f"guard fired at end {side} but a filler remains")
        elif end.port is not None:
            bad.append(f"no filler at end {side} without the guard")
        elif end.hi - end.lo < 2 * b / 3 - 1e-12:
            bad.append(f"end filler {side} under 2b/3")
    if any(s.n_seg < 1 for s in spans):
        bad.append("a piece with no segments")
    return bad


def test_every_split_keeps_its_bounds():
    population = _population()
    failures = [
        (n, u, bad)
        for n, u in population
        if not all(on_site(n, at, "centre") for at in u)
        and (bad := _bound_failures(n, u))
    ]
    assert failures == [], f"{len(failures)} of {len(population)}: {failures[:3]}"


def test_the_guard_fires_somewhere_in_the_population():
    """Not vacuous: both ends fire, and some near-end ports do not."""
    population = _population()
    fired = [split_spans(n, u, "odd").guard for n, u in population]
    assert any(g[0] for g in fired) and any(g[1] for g in fired)
    near_unfired = [
        (n, u)
        for (n, u), g in zip(population, fired, strict=True)
        if u[0] <= 1 / n and not g[0]
    ]
    assert near_unfired


def test_a_knot_split_cuts_at_every_port():
    for n, u in _population():
        plan = split_spans(n, u, "even")
        spans = plan.spans
        assert [s.hi for s in spans[:-1]] == u
        assert spans[0].lo == 0.0 and spans[-1].hi == 1.0
        assert all(a.hi == b.lo for a, b in itertools.pairwise(spans))
        assert [s.port for s in spans] == [*range(len(u)), None]
        assert [s.n_seg for s in spans] == [
            _nearest_count((s.hi - s.lo) * n) for s in spans
        ]


# ---------------------------------------------------------------------------
# (c) the guard, pinned
# ---------------------------------------------------------------------------


def test_a_port_within_a_segment_of_an_end_runs_its_piece_to_that_end():
    """The demo's k = 3 on ten segments: 0.04 is within a segment of p0, and its
    neighbour's limit (0.31 - 0.04) / 4 is no tighter, so its piece is
    [0, 0.08], one segment, with no filler at that end."""
    plan = split_spans(10, [0.04, 0.31, 0.77], "odd")
    assert plan.guard == (True, False)
    first = plan.spans[0]
    assert (first.lo, first.port, first.n_seg) == (0.0, 0, 1)
    assert first.hi == pytest.approx(0.08, abs=1e-15)
    eng = _pynec(_b(**CASES["k3"]))
    w = as_wire(eng.tups[0])
    assert w.name == "w@load0" and w.n_seg == 1
    np.testing.assert_allclose([w.p0, w.p1], [P0, P0 + 0.08 * (P1 - P0)], atol=1e-12)


@pytest.mark.parametrize(
    ("n", "u", "guard"),
    [
        # a neighbour a quarter-gap tighter than the end: the end keeps b/3
        (10, [0.05, 0.12], (False, False)),
        # a lone port within a segment, but a third of the far side is tighter
        (2, [0.3], (False, False)),
        # a lone port near either end
        (10, [0.02], (True, False)),
        (10, [0.98], (False, True)),
    ],
)
def test_the_guard_needs_its_slack(n, u, guard):
    assert split_spans(n, u, "odd").guard == guard
    assert _bound_failures(n, u) == []


# ---------------------------------------------------------------------------
# names, the meshed network, and refusals
# ---------------------------------------------------------------------------


def test_each_port_feeds_a_piece_named_for_it_and_fillers_are_unnamed():
    eng = _pynec(_b(**CASES["k3"]))
    assert [as_wire(t).name for t in eng.tups] == [
        "w@load0",
        None,
        "w@feed",
        None,
        "w@load1",
        None,
    ]
    nec5 = NEC5Engine(_b(**CASES["k3"]), require_exe=False)
    assert [as_wire(t).name for t in nec5.tups] == [
        "w@load0",
        "w@feed",
        "w@load1",
        None,
    ]


class _Collide(_Demo):
    """A second wire already named the way a split would name the feed's
    piece, with a port of its own."""

    def build_wires(self):
        return [
            *super().build_wires(),
            Wire((1.0, -1.0, 10.0), (1.0, 1.0, 10.0), n_seg=5, name="w@feed"),
        ]

    def build_network(self):
        net = super().build_network()
        return Network(
            ports={**net.ports, "x": PortOnWire("x", wire="w@feed")},
            branches=[*net.branches, Load(port="x", r=50.0)],
            sources=net.sources,
        )


def test_a_piece_name_never_takes_a_name_the_design_uses():
    eng = _pynec(_b(_Collide, load_ats=(0.77,)))
    eng.impedance()
    names = [as_wire(t).name for t in eng.tups]
    assert names == [None, "w@feed#2", None, "w@load0", None, "w@feed"]
    assert eng._network_port_loc["feed"] == (2, 2)
    assert eng._network_port_loc["x"] == (6, 3)


class _LegacyEx(_Demo):
    def build_wires(self):
        return [Wire(tuple(P0), tuple(P1), n_seg=self.n_seg, ex=1 + 0j, name="w")]


def test_a_legacy_ex_rides_on_the_first_fed_piece():
    """PyNEC ignores `ex` beside a network; NEC-5 refuses the mix, and still
    does once the wire is split."""
    eng = _pynec(_b(_LegacyEx, load_ats=(0.77,)))
    assert [as_wire(t).ex for t in eng.tups] == [None, 1 + 0j, None, None, None]
    with pytest.raises(ValueError, match="mixes legacy Wire.ex"):
        NEC5Engine(_b(_LegacyEx, load_ats=(0.77,)), require_exe=False)


def test_two_ports_at_one_point_of_a_split_wire_are_refused():
    with pytest.raises(ValueError, match="sit at the same point of wire 'w'"):
        _pynec(_b(load_ats=(0.31,)))


def test_a_wire_whose_ports_are_all_sites_of_its_own_count_stays_whole():
    """A quarter and three quarters are segment centres of ten, and 0.3 and 0.7
    are knots of ten: each wire keeps its ten segments, and there is no note."""
    pynec = _pynec(_b(feed_at=0.25, load_ats=(0.75,)))
    assert [t[2] for t in pynec.tups] == [10] and pynec.advisories == []
    nec5 = NEC5Engine(_b(feed_at=0.3, load_ats=(0.7,)), require_exe=False)
    assert [t[2] for t in nec5.tups] == [10] and nec5.advisories == []


def test_a_positioned_wire_keeps_its_authored_count():
    """Split-always: no parity bump and no re-count. 0.3 is a segment centre of
    25 and a knot of 30, counts a re-count once reached from 20 and 21, and now
    PyNEC splits the 20-segment wire and NEC-5 cuts the 21-segment one. A port
    already on a site keeps the authored count even where parity would have
    bumped it: ten segments stay ten on both engines."""
    pynec = _pynec(_b(n_seg=20, feed_at=0.3))
    assert pynec._split_wires["w"].n_seg == 20
    nec5 = NEC5Engine(_b(n_seg=21, feed_at=0.3), require_exe=False)
    assert nec5._split_wires["w"].n_seg == 21
    assert [t[2] for t in _pynec(_b(feed_at=0.25)).tups] == [10]
    assert [
        t[2] for t in NEC5Engine(_b(n_seg=9, feed_at=1 / 3), require_exe=False).tups
    ] == [9]


def test_a_knot_engine_cuts_at_every_port_once_one_is_off_its_grid():
    """0.3 is a knot of ten and 0.35 is not, so NEC-5 cuts at both. The last
    piece is 6.5 segments long and rounds up to 7."""
    eng = NEC5Engine(_b(feed_at=0.3, load_ats=(0.35,)), require_exe=False)
    assert [(as_wire(t).n_seg, as_wire(t).name) for t in eng.tups] == [
        (3, "w@feed"),
        (1, "w@load0"),
        (7, None),
    ]
    assert eng._split_ports == {"feed": "w@feed", "load0": "w@load0"}


HALF_OF_TWO_SEGMENTS = """\
GW 1 20 -9.4 0 13.7 -0.1 0 20 0.001
GW 2 2 -0.1 0 20 0.1 0 20 0.001
GW 3 20 0.1 0 20 9.4 0 13.7 0.001
GE
EX 0 2 50% 0 1 0
FR 0 1 0 0 3.68 0
EN
"""


def _deck_builder(text):
    from antennaknobs.nec_import import parse_nec

    deck = parse_nec(text, name="two_segment_half.nec", network=True)

    class _Deck(AntennaBuilder):
        default_params = MappingProxyType({"freq": 3.68, "design_freq": 3.68})

        def build_wires(self):
            return list(deck.wire_tuples())

        def build_network(self):
            return deck.network()

    return _Deck(dict(_Deck.default_params))


@pytest.mark.parametrize("engine", ["pynec", "nec2"])
def test_fifty_percent_of_two_segments_feeds_the_middle_of_three_segments_on_a_centre_engine(
    engine, monkeypatch
):
    """`EX 0 2 50% 0 1 0` on a two-segment wire. The importer writes the exact
    middle as a plain port at the wire's middle, so the parity rule serves it:
    three segments, the source on the middle one. That is the mesh the pegged
    split makes of a port at 0.5 (three one-segment pieces, below)."""
    pytest.importorskip("PyNEC")
    if engine == "pynec":
        from antennaknobs.engines.pynec import PyNECEngine

        eng = PyNECEngine(_deck_builder(HALF_OF_TWO_SEGMENTS), ground=None)
    else:
        from antennaknobs.engines import nec2

        monkeypatch.setattr(nec2, "find_nec2", lambda explicit=None: "/bin/true")
        eng = nec2.NEC2Engine(_deck_builder(HALF_OF_TWO_SEGMENTS))
    assert [as_wire(t).n_seg for t in eng.tups] == [20, 3, 20]
    (rec,) = eng.fed_segments()
    assert (rec["wire"], rec["segments"], rec["site"]) == (1, 3, "centre")
    assert eng._split_wires == {}


def test_fifty_percent_of_two_segments_feeds_the_existing_knot_on_nec5():
    eng = NEC5Engine(_deck_builder(HALF_OF_TWO_SEGMENTS), require_exe=False)
    assert [as_wire(t).n_seg for t in eng.tups] == [20, 2, 20]
    ((idx, _type, _v, knot),) = eng._sources
    assert (idx, eng._source_address(idx, knot)) == (1, (1, 2))
    assert eng._split_wires == {}


def test_a_port_positioned_at_half_of_two_segments():
    """Positioned at 0.5 instead of written as the middle: 0.5 is no segment
    centre of two segments, so PyNEC makes three one-segment pieces and feeds
    the middle one; NEC-5 feeds the knot 0.5 already is, with no cut."""
    pynec = _pynec(_b(n_seg=2, feed_at=0.5))
    ws = [as_wire(t) for t in pynec.tups]
    assert [(w.n_seg, w.name) for w in ws] == [(1, None), (1, "w@feed"), (1, None)]
    lengths = [float(np.linalg.norm(np.subtract(w.p1, w.p0))) for w in ws]
    assert lengths == pytest.approx([LENGTH / 3] * 3, rel=1e-12)
    nec5 = NEC5Engine(_b(n_seg=2, feed_at=0.5), require_exe=False)
    assert [t[2] for t in nec5.tups] == [2] and nec5._split_wires == {}


def test_momwire_splits_a_multi_port_wire_as_its_reference_engines_do():
    """AK#1519: bs2 meshes the pieces PyNEC does, razor-2p the pieces NEC-5
    does."""
    from momwire import RazorSolver

    from antennaknobs.engines.momwire import MomwireEngine

    bs2 = MomwireEngine(_b(**CASES["k3"]))
    pynec = _pynec(_b(**CASES["k3"]))
    assert bs2._edge_segments == [[as_wire(t).n_seg for t in pynec.tups]]
    razor = MomwireEngine(
        _b(**CASES["k3"]), solver=RazorSolver, solver_kwargs={"nec5_quadrature": True}
    )
    nec5 = NEC5Engine(_b(**CASES["k3"]), require_exe=False)
    assert razor._edge_segments == [[as_wire(t).n_seg] for t in nec5.tups]


def test_one_note_per_split_wire_names_every_port():
    k3 = (
        "Wire 'w' carries ports 'load0' at 0.04, 'feed' at 0.31 and 'load1' at "
        "0.77 of its length, which are not all "
    )
    (centre,) = _pynec(_b(**CASES["k3"])).advisories
    assert centre == {
        "category": "FeedPlacement",
        "text": k3 + "segment centres of its 10 segments, so the wire is split and "
        "every port is fed exactly, at the middle of a short piece of its own "
        "(AK#1511).",
    }
    (knot,) = NEC5Engine(_b(**CASES["k3"]), require_exe=False).advisories
    assert knot["text"] == (
        k3 + "knots of its 10 segments, so the wire is split at each port and every "
        "port is fed exactly, at the knot the pieces on either side share (AK#1511)."
    )


# ---------------------------------------------------------------------------
# every reader of a port sees its piece
# ---------------------------------------------------------------------------


def test_pynec_reducer_drives_each_port_at_the_middle_of_its_piece():
    b = _b(_LineFed, **CASES["k3"])
    eng = _pynec(b)
    assert eng._use_reducer
    targets = _targets(b)
    by_name = {as_wire(t).name: as_wire(t) for t in eng.tups}
    for port, point in targets.items():
        w = by_name[eng._port_wire_of[port]]
        ((seg, weight),) = eng._port_drive_points[port]
        assert weight == 1.0 and seg == (w.n_seg + 1) // 2
        centre = np.asarray(w.p0) + (seg - 0.5) / w.n_seg * np.subtract(w.p1, w.p0)
        assert np.linalg.norm(centre - point) <= 1e-9 * LENGTH


def test_nec5_reads_each_ports_current_across_its_own_cut():
    """The reducer attaches each port at the p1 knot of its piece and
    interpolates across that cut, at the second and third cuts as at the
    first."""
    eng = NEC5Engine(_b(_LineFed, **CASES["k3"]), require_exe=False)
    assert eng._use_reducer
    assert eng._port_attach == {
        "load0": (0, "p1"),
        "feed": (1, "p1"),
        "load1": (2, "p1"),
    }
    counts = [as_wire(t).n_seg for t in eng.tups]
    assert counts == [1, 3, 5, 2]
    per_tag = {i + 1: [float(i + 1)] * c for i, c in enumerate(counts)}
    lengths = [0.04, 0.27, 0.46, 0.23]
    for idx in range(3):
        h_a = lengths[idx] * LENGTH / counts[idx]
        h_b = lengths[idx + 1] * LENGTH / counts[idx + 1]
        want = ((idx + 1) * h_b + (idx + 2) * h_a) / (h_a + h_b)
        got = eng._port_knot_current(per_tag, idx, "p1")
        assert got == pytest.approx(want, rel=1e-12)


def _cut_points(eng):
    return [np.asarray(as_wire(t).p1) for t in eng.tups[:-1]]


def test_pynec_joins_every_piece_back_into_the_wire_and_the_marker_is_exact():
    import antennaknobs.web.examples  # noqa: F401  registration order
    from antennaknobs.web import adapter

    b = _b(**CASES["k3"])
    eng = _pynec(b)
    eng.impedance()
    (wc,) = eng.current_distribution()
    counts = [as_wire(t).n_seg for t in eng.tups]
    assert wc.knot_positions.shape == (sum(counts) + 1, 3)
    np.testing.assert_allclose(wc.knot_positions[[0, -1]], [P0, P1], atol=1e-12)
    knots = np.cumsum(counts)[:-1]
    np.testing.assert_allclose(wc.knot_positions[knots], _cut_points(eng), atol=1e-12)
    assert np.all(np.isfinite(wc.knot_currents)) and abs(wc.knot_currents[-1]) == 0
    pos = adapter._pynec_feed_position(b, [wc])
    assert np.linalg.norm(np.asarray(pos) - _targets(b)["feed"]) <= 1e-9 * LENGTH


def test_nec5_joins_every_piece_with_the_mean_at_each_cut():
    eng = NEC5Engine(_b(**CASES["k3"]), require_exe=False)
    counts = [as_wire(t).n_seg for t in eng.tups]
    (wc,) = eng._currents_from(
        {i + 1: [float(i + 1)] * c for i, c in enumerate(counts)}
    )
    assert wc.knot_positions.shape == (sum(counts) + 1, 3)
    knots = np.cumsum(counts)[:-1]
    np.testing.assert_allclose(
        wc.knot_positions[knots], [P0 + a * (P1 - P0) for a in (0.04, 0.31, 0.77)]
    )
    assert list(wc.knot_currents[knots]) == [1.5, 2.5, 3.5]


def test_nec2_joins_every_piece_back_into_the_wire(monkeypatch):
    pytest.importorskip("PyNEC")
    from antennaknobs.engines import nec2

    monkeypatch.setattr(nec2, "find_nec2", lambda explicit=None: "/bin/true")
    eng = nec2.NEC2Engine(_b(**CASES["k3"]))
    counts = [as_wire(t).n_seg for t in eng.tups]
    (wc,) = eng._currents_from(
        {i + 1: [float(i + 1)] * c for i, c in enumerate(counts)}
    )
    knots = np.cumsum(counts)[:-1]
    assert wc.knot_positions.shape == (sum(counts) + 1, 3)
    assert list(wc.knot_currents[knots]) == [1.5, 2.5, 3.5, 4.5, 5.5]


def test_simnec_station_cards_feed_and_load_each_ports_own_piece():
    from antennaknobs.simnec_export import _station_cards

    b = _b(**CASES["k3"])
    eng = _pynec(b)
    net = eng._network
    cards = _station_cards(eng, "feed", list(net.branches), FREQ)
    deck = "\n".join(cards)
    _assert_sites(_nec2_deck_sites(deck), _targets(b), 1e-6 * LENGTH)


# ---------------------------------------------------------------------------
# the fed piece's count
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("segments", "count"),
    [
        (0, 1),
        (0.4, 1),
        (1, 1),
        (1.99, 1),
        (2, 3),
        (2.01, 3),
        (3, 3),
        (3.99, 3),
        (4, 5),
        (5.2, 5),
        (6, 7),
        (8, 9),
    ],
)
def test_the_nearest_odd_count_takes_the_larger_at_a_tie(segments, count):
    assert _nearest_odd_count(segments) == count


@pytest.mark.parametrize(
    ("segments", "count"),
    [
        (0, 1),
        (0.4, 1),
        (0.5, 1),
        (1.5, 2),
        (2.49, 2),
        (2.5, 3),
        (34.5, 35),
        (46.5, 47),
        (46.49, 46),
        # floating point: 34.49999999999999, and its mirror image's 34.5
        ((1 - 0.77) * 150, 35),
        (0.23 * 150, 35),
    ],
)
def test_the_nearest_count_rounds_a_half_up(segments, count):
    assert _nearest_count(segments) == count


# ---------------------------------------------------------------------------
# (d) physics: the split against the same engine's whole wire
# ---------------------------------------------------------------------------
#
# Each engine's split is compared with THAT engine's whole wire at a count
# where every port sits on its grid, so a formulation difference between
# engines cancels. The bars, registered before the first run of these tests:
#
# - PyNEC, two ports (feed 0.31, 50 ohm load 0.77). The whole wire has both on
#   segment centres at the odd multiples of 50. Reference: Z_w(150). Splits:
#   authored 61 and 101. Bar: the whole-wire step bracketing both splits'
#   totals (61 and 100 segments), |Z_w(150) - Z_w(50)|.
# - PyNEC, three ports (a second 50 ohm load at 0.04). No count fits: 0.04 is
#   1/25, and an odd denominator is never a segment centre. Reference: the
#   finest count in reach that fits the other two, 450, with the 0.04 load on
#   its nearest centre half a segment (11.7 mm) away. Split: authored 101. Bar:
#   the same whole-wire ladder's step bracketing the split's 100 segments,
#   |Z_w(150) - Z_w(50)|, the 0.04 load half a segment off at each.
# - NEC-5, two and three ports. Every multiple of 100 puts a knot at all of
#   them. Split: authored 150, whose pieces are off that grid. Reference:
#   Z_w(200). Bar: the bracketing step, |Z_w(200) - Z_w(100)|. (Registered
#   after a first NEC-5 gate, split from 100 against the whole wire at 100,
#   proved degenerate: that split was the whole wire's own mesh.)
#
# Split-always (2026-09-15): no split here is forced any more. Each is the one
# the rule makes, and the whole-wire references are the rule's own whole
# wires, except PyNEC's three-port ladder, which switches the split off to
# place 0.04 on its nearest centre. A wire whose ports are all knots of its
# count now stays whole, so the degenerate NEC-5 gate is gone.
#
# Reported, not gated: each split against momwire fed at the exact arclength,
# measured before split-always. PyNEC at 101 segments, D = 0.0404 ohm on the
# centre-fed dipole: one port at a third 0.0497 ohm (1.23 D); two ports 0.1693
# ohm (4.19 D), where PyNEC's own whole wire at 150 is 0.1087 ohm (2.69 D);
# three ports 0.0841 ohm (2.08 D). PyNEC at 61, D = 0.0865 ohm: two ports
# 0.2297 ohm (2.66 D). NEC-5 at 45, D5 = 3.219 ohm: two ports 4.965 ohm
# (1.54 D5).

PHYSICS = {
    "k2": dict(feed_at=0.31, load_ats=(0.77,)),
    "k3": dict(feed_at=0.31, load_ats=(0.04, 0.77)),
}


def _pynec_class():
    pytest.importorskip("PyNEC")
    from antennaknobs.engines.pynec import PyNECEngine

    return PyNECEngine


def _pynec_engine(builder):
    return _pynec_class()(builder, ground=None)


def _nec5_engine(builder):
    return NEC5Engine(builder, ground=None)


def _whole_z(make, n, params, *, snap_class=None):
    """Z of the whole wire at exactly `n` segments. Every port must already sit
    on a site at `n`, unless `snap_class` is given: that engine class is then
    told not to split, and a port off its grid goes to its nearest site."""
    with pytest.MonkeyPatch.context() as mp:
        if snap_class is not None:
            mp.setattr(snap_class, "splits_wire_at_feed", False)
        eng = make(_b(n_seg=n, **params))
    assert [as_wire(t).n_seg for t in eng.tups] == [n]
    return _z(eng)


def _split_z(make, n, params):
    """Z of the wire the rule splits from `n` authored segments."""
    eng = make(_b(n_seg=n, **params))
    assert "w" in eng._split_wires
    return _z(eng)


@pytest.fixture(scope="module")
def pynec_whole():
    """PyNEC's whole-wire Z for both cases, by count."""
    k2 = {n: _whole_z(_pynec_engine, n, PHYSICS["k2"]) for n in (50, 150)}
    k3 = {
        n: _whole_z(_pynec_engine, n, PHYSICS["k3"], snap_class=_pynec_class())
        for n in (50, 150, 450)
    }
    return {"k2": k2, "k3": k3}


@pytest.mark.parametrize("n", [61, 101])
def test_pynec_two_port_split_agrees_with_its_own_whole_wire(pynec_whole, n):
    """|Z_split - Z_w(150)| <= |Z_w(150) - Z_w(50)|, as registered above."""
    whole = pynec_whole["k2"]
    split = _split_z(_pynec_engine, n, PHYSICS["k2"])
    assert abs(split - whole[150]) <= abs(whole[150] - whole[50])


def test_pynec_three_port_split_agrees_with_its_finest_whole_wire(pynec_whole):
    """|Z_split(101) - Z_w(450)| <= |Z_w(150) - Z_w(50)|, as registered above."""
    whole = pynec_whole["k3"]
    split = _split_z(_pynec_engine, 101, PHYSICS["k3"])
    assert abs(split - whole[450]) <= abs(whole[150] - whole[50])


@needs_nec5
@pytest.mark.parametrize("case", PHYSICS)
def test_nec5_split_off_the_whole_grid_agrees_with_its_whole_wire(case):
    """|Z_split(150) - Z_w(200)| <= |Z_w(200) - Z_w(100)|, as registered above."""
    w100 = _whole_z(_nec5_engine, 100, PHYSICS[case])
    w200 = _whole_z(_nec5_engine, 200, PHYSICS[case])
    split = _split_z(_nec5_engine, 150, PHYSICS[case])
    assert abs(split - w200) <= abs(w200 - w100)

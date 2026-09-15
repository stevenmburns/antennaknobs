"""`SimulationEngine.fed_segments()` (AK#1456): the segment each feed sits on,
as each engine meshes it. Nothing here solves.

The parity coercion is why this exists. momwire's default basis, PyNEC and
NEC-2 put a delta gap in the middle of an odd count; NEC-5 puts its source on
the centre knot of an even count. So one authored feed wire reaches the engines
as different fed segments, and at a near-open driving point that difference
moves the impedance. Rows comparing engines record both, from this method.
"""

import importlib
import json
import math
import sys
from pathlib import Path
from types import MappingProxyType

import pytest

from antennaknobs import AntennaBuilder
from antennaknobs.engines.momwire import MomwireEngine
from antennaknobs.engines.nec5 import NEC5Engine
from antennaknobs.network import Driven, Load, Network, PortOnWire, Wire, as_wire

SOIL = ("finite", 13.0, 0.005)


def _builder(name):
    return importlib.import_module(f"antennaknobs.designs.{name}").Builder()


def _summary(records):
    return [
        (r["port"], r["segments"], round(1000 * r["length_m"], 2), r["site"])
        for r in records
    ]


@pytest.mark.parametrize(
    "name",
    [
        "verticals.elevated_buried_counterpoise",
        "verticals.buried_radial_vertical",
        "specialty.buried_dipole",
    ],
)
def test_the_house_gap_is_one_segment_on_momwire_and_two_on_nec5(name):
    """The 50 mm gap wire: one 50 mm segment with the gap in its middle on
    momwire, two 25 mm segments either side of the source knot on NEC-5."""
    b = _builder(name)
    assert _summary(MomwireEngine(b, ground=SOIL).fed_segments()) == [
        (None, 1, 50.0, "centre")
    ]
    assert _summary(NEC5Engine(b, ground=SOIL, require_exe=False).fed_segments()) == [
        (None, 2, 25.0, "knot")
    ]


def test_every_legacy_feed_is_reported_in_wire_order():
    b = _builder("verticals.four_square")
    mw = MomwireEngine(b).fed_segments()
    n5 = NEC5Engine(b, require_exe=False).fed_segments()
    assert [r[1:] for r in _summary(mw)] == [(1, 100.0, "centre")] * 4
    assert [r[1:] for r in _summary(n5)] == [(2, 50.0, "knot")] * 4
    assert [r["wire"] for r in n5] == [1, 4, 7, 10]


def test_network_ports_are_reported_by_name_on_every_engine():
    b = _builder("beams.hb9cv")
    assert _summary(MomwireEngine(b).fed_segments()) == [
        ("rear", 1, 100.0, "centre"),
        ("front", 1, 100.0, "centre"),
    ]
    assert _summary(NEC5Engine(b, require_exe=False).fed_segments()) == [
        ("rear", 2, 50.0, "knot"),
        ("front", 2, 50.0, "knot"),
    ]
    pynec = pytest.importorskip("antennaknobs.engines.pynec")
    assert _summary(pynec.PyNECEngine(b).fed_segments()) == [
        ("rear", 1, 100.0, "centre"),
        ("front", 1, 100.0, "centre"),
    ]


def test_a_vertex_port_reports_its_wires_end_segment_at_each_engines_count():
    """NEC-5 exempts a vertex-only wire from the parity bump (#898) and keeps
    the authored 20 segments; momwire bumps the named wire to 21. The same
    wire, so the two segment lengths are the one wire length divided two ways."""
    b = _builder("dipoles.invvee_apex")
    (mw,) = MomwireEngine(b).fed_segments()
    (n5,) = NEC5Engine(b, require_exe=False).fed_segments()
    assert (mw["port"], mw["segments"], mw["site"]) == ("apex", 21, "end")
    assert (n5["port"], n5["segments"], n5["site"]) == ("apex", 20, "end")
    assert mw["length_m"] * 21 == pytest.approx(n5["length_m"] * 20)


def test_the_validation_pages_sites_are_the_engines_own_parities():
    """`scripts/build_validation_report.py` labels the ByDipole1 ladders'
    fed segments 'centre' for momwire bs2 and 'knot' for momwire bs1 and NEC-5.
    Those labels are these parities; nec2c's EX at the middle segment of an odd
    count is the NEC-2 spelling the PyNEC engine shares."""
    from momwire import BSplineSolver

    b = _builder("verticals.four_square")
    assert MomwireEngine(b).segment_parity == "odd"
    bs1 = MomwireEngine(b, solver=BSplineSolver, solver_kwargs={"degree": 1})
    assert bs1.segment_parity == "even"
    assert NEC5Engine(b, require_exe=False).segment_parity == "even"


ROOT = Path(__file__).resolve().parent.parent


def _validation_generator():
    sys.path.insert(0, str(ROOT / "scripts"))
    return importlib.import_module("build_validation_report")


@pytest.mark.parametrize(
    "name", ["verticals.buried_radial_vertical", "specialty.buried_dipole"]
)
def test_the_validation_pages_buried_fed_segments_are_the_engines(name):
    """The page states both engines' fed segments beside its below-ground
    cross-engine numbers as a literal (it renders without constructing an
    engine); this holds that literal to what the engines mesh."""
    page = _validation_generator()
    b = _builder(name)
    (mw,) = MomwireEngine(b, ground=SOIL).fed_segments()
    (n5,) = NEC5Engine(b, ground=SOIL, require_exe=False).fed_segments()
    assert page.BURIED_FED == (
        f"momwire {mw['segments']} × {1000 * mw['length_m']:.0f} mm, "
        f"NEC-5 {n5['segments']} × {1000 * n5['length_m']:.0f} mm"
    )


def test_the_validation_pages_leeson_fed_segment_is_the_benchs_mesh():
    page = _validation_generator()
    bench = importlib.import_module("bench_leeson")
    for case in json.loads(page.LEESON.read_text())["cases"]:
        mult = int(case["bs2"][-1][0])
        x1, x2, _dia, n = bench.build_wires(case["half_inches"], mult)[0]
        assert x1 == -x2
        assert page.leeson_bs2_fed_mm(case, mult) == pytest.approx(
            1000 * 2 * x2 * bench.IN / n
        ), case["name"]


# ---------------------------------------------------------------------------
# A wire split at its ports (AK#1510, AK#1511): the fed segment is the one
# meshed there
# ---------------------------------------------------------------------------

SPLIT_FREQ = 28.47
SPLIT_ARM = 0.25 * 299.792458 / SPLIT_FREQ


class _PositionedDipole(AntennaBuilder):
    """One 10-segment wire with its feed at `feed_at`: 0.31 is no knot of any
    count from 10 to 20 and 1/3 no segment centre of any, so the splitting
    engines cut it (`tests/test_split_at_feed_1510.py`)."""

    default_params = MappingProxyType(
        {"freq": SPLIT_FREQ, "design_freq": SPLIT_FREQ, "feed_at": 0.31}
    )

    def build_wires(self):
        return [
            Wire((0.0, -SPLIT_ARM, 10.0), (0.0, SPLIT_ARM, 10.0), n_seg=10, name="w")
        ]

    def build_network(self):
        return Network(
            ports={"feed": PortOnWire("feed", wire="w", at=self.feed_at)},
            sources=[Driven(port="feed")],
        )


def _positioned(at):
    if not hasattr(PortOnWire("x"), "at"):
        pytest.skip("the installed momwire's PortOnWire has no wire/at (momwire#1059)")
    return _PositionedDipole(dict(_PositionedDipole.default_params, feed_at=at))


def _segment(t):
    w = as_wire(t)
    return math.dist(w.p0, w.p1) / int(w.n_seg)


def test_nec5_reports_the_knot_its_split_shares_not_the_authored_wire():
    """NEC-5 breaks the wire at the port and feeds the knot the two pieces
    share, as a series source at the first piece's end: the fed segments are
    that piece's last and the next piece's first, not a tenth of the wire."""
    eng = NEC5Engine(_positioned(0.31), require_exe=False)
    assert set(eng._split_ports) == {"feed"}
    before, after = eng.tups[0], eng.tups[1]
    (rec,) = eng.fed_segments()
    assert (rec["port"], rec["wire"], rec["site"]) == ("feed", 0, "knot")
    assert rec["segments"] == as_wire(before).n_seg
    assert rec["length_m"] == pytest.approx(_segment(before))
    assert rec["length_after_m"] == pytest.approx(_segment(after))
    assert rec["length_m"] != pytest.approx(2 * SPLIT_ARM / 10)


def _centre_engine(engine, builder, monkeypatch):
    pytest.importorskip("PyNEC")
    if engine == "pynec":
        from antennaknobs.engines.pynec import PyNECEngine

        return PyNECEngine(builder, ground=None)
    from antennaknobs.engines import nec2

    monkeypatch.setattr(nec2, "find_nec2", lambda explicit=None: "/bin/true")
    return nec2.NEC2Engine(builder)


@pytest.mark.parametrize("engine", ["pynec", "nec2"])
def test_a_centre_engine_reports_the_carrying_piece_of_its_split(engine, monkeypatch):
    """PyNEC and NEC-2 give the port a short piece of its own, named
    ``w@feed``, with the port at its middle: the fed segment is that piece's
    middle one."""
    eng = _centre_engine(engine, _positioned(1 / 3), monkeypatch)
    assert set(eng._split_ports) == {"feed"}
    (index,) = [i for i, t in enumerate(eng.tups) if as_wire(t).name == "w@feed"]
    carrying = eng.tups[index]
    (rec,) = eng.fed_segments()
    assert (rec["port"], rec["wire"], rec["site"]) == ("feed", index, "centre")
    assert rec["segments"] == as_wire(carrying).n_seg
    assert rec["segments"] % 2 == 1
    assert rec["length_m"] == pytest.approx(_segment(carrying))


def test_momwire_never_splits_and_reports_the_edge_its_feed_sits_on():
    eng = MomwireEngine(_positioned(1 / 3))
    assert not getattr(eng, "_split_wires", None)
    (rec,) = eng.fed_segments()
    assert (rec["port"], rec["site"]) == ("feed", "centre")
    assert rec["length_m"] * rec["segments"] == pytest.approx(2 * SPLIT_ARM)


class _TwoPortDipole(_PositionedDipole):
    """The same wire with a 50 ohm load at 0.77 as well. No count from 10 to 20
    puts a knot, or a segment centre, at both 0.31 and 0.77, so every splitting
    engine cuts the wire for both ports (AK#1511)."""

    def build_network(self):
        return Network(
            ports={
                "feed": PortOnWire("feed", wire="w", at=0.31),
                "load": PortOnWire("load", wire="w", at=0.77),
            },
            branches=[Load(port="load", r=50.0)],
            sources=[Driven(port="feed")],
        )


def _two_port():
    _positioned(0.31)  # the same momwire#1059 skip
    return _TwoPortDipole()


def test_nec5_reports_each_port_at_the_knot_of_its_own_cut():
    """The wire breaks at 0.31 and 0.77 into pieces of 3, 5 and 2 segments. Each
    port's record is its own cut: the last segment of the piece named for it
    and the first of the next, which differ in length here."""
    eng = NEC5Engine(_two_port(), require_exe=False)
    assert eng._split_ports == {"feed": "w@feed", "load": "w@load"}
    records = {r["port"]: r for r in eng.fed_segments()}
    assert set(records) == {"feed", "load"}
    for port, index in (("feed", 0), ("load", 1)):
        piece, nxt = eng.tups[index], eng.tups[index + 1]
        rec = records[port]
        assert as_wire(piece).name == f"w@{port}"
        assert (rec["wire"], rec["site"]) == (index, "knot")
        assert rec["segments"] == as_wire(piece).n_seg
        assert rec["length_m"] == pytest.approx(_segment(piece))
        assert rec["length_after_m"] == pytest.approx(_segment(nxt))
        assert rec["length_after_m"] != pytest.approx(rec["length_m"])


@pytest.mark.parametrize("engine", ["pynec", "nec2"])
def test_a_centre_engine_reports_each_ports_own_piece(engine, monkeypatch):
    eng = _centre_engine(engine, _two_port(), monkeypatch)
    assert eng._split_ports == {"feed": "w@feed", "load": "w@load"}
    records = {r["port"]: r for r in eng.fed_segments()}
    assert set(records) == {"feed", "load"}
    for port in ("feed", "load"):
        (index,) = [i for i, t in enumerate(eng.tups) if as_wire(t).name == f"w@{port}"]
        piece = eng.tups[index]
        rec = records[port]
        assert (rec["wire"], rec["site"]) == (index, "centre")
        assert rec["segments"] == as_wire(piece).n_seg and rec["segments"] % 2 == 1
        assert rec["length_m"] == pytest.approx(_segment(piece))

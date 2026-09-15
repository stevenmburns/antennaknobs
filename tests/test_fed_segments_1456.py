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
import sys
from pathlib import Path

import pytest

from antennaknobs.engines.momwire import MomwireEngine
from antennaknobs.engines.nec5 import NEC5Engine

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

"""AK#1469 slice 1: a NEC-5 knot source at a wire's middle keeps the wire whole.

AC6LA loaded `dipoles.invvee.default.somm13.nec` from the NEC-5 catalog corpus
(QRZ, 2026-09-13): `GW 3 2 … EX 0 3 1 2`, a source at the joint in the middle
of a 2-segment centre wire. The importer cut that wire into two 1-segment
pieces, so the deck handed to NEC-5 read `GW 3 1` / `GW 4 1`. The feed marker
then sat at the middle of a piece, 2.5 cm off the source on the NEC-5 lane,
and the momwire lane drew no marker at all.

A middle knot source is antennaknobs' standard middle-of-wire feed, so the
wire now stays whole and carries a PortOnWire. Every other knot source keeps
the #824 cut; this file pins both, and where each marker lands.
"""

from __future__ import annotations

import importlib
from types import SimpleNamespace

import numpy as np
import pytest

from antennaknobs.engines.momwire import MomwireEngine
from antennaknobs.engines.nec5 import NEC5Engine
from antennaknobs.file_designs import builder_from_file
from antennaknobs.network import PortAtVertex, PortOnWire
from antennaknobs.nec_import import parse_nec

# dist/nec5_corpus/catalog-nec5/dipoles.invvee.default.somm13.nec, verbatim.
AC6LA = """CM antennaknobs catalog design dipoles.invvee (default mesh, somm13 ground)
CE
GW 1 20 0.000000E+00 5.000000E-02 7.000000E+00 0.000000E+00 2.184661E+00 5.682399E+00 5.000000E-04
GW 2 20 0.000000E+00 -2.184661E+00 5.682399E+00 0.000000E+00 -5.000000E-02 7.000000E+00 5.000000E-04
GW 3 2 0.000000E+00 -5.000000E-02 7.000000E+00 0.000000E+00 5.000000E-02 7.000000E+00 5.000000E-04
GE 1 0
GN 0 0 0 0 1.300000E+01 5.000000E-03 1.000000E+00 0.000000E+00 NOFILE
EX 0 3 1 2 1.000000E+00 0.000000E+00
FR 0 1 0 0 2.847000E+01 0.000000E+00
XQ 0
EN
"""

# A source at knot 5 of an 11-segment vertical: off-centre, so it keeps the cut.
OFF_CENTRE = (
    "CE\nGW 1 11 0 0 0 0 0 11 .001\nGE 0\nEX 0 1 -6 0 1 0\nFR 0 1 0 0 14 0\nEN\n"
)


def _markers():
    """The adapter's two marker helpers, imported the way the server does:
    `antennaknobs.web.server` first, since importing the adapter on its own
    trips its example registry's circular import."""
    importlib.import_module("antennaknobs.web.server")
    from antennaknobs.web.adapter import _feed_position, _pynec_feed_position

    return _feed_position, _pynec_feed_position


def _builder(tmp_path, text, name):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    b = builder_from_file(str(p))
    return b() if isinstance(b, type) else b


def _currents_from_tuples(builder):
    """Engine-lane stand-in: one knot row per build_wires() tuple."""
    out = []
    for t in builder.build_wires():
        p0, p1, n = np.asarray(t[0], float), np.asarray(t[1], float), int(t[2])
        out.append(SimpleNamespace(knot_positions=np.linspace(p0, p1, n + 1)))
    return out


def _currents_from_polylines(eng):
    """momwire-lane stand-in: one knot row per polyline, at its vertices."""
    return [
        SimpleNamespace(knot_positions=np.asarray(pl, float)) for pl in eng._polylines
    ]


def test_the_middle_knot_wire_stays_whole_with_a_middle_port():
    deck = parse_nec(AC6LA, network=True)
    tups = deck.wire_tuples()
    assert [(t[2], t[4] if len(t) > 4 else None) for t in tups] == [
        (20, None),
        (20, None),
        (2, "feed"),
    ]
    net = deck.network()
    assert list(net.ports) == ["feed"]
    assert isinstance(net.ports["feed"], PortOnWire)
    assert net.sources[0].port == "feed"


def test_nec5_gets_the_authored_wire_back(tmp_path):
    b = _builder(tmp_path, AC6LA, "invvee.nec")
    deck = NEC5Engine(b, ground=b.file_ground, require_exe=False).deck([b.freq])
    rows = [ln.split() for ln in deck.splitlines()]
    gw = [r for r in rows if r[:1] == ["GW"]]
    ex = [r for r in rows if r[:1] == ["EX"]]
    assert [(r[1], r[2]) for r in gw] == [("1", "20"), ("2", "20"), ("3", "2")]
    assert [r[1:5] for r in ex] == [["0", "3", "1", "2"]]


def test_an_off_centre_knot_keeps_the_cut():
    deck = parse_nec(OFF_CENTRE, network=True)
    assert [t[2] for t in deck.wire_tuples()] == [5, 6]
    assert isinstance(deck.network().ports["feed"], PortAtVertex)


def test_a_middle_knot_with_a_second_claim_keeps_the_cut():
    """A load elsewhere on the fed wire is a second claim, so the #824 cut
    stays: the wire is refined to 4 segments with its source at knot 2 and a
    load on segment 4. (On the verbatim 2-segment wire any load collides with
    the knot's own piece, which the importer already refuses by name.)"""
    text = (
        AC6LA.replace("GW 3 2 ", "GW 3 4 ")
        .replace("EX 0 3 1 2 ", "EX 0 3 2 2 ")
        .replace("XQ 0\n", "LD 0 3 4 4 50 0 0\nXQ 0\n")
    )
    deck = parse_nec(text, network=True)
    assert len(deck.wire_tuples()) > 3
    assert isinstance(deck.network().ports["feed"], PortAtVertex)


def test_refinement_keeps_the_middle_knot_in_the_middle():
    deck = parse_nec(AC6LA, network=True).refined(3)
    tups = deck.wire_tuples()
    assert [(t[2], t[4] if len(t) > 4 else None) for t in tups][-1] == (6, "feed")


def test_engine_lane_marker_sits_on_the_source(tmp_path):
    _feed_position, _pynec_feed_position = _markers()
    b = _builder(tmp_path, AC6LA, "invvee.nec")
    pos = _pynec_feed_position(b, _currents_from_tuples(b))
    assert pos == pytest.approx([0.0, 0.0, 7.0], abs=1e-9)


def test_momwire_lane_marker_sits_on_the_source(tmp_path):
    _feed_position, _pynec_feed_position = _markers()
    b = _builder(tmp_path, AC6LA, "invvee.nec")
    eng = MomwireEngine(b, ground=b.file_ground)
    pos = _feed_position(eng, _currents_from_polylines(eng))
    assert pos == pytest.approx([0.0, 0.0, 7.0], abs=1e-9)


def test_a_vertex_source_marker_sits_on_its_knot_on_both_lanes(tmp_path):
    _feed_position, _pynec_feed_position = _markers()
    b = _builder(tmp_path, OFF_CENTRE, "offcentre.nec")
    engine_lane = _pynec_feed_position(b, _currents_from_tuples(b))
    assert engine_lane == pytest.approx([0.0, 0.0, 5.0], abs=1e-9)
    eng = MomwireEngine(b, ground=None)
    momwire_lane = _feed_position(eng, _currents_from_polylines(eng))
    assert momwire_lane == pytest.approx([0.0, 0.0, 5.0], abs=1e-9)

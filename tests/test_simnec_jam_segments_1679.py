"""SimNEC's ``$GW_<tag>.JamSegments(N)``, honoured exactly (AK#1679 item 1).

Decided 2026-09-23: the file says N, so we solve N. The even-count rule does
not apply to a count the file sets, and when the feed then falls between the
sites of an engine's grid it is fed where it is by splitting the wire there
(AK#1511), never snapped. SimNEC's own re-mesh
(``NECOptions.segmentsPerWavelength``) is not emulated, and the import note
says so and names the same-mesh route, ``lastConstructedNEC.nec``.

The engine gates run the shared mesher (`SimulationEngine._coerce_wire_tuples`)
through a stub of each grid family, so they need no solver: ``_Knot`` is
NEC-5's (even parity, a source on a knot) and ``_Centre`` PyNEC's and NEC-2's
(odd parity, a gap at a segment centre).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from antennaknobs.engine import SimulationEngine
from antennaknobs.file_designs import builder_from_file
from antennaknobs.network import as_wire
from antennaknobs.simnec_import import parse_ssn

CLC = (
    Path(__file__).parent
    / "fixtures"
    / "simnec_ac6la_1679"
    / "Bydipole-TL-Xfmr-CLC.ssn"
)


class _Knot(SimulationEngine):
    segment_parity = "even"
    splits_wire_at_feed = True

    def impedance(self):
        raise NotImplementedError

    def impedance_sweep(self, freqs):
        raise NotImplementedError


class _Centre(_Knot):
    segment_parity = "odd"


def _script(jam: str) -> str:
    """A centre-fed 11-segment dipole, with ``jam`` after NECEND."""
    return f"""//dip20
P1 w1 gnd;
NECOptions.segmentsPerWavelength = 40;
NEC2
GW 1 11 0 -5 10 0 5 10 0.0005
EX 0 1 6 0 1 0
NECEND
{jam}"""


def _ssn(script: str) -> str:
    return f"""<?xml version="1.0" encoding="utf-8"?>
<SimNEC1p0>
    <SmithChartCircuit>
        <CIRCUIT>
            <element>
                <type>NETWORK</type>
                <escapeHatch/>
                <p><n>equ</n><v>{script}</v></p>
            </element>
            <element>
                <type>GENERATOR</type>
                <p><n>MHz</n><v>14.1</v></p>
                <p><n>Zo</n><v>50</v></p>
            </element>
        </CIRCUIT>
    </SmithChartCircuit>
</SimNEC1p0>
"""


def _builder(tmp_path, jam: str):
    path = tmp_path / "jam.ssn"
    path.write_text(_ssn(_script(jam)))
    return builder_from_file(str(path))


def _notes(tmp_path, jam: str) -> str:
    return _builder(tmp_path, jam).default_params["ui_params"]["notes"]


def _meshed(engine_cls, builder):
    """``([(n_seg, piece name)], advisory texts)`` as that engine meshes."""
    eng = engine_cls(builder)
    tups = eng._coerce_wire_tuples(builder.build_wires())
    pieces = [(as_wire(t).n_seg, as_wire(t).name) for t in tups]
    return pieces, [a["text"] for a in eng.advisories]


# --- the count is the file's -------------------------------------------------


@pytest.mark.parametrize("n", [20, 11, 12, 7])
def test_the_jammed_count_is_the_count(tmp_path, n):
    """GW 11 with JamSegments(N) imports as N segments on that wire, odd or
    even, and the design builds its wire with N."""
    c = parse_ssn(_ssn(_script(f"$GW_1.JamSegments({n});")), network=True)
    assert [w.n_seg for w in c.deck.wires] == [n]
    assert c.deck.pinned_wires == frozenset({0})
    b = _builder(tmp_path, f"$GW_1.JamSegments({n});")()
    assert [as_wire(t).n_seg for t in b.build_wires()] == [n]


def test_dans_jamsegments_20_solves_20(tmp_path):
    """AC6LA's CLC circuit: GW 1 has 11 segments and `$GW_1.JamSegments(20)`.
    The wire is 20 segments, and NEC-5's grid keeps it whole: the centre
    feed is its middle knot."""
    c = parse_ssn(CLC.read_text(), name=CLC.name, network=True)
    assert [w.n_seg for w in c.deck.wires] == [20]
    (f,) = c.deck.feeds
    assert f.at == 0.5
    b = builder_from_file(str(CLC))()
    assert _meshed(_Knot, b) == ([(20, "feed")], [])


def test_jamsegments_0_leaves_the_gw_count_to_the_parity_rule(tmp_path):
    """SimNEC's JamSegments(0) is "auto-segment as usual": the GW count
    stands, unpinned, and the engines treat it as any GW count."""
    c = parse_ssn(_ssn(_script("$GW_1.JamSegments(0);")), network=True)
    assert [w.n_seg for w in c.deck.wires] == [11]
    assert c.deck.pinned_wires == frozenset()
    assert _meshed(_Knot, _builder(tmp_path, "$GW_1.JamSegments(0);")()) == (
        [(12, "feed")],
        [],
    )


# --- no parity bump, and the feed-position rule where the feed is off-site ----


def test_no_engine_bumps_a_jammed_count(tmp_path):
    """The even-count rule is for counts the app chooses. A jammed count on
    a grid it already suits stays whole at exactly N: 11 on a centre engine
    (its feed at the middle segment's centre), 20 on a knot engine (its feed
    on the middle knot). Unjammed, NEC-5's grid would bump 11 to 12."""
    assert _meshed(_Centre, _builder(tmp_path, "$GW_1.JamSegments(11);")()) == (
        [(11, "feed")],
        [],
    )
    assert _meshed(_Knot, _builder(tmp_path, "$GW_1.JamSegments(20);")()) == (
        [(20, "feed")],
        [],
    )


@pytest.mark.parametrize(
    ("engine", "n", "pieces", "site"),
    [
        # 11 on NEC-5's grid: the centre is no knot of 11, so the wire is cut
        # at the feed and the source sits on the knot the halves share.
        (_Knot, 11, [(6, "feed@feed"), (6, None)], "knot"),
        # 20 on a centre engine: the centre is no segment centre of 20, so the
        # feed gets a short odd piece of its own, centred on it.
        (_Centre, 20, [(7, None), (7, "feed@feed"), (7, None)], "segment centre"),
    ],
)
def test_an_off_site_centre_feed_splits_the_wire_at_the_feed(
    tmp_path, engine, n, pieces, site
):
    """A jammed count whose centre is not a site of the engine's grid follows
    the feed-position rule (AK#1510/#1511): the feed keeps its exact place,
    the wire is split there, and the engine says so. It is never snapped to a
    neighbouring site, and the count is never bumped to reach one."""
    meshed, notes = _meshed(engine, _builder(tmp_path, f"$GW_1.JamSegments({n});")())
    assert meshed == pieces
    (note,) = notes
    assert f"which is not a {site} of its {n} segments" in note
    assert "'feed' at 0.5" in note


# --- the import note -----------------------------------------------------------


def test_jamsegments_is_applied_not_reported(tmp_path):
    """JamSegments is no longer in the not-applied note."""
    c = parse_ssn(_ssn(_script("$GW_1.JamSegments(20);")), network=True)
    assert c.ignored_directives == ()
    assert "JamSegments" not in (c.skipped_note() or "")
    notes = _notes(tmp_path, "$GW_1.JamSegments(20);")
    assert "not applied" not in notes


def test_the_note_says_simnec_re_meshes_and_names_the_same_mesh_route(tmp_path):
    """SimNEC re-meshes before it solves and antennaknobs does not emulate
    that, so the note says the numbers differ by mesh and names the deck
    SimNEC actually solved as the way to compare on one mesh."""
    notes = _notes(tmp_path, "$GW_1.JamSegments(20);")
    assert "SimNEC re-meshes the wires before it solves" in notes
    assert "segmentsPerWavelength = 40" in notes
    assert "differ from these by mesh" in notes
    assert "lastConstructedNEC.nec" in notes
    assert "~/.SimNEC/<version>/" in notes
    assert "the 1 JamSegments wire at exactly the jammed count" in notes


def test_a_jamsegments_naming_no_wire_stays_in_the_not_applied_note():
    c = parse_ssn(_ssn(_script("$GW_7.JamSegments(20);")), network=True)
    assert c.ignored_directives == ("$GW_7.JamSegments(20)",)
    assert [w.n_seg for w in c.deck.wires] == [11]


def test_a_count_that_moves_a_junction_is_refused_by_name():
    """A wire another wire joins mid-way must keep a knot at the joint: GW 1
    is joined at its knot 5 of 10, which JamSegments(20) keeps (knot 10) and
    JamSegments(11) cannot (knot 5.5)."""
    tee = """//tee
NEC2
GW 1 10 0 -5 10 0 5 10 0.0005
GW 2 5 0 0 10 0 0 15 0.0005
EX 0 2 3 0 1 0
NECEND
"""
    c = parse_ssn(_ssn(tee + "$GW_1.JamSegments(20);"), network=True)
    assert [w.n_seg for w in c.deck.wires] == [20, 5]
    with pytest.raises(ValueError, match="JamSegments: re-meshing changes which"):
        parse_ssn(_ssn(tee + "$GW_1.JamSegments(11);"), network=True)

"""EZNEC's NEC-5 decks are read as declared NEC-5 (AK#1579).

Every deck EZNEC writes carries the writer that wrote it:
`CM ! Written by EZNEC/Pro+ v. 7.0 in NEC-5 format.` That sentence is a
DECLARATION, so the AK#1476 rule applies to it: sources, probes, discrete
loads (AK#1483) and network ends sit at segment ENDS, not centres. Before
this, the whole EZNEC corpus imported with NEC-2 source semantics and every
source landed half a segment from where NEC-5 solves it.

Three facts this file pins, each measured against our licensed NEC-5:

- the STAMP is matched by phrase and its format word is read. EZNEC has
  NEC-2 and NEC-4.2 engine slots we have never captured, and the NEC-4.2
  slot's sources are not NEC-2's, so any other format word refuses by name
  rather than guessing;
- an `EX 0,tag,seg,0` lands at end 2 of `seg`. Mike WA7ARK's control deck
  through AK's NEC-5 engine returns the printout's 275.53 - 1441.0j to every
  printed digit — AK re-emits the source where NEC-5 read it;
- a TL/NT segment field names an end too: positive is end 2, negative end 1.
  Measured on the binary: on a 10-segment dipole a line attached at `2` and
  at `-3` solve bit-identically, `2` and `-2` do not, and NEC-5's own NETWORK
  DATA block echoes the sign back. So `TL 3,2,2,-1` and `EX 4,2,-1` address
  ONE node, which is one port here.

What a knot end CANNOT do is sit on a lone wire end: the node's only through
path is the ground contact, and a port in that path is expressible in neither
engine (momwire refuses a series `node_gaps` entry at a one-member junction
and a shunt `junction_ports` entry at a grounded node). Such an end keeps the
segment the card names and the deck says so — `net_ends_demoted`.
"""

from pathlib import Path

import pytest

from antennaknobs import AntennaBuilder
from antennaknobs.engines import MomwireEngine, NEC5Engine
from antennaknobs.file_designs import builder_from_file
from antennaknobs.nec_import import _eznec_declares_nec5, parse_nec
from antennaknobs.network import (
    Admittance,
    DrivenCurrent,
    PortAtVertex,
    PortOnWire,
    PortVirtual,
)

import momwire
from momwire import BSplineSolver

from conftest import needs_nec5

FIXTURES = Path(__file__).parent / "fixtures" / "eznec_virtual_wire_1577"
STAMP = "CM ! Written by EZNEC/Pro+ v. 7.0 in NEC-5 format."

# AC6LA's deck (QRZ, 2026-09-12) as AK#1476's file uses it: a 20-segment
# dipole driven at `EX 0 1 10 0`, which NEC-2 reads as the centre of segment
# 10 and NEC-5 as its end 2.
DAN = "SY len=.4836\nGW 1 20 0 -len/2 0 0 len/2 0 .0001\nEX 0 1 10 0 1 0\n"

# NEC5CL's own printout for the control deck (no virtual wire, no network:
# the same antenna and the same LD 0 capacitor, driven straight at the OCF
# point). `tests/fixtures/eznec_virtual_wire_1577/README.md` quotes the row.
NEC5_CONTROL_Z = complex(275.53, -1441.0)
NEC5_SOURCE_Z = complex(48.919, 103.89)  # failEZN5, at the virtual-node source


def _deck(text):
    return parse_nec(text, name="d.nec", network=True)


def _solve(name, engine=MomwireEngine, **kwargs):
    cls = builder_from_file(str(FIXTURES / name))
    return engine(cls(), ground=cls.file_ground, **kwargs).impedance()


def _builder(deck, freq):
    class B(AntennaBuilder):
        default_params = {"freq": freq}

        def build_wires(self):
            return deck.wire_tuples(specs=True)

        def build_network(self):
            return deck.network()

    return B()


# --------------------------------------------------------------------------
# the stamp is the declaration
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "stamp",
    [
        STAMP,
        "CM ! written by eznec/pro+ v. 7.0 in nec-5 format.",
        "CM  !  Written  by   EZNEC/Pro+  v. 7.0  in  NEC-5  format.",
        # Our own AC6LA fixture spells the product name with a space, and it
        # is the same writer; the format word is what the rule turns on.
        "CM ! Written by EZNEC Pro+ v. 7.0 in NEC-5 format.",
        "CM ! Written by EZNEC/Pro+ v. 7.0 in NEC5 format",
    ],
)
def test_the_eznec_stamp_declares_the_deck_nec5(stamp):
    deck = _deck(f"{stamp}\n{DAN}")
    assert deck.nec5_dialect is True
    (feed,) = deck.feeds
    assert (feed.seg, feed.edge) == (10, 2)  # end 2 of segment 10, not its centre
    assert getattr(deck.network().ports["feed"], "at", None) is None


def test_without_the_stamp_the_same_deck_is_still_nec2():
    """The control on every case above: AK#1476's reading is unchanged for a
    deck that does not say who wrote it."""
    deck = _deck(DAN)
    assert deck.nec5_dialect is False
    assert deck.network().ports["feed"].at == pytest.approx(19 / 40)


@pytest.mark.parametrize("word", ["NEC-2", "NEC2", "NEC-4.2", "NEC4.2"])
def test_eznecs_other_two_writers_keep_the_nec2_reading(word):
    """EZNEC's File > Save As writes NEC-2 and its External slot writes
    NEC-4.2, both stamped in the same frame with their own word. Those decks
    are ordinary NEC-2 decks this importer already reads, so the stamp is
    recognised and declares NOTHING — Save As is how most EZNEC users will
    bring a model here, and refusing it would be worse than the bug.

    The whole point, asserted: a positive-segment `EX 0,tag,seg,0` is the
    segment CENTRE under that reading, 19/40 of this 20-segment wire."""
    deck = _deck(f"CM ! Written by EZNEC/Pro+ v. 7.0 in {word} format.\n{DAN}")
    assert deck.nec5_dialect is False
    (feed,) = deck.feeds
    assert (feed.seg, feed.edge) == (10, 0)
    assert deck.network().ports["feed"].at == pytest.approx(19 / 40)


@pytest.mark.parametrize(
    ("word", "stamp"),
    [
        ("NEC-3", "CM ! Written by EZNEC/Pro+ v. 7.0 in NEC-3 format."),
        ("MININEC", "CM ! Written by EZNEC/Pro+ v. 7.0 in MININEC format."),
    ],
)
def test_an_uncaptured_eznec_writer_refuses_by_name(word, stamp):
    """Three writers are captured and every one of them has a rule. A fourth
    would spell its sources and loads its own way, and guessing which is what
    AK#1579 was, so it refuses instead."""
    with pytest.raises(ValueError, match=rf"EZNEC wrote this deck in {word} format"):
        _deck(f"{stamp}\n{DAN}")


def test_an_eznec_stamp_naming_no_format_refuses_too():
    with pytest.raises(ValueError, match="a format this stamp does not name"):
        _deck(f"CM ! Written by EZNEC/Pro+ v. 7.0\n{DAN}")


@pytest.mark.parametrize(
    "comment",
    [
        "CM converted from a NEC-5 deck",
        "CM exported by EZNEC, then hand-edited",
        "CM NEC-5 corpus",
    ],
)
def test_prose_about_eznec_or_nec5_declares_nothing(comment):
    """Matched by phrase, never by a substring: a comment that merely mentions
    the dialect or the program is prose (AK#1476)."""
    deck = _deck(f"{comment}\n{DAN}")
    assert deck.nec5_dialect is False


def test_the_bare_cm_nec5_card_still_declares():
    assert _deck(f"CM NEC-5\n{DAN}").nec5_dialect is True


# --------------------------------------------------------------------------
# sources and probes: the control deck, to the printed digit
# --------------------------------------------------------------------------
@needs_nec5
def test_the_control_deck_reproduces_its_printout_exactly():
    """The gate: AK re-emits the source where NEC-5 read it, so the licensed
    binary returns the printout's own 275.53 - 1441.0j. As written, with no
    edit to the deck — that number used to need `EX 0,1,378,2` typed in by
    hand (AK#1577's `..._when_the_port_is_a_knot`)."""
    (z,) = (complex(x) for x in _solve("WA7ARK-OCF-LoadOnly.nec", engine=NEC5Engine))
    assert z == pytest.approx(NEC5_CONTROL_Z, rel=1e-6)


def test_momwire_lands_within_one_percent_of_the_control():
    """momwire against NEC-5 on the same model once the port is in the same
    place: 0.64 % of |Z|, where the segment-centre reading was 2.11 %."""
    (z,) = (complex(x) for x in _solve("WA7ARK-OCF-LoadOnly.nec", solver=BSplineSolver))
    assert abs(z - NEC5_CONTROL_Z) / abs(NEC5_CONTROL_Z) < 0.01


def test_dans_deck_lands_within_one_percent_of_nec5():
    """The deck AK#1577 was built on, end to end: 0.75 % of |Z|, where the
    segment-centre reading was 2.44 %."""
    z_source, _z_probe = (
        complex(x) for x in _solve("failEZN5.nec", solver=BSplineSolver)
    )
    assert abs(z_source - NEC5_SOURCE_Z) / abs(NEC5_SOURCE_Z) < 0.01


def test_the_probe_and_its_load_share_one_knot_at_half_the_wire():
    """EZNEC records the current at a load by parking a 1e-10 V source on the
    same address: `LD 0,1,189,0` and `EX 0,1,189,0` are both end 2 of segment
    189 of a 378-segment wire — one knot, at 0.5 of the wire, and therefore
    one port carrying both (AK#1483's knot-sharing rule)."""
    deck = parse_nec(
        (FIXTURES / "failEZN5.nec").read_text(errors="replace"),
        name="failEZN5.nec",
        network=True,
    )
    (feed_probe,) = [f for f in deck.feeds if not f.current]
    (load,) = deck.loads
    assert (feed_probe.wire, feed_probe.seg, feed_probe.edge) == (0, 189, 2)
    assert (load.wire, load.seg, load.edge) == (0, 189, 2)
    # Knot 189 of 378 is exactly half the wire, and both ride it.
    n_seg = deck.wires[0].n_seg
    assert 189 / n_seg == 0.5
    probe_name = deck._vertex_plan[(0, 189)][0]
    net = deck.network()
    assert isinstance(net.ports[probe_name], PortAtVertex)
    # One port: the capacitor's branch and the probe's source name it both.
    (cap,) = [b for b in net.branches if getattr(b, "c", None) == 3e-10]
    (probe,) = [s for s in net.sources if s.port == probe_name]
    assert cap.port == probe_name and probe.voltage == 1e-10


# --------------------------------------------------------------------------
# the end on NT/TL
# --------------------------------------------------------------------------
# Two colinear 10-segment wires meeting at the origin, so every knot but the
# two far ends has another conductor on it. `EX 0,2,8,2` drives knot 8 of
# wire 2, clear of every attachment the cases below place.
TWO_WIRE = (
    f"{STAMP}\n"
    "CE\n"
    "GW 1,10,0.,-5.,10.,0.,0.,10.,.001\n"
    "GW 2,10,0.,0.,10.,0.,5.,10.,.001\n"
    "GE 0\nFR 0,1,0,0,14.\n"
    "EX 0,2,8,2,1.,0.\n"
    "{cards}"
    "EN\n"
)


def test_a_negative_tl_field_names_end_1_of_that_segment():
    """`TL 1,-4` is end 1 of segment 4 — knot 3 — and `TL 1,3` is end 2 of
    segment 3, which is the same knot. One node, two spellings."""
    a = _deck(TWO_WIRE.format(cards="TL 1,-4,2,5,50.,2.,0.,0.,0.,0.\n"))
    b = _deck(TWO_WIRE.format(cards="TL 1,3,2,5,50.,2.,0.,0.,0.,0.\n"))
    assert (a.tls[0].wire_a, a.tls[0].seg_a, a.tls[0].edge_a) == (0, 4, 1)
    assert (b.tls[0].wire_a, b.tls[0].seg_a, b.tls[0].edge_a) == (0, 3, 2)
    assert a.network().ports == b.network().ports
    assert a.wire_tuples() == b.wire_tuples()


def test_a_network_end_and_a_source_on_one_knot_are_one_port():
    """The shape the cardioid captures write: `EX 4,2,-1` and `TL …,2,-1`
    name knot 0 of wire 2, and AK used to read two places there — which is
    what refused captures 0120/0121."""
    deck = _deck(
        TWO_WIRE.replace("EX 0,2,8,2,1.,0.\n", "").format(
            cards=(
                "EX 4,2,6,2,1.414214,0.\n"  # knot 6 of wire 2
                "TL 1,5,2,6,50.,2.,0.,0.,0.,0.\n"  # ... and the line's far end
            )
        )
    )
    net = deck.network()
    assert isinstance(net.ports["feed"], PortAtVertex)
    assert "tl1b" not in net.ports  # it shares the source's port
    (line,) = [b for b in net.branches if getattr(b, "z0", None) == 50.0]
    assert line.b == "feed"


def test_a_network_end_at_a_lone_wire_end_keeps_its_segment_and_says_so():
    """A knot with no other conductor on it is a port between a lone
    conductor end and its ground contact, which no engine here hosts. The
    connection stays on the segment the card names, and the deck reports it
    rather than quietly moving the line."""
    deck = _deck(TWO_WIRE.format(cards="TL 1,-1,2,5,50.,2.,0.,0.,0.,0.\n"))
    assert deck.net_ends_demoted == ((0, 0),)
    assert (deck.tls[0].seg_a, deck.tls[0].edge_a) == (1, 0)
    note = deck.skipped_note()
    assert "wire 1 knot 0" in note
    assert "no other conductor there" in note


def test_a_zero_length_line_measures_between_the_knots():
    """NEC's zero-length TL is the straight-line distance between the
    CONNECTION POINTS, which on a NEC-5 deck are the knots."""
    deck = _deck(
        TWO_WIRE.format(cards="TL 1,-6,2,5,50.,0.,0.,0.,0.,0.\n"),
    )
    # knot 5 of wire 1 is y = -2.5, knot 5 of wire 2 is y = +2.5.
    assert deck.tls[0].length == pytest.approx(5.0)


# --------------------------------------------------------------------------
# the captures the `-1` end used to refuse
# --------------------------------------------------------------------------
# momwire's EZNEC capture corpus, read from the submodule at the recorded
# pointer — the same route `test_deck_nec2_corpus_1299.py` takes, and for the
# same reason: ten momwire modules read that tree, so a copy here would drift.
EZNEC_CORPUS = (
    Path(momwire.__file__).resolve().parents[2] / "tests" / "fixtures" / "eznec"
)
CAPTURES = EZNEC_CORPUS / "decks"
needs_captures = pytest.mark.skipif(
    not CAPTURES.is_dir(),
    reason=(
        f"momwire's EZNEC capture corpus is not on disk at {CAPTURES} — these "
        "read it from the momwire submodule (editable install), so a "
        "wheel-only momwire cannot run them"
    ),
)
CARDIOID = "0120_cardioid-l-network-feed.nec"


def _capture(name):
    return parse_nec(
        (CAPTURES / name).read_text(errors="replace"), name=name, network=True
    )


@needs_captures
@pytest.mark.parametrize("name", [CARDIOID, "0121_cardioid-l-network-feed.nec"])
def test_the_cardioid_captures_import(name):
    """Captures 0120/0121: a virtual wire feeding two grounded verticals
    through TL cards whose far ends carry `-1`, with an `EX 4 …,-1` on one of
    them. AK read the `-1` as segment 1 and collided a knot source with a
    segment port there; it now reads one node, and the deck opens.

    Both verticals STAND on the ground plane, so since AK#1598 the fed base is
    a ground-contact feed — an ordinary gap AT the contact (AK#1605; AK#1598
    first put it at that cell's centre) — rather than the series EMF a
    `PortAtVertex` spells. That is not a cosmetic
    change: this test used to assert the vertex port and stop at "the deck
    opens", and the shape it was pinning could not be SOLVED (momwire refuses
    a series `node_gaps` entry at a one-member junction). Hence the solve
    below, which is the claim that was missing."""
    deck = _capture(name)
    assert deck.virtual_segment_wires == frozenset({2})  # tag 3, the node holder
    net = deck.network()
    # The source and the line's far end are one port at knot 0 of wire 2 —
    # now spelled as the contact gap on the cell that knot stands in.
    assert isinstance(net.ports["feed2"], PortOnWire)
    assert not isinstance(net.ports["feed2"], PortAtVertex)
    assert net.ports["feed2"].at == 0.0  # the contact itself (AK#1605)
    assert "tl2b" not in net.ports
    # Wire 1's base carries only the line — and NOTHING IS DEMOTED any more.
    # This used to assert `net_ends_demoted == ((0, 0),)`, on the rule that a
    # lone wire end cannot host a network connection. Both verticals STAND on
    # the ground plane, so that end is a ground contact and the plane is its
    # second terminal; hosting it is what AK#1598/AK#1605 and momwire#1052 +
    # #1135 delivered, and AK#1608 retired the demotion for exactly this case.
    # The free-space case still demotes — see
    # `test_a_network_end_at_a_lone_wire_end_keeps_its_segment_and_says_so`,
    # whose fixture is `GE 0` with the wires ten metres up.
    assert deck.net_ends_demoted == ()
    assert deck.wire_tuples()  # used to raise the #824 collision


@needs_captures
@pytest.mark.parametrize("name", [CARDIOID, "0121_cardioid-l-network-feed.nec"])
def test_the_cardioid_captures_solve(name):
    """What "the deck opens" was standing in for. Before AK#1598 both captures
    imported and then raised `node_gaps[0]: junction 0 has a single member` on
    the first solve, so nothing here was reachable."""
    import numpy as np

    from antennaknobs.engines import MomwireEngine
    from antennaknobs.file_designs import builder_from_file

    cls = builder_from_file(str(CAPTURES / name))
    z = np.asarray(MomwireEngine(cls(), ground=cls.file_ground).impedance())
    assert z.shape == (2,)
    assert np.all(np.isfinite(z))

    # ... and on the RIGHT numbers, which "finite" never checked. These decks
    # carry an 18 ohm base load at the same knot as the line AND the source;
    # the load used to be dropped and the line demoted off the knot, which
    # left this route 1.29e-01 from `momwire.eznec.serve`. With the load
    # composed in series and everything external behind it (AK#1584, AK#1608),
    # the two routes we ship agree to float noise.
    from momwire.deck._nec5 import parse_nec5
    from momwire.eznec import serve

    text = (CAPTURES / name).read_text(errors="replace")
    mw = np.asarray([complex(s.impedance) for s in serve(parse_nec5(text)).sources])
    rel = float(np.max(np.abs(z - mw) / np.abs(mw)))
    assert rel < 1e-9, f"AK {z} vs serve {mw}, rel {rel:.3e}"


@needs_captures
@needs_nec5
def test_the_cardioid_capture_reaches_an_engine():
    """And it solves. 10 % / 12 % of the printout's two drive rows, which is
    reported rather than gated: both 18 ohm base loads are co-located with a
    line and stay unmodelled, and the verticals carry 30 segments."""
    deck = _capture(CARDIOID)
    zs = [
        complex(x)
        for x in NEC5Engine(
            _builder(deck, 7.15), ground=("finite", 13.0, 0.005)
        ).impedance()
    ]
    assert len(zs) == 2
    assert all(abs(z) > 1 for z in zs)


# --------------------------------------------------------------------------
# blast radius: only EZNEC's own decks move
# --------------------------------------------------------------------------
def test_every_fixture_here_lands_on_the_writer_its_stamp_names():
    """Every `.nec` fixture in this repo, all three ways: a deck stamped NEC-5
    declares, a deck stamped NEC-2 or NEC-4.2 is recognised and declares
    NOTHING, and an unstamped deck is not an EZNEC deck at all — so the
    4nec2-dialect decks (SY symbols, percent positions) and the hand-written
    NEC-2 decks keep their reading. No fixture refuses. A hash census of
    `wire_tuples()` + `network()` across the same fixtures moves 6, all of
    them EZNEC's NEC-5 export — `scratch/1579-eznec-declaration/` has it."""
    fixtures = sorted((Path(__file__).parent / "fixtures").rglob("*.nec"))
    assert len(fixtures) > 15
    seen = set()
    for f in fixtures:
        text = f.read_text(errors="replace")
        comments = [
            ln.strip()[2:].strip()
            for ln in text.splitlines()
            if ln.strip()[:2].upper() == "CM"
        ]
        declares = any(_eznec_declares_nec5(c, f.name) for c in comments)
        low = text.lower()
        if "written by eznec" not in low:
            assert declares is False, f.name
            seen.add("unstamped")
        elif "in nec-5 format" in low:
            assert declares is True, f.name
            seen.add("nec-5")
        else:
            assert declares is False, f.name
            seen.add("nec-2 family")
    assert seen == {"unstamped", "nec-5", "nec-2 family"}


# --------------------------------------------------------------------------
# one antenna, three writers
# --------------------------------------------------------------------------
# EZNEC's other two writers on the SAME model as the NEC-5 capture: see
# `tests/fixtures/eznec_writers_1579/README.md` for their provenance and
# their bytes. At the submodule pointer this branch runs against, that capture
# is `0010_dipole-in-free-space.nec` (the corpus later renumbered it 0183).
WRITERS = Path(__file__).parent / "fixtures" / "eznec_writers_1579"
DIPOLE1_NEC5 = "0010_dipole-in-free-space.nec"
DIPOLE1_FREQ = 299.7925


def _bspline_z(deck):
    return complex(
        MomwireEngine(
            _builder(deck, DIPOLE1_FREQ), solver=BSplineSolver, ground=None
        ).impedance()[0]
    )


def _file_deck(path):
    return parse_nec(path.read_text(errors="replace"), name=path.name, network=True)


def test_the_nec2_export_synthesizes_its_current_source_as_a_virtual_wire():
    """NEC-2 has no segment current source, so File > Save As spells one: a
    wire ~100 m away, an `EX 0` on it, and an `NT` between that node and the
    antenna. That is AK#1577's idiom already, and the structural detector
    takes it without the `LD 4 … 1.E+10` pins this vintage does not write.

    The `NT` is an ideal gyrator, which is how NEC-2 spells a CURRENT source,
    so AK#1595 reads the three cards as the one thing they are: the node and
    the injector collapse and the drive lands on the antenna's own port as a
    `DrivenCurrent`. EZNEC's own arithmetic checks it — `Y12 = +j` against
    `V = 1.414214j` gives 1.414214, which is exactly the current the NEC-4.2
    writer's `EX 6` asks for on the same model."""
    deck = _file_deck(WRITERS / "Dipole1-nec2-export.nec")
    assert deck.nec5_dialect is False  # the stamp names NEC-2
    assert deck.virtual_segment_wires == frozenset({1})  # tag 2
    net = deck.network()
    (src,) = net.sources
    assert isinstance(src, DrivenCurrent)
    assert src.current == pytest.approx(1.414214 + 0j)
    # On the antenna's own port on wire 1 — the NT's other end. Nothing
    # virtual, and no injector, survives to invert anything.
    assert src.port == "nt1b"
    assert isinstance(net.ports["nt1b"], PortOnWire)
    assert not [p for p in net.ports.values() if isinstance(p, PortVirtual)]
    assert not [b for b in net.branches if isinstance(b, Admittance)]


def test_the_nec42_deck_is_a_centre_fed_ex6():
    """The External NEC-4.2 slot writes NEC-4's `EX 6` segment current source.
    `I4` is a print flag in NEC-2 and NEC-4, not an end, so it takes issue
    #442's reading: the CENTRE of segment 6."""
    deck = _file_deck(WRITERS / "Dipole1-nec42-deck.nec")
    assert deck.nec5_dialect is False
    (feed,) = deck.feeds
    assert (feed.seg, feed.edge, feed.current) == (6, 0, True)
    (src,) = deck.network().sources
    assert isinstance(src, DrivenCurrent)


def test_the_two_nec2_writers_describe_the_same_antenna():
    """THE equality class, and the only pair here that is one: both decks take
    the NEC-2 reading and both put the source at the CENTRE of segment 6, so
    the single difference between them is how the drive is spelled — an `EX 6`
    current source against the phantom node, `EX 0` and gyrator EZNEC writes
    when the dialect has no such card.

    Until AK#1595 this read `1.0 / _bspline_z(export)`: the gyrator (Y11 =
    Y22 = 0, Y12 = j1, a 1 ohm gyration resistance) inverts impedance, and the
    import reported the driving point at the node the source sat on, so the
    reciprocal was the correction that made the pair agree — to 7.2e-13. The
    idiom now imports as the current source it spells, so there is nothing to
    undo and the two decks land on the same number directly."""
    via_injector = _bspline_z(_file_deck(WRITERS / "Dipole1-nec2-export.nec"))
    direct = _bspline_z(_file_deck(WRITERS / "Dipole1-nec42-deck.nec"))
    assert direct == pytest.approx(complex(82.1202, 45.9154), rel=1e-5)
    assert abs(via_injector - direct) / abs(direct) < 1e-9


@needs_captures
def test_the_nec5_writer_feeds_the_same_model_half_a_segment_higher():
    """RECORDED, not gated, and not this importer's doing. `EX 4,1,6,0` is
    NEC-5's end 2 of segment 6 — knot 6 of an 11-segment wire, 6/11 = 0.5454
    of it — where the other two writers' `EX 6,1,6,0` and `NT …,1,6` are
    NEC-2's centre of segment 6, 0.5. That half segment is the whole of the
    3.18e-02 between them on one solver.

    `EX 4` has taken NEC-5's end rule since issue #1243, so this predates
    AK#1579; AK's NEC-5 engine reproduces this capture's printout exactly
    (79.948 + 29.919j), i.e. the card is re-emitted where NEC-5 read it, and
    momwire's own EZNEC seam reads the same knot. Whether EZNEC means a
    centre-fed odd-segment model to feed at 6/11 in its NEC-5 export is a
    question about EZNEC."""
    nec5 = _capture(DIPOLE1_NEC5)
    (feed,) = nec5.feeds
    assert (feed.seg, feed.edge) == (6, 2)
    assert nec5.network().ports["feed"] == PortAtVertex("feed", end="p1")
    # Its own Z is pinned, as a guard on OUR reading of the card. The
    # cross-reading difference (3.18e-02 against the other two writers) is
    # recorded in the README, not asserted: the two feeds are not in the same
    # place, so their agreement would not mean anything and their
    # disagreement does not either.
    assert _bspline_z(nec5) == pytest.approx(complex(85.1086, 45.8302), rel=1e-5)

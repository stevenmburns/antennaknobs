"""EZNEC's NT gyrator imports as the current source it spells (AK#1595).

NEC-2 has no current-source `EX` card, so EZNEC writes one as a GYRATOR: a
phantom segment on the AK#1577 virtual wire carries an `EX 0` voltage source
and an `NT` with Y11 = Y22 = 0, Y12 = Y21 = j ties it to the real feed segment.
Imported literally the circuit is right and the readout is not — a gyrator
inverts impedance, so the driving point reported where the source sits is
1/Z of the antenna's.

The fixtures are ONE antenna in three dialects, which is what makes that a
measurement rather than an opinion: `tests/fixtures/eznec_gyrator_1595/`
has the provenance and the numbers. The gate that matters is convergence —
the NEC-2 deck and its NEC-4.2 twin must import to the same network and solve
to the same impedances, patterns and forced currents.

Detection has to stay narrow, because the same phantom wire legitimately
spells a source behind a transformer or a transmission line (AK#1577), and
there the source-side impedance is what the user asked for. Two gates hold
that line: a parametrized sweep over the NT's own Y fields, and the AK#1577
fixtures themselves.
"""

from pathlib import Path

import numpy as np
import pytest

from antennaknobs.engines import MomwireEngine
from antennaknobs.far_field import pattern_metrics
from antennaknobs.file_designs import builder_from_file
from antennaknobs.nec_import import _collapse_gyrator_drives, parse_nec
from antennaknobs.network import (
    Admittance,
    Driven,
    DrivenCurrent,
    Load,
    PortOnWire,
    PortVirtual,
)

FIXTURES = Path(__file__).parent / "fixtures" / "eznec_gyrator_1595"
VIRTUAL_1577 = Path(__file__).parent / "fixtures" / "eznec_virtual_wire_1577"

NEC2 = "Cardioidmodnec2.nec"
NEC4 = "Cardioidmodnec4.nec"

# The NEC-4.2 twin's own `EX 6` cards: what the gyrator pair must deliver.
EX6_CURRENTS = (complex(1.414214, 0.0), complex(0.0, -1.414214))
# momwire's answer on the oracle deck, which the NEC-2 deck must reproduce.
# OURS, not NEC-4.2's: the deck is the oracle for the DRIVE the other dialects
# must deliver, and these digits are what our own solver makes of it. So they
# are re-recordable when our solver's inputs deliberately change, and the
# identity below (`z2 == z4`) is what must not be.
#
# Re-recorded 2026-09-20 for AK#1607 — an imported deck is now solved at NEC's
# 299.8 MHz*m rather than the SI c, which is 2.5e-5 of relative frequency and
# moved these 3.9e-4. Both dialects moved together and still agree bitwise.
ORACLE_Z = (
    complex(36.433505553069786, -19.004373849634746),
    complex(67.76101624023624, 19.980489794638522),
)
# ... and its azimuth ring one degree above the horizon (the deck's own RP cut
# is the horizon itself; `far_field`'s grid stops one step short of it).
# Re-recorded with ORACLE_Z. The pattern is far less sensitive than the
# impedance: the peak did not move at 1e-4 dB, and the two figures that did
# are a front-to-back ratio and a null depth, which is what one expects of a
# frequency shift near a 30 dB null.
PEAK_DBI = 6.5744
NULL_DBI = -29.945
FRONT_TO_BACK_DB = 34.8489

# The gyrator card as EZNEC wrote it, and the source it drives.
GYRATOR_NT = "NT 3,2,1,1,0.,0.,0.,1.,0.,0."


def _text(name, where=FIXTURES):
    return (where / name).read_text(encoding="utf-8", errors="replace")


def _deck(name, where=FIXTURES):
    return parse_nec(_text(name, where), name=name, network=True)


def _solve(text, tmp_path, name="deck.nec"):
    """A deck through the `@file` route the workbench and CLI use: the deck's
    own segments, per-wire specs, the deck's ground."""
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    cls = builder_from_file(str(path))
    return MomwireEngine(cls(), ground=cls.file_ground)


def _shape(net):
    """A network as a name-free comparison key: what each port IS and where it
    sits, the branches, and the sources in order. Names differ between the two
    dialects by construction — the NEC-2 deck's real port is named after the
    NT end that reaches it — and the claim is about the circuit, not the
    naming."""
    ports = sorted(
        (type(p).__name__, getattr(p, "wire", None), getattr(p, "at", None))
        for p in net.ports.values()
    )
    branches = sorted(
        (type(b).__name__, getattr(b, "r", None), getattr(b, "z", None))
        for b in net.branches
    )
    sources = [(type(s).__name__, getattr(s, "current", getattr(s, "voltage", None)))
               for s in net.sources]  # fmt: skip
    return ports, branches, sources


# --------------------------------------------------------------------------
# the idiom, translated
# --------------------------------------------------------------------------
def test_the_gyrator_becomes_a_forced_current_on_the_real_segment():
    """The unit claim, and the one that pins sign, magnitude and phase: the
    two gyrators deliver EXACTLY the currents the NEC-4.2 twin's `EX 6` cards
    ask for — different phases on the two ports, so a global sign error, a
    scale error and a conjugation error all fail here."""
    net = _deck(NEC2).network()
    assert [type(s).__name__ for s in net.sources] == ["DrivenCurrent"] * 2
    assert tuple(s.current for s in net.sources) == EX6_CURRENTS
    # The phantom node and its gyrator are gone: nothing virtual survives,
    # and no `Admittance` branch is left to invert anything.
    assert not [p for p in net.ports.values() if isinstance(p, PortVirtual)]
    assert not [b for b in net.branches if isinstance(b, Admittance)]
    # The drive landed on real geometry — the segment the NT's other end
    # named, an eighth of the way up a 6-segment λ/4 vertical.
    for src in net.sources:
        port = net.ports[src.port]
        assert isinstance(port, PortOnWire)
        assert port.at == pytest.approx(1 / 12)


def test_the_two_dialects_import_to_one_network():
    """The convergence gate at the spec level: same port count, same ports in
    the same places, same branches, same sources."""
    n2, n4 = _deck(NEC2).network(), _deck(NEC4).network()
    assert len(n2.ports) == len(n4.ports) == 4
    assert _shape(n2) == _shape(n4)
    # Named, so a reader can see what the four are: two 18 Ω loads and two
    # forced drives, and nothing else.
    assert sorted(type(b).__name__ for b in n2.branches) == ["Load", "Load"]
    assert all(isinstance(b, Load) and b.r == 18.0 for b in n2.branches)


def test_the_nec4_deck_is_untouched():
    """The oracle imports as it always did — this change reaches only a deck
    whose drive sits behind a gyrator."""
    net = _deck(NEC4).network()
    assert [(s.port, s.current) for s in net.sources] == [
        ("feed1", EX6_CURRENTS[0]),
        ("feed2", EX6_CURRENTS[1]),
    ]


def test_skipped_note_names_the_gyrator_rather_than_the_nodes():
    note = _deck(NEC2).skipped_note()
    assert "1 EZNEC virtual wire (tag 3)" in note
    assert "2 NT-gyrator current sources forced on the segments they drive" in note
    # The nodes are not there to report: they collapsed with the gyrators.
    assert "virtual circuit node" not in note


# --------------------------------------------------------------------------
# the convergence gate, end to end
# --------------------------------------------------------------------------
def test_nec2_reports_the_nec4_driving_point_impedances(tmp_path):
    """Requirement 1: the deck that used to report 1/Z reports Z, and the two
    dialects agree. They agree to float noise, not to a tolerance — the
    imported networks are the same circuit on the same mesh."""
    z2 = np.asarray(_solve(_text(NEC2), tmp_path, NEC2).impedance())
    z4 = np.asarray(_solve(_text(NEC4), tmp_path, NEC4).impedance())
    assert z2 == pytest.approx(np.asarray(ORACLE_Z), rel=1e-6)
    assert z2 == pytest.approx(z4, rel=1e-12, abs=1e-12)
    # And emphatically NOT the reciprocals it used to report.
    assert abs(z2[0]) > 1.0 and abs(z2[1]) > 1.0


def test_the_pattern_is_unchanged(tmp_path):
    """Requirement 2: the pattern was already right — the gyrator delivered
    the correct currents all along — so the collapse must not move it. Pinned
    against the NEC-4.2 twin AND against absolute numbers, so a change that
    moved both decks together would still fail."""
    ff2 = _solve(_text(NEC2), tmp_path, NEC2).far_field()
    ff4 = _solve(_text(NEC4), tmp_path, NEC4).far_field()
    r2, r4 = np.asarray(ff2.rings, float), np.asarray(ff4.rings, float)
    assert np.abs(r2 - r4).max() < 1e-9

    m = pattern_metrics(ff2)
    assert m["peak_gain_dbi"] == pytest.approx(PEAK_DBI, abs=1e-3)
    assert m["azimuth_deg"] == 0.0
    assert m["front_to_back_db"] == pytest.approx(FRONT_TO_BACK_DB, abs=1e-3)
    ring = r2[-1]  # one degree above the horizon
    assert ring.min() == pytest.approx(NULL_DBI, abs=1e-3)

    # The null is a SYMMETRIC PAIR, 9 degrees either side of the back axis,
    # and the two are equal to float noise — 3.6e-15 dB. So which of them
    # `argmin` returns is the SIGN OF THAT NOISE, not a property of the
    # pattern. This used to read `phis[ring.argmin()] == approx(171.0)`,
    # which could only ever be green by luck: AK#1607's 2.5e-5 frequency
    # shift flipped it to 189 with the pattern itself unmoved. Assert the
    # symmetry, which is the real claim and cannot flip.
    phis = np.asarray(ff2.phis, float)
    lo = int(np.flatnonzero(phis == 171.0)[0])
    hi = int(np.flatnonzero(phis == 189.0)[0])
    assert {ring[lo], ring[hi]} == {ring.min()} or ring[lo] == pytest.approx(
        ring[hi], abs=1e-9
    )
    assert abs(phis[ring.argmin()] - 180.0) == pytest.approx(9.0)


def test_a_mixed_voltage_and_gyrator_deck_agrees_with_nec4(tmp_path):
    """The absolute-sign gate. Impedance, input power and a dBi pattern are
    all invariant under flipping BOTH forced currents, so the deck as written
    cannot tell `I = −Y12·V` from `+Y12·V`. Drive one element through the
    gyrator and the other with an ordinary `EX 0` on real geometry, in both
    dialects, and the relative phase stops being arbitrary: with the sign
    flipped, port 2 moves from −1.147 − 0.976j to +1.130 + 0.894j."""
    mixed2 = (
        _text(NEC2)
        .replace("EX 0,3,3,0,1.414214,0.\n", "")
        .replace("NT 3,3,2,1,0.,0.,0.,1.,0.,0.\n", "")
        .replace("EX 0,3,2,0,0.,1.414214", "EX 0,3,2,0,0.,1.414214\nEX 0,2,1,0,1.,0.")
    )
    mixed4 = _text(NEC4).replace("EX 6,2,1,0,0.,-1.414214", "EX 0,2,1,0,1.,0.")

    # The mutation has to land, or the test proves nothing. Counted over CARDS
    # — the deck's own `CM ! NT #1-2 are EZNEC current sources` says "NT " too.
    def cards(text, mnemonic):
        return sum(1 for ln in text.splitlines() if ln.startswith(mnemonic))

    assert (cards(mixed2, "NT "), cards(mixed2, "EX ")) == (1, 2)
    assert (cards(mixed4, "EX 6"), cards(mixed4, "EX ")) == (1, 2)

    net2 = parse_nec(mixed2, name="mixed2.nec", network=True).network()
    assert [type(s).__name__ for s in net2.sources] == ["DrivenCurrent", "Driven"]
    assert net2.sources[0].current == EX6_CURRENTS[0]

    z2 = np.asarray(_solve(mixed2, tmp_path, "mixed2.nec").impedance())
    z4 = np.asarray(_solve(mixed4, tmp_path, "mixed4.nec").impedance())
    assert z2 == pytest.approx(z4, rel=1e-9, abs=1e-12)
    # The voltage-driven element's port is the sensitive one — name what it
    # is, so a drift in the fixture cannot pass as agreement. Re-recorded for
    # AK#1607 with ORACLE_Z, and for the same reason.
    assert z2[1] == pytest.approx(
        complex(-1.147720151352307, -0.9753739365962907), rel=1e-5
    )


# --------------------------------------------------------------------------
# detection stays narrow
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("card", "collapses"),
    [
        ("NT 3,2,1,1,0.,0.,0.,1.,0.,0.", True),  # the gyrator EZNEC writes
        ("NT 3,2,1,1,0.,0.,0.,-1.,0.,0.", True),  # ... with the other sign
        ("NT 3,2,1,1,1.E-3,0.,0.,1.,0.,0.", False),  # Y11 real: a lossy line
        ("NT 3,2,1,1,0.,1.E-3,0.,1.,0.,0.", False),  # Y11 reactive
        ("NT 3,2,1,1,0.,0.,0.,1.,1.E-3,0.", False),  # Y22 real
        ("NT 3,2,1,1,0.,0.,1.,1.,0.,0.", False),  # Y12 not purely reactive
        ("NT 3,2,1,1,0.,0.,1.,0.,0.,0.", False),  # Y12 real: a resistive pi
    ],
)
def test_only_the_gyrator_shape_collapses(card, collapses):
    """The signature is the whole of the specificity argument, so walk the
    NT's own fields. A transformer is an all-real Y (it arrives as a
    `Transformer`, AK#1681, not an `Admittance` at all) and a lossy line is lossy, so
    its 2x2 has a nonzero diagonal — the first two rejections below are those
    two shapes, reduced to one field each."""
    net = parse_nec(
        _text(NEC2).replace(GYRATOR_NT, card), name="mutant.nec", network=True
    ).network()
    virtual = [n for n, p in net.ports.items() if isinstance(p, PortVirtual)]
    if collapses:
        assert virtual == []
        assert isinstance(net.sources[0], DrivenCurrent)
    else:
        # Untouched: the phantom node survives and still carries the EX 0.
        assert virtual == ["rig1"]
        assert net.sources[0] == Driven(port="rig1", voltage=complex(0, 1.414214))


def _gyrator_net(voltage=complex(0, 1.414214), extra_branches=(), extra_sources=()):
    """The idiom's three pieces on their own, to exercise the rule directly
    where no EX card can reach it: a driven virtual node, a gyrator, a real
    port."""
    ports = {"v": PortVirtual("v"), "r": PortOnWire("r")}
    branches = [Admittance(ports=("v", "r"), y=((0j, 1j), (1j, 0j))), *extra_branches]
    sources = [Driven(port="v", voltage=voltage), *extra_sources]
    return _collapse_gyrator_drives(ports, branches, sources)


def test_a_zero_volt_source_behind_a_gyrator_is_not_a_drive():
    """`Driven(port, 0)` is momwire's datum pin — a hard V = 0 that leaves the
    rest of the network passive — not an excitation. Forcing 0 A instead is an
    open circuit reporting an infinite driving point, a different answer, so
    the idiom is not read into it. Unreachable from a deck (a zero-volt `EX 0`
    is driven at 1 V, as NEC itself does), hence the direct call."""
    _ports, _branches, sources, gyrators = _gyrator_net(voltage=0j)
    assert gyrators == {}
    assert sources == [Driven(port="v", voltage=0j)]


def test_a_gyrator_onto_an_already_driven_port_is_left_alone():
    """Two drives on one node is not a network, so a real port that already
    carries a source is not one the forced current may move onto."""
    _ports, _branches, sources, gyrators = _gyrator_net(
        extra_sources=[Driven(port="r", voltage=1 + 0j)]
    )
    assert gyrators == {}
    assert [type(s).__name__ for s in sources] == ["Driven", "Driven"]


@pytest.mark.parametrize("name", ["failEZN5.nec", "WA7ARK-OCF-Load-Xfmr-TL.nec"])
def test_a_source_behind_a_transformer_or_line_is_left_alone(name):
    """AK#1577's own fixtures: Mike WA7ARK's OCF dipole with an EZNEC
    transformer and a lossy line behind the same kind of virtual wire. There
    the source-side impedance IS what the user asked for (the AK#1577 circuit
    gate lands on NEC-5's printed 48.919 + 103.89j), so nothing may collapse —
    the virtual nodes, the complex-Y line and the pins all stay."""
    deck = _deck(name, VIRTUAL_1577)
    net = deck.network()
    assert sorted(n for n, p in net.ports.items() if isinstance(p, PortVirtual)) == [
        "nt1a",
        "rig1" if name == "failEZN5.nec" else "rig",
    ]
    (line,) = [
        b for b in net.branches if isinstance(b, Admittance) and len(b.ports) == 2
    ]
    assert set(line.ports) == {"nt1a", "rig1" if name == "failEZN5.nec" else "rig"}
    assert "virtual circuit nodes" in deck.skipped_note()


def test_the_open_circuit_pins_collapse_with_the_node_they_held():
    """EZNEC pins every virtual segment it uses with `LD 4 … 1.E+10` in its
    newer decks (AK#1577). A pin is a shunt across an ideal voltage source, so
    it injects nothing into the rest of the circuit and goes with the node —
    the deck must still collapse, and must not leave a branch behind pointing
    at a port that no longer exists."""
    pinned = _text(NEC2).replace(
        "LD 4,1,2,0,18.,0.",
        "LD 4,3,2,0,1.E+10,0.\nLD 4,3,3,0,1.E+10,0.\nLD 4,1,2,0,18.,0.",
    )
    deck = parse_nec(pinned, name="pinned.nec", network=True)
    assert len(deck.virtual_pins) == 2
    net = deck.network()
    assert tuple(s.current for s in net.sources) == EX6_CURRENTS
    assert not [b for b in net.branches if isinstance(b, Admittance)]
    assert sorted(type(b).__name__ for b in net.branches) == ["Load", "Load"]
    # The pins are no longer reported as opens the solve carries, because it
    # does not carry them.
    assert "open-circuit pin" not in deck.skipped_note()

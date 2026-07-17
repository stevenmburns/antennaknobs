"""Tests for antennaknobs.nec_import.

Card semantics are unit-tested with inline decks against the behaviour of
nec2c 1.3.1's geometry.c (the reference the parser was transcribed from).
A smoke test over the xnec2c example decks runs only where that checkout
exists (developer machines), guarded by a skipif.
"""

import math
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from antennaknobs.nec_import import parse_nec

XNEC2C_EXAMPLES = Path.home() / "antennas" / "xnec2c" / "examples"

DIPOLE = """\
CM a plain half-wave dipole
CE
GW 1 21 0 -5.0 10.0 0 5.0 10.0 1.0E-03
GE 0
EX 0 1 11 0 1.0 0.0
FR 0 11 0 0 14.0 0.05
EN
"""


def test_basic_gw_deck():
    deck = parse_nec(DIPOLE)
    assert len(deck.wires) == 1
    w = deck.wires[0]
    assert (w.tag, w.n_seg, w.radius) == (1, 21, 1.0e-03)
    assert w.p1 == (0.0, -5.0, 10.0)
    assert w.p2 == (0.0, 5.0, 10.0)
    assert deck.comments == ("a plain half-wave dipole",)
    assert deck.ground is False
    assert deck.freq_mhz == (14.0, pytest.approx(14.5))


def test_feed_at_middle_segment_keeps_wire_whole():
    deck = parse_nec(DIPOLE)
    assert deck.feeds == ((deck.feeds[0]),)
    assert (deck.feeds[0].wire, deck.feeds[0].seg) == (0, 11)
    tups = deck.wire_tuples()
    assert len(tups) == 1
    p1, p2, n_seg, ex = tups[0]
    assert (p1, p2, n_seg, ex) == ((0.0, -5.0, 10.0), (0.0, 5.0, 10.0), 21, 1 + 0j)


def test_off_middle_feed_splits_wire_on_segment_boundaries():
    deck = parse_nec("GW 1 10 0 0 0  10 0 0  0.001\nGE\nEX 0 1 3 0 2.0 1.0\nEN\n")
    tups = deck.wire_tuples()
    # 10 segments fed at segment 3: pieces of 2 / 1 (fed) / 7 segments.
    assert [(t[2], t[3]) for t in tups] == [(2, None), (1, 2 + 1j), (7, None)]
    # Split points sit on the original segment boundaries...
    assert tups[0][1] == tups[1][0] == (2.0, 0.0, 0.0)
    assert tups[1][1] == tups[2][0] == (3.0, 0.0, 0.0)
    # ...and the outer endpoints are the original wire's.
    assert tups[0][0] == (0.0, 0.0, 0.0)
    assert tups[2][1] == (10.0, 0.0, 0.0)


def test_absolute_segment_addressing_with_tag_zero():
    deck = parse_nec(
        "GW 1 5 0 0 0  1 0 0  0.001\n"
        "GW 2 5 1 0 0  2 0 0  0.001\n"
        "GE\n"
        "EX 0 0 8 0 1.0 0.0\n"  # absolute segment 8 = wire 2, segment 3
        "EN\n"
    )
    assert (deck.feeds[0].wire, deck.feeds[0].seg) == (1, 3)


def test_comma_separated_and_fortran_d_exponents():
    deck = parse_nec("GW 1,3, 0,0,0, 0,0,1.0D+01, 1.0D-03\nGE\nEX 0 1 2 0 1 0\nEN\n")
    assert deck.wires[0].p2 == (0.0, 0.0, 10.0)
    assert deck.wires[0].radius == 1.0e-03


def test_gs_scales_everything_and_xnec2c_tag_range():
    deck = parse_nec(
        "GW 1 3 0 0 0  1 0 0  0.001\n"
        "GW 2 3 0 0 0  0 1 0  0.001\n"
        "GS 0 0 2.0\n"  # standard: scale all
        "GS 2 2 3.0\n"  # xnec2c extension: scale tag 2 only
        "GE\nEX 0 1 2 0 1 0\nEN\n"
    )
    w1, w2 = deck.wires
    assert w1.p2 == (2.0, 0.0, 0.0)
    assert w1.radius == pytest.approx(0.002)
    assert w2.p2 == (0.0, 6.0, 0.0)
    assert w2.radius == pytest.approx(0.006)


def test_gm_moves_structure_in_place():
    # The 2m_yagi.nec idiom: GM with NRPT=0 shifts every wire.
    deck = parse_nec(
        "GW 1 3 0 -1 0  0 1 0  0.001\nGM 0 0 0 0 0 -1.0 0 0 0\nGE\nEX 0 1 2 0 1 0\nEN\n"
    )
    assert deck.wires[0].p1 == (-1.0, -1.0, 0.0)
    assert deck.wires[0].p2 == (-1.0, 1.0, 0.0)


def test_gm_replication_compounds_and_closes_a_quad_loop():
    # The 20m_quad.nec idiom: one loop side, then GM 0 3 <90 deg about X>
    # replicates it into a closed square. Each copy rotates the previous one.
    deck = parse_nec(
        "GW 1 13 0 2.72 -2.72  0 2.72 2.72  0.002\n"
        "GM 0 3 90 0 0 0 0 0 0\n"
        "GE\nEX 0 1 7 0 1 0\nEN\n"
    )
    assert len(deck.wires) == 4
    assert all(w.tag == 1 for w in deck.wires)  # ITGI=0 keeps tags
    # Rotation about X by 90 deg maps (x, y, z) -> (x, -z, y).
    assert deck.wires[1].p1 == pytest.approx((0.0, 2.72, 2.72))
    assert deck.wires[1].p2 == pytest.approx((0.0, -2.72, 2.72))
    # The four sides close: every loop vertex appears exactly twice.
    counts = {}
    for w in deck.wires:
        for p in (w.p1, w.p2):
            key = tuple(round(c, 9) for c in p)
            counts[key] = counts.get(key, 0) + 1
    assert sorted(counts.values()) == [2, 2, 2, 2]


def test_gm_tag_increment_and_its_start_tag():
    deck = parse_nec(
        "GW 1 3 0 0 0  1 0 0  0.001\n"
        "GW 2 3 0 0 1  1 0 1  0.001\n"
        "GM 10 2 0 0 0 0 0 5.0 2\n"  # replicate from tag 2 on, +5 in z each
        "GE\nEX 0 1 2 0 1 0\nEN\n"
    )
    assert [w.tag for w in deck.wires] == [1, 2, 12, 22]
    assert [w.p1[2] for w in deck.wires] == [0.0, 1.0, 6.0, 11.0]


def test_gx_reflects_z_then_y_and_doubles_tag_increment():
    deck = parse_nec(
        "GW 1 3 1 1 1  2 2 2  0.001\n"
        "GX 100 011\n"  # reflect in Z=0 then Y=0
        "GE\nEX 0 1 2 0 1 0\nEN\n"
    )
    assert [w.tag for w in deck.wires] == [1, 101, 201, 301]
    assert deck.wires[1].p1 == (1.0, 1.0, -1.0)  # Z image
    assert deck.wires[2].p1 == (1.0, -1.0, 1.0)  # Y image of original
    assert deck.wires[3].p1 == (1.0, -1.0, -1.0)  # Y image of Z image


def test_gx_rejects_wire_in_symmetry_plane():
    with pytest.raises(ValueError, match="symmetry"):
        parse_nec("GW 1 3 0 -1 0  0 1 0  0.001\nGX 0 010\nGE\nEN\n")


def test_gr_forms_cylindrical_structure():
    deck = parse_nec("GW 1 3 1 0 0  1 0 1  0.001\nGR 10 4\nGE\nEX 0 1 2 0 1 0\nEN\n")
    assert [w.tag for w in deck.wires] == [1, 11, 21, 31]
    angles = [math.atan2(w.p1[1], w.p1[0]) for w in deck.wires]
    expected = [0.0, math.pi / 2, math.pi, -math.pi / 2]
    for got, want in zip(angles, expected):
        assert math.remainder(got - want, 2 * math.pi) == pytest.approx(0.0, abs=1e-12)
    assert all(math.hypot(w.p1[0], w.p1[1]) == pytest.approx(1.0) for w in deck.wires)


def test_ga_arc_chords_lie_on_the_circle():
    deck = parse_nec("GA 1 4 2.0 0 90 0.001\nGE\nEX 0 1 2 0 1 0\nEN\n")
    assert len(deck.wires) == 4
    assert all(w.n_seg == 1 for w in deck.wires)
    assert deck.wires[0].p1 == pytest.approx((2.0, 0.0, 0.0))
    assert deck.wires[-1].p2 == pytest.approx((0.0, 0.0, 2.0))
    for w in deck.wires:
        assert w.p1[1] == w.p2[1] == 0.0  # the arc lives in the XZ plane
        assert math.hypot(w.p1[0], w.p1[2]) == pytest.approx(2.0)
    # Chords connect end to start.
    assert deck.wires[1].p1 == deck.wires[0].p2


def test_gh_helix_geometry():
    # One full right-handed turn: spacing 1.0, length 1.0, radius 0.5.
    deck = parse_nec("GH 1 8 1.0 1.0 0.5 0 0.5 0 0.001\nGE\nEX 0 1 2 0 1 0\nEN\n")
    assert len(deck.wires) == 8
    assert deck.wires[0].p1 == pytest.approx((0.5, 0.0, 0.0))
    assert deck.wires[-1].p2 == pytest.approx((0.5, 0.0, 1.0))
    for w in deck.wires:
        assert math.hypot(w.p1[0], w.p1[1]) == pytest.approx(0.5)
    # Right-handed: a quarter turn up reaches +y.
    assert deck.wires[1].p2 == pytest.approx((0.0, 0.5, 0.25))
    # hl < 0 winds left-handed: x and y swap.
    left = parse_nec("GH 1 8 1.0 -1.0 0.5 0 0.5 0 0.001\nGE\nEX 0 1 2 0 1 0\nEN\n")
    assert left.wires[1].p2 == pytest.approx((0.5, 0.0, 0.25))


def test_run_config_cards_are_recorded_not_applied():
    deck = parse_nec(
        "GW 1 3 0 -1 1  0 1 1  0.001\n"
        "GE 1\n"
        "GN 2 0 0 0 13.0 0.005\n"
        "LD 5 0 0 0 3.7E+07\n"
        "TL 1 2 1 2 50.0 0\n"
        "EX 0 1 2 0 1 0\nEN\n"
    )
    assert deck.ground is True
    assert deck.ignored == ("GN", "LD", "TL")


def test_skipped_note_renders_ignored_cards_and_ground():
    deck = parse_nec(
        "GW 1 3 0 -1 1  0 1 1  0.001\n"
        "GE 1\n"
        "GN 2 0 0 0 13.0 0.005\n"
        "LD 5 0 0 0 3.7E+07\n"
        "EX 0 1 2 0 1 0\nEN\n"
    )
    note = deck.skipped_note()
    # Descriptions come from _IGNORED_CARDS (the single source of truth),
    # the ground request is called out, and mnemonic case survives.
    assert note == (
        "Deck cards not applied: GN (ground parameters), LD (loading); "
        "the deck models a ground plane — the app's own ground/loading/sweep "
        "settings are used instead."
    )


def test_skipped_note_ground_flag_only_and_clean_deck():
    # GE 1 alone (no GN card): ground is requested but nothing is in
    # `ignored`, so only the ground clause renders.
    flag_only = parse_nec("GW 1 3 0 0 1  1 0 1  0.001\nGE 1\nEX 0 1 2 0 1 0\nEN\n")
    assert flag_only.ignored == ()
    note = flag_only.skipped_note()
    assert note is not None and note.startswith("The deck models a ground plane")

    # Free-space deck with no run-config cards: nothing to report.
    clean = parse_nec("GW 1 3 0 0 1  1 0 1  0.001\nGE\nEX 0 1 2 0 1 0\nEN\n")
    assert clean.skipped_note() is None


def test_multiple_feeds_and_complex_voltage():
    deck = parse_nec(
        "GW 1 3 0 0 1  1 0 1  0.001\n"
        "GW 2 3 0 1 1  1 1 1  0.001\n"
        "GE\n"
        "EX 0 1 2 0 1.0 0.0\n"
        "EX 0 2 2 0 0.0 -1.0\n"
        "EN\n"
    )
    tups = deck.wire_tuples()
    assert [t[3] for t in tups] == [1 + 0j, -1j]


def test_errors_are_specific():
    with pytest.raises(ValueError, match="plane-wave"):
        parse_nec("GW 1 3 0 0 0 1 0 0 0.001\nGE\nEX 1 10 10 0 0 0\nEN\n")
    with pytest.raises(ValueError, match="tapered"):
        parse_nec("GW 1 3 0 0 0 1 0 0 0.0\nGC 0 0 0.5 0.001 0.002\nGE\nEN\n")
    with pytest.raises(ValueError, match="surface patch"):
        parse_nec("SP 0 0 1 0 0 0 0 0\nGE\nEN\n")
    with pytest.raises(ValueError, match="no wire has tag"):
        parse_nec("GW 1 3 0 0 0 1 0 0 0.001\nGE\nEX 0 9 1 0 1 0\nEN\n")
    with pytest.raises(ValueError, match="only 3 segments"):
        parse_nec("GW 1 3 0 0 0 1 0 0 0.001\nGE\nEX 0 1 4 0 1 0\nEN\n")
    with pytest.raises(ValueError, match="defines no wires"):
        parse_nec("CM empty\nCE\nGE\nEN\n")
    with pytest.raises(ValueError, match="line 2"):
        parse_nec("GW 1 3 0 0 0 1 0 0 0.001\nGW 2 nope 0 0 1 1 0 1 0.001\n")
    with pytest.raises(ValueError, match="no voltage-source EX"):
        parse_nec("GW 1 3 0 0 0 1 0 0 0.001\nGE\nEN\n").wire_tuples()


def test_freq_range_multiplicative():
    deck = parse_nec(
        "GW 1 3 0 0 0 1 0 0 0.001\nGE\nFR 1 3 0 0 10.0 2.0\nEX 0 1 2 0 1 0\nEN\n"
    )
    assert deck.freq_mhz == (10.0, 40.0)


def test_dominant_radius_is_length_weighted():
    deck = parse_nec(
        "GW 1 3 0 0 0  1 0 0  0.001\n"  # 1 m of 1 mm
        "GW 2 3 0 0 1  9 0 1  0.005\n"  # 8 m of 5 mm
        "GE\nEX 0 1 2 0 1 0\nEN\n"
    )
    assert deck.dominant_radius() == 0.005


ROUNDTRIP_DECKS = [
    # An off-centre-fed dipole: exercises the feed wire split.
    (
        "ocf-dipole",
        2.0,
        "CE\n"
        "GW 1 21 0. -10. 0. 0. 10. 0. 1.0E-03\n"
        "GE 0\nEX 0 1 7 0 1. 0.\nFR 0 1 0 0 7.0 0.\nXQ 0\nEN\n",
    ),
    # The xnec2c 2m_yagi geometry (sans LD loading): GM shift, middle feeds.
    (
        "2m-yagi",
        0.1,
        "CE\n"
        "GW 1 25 0.0 0.509 0.0 0.0 -0.509 0.0 5.0E-03\n"
        "GW 2 25 0.4 0.484 0.0 0.4 -0.484 0.0 5.0E-03\n"
        "GW 3 21 0.7 0.459 0.0 0.7 -0.459 0.0 5.0E-03\n"
        "GW 4 21 1.1 0.450 0.0 1.1 -0.450 0.0 5.0E-03\n"
        "GW 5 21 1.5 0.440 0.0 1.5 -0.440 0.0 5.0E-03\n"
        "GW 6 21 1.9 0.430 0.0 1.9 -0.430 0.0 5.0E-03\n"
        "GM 0 0 0. 0. 0. -1.0 0. 0. 0.\n"
        "GE 0\nEX 0 2 13 0 1. 0.\nFR 0 1 0 0 145.0 0.\nXQ 0\nEN\n",
    ),
]


@pytest.mark.skipif(shutil.which("nec2c") is None, reason="nec2c CLI not installed")
@pytest.mark.parametrize("name,tol,deck_text", ROUNDTRIP_DECKS)
def test_roundtrip_impedance_matches_nec2c(name, tol, deck_text):
    """The imported geometry, solved by PyNECEngine with the deck's radius,
    reproduces the impedance nec2c computes from the deck itself. The looser
    ocf tolerance covers the engine's odd-parity resegmentation of the split
    pieces; the feed arclength itself is preserved exactly."""
    pytest.importorskip("PyNEC")
    from types import MappingProxyType

    from antennaknobs import AntennaBuilder, WireSpec
    from antennaknobs.engines.pynec import PyNECEngine

    deck = parse_nec(deck_text, name=name)
    freq = deck.freq_mhz[0]

    class B(AntennaBuilder):
        default_params = MappingProxyType({"freq": freq})
        _deck = deck

        def build_wires(self):
            return self._deck.wire_tuples()

        def build_wire_material(self):
            return WireSpec(radius=self._deck.dominant_radius())

    (z_engine,) = PyNECEngine(B(), ground="free").impedance()
    (z_nec2c,) = _nec2c_impedances(deck_text)
    assert abs(z_engine - z_nec2c) < tol, f"engine={z_engine} nec2c={z_nec2c}"


def _nec2c_impedances(deck_text):
    with tempfile.TemporaryDirectory() as d:
        nec, out = Path(d) / "deck.nec", Path(d) / "deck.out"
        nec.write_text(deck_text)
        subprocess.run(
            ["nec2c", "-i", str(nec), "-o", str(out)], check=True, capture_output=True
        )
        lines = out.read_text().splitlines()
    zs = []
    for i, ln in enumerate(lines):
        if "ANTENNA INPUT PARAMETERS" in ln:
            j = i + 3
            while j < len(lines) and lines[j].strip():
                toks = lines[j].split()
                if len(toks) >= 8:
                    zs.append(complex(float(toks[6]), float(toks[7])))
                j += 1
            break
    return zs


@pytest.mark.skipif(
    not XNEC2C_EXAMPLES.is_dir(), reason="xnec2c examples checkout not present"
)
def test_smoke_parse_xnec2c_examples():
    """Most of the xnec2c example decks should parse; the rest must fail with
    a deliberate 'cannot model' / deck-shape error, never an unhandled one."""
    parsed, rejected = [], []
    for path in sorted(XNEC2C_EXAMPLES.glob("*.nec")):
        try:
            deck = parse_nec(path.read_text(), name=path.name)
        except ValueError as e:
            rejected.append((path.name, str(e)))
            continue
        assert deck.wires, path.name
        if deck.feeds:
            tups = deck.wire_tuples()
            assert sum(1 for t in tups if t[3] is not None) == len(deck.feeds)
        parsed.append(path.name)
    for must_parse in ("2m_yagi.nec", "20m_quad.nec", "40m-moxon.nec"):
        assert must_parse in parsed
    assert len(parsed) >= 40, (len(parsed), rejected)


# ---------------------------------------------------------------------------
# network=True — LD/TL/NT translation into build_network branches (issue #385)
# ---------------------------------------------------------------------------

from antennaknobs.nec_import import NecLoad, NecNT, NecTL  # noqa: E402
from antennaknobs.network import TL, Admittance, Load, Shunt  # noqa: E402


def _branch_ports(br):
    return (br.a, br.b) if hasattr(br, "a") else (br.port,)


def _dipole7(*cards):
    """A 7-segment dipole fed at its middle segment, plus extra cards."""
    return (
        "GW 1 7 0 -3.5 10 0 3.5 10 0.001\nGE\nEX 0 1 4 0 1 0\n"
        + "".join(c + "\n" for c in cards)
        + "EN\n"
    )


def test_network_mode_translates_single_segment_ld():
    deck = parse_nec(_dipole7("LD 0 1 2 2 5.0 2e-6 0"), network=True)
    assert deck.loads == (
        NecLoad(wire=0, seg=2, r=5.0, l=2e-6, c=None, parallel=False),
    )
    assert "LD" not in deck.ignored and deck.ignored_detail == ()

    net = deck.network()
    assert net.branches == [Load(port="load1", r=5.0, l=2e-6, c=None, parallel=False)]
    assert [(s.port, s.voltage) for s in net.sources] == [("feed", 1 + 0j)]
    assert set(net.ports) == {"feed", "load1"}

    # The loaded segment becomes its own named 1-segment wire on the deck's
    # exact boundaries; the feed keeps the whole wire? No — two marks on one
    # wire force a split, and the fed segment gets its own named piece too.
    tups = deck.wire_tuples()
    named = {t[4]: t for t in tups if len(t) == 5}
    assert set(named) == {"feed", "load1"}
    assert named["load1"][2] == 1 and named["feed"][2] == 1
    assert all(t[3] is None for t in tups)  # no legacy ex markers
    assert sum(t[2] for t in tups) == 7  # segmentation preserved


def test_ld_parallel_and_zero_legs():
    deck = parse_nec(_dipole7("LD 1 1 2 2 0 3.3e-6 4.7e-12"), network=True)
    (ld,) = deck.loads
    assert ld.parallel is True
    assert ld.r is None and ld.l == 3.3e-6 and ld.c == 4.7e-12
    # An all-zero lumped load is a no-op, not an ignored card.
    deck = parse_nec(_dipole7("LD 0 1 2 2 0 0 0"), network=True)
    assert deck.loads == () and "LD" not in deck.ignored


def test_ld_range_expands_per_segment_up_to_cap():
    deck = parse_nec(_dipole7("LD 0 1 2 4 1.0 0 0"), network=True)
    assert [(ld.wire, ld.seg) for ld in deck.loads] == [(0, 2), (0, 3), (0, 4)]
    assert all(ld.r == 1.0 for ld in deck.loads)
    # seg 4 is the fed segment: the load shares the feed's port there.
    net = deck.network()
    assert sorted(br.port for br in net.branches) == ["feed", "load1", "load2"]

    # A whole-tag range (12 segments > the 8-segment cap) is refused.
    wide = "GW 1 12 0 -3 10 0 3 10 0.001\nGE\nEX 0 1 6 0 1 0\nLD 0 1 0 0 1.0 0 0\nEN\n"
    deck = parse_nec(wide, network=True)
    assert deck.loads == ()
    assert "LD" in deck.ignored
    assert any("12 segments" in why for _m, why in deck.ignored_detail)


def test_ld4_pure_resistance_translates_reactance_does_not():
    deck = parse_nec(_dipole7("LD 4 1 2 2 50.0 0 0"), network=True)
    assert deck.loads == (
        NecLoad(wire=0, seg=2, r=50.0, l=None, c=None, parallel=False),
    )
    deck = parse_nec(_dipole7("LD 4 1 2 2 50.0 25.0 0"), network=True)
    assert deck.loads == () and "LD" in deck.ignored
    assert any("type 4" in why for _m, why in deck.ignored_detail)
    # The reason surfaces in the UI note (composes with #373).
    assert "type 4" in deck.skipped_note()


def test_ld5_whole_structure_becomes_conductivity():
    deck = parse_nec(_dipole7("LD 5 0 0 0 3.7e7 0 0"), network=True)
    assert deck.conductivity == 3.7e7
    assert "LD" not in deck.ignored
    # Ranged conductivity can't map to the single whole-antenna WireSpec.
    deck = parse_nec(_dipole7("LD 5 1 2 4 3.7e7 0 0"), network=True)
    assert deck.conductivity is None and "LD" in deck.ignored


def test_ld_minus_one_nullifies_previous_loads():
    deck = parse_nec(
        _dipole7("LD 0 1 2 2 5.0 0 0", "LD -1 0 0 0 0 0 0", "LD 0 1 3 3 7.0 0 0"),
        network=True,
    )
    assert deck.loads == (
        NecLoad(wire=0, seg=3, r=7.0, l=None, c=None, parallel=False),
    )


def test_ld_distributed_and_duplicate_are_ignored_with_reasons():
    deck = parse_nec(_dipole7("LD 2 1 2 2 1.0 1e-6 0"), network=True)
    assert deck.loads == () and any(
        "per-metre" in why for _m, why in deck.ignored_detail
    )
    deck = parse_nec(_dipole7("LD 0 1 2 2 5.0 0 0", "LD 0 1 2 2 7.0 0 0"), network=True)
    assert len(deck.loads) == 1 and deck.loads[0].r == 5.0
    assert any("not merged" in why for _m, why in deck.ignored_detail)


TWO_VERTICALS = """\
GW 1 3 0 0 0 0 0 3 0.001
GW 2 3 2 0 0 2 0 3 0.001
GE
EX 0 1 2 0 1 0
{tl}
EN
"""


def test_tl_translates_z0_length_and_crossed_polarity():
    deck = parse_nec(
        TWO_VERTICALS.format(tl="TL 1 2 2 2 300 1.5 0 0 0 0"), network=True
    )
    assert deck.tls == (
        NecTL(
            wire_a=0, seg_a=2, wire_b=1, seg_b=2, z0=300.0, length=1.5,
            transposed=False, shunt_r_a=None, shunt_r_b=None,
        ),
    )  # fmt: skip
    net = deck.network()
    (br,) = net.branches
    assert br == TL(a="feed", b="tl1b", z0=300.0, length=1.5, transposed=False)
    # Both connection points are middle segments of odd wires: whole wires
    # get named, nothing splits.
    tups = deck.wire_tuples()
    assert {t[4] for t in tups if len(t) == 5} == {"feed", "tl1b"}
    assert all(t[2] == 3 for t in tups)

    # Negative z0 is NEC's crossed line — |z0| plus transposed polarity.
    deck = parse_nec(
        TWO_VERTICALS.format(tl="TL 1 2 2 2 -73 1.5 0 0 0 0"), network=True
    )
    assert deck.tls[0].z0 == 73.0 and deck.tls[0].transposed is True


def test_tl_zero_length_is_port_separation():
    deck = parse_nec(TWO_VERTICALS.format(tl="TL 1 2 2 2 300 0 0 0 0 0"), network=True)
    # Segment midpoints sit at (0,0,1.5) and (2,0,1.5) — 2 m apart.
    assert deck.tls[0].length == pytest.approx(2.0)


def test_tl_end_conductance_becomes_shunt_reactance_becomes_admittance():
    # Conductance-only end -> Shunt(r=1/G), unchanged.
    deck = parse_nec(
        TWO_VERTICALS.format(tl="TL 1 2 2 2 73 1.5 0 0 1000.0 0"), network=True
    )
    (tl,) = deck.tls
    assert tl.shunt_r_a is None and tl.shunt_r_b == pytest.approx(1e-3)
    assert tl.shunt_y_a is None and tl.shunt_y_b is None
    net = deck.network()
    assert Shunt(port="tl1b", r=1e-3) in net.branches

    # Reactive end shunt (B != 0) -> fixed 1-port Admittance, exact at every
    # frequency (issue #423). The TL is no longer dropped, and carries no
    # ignored/susceptance note.
    deck = parse_nec(
        TWO_VERTICALS.format(tl="TL 1 2 2 2 73 1.5 0 0 0 0.02"), network=True
    )
    (tl,) = deck.tls
    assert tl.shunt_r_b is None and tl.shunt_y_b == complex(0.0, 0.02)
    assert "TL" not in deck.ignored
    assert not any(m == "TL" for m, _ in deck.ignored_detail)
    net = deck.network()
    assert Admittance(ports=("tl1b",), y=((complex(0.0, 0.02),),)) in net.branches

    # Mixed G + jB -> a single complex Admittance (not Shunt + Admittance).
    deck = parse_nec(
        TWO_VERTICALS.format(tl="TL 1 2 2 2 73 1.5 0 0 1000.0 0.02"), network=True
    )
    (tl,) = deck.tls
    assert tl.shunt_r_b is None and tl.shunt_y_b == complex(1000.0, 0.02)
    net = deck.network()
    assert Admittance(ports=("tl1b",), y=((complex(1000.0, 0.02),),)) in net.branches
    assert not any(isinstance(b, Shunt) and b.port == "tl1b" for b in net.branches)


def test_nt_real_y_decomposes_into_resistive_pi():
    deck = parse_nec(
        TWO_VERTICALS.format(tl="NT 1 2 2 2 0.02 0 -0.01 0 0.015 0"), network=True
    )
    assert deck.nts == (
        NecNT(
            wire_a=0, seg_a=2, wire_b=1, seg_b=2,
            series_r=pytest.approx(100.0),
            shunt_r_a=pytest.approx(100.0),   # 1/(Y11+Y12) = 1/0.01
            shunt_r_b=pytest.approx(200.0),   # 1/(Y22+Y12) = 1/0.005
        ),
    )  # fmt: skip
    net = deck.network()
    by_kind = {(type(br).__name__,) + _branch_ports(br): br.r for br in net.branches}
    assert by_kind == {
        ("TwoPort", "feed", "nt1b"): pytest.approx(100.0),
        ("Shunt", "feed"): pytest.approx(100.0),
        ("Shunt", "nt1b"): pytest.approx(200.0),
    }


def test_nt_susceptance_becomes_admittance_and_nt_minus_one_clears():
    # An NT with susceptance is now translated to a general complex-Y branch
    # (issue #416), carrying the full 2x2 short-circuit Y (Y21 = Y12), not
    # ignored.

    deck = parse_nec(
        TWO_VERTICALS.format(tl="NT 1 2 2 2 0.02 0.01 -0.01 0 0.015 0"),
        network=True,
    )
    assert "NT" not in deck.ignored
    (nt,) = deck.nts
    assert nt.y == ((0.02 + 0.01j, -0.01 + 0j), (-0.01 + 0j, 0.015 + 0j))
    (adm,) = [b for b in deck.network().branches if isinstance(b, Admittance)]
    assert adm.ports == ("feed", "nt1b")
    # NT -1 cancels all previous network AND transmission-line data.
    deck = parse_nec(
        TWO_VERTICALS.format(tl="TL 1 2 2 2 73 1.5 0 0 0 0\nNT -1 0 0 0 0 0 0 0 0 0"),
        network=True,
    )
    assert deck.tls == () and deck.nts == ()


def test_ld_on_a_tl_segment_is_not_composed():
    deck = parse_nec(
        TWO_VERTICALS.format(tl="TL 1 2 2 2 73 1.5 0 0 0 0\nLD 0 2 2 2 0 1e-6 0"),
        network=True,
    )
    assert deck.tls != () and deck.loads == ()
    assert any("TL/NT connection" in why for _m, why in deck.ignored_detail)


def test_network_requires_network_mode_and_default_mode_is_unchanged():
    text = _dipole7("LD 0 1 2 2 5.0 0 0")
    deck = parse_nec(text)  # default: no translation
    assert deck.network_mode is False
    assert deck.loads == () and deck.ignored == ("LD",)
    # Legacy tuples still carry the ex marker and no names.
    tups = deck.wire_tuples()
    assert all(len(t) == 4 for t in tups)
    assert sum(1 for t in tups if t[3] is not None) == 1
    with pytest.raises(ValueError, match="network=True"):
        deck.network()


def test_crossing_wires_shatter_into_wire_end_junctions():
    """NEC connects SEGMENTS whose ends coincide — wire grouping is
    irrelevant — so a deck may run one wire straight through another and
    rely on the crossing carrying current (the W8IO whip's matching straps
    do). The engines junction wire ENDS only, so the import must cut both
    wires at the shared boundary; without the cut the whip benchmark's
    matching network floats and the matched impedance is garbage."""
    deck = parse_nec(
        "GW 1 4 0 0 -2 0 0 2 0.001\n"  # vertical through the origin
        "GW 2 2 0 -1 0 0 1 0 0.001\n"  # horizontal through the origin
        "GE\nEX 0 1 1 0 1 0\nEN\n"
    )
    tups = deck.wire_tuples()
    # Vertical: fed segment 1 isolated + cut at the origin boundary → 3
    # pieces; horizontal: cut at the origin → 2 pieces. Segments preserved.
    assert [t[2] for t in tups] == [1, 1, 2, 1, 1]
    assert sum(t[2] for t in tups) == 6
    # Four wire ENDS now meet at the origin — a real junction.
    ends_at_origin = sum(1 for t in tups for e in (t[0], t[1]) if e == (0.0, 0.0, 0.0))
    assert ends_at_origin == 4
    # Non-touching parallel wires are left alone.
    deck = parse_nec(
        "GW 1 3 0 0 0 0 0 3 0.001\nGW 2 3 1 0 0 1 0 3 0.001\nGE\nEX 0 1 2 0 1 0\nEN\n"
    )
    assert len(deck.wire_tuples()) == 2

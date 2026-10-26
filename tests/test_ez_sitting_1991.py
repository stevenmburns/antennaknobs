"""The ``.ez`` readings an EZNEC sitting settled (AK#1991).

On 10-12 EZNEC itself wrote its NEC-2 and NEC-5 exports of the files whose
readings the format leaves open, at the model frequency and away from it.
Those files are other people's and are not in the repo; the fixtures here are
synthetic, written by `test_ez_import_1958.ez_file`. What is pinned is what
EZNEC printed: card for card where a card carries the number (a line length,
a load's R at a frequency, a line's Y parameters, a knot), and the arithmetic
EZNEC's numbers follow where it does not.

* a split source (NEC-2/NEC-4: a source either side; NEC-5: one at the knot);
* a lossy line's loss, ∝ √(f/F) at every frequency;
* a line of length 0: the distance between its connection points over VF --
  segment centres, or knots under NEC-5 -- and EZNEC's own 0 at VF 1;
* a line in degrees: those degrees at every frequency;
* a frequency-variable R ∝ √(f/F), in loads and L networks, and an R of 0
  with a frequency, which is no variable R at all;
* a trap: R and L in series, across C;
* the extended ground ('X' at header byte 0xA2): Sommerfeld;
* NEC-5's knot for a source or a line end: the nearest one;
* files from before EZNEC 4.0 (version code 10);
* a stub or a load on a virtual segment, which must not turn the rebuilt
  virtual wire back into a real wire 100 λ out.
"""

from __future__ import annotations

import cmath
import dataclasses
import math

import numpy as np
import pytest
from test_ez_import_1958 import (
    DIPOLE,
    F0,
    PAIR,
    _open,
    _z,
    engine_block,
    ez_file,
    line_loss_block,
    lnet_block,
    transformer_block,
    virtual_block,
)

from antennaknobs import ez_import, network
from antennaknobs.engines import MomwireEngine
from antennaknobs.ez_import import EzUndefined, decode_ez, read_ez

C0 = 299_792_458.0
NEC5 = engine_block(8, "Ext NEC-5")


def _cards(imp, *kinds):
    return [ln for ln in imp.nec_text.splitlines() if ln.split(" ")[0] in kinds]


def _no_guess(imp):
    assert not any("Readings taken" in n for n in imp.notes), imp.notes


# A vee of two 10-segment wires meeting at their end 1, at (0, 0, 10).
VEE = [
    (0.0, 0.0, 10.0, 0.0, 5.0, 10.0, 0.002, 10),
    (0.0, 0.0, 10.0, 0.0, -5.0, 10.0, 0.002, 10),
]


# --------------------------------------------------------------------------
# Split sources
# --------------------------------------------------------------------------


def test_a_split_voltage_source_is_halved_either_side_under_nec2():
    """EZNEC's NEC-2 export of a 1 V split source at a wire-end junction:
    EX 0,1,1,0,.707107 and EX 0,2,1,0,-.707107."""
    imp = read_ez(ez_file(VEE, sources=((1, 0.0, 1.0, 0.0, "W"),)))
    _no_guess(imp)
    (a, b) = _cards(imp, "EX")
    assert a.split()[:4] == ["EX", "0", "1", "1"] and b.split()[:4] == [
        "EX",
        "0",
        "2",
        "1",
    ]
    assert float(a.split()[5]) == pytest.approx(0.707107, abs=1e-6)
    assert float(b.split()[5]) == pytest.approx(-0.707107, abs=1e-6)


@pytest.mark.parametrize(("kind", "ex"), [("W", 0), ("J", 4)])
def test_a_split_source_is_one_source_at_the_junction_knot_under_nec5(kind, ex):
    """EZNEC's NEC-5 export: EX 0,1,-1,0,1.414214 (W) and EX 4,1,-1,0,
    1.414214 (J) -- one source at the junction's knot, at the full
    excitation."""
    imp = read_ez(ez_file(VEE, sources=((1, 0.0, 1.0, 0.0, kind),), blocks=[NEC5]))
    _no_guess(imp)
    (card,) = _cards(imp, "EX")
    f = card.split()
    assert f[:4] == ["EX", str(ex), "1", "-1"]
    assert float(f[5]) == pytest.approx(1.414214, abs=1e-6)


def test_the_two_readings_of_a_split_source_are_one_feed():
    """Halved either side under NEC-2, whole at the knot under NEC-5: the
    vee's driving-point impedance is the same feed both ways (to the
    difference between centre and knot placement)."""
    raw = ez_file(VEE, sources=((1, 0.0, 1.0, 0.0, "W"),))
    cls2 = _open(raw)
    z2 = complex(sum(MomwireEngine(cls2(), ground=cls2.file_ground).impedance()))
    z5 = _z(_open(raw, dialect="nec5"))
    assert abs(z2 - z5) < 0.05 * abs(z5)


# --------------------------------------------------------------------------
# Lines
# --------------------------------------------------------------------------

# 40m_DW's two lossy lines: 50 Ω, VF 0.84, 0.029 dB/m at 50 MHz, crossed,
# 15.1641 m and 8.218018 m. EZNEC's NEC-2 export printed their NT cards'
# (Y11, Y12) at three frequencies -- far below the loss frequency, so the law
# shows: a constant loss would be 3.7x to 14x too lossy.
DW_LINES = (15.1641, 8.218018)
DW_PRINTED = {
    3.575: ((3.2835e-4 - 4.429e-3j, 2.6642e-4 - 2.048e-2j),
            (5.4986e-4 - 0.0222016j, 5.4252e-4 - 0.0298788j)),
    7.15: ((1.8372e-3 + 4.2817e-2j, -1.605e-3 - 4.725e-2j),
           (2.2465e-4 - 2.1e-3j, 1.6422e-4 - 2.011e-2j)),
    14.3: ((8.3817e-4 + 1.6765e-2j, 4.6192e-4 + 2.6087e-2j),
           (6.2883e-3 + 9.3662e-2j, -6.129e-3 - 9.576e-2j)),
}  # fmt: skip


def _dw_model(freq=7.15):
    lines = tuple((1, 50.0, 2, 50.0, -50.0, ln, 0.84) for ln in DW_LINES)
    return ez_file(
        PAIR,
        freq=freq,
        lines=lines,
        blocks=[line_loss_block([(0.029, 50.0)] * 2)],
    )


@pytest.mark.parametrize("f_mhz", sorted(DW_PRINTED))
def test_a_lossy_lines_loss_follows_root_f_as_eznec_prints_it(f_mhz):
    """Our two-port at each frequency against EZNEC's printed Y: its five
    printed digits are the floor (3e-4)."""
    imp = read_ez(_dw_model())
    _no_guess(imp)
    brs = [
        b
        for b in imp.deck.network().branches
        if isinstance(b, network.TouchstoneTwoPort)
    ]
    assert len(brs) == 2 and imp.deck.fixed_frequency_nts() == ()
    for br, printed in zip(brs, DW_PRINTED[f_mhz], strict=True):
        y = br.data.y_at(f_mhz * 1e6)
        for got, want in zip((y[0, 0], y[0, 1]), printed, strict=True):
            assert abs(got - want) <= 3e-4 * abs(want), (f_mhz, got, want)


def test_the_loss_law_is_root_f_from_the_loss_frequency():
    t = ez_import.EzLine(
        ez_import.EzEnd(1, 50.0), ez_import.EzEnd(2, 50.0), 50.0, False, 10.0, 0.84,
        0.029, 50.0,
    )  # fmt: skip
    gz = ez_import._line_model(t)
    db = 20.0 / math.log(10.0)
    for f in (3.575, 7.15, 14.3, 50.0, 100.0):
        assert gz(f * 1e6)[0].real * db == pytest.approx(0.029 * math.sqrt(f / 50.0))


# Two 51-segment wires 1.313688 m apart, the second running the other way,
# and a 600 Ω line between their centres at VF 0.95, length 0 ("the physical
# distance"). EZNEC printed TL 1,26,2,26,600.,1.382829 (NEC-2: centre to
# centre over VF) and TL 1,25,2,25,600.,1.41151 (NEC-5: knot 25 to knot 25
# over VF), with the current source at EX 4,1,25. 25.5 knots is a tie at
# the centre of a mirror-symmetric pair: this import writes knot 26, the
# mirror image, whose line is as long and whose answer is the same.
ZL = [
    (-6.858, 0.0, 10.668, 6.858, 0.0, 10.668, 0.0254, 51),
    (6.858, -1.313688, 10.668, -6.858, -1.313688, 10.668, 0.0254, 51),
]


def _zl(**kw):
    return ez_file(
        ZL,
        freq=28.5,
        sources=((1, 50.0, 1.0, 0.0, "I"),),
        lines=((1, 50.0, 2, 50.0, 600.0, 0.0, 0.95),),
        **kw,
    )


def test_a_physical_distance_is_centre_to_centre_over_vf_under_nec2():
    imp = read_ez(_zl())
    _no_guess(imp)
    (tl,) = _cards(imp, "TL")
    f = tl.split()
    assert f[1:5] == ["1", "26", "2", "26"]
    assert float(f[6]) == pytest.approx(1.382829, abs=2e-6)
    assert imp.deck.tls[0].length == pytest.approx(1.382829, abs=2e-6)


def test_a_physical_distance_is_knot_to_knot_over_vf_under_nec5():
    imp = read_ez(_zl(blocks=[NEC5]))
    _no_guess(imp)
    (tl,) = _cards(imp, "TL")
    f = tl.split()
    assert f[1:5] == ["1", "26", "2", "26"]
    assert float(f[6]) == pytest.approx(1.41151, abs=2e-6)
    (ex,) = _cards(imp, "EX")
    assert ex.split()[1:4] == ["4", "1", "26"]


def test_a_physical_distance_at_vf_1_is_written_0_as_eznec_writes_it():
    """EZNEC's exports write 0 for a lossless line of the physical distance
    at VF 1 (NEC's own "between the connection points"), in both spellings."""
    for blocks in ([], [NEC5]):
        raw = ez_file(
            ZL,
            freq=28.5,
            sources=((1, 50.0, 1.0, 0.0, "I"),),
            lines=((1, 50.0, 2, 50.0, 600.0, 0.0, 1.0),),
            blocks=blocks,
        )
        imp = read_ez(raw)
        (tl,) = _cards(imp, "TL")
        assert tl.split()[6] == "0"
        want = 1.313688 if not blocks else math.hypot(1.313688, 2 * 6.858 / 51)
        assert imp.deck.tls[0].length == pytest.approx(want, rel=1e-6)


# Two one-segment feed wires 0.06096 m long, 9.140952 m apart vertically,
# the upper one between two dipole arms and the lower one joined to the upper
# by a vertical wire at one end only, so its other end is free. A 50 Ω line
# at VF 0.66 of length 0 joins their centres; the current source is on the
# lower one. EZNEC printed TL 2,1,4,1,50.,13.84993 (NEC-2) and, under NEC-5,
# TL 2,-1,4,1,50.,13.85023 with EX 4,4,1: each wire's position is a tie
# between its two knots, and the free end is not the one taken.
FEED = [
    (0.0, -5.0, 9.144, 0.0, -0.03048, 9.144, 0.002, 10),
    (0.0, -0.03048, 9.144, 0.0, 0.03048, 9.144, 0.002, 1),
    (0.0, 0.03048, 9.144, 0.0, 5.0, 9.144, 0.002, 10),
    (0.0, -0.03048, 0.003048, 0.0, 0.03048, 0.003048, 0.002, 1),
    (0.0, 0.03048, 9.144, 0.0, 0.03048, 0.003048, 0.002, 20),
]


def _feed(**kw):
    return ez_file(
        FEED,
        freq=14.0,
        sources=((4, 50.0, 1.0, 0.0, "I"),),
        lines=((2, 50.0, 4, 50.0, 50.0, 0.0, 0.66),),
        **kw,
    )


def test_a_knot_tie_on_a_feed_wire_takes_the_junction_not_the_free_end():
    imp2 = read_ez(_feed())
    (tl,) = _cards(imp2, "TL")
    assert float(tl.split()[6]) == pytest.approx(13.84993, abs=2e-5)
    imp5 = read_ez(_feed(blocks=[NEC5]))
    (tl,) = _cards(imp5, "TL")
    assert tl.split()[1:5] == ["2", "-1", "4", "1"]
    assert float(tl.split()[6]) == pytest.approx(13.85023, abs=2e-5)
    (ex,) = _cards(imp5, "EX")
    assert ex.split()[1:4] == ["4", "4", "1"]


# What EZNEC's NEC-5 export named, (position %, segments) -> field. Sources
# and line ends take the nearest knot; at a tie (p·N/100 = k + 1/2) the even
# one, as in 90 % of 15 (13.5 -> 14, the banked coupled loop) and 50 % of 3
# (1.5 -> 2). The ties EZNEC broke the other way are all a mirror-symmetric
# structure's centre, where the two knots give one answer (9 of 17, 91 of
# 183, 25 of 51 written; this rule writes 8, 92, 26).
KNOTS = {
    (20.0, 10): 2,
    (20.0, 6): 1,
    (50.0, 2): 1,
    (50.0, 1): -1,
    (26.0, 27): 7,
    (17.95, 23): 4,
    (90.0, 15): 14,
    (50.0, 3): 2,
}
# ... and loads the nearest knot, a tie toward end 2 (0 % = -1). The first
# six are this sitting's; none sits in a segment's lower half, where the
# nearest knot and the end of the segment the position lands on (what AK read
# until AK#2061) part. The AK#2061 sitting's 25 % of 21 does: knot 5, a series
# load and a parallel-connected one alike.
LOAD_KNOTS = {(34.0, 50): 17, (50.0, 19): 10, (5.56, 27): 2, (0.0, 183): -1,
              (100.0, 183): 183, (0.0, 60): -1,
              (25.0, 21): 5, (50.0, 21): 11, (50.0, 11): 6}  # fmt: skip


def test_nec5s_knot_for_a_source_or_line_end_is_the_nearest():
    for (pct, n), want in KNOTS.items():
        assert (ez_import._knot(pct, n) or -1) == want, (pct, n)
    for (pct, n), want in LOAD_KNOTS.items():
        got = ez_import._load_knot(pct, n) or -1
        assert got == want, (pct, n)


def test_the_knot_rule_reaches_the_cards():
    """A source at 26 % of 27 segments: p·N/100 = 7.02, so knot 7 under NEC-5
    (EZNEC's EX field), where NEC-2's segment is 8. A load there sits on knot
    7 too, the nearest one (AK#2061: AK put it at 8 until the sitting showed
    loads take the nearest knot)."""
    wires = [
        (0.0, 0.0, 10.0, 0.0, 5.0, 10.0, 0.002, 27),
        (0.0, 0.0, 10.0, 0.0, -5.0, 10.0, 0.002, 27),
    ]
    raw = ez_file(
        wires,
        sources=((1, 26.0, 1.0, 0.0, "V"),),
        loads=({"wire": 1, "pct": 26.0, "z": (5.0, 0.0)},),
        blocks=[NEC5],
    )
    imp = read_ez(raw)
    (ex,) = _cards(imp, "EX")
    assert ex.split()[2:4] == ["1", "7"]
    (ld,) = _cards(imp, "LD")
    assert ld.split()[2:4] == ["1", "7"]
    assert read_ez(raw, reading="nec2").deck.feeds[0].seg == 8


# 4sqtl's lines in degrees, which EZNEC's NEC-2 export printed as TL lengths
# (electrical metres) at 7.15 MHz and at twice that: the degrees are held,
# so the metres halve.
DEGREES = {90.0: (10.48225, 5.241127), 270.0: (31.44676, 15.72338)}


@pytest.mark.parametrize("deg", sorted(DEGREES))
def test_a_line_in_degrees_holds_its_degrees_at_every_frequency(deg):
    raw = ez_file(PAIR, freq=7.15, lines=((1, 50.0, 2, 50.0, 50.0, -deg, 1.0),))
    imp = read_ez(raw)
    _no_guess(imp)
    (br,) = [
        b
        for b in imp.deck.network().branches
        if isinstance(b, network.TouchstoneTwoPort)
    ]
    for f_mhz, printed in zip((7.15, 14.3), DEGREES[deg], strict=True):
        bl = 2 * math.pi * f_mhz * 1e6 / C0 * printed
        y11, y12 = -1j / (50.0 * math.tan(bl)), 1j / (50.0 * math.sin(bl))
        # Y11 is ~0 at 90° and 270°: compared against |Y12|.
        np.testing.assert_allclose(
            br.data.y_at(f_mhz * 1e6),
            [[y11, y12], [y12, y11]],
            rtol=2e-5,
            atol=2e-5 * abs(y12),
        )


def test_a_stub_in_degrees_holds_its_degrees_too():
    """A shorted 90° stub is an open at every frequency: across the feed it
    changes nothing, at the model frequency or at 1.3 times it."""
    raw = ez_file(DIPOLE, lines=((1, 50.0, -1, 0.0, 50.0, -90.0, 0.66),))
    plain = _open(ez_file(DIPOLE))
    for f in (F0, 1.3 * F0):
        assert _z(_open(raw), f) == pytest.approx(_z(plain, f), rel=1e-6), f


def test_a_line_in_degrees_follows_frequency_in_a_solve():
    """Solved at 2f, a 90° line read at f is the line read at 2f (EZNEC's
    own behaviour), not the same metres (a 180° line there)."""
    at_f = _open(
        ez_file(PAIR, freq=7.15, lines=((1, 50.0, 2, 50.0, 50.0, -90.0, 1.0),))
    )
    at_2f = _open(
        ez_file(PAIR, freq=14.3, lines=((1, 50.0, 2, 50.0, 50.0, -90.0, 1.0),))
    )
    metres = _open(
        ez_file(PAIR, freq=7.15, lines=((1, 50.0, 2, 50.0, 50.0, 10.48225, 1.0),))
    )
    z, z2 = _z(at_f, 14.3), _z(at_2f, 14.3)
    assert z == pytest.approx(z2, rel=1e-9)
    assert abs(_z(metres, 14.3) - z) > 0.1 * abs(z)


# --------------------------------------------------------------------------
# Loads and L networks
# --------------------------------------------------------------------------


def _load_z(raw, f_mhz):
    (ld,) = read_ez(raw).deck.loads
    return ld.custom.z(f_mhz * 1e6)


def test_a_variable_r_is_root_f_as_eznec_prints_it():
    """4.6.10b: series R 0.5 Ω at 4 MHz with 9.167461 µH, model at 3.55 MHz.
    EZNEC's NEC-2 exports printed LD 0 with R = 0.4710361 at 3.55 MHz and
    0.6666146 at 7.11 MHz."""
    load = {"wire": 1, "pct": 75.0, "rlc": ("S", 0.5, 9.167461e-6, 0.0, 4.0)}
    raw = ez_file(DIPOLE, freq=3.55, loads=(load,), load_type="R")
    _no_guess(read_ez(raw))
    for f, r in ((3.55, 0.4710361), (7.11, 0.6666146)):
        assert _load_z(raw, f).real == pytest.approx(r, rel=1e-6)


def test_a_trap_is_r_and_l_across_c_as_eznec_prints_it():
    """5-2: trap R 1 Ω at 28 MHz, 0.62 µH, 52.1 pF (as singles), model at
    14.175 MHz. EZNEC printed LD 4 1.286176+74.23768j there and
    1419.556-3897.852j at 28.35 MHz."""
    rlc = ("T", 1.0, 6.2e-7, 5.21e-11, 28.0)
    stored = (1.286176, 74.23768)
    load = {"wire": 1, "pct": 75.0, "z": stored, "rlc": rlc}
    raw = ez_file(DIPOLE, freq=14.175, loads=(load,), load_type="R")
    _no_guess(read_ez(raw))
    for f, want in ((14.175, 1.286176 + 74.23768j), (28.35, 1419.556 - 3897.852j)):
        assert _load_z(raw, f) == pytest.approx(want, rel=2e-6)


def test_an_r_of_zero_with_a_frequency_is_a_plain_rlc_load():
    """4.15.1c1: a series load of R 0 at 14 MHz and 36.81 pF, which the
    importer used to refuse. EZNEC printed LD 0 R=0 L=0 C=3.681E-11 at every
    frequency: the deck's own series RLC."""
    load = {"wire": 1, "pct": 75.0, "rlc": ("S", 0.0, 0.0, 3.681e-11, 14.0)}
    imp = read_ez(ez_file(DIPOLE, freq=14.175, loads=(load,), load_type="R"))
    _no_guess(imp)
    (ld,) = _cards(imp, "LD")
    f = ld.split()
    assert f[1] == "0" and float(f[7]) == pytest.approx(3.681e-11)
    (br,) = [b for b in imp.deck.network().branches if isinstance(b, network.Load)]
    assert br.r is None and br.c == pytest.approx(3.681e-11)


def test_an_l_networks_variable_r_is_root_f_as_eznec_prints_it():
    """8-3-2: series 1.56 Ω + 13.275 µH, shunt 0.05 Ω + 918.9 pF, both R at
    4 MHz, model at 3.75 MHz. EZNEC printed the NT's Y11, Y12, Y22."""
    rlc = [((1.56, 1.3275e-5, 0.0, 4.0, "S"), (0.05, 0.0, 9.189e-10, 4.0, "S"))]
    raw = ez_file(
        PAIR,
        freq=3.75,
        lnet_type="R",
        blocks=[lnet_block([((1, 50.0), (2, 50.0), 0j, 0j)], rlc)],
        counts=(0, 0, 1, 0),
    )
    imp = read_ez(raw)
    _no_guess(imp)
    (br,) = [
        b
        for b in imp.deck.network().branches
        if isinstance(b, network.TouchstoneTwoPort)
    ]
    printed = {
        3.75: (1.5439e-05 - 0.003197j, -1.544e-05 + 0.003197j, 3.8133e-05 + 0.018454j),
        7.5: (5.4584e-06 - 0.001599j, -5.458e-06 + 0.0015985j, 0.00013383 + 0.041703j),
    }
    for f, want in printed.items():
        y = br.data.y_at(f * 1e6)
        for got, w in zip((y[0, 0], y[0, 1], y[1, 1]), want, strict=True):
            assert abs(got - w) <= 4e-4 * abs(w), (f, got, w)


# --------------------------------------------------------------------------
# Ground
# --------------------------------------------------------------------------


def test_the_extended_ground_is_sommerfeld_in_every_spelling():
    """'X' at header byte 0xA2 is what EZNEC's exports follow to NEC-4's
    GN 3 (where 'H' or a blank gives GN 2): the Sommerfeld ground."""
    raw = ez_file(DIPOLE, ground="R", hag="X")
    imp = read_ez(raw)
    _no_guess(imp)
    assert "GN 2 " in imp.nec_text and imp.ground == ("finite", 13.0, 0.005)
    imp4 = read_ez(raw, reading="nec4")
    assert "GN 3 " in imp4.nec_text and imp4.ground == ("finite", 13.0, 0.005)
    assert "GN 0 " in read_ez(raw, reading="nec5").nec_text
    plain = _open(ez_file(DIPOLE, ground="R", hag="H"))
    assert _z(_open(raw, dialect="nec4")) == pytest.approx(_z(plain), rel=1e-9)


def test_the_extended_ground_under_a_buried_wire_is_still_a_reading():
    buried = [(0.0, -5.15, -0.5, 0.0, 5.15, -0.5, 0.002, 21)]
    raw = ez_file(buried, ground="R", hag="X")
    with pytest.raises(EzUndefined, match="buried") as err:
        read_ez(raw)
    assert ez_import.ACCEPT_GUESSES_ENV in str(err.value)
    imp = read_ez(raw, accept_guesses=True)
    assert any("Readings taken" in n and "buried" in n for n in imp.notes)


# --------------------------------------------------------------------------
# Version code 10
# --------------------------------------------------------------------------


def _v10(raw: bytes) -> bytes:
    """``raw`` as EZNEC before 4.0 wrote it: version code 10, no program
    word, and no records 3 and 4 after the table."""
    b = bytearray(raw[: len(raw) - 340])
    b[0x72:0x74] = (10).to_bytes(2, "little")
    b[0x90:0x94] = bytes(4)
    return bytes(b)


def test_a_version_10_file_reads_as_its_eznec_7_save_as():
    """The frame ends with the table (510 bytes for two records), a blank
    load type is R + jX and a blank load connection is series. On the six
    such files at the sitting, each read as the model of the copy EZNEC 7
    saved, card for card; so does this one."""
    load = {"wire": 1, "pct": 75.0, "z": (5.0, -40.0)}
    v7 = ez_file(PAIR, loads=(load,), pgm=0, vercode=45)
    v10 = _v10(ez_file(PAIR, loads=({**load, "conn": "\0"},), pgm=0, load_type=" "))
    assert len(v10) == 170 + 2 * 170
    a, b = decode_ez(v10), decode_ez(v7)
    assert a.version == (10, 0)
    skip = {"version"}
    for f in dataclasses.fields(a):
        if f.name not in skip:
            assert getattr(a, f.name) == getattr(b, f.name), f.name
    for reading in ("nec2", "nec5"):
        assert (
            read_ez(v10, reading=reading).nec_text
            == read_ez(v7, reading=reading).nec_text
        )
    _no_guess(read_ez(v10))


def test_a_version_10_file_with_blank_display_fields_only_warns():
    raw = bytearray(_v10(ez_file(DIPOLE, pgm=0)))
    raw[0x7A] = 0  # plot type
    raw[0x76:0x78] = b"  "  # plot polarisation 8224
    imp = read_ez(bytes(raw))
    assert any("Display settings" in n for n in imp.notes)


# --------------------------------------------------------------------------
# A stub or a load on a virtual segment
# --------------------------------------------------------------------------

VWIRE = (100.0, 100.0, 100.0, 100.0, 100.0, 101.0, 0.001, 2)


def _virtual(freq=F0, **kw):
    """A current source on virtual segment 1 drives a 1:1 transformer onto
    the dipole's centre (Z1/500 = 0.1 Ω in series)."""
    return ez_file(
        [*DIPOLE, VWIRE],
        freq=freq,
        sources=((2, 25.0, 1.0, 0.0, "I"),),
        blocks=[
            transformer_block([((2, 25.0), (1, 50.0), 50.0, 50.0)]),
            virtual_block([1, 2], 2),
        ],
        counts=(1, 0, 0, 2),
        **kw,
    )


def test_a_stub_on_a_virtual_segment_keeps_the_wire_virtual():
    """Before AK#1991 the stub's placeholder load made the reader take the
    rebuilt wire for a real one, 100 λ out at the IMPORT frequency, so the
    answer moved with it. Now the wire is nodes, and the open stub sits
    across the source with the transformer."""
    stub = ((2, 25.0, -2, 0.0, 50.0, 2.0, 0.8),)
    imp = read_ez(_virtual(lines=stub))
    assert imp.deck.virtual_segment_wires == frozenset({1})
    assert len(imp.deck.wire_tuples(specs=True)) == 1
    z_dip = _z(_open(ez_file(DIPOLE)))
    bl = 2 * math.pi * F0 * 1e6 / (0.8 * C0) * 2.0
    y_stub = 1j * math.tan(bl) / 50.0
    want = 1.0 / (y_stub + 1.0 / (z_dip + 0.1))
    got = _z(_open(_virtual(lines=stub)))
    assert got == pytest.approx(want, rel=1e-6)
    moved = _open(_virtual(freq=0.6 * F0, lines=stub))
    assert _z(moved, F0) == pytest.approx(got, rel=1e-12)


def test_a_load_on_a_virtual_segment_keeps_the_wire_virtual_and_is_a_reading(
    monkeypatch,
):
    """No file at the sitting had a load on a virtual segment, so how it
    connects there is a reading: across the segment's node, in parallel with
    what connects there. Taken on request, the wire stays nodes, and the
    answer does not move with the import frequency."""
    load = ({"wire": 2, "pct": 25.0, "z": (50.0, 0.0)},)
    with pytest.raises(EzUndefined, match="virtual segment"):
        read_ez(_virtual(loads=load))
    imp = read_ez(_virtual(loads=load), accept_guesses=True)
    assert imp.deck.virtual_segment_wires == frozenset({1})
    assert any("Readings taken" in n and "virtual segment" in n for n in imp.notes)
    z_dip = _z(_open(ez_file(DIPOLE)))
    monkeypatch.setenv(ez_import.ACCEPT_GUESSES_ENV, "1")
    got = _z(_open(_virtual(loads=load)))
    assert got == pytest.approx(1.0 / (1.0 / 50.0 + 1.0 / (z_dip + 0.1)), rel=1e-6)
    moved = _open(_virtual(freq=0.6 * F0, loads=load))
    assert _z(moved, F0) == pytest.approx(got, rel=1e-12)
    # Alone on a segment nothing else uses, it is a node to common: no
    # effect, and nothing the solver refuses.
    alone = ({"wire": 2, "pct": 75.0, "z": (50.0, 0.0)},)
    assert _z(_open(_virtual(loads=alone))) == pytest.approx(z_dip + 0.1, rel=1e-6)


# --------------------------------------------------------------------------
# What stays a reading
# --------------------------------------------------------------------------


def test_the_readings_that_remain_are_refused_by_default():
    rev = ez_file(
        PAIR,
        blocks=[transformer_block([((1, 50.0), (2, 50.0), 50.0, -200.0)])],
        counts=(1, 0, 0, 0),
    )
    lap = ez_file(
        DIPOLE,
        loads=(
            {
                "wire": 1,
                "pct": 75.0,
                "laplace": ((5.0, 2e-6, 0, 0, 0, 0), (1, 0, 0, 0, 0, 0)),
            },
        ),
        load_type="L",
    )
    for raw, named in ((rev, "reversed"), (lap, "Laplace")):
        with pytest.raises(EzUndefined, match=named):
            read_ez(raw)
        read_ez(raw, accept_guesses=True)


def test_no_settled_reading_is_listed_as_a_guess():
    """With guesses accepted, the readings the sitting settled are not in
    the notes' list of readings taken: they are the reading."""
    trap = {"wire": 1, "pct": 75.0, "rlc": ("T", 2.0, 2e-6, 60e-12, 7.0)}
    raw = ez_file(
        VEE,
        sources=((1, 0.0, 1.0, 0.0, "W"),),
        loads=(trap,),
        load_type="R",
        ground="R",
        hag="X",
    )
    _no_guess(read_ez(raw, accept_guesses=True))
    assert cmath.isfinite(_z(_open(raw)))

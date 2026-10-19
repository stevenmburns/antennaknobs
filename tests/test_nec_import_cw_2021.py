"""AK#2021 part 2: NEC-4 and NEC-5's catenary wire, ``CW ITG NS X1 Y1 Z1 X2
Y2 Z2 RAD ICAT RHM ZM``, imported as NS straight 1-segment pieces.

The expected numbers below are segment centres and lengths that NEC-4.2 and
NEC-5 computed for these same synthetic decks, run as black boxes. The two
engines agreed with each other on every deck to the printed digits (5
decimals), so the tolerance is half the last printed digit plus a hair.
They are written here as numbers, not as printouts.
"""

import itertools
import math

import pytest

from antennaknobs.file_designs import builder_from_file
from antennaknobs.nec_import import GeometryLimitError, GeometryLimits, parse_nec

TOL = 6e-6


def _deck(card: str, extra: str = "") -> str:
    return f"CE\n{card}\n{extra}GE 0\nEX 0 1 1 0 1 0\nFR 0 1 0 0 299.8 0\nEN\n"


def _pieces(deck):
    """``(centre, length)`` per segment, in deck order."""
    out = []
    for w in deck.wires:
        for j in range(w.n_seg):
            a = [w.p1[i] + (w.p2[i] - w.p1[i]) * j / w.n_seg for i in range(3)]
            b = [w.p1[i] + (w.p2[i] - w.p1[i]) * (j + 1) / w.n_seg for i in range(3)]
            out.append(([(a[i] + b[i]) / 2 for i in range(3)], math.dist(a, b)))
    return out


def _check(card, centres, lengths=None):
    got = _pieces(parse_nec(_deck(card), name="t"))
    assert len(got) == len(centres)
    for (c, _), want in zip(got, centres, strict=True):
        assert c == pytest.approx(want, abs=TOL)
    if lengths is not None:
        assert [L for _, L in got] == pytest.approx(lengths, abs=TOL)


def _mirror(half):
    """The ten centres of a span symmetric about x = 0, from its first five."""
    return list(half) + [(-x, y, z) for x, y, z in reversed(half)]


def test_icat1_point_at_midspan():
    # Through (u = 20, z = 8): the lowest point of a symmetric span.
    _check(
        "CW 1 10 -20 0 15 20 0 15 0.001 1 20 8",
        _mirror(
            [
                (-18.19635, 0.0, 13.82245),
                (-14.47229, 0.0, 11.66989),
                (-10.52739, 0.0, 9.96082),
                (-6.39888, 0.0, 8.76908),
                (-2.14743, 0.0, 8.1557),
            ]
        ),
        [4.30802, 4.30749, 4.30693, 4.30644, 4.30614]
        + [4.30614, 4.30644, 4.30693, 4.30749, 4.30802],
    )


def test_icat1_rhm_is_measured_from_end_1():
    # Unequal end heights: the point (u = 10 from END 1, z = 8) is not where
    # it would be from end 2, so the curve pins which end RHM counts from.
    _check(
        "CW 1 10 -20 0 15 20 0 20 0.001 1 10 8",
        [
            (-18.24412, 0.0, 13.41621),
            (-14.51973, 0.0, 10.52402),
            (-10.37915, 0.0, 8.28674),
            (-5.8878, 0.0, 6.91493),
            (-1.21014, 0.0, 6.57916),
            (3.42123, 0.0, 7.32712),
            (7.79169, 0.0, 9.05594),
            (11.77511, 0.0, 11.56949),
            (15.33892, 0.0, 14.66162),
            (18.5084, 0.0, 18.16411),
        ],
    )


def test_icat2_sag_below_the_chord_with_unequal_ends():
    # ZM below the straight line between the ends, not below end 1.
    _check(
        "CW 1 10 -20 0 15 20 0 20 0.001 2 20 1.5",
        [
            (-17.97729, 0.0, 14.98113),
            (-13.93222, 0.0, 15.00417),
            (-9.88966, 0.0, 15.14866),
            (-5.85324, 0.0, 15.41421),
            (-1.82654, 0.0, 15.80011),
            (2.18695, 0.0, 16.30533),
            (6.18382, 0.0, 16.92855),
            (10.16081, 0.0, 17.66817),
            (14.1148, 0.0, 18.52232),
            (18.04283, 0.0, 19.48889),
        ],
    )


def test_icat2_diagonal_span_measures_horizontal_distance():
    _check(
        "CW 1 10 -10 -10 15 10 10 15 0.001 2 10 1.5",
        [
            (-9.01264, -9.01264, 14.70726),
            (-7.0296, -7.0296, 14.18493),
            (-5.03187, -5.03187, 13.79028),
            (-3.02346, -3.02346, 13.52577),
            (-1.00855, -1.00855, 13.39309),
            (1.00855, 1.00855, 13.39309),
            (3.02346, 3.02346, 13.52577),
            (5.03187, 5.03187, 13.79028),
            (7.0296, 7.0296, 14.18493),
            (9.01264, 9.01264, 14.70726),
        ],
    )


def test_icat2_negative_sag_arches_in_equal_horizontal_steps():
    # An arch is cut into equal HORIZONTAL steps (x centres exactly 4 m
    # apart), which is what both engines do; a sag is cut by arc length.
    _check(
        "CW 1 10 -20 0 15 20 0 15 0.001 2 20 -1.5",
        _mirror(
            [
                (-18.0, 0.0, 15.27032),
                (-14.0, 0.0, 15.75065),
                (-10.0, 0.0, 16.11051),
                (-6.0, 0.0, 16.35024),
                (-2.0, 0.0, 16.47005),
            ]
        ),
        [4.03637, 4.02199, 4.01121, 4.00404, 4.00045]
        + [4.00045, 4.00404, 4.01121, 4.02199, 4.03637],
    )


def test_icat2_point_beyond_the_span():
    # RHM past end 2: a positive ZM there is met by an arch, as the engines
    # build it.
    _check(
        "CW 1 10 -20 0 15 20 0 15 0.001 2 45 1.5",
        _mirror(
            [
                (-18.0, 0.0, 15.47747),
                (-14.0, 0.0, 16.32495),
                (-10.0, 0.0, 16.95851),
                (-6.0, 0.0, 17.37992),
                (-2.0, 0.0, 17.59033),
            ]
        ),
    )


def test_icat3_length_and_equal_arc_spacing():
    _check(
        "CW 1 10 -20 0 15 20 0 15 0.001 3 41.5 0",
        _mirror(
            [
                (-18.10137, 0.0, 14.16429),
                (-14.24021, 0.0, 12.65673),
                (-10.26279, 0.0, 11.49221),
                (-6.19564, 0.0, 10.69846),
                (-2.0717, 0.0, 10.29608),
            ]
        ),
    )
    # Equal ARC length, so the chords are shortest where the curve bends most.
    deck = parse_nec(_deck("CW 1 10 -20 0 15 20 0 15 0.001 3 41.5 0"), name="t")
    total = 0.0
    for w in deck.wires:
        total += math.dist(w.p1, w.p2)
    assert total == pytest.approx(41.4856, abs=2e-4)  # chords, a hair under 41.5


def test_icat3_unequal_ends():
    _check(
        "CW 1 10 -20 0 15 20 0 20 0.001 3 45 0",
        [
            (-18.14411, 0.0, 13.73059),
            (-14.27604, 0.0, 11.45904),
            (-10.11869, 0.0, 9.7871),
            (-5.74443, 0.0, 8.8352),
            (-1.27246, 0.0, 8.68556),
            (3.15314, 0.0, 9.35212),
            (7.4004, 0.0, 10.77493),
            (11.3789, 0.0, 12.8433),
            (15.04683, 0.0, 15.43033),
            (18.40041, 0.0, 18.41884),
        ],
        [4.49699, 4.49584, 4.49462, 4.49373, 4.49357]
        + [4.49424, 4.49539, 4.49659, 4.4976, 4.49834],
    )


@pytest.mark.parametrize("length", ["39", "40"])
def test_icat3_no_longer_than_the_chord_is_the_straight_wire(length):
    deck = parse_nec(_deck(f"CW 1 10 -20 0 15 20 0 15 0.001 3 {length} 5"), name="t")
    (w,) = deck.wires
    assert (w.n_seg, w.p1, w.p2) == (10, (-20.0, 0.0, 15.0), (20.0, 0.0, 15.0))


def test_icat_in_a_float_slot():
    a = _pieces(parse_nec(_deck("CW 1 10 -20 0 15 20 0 15 0.001 2 20 1.5"), name="t"))
    b = _pieces(parse_nec(_deck("CW 1 10 -20 0 15 20 0 15 0.001 2.0 20 1.5"), name="t"))
    assert a == b


@pytest.mark.parametrize(
    ("card", "match"),
    [
        ("CW 1 10 -20 0 15 20 0 15 0.001 1.5 20 8", "ICAT must be 1"),
        ("CW 1 10 -20 0 15 20 0 15 0.001 0 20 8", "ICAT must be 1"),
        ("CW 1 10 -20 0 15 20 0 15 0.001 4 20 8", "ICAT must be 1"),
        ("CW 1 10 0 0 5 0 0 15 0.001 3 12 0", "one above the other"),
        ("CW 1 10 -20 0 15 20 0 15 0.001 2 20 0", "on the straight line"),
        ("CW 1 10 -20 0 15 20 0 20 0.001 1 10 16.25", "on the straight line"),
        ("CW 1 10 -20 0 15 20 0 15 0.001 2 0 1.5", "at an end"),
        ("CW 1 10 -10 0 10 10 0 10 0.001 1 20 8", "at an end"),
        ("CW 1 10 -20 0 15 20 0 15 0 2 20 1.5", "radius must be > 0"),
        ("CW 1 0 -20 0 15 20 0 15 0.001 2 20 1.5", "segment count"),
    ],
)
def test_refused_by_name(card, match):
    with pytest.raises(ValueError, match=match):
        parse_nec(_deck(card), name="t")


def test_radius_is_constant_and_tag_kept():
    deck = parse_nec(
        "CE\nCW 7 10 -20 0 15 20 0 15 0.002 1 20 8\nGE 0\nEX 0 7 5 0 1 0\nEN\n",
        name="t",
    )
    assert {w.radius for w in deck.wires} == {0.002}
    assert {w.tag for w in deck.wires} == {7}
    assert sum(w.n_seg for w in deck.wires) == 10


def test_pieces_join_end_to_end():
    deck = parse_nec(_deck("CW 1 10 -20 0 15 20 0 20 0.001 1 10 8"), name="t")
    ws = deck.wires
    assert ws[0].p1 == (-20.0, 0.0, 15.0)
    assert ws[-1].p2 == (20.0, 0.0, 20.0)
    for a, b in itertools.pairwise(ws):
        assert a.p2 == b.p1


def test_gs_scales_a_catenary_like_any_wire():
    card = "CW 1 10 -20 0 15 20 0 15 0.001 1 20 8"
    plain = _pieces(parse_nec(_deck(card), name="t"))
    scaled = _pieces(parse_nec(_deck(card, "GS 0 0 0.3048\n"), name="t"))
    for (c, L), (cs, Ls) in zip(plain, scaled, strict=True):
        assert cs == pytest.approx([0.3048 * v for v in c], abs=1e-12)
        assert Ls == pytest.approx(0.3048 * L, rel=1e-12)


def test_gm_copies_a_catenary_with_its_tag():
    deck = parse_nec(
        _deck("CW 1 10 -20 0 15 20 0 15 0.001 2 20 1.5", "GM 1 1 0 0 0 0 0 5 1\n"),
        name="t",
    )
    assert sorted({w.tag for w in deck.wires}) == [1, 2]
    lower = [w for w in deck.wires if w.tag == 1]
    upper = [w for w in deck.wires if w.tag == 2]
    for a, b in zip(lower, upper, strict=True):
        assert b.p1[2] == pytest.approx(a.p1[2] + 5.0)


def test_sy_symbols_in_the_fields():
    plain = _pieces(
        parse_nec(_deck("CW 1 10 -20 0 15 20 0 15 0.001 2 20 1.5"), name="t")
    )
    sy = _pieces(
        parse_nec(
            "CE\nSY h=15, s=1.5, ic=2\nCW 1 10 -20 0 h 20 0 h 0.001 ic 20 s\n"
            "GE 0\nEX 0 1 1 0 1 0\nEN\n",
            name="t",
        )
    )
    assert sy == plain


def test_a_feed_on_a_catenary_segment():
    deck = parse_nec(
        "CE\nCW 1 11 -20 0 15 20 0 15 0.001 2 20 1.5\nGE 0\nEX 0 1 6 0 1 0\nEN\n",
        name="t",
    )
    # EX's segment 6 is the sixth piece, the centre of the 11.
    (feed,) = deck.feeds
    assert (feed.wire, feed.seg) == (5, 1)
    assert deck.wires[feed.wire].p1[0] == pytest.approx(-deck.wires[feed.wire].p2[0])


def test_geometry_limits_count_catenary_segments():
    limits = GeometryLimits(max_segments=50, max_wires=1000)
    with pytest.raises(GeometryLimitError):
        parse_nec(
            _deck("CW 1 60 -20 0 15 20 0 15 0.001 2 20 1.5"), name="t", limits=limits
        )


def test_builder_from_file_imports_a_catenary(tmp_path):
    path = tmp_path / "cat.nec"
    path.write_text(
        "CM synthetic catenary dipole\nCE\n"
        "CW\t1\t21\t-20\t0\t15\t20\t0\t15\t0.001\t2\t20\t1.5\n"
        "GE\t0\nEX\t0\t1\t11\t0\t1\t0\nFR\t0\t1\t0\t0\t3.6\t0\nEN\n"
    )
    builder_from_file(str(path))

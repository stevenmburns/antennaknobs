"""NEC-5's UM card (upper medium): ``UM 0 0 0 0 EPSR SIG`` sets the medium the
structure sits in. Every solver here models the structure in air, so a UM
that says air is read as a no-op, and any other medium is refused by name.
Synthetic decks only."""

import pytest

from antennaknobs.nec_import import parse_nec

BODY = "CE\nGW 1 11 0 0 0 0 0 5 0.001\nGE 0\n{um}EX 0 1 6 0 1 0\nFR 0 1 0 0 14 0\nEN\n"


def _geometry(deck):
    return [(w.tag, w.n_seg, w.p1, w.p2, w.radius) for w in deck.wires]


@pytest.mark.parametrize(
    "um",
    [
        "UM 0 0 0 0 1 0\n",
        "UM 0 0 0 0 1.0 0.0\n",
        "UM,0,0,0,0,1,0\n",
        "UM 0 0 0 0 1.0000000001 0 ! air\n",
    ],
)
def test_air_is_a_no_op(um):
    plain = parse_nec(BODY.format(um=""), name="t")
    with_um = parse_nec(BODY.format(um=um), name="t")
    assert _geometry(with_um) == _geometry(plain)
    assert with_um.feeds == plain.feeds
    assert with_um.freq_mhz == plain.freq_mhz
    assert "UM" not in with_um.ignored


def test_air_by_sy_symbols():
    deck = parse_nec(
        "CE\nSY er=1, s=0\nGW 1 11 0 0 0 0 0 5 0.001\nGE 0\nUM 0 0 0 0 er s\n"
        "EX 0 1 6 0 1 0\nEN\n",
        name="t",
    )
    assert len(deck.wires) == 1


@pytest.mark.parametrize(
    ("um", "shown"),
    [
        ("UM 0 0 0 0 14 0.006\n", "UM εr=14, σ=0.006"),
        ("UM 0 0 0 0 2.25 0\n", "UM εr=2.25, σ=0"),
        ("UM 0 0 0 0 1 0.001\n", "UM εr=1, σ=0.001"),
        ("UM 0 0 0 0 1 -0.5\n", "UM εr=1, σ=-0.5"),
        ("UM\n", "UM εr=0, σ=0"),
    ],
)
def test_any_other_medium_is_refused_by_name(um, shown):
    with pytest.raises(ValueError) as err:
        parse_nec(BODY.format(um=um), name="t")
    msg = str(err.value)
    assert "t, line 4:" in msg
    assert "lossy or dielectric medium" in msg
    assert shown in msg
    assert "remove the card, or set it to 1 0" in msg

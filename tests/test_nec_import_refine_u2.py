"""U2 of docs/plan-buried-scope-closure.md: the refinement path for an imported deck.

A catalog design refines through its own mesh knobs, but an imported deck's only
mesh is its GW counts. `NecDeck.refined(r)` multiplies every wire's segment
count by an ODD factor and moves every reference with the mesh, so a ladder can
be run on a deck the way `nominal_nsegs` runs one on a Builder. Every segment is
divided, the source region included: momwire#1027 showed that a ladder holding
the fed segment fixed converges in the far mesh alone.

The gate is exactness, not a physics number. A deck refined by 3 must be the
same deck as the one a person would write at three times the segments: same
wires, same feeds, loads, TL and NT ends, same wire tuples. Odd factors are what
make that true for both source spellings. An old segment's centre is the centre
of its middle piece, and an old knot is still a knot (antennaknobs#1456).
"""

from __future__ import annotations

import pytest

from antennaknobs.cli import cli
from antennaknobs.nec_import import parse_nec


def _pair(authored: str, by_hand: str, r: int = 3):
    a = parse_nec(authored, network=True).refined(r)
    b = parse_nec(by_hand, network=True)
    return a, b


def _same(a, b):
    assert a.wires == b.wires
    assert a.feeds == b.feeds
    assert a.loads == b.loads
    assert a.tls == b.tls
    assert a.nts == b.nts
    assert a.wire_tuples(specs=True) == b.wire_tuples(specs=True)


def test_a_centre_feed_stays_the_centre_gap():
    _same(
        *_pair(
            "GW 1 11 0 0 0 0 0 10 .001\nGE 0\nEX 0 1 6 0 1 0\nEN\n",
            "GW 1 33 0 0 0 0 0 10 .001\nGE 0\nEX 0 1 17 0 1 0\nEN\n",
        )
    )


def test_an_off_centre_feed_and_a_lumped_load_move_to_their_middle_pieces():
    _same(
        *_pair(
            "GW 1 10 0 0 0 10 0 0 .001\nGE 0\nEX 0 1 3 0 1 0\nLD 0 1 7 7 50 0 0\nEN\n",
            "GW 1 30 0 0 0 10 0 0 .001\nGE 0\nEX 0 1 8 0 1 0\nLD 0 1 20 20 50 0 0\nEN\n",
        )
    )


def test_a_lumped_load_stays_one_element():
    a = parse_nec(
        "GW 1 10 0 0 0 10 0 0 .001\nGE 0\nEX 0 1 3 0 1 0\nLD 0 1 7 7 50 0 0\nEN\n",
        network=True,
    )
    assert len(a.refined(9).loads) == len(a.loads) == 1


TWO_VERTICALS = (
    "GW 1 3 0 0 0 0 0 3 0.001\nGW 2 3 2 0 0 2 0 3 0.001\nGE\nEX 0 1 2 0 1 0\n{tl}\nEN\n"
)
TWO_VERTICALS_X3 = (
    "GW 1 9 0 0 0 0 0 3 0.001\nGW 2 9 2 0 0 2 0 3 0.001\nGE\nEX 0 1 5 0 1 0\n{tl}\nEN\n"
)


@pytest.mark.parametrize(
    "card, card_x3",
    [
        ("TL 1 2 2 2 300 1.5 0 0 0 0", "TL 1 5 2 5 300 1.5 0 0 0 0"),
        ("TL 1 2 2 2 300 0 0 0 0 0", "TL 1 5 2 5 300 0 0 0 0 0"),
        ("NT 1 2 2 2 0.02 0 -0.01 0 0.015 0", "NT 1 5 2 5 0.02 0 -0.01 0 0.015 0"),
    ],
)
def test_tl_and_nt_ends_move_with_the_mesh(card, card_x3):
    """The zero-length TL row matters: its resolved length is the distance
    between the two segment midpoints, and an odd factor keeps both midpoints
    where they were."""
    _same(*_pair(TWO_VERTICALS.format(tl=card), TWO_VERTICALS_X3.format(tl=card_x3)))


@pytest.mark.parametrize(
    "ex, ex_x3",
    [
        ("EX 4 1 6 1 1 0", "EX 4 1 16 1 1 0"),  # end 1 of segment 6 → the same knot
        ("EX 4 1 6 2 1 0", "EX 4 1 18 2 1 0"),  # end 2 of segment 6 → the same knot
    ],
)
def test_a_knot_source_keeps_its_knot(ex, ex_x3):
    _same(
        *_pair(
            f"GW 1 11 0 0 -5 0 0 5 .001\nGE 0\n{ex}\nEN\n",
            f"GW 1 33 0 0 -5 0 0 5 .001\nGE 0\n{ex_x3}\nEN\n",
        )
    )


@pytest.mark.parametrize("r", [0, 2, 4, -3])
def test_even_or_non_positive_factors_are_refused(r):
    deck = parse_nec(
        "GW 1 11 0 0 0 0 0 10 .001\nGE 0\nEX 0 1 6 0 1 0\nEN\n", network=True
    )
    with pytest.raises(ValueError, match="odd positive integer"):
        deck.refined(r)


def test_factor_one_is_the_deck_itself():
    deck = parse_nec(
        "GW 1 11 0 0 0 0 0 10 .001\nGE 0\nEX 0 1 6 0 1 0\nEN\n", network=True
    )
    assert deck.refined(1) is deck


def test_a_simnec_circuit_has_no_refinement_path(tmp_path):
    from antennaknobs.file_designs import builder_from_file

    ssn = tmp_path / "c.ssn"
    ssn.write_text("not parsed: the refusal comes first", encoding="utf-8")
    with pytest.raises(SystemExit, match="no refinement path"):
        builder_from_file(str(ssn), refine=3)


def test_ladder_prints_one_rung_per_factor_and_a_z_inf_line(tmp_path, capsys):
    deck = tmp_path / "dip.nec"
    deck.write_text(
        "GW 1 11 0 0 -2.5 0 0 2.5 .001\nGE 0\nEX 0 1 6 0 1 0\nFR 0 1 0 0 28.4 0\nEN\n",
        encoding="utf-8",
    )
    cli(
        [
            "ladder",
            "--builder",
            f"@{deck}",
            "--refine",
            "1",
            "3",
            "--engines",
            "momwire",
            "--ground",
            "free",
        ]
    )
    out = capsys.readouterr().out
    rungs = [ln.split() for ln in out.splitlines() if ln.strip()[:1].isdigit()]
    assert [(row[0], row[1]) for row in rungs] == [("1", "11"), ("3", "33")], out
    # Two factors are too few for Z∞ (AK#1781: the estimator needs three).
    assert "Z∞ unavailable (need >= 3 rungs)" in out, out


def test_ladder_refuses_an_even_factor(tmp_path):
    deck = tmp_path / "dip.nec"
    deck.write_text(
        "GW 1 11 0 0 -2.5 0 0 2.5 .001\nGE 0\nEX 0 1 6 0 1 0\nEN\n", encoding="utf-8"
    )
    with pytest.raises(SystemExit, match="odd positive"):
        cli(["ladder", "--builder", f"@{deck}", "--refine", "1", "2"])


@pytest.mark.parametrize(
    "text",
    [
        "GW 1 3 0 1 0 0 1 3 0.001\nGX 0 010\nGE\nEX 0 1 2 0 1 0\nEN\n",
        "GW 1 3 1 0 0 1 0 1 0.001\nGR 10 4\nGE\nEX 0 1 2 0 1 0\nEN\n",
    ],
)
def test_a_live_symmetry_cell_scales_with_the_mesh(text):
    deck = parse_nec(text, network=True)
    assert deck.symmetry_cell is not None
    assert deck.refined(3).symmetry_cell == 3 * deck.symmetry_cell


def test_ladder_z_inf_on_three_factors_is_first_order():
    # Z(h) = 10 + 3 h with h = 1 / r: exact first order. Three rungs are too
    # few to observe an order, so the estimator assumes the first (AK#1781),
    # which is exact here.
    from antennaknobs.zinf import zinf_estimate

    rs = (1, 3, 9)
    est = zinf_estimate(rs, [complex(10 + 3 / r, -2 + 1 / r) for r in rs])
    assert est.status == "rough"
    assert est.z_inf == pytest.approx(complex(10, -2))


def test_ladder_z_inf_needs_three_rungs():
    from antennaknobs.zinf import zinf_estimate

    est = zinf_estimate([1, 3], [1 + 1j, 1 + 2j])
    assert est.status == "insufficient" and est.z_inf is None


# A NEC-5 TL/NT field names a segment END, a knot (AK#1579), where NEC-2's
# and NEC-4.2's name a segment centre. An L with its network landing on the
# bend knot and on an interior knot, the shape EZNEC's NEC-5 writer gives a
# feed network on a corner.
L_NEC5 = (
    "GW 1 5 0 0 4 2 0 4 .001\nGW 2 5 2 0 4 2 0 0.5 .001\nGE 0\n"
    "EX 0 2 2 2 1 0\n{net}\nFR 0 1 0 0 28 0\nEN\n"
)
L_NEC5_X3 = (
    "GW 1 15 0 0 4 2 0 4 .001\nGW 2 15 2 0 4 2 0 0.5 .001\nGE 0\n"
    "EX 0 2 6 2 1 0\n{net}\nFR 0 1 0 0 28 0\nEN\n"
)


@pytest.mark.parametrize(
    "card, card_x3",
    [
        ("NT 1 5 2 4 0 0.02 0 0 0 0.01", "NT 1 15 2 12 0 0.02 0 0 0 0.01"),
        ("TL 1 5 2 4 300 1.5 0 0 0 0", "TL 1 15 2 12 300 1.5 0 0 0 0"),
        ("NT 1 -2 2 -4 0 0.02 0 0 0 0.01", "NT 1 -4 2 -10 0 0.02 0 0 0 0.01"),
    ],
)
def test_a_nec5_network_end_keeps_its_knot(card, card_x3):
    a, b = _pair(L_NEC5.format(net=card), L_NEC5_X3.format(net=card_x3))
    assert a.dialect == "nec5"
    assert {t.edge_a for t in (*a.tls, *a.nts)} != {0}
    _same(a, b)


def _ports(tmp_path, text, r):
    import re

    from antennaknobs.file_designs import builder_from_file

    deck = tmp_path / f"L{r}.nec"
    deck.write_text(text)
    net = repr(builder_from_file(str(deck), refine=r)().build_network())
    return sorted(re.findall(r"Port(?:AtVertex|OnWire)\([^()]*\)", net))


def test_every_port_stands_in_the_same_place_on_every_rung(tmp_path):
    """The engines place a port exactly (`PortOnWire(at=)`, `PortAtVertex`),
    so a ladder is a mesh study only if every rung hands them the same
    places. Before the fix the NT end on the bend left the vertex for
    at=0.933 and the interior end went 0.8 -> 0.733 at r=3."""
    text = L_NEC5.format(net="NT 1 5 2 4 0 0.02 0 0 0 0.01")
    one = _ports(tmp_path, text, 1)
    assert "PortAtVertex(wire='nt1a', end='p1')" in one
    assert _ports(tmp_path, text, 3) == one == _ports(tmp_path, text, 9)

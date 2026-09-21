"""The two routes we ship agree on every EZNEC deck that carries a network
(AK#1584 + AK#1608 part 2).

`momwire.eznec.serve` (the signed Windows drop-in) and antennaknobs'
`builder_from_file` -> `MomwireEngine` route (the workbench and CLI) are two
ways into the same solver, shipped to different users. AK#1605 put the contact
feed in the same place on both; AK#1607 gave them the same speed of light.
What was left was the network cards, and it was two to three orders larger
than either: a median 4.6e-02 disagreement over this population, to 2.8e-01.

AK#1608's issue asked for exactly this file -- "the corpus-wide gate that
would have caught this ... runs on ONE deck. Widening it, with this issue's
numbers as the starting bar, is probably the right first commit."

Two defects are fixed here, and they had to land together because each blocks
the other:

* **AK#1584** -- a load where a line connects was DROPPED. NEC composes the
  two as a series impedance inside the segment, so it is a `TwoPort` between
  the wire's port and a circuit node that everything external attaches to.
* **AK#1608 part 2** -- a network end at a lone wire end was demoted to that
  segment's centre, half a segment from the knot the card names. A wire end
  standing in the GROUND PLANE is not electrically lone; the plane is its
  second terminal.

Neither alone helps these decks: with the end still demoted the load and the
line no longer share a node, so there is nothing to put the series element
in front of; with the load still dropped, moving the line back onto the knot
makes the missing 18 ohms matter MORE (0023 went 5.77e-02 -> 8.02e-02 in that
half-fixed state).

19 of the 28 agree to float noise now, where 2 did. The nine that remain are
pinned at what they measure, each against the open issue that owns it, so
they cannot drift quietly -- and a FIX shows up here as a failure asking for
the number to be re-recorded, which is the intended way to find out.

ONE CAVEAT ON WHAT THIS GATE MEANS. Agreement between the two routes is a
CONSISTENCY claim, not an accuracy one: it says they are the same
computation, not that the computation is right. The accuracy claim lives
outside CI, against `nec5cl`, which is licensed and cannot run here.

AND ONE ON HOW TO MEASURE IT. Every number in a comparison must come from ONE
configuration. This gate runs both routes in their DEFAULTS, which are two
different bspline lanes -- so a row's bar can be a lane difference rather
than a defect. Drafting these rows across mixed configurations produced two
confidently wrong readings in a row (that serve lagged AK on four decks; that
AK sat at the noise floor on 0011/0029/0030). At matched razor-2p the two
routes agree to float noise on every deck here except 0017.
"""

import pathlib

import momwire
import numpy as np
import pytest

from antennaknobs.engines import MomwireEngine
from antennaknobs.file_designs import builder_from_file

DECKS = (
    pathlib.Path(momwire.__file__).resolve().parents[2] / "tests/fixtures/eznec/decks"
)

# Float noise: eight orders under the smallest real disagreement below, and
# four above the 1.3e-13 worst case among the decks that agree.
NOISE = 1e-9

# deck -> (ceiling, what still owns the gap). NOISE means "the same
# computation"; anything else is a standing defect with an issue.
EXPECTED = {
    "0000_cardioid-l-network-feed": (NOISE, None),
    "0001_4-square-array-w-feed-system": (NOISE, None),
    "0002_4-square-array-w-feed-system": (NOISE, None),
    "0003_4-square-array-w-feed-system": (NOISE, None),
    "0004_4-square-array-w-feed-system": (NOISE, None),
    "0005_4-square-array-w-feed-system": (NOISE, None),
    "0006_4-square-array-w-feed-system": (NOISE, None),
    "0007_4-square-array-w-feed-system": (NOISE, None),
    "0008_4-square-array-w-feed-system": (NOISE, None),
    "0009_4-square-array-w-feed-system": (NOISE, None),
    "0012_network-connection-test": (NOISE, None),
    "0014_network-connection-test": (NOISE, None),
    "0023_4-square-array-l-ntwk-feed": (NOISE, None),
    "0024_4-square-array-w-feed-system": (NOISE, None),
    "0025_4-sq-l-ntwrk-z-match": (NOISE, None),
    "0026_cardioid-with-feed-system": (NOISE, None),
    "0027_cardioid-with-feed-system": (NOISE, None),
    "0120_cardioid-l-network-feed": (NOISE, None),
    "0121_cardioid-l-network-feed": (NOISE, None),
    # AK#1608 part 1 -- a vertex port's sign convention. These carry no
    # demoted end and no co-located load, so nothing here touches them.
    "0011_dipole-with-coax-feedline": (2.0e-2, "AK#1608 part 1"),
    "0029_dipole-with-coax-feedline": (2.0e-2, "AK#1608 part 1"),
    "0030_dipole-with-coax-feedline": (2.0e-2, "AK#1608 part 1"),
    # These four are FIXED by AK#1608 part 2, and both routes now reproduce
    # the licensed NEC-5 to 0.00 % under a matched basis. What is left on the
    # first two is a BSPLINE-LANE difference between the two routes --
    # this gate runs AK's default `BSplineSolver` against serve's default
    # `basis="bspline"`, and those two lanes are not configured identically.
    # Set both to razor-2p and the same decks agree to float noise:
    # 0016 6.1e-15, 0018 5.2e-16, 0116/0117 1.1e-14.
    #
    # Recorded carefully because an earlier draft of this file got it
    # backwards. It claimed "AK is now ahead of serve", on serve figures
    # measured in BSPLINE compared against AK figures measured in RAZOR --
    # mixed configurations. serve was never behind: at matched basis it is
    # exact on all four.
    "0016_network-connection-test": (5e-4, "the two bspline lanes differ"),
    "0018_network-connection-test": (5e-4, "the two bspline lanes differ"),
    # NOT a lane difference, and a convergence ladder is what said so. The
    # 2-3e-4 rows above refine AWAY -- 0016 goes 3.43e-04, 2.58e-05, 4.60e-06,
    # 2.42e-07, 4.47e-10 at r = 1, 3, 5, 7, 15 -- which is what a
    # discretisation artifact does. These two did NOT: 1.022e-01, 8.172e-02,
    # 8.234e-02, 8.099e-02 at r = 1, 3, 5, 7. Flat under a 7x mesh is a
    # different MODEL, not a different mesh, and the model was AK#1619: the
    # `TL` port forces a split, and the split CENTRED the base feed in the
    # piece it made -- 0.6238875 m, 1/16 of the way up a 9.9822 m vertical,
    # where serve feeds the contact. 1.022e-01 -> 1.208e-02.
    #
    # What is left is the topology the two routes choose: serve declares six
    # polylines with `junctions` and `node_gaps`, AK keeps four and positions
    # its ports. That half has never been laddered.
    "0116_40-meter-four-square-array": (1.3e-2, "the two routes' topology"),
    "0117_40-meter-four-square-array": (1.3e-2, "the two routes' topology"),
    # FIXED by AK#1617: two network ports at ONE junction now take the
    # POSITIONED spelling instead of the vertex one, which is what serve does
    # for every network end. 12.62 % -> 0.00 % against the licensed NEC-5, and
    # 1.4e-01 -> 2.2e-04 here, joining its neighbours at the bspline-lane
    # difference.
    #
    # They are NOT merged into one port, and the licensed engine is why:
    # `NT 3,-1` and `NT 2,3` are two spellings of one node and, used
    # CONSISTENTLY, interchangeable -- NEC-5 gives 0012 (both `3,-1`) and
    # 0016 (both `2,3`) the identical 114.4700 + 21.0960j. 0017 MIXES them
    # and NEC-5 returns 195.3400 - 57.4580j, a DIFFERENT circuit. Merging
    # them (an earlier draft did) turns 0017 into 0016 and costs 55.37 %.
    "0017_network-connection-test": (5e-4, "the two bspline lanes differ"),
    # Ports from the NEC-2 reading (edge 0 from the start), never demoted, so
    # no part of this change reaches it. The worst deck in the corpus.
    "0028_17-10m-log-per-arrl-ant-book": (2.9e-1, "unexplained: the NEC-2 reading"),
}


def _routes(stem):
    from momwire.deck._nec5 import parse_nec5
    from momwire.eznec import serve

    path = DECKS / f"{stem}.nec"
    text = path.read_text(errors="replace")
    mw = np.asarray([complex(s.impedance) for s in serve(parse_nec5(text)).sources])
    cls = builder_from_file(str(path))
    ak = np.asarray(MomwireEngine(cls(), ground=cls.file_ground).impedance())
    return ak, mw


def test_the_population_is_the_whole_one():
    """The table is every networked deck in the corpus, not a chosen subset.

    A gate that names its own decks can be green because the interesting one
    was never in it. This fails when momwire's corpus grows a networked deck
    that nobody added a row for."""
    networked = {
        p.stem
        for p in DECKS.glob("*.nec")
        if any(
            line[:2] in ("TL", "NT")
            for line in p.read_text(errors="replace").splitlines()
        )
    }
    assert networked == set(EXPECTED), (
        f"missing rows: {sorted(networked - set(EXPECTED))}; "
        f"stale rows: {sorted(set(EXPECTED) - networked)}"
    )


@pytest.mark.parametrize("stem", sorted(EXPECTED))
def test_the_two_routes_agree(stem):
    bar, owner = EXPECTED[stem]
    ak, mw = _routes(stem)
    assert ak.shape == mw.shape, f"{stem}: {ak.shape} vs {mw.shape}"
    rel = float(np.max(np.abs(ak - mw) / np.abs(mw)))
    assert rel < bar, f"{stem}: AK {ak} vs serve {mw}, rel {rel:.3e} >= {bar:.1e}" + (
        f" (owned by {owner})" if owner else " -- these should be one computation"
    )
    if owner is not None and rel < NOISE:
        pytest.fail(
            f"{stem} now AGREES ({rel:.3e}) but is still pinned as a standing "
            f"defect owned by {owner}. Something fixed it — move this row to "
            f"NOISE and say what did."
        )


def test_two_network_ports_at_one_junction_are_two_positioned_ports():
    """AK#1617: the shape that had no spelling here.

    Deck 0017's two `NT` cards name ONE junction through DIFFERENT wires, and
    a `PortAtVertex` is a series EMF in the through-current path — momwire
    carries one per junction, so the second raised `junction N already carries
    a node gap` and used to be demoted half a segment away, worth 12.62 %.

    `momwire.eznec.serve` never had the problem because it spells every
    network end as a POSITIONED delta gap: it hands the solver `feeds` at
    arclengths with `node_gaps=None` and no cuts, so two ports at one place
    are two list entries. This route now does the same for a crowded knot.

    Pinned as SHAPE rather than numbers: at least one of the two ends is a
    positioned `PortOnWire`, and neither is demoted."""
    from antennaknobs.nec_import import parse_nec

    deck = parse_nec(
        (DECKS / "0017_network-connection-test.nec").read_text(errors="replace"),
        name="0017",
        network=True,
    )
    assert deck.net_ends_demoted == ()
    assert len(deck._crowded_net_knots) == 2

    ports = deck.network().ports
    near = [ports[n] for n in ("nt1a", "nt2a") if n in ports]
    assert len(near) == 2, sorted(ports)
    positioned = [p for p in near if type(p).__name__ == "PortOnWire"]
    assert positioned, [type(p).__name__ for p in near]
    assert all(p.at in (0.0, 1.0) for p in positioned)


def test_the_crowded_knots_are_not_merged_into_one_port():
    """The wrong fix, pinned so it is not re-attempted.

    Merging the two spellings models a DIFFERENT antenna: consistently spelled
    they are interchangeable (NEC-5 gives 0012 and 0016 the identical
    114.4700 + 21.0960j), but 0017 mixes them and NEC-5 returns
    195.3400 - 57.4580j. Collapsing 0017 onto 0016 costs 55.37 % against the
    licensed engine."""
    from antennaknobs.nec_import import parse_nec

    def z(stem):
        cls = builder_from_file(str(DECKS / f"{stem}.nec"))
        return complex(
            np.asarray(MomwireEngine(cls(), ground=cls.file_ground).impedance())[0]
        )

    mixed, consistent = (
        z("0017_network-connection-test"),
        z("0016_network-connection-test"),
    )
    assert abs(mixed - consistent) / abs(consistent) > 0.2, (mixed, consistent)

    deck = parse_nec(
        (DECKS / "0017_network-connection-test.nec").read_text(errors="replace"),
        name="0017",
        network=True,
    )
    # Two distinct ports, not one shared by both admittance branches.
    holders = {
        b.ports[0] for b in deck.network().branches if type(b).__name__ == "Admittance"
    }
    assert len(holders) == 2, holders

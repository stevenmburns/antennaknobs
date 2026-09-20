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
    # the licensed NEC-5 to 0.00 % under a matched basis. What is left below
    # is a BSPLINE-LANE CONFIGURATION difference between the two routes --
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
    "0116_40-meter-four-square-array": (1.1e-1, "the two bspline lanes differ"),
    "0117_40-meter-four-square-array": (1.1e-1, "the two bspline lanes differ"),
    # TWO network ports meet at ONE junction, and we carry one node gap per
    # junction, so the second is still demoted to its segment centre. Not a
    # cosmetic collision: `NT 3,-1` and `NT 2,3` are two spellings of one
    # node, and used CONSISTENTLY they are interchangeable -- the licensed
    # NEC-5 gives 0012 (both `3,-1`) and 0016 (both `2,3`) the identical
    # 114.4700 + 21.0960j. 0017 MIXES them and NEC-5 returns
    # 195.3400 - 57.4580j, a different circuit. So the spelling picks which
    # element the port attaches to, and merging the two (which an earlier
    # draft of AK#1608 part 2 did) models the wrong antenna -- it turns 0017
    # into 0016 and moves it from 12.62 % to 55.37 % against NEC-5.
    #
    # NEC-5 SOLVES this deck, and so does SERVE: at razor-2p serve reproduces
    # the licensed engine to 0.00 % while this route is 12.62 % out. So the
    # defect is ENTIRELY OURS, momwire can already express the shape, and the
    # fix is to find what serve spells differently -- not a momwire feature
    # request and not a port-model rewrite.
    "0017_network-connection-test": (
        1.5e-1,
        "two network ports at one junction, AK-only",
    ),
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

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
    # `hosted()`'s OTHER branch: a network end at a knot that shares an
    # emitted piece with a source is still demoted (the #824 collision).
    # 0016 is the minimal case -- the same physical connection as 0012,
    # spelled `2,3` instead of `3,-1`.
    "0016_network-connection-test": (7.5e-2, "AK#1608, the shares-a-piece branch"),
    "0017_network-connection-test": (1.5e-1, "AK#1608, the shares-a-piece branch"),
    "0018_network-connection-test": (1.7e-1, "AK#1608, the shares-a-piece branch"),
    # Lone ends that are NOT ground contacts (z = 4.9911), so the demotion
    # correctly stands and something else owns the gap. Unexplained.
    "0116_40-meter-four-square-array": (2.3e-1, "unexplained: elevated lone ends"),
    "0117_40-meter-four-square-array": (2.3e-1, "unexplained: elevated lone ends"),
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

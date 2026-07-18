"""Dead trailing run-config cards (issue #449).

Batch NEC-2 executes at each XQ/RP with the cards read so far; config
cards after the deck's LAST execute request never take effect. Whole-deck
parsers (xnec2c, 4nec2, our importer) apply them regardless — zepp-80m's
"TL translation artifact" was exactly this: nec2c solved a disconnected
feeder stub with no ground (0 − 41243j), while hoisting its trailing
TL/GN reproduces our engines' answer to four digits (0.598 − 115.1j).
The contract here: the bench detects the pattern, refuses the
original-deck reference, and prepares a hoisted reference that solves
the deck's intended configuration.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from bench_nec_corpus import (  # noqa: E402
    dead_trailing_config,
    has_dead_trailing_config,
    reference_deck,
)

ZEPP_MINI = (
    "CE\n"
    "GW 1 27 0 0 20 0 0 60.5 1.5e-3\n"
    "GW 2 1 -0.2 0 0.5 0.2 0 0.5 1.5e-2\n"
    "GE 1\n"
    "EX 0 2 1 0 1 0\n"
    "FR 0 1 0 0 3.0 0\n"
    "RP 0 19 73 0 0 0 5 5\n"
    "TL 1 1 2 1 450 0\n"
    "GN 2 0 0 0 12 0.005\n"
    "EN\n"
)


def test_detector_flags_trailing_config():
    assert has_dead_trailing_config(ZEPP_MINI)
    mnems = ["GW", "GE", "EX", "FR", "RP", "TL", "GN", "EN"]
    assert dead_trailing_config(mnems) == [5, 6]


def test_detector_passes_wellordered_and_execless_decks():
    ordered = ZEPP_MINI.replace(
        "RP 0 19 73 0 0 0 5 5\nTL 1 1 2 1 450 0\nGN 2 0 0 0 12 0.005\n",
        "TL 1 1 2 1 450 0\nGN 2 0 0 0 12 0.005\nRP 0 19 73 0 0 0 5 5\n",
    )
    assert not has_dead_trailing_config(ordered)
    # No execute request at all: nothing can trail it (the bench appends
    # its own XQ at the end, after every card).
    assert not has_dead_trailing_config(ZEPP_MINI.replace("RP 0 19 73 0 0 0 5 5\n", ""))


def test_detector_ignores_config_between_multi_run_executes():
    # A legitimate multi-run deck: config between two executes is live,
    # only cards after the LAST execute are dead.
    mnems = ["GW", "GE", "EX", "FR", "XQ", "GN", "FR", "XQ", "EN"]
    assert dead_trailing_config(mnems) == []


def test_reference_deck_hoists_before_first_execute():
    prepared = reference_deck(ZEPP_MINI, "zepp-mini").splitlines()
    order = [ln.split()[0] for ln in prepared]
    assert order.index("TL") < order.index("RP")
    assert order.index("GN") < order.index("RP")
    # Hoisted cards keep their relative order and land after EX/FR.
    assert order.index("EX") < order.index("TL") < order.index("GN")
    # Nothing duplicated or lost.
    assert order.count("TL") == 1 and order.count("GN") == 1


def test_reference_deck_leaves_wellordered_decks_alone():
    ordered = ZEPP_MINI.replace(
        "RP 0 19 73 0 0 0 5 5\nTL 1 1 2 1 450 0\nGN 2 0 0 0 12 0.005\n",
        "TL 1 1 2 1 450 0\nGN 2 0 0 0 12 0.005\nRP 0 19 73 0 0 0 5 5\n",
    )
    order = [ln.split()[0] for ln in reference_deck(ordered, "t").splitlines()]
    assert order.index("TL") < order.index("GN") < order.index("RP")

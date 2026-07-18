"""GN-card → engine ground mapping in the corpus bench (parse_ground).

Regression anchor for the TopCap75 finding: 70 wild decks use 4nec2's
``GN 3`` MiniNec-style ground, whose impedance semantics are
perfect-ground (and which vanilla nec2c also lands in its PEC branch —
GN 3 and GN 1 give bit-identical Z). The old mapping solved them in
free space and, worse, still counted them as clean comparisons.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from bench_nec_corpus import parse_ground  # noqa: E402


def test_gn3_mininec_maps_to_pec_supported():
    spec, supported, note = parse_ground(
        "GW 1 3 0 0 0 0 0 1 .001\nGN 3 0 0 0 13 .005\nEN\n"
    )
    assert spec == "pec"
    assert supported is True


def test_unknown_iperf_is_flagged_not_clean():
    spec, supported, note = parse_ground("GN 7 0 0 0 13 .005\nEN\n")
    assert spec == "free"
    assert supported is False
    assert "IPERF=7" in note


def test_standard_types_unchanged():
    assert parse_ground("GN 1\nEN\n")[0] == "pec"
    assert parse_ground("GN 2 0 0 0 13 .005\nEN\n")[0] == ("finite", 13.0, 0.005)
    assert parse_ground("GN 0 0 0 0 13 .005\nEN\n")[0] == ("finite-fast", 13.0, 0.005)
    assert parse_ground("GN -1\nEN\n")[0] == "free"
    assert parse_ground("GW 1 3 0 0 0 0 0 1 .001\nEN\n") == ("free", True, "")


def test_gn3_with_radials_still_flags_screen():
    spec, supported, note = parse_ground("GN 3 16 0 0 13 .005\nEN\n")
    assert spec == "pec"
    assert supported is False
    assert "radial" in note

"""AK#1510: a CLI command that solves prints each distinct FeedPlacement
advisory to stderr, once, and leaves stdout as the command's own output."""

from __future__ import annotations

from conftest import needs_pynec

import antennaknobs as ant
from antennaknobs.cli import _FeedPlacementEcho

# 31% of ten segments is neither a segment centre nor a knot of those ten.
DECK = (
    "GW 1 10 0 -2.6 10 0 2.6 10 0.001\nGE\nEX 0 1 31% 0 1 0\nFR 0 1 0 0 28.47 0\nEN\n"
)
NOTE = (
    "advisory: Wire 'feed' carries port 'feed' at 0.31 of its length, which is not "
    "a segment centre of its 10 segments, so the wire is split and the port is fed "
    "exactly, at the middle of a short piece of its own (AK#1511).\n"
)
KNOT_NOTE = (
    "advisory: Wire 'feed' carries port 'feed' at 0.31 of its length, which is not "
    "a knot of its 10 segments, so the wire is split there and the port is fed "
    "exactly, at the knot the two pieces share (AK#1511).\n"
)


@needs_pynec
def test_ladder_prints_the_note_once_to_stderr_and_stdout_is_unchanged(
    tmp_path, capsys, monkeypatch
):
    deck = tmp_path / "offset.nec"
    deck.write_text(DECK)
    argv = f"ladder --builder @{deck} --refine 1 --engines pynec pynec".split()

    ant.cli(argv)
    echoed = capsys.readouterr()
    assert echoed.err.count(NOTE) == 1
    assert "advisory" not in echoed.out

    monkeypatch.setattr(_FeedPlacementEcho, "flush", lambda *a, **k: None)
    ant.cli(argv)
    silent = capsys.readouterr()
    assert NOTE not in silent.err
    assert echoed.out == silent.out


def test_export_prints_the_note_to_stderr_and_the_deck_is_unchanged(
    tmp_path, capsys, monkeypatch
):
    deck = tmp_path / "offset.nec"
    deck.write_text(DECK)
    argv = f"export --dialect nec5 --builder @{deck} --ground free".split()

    ant.cli(argv)
    echoed = capsys.readouterr()
    assert echoed.err.count(KNOT_NOTE) == 1
    assert echoed.out.count("\nGW ") == 2

    monkeypatch.setattr(_FeedPlacementEcho, "flush", lambda *a, **k: None)
    ant.cli(argv)
    silent = capsys.readouterr()
    assert silent.err == ""
    assert echoed.out == silent.out

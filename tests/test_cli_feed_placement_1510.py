"""AK#1510: a CLI command that solves prints each distinct FeedPlacement
advisory to stderr, once, and leaves stdout as the command's own output."""

from __future__ import annotations

from conftest import needs_pynec

import antennaknobs as ant
from antennaknobs.cli import _FeedPlacementEcho

# 31% of ten segments is a segment centre only at 50, past twice the count.
DECK = (
    "GW 1 10 0 -2.6 10 0 2.6 10 0.001\nGE\nEX 0 1 31% 0 1 0\nFR 0 1 0 0 28.47 0\nEN\n"
)
NOTE = (
    "advisory: Port 'feed' asks for 0.31 of the way along wire 'feed'. No segment "
    "count up to 2× the wire's own puts a segment centre there, so the wire is "
    "split in two at 0.62 of its length and the port is fed exactly, at the middle "
    "of its piece (AK#1510).\n"
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
    assert echoed.err.count(NOTE.replace("segment centre", "knot")) == 1
    assert echoed.out.count("\nGW ") == 2

    monkeypatch.setattr(_FeedPlacementEcho, "flush", lambda *a, **k: None)
    ant.cli(argv)
    silent = capsys.readouterr()
    assert silent.err == ""
    assert echoed.out == silent.out

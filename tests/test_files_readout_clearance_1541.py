"""The Files view's scrolling pane clears the floating solve readout (AK#1541).

The R/X/SWR card floats over the stage's bottom-left corner. The pane already
carried a `padding-bottom` so its last LINES could scroll out from under the
card — and the reported defect is the one thing that padding cannot move: a
scrolling box draws its horizontal scrollbar on its bottom EDGE, inside the
border and below any padding. A deck is exactly the text wide enough to need
that scrollbar, so it was the one control the card covered.

Filling the stage, the pane owns the stage's bottom edge, so it ends above the
card instead — and then must NOT also reserve the height inside its own scroll,
or the room is counted twice. As one cell of the grid it has no bottom edge of
its own to give up, and keeps the inner reservation.

WHY NOT A VITEST. jsdom computes no layout and resolves no calc() over custom
properties, so a mounted panel can only be asked which classes it carries —
which is what broke, not what changed. The stylesheet's text is the contract,
and a vitest cannot read it either way: vitest replaces CSS imports (`?raw`
included) with the empty string, and the frontend's tsconfig carries no node
types, so `node:fs` does not typecheck there. It reads fine from here, and
tests/test_axis_controls_1006.py already reaches into the frontend this way.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

CSS = (
    Path(__file__).resolve().parents[1] / "src/antennaknobs/web/frontend/src/styles.css"
).read_text(encoding="utf-8")


def padding_bottom(selector: str) -> str:
    """The `padding-bottom` of the first rule with exactly this selector."""
    at = CSS.find(f"\n{selector} {{")
    assert at >= 0, f"no rule for {selector}"
    block = CSS[CSS.index("{", at) + 1 : CSS.index("}", at)]
    found = re.search(r"padding-bottom:([^;]*);", block)
    assert found, f"{selector} declares no padding-bottom"
    return found.group(1).strip()


# The readout publishes its own height on the stage container as it collapses
# and grows (SolveReadout), and floats var(--space-6) up from the bottom edge.
# The variable is 0 where no readout floats, so reserving costs nothing there.
READOUT_HEIGHT = "--stage-readout-h"


def test_the_stage_filling_pane_ends_above_the_readout():
    pad = padding_bottom(".files-fill")
    assert READOUT_HEIGHT in pad
    assert "--space-6" in pad


def test_the_stage_filling_pane_does_not_reserve_the_height_twice():
    assert READOUT_HEIGHT not in padding_bottom(".files-fill .files-text")


def test_the_grid_cell_pane_still_reserves_inside_its_own_scroll():
    assert READOUT_HEIGHT in padding_bottom(".files-text")


@pytest.mark.parametrize("selector", [".files-fill", ".files-text"])
def test_the_rules_this_reads_are_where_it_thinks_they_are(selector):
    """A renamed class would make every assertion above vacuous."""
    assert CSS.count(f"\n{selector} {{") == 1

"""The designs folder's guide shows code that runs.

The CLAUDE.md copied into every user's designs folder is what Claude Code
reads to write a design, so a stale example there becomes every design's
bug. Two of its examples kept `TL.from_cable("RG-8X", ...)` after cables
moved out of momwire, and a bare name has raised a TypeError since; a user's
first coax design failed on exactly that line.
"""

from __future__ import annotations

import re
from pathlib import Path

from antennaknobs.network import TL, cable_from_catalog

GUIDE = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "antennaknobs"
    / "web"
    / "user_design_assets"
    / "CLAUDE.md"
)


def test_the_guide_never_passes_a_cable_name_to_from_cable():
    text = GUIDE.read_text(encoding="utf-8")
    calls = re.findall(r"TL\.from_cable\(\s*([^,)]*)", text)
    assert calls, "the guide no longer shows TL.from_cable at all"
    bare = [c for c in calls if c.strip().startswith(("'", '"'))]
    assert bare == [], f"TL.from_cable given a bare cable name: {bare}"


def test_the_guides_cable_forms_construct():
    # The catalog form, and the guide's own-numbers form with z0 and length
    # named (TL's third positional argument is z0, not the length).
    TL.from_cable(cable_from_catalog("RG-8X"), "rig", "feed", 20.0)
    line = TL("rig", "feed", z0=50, length=10.0, vf=0.82, k1=0.27, k2=0.0055)
    assert (line.z0, line.length) == (50, 10.0)
    assert 'TL("rig", "feed", z0=50, length=10.0' in GUIDE.read_text(encoding="utf-8")

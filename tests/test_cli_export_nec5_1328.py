"""antennaknobs#1328: `antennaknobs export --dialect nec5` writes the NEC-5 deck.

A NEC-5 deck posted to a public thread on 2026-09-10 was written by hand, and it
carried a NEC-2 habit into NEC-5: the source on the mast's first segment, which
NEC-5 places at that segment's far END, 0.92 m up instead of at the base. The
model's own writer (`NEC5Engine.deck`, through `nec5_export.export_nec5`) would
have written it right, but it had no CLI surface. So a deck that leaves this repo
is now produced by the tool from the model, never by hand.
"""

from __future__ import annotations

import pytest

import antennaknobs
from antennaknobs.designs.dipoles.invvee import Builder
from antennaknobs.nec5_export import export_nec5
from antennaknobs.nec_export import export_nec


def test_the_nec5_dialect_is_the_model_writers_deck(tmp_path):
    out = tmp_path / "invvee.nec"
    antennaknobs.cli(
        [
            "export",
            "--builder",
            "dipoles.invvee",
            "--dialect",
            "nec5",
            "--ground",
            "free",
            "--out",
            str(out),
        ]
    )
    expected = export_nec5(
        Builder(),
        ground=None,
        design="dipoles.invvee",
        rung="default",
        ground_name="free",
        note="written by `antennaknobs export --dialect nec5`",
    )
    assert out.read_text(encoding="utf-8") == expected


def test_the_default_dialect_is_still_the_nec2_deck(tmp_path):
    out = tmp_path / "invvee.nec"
    antennaknobs.cli(["export", "--builder", "dipoles.invvee", "--out", str(out)])
    assert out.read_text(encoding="utf-8") == export_nec(Builder())


def test_no_pattern_is_refused_for_the_nec5_dialect(tmp_path):
    """`--no-pattern` drops the NEC-2 writer's RP card; the NEC-5 writer has no
    such switch, so asking for it is an error rather than silently ignored."""
    with pytest.raises(SystemExit) as exc:
        antennaknobs.cli(
            [
                "export",
                "--builder",
                "dipoles.invvee",
                "--dialect",
                "nec5",
                "--no-pattern",
                "--out",
                str(tmp_path / "x.nec"),
            ]
        )
    assert "--no-pattern" in str(exc.value), exc.value

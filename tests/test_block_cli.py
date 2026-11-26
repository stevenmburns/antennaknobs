"""``--blocks FILE.json`` (and ``--builder @FILE.json``) runs a block program
through the normal pipeline, so the spine is testable before any editor
exists (docs/design/block-builder.md, Phases, 1)."""

from __future__ import annotations

import csv
import json

import pytest

import antennaknobs as ant
from antennaknobs.block_templates import template


def _rows(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.reader(f))


def _sweep(tmp_path, tag, *design):
    out = tmp_path / f"{tag}.csv"
    ant.cli(
        [
            "sweep",
            *design,
            "--param",
            "freq",
            "--npoints",
            "3",
            "--engine",
            "momwire:bs2",
            "--fn",
            "/dev/null",
            "--csv",
            str(out),
        ]
    )
    return _rows(out)


def test_blocks_flag_sweeps_the_same_numbers_as_the_catalog_twin(tmp_path):
    path = tmp_path / "dipole.json"
    path.write_text(json.dumps(template("dipole")), encoding="utf-8")
    ours = _sweep(tmp_path, "blocks", "--blocks", str(path))
    theirs = _sweep(tmp_path, "twin", "--builder", "dipoles.invvee:dipole")
    assert ours[0] == ["freq", "R_ohm", "X_ohm"]
    assert len(ours) == 4
    # tests/test_block_templates.py: the template is the twin's model.
    assert ours == theirs
    # And the @ spelling is the same design.
    assert _sweep(tmp_path, "at", "--builder", f"@{path}") == ours


def test_a_program_with_errors_exits_with_each_on_its_own_line(tmp_path, capsys):
    tree = template("dipole")
    tree["body"][0]["value"] = "eps2 * 2"
    tree["body"][1]["value"] = "__import__('os')"
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(tree), encoding="utf-8")
    with pytest.raises(SystemExit) as info:
        ant.cli(["structure", "--blocks", str(path)])
    msg = str(info.value)
    assert "block gap: value: no param or let is named 'eps2'" in msg
    assert "block arm: value: " in msg
    assert msg.count("\n  block ") == 2


def test_blocks_and_builder_are_one_choice(tmp_path, capsys):
    with pytest.raises(SystemExit) as info:
        ant.cli(["structure", "--blocks", "x.json", "--builder", "dipoles.invvee"])
    assert info.value.code == 2
    assert "not allowed with argument" in capsys.readouterr().err


def test_a_missing_or_garbled_file_is_refused_by_name(tmp_path):
    with pytest.raises(SystemExit, match="no such file"):
        ant.cli(["structure", "--blocks", str(tmp_path / "none.json")])
    bad = tmp_path / "garbled.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(SystemExit, match="not JSON"):
        ant.cli(["structure", "--blocks", str(bad)])

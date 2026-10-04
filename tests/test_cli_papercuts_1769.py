"""AK#1769: the CLI's first-run papercuts (QRZ 1003328 #166).

1. ``-v`` alone crashed (``args.func`` missing) and ``--version`` did not
   exist;
2. a sweep over an ordinary knob printed nothing on stdout;
3. a deck sweep announced "N=<n> segments/wire (engine default)", which reads
   as though the engine ignored the deck's own segmentation;
4. the unknown-builder hint named ``antennaknobs list`` whatever the program
   was called.
"""

from __future__ import annotations

import re
import sys

import matplotlib.pyplot as plt
import pytest

import antennaknobs as ant
from antennaknobs import program_name
from antennaknobs.cli import get_builder

DIPOLE = "dipoles.invvee:dipole"

# A 21-segment centre-fed dipole: the smallest deck that solves.
DECK = """CM 1769 dipole
CE
GW 1 21 0 -2.5 10 0 2.5 10 0.001
GE 0
EX 0 1 11 0 1 0
FR 0 1 0 0 28 0
EN
"""

_ROW = re.compile(r"^\s*(?P<x>\S+)\s+(?P<r>[+-]?\d+\.\d+)\s+(?P<xx>[+-]\d+\.\d+)$")


def _rows(text, header):
    """The rows of the block headed ``header``."""
    lines = text.splitlines()
    i = lines.index(header)
    out = []
    for line in lines[i + 1 :]:
        if line.startswith("=="):
            break
        m = _ROW.match(line)
        if m:
            out.append((float(m["x"]), float(m["r"]), float(m["xx"])))
    return out


def test_dash_v_alone_is_a_usage_error_not_a_traceback(capsys):
    with pytest.raises(SystemExit) as ei:
        ant.cli(["-v"])
    assert ei.value.code == 2
    err = capsys.readouterr().err
    assert "name a command" in err and "--version" in err
    assert "Traceback" not in err and "AttributeError" not in err


@pytest.mark.parametrize("flag", ["--version", "-V"])
def test_version_prints_both_packages(flag, capsys):
    with pytest.raises(SystemExit) as ei:
        ant.cli([flag])
    assert ei.value.code == 0
    out = capsys.readouterr().out
    assert re.match(r"^antennaknobs \S+ \(momwire \S+\)$", out.strip()), out


def test_knob_sweep_prints_its_table(capsys):
    try:
        ant.cli(
            f"sweep --builder {DIPOLE} --param length_factor --range 0.95 1.0 "
            "--npoints 3 --ground free --fn /dev/null".split()
        )
    finally:
        plt.close("all")
    out = capsys.readouterr().out
    rows = _rows(out, "== length_factor sweep ==")
    assert [r[0] for r in rows] == [0.95, 0.975, 1.0]
    # A longer dipole: X rises through resonance.
    assert rows[0][2] < rows[1][2] < rows[2][2]
    assert "ground: free space" in out


def test_multi_engine_knob_sweep_prints_a_block_per_engine(capsys):
    try:
        ant.cli(
            f"sweep --builder {DIPOLE} --param length_factor --range 0.95 1.0 "
            "--npoints 2 --ground free --engine momwire:bspline,momwire:razor-2p "
            "--panels --fn /dev/null".split()
        )
    finally:
        plt.close("all")
    out = capsys.readouterr().out
    for spec in ("momwire:bspline", "momwire:razor-2p"):
        assert len(_rows(out, f"== length_factor sweep: {spec} ==")) == 2


def test_deck_sweep_says_the_file_meshes_itself(tmp_path, capsys):
    deck = tmp_path / "d1769.nec"
    deck.write_text(DECK)
    try:
        ant.cli(
            f"sweep --builder @{deck} --engine momwire:razor-2p --npoints 2 "
            "--fn /dev/null".split()
        )
    finally:
        plt.close("all")
    err = capsys.readouterr().err
    assert "engine momwire:razor-2p: the file's own segment counts" in err
    assert "engine default" not in err and "N=40" not in err


def test_catalog_sweep_still_names_the_engine_density(capsys):
    try:
        ant.cli(
            f"sweep --builder {DIPOLE} --engine momwire:razor-2p --npoints 2 "
            "--ground free --fn /dev/null".split()
        )
    finally:
        plt.close("all")
    assert "N=40 segments/wire (engine default)" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("typed", "argv0", "shown"),
    [
        (".\\antennaknobs-cli.exe", "whatever", ".\\antennaknobs-cli.exe"),
        (None, "/venv/bin/antennaknobs", "antennaknobs"),
        (None, "/x/antennaknobs/__main__.py", "python -m antennaknobs"),
    ],
)
def test_unknown_builder_hint_names_the_invoked_program(
    typed, argv0, shown, monkeypatch
):
    if typed is None:
        monkeypatch.delenv(program_name.COMMAND_ENV, raising=False)
    else:
        monkeypatch.setenv(program_name.COMMAND_ENV, typed)
    monkeypatch.setattr(sys, "argv", [argv0])
    with pytest.raises(SystemExit) as ei:
        get_builder("dipoles.nosuch")
    assert f"(see `{shown} list`)" in str(ei.value)


def test_a_path_with_a_space_is_quoted(monkeypatch):
    monkeypatch.setenv(program_name.COMMAND_ENV, "/opt/my tools/antennaknobs")
    monkeypatch.setattr(program_name.os, "name", "posix")
    assert program_name.invoked_command() == "'/opt/my tools/antennaknobs'"

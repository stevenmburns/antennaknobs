"""antennaknobs#1563: the CLI hands every engine ONE ground.

Seen on a user Moxon at 7 m: `sweep --param nominal_nsegs` across nec5, nec2,
sinusoidal and pynec with no `--ground` split into two Richardson-converged
camps 9 Ω apart — not a solver disagreement but the engines' own defaults
(PyNEC and NEC-2 finite, momwire and NEC-5 free) compared without a word.
Pinned here:

  1. `resolve_ground` never yields the unset marker: explicit --ground, else a
     file design's own ground (AK#1432), else free space;
  2. the convergence table prints that ground under every engine header;
  3. a study with no --ground puts pynec and momwire on the SAME physics.
"""

from __future__ import annotations

import re

import matplotlib.pyplot as plt
import pytest

import antennaknobs as ant
from antennaknobs.cli import (
    _GROUND_UNSET,
    CLI_DEFAULT_GROUND,
    format_ground,
    resolve_ground,
)

DIPOLE = "dipoles.invvee:dipole"
_GROUND_RE = re.compile(r"^ground: (?P<label>.+)$")
_HEADER_RE = re.compile(r"^== nominal_nsegs convergence: (?P<name>\S+) ==$")
_ROW_RE = re.compile(r"^\s*(\d+)\s+(\d+)\s+([+-]?\d+\.\d+)\s+([+-]?\d+\.\d+)\s+")


def _ground_lines(out):
    """[(engine, ground label)] in table order — one per header, and the
    ground line must sit DIRECTLY under its header."""
    lines = out.splitlines()
    pairs = []
    for i, ln in enumerate(lines):
        m = _HEADER_RE.match(ln)
        if m:
            g = _GROUND_RE.match(lines[i + 1])
            pairs.append((m.group("name"), g.group("label") if g else None))
    return pairs


def _first_rows(out):
    """{engine: Z at the first rung}."""
    zs = {}
    current = None
    for ln in out.splitlines():
        m = _HEADER_RE.match(ln)
        if m:
            current = m.group("name")
            continue
        m = _ROW_RE.match(ln)
        if m and current is not None and current not in zs:
            zs[current] = complex(float(m.group(3)), float(m.group(4)))
    return zs


# --- 1. resolve_ground ------------------------------------------------------


def test_unset_resolves_to_the_one_cli_default():
    assert CLI_DEFAULT_GROUND == "free"
    assert resolve_ground(_GROUND_UNSET) == "free"
    assert resolve_ground(_GROUND_UNSET, builder=None) == "free"
    assert resolve_ground(_GROUND_UNSET) is not _GROUND_UNSET


def test_explicit_ground_is_parsed_and_wins():
    assert resolve_ground("free") is None
    assert resolve_ground("pec") == "pec"
    assert resolve_ground("finite") == ("finite", 13.0, 0.005)
    assert resolve_ground("finite-fast:5,0.001") == ("finite-fast", 5.0, 0.001)


def test_a_file_design_ground_is_the_default_and_an_explicit_one_still_wins():
    class Deck:
        file_ground = ("finite", 20.0, 0.03)

    class FreeDeck:
        file_ground = None

    class Catalog:
        pass

    assert resolve_ground(_GROUND_UNSET, Deck) == ("finite", 20.0, 0.03)
    assert resolve_ground(_GROUND_UNSET, Deck()) == ("finite", 20.0, 0.03)
    assert resolve_ground(_GROUND_UNSET, FreeDeck) == "free"
    assert resolve_ground(_GROUND_UNSET, Catalog) == "free"
    assert resolve_ground("pec", Deck) == "pec"


def test_format_ground_names_every_spelling():
    assert format_ground(None) == "free space"
    assert format_ground("free") == "free space"
    assert format_ground("pec") == "pec"
    assert format_ground(("finite", 13.0, 0.005)) == (
        "finite 13/0.005 (Sommerfeld-Norton)"
    )
    assert format_ground(("finite-fast", 5.0, 0.001)) == (
        "finite-fast 5/0.001 (reflection-coefficient)"
    )


# --- 2. the table says which ground -----------------------------------------


def test_convergence_table_prints_the_shared_ground_under_each_header(capsys):
    ant.cli(
        f"sweep --builder {DIPOLE} --param nominal_nsegs --markers 8 "
        f"--engine momwire:bspline,momwire:sinusoidal --fn /dev/null".split()
    )
    plt.close("all")
    pairs = _ground_lines(capsys.readouterr().out)
    assert pairs == [
        ("momwire:bspline", "free space"),
        ("momwire:sinusoidal", "free space"),
    ]


def test_convergence_table_prints_an_explicit_ground(capsys):
    ant.cli(
        f"sweep --builder {DIPOLE} --param nominal_nsegs --markers 8 "
        f"--ground finite --engine momwire:bspline --fn /dev/null".split()
    )
    plt.close("all")
    pairs = _ground_lines(capsys.readouterr().out)
    assert pairs == [("momwire:bspline", "finite 13/0.005 (Sommerfeld-Norton)")]


def test_frequency_sweep_stays_silent(capsys):
    """The ground line is a convergence-table thing; the single-engine
    frequency sweep's byte-identical silence (#1554 gate 3) is untouched."""
    ant.cli(f"sweep --builder {DIPOLE} --npoints 3 --fn /dev/null".split())
    plt.close("all")
    assert capsys.readouterr().out == ""


# --- 3. same physics on every engine ----------------------------------------


def test_no_ground_means_the_same_physics_on_pynec_and_momwire(capsys):
    """Before #1563 this pair silently ran finite (pynec) against free
    (momwire). Now both run free, and a dipole's Z agrees to the size of the
    basis difference — not the ~10 % a ground model is worth at this height."""
    pytest.importorskip("PyNEC")
    ant.cli(
        f"sweep --builder {DIPOLE} --param nominal_nsegs --markers 16 "
        f"--engine momwire:sinusoidal,pynec --fn /dev/null".split()
    )
    plt.close("all")
    out = capsys.readouterr().out
    assert [g for _, g in _ground_lines(out)] == ["free space", "free space"]
    zs = _first_rows(out)
    z_mw, z_py = zs["momwire:sinusoidal"], zs["pynec"]
    assert abs(z_mw - z_py) < 0.02 * abs(z_py), (z_mw, z_py)

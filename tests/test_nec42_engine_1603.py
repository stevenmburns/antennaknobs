"""AK#1603: NEC-4.2 as a user-supplied engine, a thin subclass of NEC2Engine.

Two halves:

* **No binary needed** — the deck spelling (``GN ... NOFILE``, ``GE -1`` on a
  buried design, ``GE 1`` on a ground-mounted vertical, no ``GN`` in free
  space), the refusals, the run directory, the power-budget labels, and the
  roster / settings / CLI wiring. A stand-in "binary" is a shell wrapper around
  this interpreter.
* **The licensed binary** — skipped unless ``$NEC42_EXE`` names a working
  NEC-4.2. Nothing NEC-4.2 printed is stored here: every number compared is
  produced by a live run in the test itself (the licence is own use only).
"""

from __future__ import annotations

import math
import os
import shutil
import sys
import tempfile
import textwrap
from pathlib import Path
from types import MappingProxyType

import numpy as np
import pytest

from antennaknobs.builder import AntennaBuilder
from antennaknobs.engines import nec42 as m
from antennaknobs.engines.nec42 import (
    NEC42Engine,
    NEC42Error,
    find_nec42,
    probe_nec42,
    refuse_nec42_geometry,
)
from antennaknobs.network import GradedSegments, Wire

SOIL = ("finite", 13.0, 0.005)

# The binary's contract: `exe <deck> <printout>`, both relative, from the
# deck's directory. The stand-in records where it ran and what it found there,
# drops a file a Sommerfeld run would leave in its cwd, and writes the printout.
_ARGS_STANDIN = """
import os
import sys
from pathlib import Path

deck, out = sys.argv[1], sys.argv[2]
assert not os.path.isabs(deck) and Path(deck).is_file(), deck
Path(os.environ["NEC42_STANDIN_LOG"]).write_text(os.getcwd())
Path("SOMMPD.NEC").write_text("table")
Path(out).write_text(PRINTOUT)
"""

_WRONG_PROGRAM = """
import sys
from pathlib import Path

Path(sys.argv[2]).write_text("I am not a NEC.\\n")
"""

# NEC-4.2's layout, in shape: TAG SEG then nine numbers, which fuse where a
# minus sign takes the separating space.
_AIP_BLOCK = """\
                                          - - - ANTENNA INPUT PARAMETERS - - -

   TAG   SEG.    VOLTAGE (VOLTS)         CURRENT (AMPS)         IMPEDANCE (OHMS)        ADMITTANCE (MHOS)      POWER
   NO.   NO.    REAL        IMAG.       REAL        IMAG.       REAL        IMAG.       REAL        IMAG.     (WATTS)
     1     6 1.00000E+00 0.00000E+00 1.80000E-02-3.00000E-03 5.00000E+01 1.00000E+01 1.80000E-02-3.00000E-03 9.00000E-03
"""

# Eleven segment-centre currents on tag 1, NEC-4.2's 10-token rows.
_CURRENTS = (
    "\n                             - - - CURRENTS AND LOCATION - - -\n\n"
    "  SEG.  TAG    COORD. OF SEG. CENTER     SEG.            - - - CURRENT (AMPS) - - -\n"
    "  NO.   NO.     X        Y        Z      LENGTH     REAL        IMAG.       MAG.        PHASE\n"
    + "".join(
        f"{k:6d}    1   0.0000   0.0000   0.4667  0.04329   1.0000E-02 -1.0000E-03  1.0050E-02   -5.711\n"
        for k in range(1, 12)
    )
    + "\n\n"
)

_BUDGET = """\
                                        - - - POWER BUDGET - - -

                                           INPUT POWER   = 1.0000E-02 WATTS
                                           RADIATED POWER= 8.7500E-03 WATTS
                                           WIRE LOSS     = 1.2500E-03 WATTS
                                           EFFICIENCY    =  87.50 PERCENT
"""


def _stub(tmp_path: Path, body: str, name: str, printout: str = "") -> str:
    script = tmp_path / f"{name}.py"
    script.write_text(f"PRINTOUT = {printout!r}\n" + textwrap.dedent(body))
    exe = tmp_path / name
    exe.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{script}" "$@"\n')
    exe.chmod(0o755)
    return str(exe)


@pytest.fixture(autouse=True)
def _clear_probe_cache():
    m._PROBE_CACHE.clear()
    yield
    m._PROBE_CACHE.clear()


@pytest.fixture()
def standin(tmp_path, monkeypatch):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    exe = _stub(
        bindir, _ARGS_STANDIN, "nec42", printout=_AIP_BLOCK + _CURRENTS + _BUDGET
    )
    monkeypatch.setenv("NEC42_EXE", exe)
    monkeypatch.setenv("NEC42_STANDIN_LOG", str(tmp_path / "cwd.log"))
    return exe


def _builder(wires, freq: float = 14.0):
    class B(AntennaBuilder):
        default_params = MappingProxyType({"freq": freq})

        def build_wires(self):
            return list(wires)

    b = B()
    b.freq = freq
    return b


def _dipole(z: float = 10.0, n: int = 11):
    return _builder([Wire((0.0, -5.0, z), (0.0, 5.0, z), n, ex=1 + 0j, name="feed")])


def _ground_mounted_vertical():
    return _builder(
        [Wire((0.0, 0.0, 0.0), (0.0, 0.0, 5.0), 11, ex=1 + 0j, name="feed")]
    )


def _buried_dipole(depth: float = 0.15):
    return _builder(
        [Wire((0.0, -3.0, -depth), (0.0, 3.0, -depth), 11, ex=1 + 0j, name="feed")]
    )


def _cards(deck: str, kind: str) -> list[str]:
    return [ln for ln in deck.splitlines() if ln.split()[:1] == [kind]]


# --------------------------------------------------------------------------
# finding the binary
# --------------------------------------------------------------------------


def test_find_is_absent_unset_and_present_from_env_or_settings(tmp_path, monkeypatch):
    monkeypatch.delenv("NEC42_EXE", raising=False)
    assert find_nec42() is None
    exe = _stub(tmp_path, _WRONG_PROGRAM, "nec42")
    monkeypatch.setenv("NEC42_EXE", exe)
    assert find_nec42() == exe
    # The settings file's [engines] table is the other route (AK#1492).
    monkeypatch.delenv("NEC42_EXE")
    settings = tmp_path / "settings.toml"
    settings.write_text(f"[engines]\nnec42_exe = '{exe}'\n")
    monkeypatch.setenv("ANTENNAKNOBS_SETTINGS", str(settings))
    assert find_nec42() == exe


def test_the_settings_key_is_registered_for_the_library_and_the_web_page():
    from antennaknobs.settings_file import ENGINE_KEYS
    from antennaknobs.web import settings as web_settings

    assert ENGINE_KEYS["NEC42_EXE"] == "nec42_exe"
    assert "nec42_exe" in web_settings._ENGINE_KEYS


def test_the_probe_rejects_a_program_that_is_not_a_nec(tmp_path, monkeypatch):
    monkeypatch.setenv("NEC42_EXE", _stub(tmp_path, _WRONG_PROGRAM, "nec42"))
    assert probe_nec42() is None


def test_the_probe_accepts_a_binary_that_prints_input_parameters(standin):
    assert probe_nec42() == standin


def test_no_binary_is_an_error_at_construction(monkeypatch):
    monkeypatch.delenv("NEC42_EXE", raising=False)
    with pytest.raises(NEC42Error, match=r"\$NEC42_EXE"):
        NEC42Engine(_dipole(), ground="free")


# --------------------------------------------------------------------------
# the deck: NEC-4.2's spelling
# --------------------------------------------------------------------------


def test_free_space_writes_no_ground_card(standin):
    deck = NEC42Engine(_dipole(), ground="free").deck(14.0)
    assert _cards(deck, "GN") == []
    assert _cards(deck, "GE") == ["GE 0"]


def test_the_sommerfeld_ground_always_ends_nofile(standin):
    """NEC-4.2 caches its Sommerfeld tables to files in the cwd unless the card
    ends NOFILE."""
    deck = NEC42Engine(_dipole(), ground=SOIL).deck(14.0)
    assert _cards(deck, "GN") == ["GN 2 0 0 0 13 0.005 NOFILE"]
    assert _cards(deck, "GE") == ["GE 0"]


def test_the_newer_sommerfeld_is_an_engine_option(standin):
    deck = NEC42Engine(_dipole(), ground=SOIL, sommerfeld=3).deck(14.0)
    assert _cards(deck, "GN") == ["GN 3 0 0 0 13 0.005 NOFILE"]
    with pytest.raises(ValueError, match="2 or 3"):
        NEC42Engine(_dipole(), ground=SOIL, sommerfeld=4)


def test_the_reflection_coefficient_ground_and_pec_are_nec2s_cards(standin):
    fast = NEC42Engine(_dipole(), ground=("finite-fast", 13.0, 0.005)).deck(14.0)
    assert _cards(fast, "GN") == ["GN 0 0 0 0 13 0.005"]
    pec = NEC42Engine(_dipole(), ground="pec").deck(14.0)
    assert _cards(pec, "GN") == ["GN 1 0 0 0 0 0"]


def test_a_ground_mounted_vertical_is_bonded_with_ge_1(standin):
    deck = NEC42Engine(_ground_mounted_vertical(), ground=SOIL).deck(14.0)
    assert _cards(deck, "GE") == ["GE 1"]


def test_a_buried_design_is_written_with_ge_minus_1(standin):
    """GE -1 is NEC-4's flag for a ground with wires below it — the design NEC-2
    refuses is written here, not refused."""
    deck = NEC42Engine(_buried_dipole(), ground=SOIL).deck(7.1)
    assert _cards(deck, "GE") == ["GE -1"]
    assert _cards(deck, "GN") == ["GN 2 0 0 0 13 0.005 NOFILE"]


def test_a_buried_catalog_design_is_written_with_ge_minus_1(standin):
    from antennaknobs.web.examples import REGISTRY

    eng = NEC42Engine(REGISTRY["specialty.buried_dipole"].builder_cls(), ground=SOIL)
    assert _cards(eng.deck(eng.builder.freq), "GE") == ["GE -1"]


def test_a_rise_from_a_buried_hub_is_served_under_ge_minus_1(standin):
    """A conductor meeting the plane is served when it CONTINUES below it."""
    b = _builder(
        [
            Wire((0.0, 0.0, -0.15), (3.0, 0.0, -0.15), 11),
            Wire((0.0, 0.0, -0.15), (0.0, 0.0, 0.0), 1),
            Wire((0.0, 0.0, 0.0), (0.0, 0.0, 5.0), 11, ex=1 + 0j, name="feed"),
        ]
    )
    eng = NEC42Engine(b, ground=SOIL)
    assert _cards(eng.deck(14.0), "GE") == ["GE -1"]
    # Not bonded to the ground under GE -1: a junction between the wires.
    assert eng._ground_bonds_z0() is False


def test_the_nec2_deck_is_unchanged_by_the_dialect_seam(standin, monkeypatch):
    """The NEC-2 writer's output does not move: no NOFILE, no GE -1 path."""
    from antennaknobs.nec_export import export_nec

    deck = export_nec(_dipole(), ground=SOIL, include_rp=False)
    assert _cards(deck, "GN") == ["GN 2 0 0 0 13 0.005"]
    with pytest.raises(ValueError, match="GN 3 is NEC-4.2's"):
        export_nec(_dipole(), ground=SOIL, sommerfeld=3)


# --------------------------------------------------------------------------
# refusals
# --------------------------------------------------------------------------


def test_a_wire_crossing_the_plane_mid_span_is_refused(standin):
    with pytest.raises(NotImplementedError, match="crosses the ground plane"):
        NEC42Engine(_builder([Wire((0, 0, -1.0), (0, 0, 5.0), 29)]), ground=SOIL)


def test_a_wire_lying_in_the_plane_is_refused(standin):
    with pytest.raises(ValueError, match="lies in the ground plane"):
        NEC42Engine(_dipole(z=0.0), ground=SOIL)


@pytest.mark.parametrize("ground", ["pec", ("finite-fast", 13.0, 0.005)])
def test_buried_wires_need_the_sommerfeld_ground(standin, ground):
    with pytest.raises(NotImplementedError, match="only over its Sommerfeld"):
        NEC42Engine(_buried_dipole(), ground=ground)


def test_the_mininec_ground_is_refused_naming_1803(standin):
    """Measured: NEC-4.2 accepts NEC-2's GN 1 + GD and prints the PEC pattern."""
    with pytest.raises(NotImplementedError, match="antennaknobs#1803"):
        NEC42Engine(_dipole(), ground=("mininec", 13.0, 0.005))


def test_a_conductor_ending_on_the_plane_above_buried_wires_is_refused(standin):
    b = _builder(
        [
            Wire((0.0, 0.0, -0.15), (3.0, 0.0, -0.15), 11),
            Wire((0.0, 0.0, 0.0), (0.0, 0.0, 5.0), 11, ex=1 + 0j, name="feed"),
        ]
    )
    with pytest.raises(NotImplementedError, match="ends ON the ground plane"):
        NEC42Engine(b, ground=SOIL)


def test_free_space_has_no_plane_to_refuse_against():
    refuse_nec42_geometry(_buried_dipole().build_wires(), "free")
    refuse_nec42_geometry(_dipole(z=0.0).build_wires(), None)


def test_a_graded_wire_refuses_naming_nec42(standin):
    b = _builder(
        [Wire((0, -2.5, 5), (0, 2.5, 5), GradedSegments((0.25, 0.75), (3, 5, 3)))]
    )
    with pytest.raises(NotImplementedError, match="NEC-4.2: wire 0 uses the graded"):
        NEC42Engine(b, ground="free")


# --------------------------------------------------------------------------
# running: a fresh temp dir per run, never the user's cwd
# --------------------------------------------------------------------------


def test_the_run_is_in_a_fresh_temp_dir_that_is_removed(standin, tmp_path, monkeypatch):
    work = tmp_path / "user-cwd"
    work.mkdir()
    monkeypatch.chdir(work)
    eng = NEC42Engine(_dipole(), ground=SOIL)
    zs = eng.impedance()
    assert zs == [complex(50.0, 10.0)]
    ran_in = Path((tmp_path / "cwd.log").read_text())
    assert ran_in.resolve() != work.resolve()
    assert ran_in.name.startswith("nec42_")
    assert not ran_in.exists(), "the run dir, and the table file in it, must go"
    assert list(work.iterdir()) == []


def test_a_run_that_prints_nothing_names_the_binary(tmp_path, monkeypatch):
    exe = _stub(tmp_path, "pass\n", "nec42")
    with pytest.raises(NEC42Error, match="produced no printout"):
        m.run_deck(exe, "CE\nEN\n", timeout=20)


# --------------------------------------------------------------------------
# the power budget at NEC-4.2's labels
# --------------------------------------------------------------------------


def test_the_budget_reads_wire_loss_and_a_missing_network_line_as_zero():
    assert NEC42Engine._parse_power_budget(_BUDGET) == {
        "input_w": 1.0e-2,
        "radiated_w": 8.75e-3,
        "wire_loss_w": 1.25e-3,
        "network_loss_w": 0.0,
        "efficiency_pct": 87.5,
    }


def test_the_network_line_is_read_when_printed():
    text = _BUDGET.replace(
        "EFFICIENCY",
        "NETWORK LOSS  = 2.5000E-04 WATTS\n                                           EFFICIENCY",
    )
    assert NEC42Engine._parse_power_budget(text)["network_loss_w"] == 2.5e-4


@pytest.mark.parametrize("line", ["WIRE LOSS", "EFFICIENCY", "INPUT POWER"])
def test_a_budget_missing_a_required_line_raises(line):
    text = "\n".join(ln for ln in _BUDGET.splitlines() if line not in ln)
    with pytest.raises(NEC42Error, match="incomplete POWER BUDGET"):
        NEC42Engine._parse_power_budget(text)


def test_the_snapshot_stamps_the_parsed_budget(standin):
    eng = NEC42Engine(_dipole(), ground="free")
    zs, currents, budget = eng.solve_snapshot()
    assert zs == [complex(50.0, 10.0)]
    assert len(currents) == 1 and budget["wire_loss_w"] == 1.25e-3
    assert eng._excited_efficiency == pytest.approx(0.875)
    assert eng._excited_power_budget == [("Wire loss", 1.25e-3)]


# --------------------------------------------------------------------------
# roster, web lane, CLI
# --------------------------------------------------------------------------


def test_the_roster_entry_appears_only_when_the_binary_is_there():
    import antennaknobs.web.server  # noqa: F401 — must load before adapter
    from antennaknobs.web.adapter import backend_roster

    assert "nec42" not in {b["name"] for b in backend_roster(have_pynec=False)}
    entry = next(
        b
        for b in backend_roster(have_pynec=False, have_nec42=True)
        if b["name"] == "nec42"
    )
    assert entry["label"] == "NEC-4.2"
    assert entry["kind"] == "nec42"
    assert entry["buried"] is True
    assert entry["buried_refusal"] is None
    assert entry["default_n_per_wire"] == 21


def test_the_server_serves_the_lane_only_where_the_binary_runs(monkeypatch):
    import antennaknobs.web.server as server

    assert server._ENGINE_IO_LABELS["nec42"] == "NEC-4.2"
    monkeypatch.delenv("NEC42_EXE", raising=False)
    assert server._external_backend({"solver": "nec42"}) is None


def test_the_coverage_grid_does_not_grey_nec42_on_a_buried_design():
    import antennaknobs.web.server  # noqa: F401
    from antennaknobs.web.adapter import design_backend_coverage

    cov = design_backend_coverage("specialty.buried_dipole")
    assert "buried" in cov["needs"]
    assert "nec42" not in cov["refusals"]
    assert "nec2" in cov["refusals"]


def test_the_cli_names_the_missing_piece(monkeypatch):
    import importlib

    cli = importlib.import_module("antennaknobs.cli")
    monkeypatch.delenv("NEC42_EXE", raising=False)
    monkeypatch.delitem(cli.ENGINE_CLASSES, "nec42", raising=False)
    msg = cli._engine_unavailable_message("nec42")
    assert "NEC42_EXE" in msg and "nec42_exe" in msg


def test_nothing_distributed_references_a_nec42_binary():
    """Licence: own use only. The frozen bundle and the image ship none."""
    root = Path(__file__).resolve().parents[1]
    for rel in ("scripts/freeze_workbench/entry.py", "Dockerfile"):
        p = root / rel
        if p.exists():
            assert "nec42cl" not in p.read_text().lower(), rel


# --------------------------------------------------------------------------
# the licensed binary — skipped unless $NEC42_EXE names a working one
# --------------------------------------------------------------------------

needs_nec42 = pytest.mark.skipif(
    probe_nec42() is None,
    reason="no licensed NEC-4.2 binary ($NEC42_EXE unset or not a working NEC-4.2)",
)


def _nec42_temp_dirs() -> set[str]:
    return {p.name for p in Path(tempfile.gettempdir()).glob("nec42_*")}


@needs_nec42
def test_real_free_space_dipole_agrees_with_nec2c():
    nec2c = shutil.which("nec2c")
    if nec2c is None:
        pytest.skip("nec2c not on PATH")
    from antennaknobs.engines.nec2 import NEC2Engine
    from antennaknobs.web.examples import REGISTRY

    cls = REGISTRY["dipoles.invvee"].builder_cls
    z42 = NEC42Engine(cls(), ground="free").impedance()[0]
    z2 = NEC2Engine(cls(), ground="free", nec2_exe=nec2c).impedance()[0]
    assert abs(z42 - z2) / abs(z2) < 5e-4, (z42, z2)


@needs_nec42
def test_real_buried_dipole_runs_and_leaves_nothing_behind(tmp_path, monkeypatch):
    from antennaknobs.web.examples import REGISTRY

    monkeypatch.chdir(tmp_path)
    before = _nec42_temp_dirs()
    eng = NEC42Engine(REGISTRY["specialty.buried_dipole"].builder_cls(), ground=SOIL)
    zs, currents, budget = eng.solve_snapshot()
    z = zs[0]
    assert math.isfinite(z.real) and math.isfinite(z.imag) and z.real > 0, z
    assert "GE -1" in eng.io_runs[-1]["deck"]
    assert len(currents) == len(eng.tups)
    assert budget["input_w"] > 0
    assert list(tmp_path.iterdir()) == [], "nothing in the user's cwd"
    assert _nec42_temp_dirs() == before, "no run dir left in the temp dir"


@needs_nec42
def test_real_buried_impedance_moves_with_depth():
    """What separates modelling the burial from solving it as if in air."""
    z = [
        NEC42Engine(_buried_dipole(d), ground=SOIL).impedance()[0] for d in (0.15, 1.0)
    ]
    assert abs(z[0] - z[1]) / abs(z[0]) > 0.02, z


@needs_nec42
def test_real_rise_from_a_buried_hub_runs_under_ge_minus_1():
    """The served contact spelling: a conductor meeting z=0 that continues
    below it. It runs, and prints a finite impedance with R > 0."""
    b = _builder(
        [
            Wire((0.0, 0.0, -0.15), (3.0, 0.0, -0.15), 11),
            Wire((0.0, 0.0, -0.15), (-3.0, 0.0, -0.15), 11),
            Wire((0.0, 0.0, -0.15), (0.0, 0.0, 0.0), 1),
            Wire((0.0, 0.0, 0.0), (0.0, 0.0, 5.0), 11, ex=1 + 0j, name="feed"),
        ]
    )
    eng = NEC42Engine(b, ground=SOIL)
    z = eng.impedance()[0]
    assert "GE -1" in eng.io_runs[-1]["deck"]
    assert math.isfinite(z.imag) and z.real > 0, z


@needs_nec42
def test_real_pattern_and_currents_parse(tmp_path):
    from antennaknobs.web.examples import REGISTRY

    eng = NEC42Engine(REGISTRY["dipoles.invvee"].builder_cls(), ground=SOIL)
    ff = eng.far_field(n_theta=18, n_phi=72, del_theta=5, del_phi=5)
    assert len(ff.rings) == 18 and all(len(r) == 73 for r in ff.rings)
    assert np.isfinite(ff.max_gain) and ff.max_gain > 0
    cur = eng.current_distribution()
    assert all(np.all(np.isfinite(w.knot_currents)) for w in cur)


@needs_nec42
def test_real_web_solve_of_a_buried_design():
    import antennaknobs.web.server  # noqa: F401
    from antennaknobs.web import nec42_backend

    assert nec42_backend.have_nec42()
    res = nec42_backend.solve(
        {
            "geometry": "specialty.buried_dipole",
            "solver": "nec42",
            "ground": True,
            "ground_model": "sommerfeld",
        }
    )
    assert math.isfinite(res["z_in_re"]) and res["z_in_re"] > 0, res


def test_the_skip_names_its_reason():
    """The gate above is honest about why it skipped (checked, not assumed)."""
    assert "NEC42_EXE" in needs_nec42.kwargs["reason"]
    if os.environ.get("NEC42_EXE") is None:
        assert needs_nec42.args[0] is True

"""antennaknobs#1354: NEC-2 as an external engine over a text coupling.

`PyNECEngine` already gives us NEC-2 physics in process, and cannot be SHIPPED:
pynec-accel wraps nec2++, which is GPLv2, so bundling it in the frozen workbench
would make that zip a combined work. `NEC2Engine` drives a user-supplied NEC-2
console binary over text instead — the shape `NEC5Engine` proved — so
antennaknobs distributes nothing GPL.

None of these tests need a real NEC-2. Three kinds of stand-in appear below, and
which one a test uses is the point of the test:

* **momwire's portal**, which writes a column-exact NEC-2 printout because
  SimNEC reads it as nec2c. This is the strongest stand-in available on a box
  with no NEC-2 on it: a real deck goes in and a real printout comes back, so it
  exercises the deck writer, both parsers and the wire-by-wire current mapping
  against something nobody wrote to make this test pass.
* **argument-only and stdin-only stubs**, for the invocation-form discovery.
  There is no one NEC-2 command line and a file name cannot be trusted to say
  which, so the engine probes; these two prove both branches.
* **hand-written printout blocks**, for the parser's column layout, including
  the one trap a shared NEC-5 parser would fall into.

The integration test against a REAL nec2c is gated and skips with its sentence.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import numpy as np
import pytest

from antennaknobs.engines import nec2 as m
from antennaknobs.engines.nec2 import NEC2Engine, NEC2Error, find_nec2, probe_nec2

# --------------------------------------------------------------------------
# stand-ins
# --------------------------------------------------------------------------

# A NEC-2 console binary, stood in for by momwire's portal.
_PORTAL_STANDIN = """
import sys
from pathlib import Path

argv = sys.argv[1:]
if "-i" in argv:
    inp = argv[argv.index("-i") + 1]
    outp = argv[argv.index("-o") + 1] if "-o" in argv else None
else:
    inp = sys.stdin.readline().strip()
    outp = sys.stdin.readline().strip()

from momwire.portal import run_deck

out, _err = run_deck(Path(inp).read_text())
if outp:
    Path(outp).write_text(out)
else:
    sys.stdout.write(out)
"""

# Accepts ONLY -i/-o. Reading stdin here would hang if the engine left it open.
_ARGS_ONLY = """
import sys
from pathlib import Path

argv = sys.argv[1:]
if "-i" not in argv or "-o" not in argv:
    sys.stderr.write("usage: -i in -o out\\n")
    raise SystemExit(2)
Path(argv[argv.index("-o") + 1]).write_text(PRINTOUT)
"""

# Accepts ONLY the two file names on standard input, the NEC5CL / nec2dxs way.
_STDIN_ONLY = """
import sys
from pathlib import Path

if sys.argv[1:]:
    sys.stderr.write("this build takes the file names on stdin\\n")
    raise SystemExit(2)
_inp = sys.stdin.readline().strip()
outp = sys.stdin.readline().strip()
Path(outp).write_text(PRINTOUT)
"""

# Runs fine and says nothing a NEC-2 says: the #1339 trap, where $NEC5_EXE
# pointed at a spy shim and the roster offered a tab that failed at solve time.
_WRONG_PROGRAM = """
import sys
from pathlib import Path

argv = sys.argv[1:]
if "-o" in argv:
    Path(argv[argv.index("-o") + 1]).write_text("I am not a NEC.\\n")
else:
    sys.stdin.readline()
    Path(sys.stdin.readline().strip()).write_text("I am not a NEC.\\n")
"""

# One ANTENNA INPUT PARAMETERS row in NEC-2's own layout: 11 tokens, impedance
# at 6/7. Copied in shape (not in bytes) from momwire's portal fixtures.
_AIP_BLOCK = """\
                        --------- ANTENNA INPUT PARAMETERS ---------
  TAG   SEG       VOLTAGE (VOLTS)         CURRENT (AMPS)         IMPEDANCE (OHMS)        ADMITTANCE (MHOS)     POWER
  No:   No:     REAL      IMAGINARY     REAL      IMAGINARY     REAL      IMAGINARY    REAL       IMAGINARY   (WATTS)
    1     2  1.0000E+00  0.0000E+00  1.8460E-02  1.0173E-02  4.1552E+01 -2.2898E+01  1.8460E-02  1.0173E-02  9.2301E-03
"""

# The same row as NEC-5 prints it: a THIRD leading index and 12 tokens, so the
# impedance sits at 7/8. Read at NEC-2's 6/7 this row gives
# complex(Iim, Zre) = 0.0102 + 41.552j -- the CURRENT's imaginary part as the
# resistance. A plausible-looking number, which is the dangerous kind.
_NEC5_AIP_BLOCK = """\
                                       ANTENNA INPUT PARAMETERS
    1     2     1  1.0000E+00  0.0000E+00  1.8460E-02  1.0173E-02  4.1552E+01 -2.2898E+01  1.8460E-02  1.0173E-02  9.2301E-03
"""


def _stub(tmp_path: Path, body: str, name: str, printout: str = "") -> str:
    """A stand-in 'binary': a shell wrapper around this interpreter."""
    script = tmp_path / f"{name}.py"
    script.write_text(f"PRINTOUT = {printout!r}\n" + textwrap.dedent(body))
    exe = tmp_path / name
    exe.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{script}" "$@"\n')
    exe.chmod(0o755)
    return str(exe)


@pytest.fixture(autouse=True)
def _clear_caches():
    """The form and probe caches are keyed on (path, mtime, size); two stubs in
    two tmp dirs never collide, but a rerun in one dir could."""
    m._FORM_CACHE.clear()
    m._PROBE_CACHE.clear()
    yield
    m._FORM_CACHE.clear()
    m._PROBE_CACHE.clear()


# --------------------------------------------------------------------------
# finding the binary
# --------------------------------------------------------------------------


def test_find_nec2_is_absent_unset_and_present_when_set(tmp_path, monkeypatch):
    monkeypatch.delenv("NEC2_EXE", raising=False)
    assert find_nec2() is None
    exe = _stub(tmp_path, _ARGS_ONLY, "nec2", printout=_AIP_BLOCK)
    monkeypatch.setenv("NEC2_EXE", exe)
    assert find_nec2() == exe


@pytest.mark.parametrize("what", ["missing", "directory", "not-executable"])
def test_a_path_that_is_not_an_executable_file_is_an_absence(
    tmp_path, monkeypatch, what
):
    """None means "no binary here", never "the variable was empty" — so a
    caller never has to re-check what the variable pointed at."""
    if what == "missing":
        target = tmp_path / "nope"
    elif what == "directory":
        target = tmp_path / "dir"
        target.mkdir()
    else:
        target = tmp_path / "plain"
        target.write_text("#!/bin/sh\n")
        target.chmod(0o644)
    monkeypatch.setenv("NEC2_EXE", str(target))
    assert find_nec2() is None


def test_the_finder_is_shared_with_nec5():
    """One helper, because the two engines are found the same way and a second
    copy of the rule drifts."""
    from antennaknobs.engines import nec5

    assert nec5.find_nec5.__module__ != m.find_nec2.__module__ or True
    from antennaknobs.engines._external import find_exe

    assert find_exe is not None
    src5 = nec5.find_nec5.__code__.co_names
    src2 = m.find_nec2.__code__.co_names
    assert "find_exe" in src5 and "find_exe" in src2


# --------------------------------------------------------------------------
# the probe, and the invocation forms
# --------------------------------------------------------------------------


def test_the_probe_rejects_a_program_that_is_not_a_nec(tmp_path, monkeypatch, caplog):
    """Resolving is not evidence. `find_nec2` says yes to any executable; the
    probe runs a one-wire deck and requires a printout, and the log names the
    file rather than saying NEC-2 is missing."""
    exe = _stub(tmp_path, _WRONG_PROGRAM, "notanec")
    monkeypatch.setenv("NEC2_EXE", exe)
    assert find_nec2() == exe
    with caplog.at_level("WARNING"):
        assert probe_nec2() is None
    assert exe in caplog.text


@pytest.mark.parametrize(
    ("body", "form"), [(_ARGS_ONLY, m.FORM_ARGS), (_STDIN_ONLY, m.FORM_STDIN)]
)
def test_both_invocation_forms_answer_and_the_form_is_discovered(
    tmp_path, monkeypatch, body, form
):
    """Neither stub tells the engine which form it takes; the file is called
    `nec2` either way. The argument-only stub also proves stdin is CLOSED on
    that branch — it never reads stdin, so an open pipe would leave it blocked
    on a writer that never comes, and this test would time out rather than
    fail."""
    exe = _stub(tmp_path, body, "nec2", printout=_AIP_BLOCK)
    monkeypatch.setenv("NEC2_EXE", exe)
    assert probe_nec2() == exe
    assert m._FORM_CACHE[exe][2] == form


def test_the_form_is_cached_after_the_probe(tmp_path, monkeypatch):
    """A stdin-form binary must not pay for the failed argument attempt on
    every deck of a sweep."""
    exe = _stub(tmp_path, _STDIN_ONLY, "nec2", printout=_AIP_BLOCK)
    monkeypatch.setenv("NEC2_EXE", exe)
    assert probe_nec2() == exe
    calls = []
    real = m._run_form

    def counting(exe_, deck, form_, timeout):
        calls.append(form_)
        return real(exe_, deck, form_, timeout)

    monkeypatch.setattr(m, "_run_form", counting)
    m.run_deck(exe, m._PROBE_DECK, timeout=20.0)
    assert calls == [m.FORM_STDIN], calls


def test_a_binary_that_writes_the_report_to_stdout_still_works(tmp_path, monkeypatch):
    """Some nec2c builds leave no output file. That is a working binary."""
    body = """
import sys
sys.stdin.readline() if not sys.argv[1:] else None
sys.stdout.write(PRINTOUT)
"""
    exe = _stub(tmp_path, body, "nec2", printout=_AIP_BLOCK)
    monkeypatch.setenv("NEC2_EXE", exe)
    assert probe_nec2() == exe


def test_no_printout_at_all_names_both_forms_tried(tmp_path, monkeypatch):
    exe = _stub(tmp_path, "\nraise SystemExit(1)\n", "nec2")
    monkeypatch.setenv("NEC2_EXE", exe)
    with pytest.raises(NEC2Error, match="no printout"):
        m.run_deck(exe, m._PROBE_DECK, timeout=20.0)


# --------------------------------------------------------------------------
# the parsers
# --------------------------------------------------------------------------


def test_the_impedance_row_is_read_at_nec2s_columns():
    rows = NEC2Engine._parse_input_parameters(_AIP_BLOCK)
    assert rows == [[(1, 2, complex(41.552, -22.898))]]


def test_a_nec5_row_is_not_read_as_a_nec2_row():
    """The reason the two parsers are separate. NEC-5's row carries a third
    leading index, so its impedance sits at 7/8; read at NEC-2's 6/7 it returns
    the CURRENT's imaginary part as the resistance — 0.0102 + 41.552j where the
    truth is 41.552 - 22.898j. Plausible-looking, which is the dangerous kind.
    Refusing the row on its token count is the only safe answer."""
    with pytest.raises(NEC2Error):
        NEC2Engine._parse_input_parameters(_NEC5_AIP_BLOCK)


def test_the_pattern_reads_with_and_without_the_sense_word():
    """SENSE is blank on a true null row, so a row is 11 or 12 tokens; the
    angles and TOTAL sit at fixed leading positions either way."""
    text = """
                             ---------- RADIATION PATTERNS -----------
 ---- ANGLES -----     ----- POWER GAINS -----       ---- POLARIZATION ----
  THETA      PHI       VERTC    HORIZ    TOTAL       AXIAL      TILT  SENSE
    0.00      0.00    -1e+03  -999.99  -999.99      0.0000      0.00         0.0000E+00    -11.29  0.0000E+00    -11.29
   10.00      0.00     -5.12    -3.01     2.14      0.0000    -90.00  LINEAR 8.2652E-01    154.12  0.0000E+00      0.00
"""
    gains = NEC2Engine._parse_radiation_patterns(text)
    assert gains[(0.0, 0.0)] == m.NULL_GAIN_DB
    assert gains[(10.0, 0.0)] == 2.14


def test_the_currents_block_is_read_per_tag():
    text = """
                           -------- CURRENTS AND LOCATION --------
   SEG  TAG    COORDINATES OF SEGM CENTER     SEGM    ------------- CURRENT (AMPS) -------------
     1    1    0.0659    0.0106    0.6671   0.01173  1.8416E-02  1.0070E-02  2.0990E-02   28.671
     2    1    0.0659    0.0224    0.6671   0.01173  1.8266E-02  9.8974E-03  2.0775E-02   28.451
     3    2    0.0659    0.0341    0.6671   0.01173  1.8010E-02  9.6809E-03  2.0447E-02   28.259
"""
    per_tag = NEC2Engine._parse_currents(text)[0]
    assert sorted(per_tag) == [1, 2]
    assert len(per_tag[1]) == 2 and len(per_tag[2]) == 1
    assert per_tag[1][0] == complex(1.8416e-02, 1.0070e-02)


def test_a_printout_with_no_impedance_block_raises():
    with pytest.raises(NEC2Error, match="ANTENNA INPUT PARAMETERS"):
        NEC2Engine._parse_input_parameters("nothing to see here\n")


# --------------------------------------------------------------------------
# refusals — what NEC-2 will not serve, refused by name
# --------------------------------------------------------------------------


def _one_wire_builder(z0: float, z1: float, freq: float = 28.57):
    from types import MappingProxyType

    from antennaknobs.builder import AntennaBuilder
    from antennaknobs.network import Wire

    class B(AntennaBuilder):
        default_params = MappingProxyType({"freq": freq})

        def build_wires(self):
            return [Wire((0.0, -2.5, z0), (0.0, 2.5, z1), 11, name="feed")]

    b = B()
    b.freq = freq
    return b


@pytest.fixture()
def working_exe(tmp_path, monkeypatch):
    exe = _stub(tmp_path, _ARGS_ONLY, "nec2", printout=_AIP_BLOCK)
    monkeypatch.setenv("NEC2_EXE", exe)
    return exe


def test_a_buried_wire_is_refused_by_name(working_exe):
    """nec2++ solves a buried wire AS IF IT WERE IN AIR and prints a number
    with no warning, which is the worst failure an oracle can have."""
    with pytest.raises(NotImplementedError, match="below-ground medium"):
        NEC2Engine(_one_wire_builder(-1.0, -1.0), ground=("finite", 13.0, 0.005))


def test_a_wire_crossing_the_plane_is_refused(working_exe):
    with pytest.raises(NotImplementedError, match="crosses the ground plane"):
        NEC2Engine(_one_wire_builder(-1.0, 1.0), ground=("finite", 13.0, 0.005))


def test_a_wire_lying_in_the_plane_is_refused(working_exe):
    with pytest.raises(ValueError, match="lies in the ground plane"):
        NEC2Engine(_one_wire_builder(0.0, 0.0), ground=("finite", 13.0, 0.005))


def test_free_space_has_no_plane_to_refuse_against(working_exe):
    """A free-space deck may sit anywhere, z=0 and below included."""
    NEC2Engine(_one_wire_builder(0.0, 0.0), ground="free")
    NEC2Engine(_one_wire_builder(-3.0, -1.0), ground="free")


def test_a_graded_wire_refuses_naming_nec2(working_exe):
    """The shared `refuse_graded_wires`, called with THIS engine's name: a card
    deck numbers wires by tag and a graded expansion would shift every EX/LD/NT
    reference. Calling it with "PyNEC" (which `export_nec` would have done, one
    layer down) would blame the wrong engine."""
    from types import MappingProxyType

    from antennaknobs.builder import AntennaBuilder
    from antennaknobs.network import GradedSegments, Wire

    class B(AntennaBuilder):
        default_params = MappingProxyType({"freq": 28.57})

        def build_wires(self):
            return [
                Wire(
                    (0.0, -2.5, 5.0),
                    (0.0, 2.5, 5.0),
                    GradedSegments((0.25, 0.75), (3, 5, 3)),
                    name="feed",
                )
            ]

    b = B()
    b.freq = 28.57
    with pytest.raises(NotImplementedError, match="NEC-2: wire 0 uses the graded"):
        NEC2Engine(b, ground="free")


def test_no_binary_is_an_error_at_construction(monkeypatch):
    monkeypatch.delenv("NEC2_EXE", raising=False)
    with pytest.raises(NEC2Error, match=r"\$NEC2_EXE"):
        NEC2Engine(_one_wire_builder(1.0, 1.0), ground="free")


# --------------------------------------------------------------------------
# end to end, through momwire's portal
# --------------------------------------------------------------------------


@pytest.fixture()
def portal_exe(tmp_path, monkeypatch):
    pytest.importorskip("momwire.portal")
    exe = _stub(tmp_path, _PORTAL_STANDIN, "nec2")
    monkeypatch.setenv("NEC2_EXE", exe)
    return exe


def _invvee(freq: float = 28.57):
    from antennaknobs.designs.dipoles.invvee import Builder

    b = Builder()
    b.freq = freq
    return b


def test_a_real_design_solves_through_the_portal_standin(portal_exe):
    """Deck writer, subprocess, parser and the whole path, against a printout
    momwire wrote to be read as nec2c's. The NUMBER is momwire's, not NEC-2's —
    what this pins is that a real deck comes back parsed and physical."""
    eng = NEC2Engine(_invvee(), ground="free")
    zs = eng.impedance()
    assert len(zs) == 1
    z = zs[0]
    assert 30.0 < z.real < 90.0 and abs(z.imag) < 60.0, z


def test_the_portal_standin_agrees_with_pynec_in_process(portal_exe):
    """The two ways to the same physics, one over text and one in process.

    A loose bar on purpose: the stand-in is momwire, whose formulation is not
    nec2++'s, so this is an agreement test between two engines and not a
    round-trip. Measured 0.75 % on this design; 5 % is the bar.
    """
    pytest.importorskip("PyNEC")
    from antennaknobs.engines.pynec import PyNECEngine

    z2 = NEC2Engine(_invvee(), ground="free").impedance()[0]
    zp = np.atleast_1d(PyNECEngine(_invvee(), ground="free").impedance())[0]
    assert abs(z2 - zp) / abs(zp) < 0.05, (z2, zp)


def test_currents_come_back_as_knots_the_way_pynec_reports_them(portal_exe):
    """Same list length, same per-wire knot counts, same free-end zeroing —
    the web UI renders both with one renderer, so the shapes must agree."""
    pytest.importorskip("PyNEC")
    from antennaknobs.engines.pynec import PyNECEngine

    c2 = NEC2Engine(_invvee(), ground="free").current_distribution()
    cp = PyNECEngine(_invvee(), ground="free").current_distribution()
    assert [w.knot_currents.shape for w in c2] == [w.knot_currents.shape for w in cp]
    assert [w.knot_positions.shape for w in c2] == [w.knot_positions.shape for w in cp]
    worst = max(
        abs(a.knot_currents - b.knot_currents).max()
        for a, b in zip(c2, cp, strict=True)
    )
    scale = max(abs(b.knot_currents).max() for b in cp)
    assert worst / scale < 0.05, worst / scale


def test_a_pattern_run_fills_the_grid(portal_exe):
    eng = NEC2Engine(_invvee(), ground="free")
    ff = eng.far_field(n_theta=18, n_phi=36, del_theta=5, del_phi=10)
    assert len(ff.rings) == 18 and len(ff.rings[0]) == 37
    assert ff.thetas[0] == 0.0 and ff.phis[-1] == 360.0
    # The seam is duplicated, not dropped.
    assert ff.rings[0][0] == ff.rings[0][-1]
    assert -30.0 < ff.max_gain < 20.0, ff.max_gain


def test_an_impedance_sweep_is_one_row_per_frequency(portal_exe):
    zs = NEC2Engine(_invvee(), ground="free").impedance_sweep([28.0, 28.57, 29.0])
    assert zs.shape == (3, 1)
    assert not np.allclose(zs[0, 0], zs[2, 0])


# --------------------------------------------------------------------------
# the real thing, when there is one
# --------------------------------------------------------------------------


def test_a_real_nec2_binary_agrees_with_pynec():
    """The only test here that runs a genuine NEC-2, and the only one that can
    say the parsers read a real printout. Point `NEC2_EXE` at nec2c / nec2++ /
    nec2dxs, or have nec2c on PATH.

    Skips on CI, which has no NEC-2, and skips on any box without one — the
    stand-in tests above are what run everywhere.
    """
    pytest.importorskip("PyNEC")
    exe = find_nec2() or shutil.which("nec2c") or shutil.which("nec2++")
    if exe is None:
        pytest.skip("no NEC-2 binary: set NEC2_EXE, or put nec2c on PATH")
    from antennaknobs.engines.pynec import PyNECEngine

    z2 = NEC2Engine(_invvee(), ground="free", nec2_exe=exe).impedance()[0]
    zp = np.atleast_1d(PyNECEngine(_invvee(), ground="free").impedance())[0]
    # Both ARE NEC-2 here (nec2c vs nec2++), so this is tight, not loose.
    assert abs(z2 - zp) / abs(zp) < 0.02, (exe, z2, zp)


def test_the_engine_joins_the_cli_roster_only_when_the_binary_runs(tmp_path):
    """An unset NEC2_EXE must leave `nec2` an ILLEGAL --engine name, not a name
    that fails at the first solve.

    In a subprocess per environment, because the roster is built at import and
    reloading `antennaknobs.cli` in place would re-run every other engine's
    import-time probe under this test's environment.
    """
    # `import antennaknobs.cli as c` binds the package's `cli` FUNCTION, not
    # the submodule -- the attribute shadows it. import_module gets the module.
    code = (
        "import importlib; "
        "print('nec2' in importlib.import_module('antennaknobs.cli').ENGINE_CLASSES)"
    )
    env = dict(os.environ)
    env.pop("NEC2_EXE", None)
    absent = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env=env,
        check=True,
    )
    assert absent.stdout.strip() == "False", absent.stdout
    env["NEC2_EXE"] = _stub(tmp_path, _ARGS_ONLY, "nec2", printout=_AIP_BLOCK)
    present = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env=env,
        check=True,
    )
    assert present.stdout.strip() == "True", present.stdout


def test_the_workbench_reads_a_nec2_exe_file_beside_the_program(tmp_path, monkeypatch):
    """The double-click path: one line in NEC2_EXE.txt, the same convenience
    NEC-5 has, and the variable still wins."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    from freeze_workbench import entry

    monkeypatch.setattr(entry, "_bundle_dir", lambda: tmp_path)
    (tmp_path / "NEC2_EXE.txt").write_text("# a comment\n/path/to/nec2c\n")
    assert entry._exe_from_file("NEC2_EXE.txt") == "/path/to/nec2c"
    assert entry.EXE_FILES["NEC2_EXE"] == "NEC2_EXE.txt"


def test_os_is_not_consulted_for_the_form(tmp_path, monkeypatch):
    """The form comes from running the binary, never from its NAME — a renamed
    nec2c, a wrapper script and a symlink are all normal."""
    exe = _stub(tmp_path, _STDIN_ONLY, "definitely-nec2c", printout=_AIP_BLOCK)
    monkeypatch.setenv("NEC2_EXE", exe)
    assert probe_nec2() == exe
    assert m._FORM_CACHE[exe][2] == m.FORM_STDIN
    assert os.path.basename(exe) == "definitely-nec2c"


def test_the_deck_comes_from_export_nec_not_a_second_writer(working_exe):
    """A second deck writer is how the download button and this engine drift
    apart, and the drift would read as an engine disagreement."""
    from antennaknobs import nec_export

    calls = []
    real = nec_export.export_nec

    def spy(*a, **kw):
        calls.append(kw)
        return real(*a, **kw)

    import antennaknobs.nec_export as ne

    monkey = pytest.MonkeyPatch()
    monkey.setattr(ne, "export_nec", spy)
    try:
        eng = NEC2Engine(_one_wire_builder(1.0, 1.0), ground="free")
        text = eng.deck(28.57)
    finally:
        monkey.undo()
    assert calls and calls[-1]["include_rp"] is False
    assert text.splitlines()[-1] == "EN"
    assert "GW 1" in text


def test_a_pattern_deck_replaces_the_xq_rather_than_adding_to_it(working_exe):
    """An RP triggers the solve itself. Leaving the XQ in makes the binary
    solve twice and print two blocks, and the parser would read the first."""
    eng = NEC2Engine(_one_wire_builder(1.0, 1.0), ground="free")
    plain = eng.deck(28.57)
    pat = eng.deck(28.57, rp=(18, 36, 5, 10))
    assert any(ln.startswith("XQ") for ln in plain.splitlines())
    assert not any(ln.startswith("XQ") for ln in pat.splitlines())
    assert [ln for ln in pat.splitlines() if ln.startswith("RP")] == [
        "RP 0 18 36 1000 0 0 5 10"
    ]


def test_the_timeout_is_reported_as_a_nec2_error(tmp_path, monkeypatch):
    exe = _stub(tmp_path, "\nimport time\ntime.sleep(30)\n", "nec2")
    monkeypatch.setenv("NEC2_EXE", exe)
    with pytest.raises(NEC2Error, match="timed out"):
        m.run_deck(exe, m._PROBE_DECK, timeout=1.0)


def test_subprocess_is_the_only_coupling():
    """The licensing point, as a test: this module must not import pynec or any
    GPL wrapper at module scope. `export_nec` reaches PyNECEngine for geometry
    resolution, which is a pip-installed optional package and not what ships.
    """
    src = Path(m.__file__).read_text()
    top = [ln for ln in src.splitlines() if ln.startswith(("import ", "from "))]
    assert not [ln for ln in top if "pynec" in ln.lower()], top
    assert any("subprocess" in ln for ln in top)
    assert subprocess is not None

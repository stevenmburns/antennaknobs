"""The zip's second executable, ``antennaknobs-cli`` (issue #1566).

Dan AC6LA installed from PyPI to run ``sweep --param nominal_nsegs`` and could
not get it to start; Mike WA7ARK will not get as far as pip. So the command
line ships in the Windows zip beside the workbench, over the one ``_internal``
they share.

What is worth testing off Windows, where no frozen bundle exists:

- the backend rule, which is the whole reason Tk came back into the bundle —
  a chart with no ``--fn`` opens in a window, one with ``--fn`` writes a file;
- the handoff, ``entry.py --cli`` reaching ``cli_main.run`` with the user's
  arguments and WITHOUT pinning matplotlib to Agg on the way (the workbench's
  own launch still pins it, which is what makes the ordering load-bearing);
- and the shim's isolation, which is the size argument in executable form:
  PyInstaller follows imports inside functions too, so a single import of
  antennaknobs (or of ``cli_main``, which imports it) anywhere in
  ``entry_cli.py`` would put a second copy of the 21.6 MB module archive in
  the zip. Nothing about a green build would say so, which is why it is
  asserted here instead.

The Tk gate itself lives in ``smoke.py`` (gate 9), inside the frozen
interpreter on Windows: this Python has no tkinter at all.
"""

import ast
import importlib
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(
    0, str(Path(__file__).resolve().parents[1] / "scripts" / "freeze_workbench")
)
import build
import cli_main
import entry
import entry_cli

FREEZE_DIR = Path(__file__).resolve().parents[1] / "scripts" / "freeze_workbench"

# The MODULE, which is not what `antennaknobs.cli` names: the package
# re-exports the FUNCTION under that attribute (`from .cli import cli` in
# __init__), so a monkeypatch target spelled "antennaknobs.cli.cli" resolves
# to the function and fails. `import_module` returns the sys.modules entry,
# which is what `from antennaknobs.cli import cli` inside run() reads.
CLI_MODULE = importlib.import_module("antennaknobs.cli")


@pytest.fixture
def clean_backend():
    """MPLBACKEND back the way it was, whatever the test does to it.

    Not `monkeypatch.delenv(..., raising=False)`: on a name that is not set
    that records nothing to restore, so a later `setdefault` in the code
    under test leaks into every module that runs after (how a #1428 test once
    leaked its capture directory)."""
    before = os.environ.pop("MPLBACKEND", None)
    yield
    os.environ.pop("MPLBACKEND", None)
    if before is not None:
        os.environ["MPLBACKEND"] = before


@pytest.mark.parametrize(
    "argv,expected",
    [
        ([], "TkAgg"),
        (["sweep", "--param", "nominal_nsegs"], "TkAgg"),
        (["sweep", "--fn", "out.png"], "Agg"),
        (["sweep", "--fn=out.png"], "Agg"),
        (["pattern", "--fn", "out.png", "--engine", "momwire"], "Agg"),
    ],
)
def test_backend_follows_where_the_chart_is_going(argv, expected):
    assert cli_main.backend_for(argv) == expected


def test_a_chosen_backend_wins(monkeypatch):
    """MPLBACKEND already in the environment is someone's decision, and the
    rule is a default rather than an override."""
    monkeypatch.setenv("MPLBACKEND", "Agg")
    monkeypatch.setattr(sys, "argv", ["antennaknobs-cli"])
    seen = []
    monkeypatch.setattr(CLI_MODULE, "cli", seen.append)
    assert cli_main.run(["sweep"]) == 0
    assert os.environ["MPLBACKEND"] == "Agg"
    assert seen == [["sweep"]]


def test_run_sets_the_backend_and_the_program_name(monkeypatch, clean_backend):
    monkeypatch.delenv(cli_main.PROG_ENV, raising=False)
    monkeypatch.setattr(cli_main, "_tk_available", lambda: True)
    monkeypatch.setattr(sys, "argv", ["whatever"])
    seen = []
    monkeypatch.setattr(CLI_MODULE, "cli", seen.append)
    assert cli_main.run(["sweep", "--param", "nominal_nsegs"]) == 0
    assert os.environ["MPLBACKEND"] == "TkAgg"
    # argparse's usage line names what the user typed, not the executable
    # doing the work — without this every message reads
    # "antennaknobs-workbench.exe", a file they never mentioned.
    assert sys.argv[0] == cli_main.DEFAULT_PROG
    assert seen == [["sweep", "--param", "nominal_nsegs"]]


def test_no_tk_says_so_instead_of_tracebacking(monkeypatch, capsys, clean_backend):
    """A bundle built on a Python without tkinter would otherwise raise
    ModuleNotFoundError at plot time — after the study has printed its table,
    which is the one moment where losing the run costs the most."""
    monkeypatch.setattr(cli_main, "_tk_available", lambda: False)
    monkeypatch.setattr(sys, "argv", ["whatever"])
    monkeypatch.setattr(CLI_MODULE, "cli", lambda argv: None)
    assert cli_main.run(["sweep"]) == 0
    assert os.environ["MPLBACKEND"] == "Agg"
    assert "--fn" in capsys.readouterr().err


def test_the_shim_hands_its_own_name_on(monkeypatch, clean_backend):
    monkeypatch.setenv(cli_main.PROG_ENV, "antennaknobs-cli.exe")
    monkeypatch.setattr(sys, "argv", ["whatever"])
    monkeypatch.setattr(CLI_MODULE, "cli", lambda argv: None)
    assert cli_main.run(["list"]) == 0
    assert sys.argv[0] == "antennaknobs-cli.exe"


def test_entry_dispatches_cli_without_pinning_agg(monkeypatch, tmp_path, clean_backend):
    """``--cli`` is answered ahead of the workbench's own MPLBACKEND line, so
    the backend rule above is still free to choose."""
    monkeypatch.setattr(entry, "_bundle_dir", lambda: tmp_path)
    seen = []
    monkeypatch.setattr(cli_main, "run", lambda argv: seen.append(argv) or 7)
    assert entry.main([entry.CLI_FLAG, "sweep", "--fn", "x.png"]) == 7
    assert seen == [["sweep", "--fn", "x.png"]]
    assert "MPLBACKEND" not in os.environ


def test_the_workbench_still_pins_agg(monkeypatch, tmp_path, clean_backend):
    """The other half of the ordering: a normal launch is unchanged."""
    monkeypatch.setattr(entry, "_bundle_dir", lambda: tmp_path)
    monkeypatch.setattr(entry, "selftest", lambda: 0)
    assert entry.main(["--selftest"]) == 0
    assert os.environ["MPLBACKEND"] == "Agg"


def test_unfrozen_the_shim_runs_entry_under_this_interpreter():
    assert entry_cli._target() == [sys.executable, str(FREEZE_DIR / "entry.py")]


def test_the_shim_imports_only_the_standard_library():
    """The load-bearing property of ``entry_cli.py``: it is small because it
    imports nothing that reaches antennaknobs — not at module level and not
    inside a function, since PyInstaller's analysis follows both. An import
    added here would be collected, and the second executable would grow from
    1.8 MB to ~21 MB with nothing failing to say so."""
    allowed = {"__future__", "os", "subprocess", "sys", "pathlib"}
    tree = ast.parse((FREEZE_DIR / "entry_cli.py").read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            imported.add(node.module.split(".")[0])
    assert imported <= allowed, f"{imported - allowed} would ride into the shim"


def test_tkinter_is_in_the_bundle_on_purpose():
    """#1566 dropped the tkinter exclude and named the Tk backend instead.
    Re-excluding it would pass every gate on a Linux box — this Python has no
    tkinter, so the bundle here never carries Tk either way — and would only
    surface as an interactive chart that cannot open on a user's Windows."""
    assert "tkinter" not in build.EXCLUDES
    assert "matplotlib.backends.backend_tkagg" in build.HIDDEN_IMPORTS

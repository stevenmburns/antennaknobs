"""The command line, run inside the frozen bundle (issue #1566).

``antennaknobs-cli[.exe]`` in the zip is a ~1.8 MB shim (``entry_cli.py``)
whose whole job is to run THIS module inside ``antennaknobs-workbench[.exe]``
beside it, through that program's ``--cli`` mode. So this file is where the
CLI actually starts: it picks matplotlib's backend from the argument list and
then hands the arguments to ``antennaknobs.cli.cli`` unchanged.

WHY A SHIM AND NOT A SECOND FROZEN PROGRAM. PyInstaller gives each program
its own module archive, and in one-dir mode that archive is APPENDED TO THE
EXECUTABLE rather than left in ``_internal``: measured here on 2026-09-17,
``antennaknobs-workbench`` is 21.7 MB of bootloader plus a 21.6 MB PYZ, and
_internal is 322 MB. A second full entry point therefore shares the 322 MB
(one ``_internal``, as the issue asks) but NOT the 21.6 MB archive, which it
would carry a second copy of — about +21 MB on a 76 MB download, for a
program that is the same code. The shim carries only the stdlib it imports
itself (1.8 MB, measured), so the second executable costs a bootloader and
the zip does not grow by a fifth. It is the same shape momwire's EZNEC
drop-in ships: one frozen engine, thin launchers beside it that run it.

The backend rule (issue #1566): a chart with nowhere to go is a chart nobody
sees, so a run that names no ``--fn`` gets ``TkAgg`` and opens a window with
matplotlib's toolbar — zoom and pan on the Smith chart, which is the whole
reason Tk is back in the bundle. A run that names ``--fn`` is writing a file
and gets ``Agg``, which needs no display. An ``MPLBACKEND`` already set in
the environment wins over both, because someone who set it meant it; and a
bundle with no Tk in it says so in one line and falls back to ``Agg`` rather
than ending a finished run in a traceback.

The backend has to be decided BEFORE anything imports ``pyplot``, since
matplotlib picks its backend at that first import. Nothing in antennaknobs
imports pyplot at module level (``sweep.py`` and ``far_field.py`` both import
it inside their plotting functions), so setting the variable here, before the
``antennaknobs`` import below, is early enough.
"""

from __future__ import annotations

import importlib.util
import os
import sys

# The one flag this module answers itself rather than passing on, so the
# smoke can prove Tk from inside the frozen interpreter (see selftest_tk).
TK_SELFTEST_FLAG = "--selftest-tk"
# What `entry_cli.py` was called, so argparse's usage line names the program
# the user typed rather than the one running the code. Without it every usage
# and error message in the frozen CLI reads "antennaknobs-workbench.exe",
# which is a file the user never mentioned.
PROG_ENV = "ANTENNAKNOBS_CLI_PROG"
DEFAULT_PROG = "antennaknobs-cli"


def backend_for(argv: list[str]) -> str:
    """The matplotlib backend a run with these arguments wants: ``Agg`` when
    the chart is going to a file, ``TkAgg`` when it is going to a window."""
    for a in argv:
        if a == "--fn" or a.startswith("--fn="):
            return "Agg"
    return "TkAgg"


def _tk_available() -> bool:
    """Whether this bundle can open a window at all. A Windows build made on
    a Python without tkinter (a Store install, a slim one) carries no Tk, and
    asking for TkAgg there ends in a `ModuleNotFoundError` traceback AFTER
    the run has printed its numbers — the worst moment to lose them."""
    return importlib.util.find_spec("tkinter") is not None


def selftest_tk() -> int:
    """Prove the Tk half of the bundle, from inside the frozen interpreter.

    Three things have to be true for an interactive chart to open, and only
    the third is about files PyInstaller had to collect: ``tkinter`` is in
    the archive, matplotlib's Tk backend is too, and Tcl/Tk's own script
    library landed in ``_internal`` — ``tkinter.Tk()`` reads ``init.tcl``
    from it and fails loudly if it is missing. Creating the root and
    destroying it again is therefore the check that the data collection
    worked, which importing alone would not catch.

    Exit codes are three-way on purpose, because "this bundle has no Tk" is a
    fact about the build platform (this Linux box's Python ships no tkinter)
    and not a failure: 0 proved, 3 absent, 1 present but broken. ``smoke.py``
    decides which of those is allowed, from whether its OWN interpreter has
    tkinter.
    """
    try:
        import tkinter
    except ImportError as exc:
        print(f"TK ABSENT: no tkinter in this bundle ({exc})")
        return 3
    try:
        from matplotlib.backends import backend_tkagg

        root = tkinter.Tk()
        patchlevel = root.tk.call("info", "patchlevel")
        root.destroy()
    except Exception as exc:  # noqa: BLE001 — the gate's own report, not a raise
        print(f"TK FAILED: {type(exc).__name__}: {exc}")
        return 1
    print(
        f"tkinter {tkinter.TkVersion}, Tcl/Tk {patchlevel}, "
        f"{backend_tkagg.FigureCanvasTkAgg.__name__} imported"
    )
    print("TK SELFTEST OK")
    return 0


def run(argv: list[str]) -> int:
    """Everything after ``--cli``: the arguments the user typed after
    ``antennaknobs-cli[.exe]``."""
    if argv and argv[0] == TK_SELFTEST_FLAG:
        return selftest_tk()
    prog = os.environ.get(PROG_ENV) or DEFAULT_PROG
    backend = backend_for(argv)
    if backend == "TkAgg" and not _tk_available():
        print(
            f"{prog}: this build carries no Tk, so a chart cannot open in a "
            "window here.\n  The run's numbers still print; --fn <file.png> "
            "writes the chart to a file.",
            file=sys.stderr,
        )
        backend = "Agg"
    os.environ.setdefault("MPLBACKEND", backend)
    sys.argv = [prog, *argv]
    from antennaknobs.cli import cli

    cli(argv)
    return 0


if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1:]))

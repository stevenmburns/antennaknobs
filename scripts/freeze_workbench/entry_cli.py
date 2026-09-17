"""PyInstaller entry point for ``antennaknobs-cli[.exe]`` (issue #1566).

The second executable in the workbench zip, beside
``antennaknobs-workbench[.exe]`` and sharing its one ``_internal``. It is the
command line the pip install spells ``python -m antennaknobs``, for the
people the zip exists for — Dan AC6LA wanting ``sweep --param
nominal_nsegs``, Mike WA7ARK who will not get as far as pip::

    antennaknobs-cli --help
    antennaknobs-cli sweep --param nominal_nsegs --builder dipoles.invvee:dipole
    antennaknobs-cli sweep --engine momwire:bspline --use_smithchart

Every argument is passed through untouched, so the documentation for `python
-m antennaknobs` is the documentation for this.

WHAT THIS FILE IS. A shim, not the program: it runs the workbench executable
beside it with a ``--cli`` flag in front of the user's arguments, and that
program runs `cli_main.run`, which is where the backend rule and the call
into ``antennaknobs.cli.cli`` live. The reason is size, measured: a PyInstaller
one-dir program keeps its module archive INSIDE its executable (the workbench
is 21.7 MB of bootloader plus a 21.6 MB PYZ), so a second full entry point
would ship a second copy of that archive — about +21 MB on a 76 MB zip, for
the same code. This shim imports nothing but the standard library, which
costs a bootloader and 1.8 MB. `cli_main.py`'s docstring has the numbers.

Consequences worth knowing:

- Two processes, not one. The shim starts, the workbench program does the
  work, and the shim returns its exit code. Ctrl-C reaches both (the console
  delivers it to the whole group); the shim waits for the program to finish
  tidying up rather than reporting a number of its own.
- Keep the folder together, as the workbench README already says: if
  ``antennaknobs-workbench[.exe]`` is not beside this one, this program can
  do nothing but say so.
- Unfrozen — running this file with a plain interpreter, which the tests do —
  the same handoff runs ``entry.py`` under ``sys.executable``. Deliberately
  the same shape, and deliberately not an ``import cli_main`` fallback:
  PyInstaller's analysis follows imports inside functions too, so one such
  import anywhere in this file would pull antennaknobs, scipy and matplotlib
  into this shim's archive and undo the whole point of it.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

NAME = "antennaknobs-cli"
WORKBENCH = "antennaknobs-workbench"
CLI_FLAG = "--cli"
# How the user spelled this program, handed on so argparse's usage line and
# its errors name it rather than the executable doing the work. `cli_main.py`
# reads it; both spellings live apart on purpose (see the note above about
# what this file may import).
PROG_ENV = "ANTENNAKNOBS_CLI_PROG"


def _target() -> list[str]:
    """The command that runs the real program, frozen or not."""
    if getattr(sys, "frozen", False):
        # The suffix is the running executable's: one OS, one spelling of
        # "executable", so this needs no `os.name` test.
        exe = Path(sys.executable).resolve()
        sibling = exe.with_name(WORKBENCH + exe.suffix)
        if not sibling.is_file():
            print(
                f"{NAME}: {sibling.name} is not beside this program.\n"
                f"  {NAME} runs the command line inside it, so the two files "
                "and the\n  _internal folder have to stay together — extract "
                "the whole zip into\n  one folder rather than copying out a "
                "single .exe.",
                file=sys.stderr,
            )
            raise SystemExit(2)
        return [str(sibling)]
    return [sys.executable, str(Path(__file__).resolve().parent / "entry.py")]


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else list(argv)
    env = dict(os.environ, **{PROG_ENV: Path(sys.argv[0]).name or NAME})
    proc = subprocess.Popen([*_target(), CLI_FLAG, *args], env=env)  # noqa: S603 — our own sibling program
    try:
        return proc.wait()
    except KeyboardInterrupt:
        # The console delivered the interrupt to the child as well, so it is
        # already stopping; wait for its own exit code rather than inventing
        # one, and only insist if it will not go.
        try:
            return proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            proc.kill()
            return 130


if __name__ == "__main__":
    raise SystemExit(main())

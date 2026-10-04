"""The command a user typed to run this program, for hints that tell them what
to type next (AK#1769).

A hint that names a command the user cannot run is worse than none: the
signed workbench's command line is ``.\\antennaknobs-cli.exe`` in PowerShell,
and a refusal saying "run `antennaknobs list`" sent a user to "not
recognized as a cmdlet" (QRZ 1003328 #166). So a hint names the program as it
was invoked:

- the frozen shim (``scripts/freeze_workbench/entry_cli.py``) hands on its own
  ``argv[0]`` verbatim through ``COMMAND_ENV``, because the program doing the
  work is a different executable whose ``argv[0]`` the user never typed;
- otherwise ``sys.argv[0]``'s file name, which is what a console script on
  PATH is called; ``python -m antennaknobs`` runs ``__main__.py`` and is
  spelled out.
"""

from __future__ import annotations

import os
import shlex
import sys
from pathlib import Path

# Kept equal to `entry_cli.COMMAND_ENV`, which may import only the standard
# library and so cannot import this module; gated in
# tests/test_cli_papercuts_1769.py.
COMMAND_ENV = "ANTENNAKNOBS_CLI_COMMAND"


def invoked_command() -> str:
    """The program as the user ran it, quoted for their shell when it holds a
    space."""
    typed = os.environ.get(COMMAND_ENV)
    if not typed:
        name = Path(sys.argv[0]).name if sys.argv and sys.argv[0] else ""
        if name in ("", "__main__.py"):
            return "python -m antennaknobs"
        typed = name
    if not any(c.isspace() for c in typed):
        return typed
    # PowerShell runs a quoted path only through the call operator.
    return f'& "{typed}"' if os.name == "nt" else shlex.quote(typed)

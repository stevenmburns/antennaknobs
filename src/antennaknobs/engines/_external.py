"""Locating a user-supplied engine binary — shared by the NEC-5 and NEC-2 wrappers.

Both wrappers drive an executable antennaknobs never ships: NEC-5 because it is
licensed (#825), NEC-2 because bundling one would make the zip a GPL combined
work (#1354). The question "where is it" has the same two answers in both cases
— an explicit path from the caller, else an environment variable — and the same
two non-answers, which is why this is one function rather than two.

The distinction the return value draws is deliberate and is the reason a bare
`os.environ.get` will not do: **None means "no binary here", never "the variable
was empty"**, so a variable pointing at a directory, a missing file or a
non-executable is an absence rather than a path a caller will later fail to
run. What None does NOT mean is "this is the wrong program" — that needs a run,
and each wrapper's own probe is where that lives (`probe_nec5`, `probe_nec2`).
"""

from __future__ import annotations

import os
from pathlib import Path


def find_exe(env_var: str, explicit: str | None = None) -> str | None:
    """The executable named explicitly, else by ``$env_var``; None if neither
    resolves to an executable file."""
    cand = explicit or os.environ.get(env_var)
    if not cand:
        return None
    p = Path(cand).expanduser()
    if p.is_file() and os.access(p, os.X_OK):
        return str(p)
    return None

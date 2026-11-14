"""The pybind-route OpenNECEngine as it stood at dbabbe4f, loaded from git.

The porty rework replaces `engines/opennec.py`; the references the parity
gate holds the new engine to were recorded from this one. It is loaded from
the commit rather than copied so the reference provably comes from the code
that shipped, and it needs pyopennec's pybind module (`nec_context`).
"""

from __future__ import annotations

import subprocess
import sys
import types
from pathlib import Path

OLD_COMMIT = "dbabbe4f"
ROOT = Path(__file__).resolve().parents[2]


def load():
    src = subprocess.run(
        ["git", "show", f"{OLD_COMMIT}:src/antennaknobs/engines/opennec.py"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    # Relative imports resolve against the real engines package.
    mod = types.ModuleType("antennaknobs.engines._opennec_pybind")
    mod.__package__ = "antennaknobs.engines"
    sys.modules[mod.__name__] = mod
    exec(compile(src, f"{OLD_COMMIT}:opennec.py", "exec"), mod.__dict__)
    return mod

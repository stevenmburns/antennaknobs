"""antennaknobs#1405: the workbench selftest names which accelerator build ran.

Since momwire 0.53.0's double build, `accelerated = True` cannot tell an AVX2
machine from a baseline one, so a transcript sent in by a user could not say
which build had loaded. The selftest line now carries `variant = <build>`, next to
the `accelerated = True` the freeze smoke anchors on.
"""

import sys
from pathlib import Path

import momwire

sys.path.insert(
    0, str(Path(__file__).resolve().parents[1] / "scripts" / "freeze_workbench")
)
import entry


def test_the_selftest_line_names_the_accelerator_variant(capsys):
    assert entry.selftest() == 0
    out = capsys.readouterr().out
    assert f"accelerated = {momwire.accelerated}" in out, out
    assert f"variant = {momwire.accelerator_variant}" in out, out

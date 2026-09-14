"""momwire#1038, antennaknobs half: a forced variant that did not load is named.

On the v0.74.0 workbench, `MOMWIRE_FORCE_VARIANT=legacy` on a bundle carrying
only the avx2 and sse2 builds made the selftest print "momwire's C++ accelerator
did not load (OpenMP runtime missing?)". That is the right outcome with the
wrong diagnosis, and it sends whoever set the variable down the libomp path for
nothing. With the variable set, the selftest now names it instead of guessing.
"""

import sys
from pathlib import Path

import momwire

sys.path.insert(
    0, str(Path(__file__).resolve().parents[1] / "scripts" / "freeze_workbench")
)
import entry


def test_a_forced_variant_that_did_not_load_is_named_not_blamed_on_openmp(
    capsys, monkeypatch
):
    monkeypatch.setattr(momwire, "accelerated", False)
    monkeypatch.setenv("MOMWIRE_FORCE_VARIANT", "legacy")
    assert entry.selftest() == 1
    out = capsys.readouterr().out
    assert "MOMWIRE_FORCE_VARIANT='legacy'" in out, out
    # The wrong guess is gone; naming OpenMP as the thing NOT to suspect first
    # is fine.
    assert "OpenMP runtime missing?" not in out, out


def test_without_a_forced_variant_the_openmp_hint_stays(capsys, monkeypatch):
    monkeypatch.setattr(momwire, "accelerated", False)
    monkeypatch.delenv("MOMWIRE_FORCE_VARIANT", raising=False)
    assert entry.selftest() == 1
    assert "OpenMP runtime missing?" in capsys.readouterr().out

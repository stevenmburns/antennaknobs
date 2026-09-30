"""The NEC-4.2 slot's GN 3 against the licensed binary (skip-unless-NEC42_EXE).

The engine is built by the adapter's own factory from a request carrying the
slot's option, not by the constructor, so the seam the workbench uses is the
one that runs. GN 3 is a different Sommerfeld evaluation, so the same design
solves to a slightly different impedance: a difference of zero would mean the
choice never reached the deck, and a large one would mean it changed the
problem rather than the integral.
"""

from __future__ import annotations

import pytest

import antennaknobs.web.server  # noqa: F401 — resolves the adapter import cycle
from antennaknobs.engines.nec42 import NEC42Engine, probe_nec42
from antennaknobs.web import adapter
from antennaknobs.web.examples import REGISTRY

needs_nec42 = pytest.mark.skipif(
    probe_nec42() is None,
    reason="no licensed NEC-4.2 binary ($NEC42_EXE unset or not a working NEC-4.2)",
)


def _z(word: str | None) -> complex:
    req = {"ground": True, "ground_model": "sommerfeld"}
    if word is not None:
        req["model_options"] = {"sommerfeld": word}
    eng = adapter._make_nec42_engine(req, REGISTRY["dipoles.invvee"].builder_cls())
    assert isinstance(eng, NEC42Engine)
    assert eng.sommerfeld == (3 if word == "GN 3" else 2)
    (z,) = eng.impedance()
    return complex(z)


@needs_nec42
def test_invvee_over_sommerfeld_soil_differs_slightly_under_gn3():
    z2, z3 = _z("GN 2"), _z("GN 3")
    assert _z(None) == z2, "the stock request is GN 2"
    d = abs(z3 - z2)
    # Measured 2026-09-30 (release-7768648 nec42cl-omp): Z(GN 2) = 48.5769 -
    # j8.5359, Z(GN 3) = 48.5803 - j8.5413, |dZ| = 0.0064 ohm.
    assert 0.0 < d < 0.5, (z2, z3)
    assert abs(z3 - z2) / abs(z2) < 0.01

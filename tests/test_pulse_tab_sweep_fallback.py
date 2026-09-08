"""The Pulse tab (#1148) sweeps: the engine falls back to per-frequency
solves for a solver without momwire's batched sweep.

Found by driving the tab in the real app after #1255: the single solve was
fine, then the frequency sweep died with ``AttributeError:
'HarringtonSolver' object has no attribute 'compute_impedance_swept'`` and
the readout went blank. Every other served basis carries the batched sweep;
the pulse family is momwire's REFERENCE row and is deliberately not
extended, so the fallback belongs here, not in momwire.

Gate: the fallback sweep equals the single-frequency path at every sample,
and a batched solver still takes the batched path (the fallback is not
silently used for everyone).
"""

import numpy as np
import pytest

from antennaknobs.designs.dipoles.invvee import Builder
from antennaknobs.engines import momwire as engine_mod
from antennaknobs.engines.momwire import MomwireEngine
from momwire import BSplineSolver, HarringtonSolver

FREQS = [27.0, 28.47, 30.0]
GROUND = ("finite-fast", 10.0, 0.002)  # the app's default ground


def test_the_pulse_family_lacks_the_batched_sweep_today():
    """Precondition, asserted so the fallback cannot outlive its reason
    unnoticed: if momwire ever grows the batched sweep on the pulse family,
    this fails and the fallback can be retired."""
    assert not hasattr(HarringtonSolver, "compute_impedance_swept")
    assert hasattr(BSplineSolver, "compute_impedance_swept")
    assert not engine_mod._has_batched_sweep(HarringtonSolver)
    assert engine_mod._has_batched_sweep(BSplineSolver)


@pytest.mark.parametrize("ground", [None, GROUND])
def test_harrington_sweep_matches_the_single_frequency_path(ground):
    eng = MomwireEngine(Builder(), solver=HarringtonSolver, ground=ground)
    zs = np.asarray(eng.impedance_sweep(FREQS))
    assert zs.shape == (len(FREQS), 1)
    for f, row in zip(FREQS, zs, strict=True):
        b = Builder()
        b.freq = f
        z1 = MomwireEngine(b, solver=HarringtonSolver, ground=ground).impedance()[0]
        assert row[0] == pytest.approx(z1, rel=1e-12), (f, row[0], z1)
    # And the sweep is a sweep: the samples differ.
    assert abs(zs[0, 0] - zs[-1, 0]) > 1.0


def test_a_batched_solver_still_takes_the_batched_path(monkeypatch):
    """Delete-the-line in the other direction: the fallback must not have
    quietly replaced the batched route for solvers that carry it."""
    calls = []
    orig = BSplineSolver.compute_impedance_swept

    def spy(self, k_array):
        calls.append(len(k_array))
        return orig(self, k_array)

    monkeypatch.setattr(BSplineSolver, "compute_impedance_swept", spy)
    zs = MomwireEngine(Builder(), solver=BSplineSolver, ground=GROUND).impedance_sweep(
        FREQS
    )
    assert calls == [len(FREQS)]
    assert np.asarray(zs).shape == (len(FREQS), 1)


def test_the_sweep_endpoint_serves_the_pulse_tab_on_the_default_ground():
    """The app path, not the engine: /sweep streams NDJSON, and the Pulse tab
    on the app's default ground (finite, refl-coef) used to stream an error
    line and blank the readout. Every line must be a point."""
    import json

    from fastapi.testclient import TestClient

    from antennaknobs.web import server

    client = TestClient(server.app)
    resp = client.post(
        "/sweep",
        json={
            "geometry": "dipoles.invvee",
            "momwire_model": "pulse",
            "ground": True,
            "freqs_mhz": FREQS,
        },
    )
    assert resp.status_code == 200, resp.text
    lines = [json.loads(ln) for ln in resp.text.splitlines() if ln.strip()]
    assert lines, resp.text
    errors = [ln for ln in lines if "error" in ln]
    assert not errors, errors
    points = [ln for ln in lines if "freq" in ln or "freq_mhz" in ln]
    assert len(points) == len(FREQS), lines

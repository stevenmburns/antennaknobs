"""Unit tests for the knob optimiser (antennaknobs.web.optimize).

The optimiser machinery is exercised with a *stub* solve_fn (a closed-form Z as
a function of the free params) so the tests are fast and deterministic — no MoM
solves. A separate slow-marked test runs one real geometry through it to confirm
the wiring to momwire_solve.
"""

from __future__ import annotations

import math

import pytest

from antennaknobs.web.optimize import _swr, optimize


def test_swr_helper():
    assert _swr(50.0, 0.0, 50.0) == pytest.approx(1.0)  # perfect match
    assert _swr(100.0, 0.0, 50.0) == pytest.approx(2.0)  # 2:1
    assert _swr(25.0, 0.0, 50.0) == pytest.approx(2.0)  # 2:1 the other way
    assert _swr(50.0, 50.0, 50.0) > 2.0  # reactance worsens it
    assert math.isfinite(_swr(1e9, 0.0, 50.0))  # open circuit stays finite


def _linear_reactance(zero_at: float, z_re: float = 50.0):
    """Stub solve_fn: X(x) crosses zero at `zero_at`, R fixed. So resonance
    (|X|) and SWR are both minimised there (Z = z_re + 0j)."""

    def solve(req: dict) -> dict:
        x = float(req["x"])
        return {"z_in_re": z_re, "z_in_im": 100.0 * (x - zero_at), "z0_ohms": 50.0}

    return solve


def test_optimize_finds_the_minimum():
    res = optimize(
        {"x": 0.80},
        [{"name": "x", "min": 0.5, "max": 1.5}],
        "resonance",
        solve_fn=_linear_reactance(1.05),
    )
    assert res["params"]["x"] == pytest.approx(1.05, abs=1e-3)
    assert res["objective_after"] == pytest.approx(0.0, abs=1e-1)
    assert res["objective_after"] < res["objective_before"]
    assert res["improved"] is True
    assert res["n_evals"] > 2


def test_optimize_clamps_to_bounds_when_optimum_is_outside():
    # Reactance zero sits at 1.30 but the user constrained x to <= 1.00.
    res = optimize(
        {"x": 0.80},
        [{"name": "x", "min": 0.5, "max": 1.0}],
        "resonance",
        solve_fn=_linear_reactance(1.30),
    )
    assert res["params"]["x"] == pytest.approx(1.0, abs=1e-3)  # pinned to the bound
    assert 0.5 <= res["params"]["x"] <= 1.0


def test_optimize_swr_objective_matches_z0():
    # Same stub: at x=1.05, Z = 50 + 0j -> SWR 1.0.
    res = optimize(
        {"x": 0.80},
        [{"name": "x", "min": 0.5, "max": 1.5}],
        "swr",
        solve_fn=_linear_reactance(1.05),
    )
    assert res["params"]["x"] == pytest.approx(1.05, abs=1e-2)
    assert res["metrics_after"]["swr"] == pytest.approx(1.0, abs=0.05)


def test_optimize_two_free_params():
    # A 2-D bowl: |X| minimised where both params hit their targets.
    def solve(req: dict) -> dict:
        a, b = float(req["a"]), float(req["b"])
        x_im = 100.0 * (a - 1.10) + 80.0 * (b - 0.90)
        return {"z_in_re": 50.0, "z_in_im": x_im, "z0_ohms": 50.0}

    res = optimize(
        {"a": 1.0, "b": 1.0},
        [{"name": "a", "min": 0.8, "max": 1.3}, {"name": "b", "min": 0.7, "max": 1.1}],
        "resonance",
        solve_fn=solve,
    )
    assert res["objective_after"] < res["objective_before"]
    assert 0.8 <= res["params"]["a"] <= 1.3
    assert 0.7 <= res["params"]["b"] <= 1.1


def test_optimize_rejects_empty_free():
    with pytest.raises(ValueError):
        optimize({"x": 1.0}, [], "swr", solve_fn=_linear_reactance(1.0))


def test_unknown_objective_falls_back_to_swr():
    res = optimize(
        {"x": 0.8},
        [{"name": "x", "min": 0.5, "max": 1.5}],
        "not_a_real_objective",
        solve_fn=_linear_reactance(1.05),
    )
    assert res["objective"] == "swr"


@pytest.mark.antenna_computation_check
def test_optimize_real_geometry_improves_resonance():
    """End-to-end through a real momwire solve (slow): tuning a length knob
    should not worsen, and usually improves, the reactance."""
    from antennaknobs.web.examples import REGISTRY

    name = "broadband.g5rv"
    ex = REGISTRY[name]
    freq = ex.default_freq or 14.0
    base = {"geometry": name, "measurement_freq_mhz": freq, "design_freq_mhz": freq}
    res = optimize(
        base,
        [{"name": "length_factor", "min": 0.85, "max": 1.15}],
        "resonance",
        solve_fn=ex.momwire_solve,
        max_evals=20,
    )
    assert res["objective_after"] <= res["objective_before"]
    assert 0.85 <= res["params"]["length_factor"] <= 1.15

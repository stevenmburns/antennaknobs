"""Knob gradients with no solve on the port-sites path (momwire#1915).

A load's position knob reaches Z through one port's arclength, and a network
value through the reducer alone, so on a trial served from a cached PortSites
their dZ/dknob needs no solve: ``PortSites.dy_dx`` for the position, chained
through the trial's own contraction and reducer, and the reducer's own
response for a network value (`PortSitesSession.gradients`). The band
optimizer then probes only the geometry knobs, by a solve.

The design is `test_optimize_port_sites_1915._CoilL`, all invented: a
geometry knob (``foot_z``, the vertical's foot), the coil's position as a
percentage of the top wire (``coil_pct``), and two network values (the coil's
``coil_uh`` and the station line's ``line_m``).
"""

from __future__ import annotations

import numpy as np
import pytest
from test_optimize_port_sites_1915 import FREQS, PCTS, _builder, _CoilL

from antennaknobs import port_sites
from antennaknobs.band_opt import builder_sweep_fn
from antennaknobs.engines.momwire import MomwireEngine
from antennaknobs.web.optimize_bands import optimize_bands, parse_bands

needs_port_sites = pytest.mark.skipif(
    not port_sites.available(), reason=port_sites.NO_PORT_SITES
)

START = {"foot_z": 0.4, "coil_pct": 38.11, "coil_uh": 4.7, "line_m": 6.4}
DIFFERENTIABLE = ("coil_pct", "coil_uh", "line_m")


def _rebuild_z(**params):
    eng = MomwireEngine(_builder(**params), **port_sites.engine_kwargs())
    return np.asarray(eng.impedance_sweep(FREQS))


def _session_at(params):
    """A session that has found its moving port, and a sweep_fn on it, at
    ``params``: two trials differing in the coil's place alone first."""
    s = port_sites.PortSitesSession()
    sweep = builder_sweep_fn(_builder(), MomwireEngine, 50.0, port_sites=s)
    sweep({**params, "coil_pct": params["coil_pct"] + 3.0}, FREQS)
    sweep(params, FREQS)
    assert s.ready()
    return s, sweep


@needs_port_sites
@pytest.mark.parametrize("pct", [PCTS[1], PCTS[2]])
def test_each_gradient_matches_a_central_difference_of_rebuilds(pct):
    """dZ/dknob per band against a central difference of whole-wire rebuilds,
    at off-knot positions: <= 1e-5 relative. The geometry knob has none."""
    params = {**START, "coil_pct": pct}
    s, sweep = _session_at(params)
    out = sweep(params, FREQS, grad_knobs=params)
    dzs = out["dzs"]
    assert set(dzs) == set(DIFFERENTIABLE)
    steps = {"coil_pct": 1e-4, "coil_uh": 1e-5 * 4.7, "line_m": 1e-5 * 6.4}
    for name, h in steps.items():
        fd = (
            _rebuild_z(**{**params, name: params[name] + h})
            - _rebuild_z(**{**params, name: params[name] - h})
        ) / (2 * h)
        rel = float(np.max(np.abs(dzs[name] - fd) / np.abs(fd)))
        assert rel <= 1e-5, (name, rel, dzs[name], fd)


@needs_port_sites
def test_the_position_gradient_is_the_cache_s_own_central_difference():
    """``dy_dx`` chained through the reducer, against a central difference of
    the cache itself (``PortSites.y`` at x +- h, exact Y, no ``dy_dx``):
    ~1e-7 relative."""
    params = {**START, "coil_pct": PCTS[2]}
    s, sweep = _session_at(params)
    dz = sweep(params, FREQS, grad_knobs={"coil_pct": params["coil_pct"]})["dzs"]
    h = 1e-4
    zp = sweep({**params, "coil_pct": params["coil_pct"] + h}, FREQS)["zs"]
    zm = sweep({**params, "coil_pct": params["coil_pct"] - h}, FREQS)["zs"]
    fd = (zp - zm) / (2 * h)
    assert s.counts["first"] == 1  # every trial above served from one build
    rel = float(np.max(np.abs(dz["coil_pct"] - fd) / np.abs(fd)))
    assert rel <= 1e-7, rel


def _run(sweep, max_evals=40):
    return optimize_bands(
        dict(START),
        [
            {"name": "foot_z", "min": 0.2, "max": 0.8},
            {"name": "coil_pct", "min": 10.0, "max": 90.0},
            {"name": "coil_uh", "min": 2.0, "max": 9.0},
            {"name": "line_m", "min": 4.0, "max": 9.0},
        ],
        parse_bands(",".join(str(f) for f in FREQS)),
        sweep_fn=sweep,
        max_evals=max_evals,
    )


@needs_port_sites
def test_a_four_knob_run_probes_only_the_geometry_knob():
    """Once the moving port is known, each gradient point of the run takes
    ONE finite-difference probe (the geometry knob) and reads the other
    three with no solve."""
    s = port_sites.PortSitesSession()
    res = _run(builder_sweep_fn(_builder(), MomwireEngine, 50.0, port_sites=s))
    g = res["gradients"]
    per = g["probes_per_point"]
    assert per, g
    # Before the moving port is known a point probes all four.
    k = next(i for i, p in enumerate(per) if p == 1)
    assert k <= 2 and all(p == 1 for p in per[k:]), per
    assert g["analytic_columns"] >= 3 * len(per[k:])
    assert s.n_gradients >= 3 * len(per[k:])


@needs_port_sites
def test_gradients_reach_the_same_or_a_better_answer_than_probes():
    """From one start and one budget, the gradient run's final J is no worse
    than the probe run's (both on the whole-wire model, both on the cache)."""
    s_g = port_sites.PortSitesSession()
    res_g = _run(builder_sweep_fn(_builder(), MomwireEngine, 50.0, port_sites=s_g))
    s_p = port_sites.PortSitesSession()
    inner = builder_sweep_fn(_builder(), MomwireEngine, 50.0, port_sites=s_p)

    def probes_only(req, freqs):
        return inner(req, freqs)

    res_p = _run(probes_only)
    assert "gradients" not in res_p
    assert res_g["objective_after"] <= res_p["objective_after"] * (1 + 1e-3), (
        res_g["objective_after"],
        res_p["objective_after"],
    )


def test_a_sweep_without_gradients_changes_nothing():
    """A sweep_fn that does not take grad_knobs (every default run) gets no
    gradient key and no extra sweep call."""
    calls = []
    inner = builder_sweep_fn(_builder(), MomwireEngine, 50.0)
    assert not inner.takes_grad_knobs

    def counted(req, freqs):
        calls.append(1)
        return inner(req, freqs)

    res = _run(counted, max_evals=6)
    assert "gradients" not in res
    assert len(calls) == res["n_solves"]


def test_the_design_has_the_knobs():
    assert set(START) <= set(_CoilL.default_params)

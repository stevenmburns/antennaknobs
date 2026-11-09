"""The momwire layer's swept multi-port admittance (AK#2219).

`antennaknobs.mw.swept_y` stacks core's per-frequency port solutions and
takes each Y's shape from the solution itself. These tests import only
momwire, numpy and the layer, so momwire's CI can run them unchanged
against a momwire PR (#2219: a core change that breaks the contract fails
there, before it ships).

Oracles, per family and per k:
- core's own `compute_y_matrix_swept`, which reads the same stream: equal
  bit for bit;
- the single-point `compute_y_matrix()` at that k, which never read a port
  count and was always right (momwire#1861's oracle): equal at its shape,
  to the swept path's evaluation-order tolerance.

The design with node gaps and no gap feeds is momwire#1861's own case,
where core's sized-by-count swept Y came back empty or broadcast wrongly.
"""

from __future__ import annotations

import numpy as np
import pytest
from momwire import BSplineSolver, RazorSolver, SinusoidalGalerkinSolver

from antennaknobs.mw import swept_y

WL = 299.792458 / 27.0
L = 5.2


def _three_arm(n_gaps: int) -> dict:
    """A straight wire in three pieces; node gaps at the first or both
    junctions, no gap feeds (momwire#1861)."""
    a, b = L / 4, L / 2
    wires = [
        np.array([(0.0, 0.0, 0.0), (0.0, 0.0, a)]),
        np.array([(0.0, 0.0, a), (0.0, 0.0, b)]),
        np.array([(0.0, 0.0, b), (0.0, 0.0, L)]),
    ]
    gaps = [(0, "end", 1.0 + 0j), (1, "end", 1.0 + 0j)][:n_gaps]
    return dict(
        wires=wires,
        n_per_edge_per_wire=[[12], [12], [24]],
        junctions=[[(0, "end"), (1, "start")], [(1, "end"), (2, "start")]],
        feeds=[],
        node_gaps=gaps,
        wavelength=WL,
        wire_radius=1e-3,
    )


def _dipole_two_feeds() -> dict:
    """One straight wire with two gap feeds off its middle."""
    wire = np.array([(0.0, -L / 2, 0.0), (0.0, L / 2, 0.0)])
    return dict(
        wires=[wire],
        n_per_edge_per_wire=[[31]],
        feeds=[(0, 0.4 * L, 1.0 + 0j), (0, 0.65 * L, 1.0 + 0j)],
        wavelength=WL,
        wire_radius=1e-3,
    )


CASES = [
    (cls, name, build)
    for cls in (BSplineSolver, SinusoidalGalerkinSolver, RazorSolver)
    for name, build in (
        ("one node gap", lambda: _three_arm(1)),
        ("two node gaps", lambda: _three_arm(2)),
        ("two gap feeds", _dipole_two_feeds),
    )
]


@pytest.mark.parametrize(
    ("cls", "name", "build"), CASES, ids=[f"{c.__name__}-{n}" for c, n, _ in CASES]
)
def test_the_layer_swept_y_is_the_per_k_y(cls, name, build):
    kw = build()
    k0 = cls(**kw).k
    ks = k0 * np.array([0.9, 1.0, 1.1])
    got = swept_y(cls(**kw), ks)
    n_ports = cls(**kw).compute_y_matrix().shape[0]
    assert got.shape == (3, n_ports, n_ports)
    assert got.dtype == np.complex128
    for i, k in enumerate(ks):
        one = np.asarray(cls(**{**kw, "wavelength": 2 * np.pi / k}).compute_y_matrix())
        np.testing.assert_allclose(got[i], one, rtol=1e-12, atol=0)


@pytest.mark.parametrize(
    ("cls", "name", "build"), CASES, ids=[f"{c.__name__}-{n}" for c, n, _ in CASES]
)
def test_the_layer_reads_the_stream_core_reads(cls, name, build):
    """Where core's own swept Y is right, the layer's equals it bit for bit:
    the two read one stream, so they cannot drift (momwire #252)."""
    kw = build()
    ks = cls(**kw).k * np.array([0.95, 1.05])
    core = np.asarray(cls(**kw).compute_y_matrix_swept(ks), dtype=np.complex128)
    np.testing.assert_array_equal(swept_y(cls(**kw), ks), core)


def test_a_solver_without_the_stream_falls_back_to_its_own_swept_y():
    class Fake:
        def compute_y_matrix_swept(self, ks):
            return np.full((len(ks), 1, 1), 2.0 + 1j)

    got = swept_y(Fake(), [1.0, 2.0])
    assert got.shape == (2, 1, 1) and got.dtype == np.complex128


def test_a_stream_that_changes_port_count_is_refused():
    class Sol:
        def __init__(self, n):
            self.y = np.eye(n)

    class Odd:
        def _port_solutions_swept(self, ks):
            yield Sol(1)
            yield Sol(2)

    with pytest.raises(ValueError, match="changed port count"):
        swept_y(Odd(), [1.0, 2.0])

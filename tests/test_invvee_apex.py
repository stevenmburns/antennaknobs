"""dipoles.invvee_apex — the apex-fed vee, and what the bridge idiom
is worth (issue #898 piece 5).

Values measured 2026-08-12 at the stock 10 m defaults in free space;
pins sit just above measurement. The POINT of the pair of pins is the
gap between them: the bridge-feed reading and the true-vertex reading
are both right for their own model, and this file keeps their distance
a measured number instead of folklore.
"""

import numpy as np
import pytest

from antennaknobs.designs.dipoles.invvee import Builder as Bridge
from antennaknobs.designs.dipoles.invvee_apex import Builder as Apex
from antennaknobs.engines.momwire import MomwireEngine

# Stock defaults, free space, momwire d=2 (2026-08-12).
Z_BRIDGE = 55.107 - 10.284j
Z_APEX = 54.458 - 12.376j


def _z(builder_cls):
    return complex(MomwireEngine(builder_cls(), ground=None).impedance()[0])


@pytest.mark.antenna_computation_check
def test_apex_and_bridge_readings_are_pinned():
    zb, za = _z(Bridge), _z(Apex)
    assert abs(zb - Z_BRIDGE) < 0.5, f"bridge moved: {zb:.3f}"
    assert abs(za - Z_APEX) < 0.5, f"apex moved: {za:.3f}"


@pytest.mark.antenna_computation_check
def test_bridge_idiom_cost_stays_measured():
    """~2.2 Ω at the stock geometry, nearly all reactance (the bridge's
    two extra junctions + 0.1 m of horizontal wire). If this drifts,
    either a feed model changed or the geometry did — both worth seeing."""
    dz = _z(Apex) - _z(Bridge)
    assert 1.0 < abs(dz) < 4.0, f"bridge-vs-apex delta now {dz:.3f}"
    assert abs(dz.imag) > abs(dz.real)  # the cost is reactive


@pytest.mark.antenna_computation_check
def test_apex_vee_runs_on_the_iterative_solvers():
    """The web's hmatrix/arrayblock backends (allowlisted for vertex
    designs since momwire 0.28.1) must give the dense answer through the
    ENGINE path — the accelerated impedance route used to solve a
    node-gap-driven deck with a zero drive (momwire#307's fix)."""
    from momwire.array_block import ArrayBlockSolver
    from momwire.hmatrix import HMatrixSolver

    z_ref = _z(Apex)
    for solver in (HMatrixSolver, ArrayBlockSolver):
        eng = MomwireEngine(Apex(), ground=None, solver=solver)
        z = complex(eng.impedance()[0])
        assert abs(z - z_ref) < 0.05, (solver.__name__, z, z_ref)


def test_vertex_designs_allowlist_the_iterative_backends():
    """`_required_backends`: a vertex-port design gets the wider list
    (iterative solvers included); a PortAtEnd design keeps the narrow
    junction-port list; a design with both is bound by the narrow one."""
    from antennaknobs.designs.wire.sterba_bl import Builder as EndPortDesign
    from antennaknobs.web import adapter

    assert adapter._required_backends(Apex) == adapter._VERTEX_PORT_BACKENDS
    assert adapter._required_backends(EndPortDesign) == adapter._JUNCTION_PORT_BACKENDS


@pytest.mark.antenna_computation_check
def test_apex_vee_solves_end_to_end():
    """The excited path (current distribution + far field) through a
    design driven ONLY by a vertex port — no gap feed anywhere."""
    eng = MomwireEngine(Apex(), ground=None)
    ff = eng.far_field()
    assert np.isfinite(ff.max_gain)
    wires = eng.current_distribution()
    peak = max(np.abs(np.asarray(w.knot_currents)).max() for w in wires)
    assert peak > 0

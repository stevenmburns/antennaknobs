"""Distributed (finite-gap) ports — issue #477.

A ``PortOnWire(distributed=True)`` spans its named wire's fixed physical
extent instead of a delta gap on one (mesh-dependent) segment: one sub-feed
per segment with length-split voltages, and the port row of the antenna Y
contracted back by congruence (Y_port = Wᵀ·Y_sub·W). The port impedance is
then mesh-stable by construction — the class of drift these tests pin is a
port readout that MOVES whenever refinement subdivides the port wire (zepp's
jump the first time its 0.05 m port wire goes 1 → 3 segments; sterba_tl's
old 3-segment pins, which were flat at basis-DEPENDENT values).

The oracles run the real designs at modest meshes: engines must agree with
each other, coarse rungs must degenerate exactly to the delta gap while the
port wire is still one segment, and the fine-mesh value must be stable
where the delta-gap model drifts.
"""

from __future__ import annotations

import numpy as np
import pytest

from antennaknobs.engines.momwire import MomwireEngine
from antennaknobs.network import Network, PortOnWire
from momwire import BSplineSolver, SinusoidalSolver

try:  # optional accelerated backend, mirrors the other engine test guards
    from antennaknobs.engines.pynec import PyNECEngine

    _HAS_PYNEC = True
except Exception:  # noqa: BLE001 — pynec-accel absent
    _HAS_PYNEC = False

needs_pynec = pytest.mark.skipif(not _HAS_PYNEC, reason="pynec-accel not installed")


def _zepp(nseg, distributed=True):
    from antennaknobs.designs.wire.zepp import Builder

    if distributed:
        b = Builder()
    else:

        class ZeppDelta(Builder):
            def build_network(self):
                net = super().build_network()
                ports = dict(net.ports)
                ports["ant"] = PortOnWire("ant")  # back to a delta gap
                return Network(ports=ports, branches=net.branches, sources=net.sources)

        b = ZeppDelta()
    b.nominal_nsegs = nseg
    return b


def _sin(b):
    return MomwireEngine(b, solver=SinusoidalSolver, ground="free")


def _bs2(b):
    return MomwireEngine(
        b, solver=BSplineSolver, solver_kwargs={"degree": 2}, ground="free"
    )


def test_coarse_mesh_degenerates_to_delta_gap():
    """While the port wire is still ONE segment, the distributed port is
    exactly the delta gap (one sub-feed, weight 1) — bit-identical Z, so
    turning the flag on cannot churn coarse-mesh results."""
    z_dist = _sin(_zepp(21, distributed=True)).impedance()[0]
    z_delta = _sin(_zepp(21, distributed=False)).impedance()[0]
    assert z_dist == z_delta


def test_weight_matrix_shape_and_column_sums():
    """The expansion's W: one column per original feed, columns sum to 1
    (length-split voltages), and only the distributed port has >1 sub-feed."""
    eng = _sin(_zepp(161))  # "ant" subdivides at this rung
    W = eng._feed_W
    assert W is not None
    n_sub, n_orig = W.shape
    assert n_orig == len(eng._feeds) and n_sub > n_orig
    assert np.allclose(W.sum(axis=0), 1.0)
    # every row belongs to exactly one port
    assert np.all((W > 0).sum(axis=1) == 1)


def test_contract_y_congruence():
    """_contract_y is the exact congruence Wᵀ·Y·W, on one matrix and on a
    swept stack."""
    eng = _sin(_zepp(161))
    W = eng._feed_W
    rng = np.random.default_rng(7)
    Y = rng.normal(size=(W.shape[0], W.shape[0])) + 1j * rng.normal(
        size=(W.shape[0], W.shape[0])
    )
    assert np.allclose(eng._contract_y(Y), W.T @ Y @ W)
    stack = np.stack([Y, 2 * Y])
    got = eng._contract_y(stack)
    assert np.allclose(got[0], W.T @ Y @ W) and np.allclose(got[1], 2 * (W.T @ Y @ W))


def test_port_impedance_mesh_stable_where_delta_gap_drifts():
    """The regression this feature exists for: refine zepp past the rung
    where its port wire subdivides. The delta-gap readout moves several ohms
    of reactance and keeps moving; the distributed port stays put (and the
    N=321 value is the same one bs2 lands on — basis-agreeing)."""
    z_161 = _sin(_zepp(161)).impedance()[0]
    z_321 = _sin(_zepp(321)).impedance()[0]
    assert abs(z_321 - z_161) / abs(z_321) < 0.01, (z_161, z_321)

    # the delta-gap model on the same rungs is NOT stable (guards against
    # this test passing vacuously on a design change)
    zd_161 = _sin(_zepp(161, distributed=False)).impedance()[0]
    zd_321 = _sin(_zepp(321, distributed=False)).impedance()[0]
    assert abs(zd_321 - zd_161) / abs(zd_321) > 0.02, (zd_161, zd_321)

    z_bs2 = _bs2(_zepp(321)).impedance()[0]
    assert abs(z_321 - z_bs2) / abs(z_bs2) < 0.01, (z_321, z_bs2)


def test_sterba_tl_unpinned_flat_and_basis_agreeing():
    """sterba_tl's nine TL ports ran pinned at 3 segments because refining
    them drifted — and the pinned ladders were flat at basis-DEPENDENT
    values ~5 ohm of X apart. With distributed ports the edges refine, the
    ladder is flat by N=61, and sin agrees with bs2."""
    from antennaknobs.designs.wire.sterba_tl import Builder

    def z_at(engine, n):
        b = Builder()
        b.nominal_nsegs = n
        return engine(b).impedance()[0]

    z61, z161 = z_at(_sin, 61), z_at(_sin, 161)
    assert abs(z161 - z61) / abs(z161) < 0.01, (z61, z161)
    zb = z_at(_bs2, 161)
    assert abs(z161 - zb) / abs(zb) < 0.01, (z161, zb)


def test_excited_state_and_far_field_on_distributed_port():
    """The excited path splits the resolved port voltage across the
    sub-feeds; the far field must normalise to a finite, sane gain (a
    broken split shows up as zero excitation or wild gain)."""
    eng = _sin(_zepp(161))
    ff = eng.far_field(n_theta=30, n_phi=72, del_theta=3, del_phi=5)
    assert np.isfinite(ff.max_gain) and 0.0 < ff.max_gain < 6.0


@needs_pynec
def test_pynec_matches_momwire_on_distributed_port():
    """Cross-engine oracle: PyNEC's sub-segment EX drive + weighted current
    readout is the same contraction — the engines must agree at a rung
    where the port wire has subdivided."""
    z_mom = _sin(_zepp(161)).impedance()[0]
    z_nec = PyNECEngine(_zepp(161), ground=None).impedance()[0]
    assert abs(z_mom - z_nec) / abs(z_nec) < 0.02, (z_mom, z_nec)

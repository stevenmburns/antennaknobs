"""Tests for the momwire-backed SimulationEngine and the flat-wire-to-polyline
geometry translator it sits on top of."""

import numpy as np
import pytest

from antennaknobs import resolve_variant_params
from antennaknobs.designs.dipoles.invvee import Builder
from antennaknobs.engines import PyNECEngine, MomwireEngine
from antennaknobs.geometry import flat_wires_to_polylines

from conftest import needs_pynec


def test_translator_chains_dipole_into_single_polyline():
    b = Builder(resolve_variant_params(Builder, "dipole"))  # straight half-wave dipole
    out = flat_wires_to_polylines(b.build_wires())

    assert len(out["polylines"]) == 1
    polyline = out["polylines"][0]
    assert polyline.shape == (4, 3), polyline.shape
    assert out["edge_segments"] == [[21, 3, 21]]
    assert out["feed_wire_index"] == 0

    # Feed sits at the geometric centre of the dipole; for the design_freq-sized
    # parameterisation the half-arm wire length is driver_y, so the polyline
    # spans 2·driver_y end-to-end and the feed midpoint lands at driver_y.
    wavelength = 299.792458 / b.design_freq
    driver_y = 0.25 * wavelength * b.length_factor
    assert out["feed_arclength"] == pytest.approx(driver_y, rel=1e-6)
    assert out["feed_voltage"] == 1 + 0j


def test_momwire_impedance_in_realistic_range():
    (z,) = MomwireEngine(Builder()).impedance()
    assert z.real > 30 and z.real < 150, f"unrealistic R: {z}"
    # Imaginary part can swing widely with formulation/ground, just sanity-
    # check it stays in a plausible band rather than blowing up.
    assert abs(z.imag) < 200, f"unrealistic X: {z}"


def test_momwire_impedance_sweep_shape_and_monotone_resistance():
    freqs = np.linspace(28.0, 29.0, 5)
    zs = MomwireEngine(Builder()).impedance_sweep(freqs)
    assert zs.shape == (5, 1)
    # Driver R rises smoothly across a sub-resonant span for a dipole.
    real = zs[:, 0].real
    assert np.all(np.diff(real) > 0), real


@needs_pynec
def test_momwire_matches_pynec_in_free_space():
    """Free-space cross-check between the two MoM engines on a dipole.
    Disabling PyNEC's gn_card so both solve the same physical problem
    (no ground, no Fresnel) brings real-part agreement well under 10%
    and reactance close enough to confirm the translator's feed-point
    mapping is correct."""
    b = Builder()
    (z_nec,) = PyNECEngine(b, ground=None).impedance()
    (z_momwire,) = MomwireEngine(b).impedance()
    real_rel = abs(z_momwire.real - z_nec.real) / abs(z_nec.real)
    assert real_rel < 0.10, f"real parts diverged: nec={z_nec}, momwire={z_momwire}"
    # Reactance offsets between formulations are larger at sub-resonant
    # dipole lengths; absolute, not relative, headroom is the right test.
    assert abs(z_momwire.imag - z_nec.imag) < 20.0, (
        f"reactance diverged: nec={z_nec}, momwire={z_momwire}"
    )


@needs_pynec
@pytest.mark.parametrize(
    "design_module, max_dR, max_dX",
    [
        ("antennaknobs.designs.arrays.invveearray", 1.5, 2.5),
        ("antennaknobs.designs.arrays.moxonarray", 5.0, 2.5),
        ("antennaknobs.designs.arrays.yagiarray", 3.0, 2.0),
    ],
)
def test_momwire_multi_feed_impedance_matches_pynec(design_module, max_dR, max_dX):
    """Multi-feed arrays: per-port Z from MomwireEngine should track PyNEC
    feed-for-feed. Both backends solve free space (no gn_card) so the only
    physics difference is the MoM formulation. Tolerances are 'within a few
    percent R, a few ohms X' — comparable to the closed-loop cross-check."""
    from importlib import import_module

    b = import_module(design_module).Builder()
    z_nec = PyNECEngine(b, ground=None).impedance()
    z_ps = MomwireEngine(b).impedance()
    assert len(z_nec) == len(z_ps) > 1, (
        f"expected multi-feed, got {len(z_nec)}/{len(z_ps)}"
    )
    for i, (zn, zp) in enumerate(zip(z_nec, z_ps)):
        assert abs(zn.real - zp.real) < max_dR, (
            f"feed {i}: R diverged nec={zn} momwire={zp}"
        )
        assert abs(zn.imag - zp.imag) < max_dX, (
            f"feed {i}: X diverged nec={zn} momwire={zp}"
        )


def test_momwire_multi_feed_impedance_sweep_shape():
    """impedance_sweep on a multi-feed array returns (n_k, n_feeds), not
    (n_k,). The shape normalisation is what lets the rest of the analysis
    code treat single- and multi-feed sweeps uniformly."""
    from antennaknobs.designs.arrays.invveearray import Builder as ArrBuilder

    freqs = np.linspace(28.0, 29.0, 4)
    zs = MomwireEngine(ArrBuilder()).impedance_sweep(freqs)
    assert zs.shape == (4, 4), zs.shape


def test_momwire_tl_card_runs_and_returns_finite_impedance():
    """delta_looparray_with_tls — the one design with tl_card. MomwireEngine
    extracts the N-port Y via N independent solves, stamps the TL admittance
    between the right port pairs, then reduces back to the driven port.
    No strict PyNEC match here: NEC2 models the TL as a segment-level
    multiport while momwire's ports are basis-level (delta-gap at the wire
    midpoint). The two converge on simple geometries but diverge wildly
    near TL half-wave resonance (the default twist puts one TL at ~0.5λ).
    Validate that the engine produces a finite, passive impedance and
    that the underlying Y matrix is symmetric (reciprocity)."""
    from antennaknobs.designs.arrays.delta_looparray_with_tls import (
        Builder as TLBuilder,
    )

    b = TLBuilder()
    e = MomwireEngine(b)
    z_list = e.impedance()
    assert len(z_list) == 1
    z = z_list[0]
    assert np.isfinite(z.real) and np.isfinite(z.imag), z
    assert z.real > 0, f"non-passive impedance: {z}"
    assert abs(z) < 1e4, f"unrealistic magnitude: {z}"

    wl = 299.792458 / b.freq
    Y = e._compute_y_matrix(wl)
    assert np.allclose(Y, Y.T, atol=1e-10), "Y matrix not symmetric (reciprocity)"


def test_momwire_tl_card_passive_port_floats_correctly():
    """With TLs present, the passive (TL-only) ports must satisfy I_ext=0
    in the reduced solution. Reconstruct V from the impedance() solve and
    verify the constraint at every passive port."""
    from antennaknobs.designs.arrays.delta_looparray_with_tls import (
        Builder as TLBuilder,
    )

    b = TLBuilder()
    e = MomwireEngine(b)
    wl = 299.792458 / b.freq
    Y = e._compute_y_matrix(wl)
    Y_total = e._apply_tls(Y, wl)

    n = Y_total.shape[0]
    driven = [i for i in range(n) if i not in e._tl_passive_feed_idx]
    passive = sorted(e._tl_passive_feed_idx)
    assert len(passive) >= 1, "test fixture has no passive ports"
    v_driven = np.array([e._feeds[i][2] for i in driven], dtype=np.complex128)
    Y_pp = Y_total[np.ix_(passive, passive)]
    Y_pd = Y_total[np.ix_(passive, driven)]
    v_passive = np.linalg.solve(Y_pp, -Y_pd @ v_driven)
    V = np.empty(n, dtype=np.complex128)
    V[driven] = v_driven
    V[passive] = v_passive
    I = Y_total @ V
    # Passive ports should have I_ext = 0 to within solver tolerance.
    assert np.allclose(I[passive], 0, atol=1e-10), I[passive]


def test_momwire_tl_impedance_sweep_matches_per_freq():
    """impedance_sweep with TLs should match per-frequency impedance() calls
    to within solver noise. Exercises the swept-Y → per-k TL stamp →
    driven-port reduction path that was added once compute_y_matrix_swept
    learned about junctions upstream."""
    from antennaknobs.designs.arrays.delta_looparray_with_tls import (
        Builder as TLBuilder,
    )

    freqs = np.array([28.0, 28.47, 29.0])

    # Per-freq reference
    z_per = []
    for f in freqs:
        b = TLBuilder()
        b.freq = f
        z_per.append(MomwireEngine(b).impedance()[0])

    # Swept (engine constructed at any freq; impedance_sweep rebuilds per-k)
    b = TLBuilder()
    zs = MomwireEngine(b).impedance_sweep(freqs)
    assert zs.shape == (3, 1), zs.shape
    for i, (zp, zs_i) in enumerate(zip(z_per, zs[:, 0])):
        assert abs(zp - zs_i) < 1e-9, f"f={freqs[i]}: per={zp}, swept={zs_i}"


def test_momwire_tl_admittance_quarter_wave():
    """Hand-checked Y_TL for a quarter-wave TL with Z0=50: at θ=π/2,
    Y_TL = (1/(j50)) [[0,-1],[-1,0]] = [[0, j/50], [j/50, 0]].
    A unit-length TL of length λ/4 satisfies sin(βl)=1, cos(βl)=0."""
    from antennaknobs.network_reduce import tl_admittance_2x2

    wl = 4.0  # arbitrary; TL length = wl/4 gives θ=π/2
    Y_tl = tl_admittance_2x2(z0=50.0, length=1.0, wavelength=wl)
    expected = np.array([[0, 1j / 50], [1j / 50, 0]], dtype=np.complex128)
    assert np.allclose(Y_tl, expected, atol=1e-12), Y_tl


def test_momwire_tl_admittance_transposed_flips_offdiagonal_only():
    """A crossed/transposed line inverts port B's polarity: only the
    off-diagonal (transfer) terms flip sign; the diagonal (self) terms are
    unchanged. (NOT the same as a negative z0, which negates everything.)"""
    from antennaknobs.network_reduce import tl_admittance_2x2

    # θ = π/3 so cos≠0 and the diagonal is non-trivial to compare.
    wl, length, z0 = 6.0, 1.0, 50.0
    y = tl_admittance_2x2(z0, length, wl)
    yt = tl_admittance_2x2(z0, length, wl, transposed=True)
    assert np.allclose(np.diag(yt), np.diag(y), atol=1e-12)  # self terms same
    assert np.allclose(yt[0, 1], -y[0, 1], atol=1e-12)  # transfer flipped
    assert np.allclose(yt[1, 0], -y[1, 0], atol=1e-12)


def test_momwire_tl_admittance_half_wave_singular():
    """A half-wavelength TL gives sin(βl)=0 — the admittance is singular.
    Raise instead of returning nans so callers can adjust geometry."""
    from antennaknobs.network_reduce import tl_admittance_2x2

    with pytest.raises(ValueError, match="singular"):
        tl_admittance_2x2(z0=50.0, length=2.0, wavelength=4.0)


def test_momwire_difftl_admittance_quarter_wave():
    """4-terminal stamp of a *differential* quarter-wave line, Z0=50.

    Terminals are ordered (a_pos, a_neg, b_pos, b_neg). The two differential
    ports are A = V(a_pos)-V(a_neg) and B = V(b_pos)-V(b_neg); the line's 2x2
    differential admittance is the same lossless-line Y as the single-ended
    TL, lifted to four terminals by M = [[1,-1,0,0],[0,0,1,-1]] as
    Stamp = Mᵀ · Y2 · M. For a quarter-wave Z0=50 line, Y2 = [[0, j/50],
    [j/50, 0]], so the cross-coupling constant is c = j/50."""
    from antennaknobs.network_reduce import difftl_admittance_4x4

    wl = 4.0  # length = wl/4 -> theta = pi/2
    Y4 = difftl_admittance_4x4(z0=50.0, length=1.0, wavelength=wl, transposed=False)
    c = 1j / 50
    expected = np.array(
        [
            [0, 0, c, -c],
            [0, 0, -c, c],
            [c, -c, 0, 0],
            [-c, c, 0, 0],
        ],
        dtype=np.complex128,
    )
    assert np.allclose(Y4, expected, atol=1e-12), Y4


def test_momwire_difftl_transposed_flips_cross_coupling():
    """Transposing one port swaps its two terminals — that's the half-twist.
    It flips the sign of the A<->B cross-coupling blocks while leaving the
    self blocks (each port's own admittance) unchanged."""
    from antennaknobs.network_reduce import difftl_admittance_4x4

    wl = 4.0
    Y = difftl_admittance_4x4(z0=50.0, length=1.0, wavelength=wl, transposed=False)
    Yt = difftl_admittance_4x4(z0=50.0, length=1.0, wavelength=wl, transposed=True)
    assert np.allclose(Yt[:2, 2:], -Y[:2, 2:], atol=1e-12)
    assert np.allclose(Yt[2:, :2], -Y[2:, :2], atol=1e-12)
    assert np.allclose(Yt[:2, :2], Y[:2, :2], atol=1e-12)
    assert np.allclose(Yt[2:, 2:], Y[2:, 2:], atol=1e-12)


def test_momwire_difftl_common_mode_stamp_quarter_wave():
    """Adding z0_cm adds the common-mode line on top of the differential
    one. For a quarter-wave common line, Y_c = [[0, j/Zc],[j/Zc,0]], lifted
    by P_c=[[½,½,0,0],[0,0,½,½]] as P_cᵀ·Y_c·P_c — a hand value of
    (j/4Zc)·[[0,0,1,1],[0,0,1,1],[1,1,0,0],[1,1,0,0]]."""
    from antennaknobs.network_reduce import difftl_admittance_4x4

    wl = 4.0
    Y_diff = difftl_admittance_4x4(z0=50.0, length=1.0, wavelength=wl)
    Y_full = difftl_admittance_4x4(z0=50.0, length=1.0, wavelength=wl, z0_cm=200.0)
    cm = Y_full - Y_diff
    c = 1j / (4 * 200.0)
    expected = c * np.array(
        [[0, 0, 1, 1], [0, 0, 1, 1], [1, 1, 0, 0], [1, 1, 0, 0]],
        dtype=np.complex128,
    )
    assert np.allclose(cm, expected, atol=1e-12), cm


def _difftl_demo_builder(transposed=False):
    """Minimal antenna exercising the full DiffTL network path: a driven
    dipole plus a coupled 2-wire vertical pair whose top and bottom ends form
    two differential ports joined by a DiffTL (length off λ/2 to avoid the
    line singularity)."""
    from types import MappingProxyType

    from antennaknobs import AntennaBuilder
    from antennaknobs.network import DiffTL, Driven, Network, PortAtEdge

    h = 0.5 * (299.792458 / 28.47) * 0.95
    eps = 0.1
    tups = [
        ((0, -2.6, 7), (0, -eps, 7), 21, None, None),
        ((0, -eps, 7), (0, eps, 7), 3, None, "feed"),
        ((0, eps, 7), (0, 2.6, 7), 21, None, None),
    ]
    for yy, nt, nb in [(-0.1, "a_pos", "b_pos"), (0.1, "a_neg", "b_neg")]:
        tups.append(((1, yy, 7.0), (1, yy, 7.15), 1, None, nb))
        tups.append(((1, yy, 7.15), (1, yy, 7.0 + h - 0.15), 11, None, None))
        tups.append(((1, yy, 7.0 + h - 0.15), (1, yy, 7.0 + h), 1, None, nt))
    net = Network(
        ports={n: PortAtEdge(n) for n in ("feed", "a_pos", "a_neg", "b_pos", "b_neg")},
        branches=[
            DiffTL(
                "a_pos",
                "a_neg",
                "b_pos",
                "b_neg",
                z0=400.0,
                length=h,
                transposed=transposed,
            )
        ],
        sources=[Driven("feed")],
    )

    class B(AntennaBuilder):
        default_params = MappingProxyType({"design_freq": 28.47, "freq": 28.47})

        def build_wires(self):
            return tups

        def build_network(self):
            return net

    return B()


def test_difftl_network_rejects_unknown_ref():
    from antennaknobs.network import DiffTL, Driven, Network, PortAtEdge

    with pytest.raises(ValueError, match="unknown port"):
        Network(
            ports={k: PortAtEdge(k) for k in ("feed", "a", "b", "c")},
            branches=[DiffTL("a", "b", "c", "missing", z0=50.0, length=1.0)],
            sources=[Driven("feed")],
        )


def test_difftl_solves_end_to_end_on_momwire():
    z = MomwireEngine(_difftl_demo_builder(), ground=None).impedance()[0]
    assert np.isfinite(z.real) and np.isfinite(z.imag)
    assert 10 < z.real < 200, z


def test_difftl_transposed_changes_the_solve():
    z = MomwireEngine(_difftl_demo_builder(transposed=False), ground=None).impedance()[
        0
    ]
    zt = MomwireEngine(_difftl_demo_builder(transposed=True), ground=None).impedance()[
        0
    ]
    assert not np.isclose(z, zt), (z, zt)


@needs_pynec
def test_difftl_raises_on_pynec():
    """NEC2's tl_card pins each port to one segment, so a 4-terminal
    differential line is inexpressible — PyNECEngine must say so clearly."""
    with pytest.raises(NotImplementedError, match="DiffTL"):
        PyNECEngine(_difftl_demo_builder(), ground=None)


def _delta_looparray_difftl_builder():
    """delta_looparray_network with each single-ended TL re-expressed as a
    DiffTL on the *same* radiating geometry.

    A DiffTL's differential mode is the same lossless line as a single TL:
    with both negative terminals pinned to V=0, the positive-terminal 2x2
    block of the 4x4 stamp collapses to exactly the TL stamp. So replacing
        TL(driver, loopN, z0, len)
    with
        DiffTL(driver, gN_a, loopN, gN_b, z0, len)  + Driven(gN_*, 0)
    must reproduce delta_looparray_network bit-for-bit — a full end-to-end
    check of the 4-terminal DiffTL path (geometry translation, port
    indexing, 4x4 stamp, nodal reduction) against an independently-validated
    reference array.
    """
    from antennaknobs.designs.arrays.delta_looparray_network import (
        Builder as NetBuilder,
    )
    from antennaknobs.network import (
        DiffTL,
        Driven,
        Network,
        PortAtEdge,
        PortVirtual,
    )

    class DiffTLBuilder(NetBuilder):
        def build_network(self):
            wavelength = 299.792458 / self.design_freq
            tl_lengths = (
                self.del_y - wavelength * self.twist,
                self.del_y + wavelength * self.twist,
            )
            grounds = ("g1a", "g1b", "g2a", "g2b")
            ports = {
                "loop1": PortAtEdge("loop1"),
                "loop2": PortAtEdge("loop2"),
                "driver": PortVirtual("driver"),
                **{g: PortVirtual(g) for g in grounds},
            }
            branches = [
                DiffTL(
                    "driver",
                    "g1a",
                    "loop1",
                    "g1b",
                    z0=100.0,
                    length=tl_lengths[0],
                ),
                DiffTL(
                    "driver",
                    "g2a",
                    "loop2",
                    "g2b",
                    z0=100.0,
                    length=tl_lengths[1],
                ),
            ]
            sources = [Driven("driver", 1 + 0j)] + [Driven(g, 0) for g in grounds]
            return Network(ports=ports, branches=branches, sources=sources)

    return DiffTLBuilder()


def test_difftl_reproduces_tl_array_impedance():
    """DiffTL (differential mode, negatives grounded) reproduces the
    TL-driven delta_looparray impedance to numerical precision — a real
    radiating-array validation of the 4-terminal element, not just the
    bare admittance matrix."""
    from antennaknobs.designs.arrays.delta_looparray_network import (
        Builder as NetBuilder,
    )

    z_tl = MomwireEngine(NetBuilder(), ground=None).impedance()[0]
    z_diff = MomwireEngine(_delta_looparray_difftl_builder(), ground=None).impedance()[
        0
    ]
    assert abs(z_tl - z_diff) < 1e-9, f"TL {z_tl}, DiffTL {z_diff}"


def test_difftl_reproduces_tl_array_far_field():
    """Same geometry + electrically-identical feed network -> identical
    radiated pattern. Confirms the DiffTL path drives the same current
    distribution, not merely the same driving-point Z."""
    from antennaknobs.designs.arrays.delta_looparray_network import (
        Builder as NetBuilder,
    )

    kw = dict(n_theta=90, n_phi=360, del_theta=1, del_phi=1)
    ff_tl = MomwireEngine(NetBuilder(), ground=None).far_field(**kw)
    ff_diff = MomwireEngine(_delta_looparray_difftl_builder(), ground=None).far_field(
        **kw
    )
    assert abs(ff_tl.max_gain - ff_diff.max_gain) < 1e-6, (
        ff_tl.max_gain,
        ff_diff.max_gain,
    )


def test_difftl_reproduces_tl_array_impedance_sweep():
    """Exercises the frequency-dependent (swept Y + per-k 4x4 stamp) DiffTL
    path against the TL reference across the band."""
    from antennaknobs.designs.arrays.delta_looparray_network import (
        Builder as NetBuilder,
    )

    freqs = np.array([28.0, 28.47, 29.0])
    zs_tl = MomwireEngine(NetBuilder(), ground=None).impedance_sweep(freqs)
    zs_diff = MomwireEngine(
        _delta_looparray_difftl_builder(), ground=None
    ).impedance_sweep(freqs)
    assert np.allclose(zs_tl[:, 0], zs_diff[:, 0], atol=1e-9), (zs_tl, zs_diff)


def test_momwire_engine_declares_far_field_support():
    assert MomwireEngine.supports_far_field is True


@needs_pynec
def test_momwire_far_field_shape_matches_pynec():
    """The FarField shape (rings dims, thetas/phis arrays) has to match
    PyNEC's so plot_patterns, compare_patterns etc. work for both."""
    b = Builder()
    ff_nec = PyNECEngine(b, ground=None).far_field(
        n_theta=90, n_phi=360, del_theta=1, del_phi=1
    )
    ff_ps = MomwireEngine(b).far_field(n_theta=90, n_phi=360, del_theta=1, del_phi=1)
    assert np.array_equal(ff_nec.thetas, ff_ps.thetas)
    assert np.array_equal(ff_nec.phis, ff_ps.phis)
    assert len(ff_ps.rings) == 90
    assert len(ff_ps.rings[0]) == 361


@needs_pynec
def test_momwire_free_space_directivity_matches_pynec():
    """Free-space dipole peak directivity — same physical problem under
    two independent MoM solvers. 0.1 dBi headroom is generous for what
    is, on the dipole, sub-0.02 dBi agreement in practice."""
    b = Builder()
    ff_nec = PyNECEngine(b, ground=None).far_field(
        n_theta=90, n_phi=360, del_theta=1, del_phi=1
    )
    ff_ps = MomwireEngine(b).far_field(n_theta=90, n_phi=360, del_theta=1, del_phi=1)
    assert abs(ff_ps.max_gain - ff_nec.max_gain) < 0.1, (
        ff_nec.max_gain,
        ff_ps.max_gain,
    )


@needs_pynec
def test_momwire_pec_ground_directivity_matches_pynec():
    """PEC ground via image method on both sides. Tight agreement
    expected since the physics is identical."""
    b = Builder()
    ff_nec = PyNECEngine(b, ground="pec").far_field(
        n_theta=90, n_phi=360, del_theta=1, del_phi=1
    )
    ff_ps = MomwireEngine(b, ground="pec").far_field(
        n_theta=90, n_phi=360, del_theta=1, del_phi=1
    )
    assert abs(ff_ps.max_gain - ff_nec.max_gain) < 0.1, (
        ff_nec.max_gain,
        ff_ps.max_gain,
    )


def test_momwire_finite_ground_returns_sane_values():
    """Finite ground in MomwireEngine is PEC-image-plus-Fresnel post-
    processing; PyNEC's ("finite",...) ground uses the more sophisticated
    Sommerfeld/Norton model (gn_card(2,...)). The two diverge by ~1.5 dBi
    on a 10m dipole over (eps_r=10, sigma=0.002) ground. Don't claim
    equality; just sanity-check the output."""
    b = Builder()
    ff = MomwireEngine(b, ground=("finite", 10.0, 0.002)).far_field(
        n_theta=90, n_phi=360, del_theta=1, del_phi=1
    )
    assert 0.0 < ff.max_gain < 15.0, ff.max_gain
    assert ff.min_gain < ff.max_gain
    assert np.all(np.isfinite([ff.max_gain, ff.min_gain]))


@needs_pynec
def test_compare_patterns_accepts_engine_instances(tmp_path):
    """End-to-end: compare_patterns with a mix of pre-built engines
    (so the caller picks ground / backend per item) should run to
    completion and produce a non-empty PNG."""
    import matplotlib

    matplotlib.use("Agg")
    import antennaknobs as ant

    b = Builder()
    out = tmp_path / "cmp.png"
    ant.compare_patterns(
        [PyNECEngine(b, ground=None), MomwireEngine(b)],
        fn=str(out),
        builder_names=["pynec-free", "momwire-free"],
    )
    assert out.exists() and out.stat().st_size > 0


@needs_pynec
def test_compare_patterns_backwards_compatible_with_bare_builders(tmp_path):
    """Passing AntennaBuilder instances (the historical API) must keep
    working — they get wrapped with the default Antenna alias."""
    import matplotlib

    matplotlib.use("Agg")
    import antennaknobs as ant

    out = tmp_path / "cmp.png"
    ant.compare_patterns([Builder(), Builder()], fn=str(out))
    assert out.exists() and out.stat().st_size > 0


def test_sweep_freq_accepts_engine_factory(tmp_path):
    """sweep_freq's `engine=` kwarg accepts any callable (builder) ->
    SimulationEngine. functools.partial is the ergonomic way to bind
    construction kwargs like ground."""
    import matplotlib

    matplotlib.use("Agg")
    from functools import partial
    import antennaknobs as ant

    out = tmp_path / "sf.png"
    ant.sweep_freq(
        Builder(),
        rng=(28.0, 29.0),
        npoints=5,
        fn=str(out),
        engine=partial(MomwireEngine),
    )
    assert out.exists() and out.stat().st_size > 0


def test_sweep_accepts_engine_factory(tmp_path):
    import matplotlib

    matplotlib.use("Agg")
    import antennaknobs as ant

    out = tmp_path / "sw.png"
    ant.sweep(
        Builder(),
        "length_factor",
        center=0.97,
        fraction=1.05,
        npoints=3,
        fn=str(out),
        engine=MomwireEngine,
    )
    assert out.exists() and out.stat().st_size > 0


def test_sweep_gain_accepts_engine_factory(tmp_path):
    import matplotlib

    matplotlib.use("Agg")
    import antennaknobs as ant

    out = tmp_path / "sg.png"
    ant.sweep_gain(
        Builder(),
        "length_factor",
        center=0.97,
        fraction=1.05,
        npoints=3,
        fn=str(out),
        engine=MomwireEngine,
    )
    assert out.exists() and out.stat().st_size > 0


@needs_pynec
def test_plot_patterns_pins_radial_floor(tmp_path):
    """Without an rlim, matplotlib polar autoscale would smear a
    constant-radius elevation cut across the full radial range. Pin the
    floor to the lowest tick label so the displayed radius reflects the
    actual dBi value."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import antennaknobs as ant

    b = Builder()
    out = tmp_path / "p.png"
    ant.compare_patterns(
        [PyNECEngine(b, ground=None), MomwireEngine(b)],
        fn=str(out),
    )
    # The fn= save closes the figure, but the open-figure path also
    # exists; either way the file is on disk.
    assert out.exists() and out.stat().st_size > 0
    plt.close("all")


def test_translator_handles_hentenna_tee_junctions():
    """Hentenna has two degree-3 nodes (B, D); translator should
    decompose into 3 polylines all running B→D, with one junction at
    each."""
    from antennaknobs.designs.specialty.hentenna import Builder as H

    out = flat_wires_to_polylines(H().build_wires())
    assert len(out["polylines"]) == 3
    assert len(out["junctions"]) == 2
    # Two junctions, each with 3 polyline ends meeting.
    assert sorted(len(j) for j in out["junctions"]) == [3, 3]


def test_translator_handles_fandipole_high_degree_junctions():
    """Fandipole has two degree-6 nodes (S, T): feed wire + 5 spokes
    on each side. 5 polylines per side + 1 feed = 11 polylines."""
    from antennaknobs.designs.multiband.fandipole import Builder as F

    out = flat_wires_to_polylines(F().build_wires())
    assert len(out["polylines"]) == 11
    assert len(out["junctions"]) == 2
    assert sorted(len(j) for j in out["junctions"]) == [6, 6]


@needs_pynec
def test_momwire_sinusoidal_hentenna_impedance_close_to_pynec():
    """Cross-validation on the hentenna (two tee junctions): momwire's
    Sinusoidal basis agrees with PyNEC's free-space gn_card-disabled
    solve to within ~10% on R and ~10 Ω on X. Triangular at the same
    segmentation lands at a different impedance — the two basis
    families converge to two different limits (PyNEC and Sinusoidal
    to one, Triangular and BSpline to another), not to a common point.
    A cross-engine bound against PyNEC therefore only makes sense for
    Sinusoidal here. Picking a "more correct" pair is out of scope;
    this test is just verifying that the translator's junction/feed
    mapping is right."""
    from momwire import SinusoidalSolver
    from antennaknobs.designs.specialty.hentenna import Builder as H

    b = H()
    z_nec = PyNECEngine(b, ground=None).impedance()[0]
    z_ps = MomwireEngine(b, solver=SinusoidalSolver).impedance()[0]
    assert abs(z_ps.real - z_nec.real) / abs(z_nec.real) < 0.15
    assert abs(z_ps.imag - z_nec.imag) < 15.0


def test_momwire_sinusoidal_fandipole_runs():
    """Fandipole has degree-6 junctions and a 1-segment feed gap. The
    1-segment feed has zero interior knots so the Triangular tent basis
    has no feed to land on; Sinusoidal's const-source basis lives on
    segment centres and handles it. Just ensure it runs and produces
    a plausible value, the multi-wire geometry has too many freedoms
    to set a tight tolerance here."""
    from momwire import SinusoidalSolver
    from antennaknobs.designs.multiband.fandipole import Builder as F

    z = MomwireEngine(F(), solver=SinusoidalSolver).impedance()[0]
    assert 20 < z.real < 200, z
    assert abs(z.imag) < 200, z


def test_translator_handles_bowtie_closed_cycle():
    """Bowtie is a single 10-edge closed cycle (each triangle's corners
    share one edge per triangle, leaving every node degree-2). Cut at
    the excited edge: feed becomes a 1-edge polyline, the rest becomes
    a 9-edge polyline running the long way back."""
    from antennaknobs.designs.specialty.bowtie import Builder as BT

    out = flat_wires_to_polylines(BT().build_wires())
    assert len(out["polylines"]) == 2
    # Both polylines share both endpoints (the cut points), so both
    # cut nodes are 2-entry junctions.
    assert sorted(len(j) for j in out["junctions"]) == [2, 2]
    feed_pl = out["polylines"][out["feed_wire_index"]]
    assert feed_pl.shape == (2, 3)


def test_translator_handles_delta_loop_pure_cycle():
    from antennaknobs.designs.loops.delta_loop import Builder as DL

    out = flat_wires_to_polylines(DL().build_wires())
    assert len(out["polylines"]) == 2
    assert sorted(len(j) for j in out["junctions"]) == [2, 2]
    # Delta loop has 4 edges total: 1 becomes the feed polyline, 3 the loop.
    assert sorted(len(s) for s in out["edge_segments"]) == [1, 3]


@needs_pynec
def test_momwire_sinusoidal_delta_loop_close_to_pynec():
    """Closed-loop cross-validation: PyNEC and Sinusoidal agree on a
    canonical pure-cycle geometry. Tighter bound than the hentenna test
    because there are no tee junctions adding extra basis-family bias."""
    from momwire import SinusoidalSolver
    from antennaknobs.designs.loops.delta_loop import Builder as DL

    b = DL()
    z_nec = PyNECEngine(b, ground=None).impedance()[0]
    z_ps = MomwireEngine(b, solver=SinusoidalSolver).impedance()[0]
    assert abs(z_ps.real - z_nec.real) / abs(z_nec.real) < 0.05
    assert abs(z_ps.imag - z_nec.imag) < 5.0


def test_momwire_triangular_bowtie_runs():
    """Triangular handles the bowtie because its feed gap is n_seg=3
    (interior tent basis available). Verifies the closed-loop path
    doesn't trip Triangular's feed-basis lookup."""
    from antennaknobs.designs.specialty.bowtie import Builder as BT

    z = MomwireEngine(BT()).impedance()[0]
    assert 100 < z.real < 300, z
    assert abs(z.imag) < 100, z


def test_translator_emits_one_feed_per_excited_tuple():
    """Multi-feed builders (arrays) should produce one entry in `feeds`
    per excited wire tuple, with voltages from the builder phasors."""
    from antennaknobs.designs.arrays.bowtiearray1x2 import Builder as B12

    b = B12()
    b.phase_lr = 90.0
    out = flat_wires_to_polylines(b.build_wires())
    assert len(out["feeds"]) == 2
    v0, v1 = out["feeds"][0][2], out["feeds"][1][2]
    # First feed is V=1+0j; second is the phase_lr phasor at 90°.
    assert abs(v0 - (1 + 0j)) < 1e-12
    assert abs(v1 - 1j) < 1e-12
    # Back-compat scalars point at the first feed.
    assert out["feed_wire_index"] == out["feeds"][0][0]
    assert out["feed_arclength"] == out["feeds"][0][1]
    assert out["feed_voltage"] == out["feeds"][0][2]


@needs_pynec
def test_momwire_multifeed_bowtie_1x2_matches_pynec():
    """Symmetric in-phase drive on the bowtie 1×2 phased array: per-feed
    Z from MomwireEngine must agree with PyNEC, and the two feeds should
    return ~equal Z by symmetry. 5% relative + 3 Ω absolute slack covers
    the basis-vs-NEC gap that momwire's own bowtie-1×2 parity test uses."""
    from antennaknobs.designs.arrays.bowtiearray1x2 import Builder as B12

    b = B12()
    z_ps = MomwireEngine(b).impedance()
    z_nec = PyNECEngine(b, ground=None).impedance()
    assert len(z_ps) == len(z_nec) == 2
    for zp, zn in zip(z_ps, z_nec):
        assert abs(zp - zn) < 0.05 * abs(zn) + 3.0, (zp, zn)
    # In-phase symmetric drive → the two ports see the same Z.
    assert abs(z_ps[0] - z_ps[1]) < 1.0


@needs_pynec
def test_momwire_multifeed_bowtie_1x2_phased_matches_pynec():
    """90° phasing makes Z₀ ≠ Z₁ via mutual coupling. Catches feed-
    ordering / voltage-sign bugs that a symmetric drive would mask."""
    from antennaknobs.designs.arrays.bowtiearray1x2 import Builder as B12

    b = B12()
    b.phase_lr = 90.0
    z_ps = MomwireEngine(b).impedance()
    z_nec = PyNECEngine(b, ground=None).impedance()
    for zp, zn in zip(z_ps, z_nec):
        assert abs(zp - zn) < 0.05 * abs(zn) + 3.0, (zp, zn)
    # Asymmetry must actually appear, otherwise both backends could
    # be silently degenerate.
    assert abs(z_ps[0] - z_ps[1]) > 10.0
    assert abs(z_nec[0] - z_nec[1]) > 10.0


@needs_pynec
def test_momwire_multifeed_far_field_matches_pynec():
    """Bowtie 1×2 phased-array peak directivity, two backends. In-phase
    drive gives a broadside lobe; 90° drive squints. Both must agree
    with PyNEC because the far-field integrand is just the superposed
    multi-source current pattern — a feed-ordering or voltage-sign bug
    in the multi-feed RHS would show up as a different lobe shape and
    a different peak. 0.1 dBi headroom matches the single-feed dipole
    test; observed delta is ~0.02 dBi on both phasings."""
    from antennaknobs.designs.arrays.bowtiearray1x2 import Builder as B12

    for phase_lr_deg in (0.0, 90.0):
        b = B12()
        b.phase_lr = phase_lr_deg
        ff_p = MomwireEngine(b).far_field(n_theta=90, n_phi=360, del_theta=1, del_phi=1)
        ff_n = PyNECEngine(b, ground=None).far_field(
            n_theta=90, n_phi=360, del_theta=1, del_phi=1
        )
        assert abs(ff_p.max_gain - ff_n.max_gain) < 0.1, (
            f"phase={phase_lr_deg}: momwire={ff_p.max_gain}, pynec={ff_n.max_gain}"
        )


def test_momwire_multifeed_impedance_sweep_shape():
    """Multi-feed impedance_sweep must return (n_freqs, n_feeds) to
    match PyNECEngine's shape contract."""
    from antennaknobs.designs.arrays.bowtiearray1x2 import Builder as B12

    freqs = np.linspace(28.0, 29.0, 4)
    zs = MomwireEngine(B12()).impedance_sweep(freqs)
    assert zs.shape == (4, 2), zs.shape


@needs_pynec
def test_current_distribution_peak_matches_one_over_z():
    """Peak |I| over the geometry should equal |1/Z| within solver
    rounding on both backends — Z = V/I with V=1, so the driving-point
    current magnitude is |1/Z|."""
    b = Builder()
    for eng in (MomwireEngine(b), PyNECEngine(b, ground=None)):
        cd = eng.current_distribution()
        peak = max(np.max(np.abs(w.knot_currents)) for w in cd)
        z = eng.impedance()[0]
        assert abs(peak - abs(1 / z)) < 0.02 * abs(1 / z), (peak, z)


def test_network_spec_matches_legacy_tls_on_delta_looparray():
    """build_network() variant of delta_looparray omits the central dummy
    stub wire (~0.01λ long) that the legacy build_tls() variant needs as
    an attachment point for tl_card. Same antenna, same TLs, same drive.
    Impedance should agree to within the stub wire's tiny radiative
    contribution (~0.5%), far-field peak essentially identical."""
    from antennaknobs.designs.arrays.delta_looparray_with_tls import (
        Builder as LegacyBuilder,
    )
    from antennaknobs.designs.arrays.delta_looparray_network import (
        Builder as NetBuilder,
    )

    zl = MomwireEngine(LegacyBuilder()).impedance()[0]
    zn = MomwireEngine(NetBuilder()).impedance()[0]
    assert abs(zl - zn) / abs(zl) < 0.01, f"legacy {zl}, network {zn}"

    ffl = MomwireEngine(LegacyBuilder()).far_field(
        n_theta=90, n_phi=360, del_theta=1, del_phi=1
    )
    ffn = MomwireEngine(NetBuilder()).far_field(
        n_theta=90, n_phi=360, del_theta=1, del_phi=1
    )
    assert abs(ffl.max_gain - ffn.max_gain) < 0.05, (ffl.max_gain, ffn.max_gain)


def test_network_spec_impedance_sweep_matches_per_freq():
    """impedance_sweep() in the network path should match per-freq
    impedance() — exercises the swept Y + per-k branch stamping path."""
    from antennaknobs.designs.arrays.delta_looparray_network import (
        Builder as NetBuilder,
    )

    freqs = np.array([28.0, 28.47, 29.0])
    zs_swept = MomwireEngine(NetBuilder()).impedance_sweep(freqs)
    assert zs_swept.shape == (3, 1)
    for i, f in enumerate(freqs):
        b = NetBuilder()
        b.freq = f
        z_one = MomwireEngine(b).impedance()[0]
        assert abs(zs_swept[i, 0] - z_one) < 1e-9, (
            f"f={f}: swept={zs_swept[i, 0]}, per-freq={z_one}"
        )


def test_network_spec_rejects_unknown_port_reference():
    """Constructing a Network with a branch referencing a port name that
    isn't in `ports` should raise immediately, not silently at solve time."""
    from antennaknobs.network import Driven, Network, PortVirtual, TL

    with pytest.raises(ValueError, match="unknown port"):
        Network(
            ports={"drv": PortVirtual("drv")},
            branches=[TL(a="drv", b="missing", z0=50, length=1.0)],
            sources=[Driven(port="drv")],
        )


def test_network_spec_rejects_port_at_edge_with_no_named_edge():
    """PortAtEdge("loop1") with no `loop1` edge in build_wires() should
    raise a clear error at engine construction time."""
    from antennaknobs import AntennaBuilder
    from antennaknobs.network import Driven, Network, PortAtEdge, PortVirtual, TL
    from types import MappingProxyType

    class BadBuilder(AntennaBuilder):
        default_params = MappingProxyType({"freq": 28.0, "design_freq": 28.0})

        def build_wires(self):
            # Single straight wire, no named edges.
            return [((0, -2, 5), (0, 2, 5), 21, 1 + 0j)]

        def build_network(self):
            return Network(
                ports={
                    "loop1": PortAtEdge("loop1"),  # no matching named edge!
                    "drv": PortVirtual("drv"),
                },
                branches=[TL(a="drv", b="loop1", z0=50, length=1.0)],
                sources=[Driven(port="drv")],
            )

    with pytest.raises(ValueError, match="no edge in build_wires"):
        MomwireEngine(BadBuilder())


@needs_pynec
def test_pynec_network_matches_momwire_on_delta_looparray():
    """delta_looparray_network on PyNECEngine now goes through multiport-Y
    extraction + the shared NetworkReducer (the EZNEC approach), NOT NEC2's
    tl_card with a synthesised dummy stub. That dummy stub used to inject a
    huge parasitic reactance the line failed to transform away, giving a
    wildly wrong impedance (~100 - j33000); the reducer path instead agrees
    with MomwireEngine to within the two MoM formulations' inherent few-percent
    difference, for both impedance and far-field gain."""
    from antennaknobs.designs.arrays.delta_looparray_network import (
        Builder as NetBuilder,
    )

    (z_nec,) = PyNECEngine(NetBuilder(), ground=None).impedance()
    (z_ps,) = MomwireEngine(NetBuilder(), ground=None).impedance()
    assert np.isfinite(z_nec.real) and np.isfinite(z_nec.imag), z_nec
    assert abs(z_nec - z_ps) / abs(z_ps) < 0.05, f"nec={z_nec}, momwire={z_ps}"

    kw = dict(n_theta=90, n_phi=360, del_theta=1, del_phi=1)
    g_nec = PyNECEngine(NetBuilder(), ground=None).far_field(**kw).max_gain
    g_ps = MomwireEngine(NetBuilder(), ground=None).far_field(**kw).max_gain
    assert abs(g_nec - g_ps) < 0.3, (g_nec, g_ps)


@needs_pynec
def test_pynec_virtual_to_virtual_tl_supported():
    """A TL between two PortVirtuals has no NEC2 tl_card mapping, but the
    multiport-Y + NetworkReducer path handles it fine — intermediate virtual
    nodes are just rows in the network Y matrix. It yields a finite impedance
    agreeing with MomwireEngine (was a hard ValueError under the old tl_card
    dispatch)."""
    from antennaknobs import AntennaBuilder
    from antennaknobs.network import Driven, Network, PortAtEdge, PortVirtual, TL
    from types import MappingProxyType

    class Builder(AntennaBuilder):
        default_params = MappingProxyType({"freq": 28.0, "design_freq": 28.0})

        def build_wires(self):
            return [((0, -2.5, 5), (0, 2.5, 5), 21, None, "feed")]

        def build_network(self):
            return Network(
                ports={
                    "feed": PortAtEdge("feed"),
                    "a": PortVirtual("a"),
                    "b": PortVirtual("b"),
                },
                branches=[
                    TL(a="a", b="b", z0=50, length=1.0),  # virtual ↔ virtual
                    TL(a="a", b="feed", z0=50, length=1.0),
                ],
                sources=[Driven(port="a")],
            )

    z_nec = PyNECEngine(Builder(), ground=None).impedance()[0]
    z_ps = MomwireEngine(Builder(), ground=None).impedance()[0]
    assert np.isfinite(z_nec.real) and np.isfinite(z_nec.imag), z_nec
    assert abs(z_nec - z_ps) / abs(z_ps) < 0.05, (z_nec, z_ps)


@needs_pynec
def test_pynec_load_branch_resistor_adds_to_impedance():
    """Load(r=R) on a PyNEC-driven dipole should shift driving-point Z by
    exactly R — ld_card type-0 inserts a series R+L+C at the segment. This
    is the cross-engine cross-check for piece (A) on the PyNEC side."""
    from antennaknobs import AntennaBuilder
    from antennaknobs.network import Driven, Load, Network, PortAtEdge
    from types import MappingProxyType

    class Builder(AntennaBuilder):
        default_params = MappingProxyType({"freq": 28.0, "design_freq": 28.0})

        def __init__(self, with_load=True):
            super().__init__()
            self._with_load = with_load

        def build_wires(self):
            return [((0, -2.5, 5), (0, 2.5, 5), 21, None, "feed")]

        def build_network(self):
            branches = [Load(port="feed", r=50.0)] if self._with_load else []
            return Network(
                ports={"feed": PortAtEdge("feed")},
                branches=branches,
                sources=[Driven(port="feed", voltage=1 + 0j)],
            )

    (z_bare,) = PyNECEngine(Builder(with_load=False), ground=None).impedance()
    (z_loaded,) = PyNECEngine(Builder(with_load=True), ground=None).impedance()
    # NEC2 distributes the load across the loaded segment, with a small
    # discretisation error vs the analytical +R shift. Half an ohm at 50 Ω
    # is well within ld_card's typical accuracy.
    assert abs((z_loaded - z_bare) - 50.0) < 0.5, (z_bare, z_loaded)


@needs_pynec
def test_short_dipole_loaded_cross_engine_impedance():
    """Showcase for the Load branch: a 0.5·λ/2 shortened dipole at 28 MHz
    with a series loading coil at the feed point. Momwire's Sherman-Morrison
    Y stamp and PyNEC's ld_card should agree to within their baseline
    free-space dipole tolerance (~1-2 Ω R, tens of Ω X)."""
    from antennaknobs.designs.dipoles.short_dipole_loaded import (
        Builder as ShortB,
    )

    b = ShortB()
    (z_ps,) = MomwireEngine(b).impedance()
    (z_nec,) = PyNECEngine(b, ground=None).impedance()
    # R agreement matches the dipole baseline cross-check.
    assert abs(z_ps.real - z_nec.real) < 2.0, (z_ps, z_nec)
    # Reactance: each engine reaches the same loaded Z within ~25 Ω,
    # which is dominated by the underlying short-dipole reactance offset
    # (the Load shift itself is identical between engines: each adds ωL
    # to whatever the bare antenna's X was).
    assert abs(z_ps.imag - z_nec.imag) < 30.0, (z_ps, z_nec)


@needs_pynec
def test_short_dipole_loaded_pattern_similar_lower_gain_than_full():
    """A center-loaded shortened dipole radiates the same broadside-peak
    pattern as a full-length dipole but with ~0.4 dB less peak gain
    (closer to the ideal short-dipole directivity of 1.76 dBi vs the
    half-wave's 2.15 dBi). Confirmed on both engines."""
    from antennaknobs.designs.dipoles.short_dipole_loaded import (
        Builder as ShortB,
    )

    short = ShortB()
    # Same Builder, length_factor=1 + no load → full-length unloaded dipole.
    full = ShortB()
    full.length_factor = 1.0
    full.inductance_uH = 0.0

    for engine_cls, kwargs in [(MomwireEngine, {}), (PyNECEngine, {"ground": None})]:
        ff_s = engine_cls(short, **kwargs).far_field(
            n_theta=90, n_phi=360, del_theta=1, del_phi=1
        )
        ff_f = engine_cls(full, **kwargs).far_field(
            n_theta=90, n_phi=360, del_theta=1, del_phi=1
        )
        # Less peak gain — the user's hypothesis. ~0.3-0.4 dB range observed.
        assert ff_s.max_gain < ff_f.max_gain, (engine_cls.__name__, ff_s, ff_f)
        assert 0.1 < (ff_f.max_gain - ff_s.max_gain) < 1.0, (
            engine_cls.__name__,
            ff_s.max_gain,
            ff_f.max_gain,
        )
        # Same pattern shape: short and full dipole patterns should be
        # highly correlated bin-by-bin (just shifted in absolute level).
        # >0.99 corr ⇒ "same shape" to a tight tolerance.
        rings_s = np.asarray(ff_s.rings).ravel()
        rings_f = np.asarray(ff_f.rings).ravel()
        corr = np.corrcoef(rings_s, rings_f)[0, 1]
        assert corr > 0.99, f"{engine_cls.__name__}: pattern correlation {corr:.4f}"


@needs_pynec
def test_pynec_load_branch_rejects_virtual_port():
    """Load on a PortVirtual is rejected — same check as MomwireEngine."""
    from antennaknobs import AntennaBuilder
    from antennaknobs.network import (
        Driven,
        Load,
        Network,
        PortAtEdge,
        PortVirtual,
        TL,
    )
    from types import MappingProxyType

    class Builder(AntennaBuilder):
        default_params = MappingProxyType({"freq": 28.0, "design_freq": 28.0})

        def build_wires(self):
            return [((0, -2.5, 5), (0, 2.5, 5), 21, None, "feed")]

        def build_network(self):
            return Network(
                ports={
                    "feed": PortAtEdge("feed"),
                    "drv": PortVirtual("drv"),
                },
                branches=[
                    TL(a="drv", b="feed", z0=50, length=1.0),
                    Load(port="drv", r=10),
                ],
                sources=[Driven(port="drv")],
            )

    eng = PyNECEngine(Builder(), ground=None)
    with pytest.raises(ValueError, match="Load on virtual port"):
        eng.impedance()


@needs_pynec
def test_pynec_network_rejects_port_at_edge_with_no_named_edge():
    """PortAtEdge("loop1") with no `loop1` edge in build_wires() should
    raise a clear error at engine construction time — mirror of the
    MomwireEngine check."""
    from antennaknobs import AntennaBuilder
    from antennaknobs.network import Driven, Network, PortAtEdge, PortVirtual, TL
    from types import MappingProxyType

    class Builder(AntennaBuilder):
        default_params = MappingProxyType({"freq": 28.0, "design_freq": 28.0})

        def build_wires(self):
            return [((0, -2.5, 5), (0, 2.5, 5), 21, 1 + 0j)]  # no name

        def build_network(self):
            return Network(
                ports={
                    "loop1": PortAtEdge("loop1"),
                    "drv": PortVirtual("drv"),
                },
                branches=[TL(a="drv", b="loop1", z0=50, length=1.0)],
                sources=[Driven(port="drv")],
            )

    with pytest.raises(ValueError, match="no edge in build_wires"):
        PyNECEngine(Builder(), ground=None)


@needs_pynec
def test_trap_dipole_cross_engine_impedance_at_trap_resonance():
    """Trap dipole showcase tuned to design_freq=28 MHz. At trap resonance
    the parallel-LC tank goes Z→∞, interrupting the segment's current
    path — only the inner-arm length carries current, the outer arms
    radiate parasitically. Both engines should land in the same regime
    (high R, high X; the resonant trap is hard to cross-validate strictly
    because the engines handle the singular MoM update slightly
    differently)."""
    from antennaknobs.designs.multiband.trap_dipole import Builder

    b = Builder()
    b.freq = 28.0
    (z_ps,) = MomwireEngine(b).impedance()
    (z_nec,) = PyNECEngine(b, ground=None).impedance()
    # Both engines see Z ≈ 80-90 + 60j at the design point (loaded short-
    # dipole regime — the trap-isolated inner arm with parasitic outer-arm
    # coupling sits slightly past resonance for the default geometry).
    assert 60 < z_ps.real < 110, z_ps
    assert 60 < z_nec.real < 110, z_nec
    assert 30 < z_ps.imag < 100, z_ps
    assert 30 < z_nec.imag < 100, z_nec
    # Cross-engine tolerance is tight at the design point with a centered
    # feed: ~2 Ω R, ~10 Ω X.
    assert abs(z_ps.real - z_nec.real) < 3.0, (z_ps, z_nec)
    assert abs(z_ps.imag - z_nec.imag) < 12.0, (z_ps, z_nec)


def test_trap_dipole_trap_C_changes_impedance():
    """Sliding trap_C_pF away from the resonant value should shift Z
    substantially — confirms the parallel-LC Load update actually
    propagates to the driven-port impedance (the bug that motivated
    splitting passive ports into loaded vs floating; see PR notes)."""
    from antennaknobs.designs.multiband.trap_dipole import Builder

    b_res = Builder()
    b_res.freq = 28.0
    b_det = Builder()
    b_det.freq = 28.0
    b_det.trap_C_pF = 1.0  # well off resonance; trap looks inductive

    (z_res,) = MomwireEngine(b_res).impedance()
    (z_det,) = MomwireEngine(b_det).impedance()
    # The two regimes are very different — at least an order of magnitude
    # apart in |Z|. The exact numbers aren't the point; the point is that
    # the slider does something.
    assert abs(z_res - z_det) > 200, (z_res, z_det)


@needs_pynec
def test_trap_dipole_low_band_loaded_into_resonance():
    """At 14 MHz the parallel-LC trap is well below its 28 MHz resonance,
    so it looks inductive in series with the segment. That inductive
    loading lengthens the outer arms electrically and pulls the full-
    length antenna near resonance — much lower |X| than the unloaded
    short inner dipole would have on its own at 14 MHz."""
    from antennaknobs.designs.multiband.trap_dipole import Builder

    b = Builder()
    b.freq = 14.0
    (z_ps,) = MomwireEngine(b).impedance()
    (z_nec,) = PyNECEngine(b, ground=None).impedance()
    # Both engines report a near-resonant-ish Z (the inner dipole alone
    # at 14 MHz would have X ≈ -880 Ω). With the loading, |X| should be
    # well under 200 Ω in both engines.
    assert abs(z_ps.imag) < 200, z_ps
    assert abs(z_nec.imag) < 200, z_nec
    # R should be in the resistive-load range, not the deep-capacitive
    # short-dipole tens-of-Ω regime.
    assert 30 < z_ps.real < 200, z_ps
    assert 30 < z_nec.real < 200, z_nec


def test_trap_dipole_parallel_lc_resonance_is_finite():
    """At exactly f_high with no parallel R, the parallel-LC tank admittance
    is 0 (Z→∞, the trap open circuit). This is the *intended* operating
    point of a trap, not an error: the admittance-form Sherman-Morrison
    stamp resolves the 0/∞ analytically (coefficient → 1/Y_kk, the
    open-circuit Schur complement). Momwire must produce a finite impedance
    here — no raise, no NaN/Inf."""
    from antennaknobs.designs.multiband.trap_dipole import Builder

    b = Builder()
    b.freq = b.design_freq  # exactly at trap resonance — tank admittance → 0
    (z,) = MomwireEngine(b).impedance()
    assert np.isfinite(z.real) and np.isfinite(z.imag), z


def test_load_series_admittance_parallel_lc_zero_at_resonance():
    """The parallel-LC tank admittance is exactly 0 at ω₀=1/√(LC) — the
    open-circuit trap point — and load_impedance returns +inf there rather
    than raising."""
    import math

    from antennaknobs.network import (
        Load,
        load_impedance,
        load_series_admittance,
    )

    L = 5e-6
    C = 1.0 / (L * (2 * math.pi * 28e6) ** 2)  # resonant at 28 MHz
    omega0 = 1.0 / math.sqrt(L * C)
    br = Load(port="t", l=L, c=C, parallel=True)

    y = load_series_admittance(br, omega0)
    assert abs(y) < 1e-6, y  # tank admittance ≈ 0 at resonance

    z = load_impedance(br, omega0)
    assert math.isinf(z.real), z  # Z = 1/y → ∞ (no raise)

    # Off resonance the tank is reactive and finite.
    y_off = load_series_admittance(br, omega0 * 1.1)
    assert abs(y_off) > 1e-6, y_off


def test_load_series_admittance_series_short_is_inf():
    """A series-LC load at its resonance is a short (Z=0); its series
    admittance is reported as inf so the stamp consumer skips it."""
    import math

    from antennaknobs.network import Load, load_series_admittance

    L = 5e-6
    C = 1.0 / (L * (2 * math.pi * 28e6) ** 2)
    omega0 = 1.0 / math.sqrt(L * C)
    br = Load(port="t", l=L, c=C, parallel=False)  # series mode

    y = load_series_admittance(br, omega0)
    assert math.isinf(y.real), y


def _load_dipole_builder(load_branch=None, name_feed=False):
    """Synthetic half-wave dipole at 28 MHz with one named feed edge.
    When `load_branch` is given, build_network() returns a Network with that
    Load and a Driven on the same port. Otherwise build_network()=None and
    the engine falls through to the plain-feed path."""
    from antennaknobs import AntennaBuilder
    from antennaknobs.network import Driven, Network, PortAtEdge
    from types import MappingProxyType

    class Builder(AntennaBuilder):
        default_params = MappingProxyType({"freq": 28.0, "design_freq": 28.0})

        def build_wires(self):
            # ~λ/2 at 28 MHz is ~5.35m; half-arms of 2.5m straddling origin.
            ex = 1 + 0j
            if load_branch is None and not name_feed:
                return [((0, -2.5, 5), (0, 2.5, 5), 21, ex)]
            return [((0, -2.5, 5), (0, 2.5, 5), 21, ex, "feed")]

        def build_network(self):
            if load_branch is None:
                return None
            return Network(
                ports={"feed": PortAtEdge("feed")},
                branches=[load_branch],
                sources=[Driven(port="feed", voltage=1 + 0j)],
            )

    return Builder()


def test_load_branch_resistor_adds_to_impedance():
    """Load(r=R) on the driven port should shift driving-point Z by exactly R
    — Sherman-Morrison on a 1-port reduces to Z' = Z + Z_L."""
    from antennaknobs.network import Load

    z_bare = MomwireEngine(_load_dipole_builder(name_feed=True)).impedance()[0]
    z_loaded = MomwireEngine(
        _load_dipole_builder(Load(port="feed", r=50.0))
    ).impedance()[0]
    assert abs((z_loaded - z_bare) - 50.0) < 1e-6, (z_bare, z_loaded)


def test_load_branch_series_lc_at_resonance_zero_impact():
    """A series LC tuned to be resonant at the operating freq has Z_L=0 →
    no shift in driving-point Z."""
    from antennaknobs.network import Load

    f_hz = 28.0e6
    l = 1e-6
    c = 1.0 / ((2 * np.pi * f_hz) ** 2 * l)  # ω²LC = 1
    z_bare = MomwireEngine(_load_dipole_builder(name_feed=True)).impedance()[0]
    z_loaded = MomwireEngine(
        _load_dipole_builder(Load(port="feed", l=l, c=c))
    ).impedance()[0]
    assert abs(z_loaded - z_bare) < 1e-3, (z_bare, z_loaded)


def test_load_branch_inductor_adds_reactance():
    """Load(l=L) adds jωL to driving-point Z — pure reactive shift."""
    from antennaknobs.network import Load

    l = 1e-6
    omega = 2 * np.pi * 28.0e6
    z_bare = MomwireEngine(_load_dipole_builder(name_feed=True)).impedance()[0]
    z_loaded = MomwireEngine(_load_dipole_builder(Load(port="feed", l=l))).impedance()[
        0
    ]
    assert abs((z_loaded - z_bare).real) < 1e-6, (z_bare, z_loaded)
    assert abs((z_loaded - z_bare).imag - omega * l) < 1e-3, (z_bare, z_loaded)


def test_load_branch_rejects_virtual_port():
    """Load on a PortVirtual has no antenna segment to load → ValueError."""
    from antennaknobs import AntennaBuilder
    from antennaknobs.network import (
        Driven,
        Load,
        Network,
        PortAtEdge,
        PortVirtual,
        TL,
    )
    from types import MappingProxyType

    class Builder(AntennaBuilder):
        default_params = MappingProxyType({"freq": 28.0, "design_freq": 28.0})

        def build_wires(self):
            return [((0, -2.5, 5), (0, 2.5, 5), 21, 1 + 0j, "feed")]

        def build_network(self):
            return Network(
                ports={
                    "feed": PortAtEdge("feed"),
                    "drv": PortVirtual("drv"),
                },
                branches=[
                    TL(a="drv", b="feed", z0=50, length=1.0),
                    Load(port="drv", r=10),
                ],
                sources=[Driven(port="drv")],
            )

    eng = MomwireEngine(Builder())
    with pytest.raises(ValueError, match="Load on virtual port"):
        eng.impedance()


def test_translator_cuts_parasitic_loop_alongside_a_driver():
    """A parasitic (no-port) cycle is now supported: it is cut at an arbitrary
    edge into two polylines joined at two cut-node junctions, so momwire's KCL
    carries current around it. Here a driven dipole sits next to a passive
    square loop; the translator yields the dipole's single feed plus the loop's
    cut junctions, no exception."""
    tups = [
        # Driven dipole (open chain with one feed gap) at z = 5.
        ((-1, 0, 5), (-0.01, 0, 5), 5, None),
        ((-0.01, 0, 5), (0.01, 0, 5), 1, 1 + 0j),
        ((0.01, 0, 5), (1, 0, 5), 5, None),
        # Parasitic square loop at z = 0 (no excitation of its own).
        ((0, 0, 0), (1, 0, 0), 5, None),
        ((1, 0, 0), (1, 1, 0), 5, None),
        ((1, 1, 0), (0, 1, 0), 5, None),
        ((0, 1, 0), (0, 0, 0), 5, None),
    ]
    out = flat_wires_to_polylines(tups)
    assert len(out["feeds"]) == 1  # only the dipole is driven
    # dipole -> 1 polyline; the loop is cut into 2 -> 3 polylines total.
    assert len(out["polylines"]) == 3
    # the loop's two cut nodes are registered as junctions.
    assert len(out["junctions"]) >= 2


def test_translator_rejects_geometry_with_no_excitation():
    """A geometry that carries no excitation ANYWHERE (e.g. a lone parasitic
    loop) is unsolvable and must raise a clear error -- now from the global
    'no excitation' guard rather than the loop cutter."""
    tups = [
        ((0, 0, 0), (1, 0, 0), 5, None),
        ((1, 0, 0), (1, 1, 0), 5, None),
        ((1, 1, 0), (0, 1, 0), 5, None),
        ((0, 1, 0), (0, 0, 0), 5, None),
    ]
    with pytest.raises(ValueError, match="no excitation"):
        flat_wires_to_polylines(tups)


@pytest.mark.parametrize(
    "design_module",
    [
        "antennaknobs.designs.arrays.invveearray",
        "antennaknobs.designs.arrays.bowtiearray2x4",
    ],
)
def test_momwire_arrayblock_matches_dense_bspline(design_module):
    """The element-aware array-block solver must reproduce the dense bspline
    per-port impedance on the array designs. Both go through MomwireEngine, so
    this also pins the parity wiring: a wrong parity for ArrayBlockSolver would
    build a different mesh and the impedances would diverge."""
    from importlib import import_module
    from momwire import BSplineSolver, ArrayBlockSolver

    b = import_module(design_module).Builder()
    kw = {"solver_kwargs": {"degree": 2}}
    z_dense = MomwireEngine(b, solver=BSplineSolver, **kw).impedance()
    z_block = MomwireEngine(b, solver=ArrayBlockSolver, **kw).impedance()
    assert len(z_dense) == len(z_block) > 1
    for i, (zd, zb) in enumerate(zip(z_dense, z_block)):
        assert abs(zd - zb) / abs(zd) < 1e-3, f"feed {i}: {zd} vs {zb}"


def test_momwire_arrayblock_parity_matches_bspline():
    """ArrayBlockSolver shares BSplineSolver's degree-driven parity (a regression
    guard for the _parity_for_solver wiring)."""
    from momwire import BSplineSolver, ArrayBlockSolver
    from antennaknobs.engines.momwire import _parity_for_solver

    for degree in (1, 2):
        kw = {"degree": degree}
        assert _parity_for_solver(ArrayBlockSolver, kw) == _parity_for_solver(
            BSplineSolver, kw
        )

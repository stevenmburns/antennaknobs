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
    # 1-segment feed bridge since issue #457 (proportional segs_for meshing).
    assert out["edge_segments"] == [[21, 1, 21]]
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
    solve to within ~10% on R and ~10 Ω on X. The polynomial bases at
    the same segmentation land at a different impedance — the two basis
    families converge to two different limits (PyNEC and Sinusoidal
    to one, BSpline to another), not to a common point.
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
    """Fandipole has degree-6 junctions and a 1-segment feed gap. A
    1-segment feed has zero interior knots, so a knot-based tent basis
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


def test_momwire_default_bowtie_runs():
    """The default engine (BSplineSolver d=2) handles the bowtie's
    closed-loop cut with its n_seg=3 feed gap (interior knot available
    for the feed)."""
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

    # A 30x120 (3 deg) grid resolves the peak lobe well enough for the
    # 0.1 dBi check: both backends sample the SAME grid, so any
    # discretization bias cancels in the difference (the observed delta is
    # 0.038 dBi and is invariant to grid step from 1 to 3 deg). Keeps this
    # RHS-ordering guard in the fast PR lane at a fraction of the 90x360 cost.
    for phase_lr_deg in (0.0, 90.0):
        b = B12()
        b.phase_lr = phase_lr_deg
        ff_p = MomwireEngine(b).far_field(n_theta=30, n_phi=120, del_theta=3, del_phi=3)
        ff_n = PyNECEngine(b, ground=None).far_field(
            n_theta=30, n_phi=120, del_theta=3, del_phi=3
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


def test_network_spec_rejects_port_on_wire_with_no_named_wire():
    """PortOnWire("loop1") with no `loop1` edge in build_wires() should
    raise a clear error at engine construction time."""
    from antennaknobs import AntennaBuilder
    from antennaknobs.network import Driven, Network, PortOnWire, PortVirtual, TL
    from types import MappingProxyType

    class BadBuilder(AntennaBuilder):
        default_params = MappingProxyType({"freq": 28.0, "design_freq": 28.0})

        def build_wires(self):
            # Single straight wire, no named edges.
            return [((0, -2, 5), (0, 2, 5), 21, 1 + 0j)]

        def build_network(self):
            return Network(
                ports={
                    "loop1": PortOnWire("loop1"),  # no matching named edge!
                    "drv": PortVirtual("drv"),
                },
                branches=[TL(a="drv", b="loop1", z0=50, length=1.0)],
                sources=[Driven(port="drv")],
            )

    with pytest.raises(ValueError, match="no wire in build_wires"):
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
    from antennaknobs.network import Driven, Network, PortOnWire, PortVirtual, TL
    from types import MappingProxyType

    class Builder(AntennaBuilder):
        default_params = MappingProxyType({"freq": 28.0, "design_freq": 28.0})

        def build_wires(self):
            return [((0, -2.5, 5), (0, 2.5, 5), 21, None, "feed")]

        def build_network(self):
            return Network(
                ports={
                    "feed": PortOnWire("feed"),
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
    from antennaknobs.network import Driven, Load, Network, PortOnWire
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
                ports={"feed": PortOnWire("feed")},
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
        PortOnWire,
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
                    "feed": PortOnWire("feed"),
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
def test_pynec_network_rejects_port_on_wire_with_no_named_wire():
    """PortOnWire("loop1") with no `loop1` edge in build_wires() should
    raise a clear error at engine construction time — mirror of the
    MomwireEngine check."""
    from antennaknobs import AntennaBuilder
    from antennaknobs.network import Driven, Network, PortOnWire, PortVirtual, TL
    from types import MappingProxyType

    class Builder(AntennaBuilder):
        default_params = MappingProxyType({"freq": 28.0, "design_freq": 28.0})

        def build_wires(self):
            return [((0, -2.5, 5), (0, 2.5, 5), 21, 1 + 0j)]  # no name

        def build_network(self):
            return Network(
                ports={
                    "loop1": PortOnWire("loop1"),
                    "drv": PortVirtual("drv"),
                },
                branches=[TL(a="drv", b="loop1", z0=50, length=1.0)],
                sources=[Driven(port="drv")],
            )

    with pytest.raises(ValueError, match="no wire in build_wires"):
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
    from antennaknobs.network import Driven, Network, PortOnWire
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
                ports={"feed": PortOnWire("feed")},
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
        PortOnWire,
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
                    "feed": PortOnWire("feed"),
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


# --------------------------------------------------------------------------
# TwoPort branch — issue #65 piece (B).
#
# A lumped series R+jωL+1/(jωC) bridging two distinct feed segments. The
# reducer stamps (1/Z)·[[1,-1],[-1,1]] into the port-Y exactly like a TL
# branch, so it inherits the TL passive-port BC (I_ext=0). PyNECEngine can
# instead emit a native NEC2 nt_card (native_nt=True) as an independent
# oracle, analogous to build_tls() -> native tl_card for TL: nt_card takes
# the 2x2 admittance directly, and stamping a TL's own admittance through it
# reproduces tl_card, so it faithfully composes whatever Y we hand it. The
# showcase is designs/arrays/lumped_coupled_pair.py.
# --------------------------------------------------------------------------


def _sinusoidal(builder):
    """MomwireEngine on the SinusoidalSolver — NEC2's own basis family, so
    the reducer-vs-native and cross-engine comparisons carry almost no basis
    error and isolate the network composition / port convention itself."""
    from momwire import SinusoidalSolver

    return MomwireEngine(builder, solver=SinusoidalSolver, ground=None)


@needs_pynec
def test_twoport_cross_engine_impedance_matches():
    """Both engines reduce the TwoPort through the shared NetworkReducer, so on
    a matched basis (momwire's SinusoidalSolver = NEC2's basis family) they must
    agree on the driving-point impedance to near machine level — the residual is
    just the two solvers' quadrature, not any composition difference. This is the
    TwoPort analogue of the delta_looparray_network TL cross-engine check."""
    from antennaknobs.designs.arrays.lumped_coupled_pair import Builder as B

    z_mom = _sinusoidal(B()).impedance()[0]
    z_nec = PyNECEngine(B(), ground=None).impedance()[0]
    assert np.isfinite(z_nec.real) and np.isfinite(z_nec.imag), z_nec
    assert z_mom.real > 0 and z_nec.real > 0, (z_mom, z_nec)  # passive: R>0
    assert abs(z_mom - z_nec) / abs(z_mom) < 2e-3, f"mom={z_mom}, nec={z_nec}"


def _open_pair_builder():
    """lumped_coupled_pair with a ~open coupling (R = 1 GΩ): the parasite is
    effectively decoupled, so every path collapses to the isolated driven
    dipole. The base case that must agree exactly."""
    from antennaknobs.designs.arrays.lumped_coupled_pair import Builder as B

    params = {**B.default_params, "coupling_r_ohm": 1e9, "coupling_l_uH": 0.0}
    return lambda: B(params=params)


@needs_pynec
def test_twoport_open_branch_agrees_across_paths():
    """With the coupling opened (huge R), the reducer stamp contributes a
    vanishing admittance, so momwire-reducer, pynec-reducer, and pynec native
    nt_card must all land on the same (isolated-dipole) impedance."""
    b = _open_pair_builder()
    z_mom = _sinusoidal(b()).impedance()[0]
    z_red = PyNECEngine(b(), ground=None).impedance()[0]
    z_nat = PyNECEngine(b(), ground=None, native_nt=True).impedance()[0]
    # Same NEC basis on both PyNEC paths -> reducer == native to near
    # machine level.
    assert abs(z_red - z_nat) / abs(z_nat) < 1e-3, (z_red, z_nat)
    # Matched-basis momwire agrees to the solvers' quadrature difference.
    assert abs(z_mom - z_nat) / abs(z_nat) < 5e-3, (z_mom, z_nat)


@needs_pynec
def test_twoport_reducer_matches_native_nt_card_impedance():
    """The native nt_card driving-point impedance must equal the reducer's,
    including with a strongly-conducting branch on the DRIVEN segment — the
    case that historically showed a 54% \"convention gap\". That gap was this
    engine's readout dividing V by the wire-only structure current; NEC's
    ANTENNA INPUT PARAMETERS include the current leaving through the network
    port (nec2c network.c), which the readout now uses. See
    docs/plan-network-impedance-readout.md (issue #283).

    The stock lumped_coupled_pair splits the 1 V source's 13.8 mA into
    ~8.0 mA up the front wire and ~7.5 mA through the coupling element, so a
    wire-only readout is off by 35 Ω — this pins driving-point agreement, not
    just far field."""
    from antennaknobs.designs.arrays.lumped_coupled_pair import Builder as B

    z_red = PyNECEngine(B(), ground=None).impedance()[0]
    z_nat = PyNECEngine(B(), ground=None, native_nt=True).impedance()[0]
    assert abs(z_red - z_nat) / abs(z_nat) < 1e-6, (z_red, z_nat)


@needs_pynec
def test_twoport_reducer_matches_native_nt_card_far_field():
    """The native nt_card oracle bakes the 2x2 admittance into one NEC solve
    (like tl_card for TL); the reducer stamps the same admittance as a circuit
    post-process. They compose the RADIATING currents identically, so the far
    field must match. This is the piece (B) analogue of test_tl_composition's
    reducer-vs-native tl_card far-field check (impedance agreement is pinned
    separately by test_twoport_reducer_matches_native_nt_card_impedance).

    On a MATCHED basis (momwire SinusoidalSolver = NEC's family) the reducer's
    composed pattern lands right on the native nt_card oracle — the physical
    proof that the composition is correct. PyNEC's OWN reducer far field is
    looser: the re-excitation round-trip through per-port NEC solves nudges
    the pattern by a few tenths of a dB (well inside the tolerance the TL
    check uses cross-engine)."""
    from antennaknobs.designs.arrays.lumped_coupled_pair import Builder as B

    kw = dict(n_theta=90, n_phi=360, del_theta=1, del_phi=1)

    def pattern(eng):
        ff = eng.far_field(**kw)
        rings = np.array(ff.rings)
        return ff.max_gain, rings[89, 0], rings[89, 180]

    g_nat, f_nat, b_nat = pattern(PyNECEngine(B(), ground=None, native_nt=True))
    g_mom, f_mom, b_mom = pattern(_sinusoidal(B()))
    g_red, f_red, b_red = pattern(PyNECEngine(B(), ground=None))
    # Matched-basis reducer sits on the native oracle (composition is correct).
    assert abs(g_mom - g_nat) < 0.1, (g_mom, g_nat)
    assert abs(f_mom - f_nat) < 0.1 and abs(b_mom - b_nat) < 0.1
    # PyNEC's own reducer far field: looser (the #63 re-excitation offset).
    assert abs(g_red - g_nat) < 0.4, (g_red, g_nat)


@needs_pynec
def test_native_nt_rejects_unemittable_networks():
    """native_nt=True can only emit real nt_cards, so it must reject networks
    it can't back with real cards rather than silently falling through to the
    reducer and ceasing to be an independent oracle: (a) no TwoPort at all,
    (b) a virtual port (nt_card attaches to real segments only)."""
    from antennaknobs import AntennaBuilder
    from antennaknobs.network import (
        Driven,
        Network,
        PortOnWire,
        PortVirtual,
        TwoPort,
    )
    from types import MappingProxyType

    class NoTwoPort(AntennaBuilder):
        default_params = MappingProxyType({"freq": 28.0, "design_freq": 28.0})

        def build_wires(self):
            return [((0, -2.5, 5), (0, 2.5, 5), 21, None, "feed")]

        def build_network(self):
            from antennaknobs.network import Load

            return Network(
                ports={"feed": PortOnWire("feed")},
                branches=[Load(port="feed", r=10.0)],
                sources=[Driven(port="feed")],
            )

    class VirtualTwoPort(AntennaBuilder):
        default_params = MappingProxyType({"freq": 28.0, "design_freq": 28.0})

        def build_wires(self):
            return [((0, -2.5, 5), (0, 2.5, 5), 21, None, "feed")]

        def build_network(self):
            return Network(
                ports={"feed": PortOnWire("feed"), "v": PortVirtual("v")},
                branches=[TwoPort(a="feed", b="v", r=10.0)],
                sources=[Driven(port="feed")],
            )

    with pytest.raises(ValueError, match="no TwoPort"):
        PyNECEngine(NoTwoPort(), ground=None, native_nt=True)
    with pytest.raises(ValueError, match="real edge"):
        PyNECEngine(VirtualTwoPort(), ground=None, native_nt=True)


# --------------------------------------------------------------------------
# Shunt branch — issue #65 Q2 (shunt-to-common), the L-match enabler.
#
# A lumped R/L/C from one port to the common reference: Y[k,k] += y. Combined
# with a series TwoPort it expresses an L / pi / T matching network. The
# showcase is designs/loops/skyloop_lmatch.py — an 80 m loop run on 17 m,
# matched to 50 Ω.
# --------------------------------------------------------------------------


def test_shunt_lmatch_matches_circuit_theory():
    """An L-match (series TwoPort in→feed, Shunt across in) must reproduce the
    exact two-element transform 1/(y_shunt + 1/(z_series + Z_ant)) of the bare
    antenna impedance — the reducer composes lumped circuit theory on top of
    the extracted antenna Y."""
    from antennaknobs import AntennaBuilder
    from antennaknobs.network import (
        Driven,
        Network,
        PortOnWire,
        PortVirtual,
        Shunt,
        TwoPort,
    )
    from types import MappingProxyType

    wl = 299.792458 / 28.0
    ls, cp = 0.20e-6, 40e-12

    def wires():
        return [((0, -0.30 * wl, 7), (0, 0.30 * wl, 7), 41, None, "feed")]

    class Bare(AntennaBuilder):
        default_params = MappingProxyType({"design_freq": 28.0, "freq": 28.0})

        def build_wires(self):
            return wires()

        def build_network(self):
            return Network(
                ports={"feed": PortOnWire("feed")}, sources=[Driven(port="feed")]
            )

    class LMatch(AntennaBuilder):
        default_params = MappingProxyType({"design_freq": 28.0, "freq": 28.0})

        def build_wires(self):
            return wires()

        def build_network(self):
            return Network(
                ports={"feed": PortOnWire("feed"), "in": PortVirtual("in")},
                branches=[
                    TwoPort(a="in", b="feed", l=ls),
                    Shunt(port="in", c=cp),
                ],
                sources=[Driven(port="in", voltage=1 + 0j)],
            )

    z_ant = _sinusoidal(Bare()).impedance()[0]
    omega = 2.0 * np.pi * 28e6
    z_hand = 1.0 / (1j * omega * cp + 1.0 / (1j * omega * ls + z_ant))
    z_net = _sinusoidal(LMatch()).impedance()[0]
    assert np.allclose(z_net, z_hand, rtol=1e-6), (z_net, z_hand)


@needs_pynec
def test_skyloop_lmatch_matches_50ohm_cross_engine():
    """The showcase: an 80 m triangular skyloop run on 17 m is wildly reactive
    (~415 + 313j) but the stock L-match brings it to ~50 Ω. Both engines agree
    (the match is exact circuit theory on the extracted antenna Y)."""
    from antennaknobs.designs.loops.skyloop_lmatch import Builder as B

    z_mom = _sinusoidal(B()).impedance()[0]
    z_nec = PyNECEngine(B(), ground=None).impedance()[0]
    for z in (z_mom, z_nec):
        assert abs(z.real - 50.0) < 5.0 and abs(z.imag) < 5.0, z  # matched
    assert abs(z_mom - z_nec) / abs(z_mom) < 0.01, (z_mom, z_nec)


@needs_pynec
def test_pynec_shunt_routes_through_reducer_not_native():
    """A Shunt has no native NEC card, so PyNECEngine must reduce it (never the
    baked-context native path), and native_nt must reject it up front."""
    from antennaknobs import AntennaBuilder
    from antennaknobs.network import Driven, Network, PortOnWire, Shunt, TwoPort
    from types import MappingProxyType

    class ShuntDipole(AntennaBuilder):
        default_params = MappingProxyType({"design_freq": 28.0, "freq": 28.0})

        def build_wires(self):
            return [((0, -2.5, 5), (0, 2.5, 5), 21, None, "feed")]

        def build_network(self):
            return Network(
                ports={"feed": PortOnWire("feed")},
                branches=[Shunt(port="feed", c=50e-12)],
                sources=[Driven(port="feed")],
            )

    eng = PyNECEngine(ShuntDipole(), ground=None)
    assert eng._use_reducer, "Shunt design should take the reducer path"
    assert np.isfinite(eng.impedance()[0].real)

    class ShuntTwoPort(AntennaBuilder):
        default_params = MappingProxyType({"design_freq": 28.0, "freq": 28.0})

        def build_wires(self):
            return [
                ((0, -2.5, 5), (0, 2.5, 5), 21, None, "feed"),
                ((1, -2.5, 5), (1, 2.5, 5), 21, None, "feed2"),
            ]

        def build_network(self):
            return Network(
                ports={"feed": PortOnWire("feed"), "feed2": PortOnWire("feed2")},
                branches=[
                    TwoPort(a="feed", b="feed2", r=20.0),
                    Shunt(port="feed", c=50e-12),
                ],
                sources=[Driven(port="feed")],
            )

    with pytest.raises(ValueError, match="Shunt"):
        PyNECEngine(ShuntTwoPort(), ground=None, native_nt=True)


def test_series_short_twoport_is_a_hard_wire_on_the_engine():
    """A 0 Ω / 0 H series TwoPort is an ideal short between two real segments
    — the degenerate stamp the old admittance reducer had to reject, now a
    plain Group-2 element in the MNA core (issue #285). Through the real MoM
    Y it must give a finite impedance equal to the vanishing-resistance
    limit."""
    from antennaknobs import AntennaBuilder
    from antennaknobs.network import Driven, Network, PortOnWire, TwoPort
    from types import MappingProxyType

    def make(r=None, l=None):
        class Pair(AntennaBuilder):
            default_params = MappingProxyType({"design_freq": 28.0, "freq": 28.0})

            def build_wires(self):
                return [
                    ((0, -2.5, 5), (0, 2.5, 5), 21, None, "feed"),
                    ((1, -2.5, 5), (1, 2.5, 5), 21, None, "feed2"),
                ]

            def build_network(self):
                return Network(
                    ports={"feed": PortOnWire("feed"), "feed2": PortOnWire("feed2")},
                    branches=[TwoPort(a="feed", b="feed2", r=r, l=l)],
                    sources=[Driven(port="feed")],
                )

        return _sinusoidal(Pair()).impedance()[0]

    z_zero_ohm = make(r=0.0)
    z_zero_henry = make(l=0.0)
    z_limit = make(r=1e-9)
    assert np.isfinite(z_zero_ohm) and np.isfinite(z_zero_henry)
    assert abs(z_zero_ohm - z_limit) / abs(z_limit) < 1e-6
    assert abs(z_zero_henry - z_limit) / abs(z_limit) < 1e-6


@needs_pynec
def test_skyloop_matchbox_inert_is_passthrough():
    """Setting both L-match arms to zero makes the matchbox inert: the series
    arm is an ideal wire (a literal 0 H TwoPort) and the shunt a 0 F open, so
    the input impedance is just the bare antenna's. Since the MNA core
    (issue #285) these degenerate values are stamped literally —
    build_network no longer special-cases the topology."""
    from antennaknobs.designs.loops.skyloop_lmatch import Builder as B
    from antennaknobs.network import Driven, Network, PortOnWire
    from types import MappingProxyType

    inert = {**B.default_params, "series_L_uH": 0.0, "shunt_C_pF": 0.0}
    z_inert = _sinusoidal(B(params=inert)).impedance()[0]

    # Bare antenna: the same loop with no network branch on the feed.
    class Bare(B):
        default_params = MappingProxyType(inert)

        def build_network(self):
            return Network(
                ports={"feed": PortOnWire("feed")}, sources=[Driven(port="feed")]
            )

    z_ant = _sinusoidal(Bare()).impedance()[0]
    assert abs(z_inert - z_ant) / abs(z_ant) < 1e-9, (z_inert, z_ant)
    # And it agrees cross-engine (the pass-through is engine-agnostic).
    z_nec = PyNECEngine(B(params=inert), ground=None).impedance()[0]
    assert abs(z_inert - z_nec) / abs(z_inert) < 0.01, (z_inert, z_nec)


# --------------------------------------------------------------------------
# inverted_l_tmatch: T-network (series C, shunt L, series C) on a short
# reactive vertical — the first design with a pure interior circuit node.
# --------------------------------------------------------------------------


def _tmatch_bare(params=None):
    """The T-match design's antenna with the matchbox removed: same
    geometry, source directly on the feed."""
    from antennaknobs.designs.verticals.inverted_l_tmatch import Builder as B
    from antennaknobs.network import Driven, Network, PortOnWire
    from types import MappingProxyType

    class Bare(B):
        default_params = MappingProxyType(params or dict(B.default_params))

        def build_network(self):
            return Network(
                ports={"feed": PortOnWire("feed")}, sources=[Driven(port="feed")]
            )

    return Bare()


def test_tmatch_matches_circuit_theory():
    """The T-network must reproduce the exact three-element transform
    Z_in = X_C1 + (Z_L ∥ (X_C2 + Z_ant)) of the bare antenna impedance —
    lumped circuit theory composed on the extracted antenna Y, through a
    tee midpoint that is a pure interior node (no antenna segment, no TL:
    the only design whose KCL row has no Group-1 stamp at all). The stock
    coil has finite Q, so Z_L carries its ESR ωL/Q (issue #298)."""
    from antennaknobs.designs.verticals.inverted_l_tmatch import Builder as B

    p = B.default_params
    omega = 2.0 * np.pi * p["freq"] * 1e6
    xc1 = 1.0 / (1j * omega * p["series_c1_pF"] * 1e-12)
    l = p["shunt_l_uH"] * 1e-6
    xl = omega * l / p["coil_q"] + 1j * omega * l
    xc2 = 1.0 / (1j * omega * p["series_c2_pF"] * 1e-12)

    z_ant = _sinusoidal(_tmatch_bare()).impedance()[0]
    z_hand = xc1 + 1.0 / (1.0 / xl + 1.0 / (xc2 + z_ant))
    z_net = _sinusoidal(B()).impedance()[0]
    assert np.allclose(z_net, z_hand, rtol=1e-9), (z_net, z_hand)


@needs_pynec
def test_inverted_l_tmatch_matches_50ohm_cross_engine():
    """The showcase: a 10 m inverted-L worked on 12 m is a short vertical
    (~10.8 − 121.7j) but the stock T-network brings it to ~50 Ω. Both
    engines agree (the match is exact circuit theory on the antenna Y)."""
    from antennaknobs.designs.verticals.inverted_l_tmatch import Builder as B

    z_mom = _sinusoidal(B()).impedance()[0]
    z_nec = PyNECEngine(B(), ground=None).impedance()[0]
    for z in (z_mom, z_nec):
        assert abs(z.real - 50.0) < 5.0 and abs(z.imag) < 5.0, z  # matched
    assert abs(z_mom - z_nec) / abs(z_mom) < 0.01, (z_mom, z_nec)


def test_tmatch_degenerate_endpoints():
    """T-network slider endpoints under the MNA core (issue #285):

    - shunt L = 0 hard-shorts the tee midpoint to common (a Group-2 ideal
      short on a pure interior node — the old admittance reducer raised
      here), so the input sees exactly C1's reactance;
    - series C2 = 0 is an OPEN that disconnects the antenna (a series
      capacitor's absent limit is C → ∞, not C → 0), so the input sees
      exactly C1 in series with the shunt L;
    - series C1 = 0 open-circuits the SOURCE itself: the delivered current
      is exactly zero and the readout reports a clean Z = ∞ (real infinity,
      no NaN, no numpy warnings — issue #289).
    """
    from antennaknobs.designs.verticals.inverted_l_tmatch import Builder as B

    p = B.default_params
    omega = 2.0 * np.pi * p["freq"] * 1e6
    xc1 = 1.0 / (1j * omega * p["series_c1_pF"] * 1e-12)
    l = p["shunt_l_uH"] * 1e-6
    xl = omega * l / p["coil_q"] + 1j * omega * l  # stock coil ESR included

    z = _sinusoidal(B(params={**p, "shunt_l_uH": 0.0})).impedance()[0]
    assert np.allclose(z, xc1, rtol=1e-12), (z, xc1)

    z = _sinusoidal(B(params={**p, "series_c2_pF": 0.0})).impedance()[0]
    assert np.allclose(z, xc1 + xl, rtol=1e-12), (z, xc1 + xl)

    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        z = _sinusoidal(B(params={**p, "series_c1_pF": 0.0})).impedance()[0]
    assert np.isinf(z.real) and z.imag == 0.0, z

"""The far field of currents below the ground plane (issue #1341; the
readout side of momwire#570).

Both readouts — `MomwireEngine._evaluate_M_perp` and the web server's
`_mag2_at_directions` — place a buried element through the interface, as
the transmitted plane wave of `antennaknobs.in_medium`, instead of imaging
it as if it stood in air. Four instruments, in order of what they pin:

* the ε̃ = 1 collapse, which fixes the assembly, the basis vectors and every
  sign at once (at ε̃ = 1 the Fresnel image coefficients are identically
  zero, so the whole grounded readout must equal free space);
* momwire's own numerical below→above Sommerfeld integrals as an oracle,
  Richardson-extrapolated in 1/R, with an adversarial probe that must miss;
* bit-identity of every above-ground readout, including that the
  transmitted helper is not entered at all when nothing is buried;
* the two readouts against each other on the catalog's buried designs —
  two implementations of one formula.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from antennaknobs import in_medium
from antennaknobs.engines.momwire import EPS0, MomwireEngine
from antennaknobs.web.server import (
    _attach_in_medium_fraction,
    _mag2_at_directions,
    _moment_segments,
    _pattern_cuts,
)

SOIL = ("finite", 13.0, 0.005)
AIR = ("finite", 1.0, 0.0)  # ε̃ = 1: a "ground" that is not one
MU0 = 4e-7 * math.pi
C0 = 299792458.0
# The two readouts derive ε̃ from the SAME ε₀ (`EPS0` here, `_EPS0` in the
# server, equal by inspection). Building a response with a differently
# rounded ε₀ moves ε̃ by 7e-10 and shows up as a 2e-10 disagreement between
# them — an artefact of the test, not of either readout.


# --- the helpers on synthetic moment sets -----------------------------------


def _moments(z_list, i_list):
    mid = np.array([[0.0, 0.0, z] for z in z_list], dtype=float)
    dr = np.tile(np.array([0.0, 0.0, 0.01]), (len(z_list), 1))
    i_mid = np.array(i_list, dtype=complex)
    return mid, dr, i_mid


def test_below_surface_mask_uses_a_relative_tolerance():
    mid, _, _ = _moments([1.0, -1e-9, -0.5], [1, 1, 1])
    mask = in_medium.below_surface_mask(mid, 0.0)
    assert mask.tolist() == [False, False, True], "float noise at z=0 is ON the plane"


def test_moment_fraction_is_current_times_length():
    mid, dr, i_mid = _moments([1.0, -1.0], [3.0, 1.0])
    mask = in_medium.below_surface_mask(mid, 0.0)
    assert in_medium.moment_fraction(dr, i_mid, mask) == pytest.approx(0.25)


# --- G1: the ε̃ = 1 collapse -------------------------------------------------


def _mixed_moment_set(seed=570, n=24, ground_z=0.0):
    """A random moment set straddling the plane — half buried, half not,
    every component complex, so no symmetry can hide a sign."""
    rng = np.random.default_rng(seed)
    mid = rng.uniform(-3.0, 3.0, (n, 3))
    mid[:, 2] = ground_z + np.concatenate(
        [rng.uniform(0.05, 2.0, n // 2), -rng.uniform(0.05, 2.0, n - n // 2)]
    )
    dr = 0.05 * rng.normal(size=(n, 3))
    i_mid = rng.normal(size=n) + 1j * rng.normal(size=n)
    return mid, dr, i_mid


def _free_space_mag2(mid, dr, i_mid, k, rhat):
    m = np.asarray(i_mid)[:, None] * dr
    M = np.einsum(
        "...n,nc->...c", np.exp(1j * k * np.einsum("...c,nc->...n", rhat, mid)), m
    )
    M_perp = M - np.sum(M * rhat, axis=-1)[..., None] * rhat
    return np.sum(M_perp.real**2 + M_perp.imag**2, axis=-1)


def _grid_rhat(theta, phi):
    s, c = np.sin(theta)[:, None], np.cos(theta)[:, None]
    cp, sp = np.cos(phi)[None, :], np.sin(phi)[None, :]
    shape = (theta.size, phi.size)
    return np.stack(
        [
            np.broadcast_to(s * cp, shape),
            np.broadcast_to(s * sp, shape),
            np.broadcast_to(c, shape),
        ],
        axis=-1,
    )


def test_transmitted_factors_collapse_to_free_space_at_unit_permittivity():
    k_p = 2.0 * np.pi / 42.8
    k_m = in_medium.medium_wavenumber(complex(1.0, 0.0), k_p)
    assert k_m == k_p
    theta = np.deg2rad(np.linspace(0.0, 89.99, 2000))
    t_e, t_h, t_v, k_mz = in_medium.transmitted_factors(theta, k_p, k_m)
    assert np.max(np.abs(t_e - 1.0)) < 1e-15
    assert np.max(np.abs(t_h - np.cos(theta))) < 1e-15
    assert np.max(np.abs(t_v + np.sin(theta))) < 1e-15
    # The depth leg is then the air leg, which is what makes the phase
    # reference of the two terms the same point.
    assert np.max(np.abs(k_mz - k_p * np.cos(theta))) < 1e-15 * k_p


@pytest.mark.parametrize("ground_z", [0.0, 1.7])
def test_engine_readout_collapses_to_free_space_at_unit_permittivity(ground_z):
    """G1, engine side. At ε̃ = 1 the Fresnel image coefficients are
    identically zero, so the whole grounded readout is the free-space one —
    which it can only be if the transmitted term's factors, basis vectors,
    signs and phase reference are all right. A non-zero plane height is in
    the sweep because the buried term's vertical leg is referenced to the
    PLANE and has to be carried back to the origin."""
    from antennaknobs.designs.dipoles.invvee import Builder

    eng = MomwireEngine(Builder(), ground=AIR, ground_z=ground_z)
    mid, dr, i_mid = _mixed_moment_set(ground_z=ground_z)
    k = 2.0 * np.pi / eng._wavelength_for(eng.builder.freq)
    freq_hz = eng.builder.freq * 1e6
    theta = np.deg2rad(np.arange(0.0, 90.0, 1.0))
    phi = np.deg2rad(np.arange(0.0, 361.0, 5.0))

    got = eng._evaluate_M_perp(mid, dr, i_mid, k, theta, phi, freq_hz)
    want = _free_space_mag2(mid, dr, i_mid, k, _grid_rhat(theta, phi))
    assert np.max(np.abs(got - want)) / np.max(want) < 1e-12


def _air_response(k, mid, dr, i_mid):
    return {
        "wires": [{"knot_positions": [[0.0, 0.0, 0.0]]}],  # never read: mid is passed
        "k_meas_m_inv": k,
        "ground": True,
        "ground_eps_r": 1.0,
        "ground_eps_im": 0.0,
        "measurement_freq_mhz": 1e-6 * k * C0 / (2.0 * np.pi),
        "directivity_norm": 1.0,
    }


def test_web_readout_collapses_to_free_space_at_unit_permittivity():
    """G1, cuts side. Same instrument on the unstructured-direction readout,
    including the zenith sample, where the plane of incidence is undefined
    and the azimuth of the transmitted basis is substituted.

    Elevations under a degree are left out, and the reason is the IMAGE
    branch, not this one. At ε̃ = 1 its Fresnel coefficients are
    (cosθ − √(1 − sin²θ))/(…), a difference of two float routes to the same
    cosine, so near the horizon they are ~1e-16/cosθ instead of zero: an
    all-above-ground moment set reads 8e-9 against free space at an
    elevation of 0.006° and 5e-14 at 0.6°, with nothing buried at all."""
    k = 2.0 * np.pi / 42.8
    mid, dr, i_mid = _mixed_moment_set(seed=1341)
    rng = np.random.default_rng(7)
    rhat = rng.normal(size=(400, 3))
    rhat[:, 2] = 0.02 + 0.98 * np.abs(rhat[:, 2])
    rhat /= np.linalg.norm(rhat, axis=1)[:, None]
    rhat = np.vstack([rhat, [0.0, 0.0, 1.0]])  # the zenith sample
    out = _air_response(k, mid, dr, i_mid)

    got = _mag2_at_directions(out, rhat, mid=mid, dr=dr, i_mid=i_mid)
    want = _free_space_mag2(mid, dr, i_mid, k, rhat)
    assert np.max(np.abs(got - want)) / np.max(want) < 1e-12


@pytest.mark.parametrize("diffraction", [False, True])
def test_the_terrain_branches_collapse_to_free_space_too(diffraction):
    """G1 through the two faceted-terrain composers, on one flat facet of
    ε̃ = 1. It is the branch-specific gate: the specular composer CORRECTS a
    reflected wave onto the caller's M_perp, so the transmitted moment
    belongs in M_perp before it, while the UTD composer rebuilds the direct
    term per segment and reads M_perp only for its shape, so the same
    moment has to travel separately and be summed into the FIELD there. A
    term folded into the wrong one of those is dropped, and this is what
    notices."""
    from antennaknobs.designs.dipoles.invvee import Builder
    from antennaknobs.terrain import Terrain, flat_terrain
    from antennaknobs.web.adapter import _pack_terrain

    terrain = Terrain(sectors=flat_terrain(*AIR[1:]).sectors, diffraction=diffraction)
    eng = MomwireEngine(Builder(), ground=("terrain", terrain))
    mid, dr, i_mid = _mixed_moment_set()
    k = 2.0 * np.pi / eng._wavelength_for(eng.builder.freq)
    theta = np.deg2rad(np.arange(0.0, 89.0, 2.0))
    phi = np.deg2rad(np.arange(0.0, 360.0, 10.0))
    rhat = _grid_rhat(theta, phi)
    want = _free_space_mag2(mid, dr, i_mid, k, rhat)

    grid = eng._evaluate_M_perp(mid, dr, i_mid, k, theta, phi, eng.builder.freq * 1e6)
    assert np.max(np.abs(grid - want)) / np.max(want) < 1e-12

    out = {
        "k_meas_m_inv": k,
        "ground": True,
        "ground_eps_r": AIR[1],
        "ground_eps_im": 0.0,
        "measurement_freq_mhz": eng.builder.freq,
        "directivity_norm": 1.0,
        "ground_terrain": _pack_terrain(terrain),
    }
    cuts = _mag2_at_directions(
        out, rhat, mid=mid, dr=dr, i_mid=i_mid, diffraction=diffraction
    )
    assert np.max(np.abs(cuts - want)) / np.max(want) < 1e-12


# --- G2: momwire's numerical transmitted integrals as the oracle ------------

_ORACLE_FREQ_HZ = 7e6
_ORACLE_SOIL = (13.0, 0.005)
# The numerical field approaches the closed form exactly as 1/R (measured
# halving ratios 2.000 on every rung, momwire scratch/570-far-field P-D), so
# the decisive comparison is the 1/R extrapolation of the rung pair, not the
# raw value at either rung: 2·E(80λ₀) − E(40λ₀).
_ORACLE_RUNGS = (40, 80)
_ORACLE_BAR = 3e-5


def _oracle_medium():
    omega = 2.0 * math.pi * _ORACLE_FREQ_HZ
    eps_t = _ORACLE_SOIL[0] - 1j * _ORACLE_SOIL[1] / (omega * EPS0)
    k_p = omega / C0
    return eps_t, k_p, in_medium.medium_wavenumber(eps_t, k_p), omega


def _numerical_far(eps_t, k_p, omega, radius, theta, phi, depth, kind):
    """R·e^{+jk_pR}·(E_θ, E_φ) at (R, θ, φ) from momwire's six numerical
    below→above integrals, assembled through its own cylindrical forms."""
    from momwire._sommerfeld_transmitted import _six_integrals_transmitted

    rho, z = radius * math.sin(theta), radius * math.cos(theta)
    v = _six_integrals_transmitted(
        eps_t, k_p, rho, z, -depth, rtol=1e-11, selfconv=False
    )
    c1 = -1j * omega * MU0 / (4.0 * math.pi)
    if kind == "VED":
        e_rho, e_phi, e_z = c1 * v[0], 0j, c1 * v[1]
    else:
        e_rho = c1 * math.cos(phi) * (v[2] + v[5])
        e_phi = -c1 * math.sin(phi) * (v[3] + v[5])
        e_z = -c1 * math.cos(phi) * v[4]
    e_th = e_rho * math.cos(theta) - e_z * math.sin(theta)
    return np.array([e_th, e_phi]) / (np.exp(-1j * k_p * radius) / radius)


def _closed_far(k_p, k_m, omega, theta, phi, depth, kind, *, sabotage=None):
    """The same two components from the shipped factors, for a unit
    horizontal (x̂) or vertical (ẑ) element at ``depth``."""
    t_e, t_h, t_v, k_mz = in_medium.transmitted_factors(np.array([theta]), k_p, k_m)
    c1 = -1j * omega * MU0 / (4.0 * math.pi)
    sign = +1j if sabotage == "depth_leg" else -1j
    phase = np.exp(sign * k_mz[0] * depth)
    if sabotage == "negate_t_v":
        t_v = -t_v
    if kind == "VED":
        return np.array([c1 * phase * t_v[0], 0j])
    return np.array(
        [c1 * phase * t_h[0] * math.cos(phi), -c1 * phase * t_e[0] * math.sin(phi)]
    )


def test_transmitted_factors_match_the_numerical_transmitted_integral():
    """G2. The closed form against momwire's own numerical below→above
    integrals — a different code path, a different quadrature and no
    stationary-phase argument anywhere in it.

    The adversarial half is the point: the same comparison with the depth
    leg conjugated, or with the vertical factor's sign flipped, has to MISS
    the bar by orders of magnitude, or the gate is measuring nothing."""
    eps_t, k_p, k_m, omega = _oracle_medium()
    lam0 = 2.0 * math.pi / k_p
    worst = {None: 0.0, "depth_leg": 0.0, "negate_t_v": 0.0}
    for kind, depth, phi in (("HED", 0.15, 0.6), ("VED", 0.6, 0.0)):
        for theta_deg in (10.0, 30.0, 50.0):
            theta = math.radians(theta_deg)
            lo, hi = (
                _numerical_far(eps_t, k_p, omega, n * lam0, theta, phi, depth, kind)
                for n in _ORACLE_RUNGS
            )
            reference = 2.0 * hi - lo
            for key in worst:
                got = _closed_far(
                    k_p, k_m, omega, theta, phi, depth, kind, sabotage=key
                )
                rel = float(np.linalg.norm(got - reference) / np.linalg.norm(reference))
                worst[key] = max(worst[key], rel)
    assert worst[None] < _ORACLE_BAR, worst
    assert worst["depth_leg"] > 1e-2, worst
    assert worst["negate_t_v"] > 1e-2, worst


# --- G3: nothing below the plane is bit-identical ----------------------------

# Σ|M_perp|² over the grid below. Measured bit-identical to the value the
# pre-change (#1341) readout produced at v0.79.0 on the same inputs, by both
# readouts — which is what "an above-ground pattern did not move" means.
_ABOVE_ONLY_MAG2_SUM = 208.8794626037643


def _above_only_moment_set():
    rng = np.random.default_rng(1060)
    mid = rng.uniform(-3.0, 3.0, (16, 3))
    mid[:, 2] = rng.uniform(0.2, 4.0, 16)
    dr = 0.05 * rng.normal(size=(16, 3))
    i_mid = rng.normal(size=16) + 1j * rng.normal(size=16)
    return mid, dr, i_mid


def test_above_ground_readout_never_enters_the_transmitted_helper(monkeypatch):
    """G3. With nothing below the plane the buried branch is not merely
    zero-valued, it is not reached: the helper is replaced by a raise."""
    from antennaknobs.designs.dipoles.invvee import Builder

    def refuse(*args, **kwargs):
        raise AssertionError("the transmitted term was evaluated with nothing buried")

    monkeypatch.setattr(in_medium, "transmitted_m_perp", refuse)
    mid, dr, i_mid = _above_only_moment_set()
    eng = MomwireEngine(Builder(), ground=SOIL)
    k = 2.0 * np.pi / eng._wavelength_for(eng.builder.freq)
    theta = np.deg2rad(np.arange(0.0, 90.0, 2.0))
    phi = np.deg2rad(np.arange(0.0, 361.0, 10.0))
    mag2 = eng._evaluate_M_perp(mid, dr, i_mid, k, theta, phi, eng.builder.freq * 1e6)
    assert float(np.sum(mag2)) == pytest.approx(_ABOVE_ONLY_MAG2_SUM, rel=1e-12)

    out = {
        "k_meas_m_inv": k,
        "ground": True,
        "ground_eps_r": SOIL[1],
        "ground_eps_im": -SOIL[2] / (2.0 * np.pi * eng.builder.freq * 1e6 * EPS0),
        "measurement_freq_mhz": eng.builder.freq,
        "directivity_norm": 1.0,
    }
    cuts = _mag2_at_directions(out, _grid_rhat(theta, phi), mid=mid, dr=dr, i_mid=i_mid)
    np.testing.assert_allclose(cuts, mag2, rtol=1e-12)


def test_free_space_far_field_is_untouched():
    from antennaknobs.designs.dipoles.invvee import Builder

    ff = MomwireEngine(Builder()).far_field(
        n_theta=90, n_phi=360, del_theta=1, del_phi=1
    )
    assert ff.in_medium_moment_fraction == 0.0
    # The pre-#1341 readout's number on this deck. "Untouched" is by
    # construction (nothing below the plane takes the same code path), and the
    # pin is to the last digit a different BLAS/CPU can still agree on —
    # CI's runner reads 1.9237984864486997 against 1.923798486448699 here,
    # which is the cross-machine bit-equality trap, not a change.
    assert ff.max_gain == pytest.approx(1.923798486448699, rel=1e-12)


def test_an_above_ground_response_carries_no_in_medium_fraction():
    out = {
        "wires": [
            {
                "knot_positions": [[0.0, 0.0, 1.0], [0.0, 0.0, 1.01]],
                "knot_currents_re": [1.0, 1.0],
                "knot_currents_im": [0.0, 0.0],
            }
        ],
        "ground": True,
    }
    _attach_in_medium_fraction(out)
    assert "in_medium_moment_fraction" not in out


# --- G4 / G5: the catalog's buried designs -----------------------------------

BURIED_DESIGNS = {
    "buried_dipole": "antennaknobs.designs.specialty.buried_dipole",
    "buried_radial_vertical": "antennaknobs.designs.verticals.buried_radial_vertical",
    "elevated_buried_counterpoise": (
        "antennaknobs.designs.verticals.elevated_buried_counterpoise"
    ),
}


def _engine(name):
    module = __import__(BURIED_DESIGNS[name], fromlist=["Builder"])
    return MomwireEngine(module.Builder(), ground=SOIL)


@pytest.mark.antenna_computation_check
def test_wholly_buried_dipole_is_served():
    """G4. Nothing is above the plane, so there is no image at all and the
    pattern is the transmitted field alone. It is a real, finite pattern:
    the 0.15 m depth is 0.013 in-medium wavelengths at 7 MHz, so what the
    soil takes is mostly the interface, not the path."""
    eng = _engine("buried_dipole")
    ff = eng.far_field(n_theta=90, n_phi=360, del_theta=1, del_phi=1)
    assert ff.in_medium_moment_fraction == pytest.approx(1.0)
    assert np.isfinite(ff.max_gain) and np.isfinite(ff.min_gain)
    assert ff.max_gain == pytest.approx(-21.42708041701554, abs=1e-6)


@pytest.mark.antenna_computation_check
def test_buried_radial_vertical_moves_less_than_the_retired_note_allowed():
    """G4. The #1341 note said imaging this screen instead of placing it
    accounted for 0.37 dB at the peak and set 0.46 dB as the bar the honest
    answer had to come in under. Measured: −0.187 dB."""
    eng = _engine("buried_radial_vertical")
    ff = eng.far_field(n_theta=90, n_phi=360, del_theta=1, del_phi=1)
    assert 0.30 < ff.in_medium_moment_fraction < 0.45
    imaged_peak_dbi = -2.7092732487947693  # the v0.79.0 readout's number
    assert ff.max_gain == pytest.approx(-2.895921847500022, abs=1e-6)
    assert abs(ff.max_gain - imaged_peak_dbi) < 0.46


@pytest.mark.antenna_computation_check
def test_elevated_buried_counterpoise_is_served():
    eng = _engine("elevated_buried_counterpoise")
    ff = eng.far_field(n_theta=90, n_phi=360, del_theta=1, del_phi=1)
    assert 0.1 < ff.in_medium_moment_fraction < 0.3
    assert ff.max_gain == pytest.approx(-1.8077375863516376, abs=1e-6)


@pytest.mark.antenna_computation_check
@pytest.mark.parametrize("name", ["buried_dipole", "buried_radial_vertical"])
def test_the_two_readouts_agree_on_a_buried_design(name):
    """G5. The engine grid and the cuts readout are two implementations of
    one formula, on the currents of a real buried solve."""
    eng = _engine(name)
    wavelength = eng._wavelength_for(eng.builder.freq)
    k = 2.0 * np.pi / wavelength
    freq_hz = eng.builder.freq * 1e6
    sim, coeffs, _z = eng._solved_excited(wavelength)
    mid, dr, i_mid = eng._segment_dipoles(sim, coeffs)
    theta = np.deg2rad(np.arange(0.0, 90.0, 3.0))
    phi = np.deg2rad(np.arange(0.0, 360.0, 6.0))

    grid = eng._evaluate_M_perp(mid, dr, i_mid, k, theta, phi, freq_hz)
    out = {
        "k_meas_m_inv": k,
        "ground": True,
        "ground_eps_r": SOIL[1],
        "ground_eps_im": -SOIL[2] / (2.0 * np.pi * freq_hz * EPS0),
        "measurement_freq_mhz": eng.builder.freq,
        "directivity_norm": 1.0,
    }
    cuts = _mag2_at_directions(out, _grid_rhat(theta, phi), mid=mid, dr=dr, i_mid=i_mid)
    assert np.max(np.abs(cuts - grid)) / np.max(grid) < 1e-10


@pytest.mark.antenna_computation_check
def test_the_web_solve_path_serves_the_buried_dipole_with_cuts():
    """G4, served. The response carries the share of current below the plane
    and a full set of cuts — no refusal, nothing withheld."""
    from antennaknobs.web import server

    out = server.solve(
        {
            "geometry": "specialty.buried_dipole",
            "ground": True,
            # The buried half-space is only a medium under the Sommerfeld
            # ground; momwire refuses the deck outright under refl-coef.
            "ground_model": "sommerfeld",
            "measurement_freq_mhz": 7.0,
            "design_freq_mhz": 7.0,
            "momwire_model": "bspline",
        }
    )
    assert "pattern_refusal" not in out and "pattern_note" not in out
    assert out["in_medium_moment_fraction"] == pytest.approx(1.0)
    mid, dr, i_mid = _moment_segments(out)
    cuts = _pattern_cuts(out, 15.0, 0.0, mid=mid, dr=dr, i_mid=i_mid)
    assert cuts is not None
    assert len(cuts["azimuth"]) == len(cuts["elevation"]) > 0
    assert all(math.isfinite(v) for v in cuts["azimuth"] + cuts["elevation"])

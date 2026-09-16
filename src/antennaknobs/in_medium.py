"""The far field of a current below the interface (issue #1341, momwire#570).

Both far-field readouts in this package — `MomwireEngine._evaluate_M_perp`
(the grid behind the compare table and the CLI plots) and the web server's
`_mag2_at_directions` (the polar-chart cuts) — build a pattern as a direct
term plus a geometric image in the ground plane, Fresnel-corrected on the
reflected wave. That is the far field of a current ABOVE the interface. A
current BELOW it reaches the air through the boundary instead, and its far
field is the transmitted plane wave. This module is where that term is
written; both readouts split their moment set on `below_surface_mask` and
add `transmitted_m_perp` to their direct term.

Conventions are momwire's: e^{+jωt}, air above z = ``ground_z`` with real
k_p = ω/c, medium below with k_m = k_p·√ε̃ on the Im k_m ≤ 0 branch, where
ε̃ = ε_r − jσ/(ωε₀). The far field is

    E = −jηk_p/(4π) · e^{−jk_pR}/R · (M_θ θ̂ + M_φ φ̂)

on NEC's basis θ̂ = (cosθcosφ, cosθsinφ, −sinθ), φ̂ = (−sinφ, cosφ, 0), so
what a readout accumulates is the moment M, not the field.

An element at (x, y, z) carrying m = I·dl at depth d = ground_z − z > 0
contributes

    k_pz = k_p cosθ,   k_mz = √(k_m² − k_p² sin²θ)         (Im k_mz ≤ 0)
    t_s  = 2 k_pz/(k_pz + k_mz)                 Fresnel TE, air → medium
    t_p  = 2 k_pz k_p k_m/(k_m² k_pz + k_p² k_mz)          Fresnel TM
    T_e  = t_s,   T_h = t_p·k_mz/k_m,   T_v = −t_p·(k_p/k_m)·sinθ
    M_θ += phase·(T_h·(m_x cosφ + m_y sinφ) + T_v·m_z)
    M_φ += phase·T_e·(−m_x sinφ + m_y cosφ)

The coefficients are the reciprocal reading of a plane wave arriving from
(θ, φ) and transmitted into the medium — Snell's sinθ_t = (k_p/k_m)·sinθ,
cosθ_t = k_mz/k_m — read at the buried source, which is why they are the
Fresnel pair. Stationary phase over momwire's below→above Sommerfeld
surfaces at the saddle λ_s = k_p sinθ gives the same three factors by a
route that touches no reciprocity argument (momwire `scratch/570-far-field/`,
gate P-C: the two spellings agree to 7.6e-16).

**The Fresnel spelling is load-bearing.** The saddle spelling reads
γ_p = √(λ_s² − k_p²) from λ_s − k_p = k_p(sinθ − 1), which cancels eight
digits at grazing (4.5e-9 at θ = 89.99°, 1e-14 below 85°). k_pz = k_p cosθ
cancels nothing at any angle; `_factors` says how k_mz keeps the same
property.

``phase`` carries the horizontal position and the vertical leg, referenced
to the SAME origin the above-ground term uses so that the two sum
coherently:

    phase = exp(+j k_p·(r̂_x x + r̂_y y + cosθ·ground_z)) · exp(−j k_mz d)

The vertical leg is the in-medium exp(−j k_mz d) from the source up to the
plane, then the air leg exp(+j k_p cosθ·ground_z) from the plane to the
origin's reference sphere — NOT exp(+j k_p cosθ·z), which is the leg the
element would have if it stood in air.

Two limits pin the assembly. At ε̃ = 1 (k_m = k_p) the factors collapse to
(1, cosθ, −sinθ) and the phase to exp(+j k_p r̂·r), so the transmitted
moment IS the free-space moment of the same currents, exactly. At θ = 90°
every factor vanishes over a lossy medium, as the finite-ground image
pattern does. The lateral wave and the critical-angle structure are
O(1/R²) at an observer in air, so they are not in the 1/R coefficient a
far-field readout is.
"""

from __future__ import annotations

from typing import NamedTuple

import numpy as np

# Below this |sinθ| the plane containing ẑ and r̂ is not resolved in float,
# so the azimuth of the transmitted basis is substituted rather than
# divided for. Exact, not a guard: see `transmitted_m_perp`.
_POLE_SIN = 1e-12


def below_surface_mask(
    mid: np.ndarray, ground_z: float | None, *, tol=None
) -> np.ndarray:
    """Segments whose midpoint lies below the ground plane at ``ground_z``.

    ``tol`` defaults to 1e-6 of the structure's largest extent (at least
    1 m): a segment whose midpoint is a float-noise below the plane is ON
    the plane, and a deliberate burial is orders of magnitude deeper.
    """
    mid = np.asarray(mid, dtype=float)
    if ground_z is None or mid.size == 0:
        return np.zeros(mid.shape[0], dtype=bool)
    if tol is None:
        extent = float(np.max(np.ptp(mid, axis=0))) if mid.shape[0] > 1 else 0.0
        tol = 1e-6 * max(extent, 1.0)
    return mid[:, 2] < float(ground_z) - tol


def moment_fraction(dr: np.ndarray, i_mid: np.ndarray, mask: np.ndarray) -> float:
    """Share of Σ|I|·|dl| carried by the masked segments."""
    w = np.abs(np.asarray(i_mid)) * np.linalg.norm(np.asarray(dr, dtype=float), axis=1)
    total = float(np.sum(w))
    return float(np.sum(w[mask]) / total) if total > 0.0 else 0.0


def medium_wavenumber(eps_t, k_p) -> complex:
    """k_m = k_p·√ε̃ on the Im ≤ 0 branch.

    Delegated to momwire's own `k_medium` rather than spelled again here, so
    the readout and the fill cannot drift apart on which root of ε̃ they
    mean — the branch is the whole content of the function.
    """
    from momwire._sommerfeld_below import k_medium

    return k_medium(eps_t, k_p)


class TransmittedFactors(NamedTuple):
    """The three angular transmission factors of the module docstring, plus
    the in-medium vertical wavenumber ``k_mz`` that carries the depth
    (exp(−j·k_mz·d)). Arrays of the direction set's shape."""

    t_e: np.ndarray
    t_h: np.ndarray
    t_v: np.ndarray
    k_mz: np.ndarray


def transmitted_factors(theta, k_p, k_m) -> TransmittedFactors:
    """(T_e, T_h, T_v, k_mz) at zenith angles ``theta`` (radians)."""
    theta = np.asarray(theta, dtype=float)
    return _factors(np.cos(theta), np.sin(theta), k_p, k_m)


def _factors(cos_t, sin_t, k_p, k_m) -> TransmittedFactors:
    """The factors from cosθ and sinθ directly — the form a readout holding
    a unit r̂ has, with sinθ = |r̂ projected on the plane| and no arccos
    round trip between them."""
    cos_t = np.asarray(cos_t, dtype=float)
    sin_t = np.asarray(sin_t, dtype=float)
    k_pz = k_p * cos_t + 0j
    # k_mz² = k_m² − k_p² sin²θ, spelled as (k_m − k_p)(k_m + k_p) + k_pz².
    # Algebraically the same; numerically it is the difference of the
    # WAVENUMBERS that is formed, which is exactly zero at ε̃ = 1, leaving
    # k_mz = k_p|cosθ| to half an ulp. The literal k_m² − (k_p sinθ)²
    # cancels against sin²θ ≈ 1 instead and reads 3e-13 on the ε̃ = 1
    # collapse at θ = 89°. The new spelling loses digits only when
    # ε̃ ≈ sin²θ — the critical angle of a medium THINNER than air, which
    # no ground is.
    k_mz = np.sqrt((k_m - k_p) * (k_m + k_p) + k_pz * k_pz)
    k_mz = np.where(k_mz.imag > 0.0, -k_mz, k_mz)  # the decaying root
    # Both denominators vanish together only at θ = 90° over ε̃ = 1, which
    # is not a ground: over any real soil k_mz is bounded away from k_pz and
    # the grazing limit of all three factors is the zero written here (the
    # same zero the image pattern goes to, and what NEC prints as −999.99).
    den_s = k_pz + k_mz
    den_p = k_m * k_m * k_pz + k_p * k_p * k_mz
    t_s = np.where(den_s == 0.0, 0.0, 2.0 * k_pz / np.where(den_s == 0.0, 1.0, den_s))
    t_p = np.where(
        den_p == 0.0,
        0.0,
        2.0 * k_pz * k_p * k_m / np.where(den_p == 0.0, 1.0, den_p),
    )
    return TransmittedFactors(t_s, t_p * k_mz / k_m, -t_p * (k_p / k_m) * sin_t, k_mz)


def transmitted_m_perp(mid, dr, i_mid, k_p, k_m, rhat, ground_z):
    """The far-field moment M_θ·θ̂ + M_φ·φ̂ of elements BELOW the plane.

    ``mid`` / ``dr`` / ``i_mid`` are the buried elements only (the caller
    splits on `below_surface_mask`); ``rhat`` is (..., 3) unit directions of
    any leading shape, so one implementation serves both a θ×φ grid and an
    unstructured cut. Returns (..., 3) complex, already transverse to r̂ by
    construction — it is built ON θ̂ and φ̂ — so the caller adds it to its
    own M_perp without projecting.

    The sum over elements is taken BEFORE the angular factors are applied:
    they depend only on the direction, so P = Σ_n phase_n·m_n is the one
    per-direction array of element size, which keeps this the same memory
    shape as the direct term beside it.
    """
    mid = np.asarray(mid, dtype=float)
    m = np.asarray(i_mid)[:, None] * np.asarray(dr, dtype=float)
    rhat = np.asarray(rhat, dtype=float)
    rx, ry, rz = rhat[..., 0], rhat[..., 1], rhat[..., 2]

    sin_t = np.sqrt(rx * rx + ry * ry)
    t_e, t_h, t_v, k_mz = _factors(rz, sin_t, k_p, k_m)

    # cosφ / sinφ for the θ̂, φ̂ basis. At the zenith the plane of incidence
    # is undefined, and there T_v = 0 and T_h = T_e, which makes
    # M_θ θ̂ + M_φ φ̂ = T_e·(m_x, m_y, 0) for ANY azimuth — so substituting
    # φ = 0 there is exact, not a guard on a division.
    at_pole = sin_t <= _POLE_SIN
    s_safe = np.where(at_pole, 1.0, sin_t)
    cos_p = np.where(at_pole, 1.0, rx / s_safe)
    sin_p = np.where(at_pole, 0.0, ry / s_safe)

    depth = float(ground_z) - mid[:, 2]  # > 0 by the caller's split
    horizontal = k_p * (rx[..., None] * mid[:, 0] + ry[..., None] * mid[:, 1])
    air_leg = (k_p * float(ground_z)) * rz
    phase = np.exp(1j * (horizontal + air_leg[..., None])) * np.exp(
        -1j * k_mz[..., None] * depth
    )
    P = np.einsum("...n,nc->...c", phase, m)

    m_th = t_h * (P[..., 0] * cos_p + P[..., 1] * sin_p) + t_v * P[..., 2]
    m_ph = t_e * (-P[..., 0] * sin_p + P[..., 1] * cos_p)
    th_hat = np.stack([rz * cos_p, rz * sin_p, -sin_t], axis=-1)
    ph_hat = np.stack([-sin_p, cos_p, np.zeros_like(sin_p)], axis=-1)
    return m_th[..., None] * th_hat + m_ph[..., None] * ph_hat

"""FastAPI server for the interactive antenna UI.

All geometries live in web.examples — each registered antenna bundles its
momwire solve/sweep and pynec build/solve into one file. Dispatchers here
look the geometry up in EXAMPLES and call its callables; adding or
removing an antenna doesn't touch this file.

The response shape is uniform across geometries — each wire is a sequence of
knots with per-knot complex currents and the feed lives on one of the wires —
so the frontend draws every geometry the same way.

Run: OMP_WAIT_POLICY=PASSIVE GOMP_SPINCOUNT=0 uvicorn antennaknobs.web.server:app --reload
(needs uvicorn[standard] — /ws is a WebSocket upgrade. The env prefix parks
idle OMP workers between solves — see the thread-policy block below; the
server works without it at ~15% higher interactive-solve latency.)
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
import time
from collections import OrderedDict
from copy import deepcopy
from pathlib import Path

import momwire
import numpy as np
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.websockets import WebSocketState
from threadpoolctl import threadpool_limits

from . import cost as _cost
from . import pynec_backend, user_designs
from .examples import REGISTRY as EXAMPLES
from .lane import LaneRegistry, Superseded, cancel_on_disconnect


def _physical_cpu_count() -> int:
    """Number of physical cores (not logical / HT siblings).

    Our quadrature kernels are FP-vector-saturated (libmvec AVX2 sin/cos
    inner loops, no spare FU bandwidth), so two HT siblings on one physical
    core contend for execution units rather than overlap. Ad-hoc bench on
    KBL-R 4C/8T showed 4-thread runs ~15% faster than 8-thread runs of the
    swept-ground hot path. Pin to physical-core count to skip that loss.

    Uses psutil for a portable answer (Windows/macOS/Linux). The previous
    /proc/cpuinfo + "assume 2 HT siblings" fallback misfired on chips
    without HT (e.g. Intel N-series E-core SoCs), pinning to half the
    actual core count.
    """
    try:
        import psutil

        n = psutil.cpu_count(logical=False)
        if n:
            return n
    except ImportError:
        pass
    return max(1, os.cpu_count() or 1)


# BLAS/OpenMP thread policy — applied at RUNTIME via threadpoolctl, not env.
#
# This block used to set OPENBLAS_NUM_THREADS / OMP_NUM_THREADS etc. before
# the heavy imports, but that never worked in a served process: importing
# `antennaknobs.web.server` executes `antennaknobs/__init__` first, which
# already pulls in numpy/scipy/PyNEC/libgomp — every pool snapshots the env
# before this module's body runs (issue #377 post-mortem; small solves were
# 5–7× slower than the config intended). threadpoolctl talks to the already-
# loaded pools directly, so it is immune to import order.
#
# The whole stack is OpenBLAS: numpy, scipy, and PyNEC each bundle their own
# copy (numpy.libs / scipy.libs / pynec_accel.libs — inspect with
# threadpoolctl.threadpool_info()); nothing links MKL. A solve has two
# core-hungry phases that run sequentially, so both get the physical-core
# count without oversubscribing:
#   - matrix fill: the per-source OMP parallel-for inside cmset() (libgomp,
#     see PR #21), and
#   - LU factorization: scipy zgesv (momwire) / LAPACKE zgetrf (pynec_accel),
#     both OpenBLAS-backed — the dominant O(N³) phase of large solves.
#
# Physical cores, not 1 and not the logical count:
#   - An older OPENBLAS_NUM_THREADS=1 pin predates PyNEC bundling OpenBLAS
#     (its factorization stayed parallel via MKL back then); with the current
#     stack it would serialize the LU phase of every big solve — the pin vs
#     NPROC is 2.3× on pynec (12.8 → 5.5 s) and 1.6× on bspline (7.3 →
#     4.6 s) at ~4000 basis on a 4C/8T box (issue #377).
#   - The FP-vector-saturated quadrature inner loops gain nothing from HT
#     siblings and lose ~15% to execution-unit contention on KBL-class
#     chips — see _physical_cpu_count().
#
# Operators can still override per-pool via the usual env vars (honored by
# the libraries at load AND respected here). Two knobs remain env-only —
# libgomp reads them once at load, before any Python code can run, so they
# must be set in the launch environment (the Dockerfile CMD does; for local
# runs see the docstring): OMP_WAIT_POLICY=PASSIVE + GOMP_SPINCOUNT=0 park
# idle OMP workers instead of busy-spinning through each solve's Python
# phases (~13–20% off small-solve latency, hentenna N=21).
_NPROC = _physical_cpu_count()
threadpool_limits(
    limits={
        "blas": int(os.environ.get("OPENBLAS_NUM_THREADS", _NPROC)),
        "openmp": int(os.environ.get("OMP_NUM_THREADS", _NPROC)),
    }
)

# Scaffold the user-design folder (TEMPLATE.py + CLAUDE.md on first run) and
# load any existing user designs into the registry at startup. They are also
# refreshed on every GET /examples so edits appear without a restart.
user_designs.ensure_scaffold()
user_designs.refresh()


# Target per-chunk wall time for the adaptive momwire /sweep chunking. The
# chunk size is tuned each iteration so a batch takes roughly this long —
# enough to amortise per-call overhead and benefit from numpy batching,
# small enough that an aborted fetch only wastes ~this much CPU before the
# next disconnect check kicks in.
_CHUNK_TARGET_MS = 500


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    try:
        v = int(os.environ.get(name, ""))
    except ValueError:
        return default
    return v if v > 0 else default


# The master switch for every hosted-only limit in this file (the solve-size
# caps and request clamps below): enforced only on the shared/hosted instance,
# which sets ANTENNAKNOBS_HOSTED via fly.toml. Local installs are unlocked.
_HOSTED = _env_flag("ANTENNAKNOBS_HOSTED")

app = FastAPI(
    title="momwire interactive",
    # The hosted instance is public with no auth: don't serve the interactive
    # API docs / OpenAPI schema there — they enumerate the exact endpoint and
    # parameter surface an attacker would probe (issue #348). Local installs
    # keep /docs for development.
    docs_url=None if _HOSTED else "/docs",
    redoc_url=None if _HOSTED else "/redoc",
    openapi_url=None if _HOSTED else "/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


C_LIGHT = 299_792_458.0  # m/s, matches the momwire solvers' eps*mu derivation to ~1e-9
_EPS0 = 8.854187817e-12  # F/m


def _attach_derived_em_fields(out: dict) -> None:
    """Augment the solve response with frequency-derived EM scalars the
    frontend would otherwise compute from raw physics constants.

    Sets:
      - `k_meas_m_inv`: wavenumber 2π f / c at measurement freq (rad/m)
      - `ground_eps_im`: imaginary part of the complex relative permittivity
        of the ground, -σ / (ω ε₀); 0 when ground is off or σ=0.

    The frontend reads these directly so it doesn't need to carry C_LIGHT
    or ε₀ literals. `lambda_design_m` is already shipped by each example.
    """
    f_hz = float(out["measurement_freq_mhz"]) * 1e6
    omega = 2.0 * np.pi * f_hz
    out["k_meas_m_inv"] = omega / C_LIGHT
    sigma = float(out.get("ground_sigma", 0.0) or 0.0)
    out["ground_eps_im"] = -sigma / (omega * _EPS0) if omega > 0 else 0.0


_ETA0 = 376.730313668  # free-space impedance, ohms


def _attach_gain_norm(out: dict) -> None:
    """Attach `directivity_norm` = η₀k²/(8π·P_in), the O(1) gain normaliser.

    Multiplying this by the frontend's azimuth-cut |M_perp(π/2, φ)|² yields
    absolute GAIN (linear); 10·log10 is dBi. Derivation: the far field of the
    moment sum M = Σ I·dr·e^{jk·r̂·x} is E = (jkη₀/4πr)·e^{−jkr}·M_perp, so the
    radiation intensity is U = r²|E|²/(2η₀) = (η₀k²/32π²)·|M_perp|² and
    gain = 4π·U/P_in = (η₀k²/8π)·|M_perp|²/P_in.

    Normalising by SOURCE input power is what makes this gain rather than
    directivity: power burned in resistive loads (terminated rhombic / T2FD)
    or absorbed by a lossy ground stays inside P_in, so no efficiency multiply
    — this replaces the old pattern-integral norm (4π/∮|M_perp|²dΩ)×efficiency,
    which equals it identically up to the solver's self-consistency gap (the
    NEC "average gain" diagnostic; `_pattern_integral_norm` measures it).

    Falls back to the pattern-integral norm when the response carries no
    usable input power (defensive: a pathological R_in ≤ 0 from a nearly
    lossless, strongly reactive discretisation).
    """
    p_in = float(out.get("input_power_w", 0.0) or 0.0)
    if p_in <= 0.0:
        _compute_directivity_norm(out)
        return
    k = float(out["k_meas_m_inv"])
    out["directivity_norm"] = _ETA0 * k * k / (8.0 * np.pi * p_in)


def _adaptive_norm_grid(k: float, lo: np.ndarray, hi: np.ndarray) -> tuple[int, int]:
    """Grid resolution (n_theta, n_phi) for the directivity-norm integral,
    sized to the structure's electrical extent.

    The far-field pattern is band-limited by the source's largest dimension: a
    structure spanning D radiates angular detail up to spherical-harmonic degree
    ~k·D, and the integrand |M_perp|² has twice that bandwidth. We size n_theta
    off the bounding-box diagonal in wavelengths, D_λ, as a constant (the base
    pattern's irreducible complexity) plus a slope in D_λ, then clamp.
    n_phi = 2·n_theta mirrors the 2× azimuthal bandwidth.

    The constant + slope are fit empirically (scripts/
    profile_ws_postproc_serialization.py) to sit safely *above* the aliasing
    floor: sampling just below the floor doesn't merely lose precision, it
    corrupts the scalar by ~1 dB (a 13.8λ loop reads −0.9 dB at n_theta=14 then
    snaps to −0.007 dB at n_theta=20). The bbox diagonal upper-bounds the true
    source diameter, so this errs conservative (a finer grid than strictly
    needed) — safe, and still ~10× cheaper than the old fixed 45×90 on the
    common electrically-small design.
    """
    lam = (2.0 * np.pi / k) if k > 0 else float("inf")
    d_lambda = float(np.linalg.norm(hi - lo)) / lam if np.isfinite(lam) else 0.0
    n_theta = int(np.clip(np.ceil(13.0 + 1.2 * d_lambda), 12, 90))
    return n_theta, 2 * n_theta


def _fine_norm_grid(n_theta_adaptive: int) -> tuple[int, int]:
    """A reference grid comfortably finer than the adaptive pick, for the
    opt-in far-field grid-check overlay. At least 45×90 (the pre-adaptive
    "gold" grid, measured converged to ~0.000 dB on the calibration designs)
    and at least 2× the adaptive n_theta, capped to bound the one-shot cost on
    electrically-huge designs. If the adaptive pick were badly low, doubling it
    crosses the aliasing floor, so the overlay still exposes the shortfall."""
    n_theta = int(np.clip(max(45, 2 * n_theta_adaptive), 45, 120))
    return n_theta, 2 * n_theta


def _moment_segments(out: dict) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Segment midpoints (Nseg,3), segment vectors dr (Nseg,3) and midpoint
    currents (Nseg,) complex — the discrete moment set behind the far-field
    sum M(r̂) = Σ I·dr·e^{jk·r̂·mid}, shared by every pattern normaliser.

    Prefers the finer-grained sample arrays (knot + segment-midpoint) when
    the model produced them, so non-tent bases get their intra-segment
    curvature integrated. Falls back to knot arrays for any backend that
    only ships knot data (PyNEC).
    """
    mids, drs, i_mids = [], [], []
    for w in out["wires"]:
        if "sample_positions" in w:
            pts = np.asarray(w["sample_positions"], dtype=np.float64)
            cur = np.asarray(
                w["sample_currents_re"], dtype=np.float64
            ) + 1j * np.asarray(w["sample_currents_im"], dtype=np.float64)
        else:
            pts = np.asarray(w["knot_positions"], dtype=np.float64)
            cur = np.asarray(w["knot_currents_re"], dtype=np.float64) + 1j * np.asarray(
                w["knot_currents_im"], dtype=np.float64
            )
        drs.append(pts[1:] - pts[:-1])
        mids.append(0.5 * (pts[1:] + pts[:-1]))
        i_mids.append(0.5 * (cur[1:] + cur[:-1]))
    return (
        np.concatenate(mids, axis=0),
        np.concatenate(drs, axis=0),
        np.concatenate(i_mids, axis=0),
    )


def _pattern_integral_norm(out: dict) -> float:
    """The pattern-integral gain norm (4π/∮|M_perp|²dΩ)·efficiency evaluated
    in CLOSED FORM — no angular grid. Because the radiated power is quadratic
    in the currents, the sphere integral collapses to a pair sum over the
    moment set with the classical mutual-radiation-resistance kernel:

        ∮ (I₃ − r̂r̂)·e^{jk·r̂·d} dΩ = 4π[ a(x)·I₃ − b(x)·d̂d̂ ],  x = k|d|
        a(x) = j₀(x) − j₁(x)/x        (→ 2/3 as x → 0)
        b(x) = j₀(x) − 3·j₁(x)/x      (→ 0   as x → 0)

    with spherical Bessels j₀, j₁ — real, smooth, exact. O(N²) pairs, no
    aliasing floor, no grid to size.

    Ground: evaluates the PEC-IMAGE functional regardless of the response's
    ground constants — image segments (x,y,z) → (x,y,−z) with horizontal
    moment components flipped reproduce the reflected wave exactly, and the
    imaged 2N system is mirror-symmetric, so the upper-hemisphere power is
    half its full-sphere power. Valid as a norm only when the response is
    PEC (eps_r at the 1e10 sentinel, where Fresnel differs from the PEC
    limit only within ~1e-5 of grazing); finite-ground responses (real
    εr/σ shipped since the web ground-parity change) must use the grid
    quadrature instead — `_norm_check` already routes them there.

    This is the same discrete functional the old grid integral sampled, so
    the delta against the P_in-based `directivity_norm` isolates the solver
    self-consistency gap (NEC's "average gain" diagnostic), not quadrature.
    """
    k = float(out["k_meas_m_inv"])
    mid, dr, i_mid = _moment_segments(out)
    w = i_mid[:, None] * dr  # complex moment per segment (Nseg, 3)
    x_pts = mid
    half = 1.0
    if bool(out.get("ground", False)):
        x_pts = np.concatenate([mid, mid * np.array([1.0, 1.0, -1.0])], axis=0)
        w = np.concatenate([w, w * np.array([-1.0, -1.0, 1.0])], axis=0)
        half = 0.5

    # Pair sum in row blocks so peak memory stays O(block·N) instead of
    # O(N²·3) — the terminated rhombic over ground is a ~2600-point set.
    n_pts = x_pts.shape[0]
    w_conj = np.conj(w)
    block = max(1, int(2e6) // max(n_pts, 1))
    p_sum = 0.0
    for s in range(0, n_pts, block):
        e = min(s + block, n_pts)
        d = x_pts[s:e, None, :] - x_pts[None, :, :]  # (B, N, 3)
        x = k * np.linalg.norm(d, axis=-1)  # (B, N)
        small = x < 1e-3
        xs = np.where(small, 1.0, x)  # avoid 0-division; small arm uses series
        sin_x, cos_x = np.sin(xs), np.cos(xs)
        j0 = sin_x / xs
        j1_over_x = (sin_x / xs - cos_x) / (xs * xs)
        x2 = x * x
        # 2-term series at small x (the exact forms lose precision to
        # cancellation): a = 2/3 − 2x²/15, b = −x²/15.
        a = np.where(small, 2.0 / 3.0 - 2.0 * x2 / 15.0, j0 - j1_over_x)
        b = np.where(small, -x2 / 15.0, j0 - 3.0 * j1_over_x)

        # w_m*ᵀ [a·I − b·d̂d̂] w_n over the block's pairs. d̂ is undefined
        # at d=0 but b→0 there, so guard the denominator instead of
        # special-casing the diagonal.
        dot_ww = w_conj[s:e] @ w.T  # (B, N)
        d_norm = np.where(small, 1.0, x / k)  # |d| with the same guard
        proj_m = np.einsum("bnc,bc->bn", d, w_conj[s:e]) / d_norm
        proj_n = np.einsum("bnc,nc->bn", d, w) / d_norm
        p_sum += float(np.sum(a * dot_ww.real - b * (proj_m * proj_n).real))
    p_rad = 4.0 * np.pi * half * p_sum
    if p_rad <= 0.0:
        return 0.0
    efficiency = float(out.get("radiation_efficiency", 1.0))
    return 4.0 * np.pi / p_rad * efficiency


def _compute_directivity_norm(
    out: dict,
    n_theta: int | None = None,
    n_phi: int | None = None,
    *,
    _theta_rule: str = "gl",
) -> None:
    """Attach `directivity_norm` = 4π / ∫|M_perp|² dΩ to the response.

    Multiplying this by the frontend's azimuth-cut |M_perp(π/2, φ)|² yields
    absolute directivity D(φ) (linear); 10·log10(D) is dBi.

    With ground enabled, integrates only the upper hemisphere and adds the
    Fresnel-reflected contribution from the geometric image so the
    normalization matches what the JS far-field code displays.

    The θ direction uses Gauss–Legendre quadrature in u = cos θ (the sin θ
    Jacobian is absorbed into the weights); φ stays a uniform rectangle rule
    (periodic → spectrally accurate). By default the grid is sized to the
    structure's electrical extent via `_adaptive_norm_grid`; callers may pass an
    explicit `n_theta`/`n_phi` (e.g. the convergence harness).
    """
    k = float(out["k_meas_m_inv"])
    ground_on = bool(out.get("ground", False))
    mid, dr, i_mid = _moment_segments(out)

    if n_theta is None or n_phi is None:
        # Size the grid to the structure's electrical extent. Segment midpoints
        # under-cover the true endpoints by at most half a (sub-λ) segment —
        # negligible for the bounding-box diagonal used to pick the resolution.
        n_theta, n_phi = _adaptive_norm_grid(k, mid.min(axis=0), mid.max(axis=0))

    # θ integration in u = cos θ, with the sin θ Jacobian (du = −sin θ dθ)
    # folded into `w_theta` so the radiated-power sum below needs no extra sin θ
    # factor. Default is Gauss–Legendre (far more accurate per θ-point above the
    # resolution floor); `_theta_rule="uniform"` selects the legacy midpoint-
    # rectangle rule and exists only so the profiling harness can quantify the
    # GL win. With ground, integrate only the upper hemisphere (θ ∈ [0, π/2]).
    half = 0.5 if ground_on else 1.0
    if _theta_rule == "gl":
        gl_x, gl_w = np.polynomial.legendre.leggauss(n_theta)
        # Map the [−1, 1] rule onto u ∈ [0, 1] for a hemisphere, else keep [−1, 1].
        u = 0.5 * (gl_x + 1.0) if ground_on else gl_x
        w_theta = half * gl_w
    elif _theta_rule == "uniform":
        theta = (np.arange(n_theta) + 0.5) * (half * np.pi / n_theta)
        u = np.cos(theta)
        w_theta = np.sin(theta) * (half * np.pi / n_theta)
    else:
        raise ValueError(f"unknown _theta_rule {_theta_rule!r}")
    cos_t = u
    sin_t = np.sqrt(np.clip(1.0 - u * u, 0.0, None))
    phi = np.arange(n_phi) * (2 * np.pi / n_phi)
    cos_p, sin_p = np.cos(phi), np.sin(phi)

    rx = sin_t[:, None] * cos_p[None, :]
    ry = sin_t[:, None] * sin_p[None, :]
    rz = np.broadcast_to(cos_t[:, None], (n_theta, n_phi))
    rhat = np.stack([rx, ry, rz], axis=-1)  # (nθ, nφ, 3)

    phase = k * np.einsum("ijc,nc->ijn", rhat, mid)  # (nθ, nφ, Nseg)
    expp = np.exp(1j * phase)
    weighted = i_mid[:, None] * dr  # (Nseg, 3)
    M = np.einsum("ijn,nc->ijc", expp, weighted)  # (nθ, nφ, 3)
    m_dot_r = np.sum(M * rhat, axis=-1)
    M_perp = M - m_dot_r[..., None] * rhat

    if ground_on:
        # PEC-image method, then Fresnel-correct the reflected wave per-ray.
        # Image current: horizontal components flipped, vertical preserved.
        # This reproduces PEC reflection when ρ_h=-1, ρ_v=+1, and lets us
        # apply the actual finite-ground coefficients to that same image.
        mid_img = mid * np.array([1.0, 1.0, -1.0])
        dr_img = dr * np.array([-1.0, -1.0, 1.0])
        weighted_img = i_mid[:, None] * dr_img
        phase_img = k * np.einsum("ijc,nc->ijn", rhat, mid_img)
        expp_img = np.exp(1j * phase_img)
        M_img = np.einsum("ijn,nc->ijc", expp_img, weighted_img)
        m_img_dot_r = np.sum(M_img * rhat, axis=-1)
        M_img_perp = M_img - m_img_dot_r[..., None] * rhat

        # Polarization basis at each ray: ĥ = ẑ × r̂ (perp to plane of
        # incidence), v̂ = r̂ × ĥ (in plane of incidence, perp to r̂).
        s = np.sqrt(rx * rx + ry * ry)
        s_safe = np.where(s > 1e-12, s, 1.0)
        h_hat = np.stack([-ry / s_safe, rx / s_safe, np.zeros_like(rx)], axis=-1)
        v_hat = np.stack([-rx * rz / s_safe, -ry * rz / s_safe, s], axis=-1)

        M_img_h = np.sum(M_img_perp * h_hat, axis=-1)  # complex (nθ, nφ)
        M_img_v = np.sum(M_img_perp * v_hat, axis=-1)

        eps_c = out["ground_eps_r"] + 1j * out["ground_eps_im"]
        cos_ti = rz
        sin2_ti = s * s
        Q = np.sqrt(eps_c - sin2_ti)
        rho_h = (cos_ti - Q) / (cos_ti + Q)
        rho_v = (eps_c * cos_ti - Q) / (eps_c * cos_ti + Q)

        # Reflected: ρ_v on the v-pol component, −ρ_h on the h-pol component
        # (the minus sign folds the PEC image's pre-applied horizontal flip
        # back out so ρ_h=−1 recovers the PEC limit exactly).
        M_refl = (rho_v * M_img_v)[..., None] * v_hat - (rho_h * M_img_h)[
            ..., None
        ] * h_hat
        M_perp = M_perp + M_refl

    mag2 = np.sum((M_perp.real**2 + M_perp.imag**2), axis=-1)  # (nθ, nφ)

    # Gauss–Legendre in θ (weight absorbs sin θ) × uniform rectangle in φ.
    dphi = 2 * np.pi / n_phi
    p_rad = float(np.sum(mag2 * w_theta[:, None]) * dphi)
    # Fold in the radiation efficiency (P_radiated / P_input) so a terminated /
    # loaded antenna plots GAIN, not directivity: 4π/p_rad is the directivity
    # normaliser, and multiplying by efficiency drops the peak by the fraction
    # of power burned in resistive loads. Defaults to 1.0 (lossless / no loads,
    # and the PyNEC path which doesn't report it), leaving every other design
    # unchanged.
    efficiency = float(out.get("radiation_efficiency", 1.0))
    out["directivity_norm"] = (4 * np.pi / p_rad * efficiency) if p_rad > 0 else 0.0
    # Record the grid that produced this norm — the far-field grid-check overlay
    # reads it to derive a finer reference grid and to label the comparison.
    out["directivity_norm_grid"] = [int(n_theta), int(n_phi)]


def _wire_record(
    knots: np.ndarray,
    currents: np.ndarray,
    label: str,
    sample_currents: np.ndarray | None = None,
) -> dict:
    """Package one wire's record for the JSON response. `currents` is a
    length-M_w complex array (one per mesh knot) as produced by each
    model's `currents_at_knots(coeffs)` method.

    When `sample_currents` is provided, additional `sample_positions` /
    `sample_currents_re` / `sample_currents_im` arrays are attached at
    knots-and-midpoints interleaved (2*N_seg + 1 entries per wire). This is
    what `_compute_directivity_norm` and the frontend renderers consume to
    resolve intra-segment basis curvature (B-spline d=2, sinusoidal three-
    term) and the B-spline enrichment shape that vanishes at every knot.
    """
    currents = np.asarray(currents, dtype=np.complex128)
    if currents.shape[0] != knots.shape[0]:
        raise ValueError(
            f"_wire_record: currents/knots length mismatch "
            f"({currents.shape[0]} vs {knots.shape[0]})"
        )
    out = {
        "label": label,
        "knot_positions": knots.tolist(),
        "knot_currents_re": currents.real.tolist(),
        "knot_currents_im": currents.imag.tolist(),
    }
    if sample_currents is not None:
        sample_currents = np.asarray(sample_currents, dtype=np.complex128)
        n_seg = knots.shape[0] - 1
        expected = 2 * n_seg + 1
        if sample_currents.shape[0] != expected:
            raise ValueError(
                f"_wire_record: sample_currents length {sample_currents.shape[0]} "
                f"!= expected 2*N_seg+1 = {expected}"
            )
        sample_positions = np.empty((expected, 3), dtype=np.float64)
        sample_positions[0::2] = knots
        sample_positions[1::2] = 0.5 * (knots[:-1] + knots[1:])
        out["sample_positions"] = sample_positions.tolist()
        out["sample_currents_re"] = sample_currents.real.tolist()
        out["sample_currents_im"] = sample_currents.imag.tolist()
    return out


def _sample_arc_for_wire(knots: np.ndarray) -> np.ndarray:
    """Build interleaved (knot_arc, midpoint_arc, knot_arc, ...) array from a
    wire's 3D knot positions. Segment lengths come from successive-knot
    distances along the polyline.
    """
    knots = np.asarray(knots, dtype=np.float64)
    h_seg = np.linalg.norm(knots[1:] - knots[:-1], axis=1)
    arc_at_knot = np.concatenate([[0.0], np.cumsum(h_seg)])
    mid_arc = 0.5 * (arc_at_knot[:-1] + arc_at_knot[1:])
    sample_arc = np.empty(2 * h_seg.shape[0] + 1, dtype=np.float64)
    sample_arc[0::2] = arc_at_knot
    sample_arc[1::2] = mid_arc
    return sample_arc


def _pack_momwire_wires(sim, coeffs, knot_arrays, labels) -> list[dict]:
    """Build wire records for every momwire wire with both knot-level currents
    AND finer-grained mid-segment samples (one extra sample per segment).

    Calls `sim.currents_at_knots(coeffs)` once for the knot values and once
    more with an `s_array` of per-wire interleaved knot-and-midpoint arcs.
    The model's basis is then evaluated exactly at the midpoints — including
    the B-spline enrichment basis Φ_sing, which is zero at the knots but
    non-zero in the interior.
    """
    sample_arcs = [_sample_arc_for_wire(k) for k in knot_arrays]
    knot_currents = sim.currents_at_knots(coeffs)
    sample_currents = sim.currents_at_knots(coeffs, s_array=sample_arcs)
    return [
        _wire_record(
            np.asarray(knot_arrays[i]),
            knot_currents[i],
            labels[i],
            sample_currents=sample_currents[i],
        )
        for i in range(len(knot_arrays))
    ]


# Momwire PEC ground: pass these to the response so the frontend's Fresnel
# far-field code treats the surface as a perfect electric conductor
# (ρ_h → −1, ρ_v → +1 in the eps_r → ∞ limit).
_PEC_GROUND_EPS_R = 1.0e10
_PEC_GROUND_SIGMA = 0.0


def _polyline_knots(polyline: np.ndarray, npe_list: list[int]) -> np.ndarray:
    """Concatenated per-edge knot positions, with shared corners deduped."""
    parts = []
    for i, n_e in enumerate(npe_list):
        seg = np.linspace(polyline[i], polyline[i + 1], n_e + 1)
        parts.append(seg if i == 0 else seg[1:])
    return np.vstack(parts)


_SOLVE_CACHE: "OrderedDict[str, dict]" = OrderedDict()
_SOLVE_CACHE_MAX = 100


# --- Live-engine size guard (hosted only) ----------------------------------
# A solve builds a method-of-moments system whose dimension N ≈ the total wire
# segment count (one basis function per segment). The dense solvers — and PyNEC
# — form an N×N complex128 matrix (memory N²·16 bytes), so an unbounded N (a
# hand-edited request cranking "segments / wire", or a big array) can exhaust a
# small box's RAM.
#
# This guard is OFF by default, so the package a user `pip install`s and runs
# locally is unlocked — solve as big as your machine allows. It turns ON only
# when ANTENNAKNOBS_HOSTED is set (truthy), which the shared instance does via
# fly.toml's [env]. So the same wheel is unlocked locally and capped online.
#
# The caps are sized to keep a single solve's matrix under ~800 MB on the 2 GB
# Fly box (basis = √(800·2²⁰/16) ≈ 7000 for a dense N×N). Measured on
# arrays.bowtiearray2x4 (see scripts/measure_solve_memory.py): PyNEC's RSS
# tracks the full dense N×N (~1 GB at basis 8000), while arrayblock's block-
# low-rank uses ~0.6× of that — so it's allowed a proportionally higher cap.
# Caps are about MEMORY, not solve time (PyNEC's ~N³ LU is slow long before it
# is large; that's a responsiveness concern, deliberately not guarded here).
# All env-overridable for self-hosting on bigger boxes. (_HOSTED and the
# _env_* helpers live above the FastAPI construction, which also needs them.)
# Caps live in the shared cost model (web/cost.py, issue #382) so admission
# is one mapping for every job kind; re-exported here because tests and ops
# docs address them as server._MAX_*.
_MAX_BASIS = _cost.MAX_BASIS
_MAX_BASIS_COMPRESSED = _cost.MAX_BASIS_COMPRESSED
_MAX_BASIS_PYNEC = _cost.MAX_BASIS_PYNEC
_COMPRESSED_MODELS = _cost.COMPRESSED_MODELS
_MAX_SWEEP_POINTS = _cost.MAX_SWEEP_POINTS
_MAX_OPT_EVALS = _cost.MAX_OPT_EVALS


class SolveTooLargeError(ValueError):
    """A solve request exceeds the hosted live-engine segment-count cap."""


def _admit(req: dict, *, kind: str, use_pynec: bool, points: int = 1):
    """The shared cost-model verdict for this request (issue #382)."""
    geometry = req.get("geometry", next(iter(EXAMPLES)))
    return _cost.admit(
        req,
        kind=kind,
        use_pynec=use_pynec,
        hosted=_HOSTED,
        example=EXAMPLES.get(geometry),
        points=points,
    )


def _check_solve_size(req: dict, *, use_pynec: bool) -> None:
    """Reject a solve whose matrix would be too large for the hosted live engine.

    No-op unless running hosted (ANTENNAKNOBS_HOSTED) — local instances are
    unlocked. Thin wrapper over the shared cost model's "refuse" verdict;
    if the size can't be estimated (geometry won't build), the normal solve
    path surfaces the real error.
    """
    adm = _admit(req, kind="live", use_pynec=use_pynec)
    if adm.verdict == "refuse":
        raise SolveTooLargeError(adm.reason)


def _refuse_or_withhold(adm, req: dict) -> None:
    """Map a batch admission verdict to its HTTP error (no-op on "run").

    "refuse" → 413 (too large for the hosted box, as before). "warn" → 403
    unless the request carries ``_approved: true`` — the server-side backstop
    for the frontend's "Solve anyway" gate: a batch of poor-match solves on a
    benchmark mesh no longer relies on the client politely holding it back.
    """
    if adm.verdict == "refuse":
        raise HTTPException(status_code=413, detail=adm.reason)
    if adm.verdict == "warn" and not req.get("_approved"):
        raise HTTPException(status_code=403, detail=adm.reason)


# Request fields that are pure metadata and never change the physics. Pop
# them before hashing so noisy frontend additions (timestamps, request ids)
# don't shred the hit rate. Anything else in `req` is treated as load-
# bearing — preferring "extra miss" over "wrong hit".
_CACHE_KEY_BLOCKLIST = frozenset(
    {
        "_request_id",
        "_client_ts",
        # Per-request sequence number for the /ws latest-wins protocol. Pure
        # metadata — echoed back so the client can order/prune responses; must
        # not shred the cache hit rate (a scrub back to an earlier value should
        # still hit even though its _seq is higher).
        "_seq",
        # Solve-lane metadata (issue #382): session identity, batch-request
        # generation, and the "Solve anyway" approval flag. All scheduling,
        # zero physics — a norm-check must hit the live solve's cache entry.
        "_session",
        "_gen",
        "_approved",
    }
)

# Per-session solve lanes (issue #382): every solve-producing compute — the
# live /ws solve, each /sweep chunk, each /converge point, /norm_check,
# /pattern, /pattern_metrics — takes a turn on its session's lane, so no two
# ever run concurrently for one client. /optimize stays outside for now: its
# evals are cache-skipping and bounded by _MAX_OPT_EVALS, and one whole-run
# turn would starve live solves — taking a turn per eval is the follow-up.
_LANES = LaneRegistry()


def _lane_key(req: dict) -> tuple[str | None, int | None]:
    """(session, generation) for the solve lane, tolerating absent/junk values.

    The session id is minted client-side (one per workbench tab); the
    generation is the client's monotonic solve counter — `_seq` on live /ws
    requests, `_gen` on batch POSTs (same counter, so a knob drag's live
    solve supersedes the batches issued for the previous state).
    """
    session = req.get("_session")
    if not isinstance(session, str) or not session:
        session = None
    gen = req.get("_gen", req.get("_seq"))
    if isinstance(gen, bool) or not isinstance(gen, int):
        gen = None
    return session, gen


# Quantisation grid for floats in the cache key. Slider grids in the UI
# are coarser than 1e-6, so this still lets back-and-forth scrubs land on
# identical values; finer than user-perceivable change so two genuinely
# different requests don't collide.
_CACHE_FLOAT_QUANT = 1e-6


def _canonical_solve_key(req: dict) -> str:
    def quantise(x):
        if isinstance(x, float):
            return round(x / _CACHE_FLOAT_QUANT) * _CACHE_FLOAT_QUANT
        if isinstance(x, dict):
            return {
                k: quantise(v) for k, v in x.items() if k not in _CACHE_KEY_BLOCKLIST
            }
        if isinstance(x, (list, tuple)):
            return [quantise(v) for v in x]
        return x

    blob = json.dumps(quantise(req), sort_keys=True, default=str).encode()
    return hashlib.blake2b(blob, digest_size=16).hexdigest()


def _solve_uncached(req: dict, cancel=None) -> dict:
    geometry = req.get("geometry", next(iter(EXAMPLES)))
    use_pynec = req.get("solver") == "pynec" and pynec_backend.HAVE_PYNEC
    _check_solve_size(req, use_pynec=use_pynec)
    if use_pynec:
        # PyNEC start-gate only: a request already superseded before its solve
        # begins dies for free here; the native solve is one opaque call with no
        # mid-solve abort, so an in-flight one runs to completion (as today).
        if cancel is not None:
            cancel.raise_if_cancelled()
        out = pynec_backend.solve(req)
    else:
        ex = EXAMPLES.get(geometry) or next(iter(EXAMPLES.values()))
        out = ex.momwire_solve(req, cancel=cancel)
        out["solver"] = "momwire"
    _attach_derived_em_fields(out)
    _attach_gain_norm(out)
    return out


def solve(req: dict, cancel=None) -> dict:
    key = _canonical_solve_key(req)
    hit = _SOLVE_CACHE.get(key)
    # Cache hits are O(1) and never worth aborting — the token is only consulted
    # on the (expensive) miss path below. A SolveAborted from _solve_uncached
    # propagates before the cache-store line, so an aborted solve is never cached.
    if hit is not None:
        _SOLVE_CACHE.move_to_end(key)
        t0 = time.perf_counter()
        out = deepcopy(hit)
        # Overwrite the cached solve_ms with the actual cost of producing
        # this response (the lookup + deepcopy) — otherwise the frontend's
        # "solve time" indicator shows a stale value from whichever earlier
        # tick first populated this cache entry.
        out["solve_ms"] = (time.perf_counter() - t0) * 1e3
        out["cache_hit"] = True
        return out
    out = _solve_uncached(req, cancel=cancel)
    out["cache_hit"] = False
    _SOLVE_CACHE[key] = deepcopy(out)
    while len(_SOLVE_CACHE) > _SOLVE_CACHE_MAX:
        _SOLVE_CACHE.popitem(last=False)
    return out


@app.post("/sweep")
async def sweep_endpoint(req: dict, request: Request):
    """Stream sweep points as NDJSON, one (freq, Z) per line.

    Streaming so the UI can show partial results as they're computed, and
    so the server can stop mid-sweep when the client disconnects — without
    this the user's slider drags abort the fetch client-side but the server
    keeps grinding through all 41 expensive PyNEC ground solves, starving
    the live /ws solves of CPU.
    """
    try:
        freqs = [float(f) for f in req.get("freqs_mhz", [])]
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=422, detail="freqs_mhz must be a list of numbers"
        ) from None
    if any(not math.isfinite(f) or f <= 0.0 for f in freqs):
        raise HTTPException(
            status_code=422,
            detail="freqs_mhz entries must be positive, finite numbers",
        )
    geometry = req.get("geometry", next(iter(EXAMPLES)))
    sweep_ex = EXAMPLES.get(geometry) or next(iter(EXAMPLES.values()))
    use_pynec = req.get("solver") == "pynec" and pynec_backend.HAVE_PYNEC
    solver_name = "pynec" if use_pynec else "momwire"
    # Admission by cost (issue #382), before the stream starts: over-cap
    # matrix or point count → clean 413 (as before); a dense-family batch on
    # a benchmark-class mesh → 403 unless the request carries the client
    # gate's "Solve anyway" approval.
    _refuse_or_withhold(
        _admit(req, kind="sweep", use_pynec=use_pynec, points=len(freqs)), req
    )
    session, lane_gen = _lane_key(req)
    # Validate the client's solver kwargs up front: this endpoint streams, so
    # an error surfacing mid-generator can't become a clean status code.
    # Imported here (like /optimize's optimizer import): adapter ↔ examples
    # resolve their import cycle examples-first, so a module-level import
    # of adapter from server would re-trip it.
    from .adapter import sanitize_model_options

    try:
        sanitize_model_options(req)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    async def gen():
        if not freqs:
            yield json.dumps({"done": True, "solver": solver_name}) + "\n"
            return

        if use_pynec:
            # Per-point loop with disconnect check; lets us bail before the
            # next ~100 ms PyNEC ground solve when the user moves a slider.
            # Multi-feed geometries take the multifeed sweep so per-feed Z
            # streams alongside the primary z_re / z_im.
            is_multifeed = sweep_ex.multi_feed
            for f in freqs:
                if await request.is_disconnected():
                    return
                try:
                    # One lane turn per point: a queued live solve gets the
                    # lane at the next point boundary. PyNEC has no mid-solve
                    # abort, so a supersession trips the token but the point
                    # runs out; the post-turn check stops the stream there.
                    async with _LANES.turn(session, "sweep", lane_gen) as token:
                        if is_multifeed:
                            primary, feeds_z = await run_in_threadpool(
                                pynec_backend._sweep_at_multifeed, req, f
                            )
                            record = {
                                "freq_mhz": f,
                                "z_re": float(primary.real),
                                "z_im": float(primary.imag),
                                "feeds_z_re": [float(z_.real) for z_ in feeds_z],
                                "feeds_z_im": [float(z_.imag) for z_ in feeds_z],
                                "solver": solver_name,
                            }
                        else:
                            z = await run_in_threadpool(pynec_backend._sweep_at, req, f)
                            record = {
                                "freq_mhz": f,
                                "z_re": float(z.real),
                                "z_im": float(z.imag),
                                "solver": solver_name,
                            }
                        superseded_mid_point = token.cancelled
                except Superseded:
                    return
                yield json.dumps(record) + "\n"
                if superseded_mid_point:
                    return
        else:
            # momwire's batched sweep is ~10x faster per-call than per-point,
            # but a 5-band fan dipole sweep at n_per_wire=21, 41 freqs takes
            # ~6 s and holds several hundred MB of J tensors — long enough
            # that rapid slider drags would otherwise pile up concurrent
            # computes in the threadpool, exhausting threads or memory and
            # surfacing as a 500 at the Vite proxy.
            #
            # Chunk the sweep so we can check is_disconnected between
            # batches. Per-freq cost has a bowl curve in chunk size:
            # tiny chunks pay per-call overhead, huge chunks thrash memory
            # bandwidth. For the 5-band fan-dipole geometry the sweet spot
            # is chunk_size ≈ 8 (115 ms/freq); for an inverted V it's much
            # larger (single-digit ms/freq, all freqs in one go is fine).
            #
            # Aim each chunk at roughly _CHUNK_TARGET_MS so the cancellation
            # granularity is consistent across geometries. Start with an
            # 8-chunk heuristic, then after each chunk recompute the next
            # size from observed per-freq cost. Converges in ~1 iteration.
            sweep_fn = sweep_ex.momwire_sweep
            chunk_size = max(1, len(freqs) // 8)
            start = 0
            while start < len(freqs):
                if await request.is_disconnected():
                    return
                chunk = freqs[start : start + chunk_size]
                t0 = time.perf_counter()
                try:
                    # One lane turn per chunk; the token reaches the solver's
                    # checkpoints, so a knob drag (newer generation) or a
                    # dropped connection (the watcher) aborts THIS chunk in
                    # ~ms instead of after minutes on a benchmark mesh.
                    async with _LANES.turn(session, "sweep", lane_gen) as token:
                        async with cancel_on_disconnect(request, token):
                            sweep_result = await run_in_threadpool(
                                sweep_fn, req, chunk, cancel=token
                            )
                except (Superseded, momwire.SolveAborted):
                    return
                # Multi-feed sweeps (bowtie array) return a 4-tuple with
                # per-feed Z appended. Everything else stays on the
                # original 2-tuple shape; the legacy z_re / z_im fields
                # always carry the primary feed for back-compat.
                feeds_re_chunk: list[list[float]] | None = None
                feeds_im_chunk: list[list[float]] | None = None
                if len(sweep_result) == 4:
                    z_re, z_im, feeds_re_chunk, feeds_im_chunk = sweep_result
                else:
                    z_re, z_im = sweep_result
                chunk_ms = (time.perf_counter() - t0) * 1000
                for i, f in enumerate(chunk):
                    record: dict = {
                        "freq_mhz": f,
                        "z_re": z_re[i],
                        "z_im": z_im[i],
                        "solver": solver_name,
                    }
                    if feeds_re_chunk is not None:
                        record["feeds_z_re"] = feeds_re_chunk[i]
                        record["feeds_z_im"] = feeds_im_chunk[i]
                    yield json.dumps(record) + "\n"
                start += len(chunk)
                # Adapt for the next chunk: target _CHUNK_TARGET_MS per
                # batch. Per-freq cost is a weak function of chunk size
                # (bowl curve), so this converges quickly.
                if chunk_ms > 0 and len(chunk) > 0:
                    per_freq_ms = chunk_ms / len(chunk)
                    chunk_size = max(1, round(_CHUNK_TARGET_MS / per_freq_ms))

        yield json.dumps({"done": True, "solver": solver_name}) + "\n"

    return StreamingResponse(gen(), media_type="application/x-ndjson")


def _solve_z_only(req: dict, cancel=None) -> tuple[complex, list[complex] | None]:
    """Run the geometry-specific solver and return only the input impedance.

    Returns (primary_z, feeds_z) where feeds_z is the per-feed Z list for
    multi-feed geometries (bowtie 1×2 array) and None for single-feed
    geometries. Skips solve()'s post-processing (derived EM fields, gain
    norm) — for the /converge sweep we only need Z(N).
    """
    geometry = req.get("geometry", next(iter(EXAMPLES)))
    use_pynec = req.get("solver") == "pynec" and pynec_backend.HAVE_PYNEC
    if use_pynec:
        # Start-gate only: PyNEC's native solve has no mid-solve abort.
        if cancel is not None:
            cancel.raise_if_cancelled()
        res = pynec_backend.solve(req)
    else:
        ex = EXAMPLES.get(geometry) or next(iter(EXAMPLES.values()))
        res = ex.momwire_solve(req, cancel=cancel)
    primary = complex(res["z_in_re"], res["z_in_im"])
    feeds_list = res.get("feeds")
    feeds_z: list[complex] | None = (
        [complex(f["z_re"], f["z_im"]) for f in feeds_list]
        if feeds_list and len(feeds_list) > 1
        else None
    )
    return primary, feeds_z


@app.post("/converge")
async def converge_endpoint(req: dict, request: Request):
    """Stream impedance vs segments/wire as NDJSON, one (n, Z) per line.

    The frontend passes `n_values: list[int]`; we re-solve the geometry at
    each N (overriding `n_per_wire`) and yield the result before starting
    the next solve. Streaming so the user sees the trajectory build up
    incrementally — the largest-N solves take noticeably longer (~N³ for
    the dense LU) and the user shouldn't have to wait for the whole sweep
    to see early points.

    Cancels on client disconnect (slider drag interrupts a stale sweep)
    using the same pattern as /sweep.
    """
    try:
        n_values = [int(n) for n in req.get("n_values", [])]
    except (TypeError, ValueError, OverflowError):
        raise HTTPException(
            status_code=422, detail="n_values must be a list of integers"
        ) from None
    use_pynec = req.get("solver") == "pynec" and pynec_backend.HAVE_PYNEC
    solver_name = "pynec" if use_pynec else "momwire"
    # Admission by cost (issue #382): point-count refuse (413) and the
    # poor-match warn (403 without approval). The per-N matrix-size refuse
    # stays inside the loop — est_basis moves with N.
    _refuse_or_withhold(
        _admit(req, kind="converge", use_pynec=use_pynec, points=len(n_values)),
        req,
    )
    session, lane_gen = _lane_key(req)

    async def gen():
        for n in n_values:
            if await request.is_disconnected():
                return
            req_n = dict(req)
            req_n["n_per_wire"] = n
            try:
                # Reject N values past the size cap (the convergence sweep is
                # exactly where someone pushes N high); surfaced per-N below.
                _check_solve_size(req_n, use_pynec=use_pynec)
                # One lane turn per point (see /sweep).
                async with _LANES.turn(session, "converge", lane_gen) as token:
                    async with cancel_on_disconnect(request, token):
                        z, feeds_z = await run_in_threadpool(
                            _solve_z_only, req_n, cancel=token
                        )
            except (Superseded, momwire.SolveAborted):
                return
            except Exception as e:
                # One-off solver failures (e.g. degenerate geometry at very
                # small N) or a size rejection shouldn't abort the whole sweep —
                # note the error for this N and keep going.
                yield (
                    json.dumps(
                        {
                            "n_per_wire": n,
                            # Same formatter as every other endpoint: type +
                            # message + user-design basename only, never a
                            # raw path or traceback (issue #348).
                            "error": user_designs.format_solve_error(e),
                            "solver": solver_name,
                        }
                    )
                    + "\n"
                )
                continue
            record: dict = {
                "n_per_wire": n,
                "z_re": float(z.real),
                "z_im": float(z.imag),
                "solver": solver_name,
            }
            # Multi-feed geometries (bowtie 1×2 array) ship per-feed Z so
            # the frontend can plot one convergence trail per port. Single-
            # feed geometries omit the field; the stream shape is unchanged.
            if feeds_z is not None:
                record["feeds_z_re"] = [float(z_.real) for z_ in feeds_z]
                record["feeds_z_im"] = [float(z_.imag) for z_ in feeds_z]
            yield json.dumps(record) + "\n"
        yield json.dumps({"done": True, "solver": solver_name}) + "\n"

    return StreamingResponse(gen(), media_type="application/x-ndjson")


@app.post("/pattern")
async def pattern_endpoint(req: dict):
    """NEC's rp_card-computed gain pattern. PyNEC-only."""
    if req.get("solver") != "pynec" or not pynec_backend.HAVE_PYNEC:
        return {"available": False}
    # rp_card needs a full NEC solve first, so the hosted matrix-size cap
    # applies here exactly like the /ws solve path.
    try:
        _check_solve_size(req, use_pynec=True)
    except SolveTooLargeError as e:
        return {"available": False, "error": str(e)}
    session, lane_gen = _lane_key(req)
    try:
        # PyNEC-only, so the token is a start gate: a queued pattern that a
        # knob drag overtook dies here instead of grinding a stale solve.
        async with _LANES.turn(session, "pattern", lane_gen):
            return await run_in_threadpool(pynec_backend.pattern, req)
    except Superseded:
        return {"available": False}


def _norm_check(req: dict, cancel=None) -> dict:
    """Consistency check for the far-field normalisation, dwell-triggered.

    The live `directivity_norm` comes from the circuit side (η₀k²/8π·P_in);
    here we recompute the same gain norm from the FIELD side — the closed-form
    pattern integral (`_pattern_integral_norm`) × efficiency. The two agree
    exactly for a self-consistent solve, so the dB gap between them is the
    discretisation's power-balance error: NEC's "average gain" diagnostic.
    The norm is a single scalar multiplying the whole pattern, so the frontend
    overlays it as a pure radial dBi shift of the live trace.

    Reuses the settled solve (a cache hit on the dwell request, so no re-solve
    on the common path). Falls back to the fine-grid quadrature when the
    response carries a finite (non-PEC-sentinel) ground — the image identity
    behind the closed form is exact only for a perfect reflector.

    Also derives `radiated_fraction` = P_radiated/P_input, the honest third
    efficiency ledger (`far_field.radiated_fraction`, issue #339). No extra
    integral: gain-per-input-watt averaged over the sphere is exactly
    efficiency · directivity_norm / pattern_norm — the norm-check ratio with
    the structural efficiency folded back out of the field-side norm. Over a
    finite ground the shortfall from 1.0 is structural loss plus real ground
    absorption; over PEC/free space it collapses to ~structural efficiency
    (times the solver's self-consistency gap, <0.05 dB on converged designs).
    """
    out = solve(dict(req), cancel=cancel)
    if "directivity_norm" not in out or out["directivity_norm"] <= 0:
        return {"available": False}
    ground_on = bool(out.get("ground", False))
    pec = float(out.get("ground_eps_r", _PEC_GROUND_EPS_R)) >= 1e6 and not float(
        out.get("ground_sigma", 0.0) or 0.0
    )
    if not ground_on or pec:
        pattern_norm = _pattern_integral_norm(out)
        method = "closed_form"
    else:
        ref = dict(out)
        # Size the reference grid off THIS design's adaptive pick (2x margin,
        # 45x90 floor — `_fine_norm_grid`'s contract), not the max-size grid:
        # passing the literal floor here used to force 90x180 on every
        # finite-ground check (~750 ms on a 6λ skyloop, ~8x the solve
        # itself). Measured: the adaptive grid already matches 90x180 to
        # <1e-4 dB on the calibration designs, so the doubled pick keeps a
        # genuine safety margin at a fraction of the cost.
        mid, _dr, _i = _moment_segments(out)
        nt_adapt, _ = _adaptive_norm_grid(
            float(out["k_meas_m_inv"]), mid.min(axis=0), mid.max(axis=0)
        )
        n_theta, n_phi = _fine_norm_grid(nt_adapt)
        _compute_directivity_norm(ref, n_theta=n_theta, n_phi=n_phi)
        pattern_norm = ref["directivity_norm"]
        method = f"grid_{n_theta}x{n_phi}"
    efficiency = float(out.get("radiation_efficiency", 1.0))
    return {
        "available": pattern_norm > 0,
        "directivity_norm": out["directivity_norm"],
        "pattern_norm": pattern_norm,
        "method": method,
        "radiation_efficiency": efficiency,
        "radiated_fraction": (
            efficiency * out["directivity_norm"] / pattern_norm
            if pattern_norm > 0
            else 0.0
        ),
    }


@app.post("/norm_check")
async def norm_check_endpoint(req: dict, request: Request):
    """Field-side vs circuit-side gain-norm consistency check for the
    far-field overlay (dwell-triggered). See `_norm_check`."""
    use_pynec = req.get("solver") == "pynec" and pynec_backend.HAVE_PYNEC
    _refuse_or_withhold(_admit(req, kind="norm_check", use_pynec=use_pynec), req)
    session, lane_gen = _lane_key(req)
    try:
        # The common path is a cache hit on the settled live solve (the lane
        # runs the live turn first, so the cache is warm by our turn); the
        # miss path is a full solve, hence the turn + disconnect watcher.
        async with _LANES.turn(session, "norm_check", lane_gen) as token:
            async with cancel_on_disconnect(request, token):
                return await run_in_threadpool(_norm_check, req, cancel=token)
    except (Superseded, momwire.SolveAborted):
        return {"available": False}


@app.post("/export_nec")
async def export_nec_endpoint(req: dict):
    """Render the current design as a downloadable NEC2 .nec card deck.

    Reuses the same builder construction as the live solve (params, variant,
    frequency, ground), so the deck matches the antenna on screen. Returns 422
    for designs with no faithful native-NEC representation (TL/virtual-
    driver networks), which the frontend surfaces as a message.
    """
    geometry = req.get("geometry", next(iter(EXAMPLES)))
    ex = EXAMPLES.get(geometry) or next(iter(EXAMPLES.values()))
    if ex.nec_export is None:
        raise HTTPException(
            status_code=422, detail="NEC export unavailable for this design."
        )
    try:
        deck = await run_in_threadpool(ex.nec_export, req)
    except (NotImplementedError, ValueError) as e:
        # ValueError: request validation (bad freq / radius / n_per_wire) —
        # a clean 422 rather than a 500 (issue #347).
        raise HTTPException(status_code=422, detail=str(e)) from e
    filename = f"{ex.name.replace('.', '_')}.nec"
    return Response(
        content=deck,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/params_source")
async def params_source_endpoint(req: dict):
    """Serialise the current knob values to a paste-ready Python params block.

    Reuses the same variant + live-knob overlay as the solve path, so the
    emitted ``default_params`` (or ``<variant>_params``) block matches the
    antenna on screen. Knob-values-only by default; pass ``include_ui: true``
    for a wholesale block and ``wrap: "mappingproxy"`` to match catalog style.
    Returns ``{"available": False}`` for a design that can't be serialised.
    """
    geometry = req.get("geometry", next(iter(EXAMPLES)))
    ex = EXAMPLES.get(geometry) or next(iter(EXAMPLES.values()))
    if ex.params_source is None:
        return {"available": False}
    try:
        source = await run_in_threadpool(ex.params_source, req)
    except Exception as exc:  # noqa: BLE001 — a user design's params can be odd
        return {"geometry": geometry, "error": user_designs.format_solve_error(exc)}
    return {"geometry": geometry, "available": True, "source": source}


@app.post("/pattern_metrics")
async def pattern_metrics_endpoint(req: dict, request: Request):
    """Scalar far-field metrics for the current antenna, for the compare table.

    Reuses the same builder + momwire engine as the live solve, so the metrics
    match the lobe drawn on screen. Returns ``{available, metrics}`` where
    metrics carries peak_gain_dbi / takeoff_deg / azimuth_deg /
    front_to_back_db / az_beamwidth_deg / el_beamwidth_deg (+ the freq).
    """
    geometry = req.get("geometry", next(iter(EXAMPLES)))
    ex = EXAMPLES.get(geometry) or next(iter(EXAMPLES.values()))
    if ex.far_field_metrics is None:
        return {"available": False}
    # far_field_metrics runs a full momwire solve; apply the hosted matrix-
    # size cap here like every other solve-forming route.
    try:
        _check_solve_size(req, use_pynec=False)
    except SolveTooLargeError as e:
        return {"geometry": geometry, "error": str(e)}
    # Lane turn with NO generation: compare-table rows describe *other*
    # designs at their defaults, so a knob drag on the live design must not
    # supersede them — they still serialize with everything else and stop
    # when their client goes away.
    session, _ = _lane_key(req)
    try:
        async with _LANES.turn(session, "pattern_metrics") as token:
            async with cancel_on_disconnect(request, token):
                metrics = await run_in_threadpool(
                    ex.far_field_metrics, req, cancel=token
                )
    except (Superseded, momwire.SolveAborted):
        return {"geometry": geometry, "available": False}
    except Exception as exc:  # noqa: BLE001 — a user design's build_wires can raise
        return {"geometry": geometry, "error": user_designs.format_solve_error(exc)}
    return {"geometry": geometry, "available": True, "metrics": metrics}


@app.post("/geometry")
async def geometry_endpoint(req: dict):
    """Fast geometry-only snapshot of the selected antenna: wire positions +
    feed marker, no MoM solve. The frontend fetches this the instant the user
    picks a new antenna so the shape renders immediately (large arrays take
    tens of seconds to solve); the live /ws solve then supplies currents,
    impedance, and far field. Geometry is solver-independent, so this always
    uses the momwire builder path regardless of the request's `solver`.
    """
    geometry = req.get("geometry", next(iter(EXAMPLES)))
    ex = EXAMPLES.get(geometry) or next(iter(EXAMPLES.values()))
    if ex.momwire_geometry is None:
        return {"available": False}
    try:
        out = await run_in_threadpool(ex.momwire_geometry, req)
    except Exception as exc:  # noqa: BLE001 — a user design's build_wires can raise
        # Geometry builds lazily on selection now, so a broken user design
        # fails here rather than at load. Return the cause (200, not 500) so the
        # frontend can show it in the solve-error banner instead of a blank stage.
        return {"geometry": geometry, "error": user_designs.format_solve_error(exc)}
    out["solver"] = "momwire"
    return out


@app.post("/optimize")
async def optimize_endpoint(req: dict):
    """Tune a chosen subset of knobs to optimise an electrical objective.

    The request is a normal solve request plus an `optimize` block:
        optimize = {
          "free": [{"name", "min", "max"}, ...],   # which knobs + their bounds
          "objective": "swr" | "resonance" | "match_z0",
          "max_evals": <int, optional>,
        }
    Returns the best params found + before/after metrics. The objective is
    evaluated at the request's measurement frequency through the geometry's
    impedance-only momwire_solve (cheap — no far field), so a run is dozens of
    quick solves rather than a far-field sweep. Always uses the momwire engine
    regardless of the request's `solver` (PyNEC would be far too slow per eval).
    """
    from .optimize import OBJECTIVES, optimize as _optimize

    opt = req.get("optimize") or {}
    free = opt.get("free") or []
    if not free:
        return {"error": "select at least one knob to vary"}
    objective = opt.get("objective", "swr")
    if objective not in OBJECTIVES:
        return {"error": f"unknown objective {objective!r}"}
    max_evals = opt.get("max_evals")
    if max_evals is not None:
        try:
            max_evals = int(max_evals)
        except (TypeError, ValueError):
            return {"error": f"max_evals must be an integer (got {max_evals!r})"}
        if max_evals <= 0:
            max_evals = None
        elif _HOSTED:
            # Hard ceiling regardless of the client value: every eval is a
            # full MoM solve that skips the solve cache, so an unbounded
            # budget is a sustained-CPU lever (issue #346).
            max_evals = min(max_evals, _MAX_OPT_EVALS)

    geometry = req.get("geometry", next(iter(EXAMPLES)))
    ex = EXAMPLES.get(geometry) or next(iter(EXAMPLES.values()))
    base = {k: v for k, v in req.items() if k != "optimize"}
    # Every optimizer eval is a full momwire solve of the base geometry (the
    # free knobs never change n_per_wire), so one hosted size check on the
    # base request covers the whole run.
    try:
        _check_solve_size(base, use_pynec=False)
    except SolveTooLargeError as e:
        return {"geometry": geometry, "error": str(e)}
    try:
        result = await run_in_threadpool(
            _optimize,
            base,
            free,
            objective,
            solve_fn=ex.momwire_solve,
            max_evals=max_evals,
        )
    except Exception as exc:  # noqa: BLE001 — a user design's build_wires can raise
        return {"geometry": geometry, "error": user_designs.format_solve_error(exc)}
    result["geometry"] = geometry
    return result


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.get("/examples")
def examples_endpoint():
    """Serve the registered antenna examples + their parameter schemas.

    The frontend reads this on mount to populate the geometry dropdown
    and render the parameter sliders generically. Each example reports
    its `multi_feed` flag (affects the response handling for arrays of
    feeds) plus a result_schema that may mix scalar ResultFieldSpec
    rows with ResultGroupSpec repeat groups.

    Reloads user designs first (live edits without a restart) and returns
    any that failed to load under `errors`, so the UI can show them.
    """
    load_errors = user_designs.refresh()

    def _sweep_policy_json(p) -> dict:
        return {
            "anchor": p.anchor,
            "lo_factor": p.lo_factor,
            "hi_factor": p.hi_factor,
            "band_locked": p.band_locked,
        }

    def _serialize_schema_item(item) -> dict:
        # Discriminate by attribute: ParamGroupSpec has `params`, ParamSpec
        # doesn't. Recurses so groups-in-groups serialize cleanly (the
        # frontend only renders one level today but the wire format is
        # already general).
        if hasattr(item, "params"):
            return {
                "kind": "group",
                "name": item.name,
                "label_template": item.label_template,
                "repeat_count": item.repeat_count,
                "max_repeats": item.max_repeats,
                "params": [_serialize_schema_item(p) for p in item.params],
                "default_overrides": list(item.default_overrides),
                "link_meas_freq_to_param": item.link_meas_freq_to_param,
            }
        return {
            "name": item.name,
            "label": item.label,
            "default": item.default,
            "kind": item.kind,
            "min": item.min,
            "max": item.max,
            "step": item.step,
            "precision": item.precision,
            "unit": item.unit,
            "visible_when": item.visible_when,
            "enum_options": (
                list(item.enum_options) if item.enum_options is not None else None
            ),
            "range_from_enum_option": item.range_from_enum_option,
            "on_change_set": item.on_change_set,
            "linked_to_design_freq": item.linked_to_design_freq,
            "link_meas_freq_to_param": item.link_meas_freq_to_param,
            "layout": item.layout,
        }

    out = []
    for name, ex in EXAMPLES.items():
        out.append(
            {
                "name": ex.name,
                "label": ex.label,
                "multi_feed": ex.multi_feed,
                "param_schema": [_serialize_schema_item(p) for p in ex.param_schema],
                "result_schema": [
                    (
                        {
                            "kind": "group",
                            "name": r.name,
                            "label_template": r.label_template,
                            "fields": [
                                {
                                    "field": f.field,
                                    "label": f.label,
                                    "precision": f.precision,
                                    "unit": f.unit,
                                }
                                for f in r.fields
                            ],
                        }
                        if hasattr(r, "fields")
                        else {
                            "field": r.field,
                            "label": r.label,
                            "precision": r.precision,
                            "unit": r.unit,
                        }
                    )
                    for r in ex.result_schema
                ],
                "bands": [
                    {
                        "key": b.key,
                        "label": b.label,
                        "freq_mhz": b.freq_mhz,
                        "min_mhz": b.min_mhz,
                        "max_mhz": b.max_mhz,
                    }
                    for b in ex.bands
                ],
                "meas_freq_range_mhz": (
                    list(ex.meas_freq_range_mhz)
                    if ex.meas_freq_range_mhz is not None
                    else None
                ),
                "default_view": ex.default_view,
                "default_freq_mhz": ex.default_freq_mhz,
                "default_backend": ex.default_backend,
                "has_design_freq": ex.has_design_freq,
                "variants": list(ex.variants),
                "variant_values": dict(ex.variant_values),
                "sweep_policy": _sweep_policy_json(ex.sweep_policy),
                # Per-variant hint overrides; only variants that differ from
                # the design-level values appear here. `sweep_policy` falls
                # back to the top-level field; `params` carries explicit
                # per-param presentation hints (slider min/max/step, precision,
                # unit, label) the frontend overlays on param_schema for the
                # active variant.
                "variant_ui": {
                    v: {
                        **(
                            {"sweep_policy": _sweep_policy_json(h["sweep_policy"])}
                            if "sweep_policy" in h
                            else {}
                        ),
                        **({"params": h["params"]} if "params" in h else {}),
                    }
                    for v, h in ex.variant_ui.items()
                },
                "notes": ex.notes,
                "layout": ex.layout,
            }
        )
    out.sort(key=lambda e: e["label"])
    return {"examples": out, "errors": load_errors}


def _resolve_user_design_path(stem: str):
    """A ``user.<stem>`` or ``<stem>`` name → the backing user-design file, or
    None. Trusting is a local, single-user action; the shared hosted instance
    never runs user code, so the endpoints below refuse when hosted."""
    from antennaknobs.user_designs import USER_NS, find_design_file

    stem = stem or ""
    if stem.startswith(f"{USER_NS}."):
        stem = stem[len(USER_NS) + 1 :]
    return find_design_file(stem)


@app.post("/trust")
def trust_endpoint(req: dict):
    """Trust a user design so it will load. `mode` is "pinned" (this exact
    version, the default) or "always" (this file + future edits, for a design
    the user authored). Local-only: refused on the hosted instance."""
    if _HOSTED:
        raise HTTPException(
            status_code=403,
            detail="trusting user designs is disabled on the hosted instance",
        )
    from antennaknobs import design_trust

    stem = req.get("stem", "")
    path = _resolve_user_design_path(stem)
    if path is None:
        raise HTTPException(status_code=404, detail=f"no such user design: {stem!r}")
    mode = "always" if req.get("allow_edits") else "pinned"
    design_trust.trust(path, mode=mode)
    # Register it now so the caller can re-fetch /examples and see it live.
    user_designs.refresh()
    return {"ok": True, "stem": path.stem, "mode": mode}


@app.post("/untrust")
def untrust_endpoint(req: dict):
    """Revoke trust for a user design so it stops loading. Local-only."""
    if _HOSTED:
        raise HTTPException(
            status_code=403,
            detail="trusting user designs is disabled on the hosted instance",
        )
    from antennaknobs import design_trust

    stem = req.get("stem", "")
    path = _resolve_user_design_path(stem)
    if path is None:
        raise HTTPException(status_code=404, detail=f"no such user design: {stem!r}")
    removed = design_trust.untrust(path)
    user_designs.refresh()
    return {"ok": True, "stem": path.stem, "removed": removed}


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    # Latest-wins mailbox. A dedicated reader task drains the socket into a
    # size-1 mailbox (overwriting any unsolved request), while the solver loop
    # below pulls the newest request whenever it's free. This squashes
    # superseded knob changes *server-side*: the client sends every change
    # eagerly with a monotonic `_seq`, and only the freshest queued request is
    # ever solved. Results known to be superseded (a newer request already sat
    # in the mailbox before we could send) are skipped — the doomed payload
    # never travels. The client renders monotonically by `_seq`, so a higher
    # `_seq` response implicitly acknowledges every lower one.
    await ws.accept()
    mailbox: list[dict] = []  # size-1: newest unsolved request only
    newer = asyncio.Event()  # set when the mailbox is (re)filled
    closed = asyncio.Event()  # set when the socket disconnects
    # In-flight solve's cancel token, shared between the reader and the solver
    # loop (both coroutines on this event loop, so no lock needed — the token's
    # flag is the only thing the threadpool worker touches). The reader trips it
    # to preempt a solve the moment a newer request lands or the socket closes.
    current: dict = {"token": None}

    async def reader() -> None:
        # Starlette requires a single reader on the socket, so *all*
        # receive_text calls happen here; the solver loop never reads.
        try:
            while True:
                req = json.loads(await ws.receive_text())
                mailbox[:] = [req]  # overwrite → squash anything unsolved
                token = current["token"]
                if token is not None:
                    token.cancel()  # preempt the now-superseded in-flight solve
                # Newer user state also preempts the session's OLDER batch
                # work (a running sweep chunk, queued converge points) right
                # now — the solver loop won't admit this request's turn until
                # the lane frees, and waiting for that would leave a stale
                # benchmark-mesh chunk grinding for minutes (issue #382).
                _LANES.advance(*_lane_key(req))
                newer.set()
        except WebSocketDisconnect:
            pass
        finally:
            closed.set()
            token = current["token"]
            if token is not None:
                token.cancel()  # disconnect: free the threadpool worker promptly
            newer.set()  # wake the solver so it can observe `closed` and exit

    reader_task = asyncio.create_task(reader())
    try:
        while True:
            await newer.wait()
            newer.clear()
            if closed.is_set() and not mailbox:
                return
            if not mailbox:
                continue
            req = mailbox.pop()
            session, lane_gen = _lane_key(req)
            try:
                # The lane turn (issue #382) serializes this solve against the
                # session's batch work — and outranks it, so at most one chunk
                # stands between a knob drag and its heatmap. Entering with
                # this request's generation cancels any older running batch
                # chunk at its next solver checkpoint.
                async with _LANES.turn(session, "live", lane_gen) as token:
                    if closed.is_set():
                        return
                    if mailbox:
                        # Superseded while we waited for the lane: solving this
                        # request would be wasted work — loop for the newer one.
                        continue
                    # Publish the token BEFORE dispatch: a reader that fires in
                    # the gap cancels a not-yet-started solve, which then raises
                    # SolveAborted at its first checkpoint — no lost-wakeup
                    # window. (While we *waited* for the lane there was no token
                    # to trip; the mailbox check above covers that stretch.)
                    current["token"] = token
                    try:
                        result = await run_in_threadpool(solve, req, cancel=token)
                    finally:
                        current["token"] = None
            except (Superseded, momwire.SolveAborted):
                # Superseded (or disconnected) mid-solve or mid-wait: a newer
                # request already overtook this one. Send nothing — the
                # superseding response will carry a higher _seq and the client
                # renders monotonically. This catch MUST precede the generic
                # handler, which would otherwise ship the abort to the client
                # as a solve-error banner.
                continue
            except Exception as exc:  # noqa: BLE001 — a user design's build_wires can raise
                # A solve that raises must not tear down the socket (that drops
                # every subsequent slider-driven solve). Send the cause so the
                # frontend shows it in the solve-error banner, then keep serving.
                result = {
                    "geometry": req.get("geometry"),
                    "error": user_designs.format_solve_error(exc),
                }
            # Echo the sequence number on EVERY response, error path included —
            # the client keys ordering, RTT accounting, and solving-state off it,
            # and a stuck request would leave `solving` true forever if any path
            # dropped the echo. The stamp lands on the (deep)copied result solve()
            # returns, never on a cached entry.
            result["_seq"] = req.get("_seq")
            # Superseded while we solved? A newer request is already queued, so
            # skip this send entirely — its response will carry a higher `_seq`
            # and the client renders monotonically. Saves the full doomed payload
            # (wires + interleaved sample-current arrays) on the wire.
            if mailbox:
                continue
            # The client can disconnect *during* the solve (rapid slider drag
            # tears down the React effect's WS and opens a fresh one before our
            # threadpool finishes). When that happens send_text races with the
            # closed socket and uvicorn logs a noisy "socket.send() raised
            # exception". Skip the send when we've already been disconnected, and
            # treat any error during send as a disconnect.
            if closed.is_set() or ws.client_state != WebSocketState.CONNECTED:
                return
            try:
                await ws.send_text(json.dumps(result))
            except (WebSocketDisconnect, RuntimeError):
                return
    finally:
        reader_task.cancel()


# Serve the built React frontend (web/static, produced by `npm run build` in
# web/frontend) at "/". Mounted LAST so every API route and FastAPI's own
# /docs + /openapi.json (local only — disabled when hosted, see the FastAPI
# construction) — all registered above — take precedence; the mount only
# catches "/", the SPA's assets, and other unclaimed GETs. html=True serves
# index.html for the root.
#
# Gated on the directory existing: a source checkout / editable install without
# a frontend build (the dev workflow, where Vite serves the SPA on :5173 and
# proxies here) simply runs API-only, while a wheel install — which ships the
# built bundle as package data — serves the whole app from this one process.
_FRONTEND_DIR = Path(__file__).resolve().parent / "static"
if _FRONTEND_DIR.is_dir():
    app.mount("/", StaticFiles(directory=_FRONTEND_DIR, html=True), name="frontend")

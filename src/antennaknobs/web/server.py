"""FastAPI server for the interactive antenna UI.

All geometries live in web.examples — each registered antenna bundles its
momwire solve/sweep and pynec build/solve into one file. Dispatchers here
look the geometry up in EXAMPLES and call its callables; adding or
removing an antenna doesn't touch this file.

The response shape is uniform across geometries — each wire is a sequence of
knots with per-knot complex currents and the feed lives on one of the wires —
so the frontend draws every geometry the same way.

Run:
    OMP_WAIT_POLICY=PASSIVE GOMP_SPINCOUNT=0 OPENBLAS_THREAD_TIMEOUT=1 \\
        uvicorn antennaknobs.web.server:app --reload

(needs uvicorn[standard] — /ws is a WebSocket upgrade. The env prefix parks
the idle workers of BOTH pools — libgomp's and OpenBLAS's — between solves;
see the thread-policy block below. The server works without it, at roughly
15% higher interactive-solve latency for the OMP half and 26-49% for the
OpenBLAS half on the swept-ground path.)
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from datetime import datetime, timezone
import math
import os
import time
from collections import OrderedDict
from collections.abc import AsyncIterator
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

from antennaknobs.terrain import Facet, Sector, Terrain, specular_cut

from . import cost as _cost
from . import nec5_backend, pynec_backend, user_designs
from .examples import REGISTRY as EXAMPLES
from .lane import LaneRegistry, Superseded, cancel_on_disconnect
from .progress_stream import ProgressStream, ProgressStreamClosed

_logger = logging.getLogger(__name__)


def _physical_cpu_count() -> int:
    """Number of physical cores (not logical / HT siblings).

    A DEFAULT, not a claim that physical is always right — see below. Override
    with OMP_NUM_THREADS / OPENBLAS_NUM_THREADS if your workload disagrees.

    The old rationale here said the quadrature kernels are FP-vector-saturated
    (libmvec AVX2 sin/cos, no spare FU bandwidth) so HT siblings contend rather
    than overlap, citing an ad-hoc KBL-R bench where 4 threads beat 8 by ~15%
    on the swept-ground path. Re-measured on two machines with OpenBLAS's
    spin-wait fixed (issue #1050 — that bench was taken with it on, which
    produces the same "fewer threads is faster" signature for a different
    reason), the picture is that the preference follows the KERNEL PATH, not
    the engine and not the server (issue #1051):

      swept refl-coef   physical wins, +9.4% (laptop) / +8..15% (desktop)
      swept Sommerfeld  a tie
      free space        LOGICAL wins, -12.1% / -1.9%
      pynec (2 decks)   LOGICAL wins, -6% to -15%

    So the FP-saturation argument is real where it applies — it just does not
    apply everywhere this pin does, and pynec pays 10-15% for it.

    We keep the physical-core default anyway, deliberately:

      - the honest margins are single digits, an order of magnitude below the
        20-30% run-to-run spread of a thermally limited laptop, so no automatic
        policy could deliver a benefit a user would actually observe;
      - on a hybrid P/E-core part `psutil.cpu_count(logical=False)` returns
        P-cores + E-cores, whose members differ in throughput. For a
        barrier-synchronised fill gated by its slowest thread, "physical core
        count" is not merely a poor policy input there, it is not a well-defined
        one. Nobody has measured that case.

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
#   - Physical over logical is a DEFAULT, not a measured win everywhere: the
#     preference follows the kernel path (refl-coef prefers physical, free
#     space and pynec prefer logical), and the margins are single digits once
#     OpenBLAS's spin-wait is off. Kept because no automatic policy can beat
#     that spread on real hardware, and because the count is not even
#     well-defined on a hybrid P/E part — see _physical_cpu_count() and
#     issue #1051. Override per-pool with the env vars below.
#
# Operators can still override per-pool via the usual env vars (honored by
# the libraries at load AND respected here). Three knobs remain env-only —
# each library reads its own once at load, before any Python code can run, so
# they must be set in the launch environment (the Dockerfile CMD does; for
# local runs see the docstring). threadpoolctl is no escape hatch for these:
# it expresses thread COUNTS only, never a wait policy or a timeout.
#   - OMP_WAIT_POLICY=PASSIVE + GOMP_SPINCOUNT=0 park idle OMP workers
#     instead of busy-spinning through each solve's Python phases (~13–20%
#     off small-solve latency, hentenna N=21).
#   - OPENBLAS_THREAD_TIMEOUT=1 does the same for OpenBLAS. Its workers
#     otherwise keep spinning after a factorization returns and steal cores
#     from the NEXT solve's OpenMP fill — isolated by pinning BLAS to 1
#     DURING the fill, where raising LU threads 1->8 still made the fill 39%
#     slower. Worth +26%/+49% on swept-ground (N=200/400) and +37%/+39% on
#     Sommerfeld (N=100/200) at the thread count pinned below, and up to 5x
#     on a 15W laptop, where the spinners cost ~250 MHz of clock as well as
#     cores. Across 2 engines, 4 decks and 3 ground models: 22 cells gained,
#     2 were null, none regressed. The nulls are pynec's large decks, where
#     the time is inside the C extension and there is no fill to steal from
#     — the mechanism predicting its own null case (issue #1050).
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


def _terrain_from_packed(d: dict) -> Terrain:
    """Rebuild the faceted terrain from a response's `ground_terrain` field
    (the adapter's _pack_terrain). Validation lives in the terrain
    dataclasses — bad client data raises ValueError/TypeError/KeyError,
    which the /cuts endpoint maps to a 400."""
    return Terrain(
        sectors=tuple(
            Sector(
                az0=float(s["az0"]),
                az1=float(s["az1"]),
                facets=tuple(
                    Facet(
                        x1=None if f[0] is None else float(f[0]),
                        z1=float(f[1]),
                        eps_r=float(f[2]),
                        sigma=float(f[3]),
                    )
                    for f in s["facets"]
                ),
            )
            for s in d["sectors"]
        )
    )


def _terrain_ray_geometry(terrain: Terrain, rhat, mid, dr, i_mid):
    """Per-ray specular-facet data for a faceted terrain: surface height z_f
    at each ray's specular point, facet downward tilt beta, and the facet
    medium (eps_r, sigma), all over rhat's leading shape. Mirrors the
    engine's grid-based branch (engines/momwire.py _evaluate_M_perp) for
    arbitrary direction sets; h_ref is the same current-weighted mean
    segment height (the web ground plane sits at z=0)."""
    w = np.abs(i_mid) * np.linalg.norm(dr, axis=1)
    wsum = float(np.sum(w))
    h_ref = float((np.sum(w * mid[:, 2]) / wsum) if wsum > 0 else np.mean(mid[:, 2]))

    shape = rhat.shape[:-1]
    rxf = rhat[..., 0].ravel()
    ryf = rhat[..., 1].ravel()
    rzf = rhat[..., 2].ravel()
    theta = np.arccos(np.clip(rzf, -1.0, 1.0))
    sec_idx = terrain.sector_for(np.degrees(np.arctan2(ryf, rxf)))
    z_f = np.empty(theta.shape)
    beta = np.empty(theta.shape)
    eps = np.empty(theta.shape)
    sig = np.empty(theta.shape)
    for i, sector in enumerate(terrain.sectors):
        rays = sec_idx == i
        if not np.any(rays):
            continue
        zf_t, b_t, e_t, s_t = specular_cut(sector, theta[rays], h_ref)
        z_f[rays] = zf_t
        beta[rays] = b_t
        eps[rays] = e_t
        sig[rays] = s_t
    return (
        z_f.reshape(shape),
        beta.reshape(shape),
        eps.reshape(shape),
        sig.reshape(shape),
    )


def _mag2_at_directions(
    out: dict,
    rhat: np.ndarray,
    *,
    mid=None,
    dr=None,
    i_mid=None,
    terrain_pec: bool = False,
):
    """|M_perp|² at arbitrary far-field directions — the single server-side
    implementation of the pattern physics (issue #547; the frontend's JS
    copy is being retired against this).

    rhat: (..., 3) unit direction array (any leading shape). With ground on,
    evaluates the PEC image + per-ray Fresnel correction from the response's
    ground constants. Returns a real array of rhat's leading shape. Callers
    that already hold the moment set pass it via mid/dr/i_mid to skip the
    re-extraction.

    terrain_pec (faceted-terrain responses only): evaluate the same facet
    geometry — image, height phase, specular selection — with the media
    forced to a perfect reflector (ρ_h=−1, ρ_v=+1). The reference integral
    for the terrain ground-absorption ledger: the real/PEC power ratio
    cancels the geometric restructuring and isolates media absorption.
    """
    k = float(out["k_meas_m_inv"])
    ground_on = bool(out.get("ground", False))
    if mid is None:
        mid, dr, i_mid = _moment_segments(out)
    rx, ry, rz = rhat[..., 0], rhat[..., 1], rhat[..., 2]

    phase = k * np.einsum("...c,nc->...n", rhat, mid)
    expp = np.exp(1j * phase)
    weighted = i_mid[:, None] * dr  # (Nseg, 3)
    M = np.einsum("...n,nc->...c", expp, weighted)
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
        phase_img = k * np.einsum("...c,nc->...n", rhat, mid_img)
        expp_img = np.exp(1j * phase_img)
        M_img = np.einsum("...n,nc->...c", expp_img, weighted_img)
        m_img_dot_r = np.sum(M_img * rhat, axis=-1)
        M_img_perp = M_img - m_img_dot_r[..., None] * rhat

        # Polarization basis at each ray: ĥ = ẑ × r̂ (perp to plane of
        # incidence), v̂ = r̂ × ĥ (in plane of incidence, perp to r̂). At the
        # pole (s → 0, e.g. the elevation cut's zenith sample, where float
        # cos(π/2) ≈ 6e-17) the basis degenerates; normal incidence makes
        # ρ_v = −ρ_h so any horizontal orthonormal pair is the correct limit
        # — substitute x̂/ŷ. Guarding only the division would instead shrink
        # ĥ, v̂ to ~0 and silently drop the reflected wave at that sample.
        s = np.sqrt(rx * rx + ry * ry)
        at_pole = s <= 1e-9
        s_safe = np.where(at_pole, 1.0, s)
        h_hat = np.stack(
            [
                np.where(at_pole, 1.0, -ry / s_safe),
                np.where(at_pole, 0.0, rx / s_safe),
                np.zeros_like(rx),
            ],
            axis=-1,
        )
        v_hat = np.stack(
            [
                np.where(at_pole, 0.0, -rx * rz / s_safe),
                np.where(at_pole, 1.0, -ry * rz / s_safe),
                np.where(at_pole, 0.0, s),
            ],
            axis=-1,
        )

        M_img_h = np.sum(M_img_perp * h_hat, axis=-1)
        M_img_v = np.sum(M_img_perp * v_hat, axis=-1)

        terr = out.get("ground_terrain")
        if terr:
            # Faceted terrain (issue #534): per ray, find the facet the
            # specular point lands on, shift the image plane to the facet
            # surface (an extra 2·k·z_f·cosθ path phase — z_f ≤ 0 below
            # the crest, so the reflected wave rides the full effective
            # height), tilt the incidence angle by the facet slope, and
            # evaluate Fresnel with the facet's medium.
            z_f, beta, eps_g, sig_g = _terrain_ray_geometry(
                _terrain_from_packed(terr), rhat, mid, dr, i_mid
            )
            pf = np.exp(2j * k * z_f * rz)
            M_img_h = M_img_h * pf
            M_img_v = M_img_v * pf
            omega = 2.0 * np.pi * float(out["measurement_freq_mhz"]) * 1e6
            eps_c = eps_g + 1j * (-sig_g / (omega * _EPS0))
            th_loc = np.clip(np.arccos(np.clip(rz, -1.0, 1.0)) - beta, 0.0, np.pi / 2)
            # On untilted facets keep the flat branch's exact trig route
            # (rz / s·s) so a single-flat-facet terrain reproduces the plain
            # finite ground bit-for-bit (mirrors the engine, #534 gate 1).
            cos_ti = np.where(beta == 0.0, rz, np.cos(th_loc))
            sin2_ti = np.where(beta == 0.0, s * s, np.sin(th_loc) ** 2)
        else:
            eps_c = out["ground_eps_r"] + 1j * out["ground_eps_im"]
            cos_ti = rz
            sin2_ti = s * s
        if terr and terrain_pec:
            # Perfect-reflector facets (see docstring): geometry intact,
            # media losses off.
            rho_h, rho_v = -1.0, 1.0
        else:
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

    return np.sum(M_perp.real**2 + M_perp.imag**2, axis=-1)


# The polar-chart cuts are sampled on this many directions around the full
# circle. The frontend draws whatever length the `azimuth`/`elevation`
# arrays carry, so this is free to change server-side.
_CUT_N_DIR = 180

# dBi floor sentinel for below-horizon samples (JSON can't carry -Infinity).
_CUT_FLOOR_DBI = -999.0

# Ceiling on a caller-specified cut parameterisation (issue #744). Adaptive
# refinement sends the base grid plus its extra angles; ~4× the uniform
# resolution is far past what any budget asks for and bounds the per-request
# far-field evaluation the way MAX_SWEEP_POINTS bounds a sweep.
_CUT_MAX_ANGLES = 720


def _cut_angles(raw, default_n: int = _CUT_N_DIR) -> np.ndarray:
    """Sanitised cut parameterisation in RADIANS.

    ``None`` gives the uniform circle the charts have always drawn (sample i
    at t = 2π·i/n). A caller-supplied list (issue #744) is validated, wrapped
    into [0, 360), deduped and SORTED here rather than trusted: the chart
    strokes these in order, so an out-of-order angle would draw a chord
    across the pattern.
    """
    if raw is None:
        return 2.0 * np.pi * np.arange(default_n) / default_n
    if not isinstance(raw, (list, tuple)):
        raise ValueError("cut angles must be a list of numbers")
    if len(raw) > _CUT_MAX_ANGLES:
        raise ValueError(f"cut angle list is over the {_CUT_MAX_ANGLES}-point limit")
    vals = []
    for a in raw:
        if isinstance(a, bool) or not isinstance(a, (int, float)):
            raise ValueError("cut angles must be numbers")
        f = float(a)
        if not math.isfinite(f):
            raise ValueError("cut angles must be finite")
        vals.append(f % 360.0)
    if not vals:
        return 2.0 * np.pi * np.arange(default_n) / default_n
    return np.radians(np.unique(np.asarray(vals, dtype=float)))


def _pattern_cuts(
    out: dict,
    az_elev_deg: float,
    elev_az_deg: float,
    *,
    mid=None,
    dr=None,
    i_mid=None,
    az_angles_deg=None,
    elev_angles_deg=None,
) -> dict | None:
    """The two polar-chart traces (issue #547): the azimuth cut at elevation
    `az_elev_deg` and the great-circle elevation cut through azimuth
    `elev_az_deg`, each a run of absolute-dBi samples.

    Both circles are parameterised as the frontend chart draws them: by
    default sample i sits at t = 2π·i/N_DIR, the azimuth cut running the
    horizon circle at the given elevation and the elevation cut the vertical
    circle whose t ∈ (180°, 360°) half dips below the horizon. With ground
    on, below-horizon samples clamp to _CUT_FLOOR_DBI. Returns None when the
    response can't support cuts (no wires or no positive gain norm).

    Adaptive refinement (issue #744) may replace either circle's uniform
    parameterisation with an explicit angle list. The response then carries
    that list back as ``az_angles_deg`` / ``elev_angles_deg``: with
    non-uniform sampling the chart can no longer DERIVE the angle from the
    index, so the parameterisation has to travel with the data. The fields
    stay ABSENT for the uniform case, which keeps every pre-#744 response
    and client valid — absent means "t = 2π·i/n", the contract that has
    always held.

    Callers that already hold the moment set (the solve_id cache, issue
    #551) pass it via mid/dr/i_mid; `out` then only needs the scalar/ground
    fields and may omit `wires`.
    """
    norm = float(out.get("directivity_norm") or 0.0)
    if norm <= 0.0 or (mid is None and not out.get("wires")):
        return None
    t_az = _cut_angles(az_angles_deg)
    t_el = _cut_angles(elev_angles_deg)

    az = np.radians(az_elev_deg)
    az_rhat = np.stack(
        [
            np.cos(az) * np.cos(t_az),
            np.cos(az) * np.sin(t_az),
            np.full_like(t_az, np.sin(az)),
        ],
        axis=-1,
    )
    el = np.radians(elev_az_deg)
    el_rhat = np.stack(
        [np.cos(el) * np.cos(t_el), np.sin(el) * np.cos(t_el), np.sin(t_el)], axis=-1
    )

    # Concatenated, not stacked: refinement can leave the two cuts with
    # different sample counts, and one evaluation over (n_az + n_el, 3) is
    # the same work as two.
    rhat = np.concatenate([az_rhat, el_rhat], axis=0)
    mag2 = _mag2_at_directions(out, rhat, mid=mid, dr=dr, i_mid=i_mid)
    if bool(out.get("ground", False)):
        mag2 = np.where(rhat[..., 2] < 0.0, 0.0, mag2)

    with np.errstate(divide="ignore"):
        dbi = 10.0 * np.log10(np.maximum(norm * mag2, 0.0))
    dbi = np.where(np.isfinite(dbi), dbi, _CUT_FLOOR_DBI)
    cuts = {
        "az_elev_deg": float(az_elev_deg),
        "elev_az_deg": float(elev_az_deg),
        "n_dir": _CUT_N_DIR,
        "floor_dbi": _CUT_FLOOR_DBI,
        "azimuth": [round(float(v), 3) for v in dbi[: len(t_az)]],
        "elevation": [round(float(v), 3) for v in dbi[len(t_az) :]],
    }
    if az_angles_deg is not None:
        cuts["az_angles_deg"] = [round(float(a), 6) for a in np.degrees(t_az)]
    if elev_angles_deg is not None:
        cuts["elev_angles_deg"] = [round(float(a), 6) for a in np.degrees(t_el)]
    return cuts


# Server-side cuts sources (issue #551): solve_id → the pre-extracted data
# _pattern_cuts needs, so /cuts and the ws cuts channel can recompute cut
# traces from a ~100-byte request instead of a re-uploaded solve body
# (~92 B/segment on the wire — 60 KB+ for the dense meshes where cut-dial
# latency is actually felt, times one request per pinned ghost).
#
# The id is ADVISORY, never authoritative: on a miss (server restart,
# eviction) the server answers 404 / ok=false and the client falls back to
# the stateless full-body request. Pins deliberately outlive sessions, so
# ghosts must never silently die with this cache. Assumes a single server
# process (true for uvicorn and the Docker image); a multi-worker deployment
# would need sticky routing or a shared store.
_CUTS_SRC_CACHE: "OrderedDict[str, dict]" = OrderedDict()
# Entries hold the numpy moment set at ~64 B/segment, so even 64 entries of
# a 4k-segment mesh bound the cache near ~16 MB.
_CUTS_SRC_CACHE_MAX = 64

# The scalar/ground fields _pattern_cuts reads besides the moment set.
_CUTS_SRC_FIELDS = (
    "k_meas_m_inv",
    "ground",
    "ground_eps_r",
    "ground_eps_im",
    "ground_terrain",
    "measurement_freq_mhz",
    "directivity_norm",
)


def _remember_cuts_source(solve_id: str, out: dict) -> None:
    """Store (or LRU-refresh) the cuts source for a solve response. Never
    raises — a response the cuts math can't digest simply isn't cached and
    the client's full-body fallback still works."""
    if solve_id in _CUTS_SRC_CACHE:
        _CUTS_SRC_CACHE.move_to_end(solve_id)
        return
    if float(out.get("directivity_norm") or 0.0) <= 0.0 or not out.get("wires"):
        return
    try:
        mid, dr, i_mid = _moment_segments(out)
    except Exception:
        _logger.exception("cuts-source extraction failed; solve_id not cached")
        return
    src = {k: out[k] for k in _CUTS_SRC_FIELDS if k in out}
    src["_mid"], src["_dr"], src["_i_mid"] = mid, dr, i_mid
    _CUTS_SRC_CACHE[solve_id] = src
    while len(_CUTS_SRC_CACHE) > _CUTS_SRC_CACHE_MAX:
        _CUTS_SRC_CACHE.popitem(last=False)


def _cuts_from_source(
    solve_id: str,
    az_elev_deg: float,
    elev_az_deg: float,
    az_angles_deg=None,
    elev_angles_deg=None,
) -> dict | None:
    """Cuts computed from the server-side source for `solve_id`, or None on
    a cache miss (callers map that to 404 / ok=false). Only sources with a
    positive norm are ever cached, so None never means "can't support cuts"
    here.

    The cached source is the moment set — angle-independent by construction
    — so a refinement request for extra angles against a live solve_id costs
    one far-field evaluation and no solve at all. That is why cut refinement
    (issue #744) does NOT take a lane turn the way sweep refinement does:
    there is no solve to serialize, only the existing pattern re-evaluated
    at more directions, on the same no-lane latest-wins channel cut-dial
    drags already use."""
    src = _CUTS_SRC_CACHE.get(solve_id)
    if src is None:
        return None
    _CUTS_SRC_CACHE.move_to_end(solve_id)
    return _pattern_cuts(
        src,
        az_elev_deg,
        elev_az_deg,
        mid=src["_mid"],
        dr=src["_dr"],
        i_mid=src["_i_mid"],
        az_angles_deg=az_angles_deg,
        elev_angles_deg=elev_angles_deg,
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
    terrain_pec: bool = False,
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

    mag2 = _mag2_at_directions(
        out, rhat, mid=mid, dr=dr, i_mid=i_mid, terrain_pec=terrain_pec
    )

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

# Per-frequency sweep impedance cache (issue #744). /sweep deliberately
# bypasses _SOLVE_CACHE — a sweep point is a Z, not a whole solve response,
# and caching 41 full responses per drag would blow that cache out — so
# until now every sweep re-solved every point from scratch. Adaptive
# refinement makes that expensive in a new way: it re-visits the SAME design
# repeatedly, adding a handful of frequencies each round, and would
# otherwise pay for the whole grid again on each re-dwell.
#
# Keyed by (design, freq): the design half is _canonical_solve_key of the
# request MINUS the freq list, so it inherits the blocklist — refinement
# metadata and cut angles don't shred it, while any genuine physics field
# (including one added next month) invalidates by default. That makes
# server-side invalidation the same object as the client's #692 signature,
# not a parallel hand-maintained list.
#
# ASYMMETRIC on purpose: every sweep WRITES, only a refinement request READS.
#   - Writing from every sweep keeps entries fresh, so what refinement reads
#     was produced by the very base sweep it is refining. A read-through base
#     sweep would instead let a stale entry (a user design edited on disk
#     under an unchanged request key — the same exposure _SOLVE_CACHE has)
#     survive in the PRIMARY curve, with no way to force a re-solve.
#   - Not reading on the base sweep also keeps the endpoint's compute path
#     for a plain sweep exactly what it was, which the #382 lane tests
#     depend on: two sessions issuing the same sweep concurrently must both
#     compute (a cross-session read-through would answer one from cache and
#     the lane's per-session serialization would go untested).
# The acceptance criterion this cache exists for — "refinement requests hit
# the cache on re-dwell" — is satisfied either way, since the refinement
# plan is deterministic in the settled sweep.
#
# Entries are 2–4 floats plus per-feed lists; 4096 of them is well under a
# megabyte, and holds ~50 full sweeps of design history.
_SWEEP_Z_CACHE: "OrderedDict[tuple[str, int], tuple]" = OrderedDict()
_SWEEP_Z_CACHE_MAX = 4096
# issue #763: which session last wrote each design's entries. A base sweep
# may read the cache ONLY back for its own writes (see
# _base_sweep_may_read_cache) — this map is what "its own" means.
_SWEEP_Z_WRITER: dict[str, str] = {}
# Hit/miss counters — observability, and the only honest way to assert "this
# request performed zero engine solves" in a test.
_SWEEP_Z_STATS = {"hits": 0, "misses": 0}

# Frequencies land back from JSON as the exact float the client sent, but
# quantise anyway (same reasoning as _CACHE_FLOAT_QUANT): a re-plan that
# recomputes 28.470000000000002 must still hit.
_SWEEP_FREQ_QUANT = 1e-9


def _sweep_design_key(req: dict) -> str:
    """Cache namespace for a sweep request: everything about the design
    except which frequencies were asked for.

    ``measurement_freq_mhz`` stays IN the key even though the sweep
    overrides the frequency per point. It is a request field, and the house
    rule for this cache key is "extra miss beats wrong hit" — a builder that
    reads the measurement frequency for anything but the excitation would
    otherwise be silently mis-cached.
    """
    return _canonical_solve_key({k: v for k, v in req.items() if k != "freqs_mhz"})


def _base_sweep_may_read_cache(req: dict, design_key: str) -> bool:
    """Issue #763: opt-in read-through for BASE sweeps, so a knob scrub
    A→B→A stops re-solving the ~41 points the cache already holds.

    Three gates, each preserving a documented ``_SWEEP_Z_CACHE`` property:

    * ``reuse_cached_z`` — the client asserts freshness for its own
      session (it knows whether the design changed since it last swept);
    * same-session writer — a session only ever reads back its OWN
      writes, so two sessions issuing the same sweep still both compute
      (the #382 lane contract stays testable);
    * never for user designs — the edited-on-disk exposure stays closed
      server-side, whatever the client asserts.
    """
    if not req.get("reuse_cached_z"):
        return False
    geometry = str(req.get("geometry", ""))
    if geometry.startswith("user.") or geometry.startswith("@"):
        return False
    session, _gen = _lane_key(req)
    if session is None:
        return False
    return _SWEEP_Z_WRITER.get(design_key) == session


def _sweep_z_get(design_key: str, freq: float) -> tuple | None:
    key = (design_key, round(freq / _SWEEP_FREQ_QUANT))
    hit = _SWEEP_Z_CACHE.get(key)
    if hit is None:
        _SWEEP_Z_STATS["misses"] += 1
        return None
    _SWEEP_Z_CACHE.move_to_end(key)
    _SWEEP_Z_STATS["hits"] += 1
    return hit


def _sweep_record(freq: float, value: tuple, solver_name: str) -> dict:
    """One NDJSON sweep line from a cache value. Per-feed fields stay OMITTED
    for single-feed geometries — the frontend allocates its per-feed buffers
    on first sight of them."""
    z_re, z_im, feeds_re, feeds_im = value
    record = {
        "freq_mhz": freq,
        "z_re": z_re,
        "z_im": z_im,
        "solver": solver_name,
    }
    if feeds_re is not None:
        record["feeds_z_re"] = feeds_re
        record["feeds_z_im"] = feeds_im
    return record


def _sweep_z_put(design_key: str, freq: float, value: tuple) -> None:
    _SWEEP_Z_CACHE[(design_key, round(freq / _SWEEP_FREQ_QUANT))] = value
    _SWEEP_Z_CACHE.move_to_end((design_key, round(freq / _SWEEP_FREQ_QUANT)))
    while len(_SWEEP_Z_CACHE) > _SWEEP_Z_CACHE_MAX:
        _SWEEP_Z_CACHE.popitem(last=False)


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
# bearing — preferring "extra miss" over "wrong hit". The client keys its
# background-analysis effects the same way (frontend/src/lib/
# solveSignature.ts, issue #692) — keep the metadata entries in lockstep.
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
        # Adaptive-refinement marker (issue #744): selects the sweep's lane
        # kind and nothing else. It MUST be blocklisted — a refinement
        # request asks for extra frequencies of the same design, so it has
        # to land on the same per-freq cache entries a base sweep would.
        "_refine",
        # Base-sweep read-through opt-in (issue #763): pure cache policy —
        # a refinement request without the flag must land on the same
        # per-freq entries the flagged base sweep wrote.
        "reuse_cached_z",
        # Polar-cut angles (issue #547): cuts are attached per-request AFTER
        # the cache, so the cached entry is angle-independent by design.
        # Leaving these in the key meant every cut-dial drag silently
        # invalidated cache hits for all subsequent knob scrubs.
        "az_elev_deg",
        "elev_az_deg",
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

    canon = quantise(req)
    # The RESOLVED backend, not the requested one: a solver the machine
    # can't serve falls back to momwire, and for NEC-5 availability is a
    # runtime $NEC5_EXE probe that can differ between requests — caching
    # under the requested name would serve a momwire fallback as a NEC-5
    # answer (or vice versa) after the environment changes.
    backend = _external_backend(req)
    canon["_resolved_solver"] = (
        "momwire"
        if backend is None
        else ("pynec" if backend is pynec_backend else "nec5")
    )
    blob = json.dumps(canon, sort_keys=True, default=str).encode()
    return hashlib.blake2b(blob, digest_size=16).hexdigest()


def _shed(fn, *args, **kwargs):
    """Threadpool shim for every solve-shaped dispatch: format the error
    while the traceback still exists, then drop the frame chain before the
    exception crosses the thread boundary.

    An exception that propagates through anyio's worker threads is retained
    (traceback, frames, and every array those frames reference) for the
    life of the process — gc.collect() doesn't release it and neither does
    reusing the pool. One failed benchmark-mesh solve pinned 5.9 GiB that
    way in the #382 acceptance pass, after which even a 330 MB sinusoidal
    solve couldn't allocate. Shedding the frames costs the debug traceback
    in the server log; the user-facing message (which needs the traceback
    for the user-design file hint) is pre-formatted here and carried on the
    exception for format_solve_error to find.
    """
    try:
        return fn(*args, **kwargs)
    except BaseException as exc:
        if not isinstance(exc, momwire.SolveAborted):
            exc._formatted_solve_error = user_designs.format_solve_error(exc)
        exc.__traceback__ = None
        exc.__context__ = None
        exc.__cause__ = None
        raise exc


def _external_backend(req: dict):
    """The non-momwire backend module a request selects (pynec / nec5), or
    None for the momwire path. Availability is re-checked here per request;
    a requested-but-unavailable engine falls back to momwire — the existing
    pynec contract, which the nec5 entry (a runtime $NEC5_EXE probe, issue
    #825) inherits."""
    s = req.get("solver")
    if s == "pynec" and pynec_backend.HAVE_PYNEC:
        return pynec_backend
    if s == "nec5" and nec5_backend.have_nec5():
        return nec5_backend
    return None


def _solve_uncached(req: dict, cancel=None) -> dict:
    geometry = req.get("geometry", next(iter(EXAMPLES)))
    backend = _external_backend(req)
    _check_solve_size(req, use_pynec=backend is not None)
    if backend is not None:
        # External-engine start-gate only: a request already superseded before
        # its solve begins dies for free here; the native solve is one opaque
        # call with no mid-solve abort (PyNEC in-process, NEC-5 a subprocess),
        # so an in-flight one runs to completion (as today).
        if cancel is not None:
            cancel.raise_if_cancelled()
        out = backend.solve(req)
        out["solver"] = "pynec" if backend is pynec_backend else "nec5"
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
        # solve_id (issue #551): the canonical key itself — already an opaque
        # 128-bit blake2b digest, so it doubles as the advisory cuts-cache
        # handle the client sends back instead of the full solve body. The
        # hit path re-remembers so an evicted cuts source repopulates from
        # the (larger) solve cache without a re-solve.
        out["solve_id"] = key
        _remember_cuts_source(key, out)
        _attach_request_cuts(out, req)
        return out
    out = _solve_uncached(req, cancel=cancel)
    out["cache_hit"] = False
    out["solve_id"] = key
    _SOLVE_CACHE[key] = deepcopy(out)
    while len(_SOLVE_CACHE) > _SOLVE_CACHE_MAX:
        _SOLVE_CACHE.popitem(last=False)
    _remember_cuts_source(key, out)
    # After the cache store: cuts depend on the request's cut angles, so the
    # cached entry stays angle-independent and every request gets fresh cuts.
    _attach_request_cuts(out, req)
    return out


def _attach_request_cuts(out: dict, req: dict) -> None:
    """Attach the request's polar-chart cuts to a solve response (issue
    #547). Never lets a cuts failure break the solve — the frontend treats
    a missing `cuts` field as "compute unavailable"."""
    try:
        cuts = _pattern_cuts(
            out,
            float(req.get("az_elev_deg", 15.0)),
            float(req.get("elev_az_deg", 0.0)),
        )
    except Exception:
        _logger.exception("pattern cuts failed; solve response ships without them")
        cuts = None
    if cuts is not None:
        out["cuts"] = cuts


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
    ext_backend = _external_backend(req)
    use_pynec = ext_backend is not None
    solver_name = req.get("solver") if use_pynec else "momwire"
    # Admission by cost (issue #382), before the stream starts: over-cap
    # matrix or point count → clean 413 (as before); a dense-family batch on
    # a benchmark-class mesh → 403 unless the request carries the client
    # gate's "Solve anyway" approval.
    _refuse_or_withhold(
        _admit(req, kind="sweep", use_pynec=use_pynec, points=len(freqs)), req
    )
    session, lane_gen = _lane_key(req)
    # Adaptive refinement (issue #744) rides this same endpoint — the freq
    # list has always been caller-chosen — but takes its OWN lane kind. If it
    # shared "sweep", lane.SAME_KIND_SUPERSEDES would have the refinement
    # request kill the base sweep whose curve it is refining, regardless of
    # generation. It also sorts below "sweep" so a genuinely new sweep goes
    # first; refinement runs mostly out of the per-freq cache anyway.
    lane_kind = "sweep_refine" if req.get("_refine") else "sweep"
    # (design, freq) impedance cache: refinement reads it (a re-dwell asks
    # for the same deterministic plan it asked for last time), every sweep
    # writes it. See _SWEEP_Z_CACHE for why the read side is asymmetric.
    design_key = _sweep_design_key(req)
    read_cache = lane_kind == "sweep_refine" or _base_sweep_may_read_cache(
        req, design_key
    )
    # Every sweep writes the cache, so record the writing session (checked
    # first, stamped second: another session's scrub must miss THIS time
    # and only start hitting once its own sweep has written).
    _writer_session, _ = _lane_key(req)
    if _writer_session is not None:
        _SWEEP_Z_WRITER[design_key] = _writer_session
        while len(_SWEEP_Z_WRITER) > _SWEEP_Z_CACHE_MAX:
            _SWEEP_Z_WRITER.pop(next(iter(_SWEEP_Z_WRITER)))
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
                cached = _sweep_z_get(design_key, f) if read_cache else None
                superseded_mid_point = False
                if cached is None:
                    try:
                        # One lane turn per point: a queued live solve gets
                        # the lane at the next point boundary. PyNEC has no
                        # mid-solve abort, so a supersession trips the token
                        # but the point runs out; the post-turn check stops
                        # the stream there. A cache hit takes no turn at all
                        # — there is no engine work to serialize.
                        async with _LANES.turn(session, lane_kind, lane_gen) as token:
                            if is_multifeed:
                                primary, feeds_z = await run_in_threadpool(
                                    _shed, ext_backend._sweep_at_multifeed, req, f
                                )
                                cached = (
                                    float(primary.real),
                                    float(primary.imag),
                                    [float(z_.real) for z_ in feeds_z],
                                    [float(z_.imag) for z_ in feeds_z],
                                )
                            else:
                                z = await run_in_threadpool(
                                    _shed, ext_backend._sweep_at, req, f
                                )
                                cached = (float(z.real), float(z.imag), None, None)
                            superseded_mid_point = token.cancelled
                    except Superseded:
                        return
                    except Exception as exc:  # noqa: BLE001 — solver can fail per point
                        yield (
                            json.dumps(
                                {
                                    "error": user_designs.format_solve_error(exc),
                                    "solver": solver_name,
                                }
                            )
                            + "\n"
                        )
                        return
                    # Store only a point that ran to completion: a superseded
                    # PyNEC point still produced a real Z (no mid-solve
                    # abort), so it is cached like any other.
                    _sweep_z_put(design_key, f, cached)
                yield json.dumps(_sweep_record(f, cached, solver_name)) + "\n"
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
                # Solve only what the (design, freq) cache doesn't already
                # hold. On a refinement round that is the handful of new
                # frequencies; on a re-dwell of an unchanged design it is
                # nothing at all, and the chunk streams without ever taking
                # a lane turn.
                known = {
                    f: (_sweep_z_get(design_key, f) if read_cache else None)
                    for f in chunk
                }
                pending = [f for f, v in known.items() if v is None]
                if pending:
                    t0 = time.perf_counter()
                    try:
                        # One lane turn per chunk; the token reaches the
                        # solver's checkpoints, so a knob drag (newer
                        # generation) or a dropped connection (the watcher)
                        # aborts THIS chunk in ~ms instead of after minutes
                        # on a benchmark mesh.
                        async with _LANES.turn(session, lane_kind, lane_gen) as token:
                            async with cancel_on_disconnect(request, token):
                                sweep_result = await run_in_threadpool(
                                    _shed, sweep_fn, req, pending, cancel=token
                                )
                    except (Superseded, momwire.SolveAborted):
                        return
                    except Exception as exc:  # noqa: BLE001 — a chunk can fail honestly
                        # e.g. an approved poor-match combo whose dense fill
                        # can't allocate: end the stream with the cause
                        # instead of tearing the NDJSON connection down
                        # mid-line.
                        yield (
                            json.dumps(
                                {
                                    "error": user_designs.format_solve_error(exc),
                                    "solver": solver_name,
                                }
                            )
                            + "\n"
                        )
                        return
                    # Multi-feed sweeps (bowtie array) return a 4-tuple with
                    # per-feed Z appended. Everything else stays on the
                    # original 2-tuple shape; the legacy z_re / z_im fields
                    # always carry the primary feed for back-compat.
                    if len(sweep_result) == 4:
                        z_re, z_im, feeds_re_chunk, feeds_im_chunk = sweep_result
                    else:
                        z_re, z_im = sweep_result
                        feeds_re_chunk = feeds_im_chunk = None
                    for i, f in enumerate(pending):
                        value = (
                            z_re[i],
                            z_im[i],
                            None if feeds_re_chunk is None else feeds_re_chunk[i],
                            None if feeds_im_chunk is None else feeds_im_chunk[i],
                        )
                        known[f] = value
                        _sweep_z_put(design_key, f, value)
                    chunk_ms = (time.perf_counter() - t0) * 1000
                    # Adapt for the next chunk: target _CHUNK_TARGET_MS per
                    # batch. Per-freq cost is a weak function of chunk size
                    # (bowl curve), so this converges quickly. Timed against
                    # the SOLVED points only — cached ones cost nothing and
                    # would otherwise inflate the next chunk without bound.
                    if chunk_ms > 0:
                        per_freq_ms = chunk_ms / len(pending)
                        chunk_size = max(1, round(_CHUNK_TARGET_MS / per_freq_ms))
                for f in chunk:
                    yield json.dumps(_sweep_record(f, known[f], solver_name)) + "\n"
                start += len(chunk)

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
    backend = _external_backend(req)
    if backend is not None:
        # Start-gate only: the external solve has no mid-solve abort.
        if cancel is not None:
            cancel.raise_if_cancelled()
        res = backend.solve(req)
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
    use_pynec = _external_backend(req) is not None
    solver_name = req.get("solver") if use_pynec else "momwire"
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
                            _shed, _solve_z_only, req_n, cancel=token
                        )
            except (Superseded, momwire.SolveAborted):
                return
            except Exception as e:  # noqa: BLE001 — one-off solver failures must not abort the whole sweep; the error is noted per N
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
    """NEC's rp_card-computed gain pattern (PyNEC or NEC-5)."""
    pat_backend = _external_backend(req)
    if pat_backend is None:
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
            return await run_in_threadpool(_shed, pat_backend.pattern, req)
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
    Over a faceted terrain the fraction is NOT an efficiency — see the
    method-tag comment below — and the frontend shows the raw Δ instead.
    """
    out = solve(dict(req), cancel=cancel)
    if "directivity_norm" not in out or out["directivity_norm"] <= 0:
        return {"available": False}
    ground_on = bool(out.get("ground", False))
    pec = float(out.get("ground_eps_r", _PEC_GROUND_EPS_R)) >= 1e6 and not float(
        out.get("ground_sigma", 0.0) or 0.0
    )
    terrain_pec_norm = None
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
        # Over a faceted terrain the P_in-referenced ratio is NOT an
        # efficiency: the far field is composed per facet while the
        # impedance solve saw only the flat crest ground, so the pattern
        # integral has no obligation to match the input power (it can
        # exceed it — the frontend shows that gap as the "ledger Δ"). The
        # honest ground-loss ledger instead references the SAME facet
        # geometry with perfect-reflector media: identical image phases,
        # tilts and specular selection cancel in the ratio, leaving purely
        # the power the ground media absorb from the reflected wave.
        if out.get("ground_terrain"):
            pec_ref = dict(out)
            _compute_directivity_norm(
                pec_ref, n_theta=n_theta, n_phi=n_phi, terrain_pec=True
            )
            terrain_pec_norm = pec_ref["directivity_norm"]
            method = f"grid_terrain_{n_theta}x{n_phi}"
        else:
            method = f"grid_{n_theta}x{n_phi}"
    efficiency = float(out.get("radiation_efficiency", 1.0))
    if terrain_pec_norm is not None:
        # P_real/P_pec (norms are inverse powers; the folded-in structural
        # efficiency cancels in the ratio and is re-applied once).
        radiated = (
            efficiency * terrain_pec_norm / pattern_norm if pattern_norm > 0 else 0.0
        )
    else:
        radiated = (
            efficiency * out["directivity_norm"] / pattern_norm
            if pattern_norm > 0
            else 0.0
        )
    return {
        "available": pattern_norm > 0,
        "directivity_norm": out["directivity_norm"],
        "pattern_norm": pattern_norm,
        "method": method,
        "radiation_efficiency": efficiency,
        "radiated_fraction": radiated,
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
                return await run_in_threadpool(_shed, _norm_check, req, cancel=token)
    except (Superseded, momwire.SolveAborted):
        return {"available": False}
    except Exception as exc:  # noqa: BLE001 — the miss path is a full solve
        # An approved poor-match solve can fail honestly (e.g. the whip's
        # B-spline J tensor is a 3 GiB allocation): report it like every
        # other solve endpoint instead of a 500 (found in the #382
        # acceptance pass under ulimit -v).
        return {"available": False, "error": user_designs.format_solve_error(exc)}


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


@app.post("/schematic")
async def schematic_endpoint(req: dict):
    """Render the design's feed network as an SVG circuit schematic (#652).

    Same builder construction as the live solve, so component labels match
    the knobs on screen. No solve happens — this is build_network() plus a
    schemdraw render, cheap enough for the frontend to refetch per knob
    change. JSON (not a raw SVG response) so "this antenna has no feed
    circuit" is an answer rather than an error: the schematic view exists
    for every design and shows an empty state for the ~2/3 without a
    network.
    """
    geometry = req.get("geometry", next(iter(EXAMPLES)))
    ex = EXAMPLES.get(geometry) or next(iter(EXAMPLES.values()))
    if ex.schematic_svg is None:
        return {"available": False}
    try:
        svg = await run_in_threadpool(ex.schematic_svg, req)
    except ValueError as e:
        # Request validation (bad freq / radius) — 422 like every endpoint.
        raise HTTPException(status_code=422, detail=str(e)) from e
    except ImportError as e:
        # schemdraw missing: an install without the schematic extra. The
        # message names the pip command; surfacing it beats a 500.
        return {"available": False, "reason": str(e)}
    if svg is None:
        # build_network() returned None: a plain build_wires antenna.
        return {"available": False}
    return {"available": True, "svg": svg}


# Upload ceilings for the measured overlay (issue #595). A NanoVNA writes
# 101–1001 points (a few tens of kB); nanovna-saver's segmented sweeps reach a
# few thousand. The caps are generous multiples of that — they exist so a
# mis-picked file (a NEC deck, a CSV log, a binary) is refused by size before
# it is parsed, not to constrain real measurements.
_MEASURED_MAX_CHARS = 4_000_000
_MEASURED_MAX_POINTS = 100_000


@app.post("/measured")
async def measured_endpoint(req: dict):
    """Parse an uploaded one-port Touchstone into a measured overlay trace.

    The file is read *in the browser* and posted here as text: parsing happens
    server-side so there is exactly one Touchstone reader (issue #593's), not a
    second one transliterated into TypeScript that could disagree with the CLI
    about the same file.

    Returns the measurement as impedance versus frequency — the same shape the
    solve and ``/sweep`` responses carry — so the chart converts it to Γ at
    whatever reference the chart is showing, and a file calibrated at 75 Ω
    lands correctly on a 50 Ω chart with no special case.

    Nothing is stored: the trace lives in the client's state, so no
    user-uploaded file is retained server-side (this endpoint is also the one
    the hosted instance exposes to arbitrary visitors).
    """
    from antennaknobs.measured import parse_measured

    text = req.get("text") or ""
    name = str(req.get("name") or "measured.s1p")
    if not isinstance(text, str) or not text.strip():
        raise HTTPException(status_code=422, detail="empty measurement file")
    if len(text) > _MEASURED_MAX_CHARS:
        raise HTTPException(
            status_code=413,
            detail=f"measurement file is too large "
            f"({len(text) // 1024} kB; limit {_MEASURED_MAX_CHARS // 1024} kB)",
        )
    label = Path(name).stem or "measured"
    try:
        trace = await run_in_threadpool(parse_measured, text, label=label)
    except ValueError as e:
        # Bad header, wrong port count, ragged records — the parser's messages
        # already name the problem; surface them verbatim as a 422.
        raise HTTPException(status_code=422, detail=str(e)) from e
    if trace.freqs.size > _MEASURED_MAX_POINTS:
        raise HTTPException(
            status_code=413,
            detail=f"measurement has {trace.freqs.size} points "
            f"(limit {_MEASURED_MAX_POINTS})",
        )
    z = trace.impedance
    return {
        "label": trace.label,
        "z0_file": trace.z0,
        "freqs_mhz": [float(f) for f in trace.freqs],
        "z_re": [float(v) for v in z.real],
        "z_im": [float(v) for v in z.imag],
    }


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


@app.post("/cuts")
def cuts_endpoint(req: dict):
    """Recompute the two polar-chart cuts at new cut angles (issue #547).

    Two request shapes:

    - ``{solve_id, az_elev_deg, elev_az_deg}`` (issue #551): ~100-byte fast
      path against the server-side cuts-source cache. 404 on an unknown id
      (restart, eviction) — the client then retries with the full body.
    - ``{solve, az_elev_deg, elev_az_deg}``: stateless backstop — the body
      carries the fields of a previously returned solve response under
      ``solve`` (wires + k_meas_m_inv + ground constants + directivity_norm
      — the client already holds all of them).

    Either shape may add ``az_angles_deg`` / ``elev_angles_deg`` (issue
    #744) to sample that cut at an explicit, possibly non-uniform, list of
    angles instead of the uniform circle; the response then echoes the
    parameterisation it used.

    Returns the same ``cuts`` object the live solve attaches. Sync def →
    FastAPI threadpool, so a big-mesh cut (~100 ms at 4k segments) never
    blocks the event loop.
    """
    az_angles = req.get("az_angles_deg")
    elev_angles = req.get("elev_angles_deg")
    solve_out = req.get("solve")
    if not isinstance(solve_out, dict):
        solve_id = req.get("solve_id")
        if not (isinstance(solve_id, str) and solve_id):
            raise HTTPException(status_code=400, detail="missing solve response body")
        try:
            cuts = _cuts_from_source(
                solve_id,
                float(req.get("az_elev_deg", 15.0)),
                float(req.get("elev_az_deg", 0.0)),
                az_angles_deg=az_angles,
                elev_angles_deg=elev_angles,
            )
        except (KeyError, TypeError, ValueError) as e:
            raise HTTPException(status_code=400, detail=f"bad cuts request: {e}") from e
        if cuts is None:
            raise HTTPException(status_code=404, detail="unknown solve_id")
        return cuts
    try:
        cuts = _pattern_cuts(
            solve_out,
            float(req.get("az_elev_deg", 15.0)),
            float(req.get("elev_az_deg", 0.0)),
            az_angles_deg=az_angles,
            elev_angles_deg=elev_angles,
        )
    except (KeyError, TypeError, ValueError) as e:
        raise HTTPException(status_code=400, detail=f"bad cuts request: {e}") from e
    if cuts is None:
        raise HTTPException(
            status_code=400, detail="solve response cannot support cuts"
        )
    return cuts


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
                    _shed, ex.far_field_metrics, req, cancel=token
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


# ---------------------------------------------------------------------------
# Streamed /optimize (issue #773): one endpoint, two representations, chosen
# by Accept. `text/event-stream` reports the run per eval; anything else (and
# no Accept at all) gets today's single JSON object, unchanged. Validation,
# the hosted caps and the _shed dispatch are shared — the stream changes only
# how a run is *reported*, never what it computes.
# ---------------------------------------------------------------------------

_SSE_MEDIA_TYPE = "text/event-stream"

# Idle gap before the stream writes a comment frame. The write is what
# discovers a silently-vanished client (see _sse_progress_body), and it also
# keeps a proxy from reaping a connection that is merely thinking. Shorter
# than an eval on any mesh worth streaming, so a live run's own progress
# frames usually pre-empt it.
_SSE_KEEPALIVE_S = 5.0

# create_task alone leaves the loop holding a weak reference: a producer whose
# consumer has already been finalised would be collectable mid-run.
_OPT_STREAM_TASKS: set[asyncio.Task] = set()


def _sse_frame(kind: str, data: dict) -> str:
    """One SSE frame, contract C2's wire form.

    The trailing BLANK LINE is load-bearing: an SSE parser emits on "\\n\\n",
    so a terminal frame written without it sits in the client's buffer and is
    never delivered. `default=str` is a fuse, not a converter — every payload
    this endpoint builds is already plain floats/ints/strings, and a stream
    must not die mid-flight over one odd value in a user design's metrics.
    """
    return f"event: {kind}\ndata: {json.dumps(data, default=str)}\n\n"


def _sse_response(gen) -> StreamingResponse:
    return StreamingResponse(
        gen,
        media_type=_SSE_MEDIA_TYPE,
        # no-store: progress is never replayable. X-Accel-Buffering: a
        # buffering reverse proxy would hold every frame until the run ended,
        # which is precisely what streaming exists to avoid.
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


def _sse_terminal_only(kind: str, data: dict) -> StreamingResponse:
    """A stream that is nothing but its one terminal event — the SSE form of a
    request rejected before any work started."""

    async def gen():
        yield _sse_frame(kind, data)

    return _sse_response(gen())


async def _next_event(events):
    """`anext` with exhaustion as a value, so the wait below can hold the
    pending pull in a Future without StopAsyncIteration crossing it."""
    try:
        return await events.__anext__()
    except StopAsyncIteration:
        return None


async def _sse_progress_body(
    request: Request, stream: ProgressStream, drive
) -> AsyncIterator[str]:
    """Frame `stream`'s events as SSE for as long as the client is there.

    Starts `drive` (the producer, an argument-free coroutine function) when
    the body starts, and closes the stream on the way out however the body
    ends — terminal event, disconnect, cancellation. Closing is what stops the
    run: the producer's next publish() raises, unwinding the optimiser at its
    next eval instead of computing solves nobody will read.

    The idle tick is not decoration. This loop parks awaiting the next event
    for as long as one MoM solve takes, and Starlette only finalises a
    streaming body at its next send — so without a probe, a browser closed at
    eval 3 would keep burning solves until eval 4 landed. The tick both polls
    the receive channel and writes a comment, so either half alone catches it.
    """
    task = asyncio.create_task(drive())
    _OPT_STREAM_TASKS.add(task)
    task.add_done_callback(_OPT_STREAM_TASKS.discard)
    events = stream.events().__aiter__()
    pending = None
    try:
        while True:
            if pending is None:
                # Carried across ticks rather than re-issued per tick:
                # cancelling an __anext__ tears the iterator's generator down,
                # so the pull must never be the thing that times out.
                pending = asyncio.ensure_future(_next_event(events))
            done, _ = await asyncio.wait({pending}, timeout=_SSE_KEEPALIVE_S)
            if not done:
                if await request.is_disconnected():
                    return
                yield ": keepalive\n\n"
                continue
            event = pending.result()
            pending = None
            if event is None:
                return  # closed without a terminal event: the consumer left
            yield _sse_frame(event.kind, event.data)
    finally:
        if pending is not None:
            pending.cancel()
        stream.close()


@app.post("/optimize")
async def optimize_endpoint(req: dict, request: Request):
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

    With `Accept: text/event-stream` the same run is streamed instead: one
    `progress` event per eval, then exactly one terminal `result` (that same
    JSON object) or `error`. Every other Accept keeps the single-response form.
    """
    from .optimize import OBJECTIVES, optimize as _optimize

    wants_sse = _SSE_MEDIA_TYPE in (request.headers.get("accept") or "")

    def _reject(payload: dict):
        """One rejection, rendered either way: the JSON path returns exactly
        the payload it always did, the stream turns it into its one terminal
        event. Neither ever emits progress — nothing ran."""
        if not wants_sse:
            return payload
        return _sse_terminal_only("error", {"detail": payload["error"]})

    opt = req.get("optimize") or {}
    free = opt.get("free") or []
    if not free:
        return _reject({"error": "select at least one knob to vary"})
    objective = opt.get("objective", "swr")
    if objective not in OBJECTIVES:
        return _reject({"error": f"unknown objective {objective!r}"})
    # #1176: surrogate seeding, off unless the client asks. Off by default
    # because it is measured neutral-to-negative from a TUNED start and only
    # decisive from a poor one — see the numbers on the issue.
    seed_surrogate = bool(opt.get("seed_surrogate", False))
    max_evals = opt.get("max_evals")
    if max_evals is not None:
        try:
            max_evals = int(max_evals)
        except (TypeError, ValueError):
            return _reject(
                {"error": f"max_evals must be an integer (got {max_evals!r})"}
            )
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
        return _reject({"geometry": geometry, "error": str(e)})

    def _run(on_progress):
        # THE dispatch, shared by both representations so _shed can never be
        # on one path and not the other: it formats the error while the
        # traceback exists and drops the frame chain before the exception
        # crosses the thread boundary (issue #382's multi-GiB retention).
        return run_in_threadpool(
            _shed,
            _optimize,
            base,
            free,
            objective,
            solve_fn=ex.momwire_solve,
            max_evals=max_evals,
            seed_surrogate=seed_surrogate,
            on_progress=on_progress,
        )

    if not wants_sse:
        try:
            result = await _run(None)
        except Exception as exc:  # noqa: BLE001 — a user design's build_wires can raise
            return {"geometry": geometry, "error": user_designs.format_solve_error(exc)}
        result["geometry"] = geometry
        return result

    stream = ProgressStream()

    async def _drive() -> None:
        try:
            # sealed() is the guarantee that the consumer can never be left
            # awaiting a producer that already died: a body that returns or
            # raises without a terminal event gets one anyway.
            with stream.sealed():
                try:
                    result = await _run(stream.publish)
                except ProgressStreamClosed:
                    # The consumer left and publish() aborted the run. Not an
                    # error — and not reportable, there is nobody to report to.
                    raise
                except Exception as exc:  # noqa: BLE001 — user design build_wires
                    stream.fail(user_designs.format_solve_error(exc))
                    return
                result["geometry"] = geometry
                stream.finish(result)
        except ProgressStreamClosed:
            pass

    return _sse_response(_sse_progress_body(request, stream, _drive))


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
                "default_freq": ex.default_freq,
                "default_design_freq": ex.default_design_freq,
                "default_backend": ex.default_backend,
                "requires_backends": (
                    list(ex.requires_backends)
                    if ex.requires_backends is not None
                    else None
                ),
                "backend_restriction": ex.backend_restriction,
                "has_stepped_radius_junction": ex.has_stepped_radius_junction,
                "has_buried_wire": ex.has_buried_wire,
                "converged_feed_suggested": ex.converged_feed_suggested,
                "ground_requirement": ex.ground_requirement,
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


@app.get("/capabilities")
def capabilities_endpoint():
    """Backend feature availability the frontend reads once on mount.

    Kept separate from /examples (the design catalog, re-fetched on every
    trust action) since capabilities are server-static. `have_pynec`: PyNEC
    is an optional backend (needs the pynec-accel package), and when it's
    absent the UI must not offer it — otherwise the /ws solve silently falls
    back to momwire (#429). `terrain_presets`: the self-describing terrain
    preset catalog (issue #560) the frontend renders its knob panel from, so
    a Python-only preset needs no TypeScript. `backends`: the same treatment
    for the solver roster (issue #628) — labels, order, ground support, knob
    schemas and panel hints, so registering a solver in the adapter's
    `_BACKENDS` makes it appear in the UI with no TypeScript either. New
    capability flags (mesh-size caps, version) belong here too.

    Both rosters are computed per request, not at import: HAVE_PYNEC is
    monkeypatched in tests and the PyNEC roster entry must follow it.
    `have_pynec` stays for compatibility — the roster's membership is what
    the current frontend gates on.
    """
    from .adapter import (
        axis_value_labels,
        backend_aliases,
        backend_roster,
        composition_axes,
        default_slots,
        model_option_specs,
        soil_presets_schema,
        soil_ranges_schema,
        terrain_presets_schema,
    )

    return {
        "have_pynec": pynec_backend.HAVE_PYNEC,
        "backends": backend_roster(
            have_pynec=pynec_backend.HAVE_PYNEC,
            have_nec5=nec5_backend.have_nec5(),
        ),
        "model_option_specs": model_option_specs(),
        "backend_aliases": backend_aliases(),
        "composition_axes": composition_axes(),
        "axis_value_labels": axis_value_labels(),
        "default_slots": default_slots(),
        "terrain_presets": terrain_presets_schema(),
        "soil_presets": soil_presets_schema(),
        "soil_ranges": soil_ranges_schema(),
    }


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
    # Cuts sidecar (issue #551): tiny `{_kind:"cuts", solve_id, angles}`
    # messages ride this same socket (warm ws was ~2× cheaper than HTTP
    # through the tunnel) and are answered from the server-side cuts-source
    # cache. Latest-wins PER SOLVE — keyed by solve_id — because one cut-dial
    # change legitimately needs cuts for the live trace AND every pinned
    # ghost; a single-slot mailbox would let the last-sent ghost starve the
    # others. Newer angles for the same solve overwrite the queued entry.
    cuts_box: dict[str, dict] = {}
    cuts_newer = asyncio.Event()
    # Two tasks send on this socket (solver loop + cuts worker); ws.send_text
    # isn't safe to interleave, so every send takes this lock.
    send_lock = asyncio.Lock()
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
                if req.get("_kind") == "cuts":
                    # Cuts request: route to the sidecar. Deliberately does
                    # NOT touch the solve mailbox, the cancel token, or the
                    # session lane — a cut-dial drag must never preempt a
                    # running solve.
                    sid = req.get("solve_id")
                    if isinstance(sid, str) and sid:
                        # Latest-wins per solve — EXCEPT that a refinement
                        # request (issue #744) gets its own slot. It asks
                        # for a different thing (the same dial angles at
                        # more sample directions), so squashing it against
                        # a dial drag would lose it every time the user is
                        # still moving.
                        refined = (
                            req.get("az_angles_deg") is not None
                            or req.get("elev_angles_deg") is not None
                        )
                        cuts_box[f"{sid}|{int(refined)}"] = req
                        cuts_newer.set()
                    continue
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
            cuts_newer.set()  # same for the cuts worker

    async def cuts_worker() -> None:
        # Drains the per-solve cuts box in arrival order. Each computation is
        # small (~1 ms typical, ~100 ms at 4k segments) but still runs in the
        # threadpool so a big-mesh cut never blocks the event loop — and by
        # extension the reader's latest-wins squashing.
        while True:
            await cuts_newer.wait()
            cuts_newer.clear()
            while cuts_box:
                if closed.is_set():
                    return
                slot = next(iter(cuts_box))
                creq = cuts_box.pop(slot)
                sid = creq["solve_id"]
                az_angles = creq.get("az_angles_deg")
                elev_angles = creq.get("elev_angles_deg")
                resp: dict = {
                    "_kind": "cuts",
                    "solve_id": sid,
                    "az_elev_deg": creq.get("az_elev_deg"),
                    "elev_az_deg": creq.get("elev_az_deg"),
                    # Echoed so the client can tell a refinement reply from a
                    # plain dial reply for the same solve and angles.
                    "refined": slot.endswith("|1"),
                }
                try:
                    cuts = await run_in_threadpool(
                        _cuts_from_source,
                        sid,
                        float(creq.get("az_elev_deg", 15.0)),
                        float(creq.get("elev_az_deg", 0.0)),
                        az_angles,
                        elev_angles,
                    )
                except Exception:  # junk angles must not kill the socket; logged below, which BLE001 permits
                    _logger.exception("ws cuts request failed")
                    cuts = None
                # Unknown id (restart/eviction) or junk request → ok:false;
                # the client falls back to the stateless POST /cuts.
                resp["ok"] = cuts is not None
                if cuts is not None:
                    resp["cuts"] = cuts
                if slot in cuts_box:
                    # Newer angles for this solve arrived while we computed —
                    # skip the doomed send; the fresh response supersedes it.
                    continue
                if closed.is_set() or ws.client_state != WebSocketState.CONNECTED:
                    return
                try:
                    async with send_lock:
                        await ws.send_text(json.dumps(resp))
                except (WebSocketDisconnect, RuntimeError):
                    return
            if closed.is_set():
                return

    reader_task = asyncio.create_task(reader())
    cuts_task = asyncio.create_task(cuts_worker())
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
                        result = await run_in_threadpool(
                            _shed, solve, req, cancel=token
                        )
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
                async with send_lock:
                    await ws.send_text(json.dumps(result))
            except (WebSocketDisconnect, RuntimeError):
                return
    finally:
        reader_task.cancel()
        cuts_task.cancel()


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
    # One line of staleness signal (#733): the mount is unconditional, so a
    # source checkout serves whatever bundle was last built — which can trail
    # frontend/src by days with no other symptom than "my change isn't
    # showing up". The build time in the log gives that failure a timestamp.
    _index = _FRONTEND_DIR / "index.html"
    if _index.is_file():
        _built = datetime.fromtimestamp(_index.stat().st_mtime, tz=timezone.utc)
        logging.getLogger(__name__).info(
            "serving frontend bundle built %s (%s)",
            _built.strftime("%Y-%m-%d %H:%M UTC"),
            _FRONTEND_DIR,
        )
    app.mount("/", StaticFiles(directory=_FRONTEND_DIR, html=True), name="frontend")

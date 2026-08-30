"""momwire#524 phase 2 — designed near-interface evaluation of the
transmitted family {U_T, V_T, W_T, dzW_T} (+ the two auxiliary surfaces
{dzpV_T = d2V/dz dz', dzpW_T = dW/dz'} that close the by-parts identities).

DERIVATION-NEAR-INTERFACE.md is the specification. The corner z, z' -> 0,
rho -> 0 is reached by DESIGN, not clamp:

  head [0, 1.1K]   : the shipped first-quadrant detour (`_head`) — branch
                     points + transmitted pole handled as production does;
  mid  [1.1K, 8K]  : real-axis adaptive Gauss (smooth, pole/cut-free);
  tail [8K, inf)   : rotated rays lam = LAM + t e^{+-j pi/4}. rho = 0 uses
                     one up-ray (J0 = 1); rho > 0 splits J0 into Hankel
                     halves, H1 up / H2 down. |integrand| ~ e^{-t(s+rho)/sqrt2}
                     — uniform through the corner, z'=0 and z=0 exact.

Convention gate: e^{+j omega t}, eps_t = eps_r - j sigma/(omega eps0),
asserted at import below.
"""

from __future__ import annotations

import numpy as np
from scipy.special import hankel1, hankel2

from momwire._sommerfeld_below import _adaptive_segment, _head
from momwire._sommerfeld_transmitted import (
    _ADAPT_DEPTH,
    _DETOUR,
    _GW,
    _GX,
    _bessel_j0_j1x,
    _gamma,
    k_medium,
)

KEYS = ("U", "V", "W", "dzW", "dzpV", "dzpW")
_LAM_MULT = 8.0
_RAY = np.exp(1j * np.pi / 4.0)
_MAX_RAY_PANELS = 90

# --- convention gate (every script: e^{+j omega t}, lossy k_m decays) ------
_kp_gate = 2.0 * np.pi / 42.831
_km_gate = k_medium(13.0 - 12.84j, _kp_gate)
assert _km_gate.imag < 0.0, "e^{+j omega t} broken: e^{-j k_m R} must decay"
assert abs(np.exp(-1j * _km_gate * 5.0) / 5.0) < abs(
    np.exp(-1j * _km_gate * 1.0) / 1.0
), "lossy-medium decay gate failed"


def _core(lam, z, zp, k_p, k_m):
    """The six spectral factors x (2 E lam), WITHOUT the Bessel factor.

    zp <= 0, so e^{-gamma_m |z'|} = e^{+gamma_m zp}. Stacked (6, n):
    0 U, 1 V, 2 W, 3 dzW (= -g_p W under the integral), 4 dzpV (= -g_p g_m V),
    5 dzpW (= +g_m W). Derivative bookkeeping: dz <-> -g_p, dz' <-> +g_m.
    """
    lam = np.asarray(lam, dtype=np.complex128)
    g_p = _gamma(lam, k_p)
    g_m = _gamma(lam, k_m)
    e = 2.0 * np.exp(g_m * zp - g_p * z) * lam
    u = e / (g_p + g_m)
    v = e / (k_m * k_m * g_p + k_p * k_p * g_m)
    w = (g_p - g_m) * v
    return np.stack([u, v, w, -g_p * w, -g_p * g_m * v, g_m * w])


def _ray_integral(f_core, factor, lam0, direction, scale, rtol):
    """integral of f_core(lam)*factor(lam) over lam = lam0 + t*direction,
    t in [0, inf). Geometric panels, each adaptive Gauss; stops when two
    consecutive panels contribute < rtol of the running total.

    Two length scales coexist on the ray: the 1/lambda (log-family)
    structure at scale ~lam0 near t = 0, and the e^{-t(s+rho)/sqrt2} decay
    at `scale`. Panels START at the lam0 scale and double toward the decay
    scale — starting at the decay scale under-resolves the log content
    when s + rho is tiny (measured: 44 % on dW/dln s at s = 1e-5)."""

    def ft(t):
        t = np.asarray(t, dtype=float)
        lam = lam0 + t * direction
        return f_core(lam) * factor(lam) * direction

    acc = None
    t_lo = 0.0
    step = min(0.25 * scale, lam0)
    quiet = 0
    for _ in range(_MAX_RAY_PANELS):
        t_hi = t_lo + step
        part = _adaptive_segment(ft, t_lo, t_hi, rtol, _ADAPT_DEPTH, _GX, _GW)
        acc = part if acc is None else acc + part
        ref = float(np.max(np.abs(acc)))
        # ref == 0.0: the whole ray underflows (e^{-lam_top*s} = 0 exactly
        # for large s at high-sigma LAM = 8|k_m| — probe33's sigma = 5
        # rung); consecutive all-zero panels are quiet, the tail IS zero.
        if ref == 0.0 or float(np.max(np.abs(part))) < rtol * ref:
            quiet += 1
            if quiet >= 2:
                return acc if acc is not None else part
        else:
            quiet = 0
        t_lo = t_hi
        step *= 2.0
    raise RuntimeError("rotated tail did not go quiet inside the panel budget")


def six_point(eps_t, k2, rho, z, zp, rtol=1e-10, lam_mult=_LAM_MULT):
    """The six designed integrals at ONE (rho, z, zp), z >= 0 >= zp,
    R = hypot(rho, z - zp) > 0. Returns (6,) complex."""
    k_p = float(k2)
    k_m = k_medium(complex(eps_t), k_p)
    rho, z, zp = float(rho), float(z), float(zp)
    if not (z >= 0.0 and zp <= 0.0):
        raise ValueError(f"need z >= 0 >= zp, got {(z, zp)!r}")
    s = z - zp
    if rho < 0.0 or s + rho <= 0.0:
        raise ValueError(f"need R > 0, got rho={rho!r}, s={s!r}")

    kk = max(k_p, abs(k_m))
    a_head = 1.1 * kk
    lam_top = lam_mult * kk
    # Far-pair kill cap (sigma = 5 class, |k_m| >> k_p): beyond
    # lam ~ 60/s the integrand is e^{-60} of the total — dead range that
    # the adaptive head/mid otherwise grind through at full depth (and
    # underflow to exact 0 on the ray). Cap the extents there, keeping
    # the k_p branch point + transmitted pole (|lam_p| ~ k_p) inside the
    # head. Inactive for s <= 60/lam_top — every near-interface pair —
    # so nothing pinned by probes 21/22 changes.
    if s > 0.0 and 60.0 / s < lam_top:
        lam_kill = 60.0 / s
        a_head = max(2.2 * k_p, min(a_head, lam_kill))
        lam_top = max(1.5 * a_head, lam_kill)

    def f_core(lam):
        return _core(lam, z, zp, k_p, k_m)

    def f_j0(lam):
        b0, _ = _bessel_j0_j1x(lam * rho)
        return f_core(lam) * b0

    head, _hp = _head(
        f_j0,
        a_head,
        rho,
        (k_p, abs(k_m.real)),
        rtol,
        _ADAPT_DEPTH,
        _DETOUR,
        _GX,
        _GW,
    )
    mid = _adaptive_segment(f_j0, a_head, lam_top, rtol, _ADAPT_DEPTH, _GX, _GW)

    scale = np.sqrt(2.0) / (s + rho)
    if rho == 0.0:
        tail = _ray_integral(f_core, lambda lam: 1.0, lam_top, _RAY, scale, rtol)
    else:
        up = _ray_integral(
            f_core,
            lambda lam: 0.5 * hankel1(0, lam * rho),
            lam_top,
            _RAY,
            scale,
            rtol,
        )
        dn = _ray_integral(
            f_core,
            lambda lam: 0.5 * hankel2(0, lam * rho),
            lam_top,
            np.conj(_RAY),
            scale,
            rtol,
        )
        tail = up + dn
    return head + mid + tail


def designed_tables(eps_t, k2, rho, z, zp, rtol=1e-10, lam_mult=_LAM_MULT):
    """Broadcast wrapper, mp_tables-compatible + the two auxiliaries.
    Accepts z' = 0 and z = 0 exactly (no clamp); refuses only R = 0."""
    rho_b, z_b, zp_b = np.broadcast_arrays(
        np.asarray(rho, float), np.asarray(z, float), np.asarray(zp, float)
    )
    out = np.empty((6,) + rho_b.shape, dtype=np.complex128)
    it = np.nditer(rho_b, flags=["multi_index"])
    for _ in it:
        ix = it.multi_index
        out[(slice(None),) + ix] = six_point(
            eps_t,
            k2,
            float(rho_b[ix]),
            float(z_b[ix]),
            float(zp_b[ix]),
            rtol=rtol,
            lam_mult=lam_mult,
        )
    return dict(zip(KEYS, out))


def radius_tables(wire_radius):
    """An mp_tables-compatible callable that folds the thin-wire offset in:
    rho_eff = hypot(rho, a) — the same-edge moments' R = sqrt(dz^2 + a^2)
    convention extended to the cross family (DERIVATION-NEAR-INTERFACE §3).
    """
    a = float(wire_radius)

    def tables(eps_t, k2, rho, z, zp, rtol=1e-10):
        rho_eff = np.hypot(np.asarray(rho, float), a)
        return designed_tables(eps_t, k2, rho_eff, z, zp, rtol=rtol)

    return tables


def install(wire_radius=None):
    """Monkeypatch mp_cross.mp_tables with the designed evaluation
    (radius-folded if a wire_radius is given). Returns the original."""
    import mp_cross

    orig = mp_cross.mp_tables
    if wire_radius is None:

        def tables(eps_t, k2, rho, z, zp, rtol=1e-10):
            return designed_tables(eps_t, k2, rho, z, zp, rtol=rtol)

        mp_cross.mp_tables = tables
    else:
        mp_cross.mp_tables = radius_tables(wire_radius)
    return orig

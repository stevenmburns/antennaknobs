"""momwire#524 phase-0 prototype: buried-dipole half-space fields, direct evaluation.

Scripts-and-gates risk burn-down.  No grids, no interpolation, no product code.
The ONLY physics source is ./EQUATIONS.md (verified 2026-08-22 against the
AGARD-LS-131 paper-8 page images); the shared geometry/soil spec is ../SPEC.md.

Conventions (momwire-identical): e^{+jwt}; upper medium (air) subscript p,
k_p real; lower medium (ground) subscript m, k_m = k_p sqrt(eps_t),
eps_t = eps_r - j sigma/(w eps0), Im(k_m) <= 0.  C1 = -j w mu0 / 4pi.
Interface at z = 0, source at (0, 0, z'), observer at (rho, phi, z),
horizontal dipole along x-hat, unit current moment (I dl = 1).

Run `python buried_proto.py` for the six gates G1-G6.
"""

from __future__ import annotations

import argparse
import math
import sys
import time
from dataclasses import dataclass

import numpy as np
from numpy.polynomial.legendre import leggauss
from scipy.constants import epsilon_0 as EPS0
from scipy.constants import mu_0 as MU0
from scipy.special import jv

# ---------------------------------------------------------------------------
# Media
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HalfSpace:
    """Air over lossy ground at one frequency."""

    freq: float
    eps_r: float
    sigma: float

    @property
    def omega(self) -> float:
        return 2.0 * math.pi * self.freq

    @property
    def eps_t(self) -> complex:
        return complex(self.eps_r) - 1j * self.sigma / (self.omega * EPS0)

    @property
    def kp(self) -> float:
        return self.omega * math.sqrt(MU0 * EPS0)

    @property
    def km(self) -> complex:
        k = self.kp * np.sqrt(complex(self.eps_t))
        if k.imag > 0:  # principal root already gives Im <= 0 for Im(eps_t) <= 0
            k = np.conj(k)
        return complex(k)

    @property
    def C1(self) -> complex:
        return -1j * self.omega * MU0 / (4.0 * math.pi)

    def assert_decay(self) -> None:
        """Runtime assertion: |e^{-j k_m R}| must DECAY with R."""
        km = self.km
        a = abs(np.exp(-1j * km * 1.0))
        b = abs(np.exp(-1j * km * 2.0))
        if not (b <= a + 1e-15):
            raise AssertionError(
                f"flipped convention: |e^-jk_m R| grows with R (k_m={km!r})"
            )


# ---------------------------------------------------------------------------
# gamma with the principal root (momwire's realization)
# ---------------------------------------------------------------------------


def gamma(lam, k):
    """(lam^2 - k^2)^{1/2}, vertical cuts down from +k / up from -k."""
    lam = np.asarray(lam, dtype=np.complex128)
    return np.sqrt(-1j * (lam - k)) * np.sqrt(1j * (lam + k))


def bessel_j0_j1x(x):
    """(J0(x), J1(x)/x) with a series switch at small |x| (rho -> 0 safe)."""
    x = np.asarray(x, dtype=np.complex128)
    small = np.abs(x) < 1e-6
    xs = np.where(small, 1.0, x)
    j0 = np.where(small, 1.0 - 0.25 * x * x, jv(0, xs))
    j1x = np.where(small, 0.5 - x * x / 16.0, jv(1, xs) / xs)
    return j0, j1x


# ---------------------------------------------------------------------------
# Quadrature engine: Gauss panels, adaptive bisection, half-sine head detour,
# Bessel-zero-partitioned accelerated tail.
# ---------------------------------------------------------------------------

_LEG: dict[int, tuple[np.ndarray, np.ndarray]] = {}


def _leg(n: int):
    if n not in _LEG:
        _LEG[n] = leggauss(n)
    return _LEG[n]


def _gauss(f, z0, z1, n):
    """Vector-valued Gauss-Legendre over the straight segment z0 -> z1."""
    x, w = _leg(n)
    mid = 0.5 * (z0 + z1)
    half = 0.5 * (z1 - z0)
    return f(mid + half * x) @ (w * half)


def _adapt(f, z0, z1, rtol, n, depth, whole=None, ref=0.0):
    if whole is None:
        whole = _gauss(f, z0, z1, n)
    mid = 0.5 * (z0 + z1)
    left = _gauss(f, z0, mid, n)
    right = _gauss(f, mid, z1, n)
    better = left + right
    err = float(np.max(np.abs(better - whole)))
    scale = max(float(np.max(np.abs(better))), ref)
    if depth <= 0 or err <= rtol * max(scale, 1e-300):
        return better
    return _adapt(f, z0, mid, rtol, n, depth - 1, left, ref) + _adapt(
        f, mid, z1, rtol, n, depth - 1, right, ref
    )


def _wynn_epsilon(seq):
    """Wynn's epsilon on a sequence of complex vectors; returns the best
    even-column entry (elementwise, so each component is accelerated on its
    own partial-sum sequence)."""
    s = np.asarray(seq)  # (nterms, K)
    n = s.shape[0]
    if n < 5:
        return s[-1]
    prev = np.zeros_like(s)
    cur = s.copy()
    best = s[-1].copy()
    with np.errstate(divide="ignore", invalid="ignore"):
        for k in range(1, n):
            d = cur[1:] - cur[:-1]
            d = np.where(np.abs(d) < 1e-300, 1e-300, d)
            nxt = prev[:-1] + 1.0 / d
            prev, cur = cur[:-1], nxt
            if k % 2 == 0 and cur.shape[0] >= 1:
                cand = cur[-1]
                if np.all(np.isfinite(cand)):
                    best = cand
            if cur.shape[0] <= 1:
                break
    return best


@dataclass
class QuadResult:
    value: np.ndarray
    head_panels: int
    tail_panels: int
    tail_converged: bool
    accel_used: bool


class Integrator:
    """Contour machinery shared by every Sommerfeld-type integral here.

    Head [0, a]: first-quadrant half-sine detour lam(t) = t + j H sin(pi t/a)
    with a = 1.1 max(k_p, |k_m|) past both branch points and a rho-adaptive
    height H (shrinks as rho grows so J0(lam rho) ~ e^{|Im lam| rho} stays
    bounded).  Tail [a, inf): panels partitioned at the J0(lam rho) zeros
    (capped so e^{-lam h} is resolved), plain summation with a Wynn-epsilon
    fallback when the plain sum has not gone quiet.
    """

    def __init__(self, n=16, rtol=1e-11, depth=14, max_panels=6000, detour=2.0):
        self.n = n
        self.rtol = rtol
        self.depth = depth
        self.max_panels = max_panels
        self.detour = detour

    # -- head ---------------------------------------------------------------
    def _head(self, fl, a, rho, marks):
        H = min(0.35 * a, self.detour / max(rho, 1e-12))
        H = max(H, 1e-6 * a)

        def ft(t):
            t = np.asarray(t, dtype=float)
            lam = t + 1j * H * np.sin(np.pi * t / a)
            dl = 1.0 + 1j * H * (np.pi / a) * np.cos(np.pi * t / a)
            return fl(lam) * dl

        edges = {0.0, a}
        for i in range(1, 7):
            edges.add(a * i / 7.0)
        for mk in marks:
            for w in (0.0, -0.15, 0.15, -0.4, 0.4):
                v = mk * (1.0 + w)
                if 0.0 < v < a:
                    edges.add(v)
        e = sorted(edges)
        total = None
        for i in range(len(e) - 1):
            part = _adapt(ft, e[i], e[i + 1], self.rtol, self.n, self.depth)
            total = part if total is None else total + part
        return total, len(e) - 1

    # -- tail ---------------------------------------------------------------
    def _tail(self, fl, a, rho, hdec, ref):
        """Panels from a to infinity along the real axis.

        Edges are the J0(lam rho) zero lattice (asymptotic spacing pi/rho,
        offset so the lattice sits on the true large-argument zeros), further
        capped so that e^{-gamma h} ~ e^{-lam h} varies by at most ~e^{-1.5}
        across a panel -- a single Gauss rule leaping across many e-foldings
        was the dominant small-rho error.
        """
        dl_decay = (1.5 / hdec) if hdec > 0 else np.inf
        if not np.isfinite(dl_decay):
            dl_decay = max(1.0, 10.0 * a)
        lat = (np.pi / rho) if rho > 0 else np.inf
        off = (-0.25 * np.pi / rho) if rho > 0 else 0.0  # zeros at (n-1/4)pi/rho

        def next_zero(zz):
            if not np.isfinite(lat):
                return np.inf
            # +1e-9 so a z sitting exactly on the lattice (round-off below it)
            # advances instead of producing a zero-length panel.
            n = math.floor((zz - off) / lat + 1e-9) + 1
            return off + n * lat

        z = a
        sums = []
        parts = 0
        quiet = 0
        converged = False
        acc = None
        ref_scale = float(np.max(np.abs(ref))) if ref is not None else 0.0
        while parts < self.max_panels:
            znext = min(next_zero(z), z + dl_decay)
            contrib = _adapt(fl, z, znext, self.rtol, self.n, 6)
            acc = contrib if acc is None else acc + contrib
            sums.append(acc.copy())
            z = znext
            parts += 1
            cmax = float(np.max(np.abs(contrib)))
            smax = max(float(np.max(np.abs(acc))), ref_scale, 1e-300)
            if cmax == 0.0 or cmax < self.rtol * smax:
                quiet += 1
                if quiet >= 2:
                    converged = True
                    break
            else:
                quiet = 0
        accel = False
        if not converged and len(sums) >= 8:
            tailseq = np.array(sums[-min(len(sums), 41) :])
            acc = _wynn_epsilon(tailseq)
            accel = True
        return acc, parts, converged, accel

    # -- driver -------------------------------------------------------------
    def run(self, fl, kp, km, rho, hdec, marks=()) -> QuadResult:
        a = 1.1 * max(abs(kp), abs(km))
        head, hp = self._head(fl, a, rho, marks)
        tail, tp, conv, acc = self._tail(fl, a, rho, hdec, head)
        return QuadResult(head + tail, hp, tp, conv, acc)


# ---------------------------------------------------------------------------
# The two integrand stacks
# ---------------------------------------------------------------------------


def stack_T(lam, rho, z, zp, kp, km, swap=False):
    """Regime-1 (transmitted) stack, EQUATIONS.md (7f)(7g) + under-integral
    derivatives.  8 components:

      0 V_T   1 dV/drho   2 d2V/drho2   3 d2V/drho dz
      4 (d2/dz2 + k_p^2)V   5 (1/rho)dV/drho   6 d2V/drho dz'   7 U_T

    `swap=True` builds the above->below twin: source ABOVE at z' > 0 (carrying
    gamma_p) and observer BELOW at z < 0 (carrying gamma_m).  The observer-side
    exponent derivative factor changes accordingly, but the reciprocity gate
    only looks at component 0.
    """
    lam = np.asarray(lam, dtype=np.complex128)
    gp = gamma(lam, kp)
    gm = gamma(lam, km)
    if swap:
        # observer below (gamma_m on |z|), source above (gamma_p on |z'|)
        e = 2.0 * np.exp(-gp * abs(zp) - gm * abs(z)) * lam
        dz = +gm  # d/dz of e^{-gamma_m |z|} at z < 0  ->  x(+gamma_m)
        dzp = -gp  # d/dz' of e^{-gamma_p |z'|} at z' > 0 -> x(-gamma_p)
        zzk = gm * gm + km * km  # (d2/dz2 + k_m^2) in the observer medium
    else:
        e = 2.0 * np.exp(-gm * abs(zp) - gp * z) * lam
        dz = -gp
        dzp = +gm
        zzk = gp * gp + kp * kp  # = lam^2
    p2 = 1.0 / (km * km * gp + kp * kp * gm)
    p1 = 1.0 / (gm + gp)
    x = lam * rho
    j0, j1x = bessel_j0_j1x(x)
    j1 = j1x * x
    A = e * p2
    return np.stack(
        [
            A * j0,
            A * (-lam * j1),
            A * (lam * lam * (j1x - j0)),
            A * (-lam * j1) * dz,
            A * zzk * j0,
            A * (-lam * lam * j1x),
            A * (-lam * j1) * dzp,
            e * p1 * j0,
        ]
    )


def d12(lam, k_s, k_o):
    """EQUATIONS.md D1/D2 generalized to an arbitrary SHARED medium s (both
    source and observer in it) and OTHER medium o.

      D1 = 2/(g_o + g_s) - 2 k_s^2 / (g_s (k_o^2 + k_s^2))
      D2 = 2/(k_o^2 g_s + k_s^2 g_o) - 2/(g_s (k_o^2 + k_s^2))

    At s = p (both above) this is exactly momwire's `_d12(lam, k1=k_m, k2=k_p)`
    (gate G6); at s = m (both below) it is EQUATIONS.md's below/below pair.
    """
    lam = np.asarray(lam, dtype=np.complex128)
    gs = gamma(lam, k_s)
    go = gamma(lam, k_o)
    ks2 = k_s * k_s
    ko2 = k_o * k_o
    d1 = 2.0 / (go + gs) - 2.0 * ks2 / (gs * (ko2 + ks2))
    d2 = 2.0 / (ko2 * gs + ks2 * go) - 2.0 / (gs * (ko2 + ks2))
    return d1, d2, gs


def stack_R(lam, rho, h, sz, k_s, k_o):
    """Remainder stack, EQUATIONS.md (5a)-(5f) generalized.  h = |z + z'|,
    sz = sign(z + z') (so d/dz -> x(-sz gamma_s)).  7 components:

      0 V_R   1 dV/drho   2 d2V/drho2   3 d2V/drho dz
      4 d2V/dz2   5 (1/rho)dV/drho   6 U_R
    """
    lam = np.asarray(lam, dtype=np.complex128)
    d1, d2, gs = d12(lam, k_s, k_o)
    e = np.exp(-gs * h) * lam
    ddz = -sz * gs
    x = lam * rho
    j0, j1x = bessel_j0_j1x(x)
    j1 = j1x * x
    A = e * d2
    return np.stack(
        [
            A * j0,
            A * (-lam * j1),
            A * (lam * lam * (j1x - j0)),
            A * (-lam * j1) * ddz,
            A * gs * gs * j0,
            A * (-lam * lam * j1x),
            e * d1 * j0,
        ]
    )


# ---------------------------------------------------------------------------
# Scalar-integral drivers (with a per-value self-convergence error estimate)
# ---------------------------------------------------------------------------

_FINE = Integrator(n=24, rtol=1e-12, depth=16, max_panels=12000)
_COARSE = Integrator(n=16, rtol=1e-10, depth=12, max_panels=12000, detour=1.2)

# Global quadrature-health tally, reported at the end of a full run.
STATS = {
    "n": 0,
    "accel": 0,
    "nonconv": 0,
    "worst_selfconv": 0.0,
    "worst_selfconv_where": None,
    "max_tail_panels": 0,
    "max_head_panels": 0,
}


def _tally(tag, q: QuadResult, rel):
    STATS["n"] += 1
    if q.accel_used:
        STATS["accel"] += 1
    if not q.tail_converged:
        STATS["nonconv"] += 1
    STATS["max_tail_panels"] = max(STATS["max_tail_panels"], q.tail_panels)
    STATS["max_head_panels"] = max(STATS["max_head_panels"], q.head_panels)
    if rel is not None and rel > STATS["worst_selfconv"]:
        STATS["worst_selfconv"] = rel
        STATS["worst_selfconv_where"] = tag


def integrals_T(hs: HalfSpace, rho, z, zp, swap=False, err=True):
    kp, km = hs.kp, hs.km
    hdec = abs(zp) + abs(z)

    def fl(lam):
        return stack_T(lam, rho, z, zp, kp, km, swap=swap)

    marks = (kp, abs(km.real))
    fine = _FINE.run(fl, kp, km, rho, hdec, marks)
    if not err:
        _tally(("T", rho, z, zp), fine, None)
        return fine.value, None, fine
    coarse = _COARSE.run(fl, kp, km, rho, hdec, marks)
    scale = np.maximum(np.abs(fine.value), 1e-300)
    rel = float(np.max(np.abs(fine.value - coarse.value) / scale))
    _tally(("T", hs.eps_r, hs.freq, rho, z, zp), fine, rel)
    return fine.value, rel, fine


def integrals_R(hs: HalfSpace, rho, z, zp, shared="m", err=True):
    kp, km = hs.kp, hs.km
    if shared == "m":
        k_s, k_o = km, kp
    else:
        k_s, k_o = kp, km
    h = abs(z + zp)
    sz = 1.0 if (z + zp) >= 0 else -1.0
    if k_s == k_o:
        # eps_t = 1: D1 = D2 = 0 identically.  In floating point the two
        # subtracted static terms leave ~1e-16 noise, and a purely RELATIVE
        # tail test can never go quiet on noise/noise -- short-circuit instead
        # (momwire's `_six_integrals` documents the same trap).
        z7 = np.zeros(7, dtype=np.complex128)
        return z7, 0.0, QuadResult(z7, 0, 0, True, False)

    def fl(lam):
        return stack_R(lam, rho, h, sz, k_s, k_o)

    marks = (kp, abs(km.real))
    fine = _FINE.run(fl, kp, km, rho, h, marks)
    if not err:
        _tally(("R", rho, z, zp), fine, None)
        return fine.value, None, fine
    coarse = _COARSE.run(fl, kp, km, rho, h, marks)
    scale = np.maximum(np.abs(fine.value), 1e-300)
    rel = float(np.max(np.abs(fine.value - coarse.value) / scale))
    _tally(("R", hs.eps_r, hs.freq, rho, z, zp), fine, rel)
    return fine.value, rel, fine


# ---------------------------------------------------------------------------
# Free-space closed forms (complex k)
# ---------------------------------------------------------------------------

_MIRROR = np.array([1.0, 1.0, -1.0])


def fs_field(C1, k, p_hat, d):
    """E of a unit current moment p_hat at displacement d = r - r_src,
    E = C1 (grad grad / k^2 + I) . (p_hat e^{-jkR}/R), complex k."""
    d = np.asarray(d, dtype=float)
    R = float(np.sqrt(np.dot(d, d)))
    Rh = d / R
    a = 1.0 / (k * R)
    G = np.exp(-1j * k * R) / R
    pr = np.dot(Rh, p_hat)
    return (
        C1
        * G
        * (
            np.asarray(p_hat, dtype=np.complex128) * (1.0 - 1j * a - a * a)
            + Rh * pr * (-1.0 + 3j * a + 3.0 * a * a)
        )
    )


def image_field(C1, k, p_hat, obs, zp, convention="mirror"):
    """AGARD (4b) image term.

    `mirror` (default, = momwire's shipped image convention): the source is
    mirrored in BOTH position and orientation and the whole block carries one
    global minus, E^I = -E^D(r - r'_img ; I_R p_hat).  This is the reading
    that reproduces the PEC limit for both orientations.

    `literal`: the left-contraction reading of the text
    "-I_R . G^D(r, I_R r')", i.e. flip the z-component of the field of an
    un-mirrored element at the image point.  Kept so the gate can measure it.
    """
    obs = np.asarray(obs, dtype=float)
    d = obs - np.array([0.0, 0.0, -zp])
    if convention == "mirror":
        return -fs_field(C1, k, np.asarray(p_hat) * _MIRROR, d)
    if convention == "literal":
        return -_MIRROR * fs_field(C1, k, p_hat, d)
    raise ValueError(convention)


# ---------------------------------------------------------------------------
# Field assembly
# ---------------------------------------------------------------------------


def _cyl_to_cart(e_rho, e_phi, e_z, phi):
    c, s = math.cos(phi), math.sin(phi)
    return np.array([e_rho * c - e_phi * s, e_rho * s + e_phi * c, e_z])


def field_transmitted(hs: HalfSpace, obs, zp, kind, err=True):
    """Regime 1: source buried at z' < 0, observer above (z > 0).  The ENTIRE
    field is the transmitted term (EQUATIONS.md 7a-7e)."""
    x, y, z = obs
    rho = math.hypot(x, y)
    phi = math.atan2(y, x)
    I, rel, q = integrals_T(hs, rho, z, zp, err=err)
    C1 = hs.C1
    if kind == "VED":
        e_rho = C1 * I[3]
        e_phi = 0.0 + 0.0j
        e_z = C1 * I[4]
    elif kind == "HED":
        e_rho = C1 * math.cos(phi) * (I[2] + I[7])
        e_phi = -C1 * math.sin(phi) * (I[5] + I[7])
        e_z = -C1 * math.cos(phi) * I[6]
    else:
        raise ValueError(kind)
    return _cyl_to_cart(e_rho, e_phi, e_z, phi), rel, q


def field_remainder(hs: HalfSpace, obs, zp, kind, shared="m", err=True):
    """The R_+- remainder of EQUATIONS.md (5a)-(5d), generalized in the shared
    medium."""
    x, y, z = obs
    rho = math.hypot(x, y)
    phi = math.atan2(y, x)
    I, rel, q = integrals_R(hs, rho, z, zp, shared=shared, err=err)
    C1 = hs.C1
    if shared == "m":
        k_s, k_o = hs.km, hs.kp
    else:
        k_s, k_o = hs.kp, hs.km
    r = (k_o * k_o) / (k_s * k_s)
    r_rho_V = C1 * r * I[3]
    r_z_V = C1 * r * (I[4] + k_s * k_s * I[0])
    if kind == "VED":
        e_rho, e_phi, e_z = r_rho_V, 0.0 + 0.0j, r_z_V
    elif kind == "HED":
        e_rho = C1 * math.cos(phi) * (I[2] + I[6])
        e_phi = -C1 * math.sin(phi) * (I[5] + I[6])
        e_z = -math.cos(phi) * r_rho_V
    else:
        raise ValueError(kind)
    return _cyl_to_cart(e_rho, e_phi, e_z, phi), rel, q


def field_in_medium(
    hs: HalfSpace,
    obs,
    zp,
    kind,
    sA=+1.0,
    s=+1.0,
    convention="mirror",
    err=True,
    parts=False,
):
    """Regime 2: both source and observer below (z, z' < 0).

    E_total = E_direct(k_m) + A_m E_image + s E_remainder,
    A_m = sA (k_p^2 - k_m^2)/(k_p^2 + k_m^2).
    """
    p_hat = np.array([1.0, 0.0, 0.0]) if kind == "HED" else np.array([0.0, 0.0, 1.0])
    C1, kp, km = hs.C1, hs.kp, hs.km
    d = np.asarray(obs, dtype=float) - np.array([0.0, 0.0, zp])
    e_dir = fs_field(C1, km, p_hat, d)
    e_img = image_field(C1, km, p_hat, obs, zp, convention=convention)
    A_m = sA * (kp * kp - km * km) / (kp * kp + km * km)
    e_rem, rel, q = field_remainder(hs, obs, zp, kind, shared="m", err=err)
    tot = e_dir + A_m * e_img + s * e_rem
    if parts:
        return tot, rel, q, dict(direct=e_dir, image=e_img, rem=e_rem, A_m=A_m)
    return tot, rel, q


# ---------------------------------------------------------------------------
# Gates
# ---------------------------------------------------------------------------

SOILS = {"A": (13.0, 0.005), "B": (20.0, 0.03), "C": (5.0, 0.001)}
_RESULTS: list[tuple[str, bool, str]] = []


def _report(name, ok, detail):
    _RESULTS.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}", flush=True)


def _relerr(a, b):
    a = np.asarray(a)
    b = np.asarray(b)
    den = np.maximum(np.abs(a), np.abs(b))
    den = np.where(den < 1e-300, 1.0, den)
    return float(np.max(np.abs(a - b) / den))


# -- G0 sanity ---------------------------------------------------------------


def gate_sommerfeld_identity():
    """Cheap contour self-test: with k_m = k_p the V_T integral must reproduce
    e^{-j k_p R}/R / k_p^2 (the Sommerfeld identity) and U_T must reproduce
    e^{-j k_p R}/R.  Catches contour bugs before anything else."""
    hs = HalfSpace(7e6, 1.0, 0.0)
    kp = hs.kp
    worst = 0.0
    lines = []
    for rho, z, zp in [
        (2.0, 1.0, -0.05),
        (10.0, 1.0, -0.15),
        (10.0, 0.1, -0.05),
        (30.0, 1.0, -0.05),
        (0.5, 3.0, -0.15),
    ]:
        I, rel, q = integrals_T(hs, rho, z, zp)
        R = math.hypot(rho, z + abs(zp))
        exact = np.exp(-1j * kp * R) / R
        e1 = _relerr(I[0] * kp * kp, exact)
        e2 = _relerr(I[7], exact)
        worst = max(worst, e1, e2)
        lines.append(
            f"    rho={rho} z={z} z'={zp}: V_T k_p^2 {e1:.2e}  U_T {e2:.2e}  (selfconv {rel:.1e}, tail {q.tail_panels}p conv={q.tail_converged})"
        )
    ok = worst < 1e-9
    _report(
        "G0 Sommerfeld identity (k_m=k_p)", ok, f"worst rel err {worst:.3e} (tol 1e-9)"
    )
    for ln in lines:
        print(ln)
    return worst


# -- G1 reciprocity ----------------------------------------------------------


def gate_G1():
    worst = 0.0
    lines = []
    for soil in ("A", "B", "C"):
        er, sg = SOILS[soil]
        for f in (7e6, 21e6):
            hs = HalfSpace(f, er, sg)
            hs.assert_decay()
            for rho, z, zp in [
                (2.0, 1.0, -0.05),
                (10.0, 1.0, -0.15),
                (5.0, 0.3, -0.02),
            ]:
                a, _, _ = integrals_T(hs, rho, z, zp, err=False)
                b, _, _ = integrals_T(hs, rho, zp, z, swap=True, err=False)
                e = _relerr(a[0], b[0])
                worst = max(worst, e)
                lines.append(
                    f"    soil {soil} f={f / 1e6:.0f}MHz rho={rho} z={z} z'={zp}: rel {e:.3e}"
                )
    ok = worst < 1e-10
    _report(
        "G1 reciprocity V_T(b->a) == V_T(a->b)",
        ok,
        f"worst rel diff {worst:.3e} (tol 1e-10)",
    )
    for ln in lines:
        print(ln)
    return worst


# -- G2 eps_t -> 1 -----------------------------------------------------------


def gate_G2():
    """eps_t -> 1: regime-1 field must equal the free-space field, and the
    below/below composition must too (A_m -> 0, D1 = D2 = 0)."""
    hs = HalfSpace(7e6, 1.0, 0.0)
    C1, kp = hs.C1, hs.kp
    worst_T = 0.0
    worst_M = 0.0
    lines = []
    for kind in ("VED", "HED"):
        p_hat = np.array([1.0, 0.0, 0.0]) if kind == "HED" else np.array([0, 0, 1.0])
        for obs, zp in [
            ((6.0, 0.0, 1.0), -0.05),
            ((10.0, 4.0, 1.0), -0.15),
            ((3.0, 3.0, 0.3), -0.02),
        ]:
            got, rel, q = field_transmitted(hs, obs, zp, kind)
            d = np.asarray(obs, dtype=float) - np.array([0.0, 0.0, zp])
            want = fs_field(C1, kp, p_hat, d)
            e = _relerr(got, want)
            worst_T = max(worst_T, e)
            lines.append(
                f"    regime1 {kind} obs={obs} z'={zp}: rel {e:.3e} (selfconv {rel:.1e})"
            )
        for obs, zp in [((4.0, 0.0, -0.5), -0.05), ((8.0, 3.0, -0.5), -0.15)]:
            got, rel, q, pp = field_in_medium(hs, obs, zp, kind, parts=True)
            want = pp["direct"]
            e = _relerr(got, want)
            worst_M = max(worst_M, e)
            lines.append(
                f"    regime2 {kind} obs={obs} z'={zp}: rel {e:.3e} "
                f"|A_m|={abs(pp['A_m']):.2e} |rem|/|dir|={np.max(np.abs(pp['rem'])) / np.max(np.abs(want)):.2e}"
            )
    worst = max(worst_T, worst_M)
    ok = worst < 1e-8
    _report(
        "G2 eps_t -> 1 reduces to free space",
        ok,
        f"worst rel err {worst:.3e} (tol 1e-8)",
    )
    for ln in lines:
        print(ln)
    return worst


# -- G3 sigma ladder ---------------------------------------------------------


def gate_G3():
    obs = (10.0, 0.0, 1.0)
    zp = -0.05
    mags = []
    lines = []
    sigmas = [0.005, 0.05, 0.5, 5.0, 50.0, 500.0]
    for sg in sigmas:
        hs = HalfSpace(7e6, 13.0, sg)
        e, rel, q = field_transmitted(hs, obs, zp, "HED")
        m = float(np.max(np.abs(e)))
        mags.append(m)
        lines.append(f"    sigma={sg:>7g} S/m: |E|max={m:.6e}  (selfconv {rel:.1e})")
    mono = all(mags[i + 1] < mags[i] for i in range(len(mags) - 1))
    ratio = mags[-1] / mags[0]
    # kernel-level cancellation 2/(gamma_m + gamma_p) -> 0 at a fixed lambda
    lam = 0.5
    kern = []
    for sg in sigmas:
        hs = HalfSpace(7e6, 13.0, sg)
        kern.append(abs(2.0 / complex(gamma(lam, hs.km) + gamma(lam, hs.kp))))
    kern_mono = all(kern[i + 1] < kern[i] for i in range(len(kern) - 1))
    ok = mono and kern_mono and ratio < 1e-3
    _report(
        "G3 sigma ladder: transmitted |E| falls monotonically",
        ok,
        f"monotone={mono} kernel-monotone={kern_mono} |E|(500)/|E|(0.005)={ratio:.3e}",
    )
    for ln in lines:
        print(ln)
    print(
        "    kernel 2/(g_m+g_p) at lambda=0.5: " + ", ".join(f"{k:.3e}" for k in kern)
    )
    return ratio


# -- G5 analytic vs finite-difference derivatives ----------------------------


def _fd1(f, h):
    """5-point central first derivative, O(h^4)."""
    return (f(-2) - 8 * f(-1) + 8 * f(1) - f(2)) / (12 * h)


def _fd2(f, h):
    """5-point central second derivative, O(h^4).

    The plain 3-point second difference is round-off limited at
    4 delta / h^2; with delta ~ 1e-13 (the integrator's own accuracy) and the
    tiny steps a naive `1e-4 * z` picks, that noise floor lands at ~1e-5
    relative -- which is exactly what the first cut of this gate measured.
    """
    return (-f(-2) + 16 * f(-1) - 30 * f(0) + 16 * f(1) - f(2)) / (12 * h * h)


def _fd_cross(f, ha, hb):
    """Richardson-extrapolated mixed second derivative, O(h^4).

    The plain 4-point cross stencil is only O(h^2); at the step sizes this
    gate can afford that truncation alone lands at ~1e-5 relative (measured),
    which is a stencil artefact, not a defect in the analytic derivative.
    """

    def d(m):
        return (f(m, m) - f(-m, m) - f(m, -m) + f(-m, -m)) / (4 * m * ha * m * hb)

    return (4.0 * d(1) - d(2)) / 3.0


def gate_G5():
    worst = 0.0
    lines = []
    for soil in ("A", "C"):
        er, sg = SOILS[soil]
        hs = HalfSpace(7e6, er, sg)
        # ---- transmitted stack ----
        for rho, z, zp in [(4.0, 1.0, -0.05), (10.0, 0.3, -0.15)]:
            I, _, _ = integrals_T(hs, rho, z, zp, err=False)
            # The integrand's variation scale in z / z' is the decay length
            # L = |z| + |z'| (that is what caps the useful lambda range), and
            # in rho it is min(rho, L).  Steps at ~2e-3 L balance the O(h^4)
            # truncation against the integrator's own ~1e-13 noise.
            L = abs(z) + abs(zp)
            hz = 2e-3 * L
            hzp = 2e-3 * L
            hr = 2e-3 * min(rho, max(L, 1.0 / hs.kp))

            def V(r_, z_, zp_):
                return integrals_T(hs, r_, z_, zp_, err=False)[0][0]

            fd_r = _fd1(lambda i: V(rho + i * hr, z, zp), hr)
            fd_rr = _fd2(lambda i: V(rho + i * hr, z, zp), hr)
            fd_rz = _fd_cross(lambda i, j: V(rho + i * hr, z + j * hz, zp), hr, hz)
            fd_rzp = _fd_cross(lambda i, j: V(rho + i * hr, z, zp + j * hzp), hr, hzp)
            fd_zz = _fd2(lambda i: V(rho, z + i * hz, zp), hz)
            pairs = [
                ("dV/drho", I[1], fd_r),
                ("d2V/drho2", I[2], fd_rr),
                ("d2V/drho dz", I[3], fd_rz),
                ("d2V/drho dz'", I[6], fd_rzp),
                ("(d2/dz2+kp^2)V", I[4], fd_zz + hs.kp**2 * V(rho, z, zp)),
                ("(1/rho)dV/drho", I[5], fd_r / rho),
            ]
            for nm, an, fd in pairs:
                e = _relerr(an, fd)
                worst = max(worst, e)
                lines.append(
                    f"    T soil {soil} rho={rho} z={z} z'={zp} {nm}: rel {e:.2e}"
                )
        # ---- remainder stack ----
        for rho, z, zp in [(4.0, -0.5, -0.05), (8.0, -0.5, -0.15)]:
            J, _, _ = integrals_R(hs, rho, z, zp, err=False)
            L = abs(z + zp)
            hz = 2e-3 * L
            hr = 2e-3 * min(rho, max(L, 1.0 / hs.kp))

            def W(r_, z_, zp_):
                return integrals_R(hs, r_, z_, zp_, err=False)[0][0]

            fd_r = _fd1(lambda i: W(rho + i * hr, z, zp), hr)
            fd_rr = _fd2(lambda i: W(rho + i * hr, z, zp), hr)
            fd_rz = _fd_cross(lambda i, j: W(rho + i * hr, z + j * hz, zp), hr, hz)
            fd_zz = _fd2(lambda i: W(rho, z + i * hz, zp), hz)
            for nm, an, fd in [
                ("dV_R/drho", J[1], fd_r),
                ("d2V_R/drho2", J[2], fd_rr),
                ("d2V_R/drho dz", J[3], fd_rz),
                ("d2V_R/dz2", J[4], fd_zz),
                ("(1/rho)dV_R/drho", J[5], fd_r / rho),
            ]:
                e = _relerr(an, fd)
                worst = max(worst, e)
                lines.append(
                    f"    R soil {soil} rho={rho} z={z} z'={zp} {nm}: rel {e:.2e}"
                )
    ok = worst < 1e-6
    _report(
        "G5 analytic vs FD derivatives", ok, f"worst rel diff {worst:.3e} (tol 1e-6)"
    )
    for ln in lines:
        print(ln)
    return worst


# -- G6 momwire anchor at +- = + ---------------------------------------------


def gate_G6():
    from momwire import _sommerfeld as ms

    worst_d = 0.0
    lines = []
    for soil in ("A", "B", "C"):
        er, sg = SOILS[soil]
        for f in (7e6, 21e6):
            hs = HalfSpace(f, er, sg)
            kp, km = hs.kp, hs.km
            lam = np.concatenate(
                [
                    np.linspace(1e-4, 3.0 * abs(km), 60),
                    np.array([0.5 * kp, kp * 1.5, abs(km) * 0.9, abs(km) * 1.1]),
                    np.geomspace(3.0 * abs(km), 400.0, 40),
                ]
            )
            mine1, mine2, _ = d12(lam, kp, km)  # shared = p (both above)
            mw1, mw2, _ = ms._d12(lam.astype(np.complex128), km, kp)
            e = max(_relerr(mine1, mw1), _relerr(mine2, mw2))
            worst_d = max(worst_d, e)
            lines.append(
                f"    D1/D2 soil {soil} f={f / 1e6:.0f}MHz over {lam.size} lambdas: rel {e:.2e}"
            )

    # stronger anchor: the four NEC interpolation surfaces at +- = +
    worst_s = 0.0
    for soil in ("A", "C"):
        er, sg = SOILS[soil]
        hs = HalfSpace(7e6, er, sg)
        kp, km = hs.kp, hs.km
        for rho, z, zp in [(3.0, 2.0, 1.0), (10.0, 1.0, 0.5), (1.0, 5.0, 3.0)]:
            J, _, _ = integrals_R(hs, rho, z, zp, shared="p", err=False)
            C1 = hs.C1
            r = (km * km) / (kp * kp)
            mine = {
                "IrhoV": C1 * r * J[3],
                "IzV": C1 * r * (J[4] + kp * kp * J[0]),
                "IrhoH": C1 * (J[2] + J[6]),
                "IphiH": -C1 * (J[5] + J[6]),
            }
            r1 = math.hypot(rho, z + zp)
            th = math.atan2(z + zp, rho)
            surf = ms.iv_surfaces_direct(
                hs.eps_t, kp, r1, th, rtol=1e-12, omega=hs.omega
            )
            phase = r1 * np.exp(1j * kp * r1)
            for k_ in mine:
                e = _relerr(mine[k_], complex(surf[k_]) / phase)
                worst_s = max(worst_s, e)
            lines.append(
                f"    surfaces soil {soil} rho={rho} z={z} z'={zp}: worst rel {worst_s:.2e}"
            )
    ok = worst_d < 1e-12 and worst_s < 1e-7
    _report(
        "G6 +-=+ anchor vs momwire",
        ok,
        f"D1/D2 worst rel {worst_d:.3e} (tol 1e-12); surfaces worst rel {worst_s:.3e} (tol 1e-7)",
    )
    for ln in lines:
        print(ln)
    return worst_d, worst_s


def diagnostics():
    """Not a gate -- contour/integrand health at the SPEC soils.

    Reports, per (soil, freq): the medium constants; how close the head
    detour passes to the lam = k_p branch point at the largest SPEC rho; the
    worst-case J0 growth e^{H rho} along the detour; and the smallest value
    the two Sommerfeld denominators (gamma_m + gamma_p) and
    (k_m^2 gamma_p + k_p^2 gamma_m) take anywhere on the head contour,
    normalized so a near-zero would show up as a near-pole.
    """
    print(
        "    soil  f      eps_t                     k_p       k_m                "
        "|k_m|/k_p  a       detour clr@rho=30  e^{H rho}  min|g_m+g_p|/|k|  "
        "min|k_m^2 g_p + k_p^2 g_m|/|k|^3"
    )
    for soil in ("A", "B", "C"):
        er, sg = SOILS[soil]
        for f in (7e6, 21e6):
            hs = HalfSpace(f, er, sg)
            hs.assert_decay()
            kp, km = hs.kp, hs.km
            a = 1.1 * max(kp, abs(km))
            rho = 30.0
            H = max(min(0.35 * a, 2.0 / rho), 1e-6 * a)
            clr = H * math.sin(math.pi * kp / a)
            t = np.linspace(1e-9, a, 20001)
            lam = t + 1j * H * np.sin(np.pi * t / a)
            gp = gamma(lam, kp)
            gm = gamma(lam, km)
            d1 = np.min(np.abs(gm + gp)) / max(kp, abs(km))
            d2 = np.min(np.abs(km * km * gp + kp * kp * gm)) / max(kp, abs(km)) ** 3
            print(
                f"    {soil}     {f / 1e6:>4.0f}   {hs.eps_t.real:8.3f}{hs.eps_t.imag:+9.3f}j   "
                f"{kp:.5f}   {km.real:+.5f}{km.imag:+.5f}j   {abs(km) / kp:7.3f}  "
                f"{a:7.4f}  {clr:12.5f}     {math.exp(H * rho):8.2f}   {d1:14.4e}   {d2:14.4e}"
            )
    print(
        "    (the head detour is deformed into the FIRST quadrant; both branch cuts\n"
        "     run DOWNWARD from +k_p / +k_m, so the deformed path crosses no cut and\n"
        "     no Zenneck pole is enclosed -- no pole extraction is used.)"
    )
    _pec_limit_probe()


def _pec_limit_probe():
    """Independent evidence for the image-dyad reading, no oracle involved.

    Take the +-=+ case (source AND observer above) and drive the ground toward
    a perfect conductor.  There C2 -> 1 and D1 = D2 -> 0, so the ENTIRE
    reflected field must be the classical image: a +z-hat element at the
    mirror point for a VED, a -x-hat element for an HED.  Score both readings
    of AGARD (4b) against that closed form.
    """
    print(
        "\n    PEC-limit probe (+-=+, sigma -> inf): the reflected field must "
        "become the classical image"
    )
    obs = (4.0, 0.0, 2.0)
    zp = 1.0
    print(
        "      sigma (S/m)   |k_m|/k_p   |rem|/|img|   rel err vs PEC image: "
        "mirror        literal"
    )
    for sg in (0.005, 5.0, 5e3, 5e6, 5e9):
        hs = HalfSpace(7e6, 13.0, sg)
        C1, kp, km = hs.C1, hs.kp, hs.km
        for kind in ("VED", "HED"):
            p_hat = np.array([1.0, 0, 0]) if kind == "HED" else np.array([0.0, 0, 1.0])
            C2 = (km * km - kp * kp) / (km * km + kp * kp)
            rem, _, _ = field_remainder(hs, obs, zp, kind, shared="p", err=False)
            d_img = np.asarray(obs, float) - np.array([0.0, 0.0, -zp])
            pec = -fs_field(C1, kp, p_hat * _MIRROR, d_img)
            got = {}
            for cv in ("mirror", "literal"):
                img = image_field(C1, kp, p_hat, obs, zp, convention=cv)
                got[cv] = C2 * img + rem
            frac = float(np.max(np.abs(rem))) / max(float(np.max(np.abs(pec))), 1e-300)
            if kind == "VED":
                print(
                    f"      {sg:<12g}  {abs(km) / kp:9.3g}   {frac:11.3e}   "
                    f"VED  {_relerr(got['mirror'], pec):.3e}   "
                    f"{_relerr(got['literal'], pec):.3e}"
                )
            else:
                print(
                    f"      {'':<12s}  {'':<9s}   {frac:11.3e}   "
                    f"HED  {_relerr(got['mirror'], pec):.3e}   "
                    f"{_relerr(got['literal'], pec):.3e}"
                )


def print_stats():
    print("\n===== quadrature health (whole run) =====")
    s = STATS
    print(f"  scalar-integral evaluations      : {s['n']}")
    print(f"  tail non-convergent (hit cap)    : {s['nonconv']}")
    print(f"  Wynn-epsilon acceleration used   : {s['accel']}")
    print(f"  max head sub-intervals           : {s['max_head_panels']}")
    print(f"  max tail panels                  : {s['max_tail_panels']}")
    print(f"  worst self-convergence estimate  : {s['worst_selfconv']:.3e}")
    print(f"    at (kind, eps_r, f, rho, z, z'): {s['worst_selfconv_where']}")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default=None)
    args = ap.parse_args(argv)
    t0 = time.time()
    order = ["DIAG", "G0", "G1", "G2", "G3", "G5", "G6", "G4", "G7"]
    if args.only:
        order = args.only.split(",")
    import gate_g4
    import gate_g7

    fns = {
        "DIAG": diagnostics,
        "G0": gate_sommerfeld_identity,
        "G1": gate_G1,
        "G2": gate_G2,
        "G3": gate_G3,
        "G5": gate_G5,
        "G6": gate_G6,
        "G4": lambda: gate_g4.gate_G4(_report),
        "G7": lambda: gate_g7.gate_G7(_report),
    }
    for g in order:
        print(f"\n===== {g} =====", flush=True)
        fns[g]()
    print_stats()
    print(f"\nTotal {time.time() - t0:.1f}s")
    nfail = sum(1 for _, ok, _ in _RESULTS if not ok)
    print("\n===== SUMMARY =====")
    for nm, ok, det in _RESULTS:
        print(f"  [{'PASS' if ok else 'FAIL'}] {nm}: {det}")
    return 1 if nfail else 0


if __name__ == "__main__":
    # Re-enter through the module object: `gate_g4` does `import buried_proto`,
    # and running this file directly would otherwise give it a SECOND module
    # instance whose STATS tally is separate from __main__'s.
    import buried_proto

    sys.exit(buried_proto.main())

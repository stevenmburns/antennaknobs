"""Ray geometry and wedge diffraction for the faceted-terrain far field
(issue #1373, the follow-on to #534).

The specular composer in ``engines/momwire.py`` is geometric optics: for
every direction it adds the antenna's direct radiation and one reflection
off a facet. Two things are missing there, and both are why the uphill band
below the slope angle is hatched on the slope page and why the downhill
curves on M0AGP's hillside pages have notches:

* nothing is ever **shadowed** — uphill below the slope angle the composer
  still adds a direct ray the crest blocks, and reports grazing cancellation
  where the sky is actually behind the hill;
* nothing is **diffracted** — where the specular point steps from one facet
  onto the next the field steps with it, and at a shadow boundary the field
  would switch off like a light.

This module supplies the pieces that fix both, for one azimuth cut at a
time (the composer treats each observation azimuth's terrain profile as a
two-dimensional problem, and so does this):

* the cut's break points and per-facet planes;
* visibility tests for the direct ray, the incident and reflected legs of a
  specular reflection, and a diffracted ray;
* the exact specular reflection off each facet as a *tilted mirror* — the
  antenna's reference point imaged across the facet's own plane, the
  reflected ray required to leave from a point inside the facet's span. The
  #534 composer located the specular point with the horizontal-mirror
  formula at the facet's mid-height and always picked *some* facet, which
  is exact for horizontal facets and increasingly wrong for a mast standing
  on a slope;
* the uniform-theory-of-diffraction (UTD) wedge coefficient at every break
  between facets, in Luebbers' form for lossy faces: the Kouyoumjian–Pathak
  four-term coefficient with the two faces' Fresnel reflection coefficients
  on the reflection terms and Fresnel transition functions on all four, so
  the total field is continuous across each shadow and reflection boundary
  (at a shadow boundary the diffracted field is exactly half the field the
  boundary switches off).

Conventions match ``terrain.py``: in a cut, ``x`` is metres outward from the
mast axis along the azimuth, ``z`` metres above the crest plane; the profile
starts at ``(0, 0)``. Elevation ``psi`` is measured from the horizontal;
the composer's zenith angle is ``theta = pi/2 - psi``. The source is the
antenna's reference point ``S = (0, h)`` with ``h`` the current-weighted
mean segment height above the crest plane — the same ``h_ref`` the specular
composer uses. Time convention ``exp(+j omega t)`` with far fields going
as ``exp(-jkr)/r``, which is the composer's ``exp(+jk r_hat . r')`` phase.

What this is not: no back-diffraction across the mast (an edge in the
opposite azimuth's cut scattering into this one), no double diffraction
(an edge's diffracted ray blocked by a further edge is simply dropped), no
surface wave, and the incident field at an edge is the antenna's far-field
radiation vector at that direction with ``1/s'`` decay — exact for edges
many antenna sizes away, an approximation for a break under the mast.
"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass

import numpy as np
from scipy.special import fresnel as _fresnel

from .terrain import Sector

# A finite facet whose end height differs from where the next one starts
# would be a vertical step; ``cliff_terrain`` spells that as a 1 mm run and
# so does this module when the infinite facet's height differs from the last
# break's.
_STEP_RUN = 1e-3
_EPS_ANGLE = 1e-9


# ---------------------------------------------------------------------------
# The cut's geometry
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Plane:
    """One facet as a mirror: ``p0`` its inner end, unit tangent ``t``
    pointing outward, unit normal ``n`` pointing into the air (``n_z > 0``),
    ``length`` (``inf`` for the last facet) and its medium."""

    p0: np.ndarray
    t: np.ndarray
    n: np.ndarray
    length: float
    eps_r: float
    sigma: float


@dataclass(frozen=True)
class Wedge:
    """An edge between two facets: its position ``p``, the angle ``a0`` of
    the 0-face (the inner facet, seen from the edge going back toward the
    mast), the exterior wedge parameter ``n`` (exterior angle ``n*pi``,
    measured from the 0-face through the air to the n-face), and the two
    faces' media."""

    p: np.ndarray
    a0: float
    n: float
    eps0: float
    sig0: float
    epsn: float
    sign: float
    sense: int = 1  # +1 front side of the cut, -1 the mirrored back side


def _side_vertices(sector: Sector) -> tuple[list[float], list[float]]:
    xs, zs = [0.0], [0.0]
    for f in sector.facets:
        if f.x1 is None:
            if abs(f.z1 - zs[-1]) > 0:
                # a vertical step into the infinite facet
                xs.append(xs[-1] + _STEP_RUN)
                zs.append(float(f.z1))
            break
        xs.append(float(f.x1))
        zs.append(float(f.z1))
    return xs, zs


def _side_planes(sector: Sector, sense: int) -> list[Plane]:
    """One sector's facets as planes in the full cut's coordinates: the
    front sector (``sense=+1``) at ``x > 0``, the back sector (``sense=-1``)
    mirrored to ``x < 0``. Each plane's ``p0`` is its end nearer the mast
    and ``t`` points away from the mast, so ``p0 + t * length`` is the outer
    end and consecutive planes meet there."""
    xs, zs = _side_vertices(sector)
    n_int = len(xs) - 1
    finite = [f for f in sector.facets if f.x1 is not None]
    last = sector.facets[-1]
    media = [(f.eps_r, f.sigma) for f in finite]
    if len(media) < n_int:
        media.append((last.eps_r, last.sigma))  # the step into the last facet
    out: list[Plane] = []
    for i in range(n_int):
        p0 = np.array([sense * xs[i], zs[i]])
        p1 = np.array([sense * xs[i + 1], zs[i + 1]])
        d = p1 - p0
        length = float(np.hypot(*d))
        t = d / length
        n = np.array([-t[1], t[0]])
        if n[1] < 0:
            n = -n
        eps, sig = media[i]
        # a subdivided ramp is one mirror: merge a facet into the previous
        # plane when it continues the same line with the same medium, so a
        # 48-facet ramp is one reflection and one pair of edges
        if out:
            prev = out[-1]
            if (
                np.allclose(prev.t, t, atol=1e-12)
                and prev.eps_r == eps
                and prev.sigma == sig
                and abs(float(np.dot(p0 - prev.p0, prev.n))) < 1e-9
            ):
                out[-1] = Plane(prev.p0, prev.t, prev.n, prev.length + length, eps, sig)
                continue
        out.append(Plane(p0, t, n, length, eps, sig))
    p0 = np.array([sense * xs[-1], zs[-1]])
    out.append(
        Plane(
            p0,
            np.array([float(sense), 0.0]),
            np.array([0.0, 1.0]),
            math.inf,
            last.eps_r,
            last.sigma,
        )
    )
    return out


def _side_wedges(planes_: list[Plane], sense: int) -> list[Wedge]:
    out: list[Wedge] = []
    for a, b in itertools.pairwise(planes_):
        p = a.p0 + a.t * a.length
        u0 = -a.t  # from the edge back toward the mast along the inner facet
        un = b.t  # from the edge away from the mast along the outer facet
        a0 = math.atan2(u0[1], u0[0])
        an = math.atan2(un[1], un[0])
        ext = (sense * (a0 - an)) % (2 * math.pi)
        n = ext / math.pi
        if abs(n - 1.0) < 1e-9:
            continue
        out.append(Wedge(p, a0, n, a.eps_r, a.sigma, b.eps_r, b.sigma, sense))
    return out


@dataclass(frozen=True)
class Cut:
    """The full two-dimensional profile through the mast for one observation
    azimuth: the sector in that azimuth at ``x > 0`` and the sector in the
    opposite azimuth mirrored to ``x < 0``. Observation directions always
    point to ``+x``; the back side matters because a facet behind the mast
    is the mirror that throws a mast-on-a-slope's radiation into the
    downhill sky, and its crest can diffract over the mast."""

    xb: np.ndarray
    zb: np.ndarray
    planes: tuple[Plane, ...]
    wedges: tuple[Wedge, ...]


def build_cut(front: Sector, back: Sector) -> Cut:
    fx, fz = _side_vertices(front)
    bx, bz = _side_vertices(back)
    xb = np.asarray([-x for x in bx[1:]][::-1] + fx)
    zb = np.asarray(bz[1:][::-1] + fz)
    pf = _side_planes(front, +1)
    pb = _side_planes(back, -1)
    return Cut(
        xb, zb, tuple(pf + pb), tuple(_side_wedges(pf, +1) + _side_wedges(pb, -1))
    )


def break_points(sector: Sector) -> tuple[np.ndarray, np.ndarray]:
    """One sector's vertices ``(x_b, z_b)`` from the mast axis outward,
    starting at ``(0, 0)`` (the front half of a cut)."""
    xs, zs = _side_vertices(sector)
    return np.asarray(xs), np.asarray(zs)


def planes(sector: Sector) -> list[Plane]:
    """One sector's facets as front-side planes."""
    return _side_planes(sector, +1)


def wedges(sector: Sector) -> list[Wedge]:
    """One sector's edges, front side; collinear breaks (a subdivided ramp)
    diffract nothing (``n == 1`` makes the coefficient vanish) and are
    skipped."""
    return _side_wedges(_side_planes(sector, +1), +1)


# ---------------------------------------------------------------------------
# Visibility
# ---------------------------------------------------------------------------


def ray_clear(px, pz, wx, wz, xb, zb, *, x_from=None):
    """Is the ray from ``(px, pz)`` in direction ``(wx, wz)`` (arrays, any
    common shape) clear of the profile vertices ``(xb, zb)``? A vertex at
    ``x > px`` (or ``x > x_from`` when given) blocks the ray if it lies
    above the ray's height there. Vertices behind the start are ignored.
    Rays going inward (``wx <= 0``) are treated as clear — this module only
    reads outward directions."""
    px, pz, wx, wz = np.broadcast_arrays(
        np.asarray(px, float),
        np.asarray(pz, float),
        np.asarray(wx, float),
        np.asarray(wz, float),
    )
    start = (
        px if x_from is None else np.broadcast_to(np.asarray(x_from, float), px.shape)
    )
    clear = np.ones(px.shape, dtype=bool)
    slope = np.where(wx > 0, wz / np.where(wx > 0, wx, 1.0), np.inf)
    for x, z in zip(xb, zb, strict=True):
        ahead = (x > start + 1e-9) & (wx > 0)
        zr = pz + (x - px) * slope
        clear &= ~(ahead & (z > zr + 1e-9))
    return clear


def segment_clear(px, pz, qx, qz, xb, zb):
    """Is the straight path from ``(px, pz)`` to ``(qx, qz)`` clear of the
    profile? Vertices strictly between the two x's block if above the
    chord."""
    px, pz, qx, qz = np.broadcast_arrays(
        np.asarray(px, float),
        np.asarray(pz, float),
        np.asarray(qx, float),
        np.asarray(qz, float),
    )
    clear = np.ones(px.shape, dtype=bool)
    lo, hi = np.minimum(px, qx), np.maximum(px, qx)
    dx = qx - px
    safe = np.where(np.abs(dx) > 1e-12, dx, 1.0)
    for x, z in zip(xb, zb, strict=True):
        between = (x > lo + 1e-9) & (x < hi - 1e-9)
        zc = pz + (x - px) * (qz - pz) / safe
        clear &= ~(between & (z > zc + 1e-9))
    return clear


# ---------------------------------------------------------------------------
# Specular reflections, facet by facet
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Reflection:
    """A specular ray path off one facet (``planes`` of length 1) or off two
    in sequence (length 2, the doubly reflected ray a concave corner such
    as a slope's toe sends skyward), for a set of source points ``src`` and
    elevations ``psi``. ``image`` (P, 2) is each source imaged across the
    planes in order; ``mask`` (P, T) marks where the path exists (every
    reflection point inside its facet, every leg clear of the profile);
    ``cos_tis`` are the cosines of the local incidence angle from each
    facet's normal, (P, T), in path order."""

    planes: tuple[Plane, ...]
    image: np.ndarray
    mask: np.ndarray
    cos_tis: tuple[np.ndarray, ...]

    @property
    def plane(self) -> Plane:
        return self.planes[0]

    @property
    def cos_ti(self) -> np.ndarray:
        return self.cos_tis[0]


def _sources(src, h=None):
    """Source points as (P, 2); a bare height ``h`` means one point on the
    mast axis, ``(0, h)``."""
    if src is None:
        src = np.array([[0.0, float(h)]])
    src = np.asarray(src, float)
    return src.reshape(-1, 2)


def _as_cut(obj) -> Cut:
    """A ``Cut`` as given, or a one-sided cut from a lone ``Sector``."""
    if isinstance(obj, Cut):
        return obj
    pf = _side_planes(obj, +1)
    xb, zb = break_points(obj)
    return Cut(xb, zb, tuple(pf), tuple(_side_wedges(pf, +1)))


def _line_key(pl: Plane):
    return (tuple(np.round(pl.n, 9)), round(float(np.dot(pl.p0, pl.n)), 6))


def reflections(
    cut, psi: np.ndarray, h: float | None = None, *, src=None
) -> list[Reflection]:
    """Every specular path from the source points (``src`` (P, 2), or the
    single point ``(0, h)``) toward elevations ``psi`` (radians above the
    horizontal): single reflections off each facet, then double reflections
    off each ordered pair of distinct facets. A path exists when the source
    (or its running image) is on the air side of each plane, each reflected
    direction leaves its plane on the air side, each reflection point lies
    within its facet's span, and no leg is blocked by the profile.

    Double reflections are what a concave corner (a slope meeting a plain)
    does with the rays that hit the slope: without them the toe wedge's
    diffraction coefficient would be patching a boundary the GO sum does not
    have, and the total would step there instead of at nothing."""
    cut = _as_cut(cut)
    S = _sources(src, h)  # (P, 2)
    psi = np.asarray(psi, float)
    w = np.stack([np.cos(psi), np.sin(psi)], axis=-1)  # (T, 2)
    xb, zb = cut.xb, cut.zb
    P, T = S.shape[0], psi.shape[0]
    out: list[Reflection] = []
    # Two facets on one line (the front and back halves of a flat plane,
    # meeting at the mast foot) would both claim the specular point that
    # sits exactly on their shared vertex; a path is claimed once, keyed on
    # the line(s) it reflects off.
    claimed: dict = {}

    def _claim(key, inside):
        prev = claimed.get(key)
        if prev is not None:
            inside = inside & ~prev
            claimed[key] = prev | inside
        else:
            claimed[key] = inside.copy()
        return inside

    wn_all = {id(pl): (w @ pl.n)[None, :] for pl in cut.planes}  # (1, T)
    for pl in cut.planes:
        d0 = (S - pl.p0[None, :]) @ pl.n  # (P,)
        above = d0 > 0.0
        if not np.any(above):
            continue
        image = S - 2.0 * d0[:, None] * pl.n[None, :]  # (P, 2)
        wn = wn_all[id(pl)]
        ok = above[:, None] & (wn > _EPS_ANGLE)
        lam = np.where(ok, d0[:, None] / np.where(ok, wn, 1.0), 0.0)  # (P, T)
        Q = image[:, None, :] + lam[..., None] * w[None, :, :]  # (P, T, 2)
        along = (Q - pl.p0) @ pl.t
        inside = ok & (along >= -1e-9) & (along <= pl.length + 1e-9)
        inside &= segment_clear(
            S[:, 0, None], S[:, 1, None], Q[..., 0], Q[..., 1], xb, zb
        )
        inside &= ray_clear(Q[..., 0], Q[..., 1], w[None, :, 0], w[None, :, 1], xb, zb)
        inside = _claim(_line_key(pl), inside)
        if np.any(inside):
            out.append(
                Reflection(
                    (pl,),
                    image,
                    inside,
                    (np.clip(np.broadcast_to(wn, (P, T)), 0.0, 1.0),),
                )
            )
    for A in cut.planes:
        dA = (S - A.p0[None, :]) @ A.n
        if not np.any(dA > 0.0):
            continue
        SA = S - 2.0 * dA[:, None] * A.n[None, :]
        for B in cut.planes:
            if B is A or _line_key(B) == _line_key(A):
                continue
            dAB = (SA - B.p0[None, :]) @ B.n
            good = (dA > 0.0) & (dAB > 0.0)
            if not np.any(good):
                continue
            SAB = SA - 2.0 * dAB[:, None] * B.n[None, :]
            wn = wn_all[id(B)]
            ok = good[:, None] & (wn > _EPS_ANGLE)
            lam2 = np.where(ok, dAB[:, None] / np.where(ok, wn, 1.0), 0.0)
            Q2 = SAB[:, None, :] + lam2[..., None] * w[None, :, :]
            along2 = (Q2 - B.p0) @ B.t
            ok &= (along2 >= -1e-9) & (along2 <= B.length + 1e-9)
            v1 = Q2 - SA[:, None, :]
            l1 = np.hypot(v1[..., 0], v1[..., 1])
            w1 = v1 / np.where(l1 > 0, l1, 1.0)[..., None]
            wn1 = w1 @ A.n
            ok &= wn1 > _EPS_ANGLE
            lam1 = np.where(ok, dA[:, None] / np.where(ok, wn1, 1.0), 0.0)
            ok &= lam1 < l1
            Q1 = SA[:, None, :] + lam1[..., None] * w1
            along1 = (Q1 - A.p0) @ A.t
            ok &= (along1 >= -1e-9) & (along1 <= A.length + 1e-9)
            ok &= segment_clear(
                S[:, 0, None], S[:, 1, None], Q1[..., 0], Q1[..., 1], xb, zb
            )
            ok &= segment_clear(Q1[..., 0], Q1[..., 1], Q2[..., 0], Q2[..., 1], xb, zb)
            ok &= ray_clear(
                Q2[..., 0], Q2[..., 1], w[None, :, 0], w[None, :, 1], xb, zb
            )
            ok = _claim((_line_key(A), _line_key(B)), ok)
            if np.any(ok):
                out.append(
                    Reflection(
                        (A, B),
                        SAB,
                        ok,
                        (
                            np.clip(wn1, 0.0, 1.0),
                            np.clip(np.broadcast_to(wn, (P, T)), 0.0, 1.0),
                        ),
                    )
                )
    if src is None:
        out = [
            Reflection(r.planes, r.image[0], r.mask[0], tuple(c[0] for c in r.cos_tis))
            for r in out
        ]
    return out


# ---------------------------------------------------------------------------
# UTD wedge diffraction (Kouyoumjian–Pathak, Luebbers' lossy faces)
# ---------------------------------------------------------------------------


def transition(X):
    """The UTD Fresnel transition function
    ``F(X) = 2j sqrt(X) exp(jX) int_{sqrt(X)}^{inf} exp(-j t^2) dt``,
    ``F -> 1`` for large ``X`` and ``F ~ sqrt(pi X) exp(j pi/4)`` for small
    ``X`` — the factor that keeps the total field continuous through a
    shadow or reflection boundary."""
    X = np.asarray(X, float)
    X = np.maximum(X, 1e-300)
    a = np.sqrt(X)
    z = a * math.sqrt(2.0 / math.pi)
    S, C = _fresnel(z)
    tail = (math.sqrt(math.pi) / 2.0) * np.exp(-1j * math.pi / 4.0) - math.sqrt(
        math.pi / 2.0
    ) * (C - 1j * S)
    return 2j * a * np.exp(1j * X) * tail


def _N_pm(beta, n, sign):
    """``N^{±}``: the integer nearest a solution of ``2πnN − β = ±π``."""
    return np.round((beta + sign * math.pi) / (2.0 * math.pi * n))


def _a_pm(beta, n, sign):
    """``a^{±}(β) = 2 cos²((2πnN^{±} − β)/2)``."""
    N = _N_pm(beta, n, sign)
    return 2.0 * np.cos((2.0 * math.pi * n * N - beta) / 2.0) ** 2


def _cot_F(arg, X):
    """``cot(arg) · F(X)`` with the boundary limit handled: both factors
    are singular/zero together at a shadow or reflection boundary."""
    arg = np.asarray(arg, float)
    s = np.sin(arg)
    small = np.abs(s) < 1e-7
    s_safe = np.where(small, 1.0, s)
    cot = np.cos(arg) / s_safe
    val = cot * transition(X)
    # limit at the boundary: n·[sqrt(2πkL) sgn(ε) − 2kLε e^{jπ/4}] e^{jπ/4}
    # is what the product tends to; the ε→0 part is the leading term, whose
    # sign flips across the boundary — the finite jump the neighbouring GO
    # term cancels. Evaluate it from a nudged argument instead of the
    # formula so the two sides are symmetric.
    if np.any(small):
        arg_n = np.where(small, np.where(arg >= 0, 1e-7, -1e-7), arg)
        cot_n = np.cos(arg_n) / np.sin(arg_n)
        val = np.where(small, cot_n * transition(X), val)
    return val


def fresnel_grazing(theta, eps_c):
    """Reflection coefficients ``(R_h, R_v)`` of a lossy half-space for a
    ray at grazing angle ``theta`` (radians from the face plane), complex
    permittivity ``eps_c``. The same formulas as the composer's, written in
    the wedge's grazing angle; ``sin`` and ``cos²`` make them symmetric
    about ``π/2`` so a face angle past ``π/2`` reads correctly."""
    st = np.sin(theta)
    Q = np.sqrt(eps_c - np.cos(theta) ** 2)
    R_h = (st - Q) / (st + Q)
    R_v = (eps_c * st - Q) / (eps_c * st + Q)
    return R_h, R_v


def wedge_coefficients(k, L, n, phi, phi_p, eps0_c, epsn_c):
    """Heuristic UTD diffraction coefficients ``(D_soft, D_hard)`` for a
    wedge of exterior angle ``n·π`` with lossy faces of complex
    permittivity ``eps0_c`` (the 0-face) and ``epsn_c`` (the n-face), at
    normal incidence (``β0 = π/2``), distance parameter ``L`` (the
    source–edge distance for a far-field observer), observation angle
    ``phi`` and incidence angle ``phi_p`` measured from the 0-face through
    the air. Soft = E parallel to the edge (uses ``R_h``), hard = E in the
    plane of incidence (uses ``R_v``).

    Luebbers' form puts the 0-face coefficient on the term whose boundary
    is the 0-face reflection and the n-face's on the n-face term. The two
    incident-field terms also carry boundaries when the wedge is concave
    (``n < 1``): the integers ``N^{±}`` are then non-zero exactly where the
    boundary belongs to a ray that has reflected off BOTH faces before
    leaving, so those terms carry ``(R_0 R_n)^{|N|}`` — the amplitude of
    the multiply reflected ray they switch — in the spirit of Holm's
    extension. With ``R = ∓1`` every factor is a sign and the perfectly
    conducting Kouyoumjian–Pathak coefficients come back."""
    phi = np.asarray(phi, float)
    phi_p = np.asarray(phi_p, float)
    C = -np.exp(-1j * math.pi / 4.0) / (2.0 * n * math.sqrt(2.0 * math.pi * k))
    dm = phi - phi_p
    dp = phi + phi_p
    kL = k * L
    D1 = _cot_F((math.pi + dm) / (2.0 * n), kL * _a_pm(dm, n, +1))
    D2 = _cot_F((math.pi - dm) / (2.0 * n), kL * _a_pm(dm, n, -1))
    D3 = _cot_F((math.pi + dp) / (2.0 * n), kL * _a_pm(dp, n, +1))  # n-face RB
    D4 = _cot_F((math.pi - dp) / (2.0 * n), kL * _a_pm(dp, n, -1))  # 0-face RB
    n1 = np.abs(_N_pm(dm, n, +1))
    n2 = np.abs(_N_pm(dm, n, -1))
    n3 = np.maximum(np.abs(_N_pm(dp, n, +1)) - 1.0, 0.0)
    n4 = np.abs(_N_pm(dp, n, -1))
    R0_h, R0_v = fresnel_grazing(phi_p, eps0_c)
    Rn_h, Rn_v = fresnel_grazing(n * math.pi - phi, epsn_c)
    out = []
    for R0, Rn in ((R0_h, Rn_h), (R0_v, Rn_v)):
        both = R0 * Rn
        out.append(
            C
            * (both**n1 * D1 + both**n2 * D2 + Rn * both**n3 * D3 + R0 * both**n4 * D4)
        )
    return out[0], out[1]


@dataclass(frozen=True)
class Diffraction:
    """One edge's diffracted contribution for source points ``src`` (P, 2)
    and elevations ``psi`` (T): the edge position ``p``, each source's
    distance ``s_p`` (P,) and unit direction ``d`` (P, 2) to the edge, the
    soft/hard coefficients (P, T) already carrying ``exp(-jk s')/sqrt(s')``,
    and the mask (P, T) of the source–edge legs that are clear and the
    diffracted rays that clear the rest of the profile."""

    wedge: Wedge
    s_p: np.ndarray
    d: np.ndarray
    D_soft: np.ndarray
    D_hard: np.ndarray
    mask: np.ndarray


def diffractions(
    cut,
    psi: np.ndarray,
    h: float | None = None,
    k: float = None,
    omega: float = None,
    eps0=None,
    *,
    src=None,
):
    """Every non-collinear edge's UTD contribution toward elevations ``psi``
    for the source points (``src`` (P, 2), or ``(0, h)``). Sources an edge
    cannot see (incident leg blocked) are masked, as are observation
    directions whose diffracted ray is blocked further out."""
    from .engines.momwire import EPS0 as _EPS0  # noqa: PLC0415 — avoid a cycle at import

    cut = _as_cut(cut)
    S = _sources(src, h)
    eps0 = _EPS0 if eps0 is None else eps0
    psi = np.asarray(psi, float)
    xb, zb = cut.xb, cut.zb
    w = np.stack([np.cos(psi), np.sin(psi)], axis=-1)
    out: list[Diffraction] = []
    for wg in cut.wedges:
        v = wg.p[None, :] - S  # (P, 2)
        s_p = np.hypot(v[:, 0], v[:, 1])
        seen = s_p > 1e-9
        d = v / np.where(seen, s_p, 1.0)[:, None]
        seen &= segment_clear(S[:, 0], S[:, 1], wg.p[0], wg.p[1], xb, zb)
        if not np.any(seen):
            continue
        # angles from the 0-face through the air; the back side of the cut
        # is a mirror image, so its angles run the other way round
        phi_p = (wg.sense * (wg.a0 - np.arctan2(-d[:, 1], -d[:, 0]))) % (
            2 * math.pi
        )  # (P,)
        phi = (wg.sense * (wg.a0 - psi)) % (2 * math.pi)  # (T,)
        in_air = (phi[None, :] <= wg.n * math.pi + 1e-9) & (
            phi_p[:, None] <= wg.n * math.pi + 1e-9
        )
        e0 = wg.eps0 - 1j * wg.sig0 / (omega * eps0)
        en = wg.epsn - 1j * wg.sign / (omega * eps0)
        Ds, Dh = wedge_coefficients(
            k, s_p[:, None], wg.n, phi[None, :], phi_p[:, None], e0, en
        )
        scale = (np.exp(-1j * k * s_p) / np.sqrt(np.where(seen, s_p, 1.0)))[:, None]
        clear_out = ray_clear(wg.p[0], wg.p[1], w[:, 0], w[:, 1], xb, zb)[None, :]
        mask = seen[:, None] & in_air & clear_out
        if src is None:
            out.append(
                Diffraction(wg, s_p[0], d[0], (Ds * scale)[0], (Dh * scale)[0], mask[0])
            )
        else:
            out.append(Diffraction(wg, s_p, d, Ds * scale, Dh * scale, mask))
    return out


def direct_visible(
    cut, psi: np.ndarray, h: float | None = None, *, src=None
) -> np.ndarray:
    """Mask (P, T) of source points whose direct ray toward each elevation
    clears the profile (``(T,)`` for a single height ``h``)."""
    cut = _as_cut(cut)
    S = _sources(src, h)
    psi = np.asarray(psi, float)
    m = ray_clear(
        S[:, 0, None],
        S[:, 1, None],
        np.cos(psi)[None, :],
        np.sin(psi)[None, :],
        cut.xb,
        cut.zb,
    )
    return m[0] if src is None else m

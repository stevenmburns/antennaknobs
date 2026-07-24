"""Faceted-terrain far-field ground (issue #534).

A terrain ground describes the surface *around* the antenna site as a
piecewise-linear height profile per azimuth sector, each facet carrying its
own medium. It is part of the **ground model**, not the antenna (a design
should be droppable onto any QTH) and not the solver (terrain never touches
the MoM matrix): the engine maps ``("terrain", Terrain(...))`` into

  - the impedance/current solve: flat Sommerfeld ground with the *crest*
    facet's medium (near-field ground interaction is crest-local), and
  - the far-field composition: per-direction specular-facet reflection —
    find the facet the specular point lands on, tilt the incidence angle by
    the facet slope, apply that facet's Fresnel coefficients, and add the
    facet's height offset to the reflected path phase.

Conventions
-----------
- Distances ``x`` are metres outward from the mast axis along the azimuth
  cut; heights ``z`` are metres relative to the crest plane (the engine's
  ``ground_z``), negative below it. The profile starts at ``(x=0, z=0)``.
- Azimuths are degrees CCW from +x, matching the engine's ``phi``.
- A facet's ``x1=None`` means it extends to infinity; every sector's last
  facet must be infinite (the terrain covers the whole ground plane).
- The specular point for elevation ``psi`` sits ``(h_ref - z)/tan(psi)``
  out from the mast; facets are scanned outward and the first one whose
  span contains its own specular point wins. ``h_ref`` is the reference
  source height (the engine uses the current-weighted mean segment height).

The flat single-facet terrain reproduces the plain ``("finite", eps, sigma)``
ground bit-for-bit — that is acceptance gate 1 of issue #534 and a test.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Facet:
    """One span of the terrain cut: from the previous facet's outer edge
    (or the mast axis) out to ``x1``, ending at height ``z1``."""

    x1: float | None  # outer edge, m from the mast axis; None = infinity
    z1: float  # surface height at x1, m relative to the crest plane
    eps_r: float
    sigma: float

    def __post_init__(self):
        if self.x1 is not None and self.x1 <= 0:
            raise ValueError(f"facet x1 must be positive, got {self.x1}")
        if self.eps_r < 1:
            raise ValueError(f"facet eps_r must be >= 1, got {self.eps_r}")
        if self.sigma < 0:
            raise ValueError(f"facet sigma must be >= 0, got {self.sigma}")


@dataclass(frozen=True)
class Sector:
    """The terrain cut applied over the CCW azimuth arc az0 -> az1 (deg)."""

    az0: float
    az1: float
    facets: tuple[Facet, ...]

    def __post_init__(self):
        object.__setattr__(self, "facets", tuple(self.facets))
        if not self.facets:
            raise ValueError("sector needs at least one facet")
        if self.facets[-1].x1 is not None:
            raise ValueError("the last facet must be infinite (x1=None)")
        xs = [f.x1 for f in self.facets[:-1]]
        if any(f is None for f in xs):
            raise ValueError("only the last facet may be infinite")
        if any(b <= a for a, b in zip(xs, xs[1:])):
            raise ValueError(f"facet edges must increase outward, got {xs}")

    @property
    def arc_deg(self) -> float:
        a = (self.az1 - self.az0) % 360.0
        return a if a > 0 else 360.0


@dataclass(frozen=True)
class Terrain:
    """A full-circle set of terrain sectors. Sectors must tile 360 degrees
    and agree on the crest (innermost facet) medium — that medium is the
    flat-Sommerfeld ground the impedance solve runs on."""

    sectors: tuple[Sector, ...]

    def __post_init__(self):
        object.__setattr__(self, "sectors", tuple(self.sectors))
        if not self.sectors:
            raise ValueError("terrain needs at least one sector")
        if abs(sum(s.arc_deg for s in self.sectors) - 360.0) > 1e-9:
            raise ValueError(
                "sectors must tile 360 deg, got arcs "
                f"{[s.arc_deg for s in self.sectors]}"
            )
        # No-overlap: walking CCW from each sector's start must land on
        # another sector's start (single-cover tiling).
        starts = sorted(s.az0 % 360.0 for s in self.sectors)
        ends = sorted((s.az0 + s.arc_deg) % 360.0 for s in self.sectors)
        if any(abs(a - b) > 1e-9 for a, b in zip(starts, ends)):
            raise ValueError("sector arcs overlap or leave a gap")
        m0 = self.crest_medium
        for s in self.sectors:
            m = (s.facets[0].eps_r, s.facets[0].sigma)
            if m != m0:
                raise ValueError(
                    "all sectors must share the crest medium (it is the "
                    f"impedance-solve ground): {m} != {m0}"
                )

    @property
    def crest_medium(self) -> tuple[float, float]:
        f = self.sectors[0].facets[0]
        return (f.eps_r, f.sigma)

    def sector_for(self, phi_deg):
        """Vectorized sector index per azimuth (degrees)."""
        phi = np.asarray(phi_deg, dtype=float) % 360.0
        idx = np.full(phi.shape, -1, dtype=int)
        for i, s in enumerate(self.sectors):
            rel = (phi - s.az0) % 360.0
            idx = np.where((idx < 0) & (rel < s.arc_deg - 1e-12), i, idx)
        # Boundary directions (rel == arc) belong to the next sector; any
        # residual -1 can only be a float-boundary artifact — assign to the
        # sector whose start it sits on.
        if np.any(idx < 0):
            for i, s in enumerate(self.sectors):
                rel = (phi - s.az0) % 360.0
                idx = np.where((idx < 0) & (rel <= s.arc_deg + 1e-9), i, idx)
        return idx


def facet_arrays(sector: Sector):
    """(x0, x1, z0, z1, beta, eps, sigma) numpy views of a sector's facets.
    ``beta`` is the downward tilt in radians (positive = surface descends
    outward); the infinite facet's x1 is +inf."""
    n = len(sector.facets)
    x0 = np.empty(n)
    x1 = np.empty(n)
    z0 = np.empty(n)
    z1 = np.empty(n)
    eps = np.empty(n)
    sig = np.empty(n)
    prev_x, prev_z = 0.0, 0.0
    for i, f in enumerate(sector.facets):
        x0[i], z0[i] = prev_x, prev_z
        x1[i] = math.inf if f.x1 is None else f.x1
        z1[i] = f.z1
        eps[i], sig[i] = f.eps_r, f.sigma
        prev_x, prev_z = x1[i], f.z1
    with np.errstate(invalid="ignore"):
        beta = np.arctan2(z0 - z1, x1 - x0)  # inf run -> beta 0 for last facet
    beta[np.isinf(x1)] = 0.0
    return x0, x1, z0, z1, beta, eps, sig


def specular_cut(sector: Sector, theta, h_ref):
    """Per-direction reflection geometry for one sector.

    theta: zenith angles, radians, array. h_ref: source reference height
    above the crest plane, metres.

    Returns (z_f, beta, eps_r, sigma) arrays over theta: the surface height
    at the specular point (relative to the crest plane), the facet's
    downward tilt, and the facet medium. Facets are scanned outward; the
    first facet whose span contains its own specular point wins (the
    infinite outer facet catches everything else).
    """
    theta = np.asarray(theta, dtype=float)
    x0, x1, z0, z1, beta, eps, sig = facet_arrays(sector)
    zmid = np.where(np.isinf(x1), z1, 0.5 * (z0 + z1))
    tan_t = np.tan(np.clip(theta, 0.0, np.pi / 2 - 1e-12))

    # x_s per (theta, facet): specular distance using each facet's own height.
    x_s = (h_ref - zmid[None, :]) * tan_t[..., None]
    hit = x_s <= x1[None, :]
    # First outward hit per theta (argmax of the boolean scan; the last
    # facet's x1=inf guarantees at least one True).
    fi = np.argmax(hit, axis=-1)

    xs = np.take_along_axis(x_s, fi[..., None], axis=-1)[..., 0]
    fx0, fx1 = x0[fi], x1[fi]
    fz0, fz1 = z0[fi], z1[fi]
    fbeta = beta[fi]
    run = fx1 - fx0
    frac = np.zeros_like(xs)
    finite = np.isfinite(run) & (run > 0)
    frac[finite] = np.clip((xs[finite] - fx0[finite]) / run[finite], 0.0, 1.0)
    z_f = np.where(np.isfinite(run), fz0 + frac * (fz1 - fz0), fz1)
    return z_f, fbeta, eps[fi], sig[fi]


def flat_terrain(eps_r: float, sigma: float) -> Terrain:
    """The degenerate single-facet terrain — must reproduce the plain
    ("finite", eps_r, sigma) ground exactly (issue #534 gate 1)."""
    return Terrain(
        sectors=(Sector(az0=0.0, az1=360.0, facets=(Facet(None, 0.0, eps_r, sigma),)),)
    )


def cliff_terrain(
    *,
    edge: float,
    drop: float,
    inner: tuple[float, float],
    outer: tuple[float, float],
    azimuth: float = 0.0,
    arc: float = 360.0,
) -> Terrain:
    """A single vertical cliff: ``inner`` medium out to ``edge`` m, then a
    sheer drop to ``outer`` medium ``drop`` m below — the NEC-2 GD-card
    geometry (#534 gate 2). ``arc`` < 360 restricts the cliff to a sector
    facing ``azimuth`` (the rest stays flat inner medium)."""
    eps_i, sig_i = inner
    eps_o, sig_o = outer
    cliff = Sector(
        az0=azimuth - arc / 2,
        az1=azimuth + arc / 2,
        facets=(
            Facet(edge, 0.0, eps_i, sig_i),
            # near-vertical drop: 1 mm of run per `drop` of fall keeps the
            # facet edges strictly increasing without a degenerate span
            Facet(edge + 1e-3, -drop, eps_i, sig_i),
            Facet(None, -drop, eps_o, sig_o),
        ),
    )
    if arc >= 360.0:
        return Terrain(sectors=(cliff,))
    flat = Sector(
        az0=azimuth + arc / 2,
        az1=azimuth - arc / 2,
        facets=(Facet(None, 0.0, eps_i, sig_i),),
    )
    return Terrain(sectors=(cliff, flat))


def levee_terrain(
    *,
    crest_width: float,
    slope_deg: float,
    drop_water: float,
    drop_land: float,
    water: tuple[float, float] = (80.0, 0.005),
    land: tuple[float, float] = (13.0, 0.005),
    crest: tuple[float, float] | None = None,
    water_azimuth: float = 0.0,
) -> Terrain:
    """The motivating QTH (issues #534/#535): a levee crest with 20-ish
    degree slopes, water ``drop_water`` m below on the side facing
    ``water_azimuth`` and land ``drop_land`` m below on the other.

    The crest and both slopes are earth (``crest``, defaulting to the land
    medium); the water medium starts at the water-side toe.
    """
    crest = land if crest is None else crest
    half = crest_width / 2.0
    run = 1.0 / math.tan(math.radians(slope_deg))

    def side(drop, toe_medium):
        eps_t, sig_t = toe_medium
        return (
            Facet(half, 0.0, *crest),
            Facet(half + drop * run, -drop, *crest),
            Facet(None, -drop, eps_t, sig_t),
        )

    return Terrain(
        sectors=(
            Sector(
                az0=water_azimuth - 90.0,
                az1=water_azimuth + 90.0,
                facets=side(drop_water, water),
            ),
            Sector(
                az0=water_azimuth + 90.0,
                az1=water_azimuth + 270.0,
                facets=side(drop_land, land),
            ),
        )
    )

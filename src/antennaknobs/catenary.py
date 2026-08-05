"""Hanging-chain equilibrium: the shape a real wire takes under its own weight.

Every catalog wire in a design is a perfectly straight line, but a wire strung
between an apex and a rigging point hangs in a catenary set by its weight per
metre and how it is tensioned.  This module is the pure-geometry half of issue
#698: given a serial chain of segments — each with a fixed arc length and a
weight per metre — and one of two rig closures, it returns the chain's actual
shape in its own vertical plane.

Nothing here imports engines, the builder, the network spec, or the web layer:
it is 2-D statics and closed forms only.  The design layer (a later unit)
embeds the returned plane curve into 3-D at some azimuth and emits it as a
chord polyline.

Coordinates and sign conventions
--------------------------------
Work in the chain's own vertical plane: ``x`` runs horizontally in the
direction the chain travels, ``z`` is up.  Gravity is ``-z``.

The internal tension state at arc position ``s`` is the vector

    t(s) = (H, V(s))

meaning *the force the downstream material exerts on the upstream material* —
it pulls forward, along increasing arc length.  Statics on an element gives
``dt/ds = (0, +w)``, so

  * ``H`` — the horizontal component — is **constant along the whole chain**,
    and is the single scalar that sets the catenary's shape; and
  * ``V(s) = V0 + w·s`` accumulates the weight hung below.

``H > 0`` always, which also makes ``x`` strictly increasing along the chain
(``dx/ds = H/T > 0``).  A chain hanging straight down has ``H = 0``: a real
equilibrium, but a degenerate one this formulation cannot express, so the
solvers reject it with an explicit error rather than limping toward it.

The *support* forces reported on :class:`ChainSolution` follow from the same
convention: the apex support must supply ``-t(0)`` and the far support ``+t(L)``
so that

    F_apex + F_end = (0, Σ Lᵢ·wᵢ)

— horizontal components cancel exactly, verticals sum to the total weight.
That identity is the module's cheapest global correctness check and is
asserted in the tests.

Closed forms
------------
With ``a = H/w`` the catenary parameter and ``v = V/H`` the local slope:

    z(x) = a·cosh((x − x_v)/a) + c      s(x) = a·sinh((x − x_v)/a)
    T(x) = H·cosh((x − x_v)/a) = w·(z(x) − c) = √(H² + V²)

Marching a segment means: from the start position and ``(H, V0)`` advance the
arc length ``L`` and read off the end position and ``V1 = V0 + w·L``.  The
displacement over an arc length ``s`` is, exactly,

    Δx = a·(asinh(v₁) − asinh(v₀))      Δz = (T₁ − T₀)/w

Note that ``Δz`` never evaluates ``cosh`` — the naive ``a·cosh(x/a)`` form
overflows long before a taut wire is taut enough to matter.  See "Numerics".

Architecture: a swappable marching kernel
-----------------------------------------
The solve is split into

  1. a **marching kernel** (:func:`march_continuous`) that turns
     ``(start, (H, V0), segments)`` into per-segment polylines and end states,
     and
  2. a **2-unknown shooting wrapper** that hunts for the ``(H, V0)`` satisfying
     the rig closure.

Only the continuous closed-form kernel ships now.  Keeping it behind the
:class:`MarchKernel` call signature is deliberate: a *discrete funicular*
kernel (per-node force balance) slots in behind exactly the same interface
when point masses — insulators, a hanging feedline — or per-segment wind/ice
loads are wanted, and those break the closed forms but not the shooting
wrapper.  The continuous kernel ships first because it makes the mechanical
shape exact and independent of chord count: a convergence ladder then refines
only the *electrical* discretization, never a moving geometric target (the
#606 lesson — do not let a discretization parameter read as physics).

Deliberately out of scope, stated honestly:

  * **Wire elasticity.**  Copper stretch is second-order at these tensions and
    an inextensible chain stays closed-form.  A stretching chain couples the
    arc length to the tension and turns every march into an inner solve.
  * **Wind and ice loading.**  This is the follow-up the kernel seam exists
    for: a transverse distributed load is not a vertical-plane catenary.
  * **Ground contact of a slack wire.**  A wire that touches the ground needs
    a constrained energy minimization; the catenary simply cannot express the
    unilateral contact condition, and pretending otherwise would silently
    return a shape that passes below grade.
  * **Non-serial topologies** — branches, sliding pulleys, multi-wire
    halyards.  Those need the fully assembled per-node force-balance system,
    which is not worth building until such a design actually appears.

Numerics: the taut limit
------------------------
As a wire is pulled taut, ``a = H/w`` grows without bound and every naive form
falls over.  The governing small parameter is

    d = w·L/H = L/a

— the segment's arc length measured in catenary parameters, i.e. how much the
chain bends over the segment.  For ``d`` small the exact displacement formulas
subtract two nearly equal numbers of size ``a``, so their *absolute* error is
``eps·a``: at ``a = 10¹⁰ m`` that is microns of garbage in a millimetre-scale
answer.  Below :data:`TAUT_D` the module therefore switches to a midpoint
Taylor expansion in ``d`` (the small-sag / parabolic expansion, carried to
``d⁴``), which is cancellation-free and reduces to a straight line at ``d = 0``
— so massless segments (``w = 0``, a taut halyard) fall out of the same code
path with no special case.  The threshold is chosen where the two branches
agree to ~1e-13 relative; :func:`chord_sag` uses a second, tighter threshold
because a perpendicular sag is a far more cancellation-sensitive quantity than
a position.  Both are exercised by continuity tests that straddle them.

Issue #698.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Sequence

import numpy as np

# Standard gravity, m/s².  Catalog wire weights are grams per metre; the chain
# math wants newtons per metre.
GRAVITY = 9.80665

# Switch to the midpoint series when d = w·L/H falls below this.  Rationale:
# at d = 1e-3 the exact form's cancellation error is ~eps/d ≈ 2e-13 relative
# while the series truncates at O(d⁴/1920) ≈ 5e-16 relative, so the two agree
# to ~2e-13 and the crossover is seamless.  Larger d and the series would
# truncate visibly; smaller and the exact form would already be losing digits.
TAUT_D = 1.0e-3

# The same crossover for the chord-perpendicular sag, which is a *difference*
# of O(L²) products divided by O(L) — its absolute error is ~eps·L against a
# sag of ~L·d/8, i.e. a relative error of ~8·eps/d.  Matching that against the
# transverse-string formula's O(d²) truncation puts the balance point two
# decades lower than TAUT_D: at d = 1e-5 both branches carry ~1e-10 relative
# error.  A single shared threshold would leave a visible 1e-6 step in the sag.
TAUT_SAG_D = 1.0e-5

# Newton's residuals are non-dimensionalised (positions by the chain's total
# length, forces by whichever of the rope pull and the chain's own weight is
# larger), so one tolerance covers both closures at any scale.
_NEWTON_TOL = 1.0e-11
_NEWTON_MAX_ITER = 80


def weight_n_per_m(weight_g_per_m: float) -> float:
    """Catalog wire weight (grams per metre) → chain load (newtons per metre)."""
    return weight_g_per_m * 1.0e-3 * GRAVITY


# --------------------------------------------------------------------------
# Segment description and kernel outputs
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ChainSegment:
    """One inextensible span of the serial chain.

    ``length_m`` is the *arc* length — the cut length of wire or rope, which is
    a fixed input and never a solver unknown (the electrical knob must not move
    when the tension knob does).  ``weight_n_per_m`` is the distributed load;
    ``0.0`` means a massless segment, which marches as a straight line.

    A future discrete kernel will read extra fields here (a point mass at the
    downstream junction, a transverse wind load); the continuous kernel needs
    only these two.
    """

    length_m: float
    weight_n_per_m: float
    name: str = ""

    def __post_init__(self) -> None:
        if not (self.length_m > 0.0):
            raise ValueError(
                f"chain segment {self.name or '?'!r}: arc length must be "
                f"positive, got {self.length_m!r} m"
            )
        if self.weight_n_per_m < 0.0:
            raise ValueError(
                f"chain segment {self.name or '?'!r}: weight per metre must be "
                f"non-negative, got {self.weight_n_per_m!r} N/m"
            )


@dataclass(frozen=True, eq=False)
class SegmentMarch:
    """Raw kernel output for one segment: samples, end position, end tension.

    ``points`` is ``(n, 2)`` of ``(x, z)`` sampled uniformly in *arc length*
    from the segment's start to its end inclusive.  ``end_tension`` is the
    forward internal tension ``(H, V1)`` handed to the next segment.

    ``eq=False`` (as in :class:`~antennaknobs.touchstone.Touchstone`) because
    the array makes value equality meaningless and unhashable.
    """

    points: np.ndarray
    end_point: tuple[float, float]
    end_tension: tuple[float, float]


#: Signature every marching kernel must honour.  The continuous kernel is
#: :func:`march_continuous`; a discrete funicular kernel will present the same
#: call and return the same objects, so the shooting wrapper never changes.
MarchKernel = Callable[
    [tuple[float, float], tuple[float, float], Sequence[ChainSegment], int],
    "tuple[SegmentMarch, ...]",
]


# --------------------------------------------------------------------------
# Continuous catenary kernel
# --------------------------------------------------------------------------


def _offset(h: float, v0: float, w: float, s: float) -> tuple[float, float]:
    """Displacement ``(Δx, Δz)`` after advancing arc length ``s``.

    Exact catenary displacement, written to avoid the two ways the textbook
    form dies in the taut limit: ``Δz`` is ``(T₁ − T₀)/w`` rather than a
    difference of ``a·cosh`` (no overflow), and below :data:`TAUT_D` both
    components come from a midpoint Taylor expansion in ``d = w·s/h`` (no
    cancellation).  ``w = 0`` lands in the series branch with ``d = 0`` and
    yields the straight-line result exactly.
    """
    if s == 0.0:
        return 0.0, 0.0
    slope0 = v0 / h
    d = w * s / h
    slope1 = slope0 + d
    if abs(d) < TAUT_D:
        # Midpoint expansion kills the even-order derivatives, so the leading
        # correction is O(d²) and the next is O(d⁴):
        #   Δx = s·[f'(m) + f'''(m)·d²/24 + f⁽⁵⁾(m)·d⁴/1920],  f = asinh
        #   Δz = s·[g'(m) + g'''(m)·d²/24 + g⁽⁵⁾(m)·d⁴/1920],  g = √(1+v²)
        m = 0.5 * (slope0 + slope1)
        m2 = m * m
        g = math.sqrt(1.0 + m2)
        g5 = g**5
        g9 = g**9
        d2 = d * d
        d4 = d2 * d2
        fx = (
            1.0 / g
            + (2.0 * m2 - 1.0) / g5 * (d2 / 24.0)
            + (9.0 - 72.0 * m2 + 24.0 * m2 * m2) / g9 * (d4 / 1920.0)
        )
        fz = (
            m / g
            + (-3.0 * m) / g5 * (d2 / 24.0)
            + (45.0 * m - 60.0 * m2 * m) / g9 * (d4 / 1920.0)
        )
        return s * fx, s * fz
    a = h / w
    dx = a * (math.asinh(slope1) - math.asinh(slope0))
    dz = (math.hypot(h, v0 + w * s) - math.hypot(h, v0)) / w
    return dx, dz


def chord_sag(h: float, v0: float, w: float, length_m: float) -> float:
    """Max distance of a catenary segment from its own chord, measured ⟂.

    A catenary is convex (``z'' = cosh(·)/a > 0``), so the arc lies entirely
    below its chord and the maximum offset is unsigned and unambiguous.  It
    occurs where the tangent is parallel to the chord, i.e. where the local
    slope ``V/H`` equals the chord slope — the mean value theorem guarantees
    such a point exists because ``x`` is monotone.

    Below :data:`TAUT_SAG_D` the exact cross-product form has cancelled away
    its significant digits, so the sag comes from the taut-string result
    ``q·C²/(8·T)`` with the transverse load ``q = w·Δx/C``:

        sag ≈ w·Δx·C/(8·T_mid)

    which reduces to the familiar ``w·d²/(8H)`` for a level span.
    """
    if w == 0.0:
        return 0.0
    dx, dz = _offset(h, v0, w, length_m)
    chord = math.hypot(dx, dz)
    if chord == 0.0:
        return 0.0
    if w * length_m / h < TAUT_SAG_D:
        t_mid = math.hypot(h, v0 + 0.5 * w * length_m)
        return w * dx * chord / (8.0 * t_mid)
    # Tangent parallel to the chord: V* = H·(Δz/Δx), reached at arc length
    # s* = (V* − V0)/w.  Its perpendicular offset is the 2-D cross product
    # with the unit chord.
    v_star = h * (dz / dx)
    s_star = (v_star - v0) / w
    s_star = min(max(s_star, 0.0), length_m)
    px, pz = _offset(h, v0, w, s_star)
    return abs((dx * pz - dz * px) / chord)


def march_continuous(
    start: tuple[float, float],
    tension: tuple[float, float],
    segments: Sequence[ChainSegment],
    samples_per_segment: int = 33,
) -> tuple[SegmentMarch, ...]:
    """March a serial chain with the continuous closed-form catenary.

    Given the start point, the forward internal tension ``(H, V0)`` there, and
    the segment list, walk segment by segment: each one is an exact catenary
    arc of its own parameter ``a = H/wᵢ`` (a straight line where ``wᵢ = 0``),
    joined to the next at the position and tension the previous one ended at.
    ``H`` is shared by every segment — that is what makes the chain serial and
    the whole problem two-unknown.

    Raises :class:`ValueError` for ``H ≤ 0`` (a vertical hanging chain; see the
    module docstring) or a sample count below 2.
    """
    h, v = tension
    if not (h > 0.0):
        raise ValueError(
            f"horizontal tension must be positive, got H = {h!r} N; a chain "
            "hanging straight down (H = 0) is a degenerate equilibrium this "
            "catenary formulation cannot represent"
        )
    if not math.isfinite(h) or not math.isfinite(v):
        raise ValueError(f"non-finite tension state (H, V0) = ({h!r}, {v!r})")
    if samples_per_segment < 2:
        raise ValueError(
            f"samples_per_segment must be at least 2 (both endpoints), got "
            f"{samples_per_segment}"
        )
    if not segments:
        raise ValueError("a chain needs at least one segment")

    x, z = start
    out: list[SegmentMarch] = []
    for seg in segments:
        length = seg.length_m
        w = seg.weight_n_per_m
        pts = np.empty((samples_per_segment, 2), dtype=float)
        for i in range(samples_per_segment):
            s = length * i / (samples_per_segment - 1)
            dx, dz = _offset(h, v, w, s)
            pts[i, 0] = x + dx
            pts[i, 1] = z + dz
        # Recompute the endpoint from the closed form rather than trusting the
        # last sample's rounding, then hand the exact state to the next span.
        dx_end, dz_end = _offset(h, v, w, length)
        x, z = x + dx_end, z + dz_end
        pts[-1, 0] = x
        pts[-1, 1] = z
        v = v + w * length
        out.append(SegmentMarch(points=pts, end_point=(x, z), end_tension=(h, v)))
    return tuple(out)


# --------------------------------------------------------------------------
# Result object
# --------------------------------------------------------------------------


@dataclass(frozen=True, eq=False)
class SegmentShape:
    """One solved segment: its sampled arc plus the per-segment diagnostics.

    ``points`` is ``(n, 2)`` of ``(x, z)`` in the chain's vertical plane,
    uniform in arc length.  ``polyline_length_m`` is the length of that
    *sampled* polyline — always slightly short of ``arc_length_m``, by
    ``O(1/n²)``, which is the internal consistency check the caller (and the
    tests) use to size the sampling.  ``max_sag_m`` is measured perpendicular
    to the segment's own chord, not vertically, and not from the whole chain's
    chord.
    """

    name: str
    points: np.ndarray
    arc_length_m: float
    polyline_length_m: float
    max_sag_m: float
    weight_n_per_m: float
    start_tension_vector: tuple[float, float]
    end_tension_vector: tuple[float, float]

    @property
    def chord_length_m(self) -> float:
        return float(np.hypot(*(self.points[-1] - self.points[0])))


@dataclass(frozen=True, eq=False)
class ChainSolution:
    """A solved hanging chain in its own vertical plane.

    ``segments`` carries the sampled shape and per-segment diagnostics in chain
    order; ``junctions`` are the interior joins between consecutive segments
    (empty for a single-segment chain).

    The two tension *vectors* are the forces the **supports exert on the
    chain**, not the internal tension in a fixed direction — so they sum to the
    chain's total weight pointing up and their horizontal parts cancel (see the
    module docstring).  ``apex_tension`` / ``end_tension`` are their magnitudes,
    which are also the internal line tensions at those points.
    ``horizontal_tension_n`` is the shared ``H``, the one number that sets the
    shape.
    """

    apex: tuple[float, float]
    end_point: tuple[float, float]
    segments: tuple[SegmentShape, ...]
    junctions: tuple[tuple[float, float], ...]
    apex_tension_vector: tuple[float, float]
    end_tension_vector: tuple[float, float]
    apex_tension: float
    end_tension: float
    horizontal_tension_n: float
    total_weight_n: float
    iterations: int
    residual: float

    @property
    def polyline(self) -> np.ndarray:
        """All segments concatenated, duplicate junction samples dropped."""
        parts = [self.segments[0].points]
        parts.extend(seg.points[1:] for seg in self.segments[1:])
        return np.vstack(parts)

    @property
    def max_sag_m(self) -> float:
        """Largest per-segment chord sag over the chain."""
        return max(seg.max_sag_m for seg in self.segments)

    @property
    def total_arc_length_m(self) -> float:
        return sum(seg.arc_length_m for seg in self.segments)


def _assemble(
    apex: tuple[float, float],
    tension: tuple[float, float],
    segments: Sequence[ChainSegment],
    marched: Sequence[SegmentMarch],
    iterations: int,
    residual: float,
) -> ChainSolution:
    """Package a converged march into a :class:`ChainSolution`."""
    h = tension[0]
    v = tension[1]
    shapes: list[SegmentShape] = []
    for seg, march in zip(segments, marched):
        steps = np.diff(march.points, axis=0)
        polyline_length = float(np.hypot(steps[:, 0], steps[:, 1]).sum())
        shapes.append(
            SegmentShape(
                name=seg.name,
                points=march.points,
                arc_length_m=seg.length_m,
                polyline_length_m=polyline_length,
                max_sag_m=chord_sag(h, v, seg.weight_n_per_m, seg.length_m),
                weight_n_per_m=seg.weight_n_per_m,
                start_tension_vector=(h, v),
                end_tension_vector=march.end_tension,
            )
        )
        v = march.end_tension[1]

    total_weight = sum(s.length_m * s.weight_n_per_m for s in segments)
    # Support forces: the apex holds the chain back (−t(0)); the far support
    # pulls it on (+t(L)).  Their sum is the weight, pointing up.
    apex_force = (-tension[0], -tension[1])
    end_force = marched[-1].end_tension
    return ChainSolution(
        apex=apex,
        end_point=marched[-1].end_point,
        segments=tuple(shapes),
        junctions=tuple(m.end_point for m in marched[:-1]),
        apex_tension_vector=apex_force,
        end_tension_vector=end_force,
        apex_tension=math.hypot(*apex_force),
        end_tension=math.hypot(*end_force),
        horizontal_tension_n=h,
        total_weight_n=total_weight,
        iterations=iterations,
        residual=residual,
    )


# --------------------------------------------------------------------------
# Damped Newton on the 2-unknown shooting problem
# --------------------------------------------------------------------------

# The unknowns are non-dimensionalised as q = (ln H, V0/H):
#   * ln H keeps H > 0 structurally — no barrier, no clamping — and makes the
#     Jacobian scale-free across the ten decades of tension a knob scrub can
#     visit (a taut chain's position depends on H only through ln H, so this
#     is also the difference between a well- and an ill-conditioned solve);
#   * V0/H is the chain's slope at the apex, an O(1) dimensionless number.
_Q_STEP = 1.0e-6
# Largest Newton step in q-space per iteration.  One unit of ln H is a factor
# of e in tension; letting Newton leap further from a bad Jacobian is how the
# solve ends up in the overflow weeds.
_MAX_STEP = 2.0
_H_FLOOR_REL = 1.0e-12


class _Infeasible(Exception):
    """Residual could not be evaluated at this trial point."""


def _damped_newton(
    residual: Callable[[np.ndarray], np.ndarray],
    q0: np.ndarray,
) -> tuple[np.ndarray, int, float]:
    """Damped Newton with a finite-difference Jacobian on a 2-vector.

    Two unknowns is far too small to be worth an analytic Jacobian or a scipy
    dependency: three residual evaluations per iteration, a backtracking line
    search on ‖r‖, and a step clamp make this robust enough to survive a knob
    being scrubbed through configurations that briefly have no equilibrium.
    """
    q = np.array(q0, dtype=float)
    try:
        r = residual(q)
    except _Infeasible as exc:
        raise ValueError(f"initial guess is infeasible: {exc}") from exc
    norm = float(np.linalg.norm(r))

    for it in range(1, _NEWTON_MAX_ITER + 1):
        if norm < _NEWTON_TOL:
            return q, it - 1, norm
        jac = np.empty((2, 2), dtype=float)
        for k in range(2):
            # Relative step: the apex slope V0/H is O(1) for a normal arm but
            # runs to 1e3 or more for a nearly vertical one, where a fixed
            # absolute step would be lost in the mantissa and hand Newton a
            # column of pure noise.
            step_k = _Q_STEP * max(1.0, abs(q[k]))
            qk = q.copy()
            qk[k] += step_k
            try:
                rk = residual(qk)
            except _Infeasible:
                qk[k] = q[k] - step_k
                rk = residual(qk)
                jac[:, k] = (r - rk) / step_k
            else:
                jac[:, k] = (rk - r) / step_k
        try:
            step = np.linalg.solve(jac, -r)
        except np.linalg.LinAlgError:
            step = -r
        if not np.all(np.isfinite(step)):
            step = -r
        # Clamp componentwise against each unknown's own scale, so a steep arm
        # (large |V0/H|) is not held to the same absolute leash as a shallow
        # one while ln H stays capped at a couple of e-foldings per iteration.
        limits = np.array([_MAX_STEP, _MAX_STEP * max(1.0, abs(q[1]))])
        excess = float(np.max(np.abs(step) / limits))
        if excess > 1.0:
            step /= excess

        lam = 1.0
        for _ in range(40):
            trial = q + lam * step
            try:
                r_trial = residual(trial)
            except _Infeasible:
                lam *= 0.5
                continue
            n_trial = float(np.linalg.norm(r_trial))
            if math.isfinite(n_trial) and n_trial < (1.0 - 1.0e-4 * lam) * norm:
                q, r, norm = trial, r_trial, n_trial
                break
            lam *= 0.5
        else:
            # No downhill step exists — either converged to round-off or stuck.
            return q, it, norm
    return q, _NEWTON_MAX_ITER, norm


def _shoot(
    residual: Callable[[np.ndarray], np.ndarray],
    guesses: Sequence[tuple[float, float]],
    what: str,
    hint: str,
) -> tuple[np.ndarray, int, float]:
    """Run :func:`_damped_newton` from each guess in turn; first win returns.

    Retrying from perturbed starts (a decade either side of the physical
    estimate) costs a few milliseconds and turns most "no equilibrium" reports
    that were really "bad initial guess" into solves.
    """
    best_norm = math.inf
    for guess in guesses:
        if not (guess[0] > 0.0) or not math.isfinite(guess[0]):
            continue
        q0 = np.array([math.log(guess[0]), guess[1] / guess[0]], dtype=float)
        try:
            q, iters, norm = _damped_newton(residual, q0)
        except ValueError:
            continue
        if norm < _NEWTON_TOL:
            return q, iters, norm
        best_norm = min(best_norm, norm)
    raise ValueError(
        f"no equilibrium found for {what}: the shooting solve stalled at a "
        f"residual of {best_norm:.3e} (target {_NEWTON_TOL:.0e}). {hint}"
    )


# --------------------------------------------------------------------------
# Rig closure 1 — tensioned halyard (massless rope of specified tension)
# --------------------------------------------------------------------------


def solve_tensioned(
    apex: tuple[float, float],
    wire_length_m: float,
    wire_weight_n_per_m: float,
    stake: tuple[float, float],
    rope_tension_n: float,
    *,
    samples_per_segment: int = 33,
    kernel: MarchKernel = march_continuous,
    name: str = "wire",
) -> ChainSolution:
    """Model 1: a wire of fixed cut length held by a rope of specified tension.

    The wire hangs from ``apex``; its far end is held by a *massless* straight
    rope running to ``stake`` and pulling with magnitude ``rope_tension_n``.
    The wire's end position is **not** an input — equilibrium places it, which
    is the whole point: ``rope_tension_n`` is the design knob and the arm's
    droop is the answer.

    The closure is that the end tension vector equals the rope pull:

        t(L) = T_rope · (stake − end) / ‖stake − end‖

    As ``T_rope → ∞`` the wire converges to the straight chord of length
    ``wire_length_m`` from ``apex`` toward ``stake`` — the taut-limit oracle
    against a straight inverted-vee arm.

    Raises :class:`ValueError` when no equilibrium exists.  Two cases are
    physical, not numerical: a stake that is not horizontally beyond the apex
    (the rope would have to pull backwards, needing ``H ≤ 0``), and a stake
    closer to the apex than the wire is long — the wire's end runs past the
    stake, so again the rope reverses, and no tension rescues it.

    The tension itself is otherwise unconstrained: the solve is exercised from
    1e-6 N (a wire hanging all but vertically) to 1e12 N (a straight chord)
    without special-casing, which is what a scrubbed UI knob demands.
    """
    if not (wire_length_m > 0.0):
        raise ValueError(f"wire length must be positive, got {wire_length_m!r} m")
    if not (wire_weight_n_per_m > 0.0):
        raise ValueError(
            "a weightless wire has no catenary: wire_weight_n_per_m must be "
            f"positive, got {wire_weight_n_per_m!r} N/m (pick a WireSpec with a "
            "real weight_g_per_m)"
        )
    if not (rope_tension_n > 0.0):
        raise ValueError(
            f"rope tension must be positive, got {rope_tension_n!r} N; a slack "
            "rope holds nothing and leaves no equilibrium for the wire's end"
        )

    span_x = stake[0] - apex[0]
    if span_x <= 0.0:
        raise ValueError(
            f"stake must be horizontally beyond the apex: apex x = {apex[0]!r} m, "
            f"stake x = {stake[0]!r} m.  With the stake level with or behind the "
            "apex the rope would pull the wire's end backwards, which needs a "
            "non-positive horizontal tension (a vertical hanging chain)"
        )

    segments = (
        ChainSegment(
            length_m=wire_length_m, weight_n_per_m=wire_weight_n_per_m, name=name
        ),
    )
    total_weight = wire_length_m * wire_weight_n_per_m
    # Non-dimensionalise the force residual by whichever of the rope pull and
    # the wire's own weight actually sets the scale.  Dividing by the rope
    # tension alone looks natural but blows the residual up (and stalls Newton
    # on round-off) when a knob scrub drives the tension far below the weight
    # the wire is asking the rope to help carry.
    force_scale = max(rope_tension_n, total_weight)
    h_floor = _H_FLOOR_REL * force_scale

    def residual(q: np.ndarray) -> np.ndarray:
        h = math.exp(q[0])
        if not math.isfinite(h) or h <= h_floor:
            raise _Infeasible("horizontal tension collapsed to zero")
        v0 = q[1] * h
        marched = kernel(apex, (h, v0), segments, 2)
        end = marched[-1].end_point
        rx = stake[0] - end[0]
        rz = stake[1] - end[1]
        dist = math.hypot(rx, rz)
        if dist == 0.0:
            raise _Infeasible("wire end coincides with the stake")
        pull = (rope_tension_n * rx / dist, rope_tension_n * rz / dist)
        end_t = marched[-1].end_tension
        return np.array(
            [
                (end_t[0] - pull[0]) / force_scale,
                (end_t[1] - pull[1]) / force_scale,
            ],
            dtype=float,
        )

    # Physical first guess: pretend the wire is already straight from the apex
    # toward the stake, then read the tension the rope would have to apply
    # there.  That is exact in the taut limit and merely close otherwise.
    ax, az = apex
    sx, sz = stake
    reach = math.hypot(sx - ax, sz - az)
    ux, uz = (sx - ax) / reach, (sz - az) / reach
    guess_h = rope_tension_n * ux
    guess_v1 = rope_tension_n * uz
    guess_v0 = guess_v1 - total_weight
    guesses = [
        (guess_h, guess_v0),
        (max(guess_h, total_weight), guess_v0),
        (0.1 * max(guess_h, total_weight), guess_v0),
        (10.0 * max(guess_h, total_weight), guess_v0),
        (total_weight, -total_weight),
    ]
    hint = (
        f"With a rope tension of {rope_tension_n:g} N pulling a {wire_length_m:g} m "
        f"wire toward a stake {reach:g} m away, check that the stake is farther "
        "from the apex than the wire is long (otherwise the taut wire overshoots "
        "it and the rope must pull backwards) and that the tension is large "
        "enough to keep the wire off the vertical."
    )
    q, iters, norm = _shoot(
        residual, guesses, "the tensioned-halyard rig (model 1)", hint
    )

    h = math.exp(q[0])
    v0 = q[1] * h
    marched = kernel(apex, (h, v0), segments, samples_per_segment)
    return _assemble(apex, (h, v0), segments, marched, iters, norm)


# --------------------------------------------------------------------------
# Rig closure 2 — heavy rope of fixed length to a ground anchor
# --------------------------------------------------------------------------


def solve_anchored(
    apex: tuple[float, float],
    segments: Sequence[ChainSegment],
    anchor: tuple[float, float],
    *,
    samples_per_segment: int = 33,
    kernel: MarchKernel = march_continuous,
) -> ChainSolution:
    """Model 2: a multi-segment chain of fixed lengths landing on an anchor.

    The chain — typically antenna wire then halyard, each with its own length
    and weight per metre — hangs from ``apex`` and its far end must land on
    ``anchor``.  Fixed endpoints plus inextensible fixed lengths leave **no
    tension freedom**: tension is an *output* here, a readout, not a knob.  The
    knob a winch actually turns is the rope's take-up, i.e. its ``length_m``.

    The closure is simply ``end == anchor``; the two unknowns are again
    ``(H, V0)``.

    Raises :class:`ValueError` when the chain cannot reach — the straight-line
    distance to the anchor exceeds the total arc length (a rope shorter than
    the gap) — or when the anchor is not horizontally beyond the apex, which
    would need a vertical hanging chain.
    """
    segments = tuple(segments)
    if not segments:
        raise ValueError("a chain needs at least one segment")

    total_length = sum(s.length_m for s in segments)
    total_weight = sum(s.length_m * s.weight_n_per_m for s in segments)
    if total_weight <= 0.0:
        raise ValueError(
            "a weightless chain has no catenary: every segment has "
            "weight_n_per_m = 0, so the shape is a straight line and no "
            "tension can be recovered (pick a WireSpec with a real "
            "weight_g_per_m)"
        )

    dx = anchor[0] - apex[0]
    dz = anchor[1] - apex[1]
    reach = math.hypot(dx, dz)
    if reach >= total_length:
        raise ValueError(
            f"chain cannot reach the anchor: the straight-line distance is "
            f"{reach:.6g} m but the segments total only {total_length:.6g} m of "
            "arc.  Lengthen the rope (reduce the take-up) or move the anchor "
            "closer; an inextensible chain has no equilibrium once it is pulled "
            "straight."
        )
    if dx <= 0.0:
        raise ValueError(
            f"anchor must be horizontally beyond the apex: apex x = {apex[0]!r} m, "
            f"anchor x = {anchor[0]!r} m.  A chain hanging straight down needs "
            "zero horizontal tension, a degenerate equilibrium this catenary "
            "formulation cannot represent"
        )

    h_floor = _H_FLOOR_REL * total_weight

    def residual(q: np.ndarray) -> np.ndarray:
        h = math.exp(q[0])
        if not math.isfinite(h) or h <= h_floor:
            raise _Infeasible("horizontal tension collapsed to zero")
        v0 = q[1] * h
        marched = kernel(apex, (h, v0), segments, 2)
        end = marched[-1].end_point
        return np.array(
            [
                (end[0] - anchor[0]) / total_length,
                (end[1] - anchor[1]) / total_length,
            ],
            dtype=float,
        )

    # Straight-chord initialisation via the shallow-parabola relations: a
    # parabola of sag f over a chord of length C carries an excess arc length
    # of 8f²/(3C), and its sag is w·C²/(8·H).  Invert both to get an H that
    # already has the right order of magnitude, then offset the apex slope by
    # the parabola's end slope, 4f/C.
    slack = total_length - reach
    sag_guess = math.sqrt(max(3.0 * reach * slack / 8.0, 1e-30))
    w_mean = total_weight / total_length
    chord_slope = dz / dx
    guess_h = max(w_mean * dx * reach / (8.0 * sag_guess), 1e-9 * total_weight)
    guess_v0 = guess_h * (chord_slope - 4.0 * sag_guess / reach)
    guesses = [
        (guess_h, guess_v0),
        (guess_h, guess_h * chord_slope),
        (0.1 * guess_h, guess_v0),
        (10.0 * guess_h, guess_v0),
        (total_weight, -total_weight),
    ]
    hint = (
        f"The chain totals {total_length:.6g} m of arc across a {reach:.6g} m gap "
        f"(slack {slack:.6g} m); very small slack makes the tension diverge and "
        "the solve ill-conditioned — lengthen the rope slightly."
    )
    q, iters, norm = _shoot(residual, guesses, "the anchored-chain rig (model 2)", hint)

    h = math.exp(q[0])
    v0 = q[1] * h
    marched = kernel(apex, (h, v0), segments, samples_per_segment)
    return _assemble(apex, (h, v0), segments, marched, iters, norm)


def solve_sprung(
    apex: tuple[float, float],
    segments: Sequence[ChainSegment],
    anchor: tuple[float, float],
    spring_l0_m: float,
    spring_k_n_per_m: float,
    *,
    samples_per_segment: int = 33,
    kernel: MarchKernel = march_continuous,
) -> ChainSolution:
    """Model 3: a chain whose far end reaches the anchor through a bungee.

    The chain hangs from ``apex`` as in the other two closures; its far end is
    neither tied straight to ``anchor`` (:func:`solve_anchored`) nor pulled at
    a caller-specified tension (:func:`solve_tensioned`).  Instead it is
    coupled to the anchor through a *massless* linear spring of natural length
    ``spring_l0_m`` and stiffness ``spring_k_n_per_m``: being massless, the
    spring is straight and transmits the chain's own end tension unchanged, so
    it stretches to exactly whatever length that tension demands,

        L_s = spring_l0_m + T_end / spring_k_n_per_m,      T_end = |t(L)|

    and the closure is that the chain's end, walked forward by ``L_s`` along
    the tension direction, lands on the anchor:

        end + L_s · t̂_end == anchor,      t̂_end = t(L) / T_end

    The unknowns are again ``(H, V0)``.  A spring end can only pull —
    ``T_end`` is always positive and ``L_s`` is always at least
    ``spring_l0_m``, never less, so there is no "pushing" branch to guard
    against.  The only way this closure can fail to have a solution is
    geometric: no tension state closes the gap to the anchor, which the
    shooting solve reports as the module's usual "no equilibrium found" error.

    ``end_point`` on the returned :class:`ChainSolution` is the *chain's* end
    — where the spring attaches, not the anchor — and ``end_tension_vector``
    is the spring's pull on the chain, the same convention as the other two
    closures.  The spring's own stretched geometry needs no extra fields to
    recover: its stretched length is ``hypot(anchor − end_point)`` (that is
    the closure itself) and its stretch beyond natural length is
    ``end_tension / spring_k_n_per_m``.

    Two limits recover the existing closures and are this one's oracles:

      * ``spring_k_n_per_m → ∞`` is :func:`solve_anchored` to a rigid link of
        length ``spring_l0_m``; taking ``spring_l0_m = 0`` shrinks that link
        to nothing, so the whole solution — ``H``, ``V0``, both tensions, the
        shape — converges to ``solve_anchored`` with the *same* anchor.
      * ``spring_k_n_per_m → 0`` degenerates to :func:`solve_tensioned`: the
        spring becomes so soft that its tension is set almost entirely by
        geometry (``T_end ≈ spring_k_n_per_m · (reach − arc − l0)``), which is
        exactly "how far you stretched the cord" — the same knob
        :func:`solve_tensioned` takes as an explicit input.

    Raises :class:`ValueError` for ``spring_k_n_per_m ≤ 0``, ``spring_l0_m <
    0``, an empty or weightless chain, an anchor not horizontally beyond the
    apex (same degenerate-vertical-chain rationale as the other two
    closures), or a geometry the shooting solve cannot close — whose hint
    calls out the spring's stiffness and natural length as the first things
    to check.
    """
    segments = tuple(segments)
    if not segments:
        raise ValueError("a chain needs at least one segment")
    if not (spring_k_n_per_m > 0.0):
        raise ValueError(
            f"spring stiffness must be positive, got {spring_k_n_per_m!r} N/m; "
            "a non-positive stiffness is not a spring (zero transmits no "
            "force, negative pushes)"
        )
    if spring_l0_m < 0.0:
        raise ValueError(
            f"spring natural length must be non-negative, got {spring_l0_m!r} m"
        )

    total_length = sum(s.length_m for s in segments)
    total_weight = sum(s.length_m * s.weight_n_per_m for s in segments)
    if total_weight <= 0.0:
        raise ValueError(
            "a weightless chain has no catenary: every segment has "
            "weight_n_per_m = 0, so the shape is a straight line and no "
            "tension can be recovered (pick a WireSpec with a real "
            "weight_g_per_m)"
        )

    dx = anchor[0] - apex[0]
    dz = anchor[1] - apex[1]
    reach = math.hypot(dx, dz)
    if dx <= 0.0:
        raise ValueError(
            f"anchor must be horizontally beyond the apex: apex x = {apex[0]!r} m, "
            f"anchor x = {anchor[0]!r} m.  A chain hanging straight down needs "
            "zero horizontal tension, a degenerate equilibrium this catenary "
            "formulation cannot represent"
        )

    # Non-dimensionalise positions by the chain's own arc length plus the
    # spring's unstretched length: the same "length that actually sets the
    # geometry" idea as solve_anchored's total_length, extended to cover a
    # rig where a long soft cord, not the short chain, dominates the scale.
    scale = total_length + spring_l0_m
    h_floor = _H_FLOOR_REL * total_weight

    def residual(q: np.ndarray) -> np.ndarray:
        h = math.exp(q[0])
        if not math.isfinite(h) or h <= h_floor:
            raise _Infeasible("horizontal tension collapsed to zero")
        v0 = q[1] * h
        marched = kernel(apex, (h, v0), segments, 2)
        end = marched[-1].end_point
        end_t = marched[-1].end_tension
        t_end = math.hypot(*end_t)
        ux, uz = end_t[0] / t_end, end_t[1] / t_end
        stretch = spring_l0_m + t_end / spring_k_n_per_m
        return np.array(
            [
                (anchor[0] - (end[0] + stretch * ux)) / scale,
                (anchor[1] - (end[1] + stretch * uz)) / scale,
            ],
            dtype=float,
        )

    # Two limiting guesses bracket the physical range:
    #
    #  (a) the stiff-spring limit: the spring barely stretches beyond its
    #      natural length, so pretend it is a rigid link of length
    #      spring_l0_m and reuse solve_anchored's own straight-chord/parabola
    #      guess, aimed at the pseudo-anchor that rigid link would attach to
    #      — the real anchor pulled back toward the apex by spring_l0_m along
    #      the apex-anchor line.
    #  (b) the soft-spring limit: the spring supplies essentially all the
    #      compliance, so estimate its tension from how far the chain's own
    #      arc length falls short of the total reach, then guess the state a
    #      massless rope at that tension would produce (solve_tensioned's own
    #      guess), pulling along the apex-anchor line.
    ux_chord, uz_chord = dx / reach, dz / reach
    guesses: list[tuple[float, float]] = []

    px = anchor[0] - spring_l0_m * ux_chord
    pz = anchor[1] - spring_l0_m * uz_chord
    pdx = px - apex[0]
    pdz = pz - apex[1]
    preach = math.hypot(pdx, pdz)
    if pdx > 0.0 and 0.0 < preach < total_length:
        slack = total_length - preach
        sag_guess = math.sqrt(max(3.0 * preach * slack / 8.0, 1e-30))
        w_mean = total_weight / total_length
        chord_slope = pdz / pdx
        guess_h_a = max(w_mean * pdx * preach / (8.0 * sag_guess), 1e-9 * total_weight)
        guess_v0_a = guess_h_a * (chord_slope - 4.0 * sag_guess / preach)
        guesses.append((guess_h_a, guess_v0_a))
        guesses.append((guess_h_a, guess_h_a * chord_slope))

    tension_guess = spring_k_n_per_m * max(
        reach - total_length - spring_l0_m, 1.0e-6 * max(total_weight, 1.0)
    )
    guess_h_b = tension_guess * ux_chord
    guess_v1_b = tension_guess * uz_chord
    guess_v0_b = guess_v1_b - total_weight
    guesses.append((guess_h_b, guess_v0_b))
    guesses.append((0.1 * max(guess_h_b, total_weight), guess_v0_b))
    guesses.append((10.0 * max(guess_h_b, total_weight), guess_v0_b))
    guesses.append((total_weight, -total_weight))

    hint = (
        f"With a spring of natural length {spring_l0_m:g} m and stiffness "
        f"{spring_k_n_per_m:g} N/m coupling a {total_length:.6g} m chain to an "
        f"anchor {reach:.6g} m away, check that the stiffness and natural "
        "length are not so small together that no tension state closes the "
        "gap, and that the anchor is far enough beyond the apex to keep the "
        "chain off the vertical."
    )
    q, iters, norm = _shoot(residual, guesses, "the sprung-chain rig (model 3)", hint)

    h = math.exp(q[0])
    v0 = q[1] * h
    marched = kernel(apex, (h, v0), segments, samples_per_segment)
    return _assemble(apex, (h, v0), segments, marched, iters, norm)


def solve_chain(
    apex: tuple[float, float],
    tension: tuple[float, float],
    segments: Sequence[ChainSegment],
    *,
    samples_per_segment: int = 33,
    kernel: MarchKernel = march_continuous,
) -> ChainSolution:
    """Package a *known* ``(H, V0)`` state as a :class:`ChainSolution`.

    No solve — this is the open-loop march, useful for oracles (a symmetric
    span whose tension state is known analytically) and for a caller that has
    already pinned the tension by other means.
    """
    segments = tuple(segments)
    marched = kernel(apex, tension, segments, samples_per_segment)
    return _assemble(apex, tension, segments, marched, 0, 0.0)


__all__ = [
    "GRAVITY",
    "TAUT_D",
    "TAUT_SAG_D",
    "ChainSegment",
    "ChainSolution",
    "MarchKernel",
    "SegmentMarch",
    "SegmentShape",
    "chord_sag",
    "march_continuous",
    "solve_anchored",
    "solve_chain",
    "solve_sprung",
    "solve_tensioned",
    "weight_n_per_m",
]

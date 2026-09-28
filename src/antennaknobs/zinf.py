"""The extrapolated impedance Z∞ of a refinement ladder (AK#1781).

ONE estimator, implemented twice and kept identical: here (the CLI's density
study, ``sweep --param nominal_nsegs``, and the ``ladder`` subcommand) and in
``web/frontend/src/lib/zinf.ts`` (the workbench's Z-vs-parameter view and
Smith chart). The shared vectors in
``web/frontend/src/__tests__/fixtures/zinfVectors.json`` are generated from
THIS implementation (``scripts/gen_zinf_vectors.py``) and gate both: pytest
(``tests/test_zinf_vectors_1781.py``) and vitest (``zinf.test.ts``) each
require their language to reproduce every case to 1e-12. A change to the
rule below is a change to both files and a regenerated JSON.

The rule (``zinf_estimate``), for rungs ``x_k > 0`` strictly increasing (the
refinement variable: segments achieved, or a refinement factor) and complex
``Z_k``, ``k = 0..m-1``:

1. ``m < 3`` (or ``x`` not positive and strictly increasing):
   ``insufficient``, no estimate.
2. ``d_k = |Z_{k+1} - Z_k|``. If the last step ``d_{m-2} <= 1e-6 |Z_{m-1}|``:
   ``converged``, ``Z∞ = Z_{m-1}``, no p.
3. Local slopes ``s_j = -(ln d_{j+1} - ln d_j) / (ln x_{j+1} - ln x_j)``,
   each difference ``d_j`` placed at its lower rung ``x_j``; defined only
   where both d are > 0.
4. Oscillating: the last two step vectors point in opposite directions,
   ``Re(D_{m-2} conj(D_{m-3})) < 0`` with ``D_k = Z_{k+1} - Z_k`` -> rough.
5. Straight (needs ``m >= 4``): the last two local slopes ``s_a, s_b`` are
   finite, ``|s_a - s_b| <= 0.10 |(s_a + s_b) / 2|``, and p (below) is in
   ``[0.25, 4]``.
6. Straight: ``p = -`` the least-squares slope of ``ln d_k`` on ``ln x_k``
   over the last ``min(3, m-1)`` differences; then ``Z = Z∞ + C x^-p``
   fitted by complex least squares through the last 3 rungs ->
   ``asymptotic``, with p.
7. Otherwise (``m == 3``, not straight, oscillating, p out of range): the
   theoretical first order, ``Z∞ = Z_{m-1} + (Z_{m-1} - Z_{m-2}) /
   (x_{m-1}/x_{m-2} - 1)`` -> ``rough``, no p.

One p per ladder, from the complex step: R and X are not extrapolated
separately. Plain ``math`` in double precision, no numpy, in the same
operation order as the TypeScript, so the two agree to rounding.

A reason beside "rough" (``feed_mesh_step``): the common cause is a feed
mesh that does not refine with the ladder. A short feed wire's segment
count moves in steps of two to keep the source centred (1 -> 3 on an
odd-parity basis, 2 -> 4 on an even one), so the fed segment stays fixed
for several rungs and then jumps, and each jump kinks the ladder (AK#1767's
feed-gap wires). Given the fed segment's length at each rung, the helper
finds the step, within the last ``FEED_MESH_WINDOW`` rungs (the ones the
straightness test reads), where that length departs most from the ``1/x``
scaling of a uniform refinement, and reports it when the departure exceeds
``FEED_MESH_TOL``. It never changes the estimate.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

#: Step 2's floor, relative to the finest |Z|.
CONVERGED_REL = 1e-6
#: Step 5's straightness tolerance on the last two local slopes.
STRAIGHT_REL = 0.10
#: Step 5's admissible observed order.
P_MIN, P_MAX = 0.25, 4.0
#: Step 7's assumed order.
P_THEORY = 1.0


@dataclass(frozen=True)
class ZInfEstimate:
    """``z_inf`` is None only when ``status == "insufficient"``; ``p`` is set
    only when ``status == "asymptotic"``."""

    z_inf: complex | None
    p: float | None
    status: str  # "insufficient" | "converged" | "asymptotic" | "rough"


def _local_slope(d0, d1, x0, x1):
    if not (d0 > 0 and d1 > 0):
        return None
    return -(math.log(d1) - math.log(d0)) / (math.log(x1) - math.log(x0))


def _fit_order(xs, ds):
    """``-`` the least-squares slope of ln d on ln x."""
    n = len(xs)
    lx = [math.log(x) for x in xs]
    ld = [math.log(d) for d in ds]
    # Plain loops, not sum(): since Python 3.12 sum() of floats is
    # compensated, and the TypeScript twin adds left to right.
    sx = 0.0
    sd = 0.0
    for i in range(n):
        sx += lx[i]
    for i in range(n):
        sd += ld[i]
    mx = sx / n
    md = sd / n
    num = 0.0
    den = 0.0
    for i in range(n):
        num += (lx[i] - mx) * (ld[i] - md)
        den += (lx[i] - mx) * (lx[i] - mx)
    return -(num / den)


def _fit_zinf(xs, zs, p):
    """Complex least squares for ``Z = Z∞ + C x^-p``; returns Z∞."""
    s0 = 0.0
    s1 = 0.0
    s2 = 0.0
    t0r = 0.0
    t0i = 0.0
    t1r = 0.0
    t1i = 0.0
    for x, z in zip(xs, zs, strict=True):
        u = math.pow(x, -p)
        s0 += 1.0
        s1 += u
        s2 += u * u
        t0r += z.real
        t0i += z.imag
        t1r += u * z.real
        t1i += u * z.imag
    det = s0 * s2 - s1 * s1
    return complex((s2 * t0r - s1 * t1r) / det, (s2 * t0i - s1 * t1i) / det)


def zinf_estimate(x, z) -> ZInfEstimate:
    """Z∞ of the ladder ``(x_k, Z_k)``: the rule in this module's docstring."""
    xs = [float(v) for v in x]
    zs = [complex(v) for v in z]
    m = len(zs)
    if m != len(xs):
        raise ValueError(f"x and z differ in length ({len(xs)} vs {m})")
    ok = m >= 3 and all(v > 0 for v in xs)
    ok = ok and all(xs[k + 1] > xs[k] for k in range(m - 1))
    if not ok:
        return ZInfEstimate(None, None, "insufficient")

    steps = [zs[k + 1] - zs[k] for k in range(m - 1)]
    ds = [abs(s) for s in steps]
    z_last = zs[m - 1]
    if ds[m - 2] <= CONVERGED_REL * abs(z_last):
        return ZInfEstimate(z_last, None, "converged")

    a, b = steps[m - 2], steps[m - 3]
    oscillating = a.real * b.real + a.imag * b.imag < 0
    if not oscillating and m >= 4:
        s_a = _local_slope(ds[m - 4], ds[m - 3], xs[m - 4], xs[m - 3])
        s_b = _local_slope(ds[m - 3], ds[m - 2], xs[m - 3], xs[m - 2])
        if (
            s_a is not None
            and s_b is not None
            and math.isfinite(s_a)
            and math.isfinite(s_b)
            and abs(s_a - s_b) <= STRAIGHT_REL * abs((s_a + s_b) / 2)
        ):
            n = min(3, m - 1)
            p = _fit_order(xs[m - 1 - n : m - 1], ds[m - 1 - n : m - 1])
            if P_MIN <= p <= P_MAX:
                return ZInfEstimate(
                    _fit_zinf(xs[m - 3 :], zs[m - 3 :], p), p, "asymptotic"
                )

    # Componentwise, not complex division: Python's complex / float has
    # changed algorithm across versions, and the TypeScript is componentwise.
    ratio = math.pow(xs[m - 1] / xs[m - 2], P_THEORY)
    z_prev = zs[m - 2]
    re = z_last.real + (z_last.real - z_prev.real) / (ratio - 1)
    im = z_last.imag + (z_last.imag - z_prev.imag) / (ratio - 1)
    return ZInfEstimate(complex(re, im), None, "rough")


#: ``feed_mesh_step``'s window: the last rungs, as the straightness test reads.
FEED_MESH_WINDOW = 4
#: ``feed_mesh_step``'s threshold: the factor by which one step's fed-segment
#: ratio may differ from the ladder's own ratio before it is reported.
FEED_MESH_TOL = 1.25


def feed_mesh_step(x, fed_len) -> int | None:
    """Index ``k`` of the step ``x_k -> x_{k+1}`` where the fed segment least
    follows the ladder, or None (see the module docstring).

    ``fed_len`` is the fed segment's length at each rung. The departure of a
    step is ``|ln(len_k / len_{k+1}) - ln(x_{k+1} / x_k)|``: zero when the
    fed segment shrinks with the mesh, ``ln 1.4`` when it stays put while x
    grows 1.4x, and larger still at a jump. Only steps departing by more
    than ``ln FEED_MESH_TOL`` count. A JUMP (the length changed) is preferred
    over a step where it stayed put, being the one a user can find in the
    mesh; within each kind the first step with the largest departure wins.
    None when no step counts, or when the inputs are short, misaligned or
    not positive."""
    m = len(x)
    if m < 2 or len(fed_len) != m:
        return None
    tol = math.log(FEED_MESH_TOL)
    best_jump, jump_dev = None, tol
    best_held, held_dev = None, tol
    for k in range(max(0, m - FEED_MESH_WINDOW), m - 1):
        x0, x1 = float(x[k]), float(x[k + 1])
        l0, l1 = float(fed_len[k]), float(fed_len[k + 1])
        if not (x0 > 0 and x1 > x0 and l0 > 0 and l1 > 0):
            return None
        dev = abs(math.log(l0 / l1) - math.log(x1 / x0))
        if _same_length(l0, l1):
            if dev > held_dev:
                best_held, held_dev = k, dev
        elif dev > jump_dev:
            best_jump, jump_dev = k, dev
    return best_jump if best_jump is not None else best_held


def _same_length(a, b):
    return abs(a - b) <= 1e-9 * max(a, b)


def describe_feed_mesh(x, fed_len, k: int, x_name: str = "N") -> str:
    """The CLI's line for a ``feed_mesh_step`` hit at step ``k``."""
    l0, l1 = fed_len[k] * 1000.0, fed_len[k + 1] * 1000.0
    x0, x1 = x[k], x[k + 1]
    if _same_length(l0, l1):
        where = f"stayed {l0:.1f} mm from {x_name} = {x0:g} to {x1:g}"
    else:
        where = f"went {l0:.1f} → {l1:.1f} mm between {x_name} = {x0:g} and {x1:g}"
    return (
        f"the fed segment {where}: the feed mesh does not refine with the "
        "ladder (AK#1767)"
    )


def describe(est: ZInfEstimate, digits: int = 3) -> str:
    """The CLI's one-line reading: ``Z∞ = R±Xj  (p = 0.98, asymptotic)``,
    ``(rough: not yet asymptotic, first order assumed)``, ``(converged)``,
    or ``Z∞ unavailable (need >= 3 rungs)``."""
    if est.z_inf is None:
        return "Z∞ unavailable (need >= 3 rungs)"
    z = est.z_inf
    head = f"Z∞ = {z.real:.{digits}f}{z.imag:+.{digits}f}j"
    if est.status == "asymptotic":
        return f"{head}  (p = {est.p:.2f}, asymptotic)"
    if est.status == "rough":
        return f"{head}  (rough: not yet asymptotic, first order assumed)"
    return f"{head}  (converged)"

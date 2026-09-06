"""Knob optimisation: vary a chosen subset of params within user-set bounds to
optimise an electrical objective (impedance match / SWR, resonance, …).

Deliberately free of any web framework. The objective is evaluated through an
injected ``solve_fn(req) -> response`` callback, so the same code runs:
  - under the FastAPI ``/optimize`` endpoint, wired to a registry example's
    cheap impedance-only ``momwire_solve`` (no far-field — we only read Z), and
  - under unit tests, wired to a builder/example solve directly or to a stub.

The optimiser is a bounded Nelder–Mead (derivative-free — each objective eval is
a full MoM solve, so finite-difference gradients would be wasteful) started from
the params' current values. It's a *local* search: it refines the operating
point the user is already near, which matches the "nudge these knobs to tune
this" workflow. A global pass (differential_evolution) can be layered on later.

Request shape (the bits this module reads), in addition to a normal solve req:
    optimize = {
        "free": [{"name": "length_factor", "min": 0.9, "max": 1.1}, ...],
        "objective": "swr" | "resonance" | "match_z0",
        "max_evals": <int, optional cap>,
    }
"""

from __future__ import annotations

from typing import Callable

import numpy as np
from scipy.optimize import minimize

# Objective keys the UI can offer. Each maps a solve response -> a scalar to
# MINIMISE (so a perfect match / resonance is 0).
OBJECTIVES = ("swr", "resonance", "match_z0")


def _swr(z_re: float, z_im: float, z0: float) -> float:
    """Voltage SWR of impedance Z against a real reference Z0. 1.0 = perfect
    match; clamped just below the open-circuit singularity so a totally
    mismatched candidate returns a large-but-finite penalty the optimiser can
    still descend from."""
    z = complex(z_re, z_im)
    denom = z + z0
    gamma = 1.0 if denom == 0 else abs((z - z0) / denom)
    gamma = min(gamma, 1.0 - 1e-9)
    return (1.0 + gamma) / (1.0 - gamma)


def _feed_zs(out: dict) -> list[complex]:
    """The impedances a solve response puts up for scoring, one per feed.

    Bare multi-feed designs (several independently driven ports, no common
    network) carry a per-feed table in ``feeds`` — every port needs a match,
    so every entry is scored. Everything else carries only ``z_in_re``/
    ``z_in_im``: single-feed designs trivially, and networked designs whose
    one source drives the elements through a splitter/harness — there the
    meaningful match is the network's driven plane, which is exactly what
    ``z_in`` is referenced to (issues #652/#785)."""
    feeds = out.get("feeds")
    if feeds:
        return [complex(float(f["z_re"]), float(f["z_im"])) for f in feeds]
    return [complex(float(out["z_in_re"]), float(out["z_in_im"]))]


def _objective_value(out: dict, key: str) -> float:
    """The scalar to minimise. Multi-feed designs score their WORST feed
    (minimax, issue #785): a sum lets one badly mismatched element hide behind
    several good ones, and the guarantee a driven array actually wants is "no
    element is badly matched". The CLI optimiser aggregates the same way; the
    two still differ in *form* (CLI default: |Z−Z0| distance, web default:
    SWR) — deliberate, each matches what its surface displays."""
    z0 = float(out.get("z0_ohms", 50.0))
    zs = _feed_zs(out)
    if key == "resonance":
        return max(abs(z.imag) for z in zs)  # cancel reactance
    if key == "match_z0":
        return max(abs(z - z0) for z in zs)  # complex distance to Z0
    return max(_swr(z.real, z.imag, z0) for z in zs)  # default: minimise SWR


# Root-finding tolerances. `_ROOT_XTOL` is deliberately the SAME 1e-4 that the
# Nelder-Mead call below passes as `xatol`, so switching methods does not
# silently change how tightly a knob is resolved; `_ROOT_FTOL` is the residual
# at which a root is called found. Neither is the study's 1 ohm reporting
# tolerance (#1202) -- that is how the gates *score* a run, not where a run
# stops. A secant costs one solve per step and converges superlinearly, so
# tightening it past the reporting tolerance is nearly free.
_ROOT_XTOL = 1e-4  # knob units
_ROOT_FTOL = 1e-3  # ohm


def _signed_reactance(out: dict) -> float | None:
    """The SIGNED X a scalar root-finder needs, or None if there isn't one.

    `_objective_value(.., "resonance")` is `max(abs(X))` over the feeds: an
    absolute value, and on a multi-feed design a minimax. Neither is a function
    with a sign change to bracket -- |X| touches zero without crossing it, and
    a minimax of several feeds generally has no common root at all. So the
    root-finding path is single-feed only, and this returns None to say so.
    """
    zs = _feed_zs(out)
    if len(zs) != 1:
        return None
    return zs[0].imag


def _secant_root(probe, x0, lo, hi, budget, *, span_frac=0.05):
    """Secant on a scalar residual over [lo, hi]. Returns (x, ok, reason).

    Costs ONE new solve per step: the previous iterate is reused, where a
    Newton finite-difference derivative would pay two. Measured on #1202: 3-4
    solves against Nelder-Mead's 10-16.

    Bails out (ok=False) when the step leaves the box or the residual grows on
    two consecutive steps -- the two ways a secant goes wrong on a curve that
    is not locally monotonic. The caller brackets instead.
    """
    span = max((hi - lo) * span_frac, _ROOT_XTOL)
    a = min(max(float(x0), lo), hi)
    fa = probe(a)
    if fa is None:
        return a, False, "multi-feed"
    if abs(fa) <= _ROOT_FTOL:
        return a, True, "already-at-root"
    # One bracketing step, taken DOWNHILL in |f| where the box allows it.
    b = a + span if a + span <= hi else a - span
    b = min(max(b, lo), hi)
    fb = probe(b)
    if fb is None:
        return a, False, "multi-feed"
    grew = 0
    best = (abs(fa), a) if abs(fa) < abs(fb) else (abs(fb), b)
    while budget > 0:
        budget -= 1
        if fb == fa:
            return best[1], False, "flat"
        c = b - fb * (b - a) / (fb - fa)
        if not (lo - 1e-12 <= c <= hi + 1e-12):
            return best[1], False, "left-the-box"
        c = min(max(c, lo), hi)
        if abs(c - b) <= _ROOT_XTOL:
            return c, True, "xtol"
        fc = probe(c)
        if fc is None:
            return best[1], False, "multi-feed"
        if abs(fc) < best[0]:
            best = (abs(fc), c)
        grew = grew + 1 if abs(fc) >= abs(fb) else 0
        if grew >= 2:
            return best[1], False, "residual-grew"
        a, fa, b, fb = b, fb, c, fc
        if abs(fc) <= _ROOT_FTOL:
            return c, True, "ftol"
    return best[1], False, "budget"


def _surrogate_root_start(probe, box, n, rng, z0):
    """Sample the box, fit Z, and return where the ROOT is predicted to be,
    plus the sampled points ranked by how close they actually came.

    Deliberately NOT `_surrogate_seed`, and the difference is the whole point.
    That one returns its best SOLVED sample, which is right for a Nelder-Mead
    finisher: NM needs a good incumbent and cannot use a prediction.

    A Newton finisher needs something else -- the right BASIN. Measured on the
    buried vertical (#1202): R along the X = 0 contour rises to 50.7 at
    radial_factor 0.31, falls to 45.1 at 0.54, then saturates at 48.5. The
    best-scoring SAMPLE landed at 0.65, past that ridge, where R can never
    reach 50 and Newton walks into the upper bound. The fitted surface's
    predicted crossing landed at 0.43, on the correct side, and Newton
    converged from it in 8 solves.

    So the prediction is a legitimate START (it gets solved on the first step),
    while the ANSWER stays a solved point -- the abort rule is untouched.
    """
    d = len(box)
    lo = np.array([b[0] for b in box], dtype=float)
    span = np.array([b[1] - b[0] for b in box], dtype=float)
    us, zs = [], []
    for u in _seed_points(d, n, rng):
        z = probe(lo + np.clip(u, 0.0, 1.0) * span)
        if z is None:
            return None, []
        us.append(np.asarray(u, dtype=float))
        zs.append(z)
    ranked = [
        list(lo + u * span)
        for u, _ in sorted(zip(us, zs, strict=True), key=lambda t: abs(t[1] - z0))
    ]
    A = _quad_features(np.asarray(us))
    if A.shape[0] < A.shape[1]:
        return (ranked[0] if ranked else None), ranked
    re = np.linalg.lstsq(A, np.array([z.real for z in zs]), rcond=None)[0]
    im = np.linalg.lstsq(A, np.array([z.imag for z in zs]), rcond=None)[0]
    cand = rng.random((4096, d))
    F = _quad_features(cand)
    pred = np.hypot(F @ re - z0, F @ im)
    u_pred = cand[int(np.argmin(pred))]
    return list(lo + u_pred * span), ranked


def _newton_root2(probe, x0, box, budget, *, broyden_between=True):
    """Newton on the two-component residual F = (R - R0, X). Returns (x, ok, why).

    Three things here are load-bearing, and each was measured in #1202:

    **Box-aware finite differences.** A plain forward difference is DEGENERATE
    on the boundary: at a box corner every perturbation clips back onto the
    corner, J comes out identically zero and the linear solve dies singular.
    Measured on moxon from the far start -- Newton stopped after 4 solves with
    a residual of 35 ohm. Stepping inward instead turns that into 7 solves.

    **A fresh Jacobian costs 2 solves, not 3.** The base point is already
    solved and the #1176 memo answers it for free, so only the two
    perturbations are new. That is why refreshing is affordable at all.

    **The stall detector.** On the buried vertical, R along the X = 0 contour
    rises to 50.7 at radial_factor 0.31, falls to 45.1 at 0.54, then saturates
    at 48.5 -- so a start past that ridge sends Newton chasing R = 50 into the
    upper bound, where the residual CANNOT be zeroed. Unguarded it burned all
    80 solves thrashing there. Two non-improving steps buy one Jacobian
    refresh; a third hands back to the caller, which falls back to Nelder-Mead
    from the best SOLVED point.
    """
    n = len(x0)
    lo = np.array([b[0] for b in box], dtype=float)
    hi = np.array([b[1] for b in box], dtype=float)
    h = np.maximum((hi - lo) * 0.002, 1e-12)
    used = 0

    def clip(x):
        return np.minimum(np.maximum(x, lo), hi)

    def call(x):
        nonlocal used
        used += 1
        return probe(x)

    def jac(x, F):
        """Forward differences, flipped INWARD wherever the box says so."""
        J = np.zeros((n, n))
        for j in range(n):
            step = h[j] if x[j] + h[j] <= hi[j] else -h[j]
            if x[j] + step < lo[j]:
                step = h[j]
            xp = x.copy()
            xp[j] = min(max(xp[j] + step, lo[j]), hi[j])
            dh = xp[j] - x[j]
            Fp = call(xp)
            if Fp is None:
                return None
            J[:, j] = (Fp - F) / (dh if dh else h[j])
        return J

    x = clip(np.asarray(x0, dtype=float))
    F = call(x)
    if F is None:
        return list(x), False, "multi-feed"
    best = (float(np.linalg.norm(F)), x.copy())
    if best[0] <= _ROOT_FTOL:
        return list(x), True, "already-at-root"
    J = jac(x, F)
    if J is None:
        return list(best[1]), False, "multi-feed"
    stall = 0
    refreshed = False
    while used < budget:
        try:
            step = np.linalg.solve(J, -F)
        except np.linalg.LinAlgError:
            return list(best[1]), False, "singular"
        t = 1.0
        xn, Fn = None, None
        while used < budget:
            xt = clip(x + t * step)
            Ft = call(xt)
            if Ft is None:
                return list(best[1]), False, "multi-feed"
            if np.linalg.norm(Ft) < np.linalg.norm(F) or t < 0.06:
                xn, Fn = xt, Ft
                break
            t *= 0.5
        if xn is None:
            return list(best[1]), False, "budget"
        prev = float(np.linalg.norm(F))
        nrm = float(np.linalg.norm(Fn))
        if nrm < best[0]:
            best = (nrm, xn.copy())
        moved = float(np.linalg.norm(xn - x))
        dx, dF = xn - x, Fn - F
        x, F = xn, Fn
        if nrm <= _ROOT_FTOL:
            return list(x), True, "ftol"
        if moved <= _ROOT_XTOL:
            # The step went to zero. If the residual is still above tolerance
            # this is a stationary point of |F| that is NOT a root -- on a real
            # deck, the two contours not crossing anywhere reachable. Name it
            # so, rather than reporting the convergence test that caught it.
            done = best[0] <= _ROOT_FTOL
            return list(best[1]), done, "xtol" if done else "no-crossing"
        # A step that does not cut the residual by at least 1 % is not
        # progress. Two of those in a row is the stall.
        stall = 0 if nrm < 0.99 * prev else stall + 1
        if stall >= 2:
            if refreshed:
                # Two more non-improving steps AFTER a refresh: the residual
                # cannot be zeroed from here (typically a bound). Hand back.
                return list(best[1]), False, "stalled"
            refreshed = True
            stall = 0
            Jn = jac(x, F)
            if Jn is None:
                return list(best[1]), False, "multi-feed"
            J = Jn
            continue
        if broyden_between and np.dot(dx, dx) > 0:
            J = J + np.outer(dF - J @ dx, dx) / np.dot(dx, dx)
        else:
            Jn = jac(x, F)
            if Jn is None:
                return list(best[1]), False, "multi-feed"
            J = Jn
    return list(best[1]), best[0] <= _ROOT_FTOL, "budget"


def _bracket_brent(probe, lo, hi, budget, *, n_scan=5):
    """Scan for a sign change, then secant-with-bisection-fallback inside it.

    This is the path for a start the secant could not use. If the scan finds NO
    sign change, the residual has no root in the box -- reported as such
    (ok=False, "no-sign-change") rather than parked silently on a bound.
    """
    if budget < n_scan:
        n_scan = max(2, budget)
    vs = list(np.linspace(lo, hi, n_scan))
    fs = []
    for v in vs:
        if budget <= 0:
            return v, False, "budget"
        budget -= 1
        f = probe(v)
        if f is None:
            return v, False, "multi-feed"
        fs.append(f)
    best = min(zip(vs, fs, strict=True), key=lambda t: abs(t[1]))
    br = None
    for i in range(len(vs) - 1):
        if fs[i] == 0.0:
            return vs[i], True, "scan-hit"
        if fs[i] * fs[i + 1] < 0:
            br = (vs[i], fs[i], vs[i + 1], fs[i + 1])
            break
    if br is None:
        return best[0], False, "no-sign-change"
    a, fa, b, fb = br
    while budget > 0:
        budget -= 1
        c = b - fb * (b - a) / (fb - fa) if fb != fa else 0.5 * (a + b)
        if not (min(a, b) < c < max(a, b)):
            c = 0.5 * (a + b)
        fc = probe(c)
        if fc is None:
            return best[0], False, "multi-feed"
        if abs(fc) < abs(best[1]):
            best = (c, fc)
        if abs(fc) <= _ROOT_FTOL or abs(b - a) <= _ROOT_XTOL:
            return c, True, "ftol"
        if fa * fc < 0:
            b, fb = c, fc
        else:
            a, fa = c, fc
    return best[0], False, "budget"


def _residual(out: dict, key: str) -> float | None:
    """What a ROOT-finder is driving to zero, or None when the objective is not
    a root problem. Distinct from `_objective_value`: the residual falls
    monotonically under Newton/secant, which is exactly why the readout shows
    it instead of a simplex's best-so-far (#1202)."""
    zs = _feed_zs(out)
    if len(zs) != 1:
        return None
    z = zs[0]
    if key == "resonance":
        return abs(z.imag)
    if key == "match_z0":
        return abs(z - float(out.get("z0_ohms", 50.0) or 50.0))
    return None


def _residual_vec(out: dict) -> "np.ndarray | None":
    """The TWO-COMPONENT root a `match_z0` run is really solving:
    (R - R0, X). None unless the response is single-feed -- a minimax over
    several ports is not a root system."""
    zs = _feed_zs(out)
    if len(zs) != 1:
        return None
    z0 = float(out.get("z0_ohms", 50.0) or 50.0)
    return np.array([zs[0].real - z0, zs[0].imag])


def _metrics(out: dict) -> dict:
    """The handful of numbers the UI shows before/after, derived from one solve.

    On a multi-feed design ``swr`` is the WORST feed's — the number the
    objective drives (#785) — while ``z_in_re``/``z_in_im`` stay feed 0 to
    match the primary readout; ``worst_feed``/``n_feeds`` say which and how
    many. Single-feed responses keep the exact four-key shape.

    ``feeds`` carries every port's Z (#789) so a live Smith chart can draw the
    whole array mid-run. Without it the chart plots ``z_in`` — feed 0 — while
    the minimax objective chases some other feed, so the ring can sit still
    while the impedance actually being optimised walks off screen. Z only:
    the settled solve's feed rows carry position and drive voltage too, and
    neither changes during a run."""
    z0 = float(out.get("z0_ohms", 50.0))
    z_re = float(out["z_in_re"])
    z_im = float(out["z_in_im"])
    m = {
        "z_in_re": z_re,
        "z_in_im": z_im,
        "z0_ohms": z0,
        "swr": _swr(z_re, z_im, z0),
    }
    zs = _feed_zs(out)
    if len(zs) > 1:
        swrs = [_swr(z.real, z.imag, z0) for z in zs]
        worst = max(range(len(swrs)), key=swrs.__getitem__)
        m["swr"] = swrs[worst]
        m["worst_feed"] = worst
        m["n_feeds"] = len(zs)
        m["feeds"] = [{"z_re": z.real, "z_im": z.imag} for z in zs]
    return m


# --- surrogate seeding (issue #1176) --------------------------------------
#
# Nelder-Mead starts from the user's current point and crawls. On two knobs it
# does not converge at all inside its own budget — measured 81/82 solves
# against a `maxfev` of 80 — so its answer is "as good as 80 evals got".
#
# The seed fits a cheap response surface to the solves it has already made,
# reads a promising point off it, and hands that to Nelder-Mead as the start.
# Measured (#1176 design study), against NM alone on the same decks:
#
#     invvee, 2 knobs    NM 81 solves -> SWR 1.0000    seeded 44 -> 1.0010
#     moxon,  2 knobs    NM 82 solves -> SWR 1.0000    seeded 44 -> 1.0038
#
# 1.004 against 1.000 is far below anything an antenna measurement resolves,
# at 54 % of the solves.
#
# FIT THE IMPEDANCE, NOT THE OBJECTIVE. This is the load-bearing decision and
# it is the opposite of the obvious implementation. SWR has a kink at the
# match and a cliff beyond it, and the catalog's objectives are strongly
# ASYMMETRIC about their optimum (moxon's `t0_factor` runs 1.43 -> 2.19 ->
# 4.40 -> 6.52 across three steps to the right of its minimum, a second
# difference of 32 % of the range). A quadratic fitted to that is biased
# toward the gentle side: the first prototype converged in fewer solves to a
# DISPLACED optimum, and a local refinement stage did not fix it. Z is smooth
# through the same region. Fitting Re(Z) and Im(Z) separately and forming the
# objective from the prediction:
#
#     deck     fit SWR      fit Z
#     invvee   1.0192       1.0159
#     moxon    1.6121       1.1106      <- the asymmetric one
#
# THE ANSWER IS ALWAYS A SOLVED POINT. The surface proposes; it never decides.
# Everything returned from here was measured, so an abort mid-seed hands back
# the best point actually solved rather than the surface's argmin — which was
# measured up to 0.5 SWR away from what that point turned out to be worth.


def _quad_features(u):
    """Columns of the quadratic basis on the unit cube: 1, x_i, x_i x_j."""
    n, d = u.shape
    cols = [np.ones(n)]
    cols.extend(u[:, i] for i in range(d))
    for i in range(d):
        cols.extend(u[:, i] * u[:, j] for j in range(i, d))
    return np.vstack(cols).T


def _seed_points(d, n, rng):
    """A space-filling start: Latin hypercube, one sample per stratum.

    Not `rng.random((n, d))`: an unstratified draw leaves gaps and clusters at
    these tiny sample counts, and the whole point of the seed is to see the
    box before fitting a surface to it.
    """
    cuts = (np.arange(n)[:, None] + rng.random((n, d))) / n
    for i in range(d):
        rng.shuffle(cuts[:, i])
    return cuts


def _surrogate_seed(probe, d, n_seed, budget, rng):
    """Seed a search by fitting Z over the unit cube; return the best SOLVED
    point as (u, value).

    `probe(u)` solves at unit-cube coordinates and returns
    `(objective, z_complex, z0)`. Everything this returns was measured.
    """
    us, objs, zs = [], [], []

    def take(u):
        obj, z, z0 = probe(u)
        us.append(np.asarray(u, dtype=float))
        objs.append(float(obj))
        zs.append((complex(z), float(z0)))
        return obj

    for u in _seed_points(d, n_seed, rng):
        take(u)

    while len(us) < budget:
        U = np.asarray(us)
        A = _quad_features(U)
        if A.shape[0] < A.shape[1]:
            break
        re = np.linalg.lstsq(A, np.array([z.real for z, _ in zs]), rcond=None)[0]
        im = np.linalg.lstsq(A, np.array([z.imag for z, _ in zs]), rcond=None)[0]
        cand = rng.random((2048, d))
        F = _quad_features(cand)
        z0 = zs[0][1]
        pred = np.array([_swr(r, i, z0) for r, i in zip(F @ re, F @ im, strict=True)])
        # nearest-neighbour guard: proposing a point we have already solved
        # spends an eval to learn nothing (the memo would answer it, but the
        # surface would then never move)
        for idx in np.argsort(pred):
            u = cand[idx]
            if all(np.linalg.norm(u - prev) > 1e-3 for prev in us):
                take(u)
                break
        else:
            break

    best = int(np.argmin(objs))
    return us[best], objs[best]


def optimize(
    base_req: dict,
    free: list[dict],
    objective: str = "swr",
    *,
    solve_fn: Callable[[dict], dict],
    max_evals: int | None = None,
    on_progress: Callable[[dict], None] | None = None,
    seed_surrogate: bool = False,
    seed_state: int = 0,
) -> dict:
    """Optimise ``objective`` over the ``free`` params within their bounds.

    ``free`` is a list of ``{"name", "min", "max"}``. ``solve_fn`` takes a solve
    request and returns a response carrying ``z_in_re``/``z_in_im``/``z0_ohms``.
    Returns the best params found plus before/after objective + metrics.

    ``on_progress``, if given, is called once per solve (see ``_solve_at``) with
    ``{"n_evals", "params", "objective", "metrics"}``. ``None`` (the default)
    leaves behaviour identical to no callback support at all.
    """
    if not free:
        raise ValueError("no free params selected to optimise")
    if objective not in OBJECTIVES:
        objective = "swr"

    names = [f["name"] for f in free]
    lo = [float(f["min"]) for f in free]
    hi = [float(f["max"]) for f in free]

    # Start from each param's current value, clipped into its bound.
    x0 = []
    for name, lob, hib in zip(names, lo, hi, strict=True):
        cur = float(base_req.get(name, 0.5 * (lob + hib)))
        x0.append(min(max(cur, lob), hib))

    n_evals = 0
    n_solves = 0
    # Which stage is running, for the readout (#1202). A root-finder's residual
    # falls monotonically and a simplex's does not, so the readout needs to say
    # which it is looking at rather than leaving the user to infer it.
    phase = "search"
    # Where the run is, for the readout (#1176). `seed_total` is 0 whenever
    # the seed is not running, so "am I seeding" is one comparison on the
    # client and not a phase machine.
    seed_index = 0
    seed_total = 0
    # One run's solved points, keyed on the EXACT parameter tuple (issue
    # #1176). Nelder-Mead keeps only its current simplex, so it re-probes
    # points it has already paid for: measured 21-35 % of the solves on a
    # one-knob run (invvee 21 %, a vertical over Sommerfeld 35 %, the buried
    # screen 25-29 %) and 2-4 % on a two-knob run, where the simplex crawls
    # through a tight region without landing twice on the same floats.
    #
    # THE KEY IS EXACT, deliberately. A tolerance-keyed cache would answer a
    # DIFFERENT point with a previous point's solve — faster, and a lie about
    # the objective, which would change the search's trajectory and the answer
    # it lands on. With exact keys the run is bit-for-bit the run it was, only
    # cheaper; the "within xatol" repeats (up to 57 % on two knobs) are
    # deliberately left on the table for the surrogate seeding to address, not
    # a rounding rule here.
    #
    # PER RUN, never across requests. The optimizer's evals bypass the server's
    # `_SOLVE_CACHE` on purpose — an unbounded budget is a sustained-CPU lever
    # (#346) — and this does not reopen that: it is bounded by `max_evals`,
    # lives on the stack of one `optimize()` call, and makes a run strictly
    # cheaper than the run it replaces.
    memo: dict[tuple[float, ...], dict] = {}

    def _solve_at(x) -> dict:
        nonlocal n_evals, n_solves
        req = dict(base_req)
        params = {}
        for name, v in zip(names, x, strict=True):
            val = float(v)
            req[name] = val
            params[name] = val
        n_evals += 1
        key = tuple(params[name] for name in names)
        out = memo.get(key)
        if out is None:
            out = solve_fn(req)
            n_solves += 1
            memo[key] = out
        # Emitted here, not via scipy's minimize(callback=...): that callback
        # fires once per Nelder-Mead ITERATION (a reflection/expansion/contraction
        # that itself costs 1-2 evals), not once per eval — e.g. ~30 callbacks for
        # 60 evals — and it doesn't fire at all until the initial simplex (N+1
        # evals) is built, leaving a dead zone at the start of every run. Every
        # solve, in every phase (baseline, simplex, confirmation), goes through
        # this one choke point, so hooking here is the only way to get gapless
        # per-eval granularity that also covers the initial-simplex evals.
        if on_progress is not None:
            on_progress(
                {
                    "n_evals": n_evals,
                    "params": params,
                    "objective": _objective_value(out, objective),
                    "metrics": _metrics(out),
                    "seed_index": seed_index,
                    "seed_total": seed_total,
                    "phase": phase,
                    "residual": _residual(out, objective),
                }
            )
        return out

    def f(x) -> float:
        return _objective_value(_solve_at(x), objective)

    out0 = _solve_at(x0)

    # --- scalar root path: one knob, X = 0 (#1202) ----------------------
    # `resonance` on a single knob is a SCALAR ROOT, not a minimum, and
    # Nelder-Mead never uses that. Measured: 3-4 solves against NM's 10-16 on
    # both study decks from both starts.
    #
    # Guarded on the response being SINGLE-FEED. Multi-feed `resonance` is a
    # minimax of |X| over ports, which has no sign change to bracket and
    # generally no common root -- `_signed_reactance` returns None and this
    # whole branch is skipped, leaving NM exactly as it was.
    method = "nelder-mead"
    root_reason = None
    x_root = None
    # Two knobs to Z0 is a two-component root (R - R0, X). Same single-feed
    # guard as the scalar path, and the same reason for it.
    newton_path = (
        objective == "match_z0" and len(free) == 2 and _residual_vec(out0) is not None
    )
    if (
        objective == "resonance"
        and len(free) == 1
        and _signed_reactance(out0) is not None
    ):
        lo0, hi0 = lo[0], hi[0]
        budget0 = (int(max_evals) if max_evals else min(200, 40 * len(free))) - n_evals

        def _probe_x(v):
            return _signed_reactance(_solve_at([v]))

        phase = "secant"
        x_root, ok, root_reason = _secant_root(
            _probe_x, x0[0], lo0, hi0, max(budget0, 2)
        )
        if not ok and root_reason != "multi-feed":
            # The secant's two failure modes (step left the box, residual grew
            # twice) both mean "this start is not usable", not "there is no
            # root". Scan for a bracket before giving up on the method.
            phase = "bracket"
            x_root, ok, root_reason = _bracket_brent(
                _probe_x, lo0, hi0, max(budget0 - n_evals + 1, 2)
            )
        if ok:
            x_root = [x_root]
            method = "secant" if phase == "secant" else "bracket-brent"
        else:
            # No root reachable in the box (or the budget ran out). Fall through
            # to Nelder-Mead from the best SOLVED point, and say why in the
            # result -- never park silently on a bound.
            phase = "fallback"
            method = f"nelder-mead (root: {root_reason})"
            if x_root is not None:
                x0 = [min(max(float(x_root), lo0), hi0)]
            x_root = None

    # --- surrogate seeding (#1176) -------------------------------------
    # Runs BEFORE Nelder-Mead and hands it a start, rather than replacing it.
    # Framing it as a peer method would invite picking the one that does not
    # finish: measured, the surface alone reaches 1.016 (invvee) / 1.111
    # (moxon) where NM reaches 1.0000, and the two together reach 1.001 /
    # 1.004 in 54 % of the solves. It is a seeding stage, and the name says so.
    #
    # One knob is excluded: a 1-D quadratic needs 3 points and NM converges in
    # 24 solves there anyway (measured), so the seed would spend an eighth of
    # the run to save nothing. The saving is on 2+ knobs, which is also where
    # NM runs out of budget rather than converging.
    n_seed = 0
    if seed_surrogate and len(free) >= 2:
        d = len(free)
        n_coef = 1 + d + d * (d + 1) // 2
        n_seed = n_coef
        # 2x the coefficient count: 12 points for two knobs, which is what
        # the study measured as the knee — 18 was no better (moxon 1.0080
        # against 1.0038), so the seed stays small and leaves the budget to
        # the finisher. Never more than a third of the run.
        total_budget = int(max_evals) if max_evals else min(200, 40 * len(free))
        seed_budget = max(n_coef, min(2 * n_coef, total_budget // 3))
        phase = "seeding"
        lo_a = np.asarray(lo, dtype=float)
        span = np.asarray(hi, dtype=float) - lo_a

        seed_total = seed_budget

        def _probe(u):
            nonlocal seed_index
            seed_index += 1
            out = _solve_at(lo_a + np.clip(np.asarray(u, float), 0.0, 1.0) * span)
            return (
                _objective_value(out, objective),
                complex(out.get("z_in_re", 0.0), out.get("z_in_im", 0.0)),
                float(out.get("z0_ohms", 50.0) or 50.0),
            )

        u_best, _obj_best = _surrogate_seed(
            _probe, d, n_seed, seed_budget, np.random.default_rng(seed_state)
        )
        # The incumbent is a SOLVED point, never the surface's argmin.
        x0 = list(lo_a + u_best * span)
        seed_index = 0
        seed_total = 0

    if newton_path:
        box2 = list(zip(lo, hi, strict=True))
        total2 = int(max_evals) if max_evals else min(200, 40 * len(free))
        rng2 = np.random.default_rng(seed_state)

        def _probe_z(x):
            # Drives the seeding readout the same way #1176's does: the survey
            # samples the whole box, so its residual jumps around and a bare
            # eval number reads as the run going backwards.
            nonlocal seed_index
            seed_index += 1
            zs = _feed_zs(_solve_at(list(x)))
            return zs[0] if len(zs) == 1 else None

        def _probe_f(x):
            return _residual_vec(_solve_at(list(x)))

        # The seed runs unconditionally on this path: the study measured that
        # bare Newton FAILS on a real deck from the catalogue start, so the
        # global sample is part of the method here rather than a toggle. The
        # `seed_surrogate` toggle keeps its meaning for the Nelder-Mead path,
        # which is the only place it ever applied.
        phase = "seeding"
        n_coef2 = 1 + 2 + 3
        seed_index, seed_total = 0, n_coef2
        x_pred, ranked = _surrogate_root_start(
            _probe_z, box2, n_coef2, rng2, float(out0.get("z0_ohms", 50.0) or 50.0)
        )
        n_seed = n_coef2
        seed_index, seed_total = 0, 0

        # Try the predicted crossing first, then the best solved samples. A
        # restart costs only its own steps -- the samples are already paid for,
        # and the memo answers them free.
        starts = [x for x in ([x_pred] if x_pred else []) + ranked[:2] if x]
        phase = "newton"
        xr, ok, root_reason = None, False, "no-start"
        for st in starts:
            budget_n = total2 - n_evals
            if budget_n < 4:
                root_reason = "budget"
                break
            xr, ok, root_reason = _newton_root2(_probe_f, st, box2, budget_n)
            if ok:
                break
        if ok:
            x_root, method = xr, "seed + newton"
        else:
            # Stalled, singular, or out of budget. Hand the best SOLVED point
            # to Nelder-Mead and say why -- never present a bound as a root.
            phase = "fallback"
            method = f"nelder-mead (root: {root_reason})"
            if xr is not None:
                x0 = [
                    min(max(float(v), lob), hib)
                    for v, lob, hib in zip(xr, lo, hi, strict=True)
                ]

    # Cap the work: each eval is a full solve. ~40 per free param, hard-capped so
    # a wide search can't run away. The UI can override via max_evals. The
    # seed's own evals come out of this budget, so a seeded run never costs
    # more solves than an unseeded one.
    if x_root is not None:
        # The root path converged; Nelder-Mead has nothing to add and would
        # only spend solves confirming it.
        x_best = [
            min(max(float(v), lob), hib)
            for v, lob, hib in zip(x_root, lo, hi, strict=True)
        ]
    else:
        phase = "nelder-mead" if phase == "search" else phase
        maxfev = max(
            1, (int(max_evals) if max_evals else min(200, 40 * len(free))) - n_evals + 1
        )
        res = minimize(
            f,
            x0,
            method="Nelder-Mead",
            bounds=list(zip(lo, hi, strict=True)),
            options={"maxfev": maxfev, "xatol": 1e-4, "fatol": 1e-5},
        )

        # res.x can sit a hair outside bounds after the final reflection; clip.
        x_best = [
            min(max(float(v), lob), hib)
            for v, lob, hib in zip(res.x, lo, hi, strict=True)
        ]
    out1 = _solve_at(x_best)

    before = _objective_value(out0, objective)
    after = _objective_value(out1, objective)
    # Only claim the optimum if it actually didn't get worse (Nelder–Mead can
    # report success while terminating at the start point for a flat objective).
    best_params = (
        dict(zip(names, x_best, strict=True))
        if after <= before
        else dict(zip(names, x0, strict=True))
    )

    return {
        "objective": objective,
        "params": {k: float(v) for k, v in best_params.items()},
        "objective_before": before,
        "objective_after": min(before, after),
        "metrics_before": _metrics(out0),
        "metrics_after": _metrics(out1 if after <= before else out0),
        "n_evals": n_evals,
        # Objective evaluations vs solver calls: they differ by the memo's
        # hits (#1176). `n_evals` keeps its meaning — one per `_solve_at`, so
        # the progress stream stays gapless — and this is what the run
        # actually cost.
        "n_solves": n_solves,
        # How many of the evals went to the surrogate seed (#1176); 0 when it
        # did not run. The readout distinguishes the phases with this.
        "n_seed": n_seed,
        # Which path actually ran, and what the root-finder was driving to zero
        # (#1202). `residual_after` is None for objectives that are not roots.
        "method": method,
        "residual_before": _residual(out0, objective),
        "residual_after": _residual(out1 if after <= before else out0, objective),
        "improved": after < before,
    }

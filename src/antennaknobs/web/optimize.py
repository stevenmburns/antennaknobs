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
                }
            )
        return out

    def f(x) -> float:
        return _objective_value(_solve_at(x), objective)

    out0 = _solve_at(x0)

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

    # Cap the work: each eval is a full solve. ~40 per free param, hard-capped so
    # a wide search can't run away. The UI can override via max_evals. The
    # seed's own evals come out of this budget, so a seeded run never costs
    # more solves than an unseeded one.
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
        min(max(float(v), lob), hib) for v, lob, hib in zip(res.x, lo, hi, strict=True)
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
        "improved": after < before,
    }

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


def optimize(
    base_req: dict,
    free: list[dict],
    objective: str = "swr",
    *,
    solve_fn: Callable[[dict], dict],
    max_evals: int | None = None,
    on_progress: Callable[[dict], None] | None = None,
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
                }
            )
        return out

    def f(x) -> float:
        return _objective_value(_solve_at(x), objective)

    out0 = _solve_at(x0)

    # Cap the work: each eval is a full solve. ~40 per free param, hard-capped so
    # a wide search can't run away. The UI can override via max_evals.
    maxfev = int(max_evals) if max_evals else min(200, 40 * len(free))
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
        "improved": after < before,
    }

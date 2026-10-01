"""Holding an objective at every sweep point (AK#1757, sweep-framework step 6).

An `analyses.Hold` says "keep it resonant (or matched) while this knob
sweeps": at each swept x the hold's knobs are re-solved for its objective,
and the analysis's views are drawn at that optimised point. Nothing here is a
second optimizer. Each point IS one call of the workbench's own
``web.optimize.optimize`` (its scalar secant / bracket for ``resonance`` on
one knob, its two-component Newton for ``match_z0`` on two), with:

- ``warm=True`` when the point starts from the previous point's solution
  (``Hold.warm_start``, continuation, as the workbench's track-while-drag
  does), so the two-knob path tries Newton from that start before sampling
  the box;
- ``fallback=False``, so a point with no root is a GAP, not a simplex's
  best effort drawn as a plausible wrong value.

The rules (docs/design/sweep-framework-step6.md):

1. A point the optimizer does not converge at (its root path's own verdict),
   or whose solved residual is over `HOLD_TOL`, is a gap with its reason. The
   next point warm-starts from the last CONVERGED point. After
   `FAILS_BEFORE_COLD` failures in a row, each remaining point cold-starts
   from the defaults once (a converged one resumes the warm chain); one that
   fails then is given up on, a gap.
2. The bounds are the knobs' own ``ui_params`` min/max, as the workbench's
   optimizer reads them (its knob menu's opt extents default to the slider's).
   A held knob without both is refused by name.
3. What the optimizer cannot serve is refused by name, not run: ``swr`` (a
   minimisation, no root and so no verdict a point could be drawn on), a
   frequency or density sweep, a map, a multi-feed design.

Framework-free: the CLI (`analysis_run`) and the workbench's ``/param_sweep``
(``web.server``) both call `hold_line`, with a ``solve_fn`` of their own.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from . import analyses as an

#: The residual (ohms) a converged point must be within: the workbench's
#: hold tolerance (``web.tracker.TRACK_TOL``, the user-facing one the #1202
#: study measured against). The optimizer's own stop is far tighter
#: (``web.optimize._ROOT_FTOL``, 1e-3 ohm); this is the backstop for a root
#: called on a step size (``xtol``) whose solved residual is still large.
HOLD_TOL = 1.0

#: Failures in a row after which the remaining points cold-start (rule 1).
FAILS_BEFORE_COLD = 3


class HoldRefused(ValueError):
    """What a hold cannot serve, by name: the analysis, or one cell."""


def analysis_refusal(a: an.Analysis, builder=None) -> str | None:
    """Why ``a``'s hold cannot run at all (beyond `an.problems`), or None.
    ``builder`` (the analysis's design) resolves a role or a knob named
    directly, to tell a density knob; without it only the spec is read."""
    h = a.hold
    if h is None:
        return None
    if h.objective == "swr":
        return (
            "hold swr: SWR is a minimisation, not a root, so the optimizer has "
            "no verdict a held point could be drawn or left a gap on; hold "
            "resonance (one knob) or match_z0 (two)"
        )
    if len(a.sweeps) != 1:
        return (
            "a hold on a two-sweep map: not in v1 (sweep-framework step 6 holds "
            "along one swept knob); cross the second knob as a family"
        )
    s = a.sweep
    if s.knob == an.FREQUENCY:
        return (
            "a hold on a frequency sweep: not in v1 (the frequency sweep is one "
            "build solved across the band, and a hold rebuilds and re-solves at "
            "every point; sweep a knob, or hold at the measurement frequency)"
        )
    dens = an.density_knob(builder) if builder is not None else None
    swept = an.resolve(s.knob, builder).knob if builder is not None else None
    if s.knob == an.DENSITY or (swept is not None and swept in (dens, "nominal_nsegs")):
        return (
            "a hold on a density ladder: not in v1 (a convergence study reads "
            "Z as the mesh refines, and a hold would move the design under it)"
        )
    return None


def free_of(hold: an.Hold, builder) -> list[dict]:
    """The hold's knobs on ``builder`` as the optimizer takes them,
    ``[{name, min, max}]``, bounded by each knob's ``ui_params`` min/max
    (rule 2); `HoldRefused` by name for a knob that does not resolve, the
    density knob, or a knob with no range of its own."""
    params = an._params(builder)
    ui = an._ui(params)
    dens = an.density_knob(builder)
    out = []
    for k in hold.adjust:
        r = an.resolve(k, builder)
        if r.knob is None:
            raise HoldRefused(r.reason)
        if r.knob in (dens, "nominal_nsegs"):
            raise HoldRefused(
                f"the hold adjusts {r.knob}, the density knob: the engine holds "
                "every solve at its own density, so it is not a knob to hold"
            )
        meta = ui.get(r.knob)
        lo = meta.get("min") if isinstance(meta, Mapping) else None
        hi = meta.get("max") if isinstance(meta, Mapping) else None
        if lo is None or hi is None or not float(lo) < float(hi):
            raise HoldRefused(
                f"the hold adjusts {r.knob}, which has no ui_params min/max to "
                "bound it: the optimizer searches within a knob's own range; "
                f'give {r.knob} a "min" and "max" in ui_params'
            )
        out.append({"name": r.knob, "min": float(lo), "max": float(hi)})
    return out


@dataclass(frozen=True)
class HeldPoint:
    """One swept point of a held line. ``start`` is where the optimizer
    started (``cold``: the defaults; else the last converged point's knobs);
    ``params`` and ``z`` are its answer (port 0), the best SOLVED point even
    when it did not converge; ``converged`` False makes it a gap, with
    ``reason``."""

    x: float
    start: dict
    cold: bool
    params: dict
    z: complex
    residual: float | None
    converged: bool
    reason: str | None
    method: str
    n_solves: int


def _gap_reason(res: Mapping, free: Sequence[Mapping], objective: str) -> str | None:
    """Why ``res`` (an ``optimize`` result) is a gap, or None when it holds."""
    resid = res.get("residual_after")
    if res.get("converged"):
        if resid is not None and resid <= HOLD_TOL:
            return None
        return (
            f"the root search stopped at a residual of {resid:.3g} ohm, over the "
            f"hold's {HOLD_TOL:g} ohm"
        )
    why = res.get("root_reason") or "no root path ran"
    words = {
        "no-sign-change": "X does not change sign anywhere in the knob's range",
        "no-crossing": "R = Z0 and X = 0 do not cross within the knobs' ranges",
        "stalled": "the root search stalled",
        "singular": "the knobs do not move R and X independently here",
        "flat": "X does not respond to the knob",
        "budget": "the optimizer ran out of solves",
        "multi-feed": "the design has several feeds",
    }.get(why, why)
    target = "resonance" if objective == "resonance" else "match"
    text = f"no {target} held ({words})"
    params = res.get("params") or {}
    edge = []
    for f in free:
        v = params.get(f["name"])
        if v is None:
            continue
        span = f["max"] - f["min"]
        if v <= f["min"] + 0.002 * span:
            edge.append(f"{f['name']} at its ui_params min {f['min']:g}")
        elif v >= f["max"] - 0.002 * span:
            edge.append(f"{f['name']} at its ui_params max {f['max']:g}")
    if edge:
        text += "; " + ", ".join(edge)
    return text


def hold_point(
    x,
    knob: str,
    start: Mapping,
    free: Sequence[Mapping],
    objective: str,
    *,
    solve_fn: Callable[[dict], dict],
    warm: bool,
    base: Mapping | None = None,
    max_evals: int | None = None,
) -> tuple[dict, dict]:
    """ONE held point, exactly as `hold_line` runs it: ``(request, optimize
    result)``. The request is ``base`` with the swept ``knob`` at ``x`` and
    the held knobs at ``start``; the result is ``web.optimize.optimize`` on
    it. The seam a test calls the optimizer standalone beside."""
    from .web.optimize import optimize

    req = {**(base or {}), knob: x, **start}
    res = optimize(
        req,
        [dict(f) for f in free],
        objective,
        solve_fn=solve_fn,
        max_evals=max_evals,
        warm=warm,
        fallback=False,
    )
    return req, res


def hold_line(
    xs: Sequence,
    knob: str,
    free: Sequence[Mapping],
    objective: str,
    *,
    solve_fn: Callable[[dict], dict],
    defaults: Mapping,
    warm_start: bool = True,
    base: Mapping | None = None,
    max_evals: int | None = None,
    on_point: Callable[[HeldPoint], None] | None = None,
) -> list[HeldPoint]:
    """The held line along ``xs`` of ``knob`` (module docstring, rule 1).
    ``defaults`` are the held knobs' starting values (the design's own);
    ``on_point`` sees each point as it lands (the workbench streams them)."""
    points: list[HeldPoint] = []
    last: dict | None = None
    fails = 0
    cold_mode = False
    failed: list[Exception] = []
    for x in xs:
        warm = warm_start and last is not None and not cold_mode
        start = dict(last) if warm else {f["name"]: defaults[f["name"]] for f in free}
        try:
            _req, res = hold_point(
                x,
                knob,
                start,
                free,
                objective,
                solve_fn=solve_fn,
                warm=warm,
                base=base,
                max_evals=max_evals,
            )
        except HoldRefused:
            raise
        except (ValueError, NotImplementedError) as e:
            # A solve the search asked for failed: a candidate the engine
            # refuses (a wire end in the ground plane, say). The optimizer has
            # no notion of a failed probe, so the POINT failed: a gap with the
            # engine's words, never a value. Every point failing is the
            # engine refusing the cell, re-raised below.
            failed.append(e)
            pt = HeldPoint(
                x=x,
                start=start,
                cold=not warm,
                params=dict(start),
                z=complex(math.nan, math.nan),
                residual=None,
                converged=False,
                reason=f"a solve inside the search failed: {_short(e)}",
                method="failed",
                n_solves=0,
            )
        else:
            reason = _gap_reason(res, free, objective)
            m = res["metrics_after"]
            pt = HeldPoint(
                x=x,
                start=start,
                cold=not warm,
                params=dict(res["params"]),
                z=complex(m["z_in_re"], m["z_in_im"]),
                residual=res.get("residual_after"),
                converged=reason is None,
                reason=reason,
                method=str(res.get("method")),
                n_solves=int(res.get("n_solves") or 0),
            )
        points.append(pt)
        if pt.converged:
            last, fails, cold_mode = pt.params, 0, False
        else:
            fails += 1
            if warm_start and fails >= FAILS_BEFORE_COLD:
                # Rule 1's recovery: from here each point cold-starts from
                # the defaults, once; a converged one resumes the warm chain.
                cold_mode = True
        if on_point is not None:
            on_point(pt)
    if points and len(failed) == len(points):
        raise failed[0]
    return points


def _short(e: Exception, limit: int = 160) -> str:
    """An engine's refusal, cut to its first sentence (they run long)."""
    text = " ".join(str(e).split())
    cut = text.find(": ", 40)
    if 0 < cut < limit:
        text = text[:cut]
    return text if len(text) <= limit else text[: limit - 1] + "…"


def builder_solve_fn(builder, factory: Callable, z0: float) -> Callable[[dict], dict]:
    """The CLI's ``solve_fn``: each knob of the request set on ``builder``
    (a cell's own), solved through the cell's engine ``factory``, as
    ``sweep._solve_at`` solves a knob sweep, and answered in the optimizer's
    response shape. A design with several feeds is refused by name: the
    optimizer's root paths hold one feed's Z."""
    params = an._params(builder)

    def solve(req: dict) -> dict:
        for k, v in req.items():
            if k in params:
                setattr(builder, k, v)
        zs = factory(builder).impedance()
        zs = list(zs) if hasattr(zs, "__len__") else [zs]
        if len(zs) != 1:
            raise HoldRefused(
                f"this design drives {len(zs)} feeds: a hold drives one feed's "
                "Z to its target (the optimizer's root paths are single-feed)"
            )
        z = complex(zs[0])
        return {"z_in_re": z.real, "z_in_im": z.imag, "z0_ohms": float(z0)}

    return solve


def defaults_of(builder, free: Sequence[Mapping]) -> dict:
    """The held knobs' values on ``builder``: where a cold point starts."""
    return {f["name"]: float(getattr(builder, f["name"])) for f in free}


def metric_off(metric, gain, freq) -> tuple:
    """``(value, why)``: ``metric`` read off a solved gain evaluator at
    ``freq`` (the workbench's captured state, `adapter.capture_solved_metrics`),
    as ``/param_sweep`` reads a plain point's; ``why`` names a metric the
    engine cannot read, with ``value`` None."""
    from . import metrics as mx

    try:
        return mx.evaluate(metric, mx.EvaluatorSource(gain, freq)), None
    except (ValueError, NotImplementedError) as e:
        return None, str(e)

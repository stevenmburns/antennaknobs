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

A BAND hold (``an.Hold(bands=...)``, AK#1906) holds a multi-band objective
instead: each point is one call of the band optimizer
(``web.optimize_bands.optimize_bands``, the ``optimize --bands`` run), the
SWR minimax for ``swr`` and the root form for ``resonance`` / ``match_z0``
(`hold_bands_line`). Rule 1 applies as it is: a point the root form does not
reach (its ``root_status`` is not "root") is a gap, never its near miss, and
so is a minimax answer with no band near a match. Its knobs may be group
leaves (``bands.0.length``), and a knob the design gives no range searches
+/-20 % of its value, as ``optimize --bands`` does (`band_free_of`).

Framework-free: the CLI (`analysis_run`) and the workbench's ``/param_sweep``
(``web.server``) both call `hold_line` (and `hold_bands_line`), with a
``solve_fn`` (``sweep_fn``) of their own.
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
    if h.objective == "swr" and not h.bands:
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
    #: A band hold's per-band readings at the answer (the band optimizer's
    #: records: freq_mhz, z_re, z_im, swr, ...); () for a hold at one
    #: frequency, whose ``z`` is its one reading.
    bands: tuple = ()


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

    def point(x, start: dict, warm: bool) -> HeldPoint:
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
        reason = _gap_reason(res, free, objective)
        m = res["metrics_after"]
        return HeldPoint(
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

    return _line(xs, free, point, defaults, warm_start, on_point)


def _line(
    xs: Sequence,
    free: Sequence[Mapping],
    point: Callable[[object, dict, bool], HeldPoint],
    defaults: Mapping,
    warm_start: bool,
    on_point: Callable[[HeldPoint], None] | None,
) -> list[HeldPoint]:
    """Rule 1's walk along ``xs``, whatever a point optimizes: ``point(x,
    start, warm)`` solves one, from the last converged point's knobs when
    ``warm``, else from ``defaults``."""
    points: list[HeldPoint] = []
    last: dict | None = None
    fails = 0
    cold_mode = False
    failed: list[Exception] = []
    for x in xs:
        warm = warm_start and last is not None and not cold_mode
        start = dict(last) if warm else {f["name"]: defaults[f["name"]] for f in free}
        try:
            pt = point(x, start, warm)
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


# ── band holds (AK#1906) ─────────────────────────────────────────────────────


def band_free_of(h: an.Hold, builder) -> list[dict]:
    """A band hold's knobs on ``builder`` as the band optimizer takes them,
    ``[{name, min, max}]``: a role or a knob name resolved as for any hold,
    or a group leaf by its path; each bounded as ``optimize --bands`` bounds
    it (its ``ui_params`` range, else +/-20 % of its value,
    `band_opt.free_for`). `HoldRefused` names one that cannot be."""
    from .band_opt import free_for

    dens = an.density_knob(builder)
    names = []
    for k in h.adjust:
        r = an.resolve(k, builder)
        if r.knob is None and an.is_leaf(k, builder):
            names.append(k)
            continue
        if r.knob is None:
            raise HoldRefused(r.reason)
        if r.knob in (dens, "nominal_nsegs"):
            raise HoldRefused(
                f"the hold adjusts {r.knob}, the density knob: the engine holds "
                "every solve at its own density, so it is not a knob to hold"
            )
        names.append(r.knob)
    try:
        return free_for(builder, names)
    except SystemExit as e:
        raise HoldRefused(str(e)) from None


def band_defaults_of(builder, free: Sequence[Mapping]) -> dict:
    """A band hold's knobs on ``builder``, group leaves by their path."""
    from .opt import _get_path

    return {f["name"]: float(_get_path(builder, f["name"])) for f in free}


def bands_of(h: an.Hold) -> list:
    """The hold's bands as the band optimizer takes them, a band naming no
    objective at the hold's."""
    from .web.optimize_bands import Band

    return [
        Band(b.freq, b.objective_in(h.objective), b.feed, b.z0, tuple(b.knobs))
        for b in h.bands
    ]


def _band_gap_reason(res: Mapping, form: str) -> str | None:
    """Why the band optimizer's answer ``res`` is a gap, or None (module
    docstring): the root form not at a root, or no band near a match."""
    if form == "root" and res.get("root_status") != "root":
        why = res.get("root_status") or "no root path ran"
        text = f"no root held across the bands ({why})"
        edge = [f"{b['name']} at its {b['bound']}" for b in res.get("at_bound") or []]
        return text + ("; " + ", ".join(edge) if edge else "")
    if res.get("far_from_match"):
        return f"no band near a match (worst SWR {res.get('worst_swr_after', math.inf):.3g})"
    return None


def hold_bands_point(
    x,
    knob: str,
    start: Mapping,
    free: Sequence[Mapping],
    h: an.Hold,
    *,
    sweep_fn: Callable[[dict, list], dict],
    base: Mapping | None = None,
    max_evals: int | None = None,
) -> tuple[dict, dict]:
    """ONE held point of a band hold, as `hold_bands_line` runs it:
    ``(request, band optimizer result)``, the request ``base`` with the
    swept ``knob`` at ``x`` and the held knobs at ``start``. The seam a
    test calls the band optimizer standalone beside."""
    from .web.optimize_bands import optimize_bands

    req = {**(base or {}), knob: x, **start}
    res = optimize_bands(
        req,
        [dict(f) for f in free],
        bands_of(h),
        sweep_fn=sweep_fn,
        mode=h.form,
        max_evals=max_evals,
        mean_weight=h.mean_weight,
    )
    return req, res


def hold_bands_line(
    xs: Sequence,
    knob: str,
    free: Sequence[Mapping],
    h: an.Hold,
    *,
    sweep_fn: Callable[[dict, list], dict],
    defaults: Mapping,
    base: Mapping | None = None,
    max_evals: int | None = None,
    on_point: Callable[[HeldPoint], None] | None = None,
) -> list[HeldPoint]:
    """A band hold's line along ``xs`` of ``knob``: rule 1 as `hold_line`
    walks it, each point one band run (`hold_bands_point`). A point's ``z``
    is its first band's reading and ``bands`` every band's; ``residual`` the
    worst band's value (SWR, or ohms for a root)."""

    def point(x, start: dict, warm: bool) -> HeldPoint:
        _req, res = hold_bands_point(
            x,
            knob,
            start,
            free,
            h,
            sweep_fn=sweep_fn,
            base=base,
            max_evals=max_evals,
        )
        reason = _band_gap_reason(res, h.form)
        after = tuple(res.get("bands_after") or ())
        z = (
            complex(after[0]["z_re"], after[0]["z_im"])
            if after and after[0].get("z_re") is not None
            else complex(math.nan, math.nan)
        )
        return HeldPoint(
            x=x,
            start=start,
            cold=not warm,
            params=dict(res["params"]),
            z=z,
            residual=res.get("objective_worst_after"),
            converged=reason is None,
            reason=reason,
            method=f"bands {res.get('form')}",
            n_solves=int(res.get("n_solves") or 0),
            bands=after,
        )

    return _line(xs, free, point, defaults, h.warm_start, on_point)


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

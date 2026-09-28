"""What the workbench can run of a design's analyses (AK#1757, step 3).

``POST /analyses`` lists a design's offered analyses (`analyses.offered`),
each with its one-line summary, its Python, its problems, and a
``workbench`` entry saying how the Z-vs-parameter view runs it:

- ``{runs: True, param, values, log, note}``: ``param`` and ``values`` are
  exactly what ``/param_sweep`` takes. The values come from the same
  functions ``antennaknobs analyze`` sweeps (`analysis_run.knob_xs`,
  `analysis_run.density_rungs`), so a picked analysis and the CLI solve one
  ladder;
- ``{runs: False, why}``: why the workbench cannot draw it yet, one
  string (reasons joined by "; "), each naming the sweep-framework step it
  is planned for, or the problem `analyses.problems` found.

A cross over engines or grounds runs ONE cell in the workbench, the
session's own engine and ground, and ``note`` says so. Framework-free, so it
is tested without a server.
"""

from __future__ import annotations

from collections.abc import Mapping

from .. import analyses as an
from .. import analysis_run as ar
from .param_sweep import DENSITY, ParamSweepError, sweep_values

# The sweep-framework step each piece the workbench cannot draw yet is
# planned for (Steve, 2026-09-28): 4 the frequency sweep and the SWR / S11 /
# Smith views; 5 planes, designs, families and the map; 6 hold.
_VIEW_STEP = {an.Swr: 4, an.S11: 4, an.Smith: 4, an.Map: 5, an.Knobs: 6, an.Table: 4}
_CROSS_STEP = {"planes": 5, "designs": 5, "step": 5}
# The crosses the workbench draws one cell of: the session's own.
_SESSION_CROSS = {"engines": "engine", "grounds": "ground"}


def _later(what: str, step: int) -> str:
    return f"{what}: not in the workbench yet (sweep-framework step {step})"


def gaps(a: an.Analysis) -> list[str]:
    """What keeps the workbench from running ``a`` (beyond `an.problems`)."""
    out = []
    if len(a.sweeps) > 1:
        out.append(_later("a two-sweep map", 5))
    elif a.sweep.knob == an.FREQUENCY:
        out.append(_later("a frequency sweep", 4))
    for c in a.crosses:
        if c.kind in _CROSS_STEP:
            out.append(_later(f"a cross over {c.kind}", _CROSS_STEP[c.kind]))
    if a.hold is not None:
        out.append(_later("hold (optimise at each point)", 6))
    # The Z-vs-parameter view draws R and X; an analysis without Rx has
    # nothing the view can show.
    if not any(isinstance(v, an.Rx) for v in a.views):
        out += [
            _later(f"the {type(v).__name__} view", _VIEW_STEP.get(type(v), 4))
            for v in a.views
        ]
    return out


def _note(a: an.Analysis, *, deck_density: bool) -> str | None:
    parts = []
    crossed = [c for c in a.crosses if c.kind in _SESSION_CROSS]
    if crossed:
        kinds = " and ".join(c.kind for c in crossed)
        own = " and ".join(_SESSION_CROSS[c.kind] for c in crossed)
        parts.append(
            f"crossed over {kinds}: the workbench draws this session's {own}; "
            f"`antennaknobs analyze` draws all {a.curves}"
        )
    for field in ("engine", "ground"):
        value = getattr(a, field)
        crossed_here = any(_SESSION_CROSS[c.kind] == field for c in crossed)
        if value is not None and not crossed_here:
            parts.append(
                f"the analysis names {field} {value}; the workbench uses this "
                f"session's {field}"
            )
    if deck_density:
        parts.append(
            "Z∞ for a deck's own density knob is CLI-only for now: the "
            "workbench draws the ladder as a knob sweep"
        )
    return "; ".join(parts) or None


def workbench(a: an.Analysis, builder, req: Mapping) -> dict:
    """How the workbench runs ``a`` on ``builder`` (built from ``req``)."""
    why = an.problems(a, builder) + gaps(a)
    if why:
        return {"runs": False, "why": "; ".join(why)}
    s = a.sweep
    knob = an.resolve(s.knob, builder).knob
    density = knob == "nominal_nsegs" or knob == an.density_knob(builder)
    if density:
        values = list(ar.density_rungs(s)[0])
        param = DENSITY if knob == "nominal_nsegs" else knob
        log = True
    else:
        try:
            values = [float(x) for x in ar.knob_xs(s, builder, knob)]
        except SystemExit as e:  # `_knob_range`'s refusal, by name
            return {"runs": False, "why": str(e)}
        param = knob
        log = s.spacing == "log"
    try:
        # What /param_sweep would solve: an int knob's values as whole counts.
        values = sweep_values(req, param, values)
    except ParamSweepError as e:
        return {"runs": False, "why": str(e)}
    return {
        "runs": True,
        "param": param,
        "values": values,
        "log": log,
        "note": _note(a, deck_density=density and param != DENSITY),
    }


def builder_for(cls, req: Mapping):
    """The design ``req`` names, built as ``/param_sweep`` builds it
    (`adapter._build_builder`: the variant's params, the request's knobs),
    with the variant's ``ui_params`` put back: a Builder is constructed
    without them, and they carry the roles and knob ranges an analysis
    resolves against."""
    from .adapter import _build_builder, _variant_params

    builder = _build_builder(cls, dict(req))
    ui = _variant_params(cls, req.get("variant")).get("ui_params")
    if ui is not None:
        builder.ui_params = ui
    return builder


def offer(builder, req: Mapping) -> list[dict]:
    """Every offered analysis on ``builder``, as ``/analyses`` serves it."""
    out = []
    for a in an.offered(builder):
        out.append(
            {
                "name": a.name,
                "summary": ar.summary(a, builder),
                "code": an.to_code(a),
                "problems": an.problems(a, builder),
                "workbench": workbench(a, builder, req),
            }
        )
    return out

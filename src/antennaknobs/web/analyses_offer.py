"""What the workbench can run of a design's analyses (AK#1757, steps 3-4).

``POST /analyses`` lists a design's offered analyses (`analyses.offered`),
each with its one-line summary, its Python, its problems, and a
``workbench`` entry saying how the workbench runs it:

- ``{runs: True, kind: "knob", param, values, log, views, metric, hold,
  note}``: the Z-vs-parameter view. ``hold`` is None, or the analysis's hold
  (AK#1757 step 6: ``{objective, knobs, bounds, z0, warm_start, spec}``,
  `_hold_entry`), which each curve's ``/param_sweep`` sends back as
  ``spec``. ``param`` and ``values`` are exactly what
  ``/param_sweep`` takes. The values come from the same functions
  ``antennaknobs analyze`` sweeps (`analysis_run.knob_xs`,
  `analysis_run.density_rungs`), so a picked analysis and the CLI solve one
  ladder. ``views`` are the ones the chart draws of a knob sweep ("Rx",
  "Smith", "Table", and "Metric" for an `analyses.MetricPlot`, AK#1828), in
  the analysis's order; ``metric`` is the first MetricPlot as the chart
  draws it, ``{name, unit, relative_to, relative_unit, spec}`` (``spec`` the
  metric as data, which ``/param_sweep`` reads off each point), or None;
- ``{runs: True, kind: "frequency", range, level, points, freqs, views,
  swr, note}``: the frequency sweep (step 4). ``range`` is the span and
  grid `analysis_run.frequency_range` resolves, in ``/examples``'
  ``sweep_range`` shape, when it is absolute (the analysis's own, or the
  design's: ``level`` "analysis", "file" or "design"); None when it is the
  band policy (``level`` "policy" / "default"), which is relative to the
  session's band and so is the frontend's to place. ``points`` is the
  analysis's own count, or None. ``freqs`` is the analysis's explicit
  frequency list (``Sweep(values=...)``), exactly the MHz ``analyze``
  sweeps (`analysis_run.frequency_xs`), in its order, and None for a range;
  with a list, ``range`` spans it (lin, its count) and ``level`` is
  "analysis" (step 5 unit 5). ``views`` are the ones the workbench draws
  ("Swr", "S11", "Smith", "Rx", "Table"), in the analysis's order; ``swr``
  is the Swr view's ``scale`` and the ``Ref`` threshold;
- ``{runs: True, kind: "pattern", views, freq, note}`` (AK#1757 step 7): a
  pattern (``sweep=None``), one solve per cell at its measurement
  frequency, the solve the live chart and the pattern pins draw from.
  ``views`` are its views in order, each ``{view: "Elevation", az}``,
  ``{view: "Azimuth", el}`` or ``{view: "PatternTable"}``; ``freq`` is the
  tab's design's measurement frequency (a cell's own may differ: a state or
  a family setting ``freq``). The chart asks ``POST /pattern_cell`` for each
  cell (`server.pattern_cell_endpoint`);
- ``{runs: True, kind: "map", x, y, refs, views, limit, note}`` (the sweep
  framework's map, docs/design/sweep-framework-map.md): a two-knob map, one
  grid, which the chart asks ``POST /map`` for. ``x`` and ``y`` are each
  ``{param, values, log, lo, hi, points, spacing}``: ``param`` and
  ``values`` exactly what ``/map`` takes, from `analysis_run.knob_xs`, the
  CLI's own grid, and the axis as the spec writes it (``lo`` / ``hi`` the
  ends of ``values``). ``refs`` is ``{r, x, swr}``, the `Ref` lines the
  chart contours (R = r, X = x, and SWR = swr as its |Γ|), and ``views``
  is ``["Map"]``; the Table view is left out by name in ``note``.
  ``limit`` is ``{points, seconds}`` on the hosted instance (its map cap
  and sweep wall-time budget), None locally. A map
  with a cross, or with a frequency or density axis, is ``runs: False``
  with its reason (map note, decisions 9 and 10);
- ``{runs: False, why}``: why the workbench cannot draw it yet, one
  string (reasons joined by "; "), each naming the sweep-framework step it
  is planned for, or the problem `analyses.problems` found.

Both runnable shapes also carry ``engines`` and ``grounds``: the engine
specs and ground specs the analysis lists (its cross over engines or
grounds, else its one ``engine`` / ``ground``), in its order, or None when
it names none. The analysis chart preselects the solver slots and ground
slots that hold them (AK#1757 step 5 unit 4). It skips an engine no slot
holds, naming it in a note, and draws every slot when it would skip them all
(Steve, 2026-10-01); a ground no slot holds is a refused cell. With None it
draws the session's active slot and ground. All of that is the page's:
these lists are what the analysis names, as ``analyze`` runs them.

And the analysis's other crosses, each None when it has none, which the
chart multiplies with its slots into one curve per cell as
``antennaknobs analyze`` does (`analysis_run.cells`):

- ``axes``: the kinds of its crosses, in the order they are written (the
  order of the product, and of the parts of a cell's label);
- ``planes``: ``[{name, refused}]``, ``refused`` being the CLI's own words
  for a plane this design does not offer (`analysis_run.plane_refusal`), or
  that the workbench cannot measure at (a drive of several sources);
- ``designs``: ``[{name, refused, param, values, range, freqs}]``, each
  design as its own defaults build it (the CLI's design cell): ``refused``
  names a design the catalog lacks or whose sweep does not resolve there; a
  knob sweep's ``param`` and ``values`` are that design's own (a role may
  resolve to another knob, and a range left to the knob is that design's
  range); a frequency sweep's ``range`` (with its ``level``) and ``freqs``
  are that design's own band and the exact grid ``analyze`` sweeps on it
  (`analysis_run.frequency_xs`), so two designs on different bands each
  sweep their own;
- ``states``: ``[{name, design, knobs, label, refused, param, values,
  range, freqs, on}]`` (step 7): each named knob setting, set over its
  design's DEFAULTS (the tab's variant's for the tab's own design, never
  its live knobs, so a state is the same curve every session), with the
  cell's sweep served as a design cell's is (`_state_entry`; a pattern's
  cells sweep nothing, so only ``refused`` says anything); ``on`` holds
  one design entry per design when an unnamed state multiplies with a
  designs cross;
- ``step``: ``{knob, values, labels}``, a family: the knob each cell sets,
  its values (coerced as ``/param_sweep`` coerces; a family over the
  measurement frequency, ``knob`` "freq", is served as MHz above zero,
  AK#1935), and each cell's label part (`analysis_run.step_label`);
- ``cells``: ``[{label, state, engine, ground, plane, refused, param,
  values, range, freqs}]`` (step 7 unit 4), a ``cells=`` cross's listed
  cells, in order: a UNION the chart draws one curve per entry of, never
  multiplied with its slot checkboxes. ``state`` is ``{name, design,
  variant, knobs, label}`` or None; ``engine`` / ``ground`` the cell's own
  spec or None (the analysis's, else the chart's active slot); the sweep
  and refusal are served as a state's are (`_cell_entry`).

Every design, state and listed cell entry also says whether it is a
MetricPlot's ``reference`` (the cell its ``relative_to`` names) and ``fixed``
(solved once at its own setting: ``param`` the swept knob and ``values`` its
one value of it, which it sets).

Every entry also carries ``spec``, the analysis as data (`analyses.to_data`),
which the chart edits and sends back to keep what it built (``POST /keep``,
unit 4); and a state's entry its ``variant``.

Then the design's STUDIES (`offer_studies`, AK#1757 step 7): analyses over
several designs, from a module-level ``build_studies()`` in a studies
directory crossing it, or its own Builder's ``build_studies()`` method
(`studies`). Each is served as a design analysis is, hosted by the tab's
design (the design cross builds each of its designs at its own defaults, as
for any analysis), with its ``name`` the study's full ``source:name`` (unique
beside the design's own analyses, which the picker tells apart by name) and
``study: {source, name}``, the short name the picker shows under its Studies
group (``study`` is None on the design's own analyses). So E7 is on the invvee and the invvee_apex tabs, and on no other.

Every entry says where it comes from, ``origin`` (AK#1935): "design" (the
design's own ``build_analyses()``, inherited ones included), "generic" (the
library's, which every design is offered: the picker always heads them
General), or "study".

Framework-free, so it is tested without a server.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from pathlib import PurePath

from .. import analyses as an
from .. import analysis_run as ar
from .. import hold as hd
from .param_sweep import DENSITY, ParamSweepError, sweep_values

#: The callable metrics' functions this process has served (AK#1828), by
#: reference (``module.qualname``): what ``/param_sweep`` and ``/keep`` read a
#: page's metric data back through (`analyses.from_data`'s ``functions``).
#: Filled only by `offer` / `offer_studies`, from trusted files, so a page can
#: name a function only if this workbench offered it; on the hosted instance
#: only the catalog's own are ever offered (`hosted_refusal`).
SERVED_FUNCTIONS: dict = {}


def hosted_refusal(a: an.Analysis) -> str | None:
    """Why the hosted instance does not offer ``a`` (AK#1828 ruling): it
    calls a metric function that is not the catalog's. A callable is code
    from a file; the hosted instance runs only the catalog's (ours)."""
    foreign = [m for m in an.metrics_of(a) if not an.is_catalog_function(m.fn)]
    if not foreign:
        return None
    names = ", ".join(f"{m.name!r} ({m.fn.__qualname__})" for m in foreign)
    return (
        f"the metric {names} calls a function of its own, which runs only on a "
        "local workbench (the hosted instance runs the catalog's code only)"
    )


def _serve_functions(a: an.Analysis) -> None:
    for m in an.metrics_of(a):
        SERVED_FUNCTIONS[m.ref] = m.fn


# The workbench's frequency-sweep views, by the names /analyses serves.
_FREQUENCY_VIEWS = {
    an.Swr: "Swr",
    an.S11: "S11",
    an.Smith: "Smith",
    an.Rx: "Rx",
    an.Table: "Table",
}
# A knob sweep's: R/X against the knob, its Smith trail, the numbers, a
# metric against the knob (AK#1828), and a held sweep's knobs (AK#1757 step
# 6; `an.Analysis` refuses Knobs without a hold).
_KNOB_VIEWS = {
    an.Rx: "Rx",
    an.Smith: "Smith",
    an.Table: "Table",
    an.MetricPlot: "Metric",
    an.Knobs: "Knobs",
}


def _view_gap(v: an.View, sweep: str) -> str:
    """Why the workbench does not draw view ``v`` of a ``sweep`` sweep."""
    name = f"the {type(v).__name__} view"
    unknown = ar.not_a_view(v)
    if unknown:
        return unknown
    return (
        f"{name} of a {sweep} sweep: the analysis chart does not draw it; "
        "`antennaknobs analyze` draws it"
    )


def _served_view(v: an.View, views: Mapping) -> str | None:
    """The served name of view ``v`` among ``views`` (a subclass is its
    base), or None."""
    return next((n for cls, n in views.items() if isinstance(v, cls)), None)


def _frequency_view(v: an.View) -> str | None:
    return _served_view(v, _FREQUENCY_VIEWS)


def _knob_view(v: an.View) -> str | None:
    return _served_view(v, _KNOB_VIEWS)


def _is_frequency(a: an.Analysis) -> bool:
    return len(a.sweeps) == 1 and a.sweeps[0].knob == an.FREQUENCY


def _pattern_view(v: an.View) -> dict | None:
    """A pattern view as ``/analyses`` serves it, or None for any other."""
    if isinstance(v, an.Elevation):
        return {"view": "Elevation", "az": v.az}
    if isinstance(v, an.Azimuth):
        return {"view": "Azimuth", "el": v.el}
    if isinstance(v, an.PatternTable):
        return {"view": "PatternTable"}
    return None


def gaps(a: an.Analysis, builder=None) -> list[str]:
    """What keeps the workbench from running ``a`` (beyond `an.problems`);
    ``builder`` (the tab's design) tells a hold on its density knob."""
    if len(a.sweeps) == 2:
        return _map_gaps(a)
    out = []
    held = hd.analysis_refusal(a, builder)
    if held:
        out.append(held)
    elif a.hold is not None and a.hold.bands:
        # Its views are per-band SWR along the sweep, which the knob chart
        # does not draw (it draws one curve per cell, and no Swr view).
        out.append(
            "a hold across several bands: `antennaknobs analyze` draws it (each "
            "band's SWR along the sweep, and the knobs); not in the workbench yet"
        )
    if an.is_pattern(a):
        # Every view of a pattern is a pattern view (`an.Analysis` refuses
        # any other when built), and the chart draws each; a design's own
        # View subclass is named as the CLI names it.
        out += [why for v in a.views if (why := ar.not_a_view(v))]
    elif _is_frequency(a):
        if not any(_frequency_view(v) for v in a.views):
            out += [_view_gap(v, "frequency") for v in a.views]
    # A knob analysis the chart can show none of (only Swr, say) is refused.
    elif not any(_knob_view(v) for v in a.views):
        out += [_view_gap(v, "knob") for v in a.views]
    return out


def _map_gaps(a: an.Analysis) -> list[str]:
    """What keeps the workbench from drawing the map ``a`` (map note,
    decisions 9, 10 and 14): a cross (the chart draws one grid), a frequency
    axis (a per-point map is not the CLI's vectorized frequency solve), or
    no Map view among its views. A density axis is `analysis_run.
    density_moved`'s refusal, which the CLI shares."""
    out = []
    if a.crosses:
        kinds = ", ".join(c.kind for c in a.crosses)
        out.append(
            f"a map with a cross over {kinds}: the workbench draws one grid; "
            "`antennaknobs analyze` draws one panel per cell"
        )
    if any(s.knob == an.FREQUENCY for s in a.sweeps):
        out.append(
            "a map with a frequency axis: the workbench maps two knobs; "
            "`antennaknobs analyze` draws it"
        )
    if not any(isinstance(v, an.Map) for v in a.views):
        out += [
            f"the {type(v).__name__} view of a map: the workbench draws the "
            "Map view (hover it for the numbers); `antennaknobs analyze` "
            "prints the table"
            if isinstance(v, an.Table)
            else (ar.not_a_view(v) or _view_gap(v, "map"))
            for v in a.views
        ]
    return out


def _map_axis(s: an.Sweep, builder, req: Mapping) -> dict:
    """One map axis as ``/map`` takes it and the chart edits it, or
    `_Refusal`: the knob, its values from `analysis_run.knob_xs` (the CLI's
    grid), coerced as ``/map`` coerces them, and the axis as written."""
    knob = an.resolve(s.knob, builder).knob
    try:
        values = [float(x) for x in ar.knob_xs(s, builder, knob)]
    except SystemExit as e:  # `_knob_range`'s refusal, by name
        raise _Refusal(str(e)) from None
    try:
        values = sweep_values(req, knob, values)
    except ParamSweepError as e:
        raise _Refusal(str(e)) from None
    return {
        "param": knob,
        "values": values,
        "log": s.spacing == "log",
        "lo": min(values),
        "hi": max(values),
        "points": len(values),
        "spacing": s.spacing or "lin",
    }


def _map(a: an.Analysis, builder, req: Mapping, *, hosted: bool) -> dict:
    """A runnable map (map note, unit 1), as the chart draws it. Hosted, it
    carries the instance's map cap and wall-time budget (``limit``), so the
    chart's Run says why before /map refuses it; None on a local workbench,
    which bounds neither."""
    from .cost import MAX_MAP_POINTS, MAX_SWEEP_SECONDS

    sx, sy = a.sweeps
    refs = a.references
    left = [
        f"left out: {_map_gaps(an.Analysis(a.name, a.sweeps, views=(v,)))[0]}"
        for v in a.views
        if not isinstance(v, an.Map)
    ]
    return {
        "runs": True,
        "kind": "map",
        "x": _map_axis(sx, builder, req),
        "y": _map_axis(sy, builder, req),
        "refs": {
            "r": [float(r) for r in refs.r],
            "x": [float(x) for x in refs.x],
            "swr": None if refs.swr is None else float(refs.swr),
        },
        "views": ["Map"],
        "limit": (
            {"points": MAX_MAP_POINTS, "seconds": MAX_SWEEP_SECONDS} if hosted else None
        ),
        **_listed(a),
        "note": "; ".join(left) or None,
    }


def listed(a: an.Analysis, kind: str) -> list[str] | None:
    """The specs ``a`` lists for ``kind`` ("engines" or "grounds"): its cross
    over them, else its one ``engine`` / ``ground``, else None."""
    for c in a.crosses:
        if c.kind == kind:
            return list(getattr(c, kind))
    one = getattr(a, kind[:-1])
    return [one] if one is not None else None


def _listed(a: an.Analysis) -> dict:
    return {"engines": listed(a, "engines"), "grounds": listed(a, "grounds")}


class _Refusal(Exception):
    """What refuses a whole analysis in the workbench, found while serving
    its crosses."""


def _plane_entry(builder, plane: str) -> dict:
    why = ar.plane_refusal(builder, plane)
    if why is None:
        net = builder.build_network()
        if len(net.sources) != 1:
            # The plane selector's seam (`adapter._apply_plane`) moves a
            # single source; a drive of several has no one plane to move.
            why = (
                f"plane {plane!r}: this design drives {len(net.sources)} "
                "sources, and the workbench measures a plane on a single-"
                "source drive only; `antennaknobs analyze` draws it"
            )
    return {"name": plane, "refused": why}


def _knob_run(a: an.Analysis, builder, req: Mapping) -> dict:
    """A knob analysis on ``builder`` as ``/param_sweep`` takes it:
    ``{param, values, log, density}``, or `_Refusal` naming why not."""
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
            raise _Refusal(str(e)) from None
        param = knob
        log = s.spacing == "log"
    try:
        # What /param_sweep would solve: an int knob's values as whole counts.
        values = sweep_values(req, param, values)
    except ParamSweepError as e:
        raise _Refusal(str(e)) from None
    return {"param": param, "values": values, "log": log, "density": density}


def _design_entry(
    a: an.Analysis,
    name: str,
    density: bool,
    state: an.State | None = None,
    variant: str | None = None,
) -> dict:
    """One design cell: ``name`` built at its own defaults (``variant``'s,
    when given), as the CLI's design cell builds it (`analysis_run._prepare`),
    refused by name where the catalog lacks it or the sweep does not resolve
    there. With ``state``, the state's knobs are set over those defaults
    first, refused by name where `analyses.state_refusal` says, so the
    sweep's values and band are the ones ``analyze`` sweeps on that cell."""
    from .examples import UnknownGeometryError, example_for

    out = {
        "name": name,
        "refused": None,
        "param": None,
        "values": None,
        "range": None,
        "freqs": None,
        "reference": False,
        "fixed": False,
    }
    try:
        cls = getattr(example_for(name), "builder_cls", None)
    except UnknownGeometryError as e:
        return {**out, "refused": str(e)}
    if cls is None:
        return {**out, "refused": f"{name!r} has no builder to cross"}
    if variant is not None and not _has_variant(cls, variant):
        # `adapter._variant_params` falls back to the defaults for a name it
        # does not know (a stale page); a state naming one is a spec to fix,
        # refused by name as the CLI's registry refuses it.
        return {**out, "refused": f"{name} has no variant {variant!r}"}
    req = {"geometry": name}
    if variant is not None:
        req["variant"] = variant
    b = builder_for(cls, req)
    reference = state is not None and an.is_reference(state, a)
    out["reference"] = reference
    fixed = reference and not an.is_pattern(a) and _fixed_reference(a, state, b)
    if fixed:
        # A MetricPlot's fixed reference (AK#1828): one solve at its own
        # setting. The chart sweeps it at its one value of the swept knob,
        # which it sets; one whose design lacks the knob has nothing the
        # chart's knob sweep could set, and `analyze` draws it.
        knob = an.resolve(a.sweep.knob, b).knob
        why = an.state_refusal(state, a, b, fixed=True)
        if why is None and (knob is None or knob not in state.settings):
            why = (
                f"the reference {state.label!r} has no {an._knob_name(a.sweep.knob)} "
                "to hold fixed; `antennaknobs analyze` draws it"
            )
        if why:
            return {**out, "refused": why}
        for k, v in state.settings.items():
            setattr(b, k, v)
        try:
            values = sweep_values(req, knob, [float(getattr(b, knob))])
        except ParamSweepError as e:
            return {**out, "refused": str(e)}
        return {**out, "param": knob, "values": values, "fixed": True}
    why = ar.sweep_refusal(a, b, density) or ar.density_moved(a, b)
    if why is None and state is not None:
        why = an.state_refusal(state, a, b)
    if why:
        return {**out, "refused": why}
    if state is not None:
        for k, v in state.settings.items():
            setattr(b, k, v)
    if an.is_pattern(a):
        # One solve at the cell's own frequency: nothing is swept, so the
        # cell is its design (and its state) or its refusal.
        return out
    if _is_frequency(a):
        # The design's own band, as the CLI's design cell sweeps it: the
        # analysis's range, else that design's (`frequency_range`), on the
        # grid `frequency_xs` makes, so each design stays on its band.
        try:
            r = ar.frequency_range(a.sweep, b)
            freqs = [float(f) for f in ar.frequency_xs(a.sweep, b)]
        except (SystemExit, ValueError) as e:
            return {**out, "refused": f"no frequency range on {name}: {e}"}
        if not freqs:
            return {**out, "refused": f"no frequency range on {name}"}
        out.update(range={**r.as_spec(), "level": r.level}, freqs=freqs)
        return out
    try:
        run = _knob_run(a, b, req)
    except _Refusal as e:
        return {**out, "refused": str(e)}
    out.update(param=run["param"], values=run["values"])
    return out


def _fixed_reference(a: an.Analysis, state: an.State, builder) -> bool:
    """Whether a reference state is FIXED on ``builder`` (`analysis_run.
    reference_fixed`'s rule: it sets the swept knob, or its design lacks
    it)."""
    return ar.reference_fixed(ar.Cell(state.label, "", None, state=state), a, builder)


def _metric_view(a: an.Analysis) -> dict | None:
    """The first `MetricPlot` as the chart draws it (AK#1828): the metric's
    name, unit and data (`analyses.to_data`, which ``/param_sweep`` reads
    back), the cell it is relative to, and the unit of a difference."""
    plots = an.metric_plots(a)
    if not plots:
        return None
    v = plots[0]
    m = v.metric
    return {
        "name": m.name,
        "unit": m.unit,
        "relative_to": v.relative_to,
        "relative_unit": "dB" if m.unit == "dBi" else m.unit,
        "spec": an.to_data(m),
    }


def _has_variant(cls, variant: str) -> bool:
    """Whether ``cls`` has ``variant``: "default", or a ``<variant>_params``
    mapping (`cli.list_variants`'s rule)."""
    return variant == "default" or isinstance(
        getattr(cls, f"{variant}_params", None), Mapping
    )


def _frequency_values(raw) -> list[float]:
    """A frequency family's MHz, or `ParamSweepError`: each a finite number
    above zero, as a measurement frequency must be."""
    out = []
    for v in raw:
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise ParamSweepError(f"a frequency is a number (got {v!r})")
        if not (math.isfinite(v) and v > 0):
            raise ParamSweepError(f"a frequency is above zero (got {v!r})")
        out.append(float(v))
    return out


def _step_entry(s: an.Sweep, builder, req: Mapping) -> dict:
    """A family: the knob each cell sets, its values as ``/param_sweep``
    would take them, and each cell's label part. A family over the
    measurement frequency (`an.FREQUENCY`, which resolves to ``freq``;
    AK#1935) is served too: ``/param_sweep`` refuses ``freq`` as a knob
    (a frequency sweep in disguise), but a pattern cell is one solve, and
    the chart sets that cell's measurement frequency, as `analyze` sets
    ``freq`` on the cell's builder."""
    knob = an.resolve(s.knob, builder).knob
    try:
        raw = ar.step_values(s, builder)
        if knob == "freq":
            values = _frequency_values(raw)
        else:
            values = sweep_values(req, knob, [float(v) for v in raw])
    except (SystemExit, ParamSweepError) as e:
        raise _Refusal(f"the family over {knob}: {e}") from None
    return {
        "knob": knob,
        "values": values,
        "labels": [ar.step_label(s, builder, v) for v in raw],
    }


def _state_entry(a: an.Analysis, st: an.State, req: Mapping, density: bool) -> dict:
    """One state (AK#1757 step 7), as the chart sets it (module docstring):
    its name, its design (None: the tab's), its knobs, and its label part;
    then where it is set. A state naming a design, or one on the tab's own
    design, is ONE cell: `_design_entry` on that design at its defaults
    (the tab's variant's, for the tab's design: never its live knobs) with
    the knobs set, so its ``refused``, ``param`` / ``values`` and
    ``range`` / ``freqs`` are that cell's. Beside a designs cross, an
    unnamed state is set on each of those designs: ``on`` holds one such
    entry per design, in the cross's order, and the top-level fields are
    None."""
    head = {
        "name": st.name,
        "design": st.design,
        "variant": st.variant,
        "knobs": st.settings,
        "label": st.label,
        "on": None,
    }
    if st.design is None and an.crosses_designs(a):
        designs = an.named_designs(a)
        return {
            **head,
            "refused": None,
            "param": None,
            "values": None,
            "range": None,
            "freqs": None,
            "reference": an.is_reference(st, a),
            "fixed": False,
            "on": [_design_entry(a, d, density, st) for d in designs],
        }
    if st.design is not None:
        cell = _design_entry(a, st.design, density, st, variant=st.variant)
    else:
        cell = _design_entry(
            a, str(req.get("geometry") or ""), density, st, variant=req.get("variant")
        )
    cell.pop("name")
    return {**head, **cell}


def _cell_entry(
    a: an.Analysis, c: an.Cell, builder, req: Mapping, density: bool
) -> dict:
    """One listed cell (unit 4), as the chart sets it: its label, its state
    (`_state_entry`'s head), engine, ground and plane, and where it is set.
    A cell with a state is that state's cell (its design at its defaults,
    the tab's for an unnamed one); one with none is the tab's design as the
    chart runs it, whose sweep is the chart's own (``param`` and the rest
    None). A plane the cell's design does not offer is its refusal."""
    head = {
        "label": c.label,
        "state": None,
        "engine": c.engine,
        "ground": c.ground,
        "plane": c.plane,
    }
    if c.state is None:
        cell = {
            "refused": None,
            "param": None,
            "values": None,
            "range": None,
            "freqs": None,
            "reference": False,
            "fixed": False,
        }
        on = builder
    else:
        st = _state_entry(a, c.state, req, density)
        head["state"] = {
            k: st[k] for k in ("name", "design", "variant", "knobs", "label")
        }
        cell = {
            k: st[k]
            for k in (
                "refused",
                "param",
                "values",
                "range",
                "freqs",
                "reference",
                "fixed",
            )
        }
        on = None
    if c.plane is not None and cell["refused"] is None:
        if on is None:
            on = _cell_builder(c.state, req)
        if on is not None:
            cell["refused"] = _plane_entry(on, c.plane)["refused"]
    return {**head, **cell}


def _cell_builder(st: an.State, req: Mapping):
    """The builder a state's cell is set on, its knobs set, for its plane."""
    from .examples import UnknownGeometryError, example_for

    name = st.design or str(req.get("geometry") or "")
    try:
        cls = getattr(example_for(name), "builder_cls", None)
    except UnknownGeometryError:
        return None
    if cls is None:
        return None
    sub = {"geometry": name}
    variant = st.variant if st.design is not None else req.get("variant")
    if variant is not None:
        sub["variant"] = variant
    b = builder_for(cls, sub)
    for k, v in st.settings.items():
        setattr(b, k, v)
    return b


def _crosses(a: an.Analysis, builder, req: Mapping, *, density: bool) -> dict:
    """The analysis's crosses over planes, designs, states and a family, as
    the chart multiplies them (module docstring), or `_Refusal`."""
    out = {
        "axes": [c.kind for c in a.crosses],
        "planes": None,
        "designs": None,
        "states": None,
        "cells": None,
        "step": None,
    }
    for c in a.crosses:
        if c.kind == "planes":
            out["planes"] = [_plane_entry(builder, p) for p in c.planes]
        elif c.kind == "designs":
            out["designs"] = [_design_entry(a, d, density) for d in c.designs]
        elif c.kind == "states":
            out["states"] = [_state_entry(a, st, req, density) for st in c.states]
        elif c.kind == "cells":
            out["cells"] = [
                _cell_entry(a, cell, builder, req, density) for cell in c.cells
            ]
        elif c.kind == "step":
            out["step"] = _step_entry(c.step, builder, req)
    return out


def _note(a: an.Analysis, *, deck_density: bool) -> str | None:
    parts = []
    if deck_density:
        parts.append(
            "Z∞ for a deck's own density knob is CLI-only for now: the "
            "workbench draws the ladder as a knob sweep"
        )
    return "; ".join(parts) or None


def _frequency(a: an.Analysis, builder, crosses: dict) -> dict:
    """A runnable frequency analysis as the workbench's frequency sweep."""
    s = a.sweep
    freqs = None
    if s.values is not None:
        # An explicit list: exactly what `analyze` sweeps, in its order; the
        # range spans it, so a chart showing it has ends to edit.
        freqs = [float(f) for f in ar.frequency_xs(s, builder)]
        spec = {
            "lo": min(freqs),
            "hi": max(freqs),
            "spacing": "lin",
            "source": "design",
            "points": len(freqs),
        }
        level = "analysis"
    else:
        r = ar.frequency_range(s, builder)
        absolute = r.level in ("analysis", "file", "design")
        spec = r.as_spec() if absolute else None
        level = r.level
    views = [n for v in a.views if (n := _frequency_view(v))]
    swr = next((v for v in a.views if isinstance(v, an.Swr)), None)
    left = [
        f"left out: {_view_gap(v, 'frequency')}"
        for v in a.views
        if not _frequency_view(v)
    ]
    note = "; ".join(filter(None, [_note(a, deck_density=False), *left])) or None
    return {
        "runs": True,
        "kind": "frequency",
        "range": spec,
        "level": level,
        "points": s.points,
        "freqs": freqs,
        "views": views,
        "swr": {
            "scale": swr.scale if swr is not None else None,
            "threshold": a.references.swr,
        },
        **_listed(a),
        **crosses,
        "note": note,
    }


def _pattern(a: an.Analysis, builder, crosses: dict) -> dict:
    """A runnable pattern (AK#1757 step 7), as the chart draws it."""
    params = an._params(builder)
    freq = params.get("freq") if "freq" in params else None
    user = ar.table_metrics(a)
    # The chart's table is the compare table's; a metric column the table
    # names is `analyze`'s for now (AK#1828), and said so, never dropped
    # without a word.
    note = (
        "left out: the table's metric columns "
        + ", ".join(repr(m.name) for m in user)
        + " (`antennaknobs analyze` prints them)"
        if user
        else None
    )
    return {
        "runs": True,
        "kind": "pattern",
        "views": [d for v in a.views if (d := _pattern_view(v))],
        "freq": float(freq) if isinstance(freq, (int, float)) else None,
        **_listed(a),
        **crosses,
        "note": note,
    }


def _optimize_run(o: an.Optimize, builder, req: Mapping) -> dict:
    """A kept multi-band run (AK#1906) as the workbench jumps to it: its
    start (the knobs it sets over the design's defaults), its knobs and
    ranges, its bands and form, and its stored result. The tab must be on
    the run's variant: a jump sets knobs, never the variant."""
    why = an.problems(o, builder)
    if why:
        return {"runs": False, "why": "; ".join(why)}
    here = req.get("variant") or "default"
    kept = o.start.variant or "default"
    if not str(o.design).startswith("@") and here != kept:
        return {
            "runs": False,
            "why": f"kept on the {kept} variant: switch to it to jump to this run",
        }
    r = o.result
    return {
        "runs": True,
        "kind": "optimize",
        "state": {k: v for k, v in o.start.settings.items()},
        "free": [{"name": k.name, "min": k.min, "max": k.max} for k in o.knobs],
        "bands": [
            {
                "freq": b.freq,
                "objective": b.objective_in("swr"),
                "feed": b.feed,
                "z0": b.z0,
            }
            for b in o.bands
        ],
        "mode": o.mode,
        "mean_weight": o.mean_weight,
        "z0": o.z0,
        "result": None
        if r is None
        else {
            "knobs": dict(r.knobs),
            "bands": [
                {
                    "freq": b.freq,
                    "swr_before": b.swr_before,
                    "swr_after": b.swr_after,
                }
                for b in r.bands
            ],
        },
        "note": None,
    }


def workbench(a: an.Analysis, builder, req: Mapping, *, hosted: bool = False) -> dict:
    """How the workbench runs ``a`` on ``builder`` (built from ``req``).
    ``hosted``: the shared instance, which offers no callable metric but
    the catalog's (`hosted_refusal`). A kept multi-band run is jumped to,
    not drawn (`_optimize_run`)."""
    if an.is_optimize(a):
        return _optimize_run(a, builder, req)
    why = an.problems(a, builder) + gaps(a, builder)
    if hosted and (refusal := hosted_refusal(a)):
        why.append(refusal)
    # A family or map axis on the density knob, refused as the CLI refuses
    # it (the engine holds a non-ladder sweep at its own density).
    moved = ar.density_moved(a, builder)
    if moved:
        why.append(moved)
    if why:
        return {"runs": False, "why": "; ".join(why)}
    if an.is_pattern(a):
        try:
            return _pattern(a, builder, _crosses(a, builder, req, density=False))
        except _Refusal as e:
            return {"runs": False, "why": str(e)}
    if len(a.sweeps) == 2:
        try:
            return _map(a, builder, req, hosted=hosted)
        except _Refusal as e:
            return {"runs": False, "why": str(e)}
    frequency = _is_frequency(a)
    try:
        run = None if frequency else _knob_run(a, builder, req)
        density = run is not None and run["density"]
        crosses = _crosses(a, builder, req, density=density)
        held = _hold_entry(a, builder)
    except _Refusal as e:
        return {"runs": False, "why": str(e)}
    if run is None:
        return _frequency(a, builder, crosses)
    return {
        "runs": True,
        "kind": "knob",
        "param": run["param"],
        "values": run["values"],
        "log": run["log"],
        # A density ladder's metric is not drawn, as `analyze` does not
        # draw it (`analysis_run._DENSITY_METRIC`).
        "views": [
            n
            for v in a.views
            if (n := _knob_view(v)) and not (n == "Metric" and run["density"])
        ],
        "metric": None if run["density"] else _metric_view(a),
        "hold": held,
        **_listed(a),
        **crosses,
        "note": _note(a, deck_density=density and run["param"] != DENSITY)
        or _metric_note(a),
    }


def _metric_note(a: an.Analysis) -> str | None:
    """What the chart leaves out of an analysis's metric plots: it draws the
    first; `analyze` draws every one."""
    plots = an.metric_plots(a)
    if len(plots) < 2:
        return None
    rest = ", ".join(repr(v.metric.name) for v in plots[1:])
    return f"left out: the MetricPlot of {rest} (the chart draws the first; `antennaknobs analyze` draws each)"


def _hold_entry(a: an.Analysis, builder) -> dict | None:
    """A knob analysis's hold as the chart runs it (AK#1757 step 6), or None:
    its objective, its knobs on the tab's design with their bounds (the
    ``ui_params`` min/max, `hold.free_of`), its Z0 (None: the session's),
    warm start, and ``spec``, the hold as data, which the chart sends back
    with each curve's ``/param_sweep`` so the server resolves it on that
    cell's own design. A knob the hold cannot bound is the analysis's
    refusal, by name."""
    if a.hold is None:
        return None
    try:
        free = hd.free_of(a.hold, builder)
    except hd.HoldRefused as e:
        raise _Refusal(str(e)) from None
    return {
        "objective": a.hold.objective,
        "knobs": [f["name"] for f in free],
        "bounds": {f["name"]: [f["min"], f["max"]] for f in free},
        "z0": a.hold.z0,
        "warm_start": a.hold.warm_start,
        "spec": an.to_data(a.hold),
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


def _entry(a: an.Analysis, builder, req: Mapping, hosted: bool) -> dict:
    """One analysis as ``/analyses`` serves it, its callable metrics' functions
    recorded as served (`SERVED_FUNCTIONS`) when this instance may run them."""
    w = workbench(a, builder, req, hosted=hosted)
    if not (hosted and hosted_refusal(a)):
        _serve_functions(a)
    return {
        "name": a.name,
        # The heading it is listed under (AK#1907): None is the library's.
        "group": an.group_of(a),
        "summary": ar.summary(a, builder),
        "code": an.code_with_imports(a),
        "spec": an.to_data(a),
        "problems": an.problems(a, builder),
        "workbench": w,
    }


def offer(builder, req: Mapping, *, hosted: bool = False) -> list[dict]:
    """Every offered analysis on ``builder``, as ``/analyses`` serves it,
    with its ``origin`` (AK#1935): "design" for the design's own, "generic"
    for the library's (`analyses.offered_with_origin`)."""
    # A design's own analysis: not a study (`offer_studies`).
    return [
        {**_entry(a, builder, req, hosted), "study": None, "origin": origin}
        for a, origin in an.offered_with_origin(builder)
    ]


def _same_deck(design: str, deck: str) -> bool:
    """Whether a kept run's ``@path`` design is the opened deck ``@name``:
    the same file name, wherever the run found it."""
    return (
        design.startswith("@")
        and deck.startswith("@")
        and PurePath(design[1:].replace("\\", "/")).name == PurePath(deck[1:]).name
    )


def offer_studies(
    builder, req: Mapping, *, hosted: bool = False, deck: str | None = None
) -> list[dict]:
    """The studies the tab of the design ``req`` names lists, as
    ``/analyses`` serves them (module docstring): the module-level studies
    crossing it, and its own Builder's method studies (this design against
    its references, on this tab only). A user study file not allowed yet is
    never imported, so which designs it crosses is not known: it is not
    served here, and ``analyze --list-studies`` names it. ``deck``: the tab
    is an opened deck, ``@<its file name>``, and a kept band run on a deck
    of that name is listed on it too (AK#1906)."""
    from .. import studies

    geometry = str(req.get("geometry") or "")
    found = studies.pool(geometry, builder)
    listed = studies.including(geometry, found)
    if deck is not None:
        listed += [
            st
            for st in found.studies
            if an.is_optimize(st.analysis)
            and st not in listed
            and _same_deck(st.analysis.design, deck)
        ]
    out = []
    for st in listed:
        a = st.analysis
        out.append(
            {
                **_entry(a, builder, req, hosted),
                "name": st.name,
                "study": {"source": st.source, "name": a.name},
                # Neither the design's own nor generic: a study is listed
                # in its own section (AK#1935).
                "origin": "study",
            }
        )
    return out

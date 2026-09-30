"""What the workbench can run of a design's analyses (AK#1757, steps 3-4).

``POST /analyses`` lists a design's offered analyses (`analyses.offered`),
each with its one-line summary, its Python, its problems, and a
``workbench`` entry saying how the workbench runs it:

- ``{runs: True, kind: "knob", param, values, log, views, note}``: the
  Z-vs-parameter view. ``param`` and ``values`` are exactly what
  ``/param_sweep`` takes. The values come from the same functions
  ``antennaknobs analyze`` sweeps (`analysis_run.knob_xs`,
  `analysis_run.density_rungs`), so a picked analysis and the CLI solve one
  ladder. ``views`` are the ones the chart draws of a knob sweep ("Rx",
  "Smith", "Table"), in the analysis's order;
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
- ``{runs: False, why}``: why the workbench cannot draw it yet, one
  string (reasons joined by "; "), each naming the sweep-framework step it
  is planned for, or the problem `analyses.problems` found.

Both runnable shapes also carry ``engines`` and ``grounds``: the engine
specs and ground specs the analysis lists (its cross over engines or
grounds, else its one ``engine`` / ``ground``), in its order, or None when
it names none. The analysis chart preselects the solver slots and ground
slots that hold them, and names each one no slot holds as a refused cell
(AK#1757 step 5 unit 4); with None it draws the session's active slot and
ground.

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
  cell's sweep served as a design cell's is (`_state_entry`); ``on`` holds
  one design entry per design when an unnamed state multiplies with a
  designs cross;
- ``step``: ``{knob, values, labels}``, a family: the knob each cell sets,
  its values (coerced as ``/param_sweep`` coerces), and each cell's label
  part (`analysis_run.step_label`).

Then the design's STUDIES (`offer_studies`, AK#1757 step 7): analyses over
several designs, from a module-level ``build_studies()`` crossing it, or its
own Builder's ``build_studies()`` method (`studies`). Each is served as a design analysis is, hosted by the tab's
design (the design cross builds each of its designs at its own defaults, as
for any analysis), with its ``name`` the study's full ``source:name`` (unique
beside the design's own analyses, which the picker tells apart by name) and
``study: {source, name}``, the short name the picker shows under its Studies
group (``study`` is None on the design's own analyses). So E7 is on the invvee and the invvee_apex tabs, and on no other.

Framework-free, so it is tested without a server.
"""

from __future__ import annotations

from collections.abc import Mapping

from .. import analyses as an
from .. import analysis_run as ar
from .param_sweep import DENSITY, ParamSweepError, sweep_values

# The sweep-framework step each piece the workbench cannot draw yet is
# planned for (Steve, 2026-09-28): 5 the map; 6 hold. Crosses over planes,
# designs and families draw since step 5 unit 4; the table, R/X against
# frequency and explicit frequencies since unit 5.
_VIEW_STEP = {an.Map: 5, an.Knobs: 6}
# The workbench's frequency-sweep views, by the names /analyses serves.
_FREQUENCY_VIEWS = {
    an.Swr: "Swr",
    an.S11: "S11",
    an.Smith: "Smith",
    an.Rx: "Rx",
    an.Table: "Table",
}
# A knob sweep's: R/X against the knob, its Smith trail, the numbers.
_KNOB_VIEWS = {an.Rx: "Rx", an.Smith: "Smith", an.Table: "Table"}


def _later(what: str, step: int) -> str:
    return f"{what}: not in the workbench yet (sweep-framework step {step})"


def _view_gap(v: an.View, sweep: str) -> str:
    """Why the workbench does not draw view ``v`` of a ``sweep`` sweep."""
    name = f"the {type(v).__name__} view"
    unknown = ar.not_a_view(v)
    if unknown:
        return unknown
    step = next((s for cls, s in _VIEW_STEP.items() if isinstance(v, cls)), None)
    if step is not None:
        return _later(name, step)
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
    return len(a.sweeps) == 1 and a.sweep.knob == an.FREQUENCY


def gaps(a: an.Analysis) -> list[str]:
    """What keeps the workbench from running ``a`` (beyond `an.problems`)."""
    out = []
    if len(a.sweeps) > 1:
        out.append(_later("a two-sweep map", 5))
    if a.hold is not None:
        out.append(_later("hold (optimise at each point)", 6))
    if _is_frequency(a):
        if not any(_frequency_view(v) for v in a.views):
            out += [_view_gap(v, "frequency") for v in a.views]
    # A knob analysis the chart can show none of (only Swr, say) is refused.
    elif not any(_knob_view(v) for v in a.views):
        out += [_view_gap(v, "knob") for v in a.views]
    return out


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
    }
    try:
        cls = getattr(example_for(name), "builder_cls", None)
    except UnknownGeometryError as e:
        return {**out, "refused": str(e)}
    if cls is None:
        return {**out, "refused": f"{name!r} has no builder to cross"}
    req = {"geometry": name}
    if variant is not None:
        req["variant"] = variant
    b = builder_for(cls, req)
    why = ar.sweep_refusal(a, b, density) or ar.density_moved(a, b)
    if why is None and state is not None:
        why = an.state_refusal(state, a, b)
    if why:
        return {**out, "refused": why}
    if state is not None:
        for k, v in state.knobs:
            setattr(b, k, v)
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


def _step_entry(s: an.Sweep, builder, req: Mapping) -> dict:
    """A family: the knob each cell sets, its values as ``/param_sweep``
    would take them, and each cell's label part."""
    knob = an.resolve(s.knob, builder).knob
    try:
        raw = ar.step_values(s, builder)
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
            "on": [_design_entry(a, d, density, st) for d in designs],
        }
    if st.design is not None:
        cell = _design_entry(a, st.design, density, st)
    else:
        cell = _design_entry(
            a, str(req.get("geometry") or ""), density, st, variant=req.get("variant")
        )
    cell.pop("name")
    return {**head, **cell}


def _crosses(a: an.Analysis, builder, req: Mapping, *, density: bool) -> dict:
    """The analysis's crosses over planes, designs, states and a family, as
    the chart multiplies them (module docstring), or `_Refusal`."""
    out = {
        "axes": [c.kind for c in a.crosses],
        "planes": None,
        "designs": None,
        "states": None,
        "step": None,
    }
    for c in a.crosses:
        if c.kind == "planes":
            out["planes"] = [_plane_entry(builder, p) for p in c.planes]
        elif c.kind == "designs":
            out["designs"] = [_design_entry(a, d, density) for d in c.designs]
        elif c.kind == "states":
            out["states"] = [_state_entry(a, st, req, density) for st in c.states]
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


def workbench(a: an.Analysis, builder, req: Mapping) -> dict:
    """How the workbench runs ``a`` on ``builder`` (built from ``req``)."""
    why = an.problems(a, builder) + gaps(a)
    # A family or map axis on the density knob, refused as the CLI refuses
    # it (the engine holds a non-ladder sweep at its own density).
    moved = ar.density_moved(a, builder)
    if moved:
        why.append(moved)
    if why:
        return {"runs": False, "why": "; ".join(why)}
    frequency = _is_frequency(a)
    try:
        run = None if frequency else _knob_run(a, builder, req)
        density = run is not None and run["density"]
        crosses = _crosses(a, builder, req, density=density)
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
        "views": [n for v in a.views if (n := _knob_view(v))],
        **_listed(a),
        **crosses,
        "note": _note(a, deck_density=density and run["param"] != DENSITY),
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
                # A design's own analysis: not a study (`offer_studies`).
                "study": None,
            }
        )
    return out


def offer_studies(builder, req: Mapping) -> list[dict]:
    """The studies the tab of the design ``req`` names lists, as
    ``/analyses`` serves them (module docstring): the module-level studies
    crossing it, and its own Builder's method studies (this design against
    its references, on this tab only). A user study file not allowed yet is
    never imported, so which designs it crosses is not known: it is not
    served here, and ``analyze --list-studies`` names it."""
    from .. import studies

    geometry = str(req.get("geometry") or "")
    out = []
    for st in studies.including(geometry, studies.pool(geometry, builder)):
        a = st.analysis
        out.append(
            {
                "name": st.name,
                "study": {"source": st.source, "name": a.name},
                "summary": ar.summary(a, builder),
                "code": an.to_code(a),
                "problems": an.problems(a, builder),
                "workbench": workbench(a, builder, req),
            }
        )
    return out

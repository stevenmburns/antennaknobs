"""Running an `analyses.Analysis` from the command line (``antennaknobs
analyze``, AK#1757): the sweep framework, CLI first.

Nothing here solves or draws on its own account. A knob sweep solves through
``sweep._solve_at`` and a density sweep through ``sweep._convergence_rows``,
the same functions ``antennaknobs sweep --param`` calls, so an analysis and
the equivalent ``sweep`` command are the same numbers by construction; the
chart is ``sweep._rx_overlay`` and the table ``sweep._print_convergence_table``.

What runs: a sweep over a knob, `analyses.DENSITY`, `analyses.HEIGHT` or
`analyses.FREQUENCY`, or a pair of them (a map); crosses over engines,
grounds, measurement planes, designs, named knob settings (`analyses.State`,
step 7) and a second knob's values (a family), their product one curve (or
one map) per cell; or a list of whole cells (``cells=``, step 7 unit 4), one
curve per listed cell; the `Rx`, `Table`, `Swr`,
`S11`, `Smith` and `Map` views; `Ref` lines on R and X, the SWR threshold,
and the map's contours. A frequency sweep solves through ``sweep.swr_curve``,
the solve behind ``sweep --swr``, over `frequency_range.design_range` when
the spec gives no range: the rule ``sweep --swr`` and the workbench read.
A HOLD (AK#1757 step 6) on a knob sweep runs the workbench's optimizer at
every point of every cell (`hold_cell`, ``antennaknobs.hold``), each cell on
its own builder from its own defaults: a point's Z is the optimum's, a point
the optimizer does not converge at is a gap (NaN on the curve, its reason
printed), and `an.Knobs` draws the held knobs against x.
Everything else is refused by name, with the step it is planned for, when
the analysis is listed and when it is asked to run.

A PATTERN (``sweep=None``, AK#1757 step 7) solves each cell once, at its
builder's measurement frequency (``freq``: the design's own, a state's or a
family's), and reads the far field exactly as ``compare_patterns`` does
(``far_field(n_theta=90, n_phi=360, del_theta=1, del_phi=1)``, NEC's 1-degree
grid): an `an.Elevation` cut is that grid's column at the cut's azimuth and the
one opposite, an `an.Azimuth` cut its row at the cut's elevation, so a cell's
cut IS the design's pattern, sample for sample (`pattern_cut`). The
`an.PatternTable` is `far_field.engine_pattern_metrics`: the workbench compare
table's own function on a momwire cell, read as metrics
(`analyses.TABLE_METRICS` through `metrics.table_values`, AK#1828, the same
numbers bit for bit), then a column per metric the table names.

How a cell is made (`cells`, `_prepare`): each cell is one combination of
the crosses, in the order they are written, and solves on a builder of its
own, so nothing one cell sets reaches the next:

- a design cell builds that design through the caller's ``design_seam``
  (the CLI's registry lookup and engine factory, with that design's own
  file ground and deck flags), and resolves the sweep on it;
- a family cell sets the step knob on its builder before the sweep moves x;
- a state cell sets the state's knobs on its builder, its design's (the
  state's own ``design=``, a design cross's, else the session's) at its
  defaults, refused by name where `analyses.state_refusal` says;
- a plane cell solves the design as a VNA clipped on at that port would see
  it: before each engine is built, the design's network is re-sourced there
  by `plane.driven_at` and shadows ``build_network`` on the builder, the
  workbench's plane selector's own seam (``web.adapter._apply_plane``).

One chart per run: `Rx` is ``sweep._rx_overlay``'s chart, as ``sweep``
draws it; `Swr`, `S11` and `Smith` are panels of one figure beside it
(`_views_figure`), written to ``fn`` when there is no `Rx`, else to
``<stem>-views<suffix>``. A map is its own figure (`_map_figure`), one panel
per cell.

A cross cell that cannot be served (an engine not on this machine's roster
or refusing the design, a plane the design does not offer, a design lacking
the swept knob) is a REFUSED cell: named in the output and in the legend,
while the other cells run.
"""

from __future__ import annotations

import argparse
import dataclasses
import itertools
import math
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from . import analyses as an
from . import frequency_range as fr
from . import hold, sweep_csv
from .sweep_csv import CsvOut

# The sweep-framework step each refused piece is planned for (Steve,
# 2026-09-28). Every view has landed: holds and the Knobs view in step 6.
_VIEW_STEP: dict = {}
_RUNS = (
    an.Rx,
    an.Table,
    an.Swr,
    an.S11,
    an.Smith,
    an.Map,
    an.MetricPlot,
    an.Knobs,
    *an.PATTERN_VIEWS,
)
# The views drawn as panels of one figure (`_views_figure`).
_PANELS = (an.Swr, an.S11, an.Smith)
# The views that draw a curve against one swept value.
_CURVE_VIEWS = (an.Rx, *_PANELS, an.MetricPlot)
# The views that read the feed impedance (a MetricPlot reads the far field).
_Z_VIEWS = (an.Rx, an.Table, *_PANELS)


def _later(what: str, step: int) -> str:
    return f"{what}: not in the CLI yet (sweep-framework step {step})"


def view_step(v: an.View) -> int | None:
    """The step that brings view ``v``, or None when none plans it. By
    isinstance, so a subclass of a planned view is that view."""
    return next((step for cls, step in _VIEW_STEP.items() if isinstance(v, cls)), None)


def not_a_view(v: an.View) -> str | None:
    """Why ``v`` is no view antennaknobs draws or plans (a design's own
    `analyses.View` subclass), or None when it is one."""
    if isinstance(v, (*_RUNS, *_VIEW_STEP)):
        return None
    drawn = ", ".join(f"an.{c.__name__}()" for c in (*_RUNS, *_VIEW_STEP))
    return (
        f"the {type(v).__name__} view: not a view antennaknobs draws "
        f"(the views are {drawn})"
    )


def _misfit(v: an.View, a: an.Analysis) -> str | None:
    """Why view ``v`` does not fit ``a``'s sweep: a map needs a pair of
    sweeps, and a curve view one."""
    name = f"the {type(v).__name__} view"
    pair = len(a.sweeps) == 2
    if isinstance(v, an.Map) and not pair:
        return (
            f"{name}: a map draws a pair of sweeps, an.Analysis(name, (x, y)); "
            "this analysis sweeps one"
        )
    if pair and isinstance(v, _CURVE_VIEWS):
        return (
            f"{name} of a two-sweep map: a map draws Map and Table; cross the "
            "second knob as a family (an.Cross(step=...)) to draw curves"
        )
    if isinstance(v, an.MetricPlot) and any(s.knob == an.DENSITY for s in a.sweeps):
        return _DENSITY_METRIC
    return None


# A metric against the density ladder (its convergence) needs the ladder's
# own solve route, which reads impedance only.
_DENSITY_METRIC = (
    "the MetricPlot view of a density ladder: a metric's convergence is not "
    "in v1 (AK#1828); sweep a knob or the frequency"
)


def _draws(v: an.View, a: an.Analysis) -> bool:
    return isinstance(v, _RUNS) and _misfit(v, a) is None


def _view_why(v: an.View, a: an.Analysis) -> str:
    return (
        not_a_view(v)
        or _misfit(v, a)
        or _later(f"the {type(v).__name__} view", view_step(v))
    )


def _has(a: an.Analysis, cls) -> bool:
    """Whether ``a`` draws a view of ``cls`` (a subclass is that view)."""
    return any(isinstance(v, cls) and _draws(v, a) for v in a.views)


def density_moved(a: an.Analysis, builder) -> str | None:
    """Why ``a`` moves the density knob other than as a ladder, or None. The
    CLI's engines hold every non-density sweep at the engine's own density
    (#1543), so a map axis or a family step on that knob would be undone at
    every solve and draw the same mesh throughout."""
    dens = an.density_knob(builder) if builder is not None else None
    moved = []
    if len(a.sweeps) == 2:
        moved += [s.knob for s in a.sweeps]
    moved += [c.step.knob for c in a.crosses if c.step is not None]
    for k in moved:
        if k == an.DENSITY or (
            dens is not None and an.resolve(k, builder).knob == dens
        ):
            return (
                "a map axis or family over the density knob: not something "
                "`analyze` runs (the engine holds a non-ladder sweep at its own "
                "density); sweep the density (an.convergence) and cross the "
                "other knob as a family"
            )
    return None


def cli_gaps(a: an.Analysis, builder=None) -> list[str]:
    """What refuses ``a`` as a whole in the CLI (on ``builder``, when
    given, which resolves a knob named directly)."""
    out = []
    held = hold.analysis_refusal(a, builder)
    if held:
        out.append(held)
    moved = density_moved(a, builder)
    if moved:
        out.append(moved)
    if not any(_draws(v, a) for v in a.views):
        out += [_view_why(v, a) for v in a.views]
    return out


def skipped_views(a: an.Analysis) -> list[str]:
    """Views left out of a run that draws at least one view."""
    if not any(_draws(v, a) for v in a.views):
        return []
    return [_view_why(v, a) for v in a.views if not _draws(v, a)]


def _fmt(v) -> str:
    return f"{v:g}" if isinstance(v, (int, float)) else str(v)


def _cross_words(c: an.Cross) -> str:
    if c.step is not None:
        knob = c.step.knob.name if isinstance(c.step.knob, an.Role) else c.step.knob
        return f"{c.size} values of {knob}"
    return f"{c.size} {c.kind}"


def summary(a: an.Analysis, builder) -> str:
    """One line: what is swept, over what, into how many curves (a pattern:
    at what frequency, into how many patterns)."""
    parts = []
    for s in a.sweeps:
        r = an.resolve(s.knob, builder)
        what = s.knob.name if isinstance(s.knob, an.Role) else s.knob
        if r.knob is not None and r.knob != what:
            what = f"{what} ({r.knob})"
        if s.values is not None:
            what += f" at {', '.join(_fmt(v) for v in s.values)}"
        elif s.lo is not None:
            what += f" {_fmt(s.lo)}..{_fmt(s.hi)}"
        elif s.knob == an.FREQUENCY and r.knob is not None:
            what += _own_range_words(s, builder)
        if s.points is not None:
            what += f", {s.points} points"
        if s.spacing == "log":
            what += ", log"
        parts.append(what)
    text = " x ".join(parts)
    if an.is_pattern(a):
        text = "pattern" + _pattern_freq_words(builder)
    crosses = " x ".join(_cross_words(c) for c in a.crosses)
    n = a.curves
    unit = "pattern" if an.is_pattern(a) else "map" if len(a.sweeps) == 2 else "curve"
    text += f"; {n} {unit}{'s' if n != 1 else ''}" + (
        f" ({crosses})" if crosses else ""
    )
    if a.hold is not None:
        held = ", ".join(an._knob_name(k) for k in a.hold.adjust)
        text += f"; hold {a.hold.objective} on {held}"
    return text + f"; views {', '.join(type(v).__name__ for v in a.views)}"


def _pattern_freq_words(builder) -> str:
    """Where a pattern is solved: the design's measurement frequency, which a
    state or a family may set on a cell (``freq``, the knob `an.FREQUENCY`
    names)."""
    f = getattr(builder, "freq", None) if "freq" in an._params(builder) else None
    return f" at {_fmt(f)} MHz (freq)" if isinstance(f, (int, float)) else ""


def _own_range_words(s: an.Sweep, builder) -> str:
    """A frequency sweep's own range, for its summary. A band policy's span
    depends on where the tool anchors it (the workbench's band tab), so it is
    named, not given."""
    r = frequency_range(s, builder)
    if r.level not in ("file", "design"):
        return f" ({fr.level_words(r)})"
    words = f" {_fmt(r.lo)}..{_fmt(r.hi)} MHz ({fr.level_words(r)}"
    if s.points is None and (r.step is not None or r.points is not None):
        words += f", {r.count()} points"
    return words + ")"


def list_lines(builder) -> list[str]:
    """``analyze --list``: one line per offered analysis, with every reason
    it cannot run here."""
    offered = an.offered(builder)
    width = max((len(a.name) for a in offered), default=0)
    lines = []
    for a in offered:
        probs = an.problems(a, builder) + cli_gaps(a, builder)
        lines.append(f"{a.name:<{width}}  {summary(a, builder)}")
        for p in probs:
            lines.append(f"{'':<{width}}    {p}")
        if not probs:
            for p in skipped_views(a):
                lines.append(f"{'':<{width}}    (runs without {p})")
    return lines


def study_lines(design: str | None, get_builder: Callable) -> list[str]:
    """``analyze --list-studies``: one line per study (AK#1757 step 7), with
    every reason it cannot run here, as `list_lines` lists a design's; then
    what was found but cannot run (a user file not allowed yet, a study
    refused by name). ``design`` keeps the studies its tab lists: the
    module-level ones crossing it and its Builder's method studies (which
    are listed nowhere else). The summary reads the study on its first
    design, the design ``--study`` runs it on."""
    from . import studies

    if design is None:
        found = studies.discover()
        shown = found.studies
    else:
        # The design's own method studies too, as its tab lists them.
        found = studies.pool(design, get_builder(design)())
        shown = studies.including(design, found)
    # What cannot run is listed under a filter too: a file not allowed yet
    # is never imported, so which designs it crosses is not known, and a
    # study refused for naming none crosses nothing to filter by.
    blocked = found.blocked
    width = max((len(s.name) for s in shown), default=0)
    lines = []
    for s in shown:
        try:
            host = get_builder(s.designs[0])()
        except (SystemExit, ValueError) as e:
            lines.append(f"{s.name:<{width}}  crosses {', '.join(s.designs)}")
            lines.append(f"{'':<{width}}    REFUSED: its first design: {e}")
            continue
        probs = an.problems(s.analysis, host) + cli_gaps(s.analysis, host)
        lines.append(f"{s.name:<{width}}  {summary(s.analysis, host)}")
        lines.append(f"{'':<{width}}    crosses {', '.join(s.designs)}")
        lines += [f"{'':<{width}}    {p}" for p in probs]
        if not probs:
            lines += [
                f"{'':<{width}}    (runs without {p})"
                for p in skipped_views(s.analysis)
            ]
    for b in blocked:
        lines.append(f"{b.label}  (cannot run)")
        lines.append(f"    {b.reason}")
    if not lines:
        where = f" crossing {design}" if design is not None else ""
        lines.append(f"no studies{where}")
    return lines


def find(builder, name: str) -> an.Analysis:
    """The offered analysis called ``name``, or a SystemExit naming them."""
    offered = an.offered(builder)
    for a in offered:
        if a.name == name:
            return a
    names = ", ".join(repr(a.name) for a in offered)
    raise SystemExit(f"no analysis {name!r} on this design; offered: {names}")


@dataclass(frozen=True)
class Cell:
    """One curve (or one map): its label, and what makes it. ``engine`` is
    an engine spec; ``ground`` a ground spec, None the session's; ``plane``
    the port it is measured at, None the design's own; ``design`` a registry
    name, None the analysis's own design; ``step`` a family's ``(knob or
    role, value)``, None when there is no family; ``state`` the `an.State`
    whose knobs the cell sets over its design's defaults, None when the
    analysis crosses no states. A state naming its design makes that design
    the cell's."""

    label: str
    engine: str
    ground: str | None
    plane: str | None = None
    design: str | None = None
    step: tuple[str | an.Role, float] | None = None
    state: an.State | None = None


def step_values(s: an.Sweep, builder) -> list:
    """A family's values: the spec's own, else `knob_xs` on ``builder``."""
    if s.values is not None:
        return list(s.values)
    knob = an.resolve(s.knob, builder).knob
    if knob is None:
        raise SystemExit(an.resolve(s.knob, builder).reason)
    return [x.item() if hasattr(x, "item") else x for x in knob_xs(s, builder, knob)]


def _step_name(s: an.Sweep, builder) -> str:
    """The knob a family's labels name: the resolved knob, as the design
    names it, else the spec's own spelling."""
    if builder is not None:
        knob = an.resolve(s.knob, builder).knob
        if knob is not None:
            return knob
    return an._knob_name(s.knob)


def step_label(s: an.Sweep, builder, value) -> str:
    """A family cell's label part, ``knob = value``: what `cells` names it
    and the workbench's ``/analyses`` serves, so both tools label alike."""
    return f"{_step_name(s, builder)} = {_fmt(value)}"


def cells(a: an.Analysis, session_engine: str, builder=None) -> list[Cell]:
    """The product of ``a``'s crosses, in the order they are written. A
    label names what varies, each part as the spec spells it: the engine,
    the ground, the plane (as the design names its port), the design, and a
    family's ``knob = value``, joined by ", ". ``builder`` (the analysis's
    own design) gives a family's values when the spec gives a range.

    A ``cells=`` cross (AK#1757 step 7, unit 4) is its listed cells instead,
    in order, a union: each cell's own state (its design and variant with
    it), engine, ground and plane, what it leaves out the analysis's, its
    label the cell's own (`analyses.Cell.label`), or its engine's for a cell
    that sets nothing."""
    listed = an.cells_of(a)
    if listed:
        return [_listed_cell(c, a, session_engine) for c in listed]
    axes = []
    for c in a.crosses:
        if c.step is not None:
            axes.append(
                [
                    ("step", (c.step.knob, v), step_label(c.step, builder, v))
                    for v in step_values(c.step, builder)
                ]
            )
        elif c.kind == "states":
            axes.append([("states", st, st.label) for st in c.states])
        else:
            axes.append([(c.kind, v, v) for v in getattr(c, c.kind)])
    out = []
    for combo in itertools.product(*axes):
        chosen = {kind: value for kind, value, _ in combo}
        engine = chosen.get("engines", a.engine or session_engine)
        label = ", ".join(part for _, _, part in combo) if combo else engine
        state = chosen.get("states")
        # A state naming its design is that design's cell (at its variant,
        # the registry's ``name:variant``); `an.problems` refuses one beside
        # a designs cross, so the two never compete.
        design = chosen.get("designs") or (state.spec if state else None)
        out.append(
            Cell(
                label,
                engine,
                chosen.get("grounds", a.ground),
                plane=chosen.get("planes"),
                design=design,
                step=chosen.get("step"),
                state=state,
            )
        )
    return out


def _listed_cell(c: an.Cell, a: an.Analysis, session_engine: str) -> Cell:
    """One cell of a ``cells=`` cross, as `cells` makes a product's."""
    engine = c.engine or a.engine or session_engine
    return Cell(
        c.label or engine,
        engine,
        c.ground or a.ground,
        plane=c.plane,
        design=c.state.spec if c.state is not None else None,
        state=c.state,
    )


def _knob_range(s: an.Sweep, builder, knob: str) -> tuple[float, float]:
    """A knob sweep's lo/hi: the spec's, else the knob's ``ui_params``
    min/max, else the workbench's own ±50 % window around the default."""
    if s.lo is not None:
        return float(s.lo), float(s.hi)
    params = builder._params
    ui = params.get("ui_params") or {}
    meta = ui.get(knob) if hasattr(ui, "get") else None
    if (
        hasattr(meta, "get")
        and meta.get("min") is not None
        and meta.get("max") is not None
    ):
        return float(meta["min"]), float(meta["max"])
    d = float(getattr(builder, knob))
    if d == 0:
        raise SystemExit(
            f"{knob} has no range of its own (no ui_params min/max, default 0); "
            "give the Sweep lo and hi"
        )
    return (d * 0.5, d * 1.5) if d > 0 else (d * 1.5, d * 0.5)


def _sweep_module():
    import importlib

    # The module, not the package's `sweep` function of the same name.
    return importlib.import_module(f"{__package__}.sweep")


def density_rungs(s: an.Sweep):
    """A density sweep's ``(rungs, ladder_rungs, marked, drawn_marks)``, as
    ``sweep._convergence_rungs`` gives them: the app's ladder when the spec
    gives no range, else a geometric one; explicit values are the ladder.
    ``rungs`` is what solves. The workbench's ``/analyses`` reads the same
    rungs, so both tools sweep one ladder."""
    rng = (s.lo, s.hi) if s.lo is not None else None
    return _sweep_module()._convergence_rungs(rng, s.points, s.values or ())


def knob_xs(s: an.Sweep, builder, knob: str) -> np.ndarray:
    """A knob sweep's values on ``builder``: the spec's explicit values, else
    ``gen_xs`` over the spec's or the knob's own range (`_knob_range`),
    ``DEFAULT_POINTS`` when the spec gives no count. The ONE place a knob
    analysis's x values come from: ``analyze`` and the workbench's
    ``/analyses`` both call it."""
    if s.values is not None:
        return np.asarray(s.values)
    return _sweep_module().gen_xs(
        getattr(builder, knob),
        _knob_range(s, builder, knob),
        None,
        None,
        s.points or an.DEFAULT_POINTS,
        log=s.spacing == "log",
    )


def frequency_range(s: an.Sweep, builder) -> fr.FrequencyRange:
    """A frequency sweep's range on ``builder``: the spec's ``lo``/``hi``
    (level "analysis"; linear unless it says "log"), else the design's own
    (`frequency_range.design_range`). The spec's ``points`` or ``spacing``
    replaces the design's density or spacing."""
    if s.lo is not None:
        return fr.FrequencyRange(
            float(s.lo), float(s.hi), "analysis", s.spacing or "lin", points=s.points
        )
    r = fr.design_range(builder._params)
    if s.points is not None:
        r = dataclasses.replace(r, step=None, points=s.points)
    if s.spacing is not None and s.spacing != r.spacing:
        # A lin step means nothing on a log grid: keep its count instead.
        points = r.count() if r.step is not None or r.points is not None else None
        r = dataclasses.replace(r, spacing=s.spacing, step=None, points=points)
    return r


def frequency_xs(s: an.Sweep, builder) -> np.ndarray:
    """A frequency sweep's MHz: the spec's explicit values, else
    `frequency_range`'s grid (`CLI_POINTS` where nothing states a count).
    The ONE place a frequency analysis's points come from in the CLI."""
    if s.values is not None:
        return np.asarray(s.values, dtype=float)
    return frequency_range(s, builder).grid()


def _print_sweep_table(knob, curves, ground_label):
    """The `Table` view of a knob sweep: x, R and X per curve (port 0)."""
    for name, xs, zs in curves:
        print(f"== {knob} sweep: {name} ==")
        print(f"ground: {ground_label[name]}")
        print(f"{knob:>12} {'R (Ω)':>9} {'X (Ω)':>9}")
        for x, z in zip(xs, zs, strict=True):
            print(f"{x:>12.6g} {z.real:>9.3f} {z.imag:>+9.3f}")


def _references(axes, refs: an.Ref) -> None:
    ax_r, ax_x = axes
    for ax, values in ((ax_r, refs.r), (ax_x, refs.x)):
        if ax is None:
            continue
        for v in values:
            ax.axhline(v, color="0.35", linestyle="-.", lw=0.8, alpha=0.8)


# The engine factory for one cell: (engine spec, ground spec or None for the
# session's, density study?) -> factory. It raises argparse.ArgumentTypeError
# for an engine this machine does not have.
FactoryFor = Callable[[str, "str | None", bool], Callable]
# A design cross's seam: registry name -> (builder factory, its FactoryFor,
# its ground label for a ground spec). The CLI's is `cli.get_builder` and the
# engine factory closed over that design (its own file ground, deck flags).
DesignSeam = Callable[[str], "tuple[Callable, FactoryFor, Callable[[str | None], str]]"]


class _Refused(Exception):
    """A cell that cannot be served, and why."""


def at_plane(factory: Callable, plane: str) -> Callable:
    """``factory`` measuring at port ``plane``: each engine it builds solves
    the design re-sourced there by `plane.driven_at`, the upstream chain cut
    away, as the workbench's plane selector solves it
    (``web.adapter._apply_plane``, the same instance shadow). The network is
    re-read from the design at every build, so a knob sweep that moves a
    network value is cut afresh at each point. A plane the design does not
    offer (`plane.planes_of`) is a ValueError naming the ones it does: the
    cell is refused, and the rest run."""
    from .plane import driven_at

    def make(builder):
        # The design's own network, not a shadow an earlier build left.
        builder.__dict__.pop("build_network", None)
        pruned = driven_at(_plane_network(builder, plane), plane)
        # object.__setattr__, not assignment: Builder.__setattr__ files a
        # write into _params, where the class method still wins the lookup,
        # and every plane would quietly solve at the design's own.
        object.__setattr__(builder, "build_network", lambda: pruned)
        return factory(builder)

    return make


def _plane_network(builder, plane: str):
    """``builder``'s network, when it offers port ``plane``; else a
    ValueError naming why not (no network, or the planes it does offer)."""
    from .plane import planes_of

    build = getattr(builder, "build_network", None)
    net = build() if callable(build) else None
    if net is None:
        raise ValueError(
            f"no plane {plane!r}: this design has no network, so no port "
            "to measure at but its own feed"
        )
    planes = planes_of(net)
    if plane not in planes:
        raise ValueError(
            f"no plane {plane!r} on this design; it offers "
            f"{', '.join(planes) or 'none'}"
        )
    return net


def plane_refusal(builder, plane: str) -> str | None:
    """Why a plane cell at ``plane`` is refused on ``builder`` (`at_plane`'s
    words), or None when the design offers it. The workbench's ``/analyses``
    serves it per plane."""
    try:
        _plane_network(builder, plane)
    except ValueError as e:
        return str(e)
    return None


def sweep_refusal(a: an.Analysis, builder, density: bool) -> str | None:
    """Why ``a``'s sweep cannot run on ``builder`` (a design cell's own), or
    None: a knob that does not resolve there, or a knob whose density role
    differs from the analysis's (``density``: the session design's sweep is
    a convergence ladder)."""
    knobs = []
    for s in a.sweeps:
        r = an.resolve(s.knob, builder)
        if r.knob is None:
            return r.reason
        knobs.append(r.knob)
    if len(knobs) == 1 and _is_density(builder, knobs[0]) != density:
        return f"on this design {knobs[0]} " + (
            "is not the density knob, so its sweep is no convergence ladder"
            if density
            else "plays the density role, and the analysis sweeps a knob"
        )
    return None


@dataclass
class _Prepared:
    """A cell ready to solve: its own builder with the family step set, the
    sweep's knob(s) resolved on it, and its engine factory."""

    label: str
    builder: object
    knobs: list[str]
    factory: Callable
    ground_label: str


def _is_density(builder, knob: str) -> bool:
    return knob == "nominal_nsegs" or knob == an.density_knob(builder)


def _prepare(
    cell: Cell,
    a: an.Analysis,
    session: tuple,
    design_seam: DesignSeam | None,
    density: bool,
    fixed: bool = False,
) -> _Prepared:
    """``cell`` on a builder of its own, or `_Refused` naming why not.
    ``fixed``: a `MetricPlot`'s fixed reference (AK#1828), solved once at
    its own setting: the sweep need not resolve on it, its state may set
    what the sweep, the family or the hold moves, and its ``knobs`` are
    empty (nothing is swept on it)."""
    builder_factory, factory_for, label_for = _cell_seam(cell, session, design_seam)
    # A state cell's builder is its design at its DEFAULTS, the state's
    # knobs set over them (AK#1757 step 7): the factory is the registry's
    # (`analyze` takes no --set), so a state names the same curve wherever
    # it runs. The workbench builds it the same way, from the tab's variant
    # defaults and never its live knobs.
    b = builder_factory()
    why = None if fixed else sweep_refusal(a, b, density)
    if why:
        raise _Refused(why)
    if cell.state is not None:
        why = an.state_refusal(cell.state, a, b, fixed=fixed)
        if why:
            raise _Refused(why)
        # The refusals keep a state off every knob the sweep, the family and
        # the hold move, so the order they are set in cannot matter. A group
        # knob is set as plain data, the shape its default is written in.
        for k, v in cell.state.settings.items():
            setattr(b, k, v)
    knobs = [] if fixed else [an.resolve(s.knob, b).knob for s in a.sweeps]
    moved = density_moved(a, b) if cell.design is not None else None
    if moved:
        raise _Refused(moved)
    if cell.step is not None:
        target, value = cell.step
        r = an.resolve(target, b)
        if r.knob is None:
            raise _Refused(r.reason)
        if r.knob in knobs:
            raise _Refused(f"the family steps {r.knob}, the swept knob on this design")
        setattr(b, r.knob, value)
    try:
        factory = factory_for(cell.engine, cell.ground, density)
    except argparse.ArgumentTypeError as e:
        raise _Refused(str(e)) from None
    if cell.plane is not None:
        factory = at_plane(factory, cell.plane)
    return _Prepared(cell.label, b, knobs, factory, label_for(cell.ground))


def _cell_seam(cell: Cell, session: tuple, design_seam: DesignSeam | None) -> tuple:
    """The (builder factory, engine factory, ground label) ``cell`` is made
    with: the session's, or its design's through ``design_seam``; a design
    the registry lacks is `_Refused` by name."""
    if cell.design is None:
        return session
    if design_seam is None:
        raise TypeError("a cross over designs needs run(design_seam=...)")
    try:
        return design_seam(cell.design)
    except (SystemExit, ValueError) as e:
        # The registry's "unknown builder" is a SystemExit: here it is one
        # cell's reason, not the run's.
        raise _Refused(str(e)) from None


def reference_fixed(cell: Cell, a: an.Analysis, builder) -> bool:
    """Whether a `MetricPlot` reference ``cell`` (AK#1828), on ``builder``
    (its design at its defaults), is FIXED: its sweep does not resolve there
    (its design has no such knob), or its state sets the knob the sweep
    moves. Then it is solved once, at its own setting, and drawn flat."""
    for s in a.sweeps:
        knob = an.resolve(s.knob, builder).knob
        if knob is None:
            return True
        if cell.state is not None and knob in cell.state.settings:
            return True
    return False


def references(a: an.Analysis, plot: an.MetricPlot, cells_: list[Cell]) -> dict:
    """``{label: reference label}`` for ``plot``'s ``relative_to``: each
    cell's reference is the cell it names (`analyses.reference_matches`),
    the one that matches it on engine, ground, plane and family step when it
    names several (one per engine, say). A cell with none maps to None."""
    if plot.relative_to is None:
        return {c.label: None for c in cells_}
    named = [
        c
        for c in cells_
        if an.reference_matches(
            plot.relative_to, state=c.state, design=c.design, label=c.label
        )
    ]
    out = {}
    for c in cells_:
        if len(named) == 1:
            out[c.label] = named[0].label
            continue
        same = [
            r
            for r in named
            if (r.engine, r.ground, r.plane, r.step)
            == (c.engine, c.ground, c.plane, c.step)
        ]
        out[c.label] = same[0].label if len(same) == 1 else None
    return out


def _xs(s: an.Sweep, builder, knob: str) -> np.ndarray:
    return (
        frequency_xs(s, builder)
        if s.knob == an.FREQUENCY
        else knob_xs(s, builder, knob)
    )


def _solve_line(builder, s: an.Sweep, knob: str, xs, factory, z0) -> np.ndarray:
    """Z at every port, (points, ports), along one knob or frequency sweep:
    ``sweep.swr_curve`` for frequency (one build, the engine's vectorized
    sweep), ``sweep._solve_at`` for a knob (a build per point)."""
    sw = _sweep_module()
    if s.knob == an.FREQUENCY:
        zs, _swr = sw.swr_curve(builder, "freq", xs, factory, z0)
        return np.asarray(zs)
    return np.array(sw._solve_at(builder, knob, xs, factory))


def solve_map(p: _Prepared, a: an.Analysis, z0: float):
    """One map cell: ``(xs, ys, Z)``, Z shaped (len(ys), len(xs)) at port 0.
    Each row sets y on the cell's builder and runs x's own line solve, so a
    map row IS the one-sweep analysis of x at that y."""
    sx, sy = a.sweeps
    kx, ky = p.knobs
    xs = _xs(sx, p.builder, kx)
    ys = _xs(sy, p.builder, ky)
    rows = []
    for y in ys:
        setattr(p.builder, ky, y.item() if hasattr(y, "item") else y)
        rows.append(_solve_line(p.builder, sx, kx, xs, p.factory, z0)[:, 0])
    return xs, ys, np.array(rows)


def run(
    a: an.Analysis,
    builder_factory: Callable,
    *,
    factory_for: FactoryFor,
    ground_label_for: Callable[[str | None], str],
    session_engine: str,
    z0: float = 50.0,
    fn: str | None = None,
    design_seam: DesignSeam | None = None,
    csv: CsvOut | None = None,
) -> dict:
    """Run ``a`` on the design ``builder_factory`` makes. Returns what was
    computed, ``{"curves": {label: (xs, zs)}, "refused": {label: reason},
    "estimates": {label: ZInfEstimate}}`` (estimates on a density sweep
    only; a map's cells are ``"maps": {label: (xs, ys, Z)}`` instead of
    curves), for the tests; the table goes to stdout and the chart to
    ``fn``. ``design_seam`` builds a design cross's other designs. ``csv``
    writes the sweep's numbers (``sweep_csv``): a frequency sweep's R, X and
    SWR per curve, a knob sweep's R and X, a density study's table columns;
    a two-sweep map has no such form and refuses."""
    import matplotlib.pyplot as plt

    from .core import save_or_show

    sw = _sweep_module()

    builder = builder_factory()
    probs = an.problems(a, builder) + cli_gaps(a, builder)
    if probs:
        raise SystemExit(f"analysis {a.name!r}: " + "; ".join(probs))
    if an.is_pattern(a):
        return _run_patterns(
            a,
            builder,
            session=(builder_factory, factory_for, ground_label_for),
            session_engine=session_engine,
            design_seam=design_seam,
            fn=fn,
            csv=csv,
        )
    knob = an.resolve(a.sweeps[0].knob, builder).knob
    is_map = len(a.sweeps) == 2
    if csv is not None and is_map:
        raise SystemExit(
            f"analysis {a.name!r}: --csv writes one row per swept point; a "
            "two-sweep map is a grid, not a table of points"
        )
    density = not is_map and _is_density(builder, knob)
    print(f"analysis {a.name!r}: {summary(a, builder)}")
    for p in skipped_views(a):
        print(f"  runs without {p}")

    refused: dict[str, str] = {}
    prepared: list[_Prepared] = []
    session = (builder_factory, factory_for, ground_label_for)
    all_cells = cells(a, session_engine, builder)
    for cell in all_cells:
        try:
            prepared.append(_prepare(cell, a, session, design_seam, density))
        except _Refused as e:
            refused[cell.label] = str(e)
    ground_label = {p.label: p.ground_label for p in prepared}

    out: dict = {"curves": {}, "refused": refused}
    if is_map:
        return _run_map(a, prepared, refused, out, builder, z0=z0, fn=fn)

    plots = [v for v in a.views if isinstance(v, an.MetricPlot) and _draws(v, a)]
    if plots and density:
        print(f"  runs without {_DENSITY_METRIC}")
        plots = []
    metric_cols: dict[str, list] = {}
    if plots:
        out["metrics"], metric_cols = _run_metric_plots(
            a,
            plots,
            all_cells,
            prepared,
            refused,
            session=session,
            design_seam=design_seam,
            builder=builder,
        )
        if not any(_has(a, cls) for cls in _Z_VIEWS):
            # A metric plot alone reads no impedance: nothing else solves.
            if csv is not None:
                knob_name = "MHz" if a.sweep.knob == an.FREQUENCY else knob
                csv.write(
                    knob_name,
                    [(label, xs, cols) for label, (xs, cols) in metric_cols.items()],
                )
            _report_refused(refused)
            _metric_figure(a, plots, out["metrics"], builder, knob, list(refused))
            save_or_show(plt, fn)
            return out

    s = a.sweep
    frequency = s.knob == an.FREQUENCY
    planes = any(c.kind == "planes" for c in a.crosses)
    # One (label, xs, Z at port 0) per curve that solved: what the Swr, S11
    # and Smith panels draw, whatever was swept.
    curves = []
    # A held analysis's points per curve (step 6): the knobs and verdicts.
    held: dict[str, list[hold.HeldPoint]] = {}
    if a.hold is not None:
        out["held"] = held
    nports = 1
    # A refusal is the engine declining the design (NEC-2 and a vertex feed),
    # which every engine raises as ValueError / NotImplementedError, or a
    # plane the design does not offer (`at_plane`); any other failure is a
    # real error and propagates.
    if density:
        rungs, ladder, _marked, drawn = density_rungs(s)
        per, fed = {}, {}
        for p in prepared:
            try:
                rows, lens, n = sw._convergence_rows(
                    p.builder, p.factory, rungs, p.knobs[0]
                )
            except (ValueError, NotImplementedError) as e:
                refused[p.label] = str(e)
                continue
            per[p.label], fed[p.label] = rows, lens
            nports = max(nports, n)
            out["curves"][p.label] = ([r[0] for r in rows], [r[2] for r in rows])
            curves.append((p.label, [r[1] for r in rows], [r[2] for r in rows]))
        if not per:
            _report_refused(refused)
            raise SystemExit(f"analysis {a.name!r}: every curve was refused")
        estimates, reasons = sw._convergence_estimates(per, fed, ladder)
        out["estimates"] = estimates
        if csv is not None:
            csv.write(
                "nominal_N" if knob == "nominal_nsegs" else knob,
                [sweep_csv.density_curve(n, r, z0) for n, r in per.items()],
            )
        if _has(a, an.Table):
            sw._print_convergence_table(
                per,
                estimates,
                z0,
                ground_label={k: ground_label[k] for k in per},
                reasons=reasons,
                knob=knob,
            )
        _report_refused(refused)
        xlabel, log, title = (
            "segments achieved (log)",
            True,
            sw._convergence_title(knob, nports),
        )
        if _has(a, an.Rx):
            axes = sw._rx_overlay(
                sw._convergence_panels(per, estimates, drawn),
                xlabel=xlabel,
                title=title,
                log_x=True,
                xname="N",
                refused=list(refused),
            )
            _references(axes, a.references)
    else:
        log = s.spacing == "log"
        if frequency:
            session_xs = frequency_xs(s, builder)
            print(f"  {_grid_words(s, builder, session_xs)}")
        for p in prepared:
            xs = _xs(s, p.builder, p.knobs[0])
            if frequency and not np.array_equal(xs, session_xs):
                print(f"  {p.label}: {_grid_words(s, p.builder, xs)}")
            try:
                if a.hold is not None:
                    # A held line (step 6): the optimizer at every point,
                    # each point's Z at its optimised knobs, a gap a NaN.
                    pts = hold_cell(p, a, xs, z0)
                    held[p.label] = pts
                    zs = np.array(
                        [
                            [pt.z if pt.converged else complex(np.nan, np.nan)]
                            for pt in pts
                        ]
                    )
                else:
                    zs = _solve_line(p.builder, s, p.knobs[0], xs, p.factory, z0)
            except (ValueError, NotImplementedError) as e:
                # HoldRefused is a ValueError: a cell the hold cannot serve
                # (a knob with no range there, a multi-feed design).
                refused[p.label] = str(e)
                continue
            nports = max(nports, zs.shape[1])
            curves.append((p.label, xs, zs[:, 0]))
            out["curves"][p.label] = (list(xs), list(zs[:, 0]))
        if not curves:
            _report_refused(refused)
            raise SystemExit(f"analysis {a.name!r}: every curve was refused")
        if csv is not None:
            csv.write(
                "MHz" if frequency else knob,
                [
                    held_csv_curve(name, held[name])
                    if name in held
                    else sweep_csv.impedance_curve(
                        name, x, z, swr_of(z, z0) if frequency else None
                    )
                    for name, x, z in curves
                ]
                # A MetricPlot's columns, a curve per cell beside them
                # (AK#1828): their own x, which `sweep_csv.table` aligns.
                + [(label, xs, cols) for label, (xs, cols) in metric_cols.items()],
            )
        if _has(a, an.Table):
            if frequency:
                _print_frequency_table(curves, ground_label, z0)
            elif held:
                _print_held_table(knob, held, ground_label)
            else:
                _print_sweep_table(knob, curves, ground_label)
        for label, pts in held.items():
            for line in held_lines(label, knob, pts, a.hold):
                print(line)
        _report_refused(refused)
        xlabel = sw._param_label(knob)
        # Planes crossed: no one port is "the" plane the title could name.
        title = (
            f"impedance per measurement plane vs {knob}"
            if planes
            else sw._z_title(builder, knob)
        )
        if nports > 1:
            title += f" (port 1 of {nports})"
        if _has(a, an.Rx):
            axes = sw._rx_overlay(
                [(name, x, z, [], None) for name, x, z in curves],
                xlabel=xlabel,
                title=title,
                log_x=log,
                xname=knob,
                refused=list(refused),
            )
            _references(axes, a.references)
    threshold = a.references.swr
    if frequency and threshold is not None:
        out["bandwidth"] = {}
        for label, x, z in curves:
            bands = swr_bands(x, swr_of(z, z0), threshold)
            out["bandwidth"][label] = bands
            print(
                bandwidth_line(label, x, swr_of(z, z0), bands, threshold, builder.freq)
            )
    if _has(a, an.Rx):
        save_or_show(plt, fn)
    panels = [v for v in a.views if isinstance(v, _PANELS) and _draws(v, a)]
    if panels:
        _views_figure(
            curves,
            panels,
            xlabel=xlabel,
            log_x=log,
            title=title,
            z0=z0,
            threshold=threshold,
            refused=list(refused),
        )
        save_or_show(plt, _views_fn(fn) if _has(a, an.Rx) else fn)
    if plots:
        _metric_figure(a, plots, out["metrics"], builder, knob, list(refused))
        save_or_show(plt, _views_fn(fn, "-metrics"))
    if a.hold is not None and _has(a, an.Knobs) and not density:
        _knobs_figure(held, xlabel=xlabel, log_x=log, a=a, refused=list(refused))
        first = _has(a, an.Rx) or bool(panels) or bool(plots)
        save_or_show(plt, _views_fn(fn, "-knobs") if first else fn)
    return out


# ── holds (AK#1757 step 6) ───────────────────────────────────────────────


def hold_cell(p: _Prepared, a: an.Analysis, xs, z0: float) -> list[hold.HeldPoint]:
    """One cell's held line: the hold's knobs on the cell's own builder,
    bounded by their ``ui_params`` (`hold.free_of`), starting from that
    builder's values (its design's defaults, a state's or family's settings
    over them), each point solved through the cell's engine factory at the
    hold's Z0 (the session's when it names none). `hold.HoldRefused` names a
    cell the hold cannot serve."""
    free = hold.free_of(a.hold, p.builder)
    z0h = a.hold.z0 if a.hold.z0 is not None else z0
    return hold.hold_line(
        [float(x) for x in xs],
        p.knobs[0],
        free,
        a.hold.objective,
        solve_fn=hold.builder_solve_fn(p.builder, p.factory, z0h),
        defaults=hold.defaults_of(p.builder, free),
        warm_start=a.hold.warm_start,
    )


def held_lines(label: str, knob: str, pts, h: an.Hold) -> list[str]:
    """What a held curve says beside its numbers: one summary line, then
    every gap with its reason, and where the recovery cold-started."""
    gaps = [pt for pt in pts if not pt.converged]
    names = ", ".join(an._knob_name(k) for k in h.adjust)
    solves = sum(pt.n_solves for pt in pts)
    resid = [pt.residual for pt in pts if pt.converged and pt.residual is not None]
    worst = f", worst residual {max(resid):.3g} ohm" if resid else ""
    lines = [
        f"{label}: held {h.objective} on {names}: {len(pts) - len(gaps)} of "
        f"{len(pts)} points held, {len(gaps)} gap{'s' if len(gaps) != 1 else ''}, "
        f"{solves} solves{worst}"
    ]
    for i, pt in enumerate(pts):
        restart = pt.cold and i > 0 and h.warm_start
        if not pt.converged:
            lines.append(f"  gap at {knob} = {_fmt(pt.x)}: {pt.reason}")
        if restart:
            lines.append(
                f"  {knob} = {_fmt(pt.x)}: cold start from the defaults "
                f"({'held' if pt.converged else 'given up'})"
            )
    return lines


def _print_held_table(knob, held, ground_label):
    """The `Table` view of a held sweep: x, R, X and the held knobs per
    curve, a gap's row its reason."""
    for name, pts in held.items():
        print(f"== {knob} sweep, held: {name} ==")
        print(f"ground: {ground_label[name]}")
        names = list(pts[0].params) if pts else []
        head = f"{knob:>12} {'R (Ω)':>9} {'X (Ω)':>9}"
        print(head + "".join(f" {n:>14}" for n in names))
        for pt in pts:
            if not pt.converged:
                print(f"{pt.x:>12.6g}  gap: {pt.reason}")
                continue
            z = pt.z
            row = f"{pt.x:>12.6g} {z.real:>9.3f} {z.imag:>+9.3f}"
            print(row + "".join(f" {pt.params[n]:>14.6g}" for n in names))


def held_csv_curve(label, pts) -> sweep_csv.Curve:
    """A held curve's CSV columns: R and X, then each held knob, a gap's
    cells left empty (never a value the hold did not reach)."""
    names = list(pts[0].params) if pts else []

    def col(f):
        return [f(pt) if pt.converged else None for pt in pts]

    cols = [("R_ohm", col(lambda pt: pt.z.real)), ("X_ohm", col(lambda pt: pt.z.imag))]
    cols += [(n, col(lambda pt, n=n: pt.params[n])) for n in names]
    return label, [pt.x for pt in pts], cols


def _knobs_figure(held, *, xlabel, log_x, a: an.Analysis, refused) -> None:
    """The `Knobs` view: each held knob against x, one panel per knob, one
    line per curve; a gap breaks the line and is marked on the x axis."""
    import matplotlib.pyplot as plt

    names = []
    for pts in held.values():
        for n in pts[0].params if pts else ():
            if n not in names:
                names.append(n)
    rows = max(1, len(names))
    fig, axes = plt.subplots(rows, 1, figsize=(9.0, 2.8 + 2.4 * rows), sharex=True)
    axes = list(np.atleast_1d(axes))
    for ax, n in zip(axes, names, strict=False):
        for i, (label, pts) in enumerate(held.items()):
            xs = [pt.x for pt in pts]
            ys = [pt.params[n] if pt.converged else np.nan for pt in pts]
            color = f"C{i % 10}"
            ax.plot(xs, ys, color=color, marker="o", ms=3, lw=1.3, label=label)
            gx = [pt.x for pt in pts if not pt.converged]
            if gx:
                ax.plot(
                    gx,
                    [0.03] * len(gx),
                    linestyle="None",
                    marker="x",
                    color=color,
                    transform=ax.get_xaxis_transform(),
                    label=f"{label}: gap",
                )
        ax.set_ylabel(n)
        ax.yaxis.get_major_formatter().set_useOffset(False)
        ax.grid(True, alpha=0.3)
    if log_x:
        axes[-1].set_xscale("log")
    axes[-1].set_xlabel(xlabel)
    for name in refused:
        axes[0].plot(
            [], [], linestyle="None", marker="x", color="0.5", label=f"{name}: refused"
        )
    axes[0].legend(fontsize=7, frameon=False)
    axes[0].set_title(f"{a.name}: the knobs that hold {a.hold.objective}", fontsize=10)
    fig.tight_layout()


# ── patterns (AK#1757 step 7) ────────────────────────────────────────────

# The far-field grid every cell is read on: `far_field.compare_patterns`'s,
# which every engine returns (theta 0..89 from the zenith, phi 0..360 with the
# seam duplicated, 1-degree steps).
PATTERN_GRID = {"n_theta": 90, "n_phi": 360, "del_theta": 1, "del_phi": 1}


@dataclass(frozen=True)
class PatternCell:
    """One solved pattern cell: its measurement frequency, the engine's
    `FarField` on `PATTERN_GRID`, its metrics (the pattern table's,
    `analyses.TABLE_METRICS`, keyed as ``engine_pattern_metrics`` keys
    them), its ground's label, and the user's metrics (AK#1828: every
    `PatternTable`'s ``metrics``, by name)."""

    freq: float
    ff: object
    metrics: dict
    ground_label: str
    values: dict = dataclasses.field(default_factory=dict)


def cut_name(v: an.View) -> str:
    """A cut view's name, as the CSV's ``cut`` column and the figure say it."""
    if isinstance(v, an.Elevation):
        return f"elevation az={_fmt(v.az)}"
    return f"azimuth el={_fmt(v.el)}"


def _grid_index(axis, deg: float, what: str) -> int:
    hit = np.flatnonzero(np.isclose(np.asarray(axis, float), deg, atol=1e-9))
    if hit.size == 0:
        raise ValueError(f"the far-field grid has no {what} = {deg:g} degrees")
    return int(hit[0])


def pattern_cut(ff, v: an.View) -> tuple[np.ndarray, np.ndarray]:
    """``(angles, dBi)``: cut ``v`` read off the grid ``ff``, sample for
    sample, never interpolated.

    - `an.Elevation`: angle is the elevation from the cut's horizon (its
      azimuth ``az``) up over the zenith (90) to the opposite horizon
      (``az`` + 180), 1..179: the column at ``az`` for 1..90 and the one
      opposite for 91..179, as ``far_field.plot_patterns`` draws it (less
      its second copy of the zenith, one direction sampled twice);
    - `an.Azimuth`: angle is the azimuth 0..359 of the row at the cut's
      elevation (less the grid's duplicated 360 seam)."""
    rings = np.asarray(ff.rings, float)
    thetas = np.asarray(ff.thetas, float)
    phis = np.asarray(ff.phis, float)
    if isinstance(v, an.Elevation):
        front = _grid_index(phis, v.az % 360, "azimuth")
        back = _grid_index(phis, (v.az + 180) % 360, "azimuth")
        up = rings[::-1, front]  # theta 89..0: elevation 1..90
        down = rings[1:, back]  # theta 1..89: elevation 91..179
        angles = np.concatenate([90.0 - thetas[::-1], 90.0 + thetas[1:]])
        return angles, np.concatenate([up, down])
    row = _grid_index(thetas, 90.0 - v.el, "elevation")
    seam = len(phis) - 1 if np.isclose(phis[-1] - phis[0], 360.0) else len(phis)
    return phis[:seam].copy(), rings[row, :seam].copy()


def _cut_views(a: an.Analysis) -> list[an.View]:
    return [v for v in a.views if isinstance(v, (an.Elevation, an.Azimuth))]


def table_metrics(a: an.Analysis) -> tuple[an.PatternMetric, ...]:
    """The user's metrics every `PatternTable` of ``a`` asks for, each once,
    in order (AK#1828): the table's columns after its fixed ones."""
    out: list[an.PatternMetric] = []
    for v in a.views:
        if isinstance(v, an.PatternTable):
            out += [m for m in v.metrics if m not in out]
    return tuple(out)


def _run_patterns(
    a: an.Analysis,
    builder,
    *,
    session: tuple,
    session_engine: str,
    design_seam: DesignSeam | None,
    fn: str | None,
    csv: CsvOut | None,
) -> dict:
    """A pattern analysis: each cell solved once on its own builder and
    engine (`_prepare`, as every analysis's cell), its far field read on
    `PATTERN_GRID`, the cuts drawn one panel per cut view with a trace per
    cell, the metrics table printed. Returns ``{"patterns": {label:
    PatternCell}, "cuts": {label: {cut name: (angles, dBi)}}, "refused":
    {label: reason}}``."""
    from . import metrics as mx

    cut_views = _cut_views(a)
    user = table_metrics(a)
    print(f"analysis {a.name!r}: {summary(a, builder)}")
    refused: dict[str, str] = {}
    prepared: list[_Prepared] = []
    for cell in cells(a, session_engine, builder):
        try:
            prepared.append(_prepare(cell, a, session, design_seam, False))
        except _Refused as e:
            refused[cell.label] = str(e)
    solved: dict[str, PatternCell] = {}
    for p in prepared:
        # As for a curve: an engine declining the design is a refused cell,
        # any other failure a real error that propagates.
        try:
            eng = p.factory(p.builder)
            ff = eng.far_field(**PATTERN_GRID)
            # The table's columns are metrics (AK#1828): one path, the same
            # numbers as `far_field.engine_pattern_metrics` (pinned).
            src = mx.source_for(eng, ff)
            metrics = mx.table_values(src)
            values = mx.values(user, src)
        except (ValueError, NotImplementedError) as e:
            # A MetricError is a ValueError: a metric this engine cannot
            # read refuses its cell by name, as an engine declining does.
            refused[p.label] = str(e)
            continue
        solved[p.label] = PatternCell(
            float(p.builder.freq), ff, metrics, p.ground_label, values
        )
    if not solved:
        _report_refused(refused)
        raise SystemExit(f"analysis {a.name!r}: every pattern was refused")
    cuts = {
        label: {cut_name(v): pattern_cut(c.ff, v) for v in cut_views}
        for label, c in solved.items()
    }
    for label, c in solved.items():
        print(f"  {label}: {_fmt(c.freq)} MHz, ground: {c.ground_label}")
    if _has(a, an.PatternTable):
        from .far_field import _print_metrics_table

        _print_metrics_table(
            list(solved),
            [c.metrics for c in solved.values()],
            extra=[
                (mx.column_heading(m), [c.values[m.name] for c in solved.values()])
                for m in user
            ],
        )
    _report_refused(refused)
    if csv is not None:
        if cut_views:
            csv.write_rows(
                *sweep_csv.pattern_table(cuts, [cut_name(v) for v in cut_views])
            )
            if user:
                print(
                    "  --csv writes the cuts; the table's metric columns are in "
                    "the printed table (a pattern of only an.PatternTable writes "
                    "the table)"
                )
        else:
            csv.write_rows(
                *sweep_csv.metrics_table(
                    {label: c.metrics for label, c in solved.items()},
                    [(mx.column_heading(m), m.name) for m in user],
                    {label: c.values for label, c in solved.items()},
                )
            )
    if cut_views:
        import matplotlib.pyplot as plt

        from .core import save_or_show

        _pattern_figure(a, cut_views, cuts, list(refused))
        save_or_show(plt, fn)
    return {"patterns": solved, "cuts": cuts, "refused": refused}


def _pattern_figure(a: an.Analysis, cut_views, cuts, refused) -> None:
    """One polar panel per cut view, in the analysis's order, a trace per
    cell in one colour across every panel, and one legend below them:
    ``far_field.plot_patterns``' dBi axes (its fixed floor and rings), so a
    pattern analysis reads as ``compare_patterns`` does."""
    import matplotlib.pyplot as plt

    from .far_field import _finalise_dbi_polar, _init_dbi_polar

    n = len(cut_views)
    # An elevation cut is a half-disc: a figure of elevation cuts alone is
    # about half as tall as one holding a full azimuth circle.
    tall = any(isinstance(v, an.Azimuth) for v in cut_views)
    fig, axes = plt.subplots(
        ncols=n,
        subplot_kw={"projection": "polar"},
        figsize=(6 * n, 6.5 if tall else 4.4),
        squeeze=False,
    )
    for ax, v in zip(axes[0], cut_views, strict=True):
        _init_dbi_polar(ax)
        name = cut_name(v)
        for i, (label, per) in enumerate(cuts.items()):
            angles, dbi = per[name]
            if isinstance(v, an.Azimuth):
                # Closed round the circle, as the grid's own ring is.
                angles = np.append(angles, angles[0] + 360.0)
                dbi = np.append(dbi, dbi[0])
            ax.plot(np.deg2rad(angles), dbi, color=f"C{i}", label=label)
        if isinstance(v, an.Elevation):
            # The classic half-disc: the cut's horizon (0) over the zenith
            # to the opposite horizon (180).
            ax.set_thetamin(0)
            ax.set_thetamax(180)
            title = f"elevation cut, az {_fmt(v.az)}°→{_fmt((v.az + 180) % 360)}° (dBi)"
        else:
            title = f"azimuth cut @ {_fmt(v.el)}° elevation (dBi)"
        _finalise_dbi_polar(ax, title=title)
    handles, labels = axes[0][0].get_legend_handles_labels()
    for r in refused:
        (h,) = axes[0][0].plot([], [], linestyle="None", marker="x", color="0.5")
        handles.append(h)
        labels.append(f"{r}: refused")
    fig.legend(
        handles,
        labels,
        loc="lower center",
        ncol=min(len(labels), 3),
        frameon=False,
        fontsize=9,
    )
    fig.suptitle(a.name, fontsize=11)
    # Room below the panels for the legend's rows (inches, then a fraction).
    rows = math.ceil(len(labels) / 3)
    fig.subplots_adjust(bottom=(0.45 + 0.3 * rows) / fig.get_figheight())


# ── the map ──────────────────────────────────────────────────────────────


def _run_map(a, prepared, refused, out, builder, *, z0, fn) -> dict:
    """A two-sweep analysis: one grid per cell (`solve_map`), its table, the
    best cell's line, and the map figure."""
    import matplotlib.pyplot as plt

    from .core import save_or_show

    sw = _sweep_module()
    maps = {}
    for p in prepared:
        try:
            maps[p.label] = solve_map(p, a, z0)
        except (ValueError, NotImplementedError) as e:
            refused[p.label] = str(e)
    out["maps"] = maps
    if not maps:
        _report_refused(refused)
        raise SystemExit(f"analysis {a.name!r}: every map was refused")
    kx, ky = (an.resolve(s.knob, builder).knob for s in a.sweeps)
    ground_label = {p.label: p.ground_label for p in prepared}
    if _has(a, an.Table):
        _print_map_table(maps, kx, ky, ground_label, z0)
    for label, (xs, ys, z) in maps.items():
        print(best_cell_line(label, xs, ys, z, kx, ky, z0))
    _report_refused(refused)
    if _has(a, an.Map):
        _map_figure(
            maps,
            xlabel=sw._param_label(kx),
            ylabel=sw._param_label(ky),
            refs=a.references,
            z0=z0,
            title=f"{a.name}: |Γ| on {z0:g} Ω",
            refused=list(refused),
        )
        save_or_show(plt, fn)
    return out


def best_cell_line(label, xs, ys, z, kx, ky, z0) -> str:
    """Where a map's |Γ| is least: the grid's best cell, not an optimum
    between cells (the optimizer's question, not the map's)."""
    gamma = np.abs((z - z0) / (z + z0))
    j, i = np.unravel_index(np.nanargmin(gamma), gamma.shape)
    g = float(gamma[j, i])
    swr = (1 + g) / (1 - g) if g < 1 else math.inf
    return (
        f"{label}: least |Γ| {g:.3g} (SWR {swr:.3g}) at {kx} {xs[i]:.6g}, "
        f"{ky} {ys[j]:.6g}: Z {z[j, i].real:.2f} {z[j, i].imag:+.2f}j"
    )


def _print_map_table(maps, kx, ky, ground_label, z0):
    """The `Table` view of a map: one row per grid cell, y outer, x inner."""
    for name, (xs, ys, z) in maps.items():
        print(f"== {kx} x {ky} map: {name} ==")
        print(f"ground: {ground_label[name]}")
        print(f"{kx:>12} {ky:>12} {'R (Ω)':>9} {'X (Ω)':>9} {'SWR':>8}")
        swr = swr_of(z, z0)
        for j, y in enumerate(ys):
            for i, x in enumerate(xs):
                zz = z[j, i]
                print(
                    f"{x:>12.6g} {y:>12.6g} {zz.real:>9.3f} {zz.imag:>+9.3f} "
                    f"{swr[j, i]:>8.3f}"
                )


def map_contours(refs: an.Ref, z0: float) -> list[tuple[str, float]]:
    """The map's contours, as ``(quantity, level)``: the `Ref` lines, R = r
    and X = x, since a map's reference lines are where the grid crosses
    them. With no Ref, X = 0 and R = z0: resonance, and the match."""
    if not refs.r and not refs.x:
        return [("X", 0.0), ("R", float(z0))]
    return [("X", float(x)) for x in refs.x] + [("R", float(r)) for r in refs.r]


def _map_figure(maps, *, xlabel, ylabel, refs, z0, title, refused):
    """One panel per map cell: |Γ| on ``z0`` as a heat map, and the contours
    `map_contours` names, each drawn from that cell's own grid. A level the
    grid never reaches is named in the legend as such, not dropped."""
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    n = len(maps)
    ncols = min(n, 3)
    nrows = math.ceil(n / ncols)
    fig, axs = plt.subplots(
        nrows, ncols, figsize=(6.2 * ncols, 5.0 * nrows), squeeze=False
    )
    contours = map_contours(refs, z0)
    styles = {"X": ("black", "-"), "R": (None, "--")}
    for k, (ax, (name, (xs, ys, z))) in enumerate(
        zip(axs.flat, maps.items(), strict=False)
    ):
        gamma = np.abs((z - z0) / (z + z0))
        mesh = ax.pcolormesh(
            xs, ys, gamma, shading="nearest", cmap="viridis_r", vmin=0.0, vmax=1.0
        )
        fig.colorbar(mesh, ax=ax, label=f"|Γ| on {z0:g} Ω")
        handles = []
        r_i = 0
        for quantity, level in contours:
            field = z.imag if quantity == "X" else z.real
            color, ls = styles[quantity]
            if color is None:
                color = ("tab:orange", "tab:red", "magenta", "tab:pink")[r_i % 4]
                r_i += 1
            label = f"{quantity} = {level:g} Ω"
            finite = field[np.isfinite(field)]
            if finite.size and finite.min() < level < finite.max():
                ax.contour(
                    xs, ys, field, levels=[level], colors=[color], linestyles=[ls]
                )
            else:
                label += " (not reached)"
            handles.append(Line2D([], [], color=color, linestyle=ls, label=label))
        for r in refused:
            handles.append(
                Line2D(
                    [],
                    [],
                    linestyle="None",
                    marker="x",
                    color="0.5",
                    label=f"{r}: refused",
                )  # fmt: skip
            )
        ax.legend(handles=handles, fontsize=7, loc="upper right", framealpha=0.8)
        ax.set_xlabel(xlabel)
        ax.set_ylabel(ylabel)
        ax.set_title(name, fontsize=10)
    for ax in list(axs.flat)[n:]:
        ax.set_visible(False)
    fig.suptitle(title, fontsize=11)
    fig.tight_layout()


def _views_fn(fn: str | None, tag: str = "-views") -> str | None:
    """Where the panels (``tag`` "-views") or the metric plots ("-metrics")
    go beside another figure written to ``fn``."""
    if fn is None or fn == "/dev/null":
        return fn
    from pathlib import Path

    p = Path(fn)
    return str(p.with_name(f"{p.stem}{tag}{p.suffix}"))


# ── metric plots (AK#1828) ───────────────────────────────────────────────


@dataclass(frozen=True)
class MetricCurve:
    """One cell's curve on a `MetricPlot`: ``xs`` and the metric there;
    ``fixed`` for a fixed reference (one solve, ``xs`` empty, ``values`` its
    one value); ``reference`` the label of the cell it is drawn relative to
    and ``relative`` the differences (None when the plot names none, or
    this cell's reference did not solve)."""

    xs: tuple
    values: tuple
    fixed: bool = False
    reference: str | None = None
    relative: tuple | None = None


def _metric_values(p: _Prepared, a: an.Analysis, metrics) -> tuple[list, list]:
    """``(xs, rows)``: each metric at every x of ``a``'s sweep on prepared
    cell ``p``, one solve per point (a far-field cut per metric on it). A
    fixed reference (no knobs) is solved once: ``xs`` empty, one row."""
    from . import metrics as mx

    def read():
        src = mx.source_for(p.factory(p.builder))
        return [mx.evaluate(m, src) for m in metrics]

    if not p.knobs:
        return [], [read()]
    s = a.sweep
    knob = p.knobs[0]
    xs = list(_xs(s, p.builder, knob))
    rows = []
    # The knob is put back after: the impedance views solve on the same
    # builder next, and a knob's own range is read off its value.
    own = getattr(p.builder, knob)
    try:
        for x in xs:
            setattr(p.builder, knob, x.item() if hasattr(x, "item") else x)
            rows.append(read())
    finally:
        setattr(p.builder, knob, own)
    return xs, rows


def _run_metric_plots(
    a, plots, all_cells, prepared, refused, *, session, design_seam, builder
):
    """Every `MetricPlot` of ``a``: each prepared cell's metrics against x
    (`_metric_values`, one solve per point for all the plots at once), each
    plot's references (`references`; a fixed one solved once, `_prepare`'s
    ``fixed``), the differences, and the table printed. Returns ``({metric
    name: {label: MetricCurve}}, {label: CSV columns})``."""
    metrics = []
    for v in plots:
        if v.metric not in metrics:
            metrics.append(v.metric)
    by_label = {c.label: c for c in all_cells}
    ready = {p.label: p for p in prepared}
    # A reference the impedance views refused because it is fixed (its state
    # sets the swept knob, its design lacks it) is solved once for the plot.
    for v in plots:
        for ref in set(references(a, v, all_cells).values()) - {None}:
            if ref in ready or ref not in by_label:
                continue
            cell = by_label[ref]
            try:
                b = _cell_seam(cell, session, design_seam)[0]()
                if not reference_fixed(cell, a, b):
                    continue
                ready[ref] = _prepare(cell, a, session, design_seam, False, fixed=True)
                if not any(_has(a, cls) for cls in _Z_VIEWS):
                    # Nothing else draws it: it is not refused. Beside R/X it
                    # stays refused THERE, by name, and the plot says fixed.
                    refused.pop(ref, None)
            except _Refused as e:
                refused[ref] = str(e)
    solved: dict[str, tuple] = {}
    for label, p in ready.items():
        try:
            solved[label] = _metric_values(p, a, metrics)
        except (ValueError, NotImplementedError) as e:
            # An engine declining the design, or a metric it cannot read
            # (`metrics.MetricError`), refuses the cell by name.
            refused[label] = str(e)
    if not solved:
        _report_refused(refused)
        raise SystemExit(f"analysis {a.name!r}: every curve was refused")
    out: dict = {}
    cols: dict[str, list] = {label: ([], []) for label in solved}
    for v in plots:
        i = metrics.index(v.metric)
        refs = references(a, v, all_cells)
        per: dict[str, MetricCurve] = {}
        for label, (xs, rows) in solved.items():
            per[label] = MetricCurve(tuple(xs), tuple(r[i] for r in rows), fixed=not xs)
        for label, curve in list(per.items()):
            ref = refs.get(label)
            base = per.get(ref) if ref is not None else None
            rel = None
            if base is not None and not curve.fixed:
                rel = tuple(
                    _diff(curve.values[k], _ref_at(base, curve.xs[k]))
                    for k in range(len(curve.xs))
                )
            elif base is not None:
                rel = (_diff(curve.values[0], base.values[0] if base.fixed else None),)
            per[label] = dataclasses.replace(curve, reference=ref, relative=rel)
        out[v.metric.name] = per
        _print_metric_table(a, v, per, builder)
        for label, curve in per.items():
            if curve.fixed:
                continue
            xs_col, c = cols[label]
            if not xs_col:
                xs_col.extend(curve.xs)
            c.append((_metric_heading(v.metric), curve.values))
            if curve.relative is not None:
                c.append((f"{v.metric.name} vs {curve.reference} ({_unit(v)})",
                          curve.relative))  # fmt: skip
    return out, {label: (xs, c) for label, (xs, c) in cols.items() if xs}


def _ref_at(base: MetricCurve, x) -> float | None:
    """The reference's value at ``x``: its one value when fixed, else its
    point at that x (None when it has none there)."""
    if base.fixed:
        return base.values[0]
    for bx, bv in zip(base.xs, base.values, strict=True):
        if float(bx) == float(x):
            return bv
    return None


def _diff(v, ref) -> float | None:
    return None if v is None or ref is None else float(v) - float(ref)


def _unit(v: an.MetricPlot) -> str:
    # A difference of gains is in dB, not dBi.
    return "dB" if v.metric.unit == "dBi" else v.metric.unit


def _metric_heading(m: an.PatternMetric) -> str:
    return f"{m.name} ({m.unit})" if m.unit else m.name


def _print_metric_table(a, v: an.MetricPlot, per: dict, builder) -> None:
    """A metric plot's numbers: one block per cell, x and the metric (and
    the difference from its reference), or a fixed reference's one value."""
    xname = "MHz" if a.sweep.knob == an.FREQUENCY else _step_name(a.sweep, builder)
    for label, c in per.items():
        print(f"== {_metric_heading(v.metric)} vs {xname}: {label} ==")
        if c.reference is not None and c.reference != label:
            print(f"relative to {c.reference}")
        if c.fixed:
            line = f"fixed reference, solved once: {_fmt_metric(c.values[0])}"
            print(line)
            continue
        head = f"{xname:>12} {v.metric.name:>14}"
        if c.relative is not None:
            head += f" {'vs ' + str(c.reference):>14}"
        print(head)
        for k, x in enumerate(c.xs):
            row = f"{float(x):>12.6g} {_fmt_metric(c.values[k]):>14}"
            if c.relative is not None:
                row += f" {_fmt_metric(c.relative[k]):>14}"
            print(row)


def _fmt_metric(v) -> str:
    return "—" if v is None else f"{v:.3f}"


def _metric_figure(a, plots, results, builder, knob, refused) -> None:
    """One panel per `MetricPlot`: each cell's metric (or its difference
    from its reference) against x, a fixed reference as a flat line."""
    import matplotlib.pyplot as plt

    sw = _sweep_module()
    fig, axs = plt.subplots(
        1, len(plots), figsize=(6.2 * len(plots), 4.6), squeeze=False
    )
    xlabel = (
        "frequency (MHz)" if a.sweep.knob == an.FREQUENCY else sw._param_label(knob)
    )
    for ax, v in zip(axs[0], plots, strict=True):
        per = results[v.metric.name]
        span = [float(x) for c in per.values() for x in c.xs]
        for i, (label, c) in enumerate(per.items()):
            ys = c.relative if v.relative_to is not None else c.values
            if ys is None:
                continue
            if c.fixed:
                if span:
                    ax.plot([min(span), max(span)], [ys[0], ys[0]], color=f"C{i}",
                            linestyle="--", label=f"{label} (fixed)")  # fmt: skip
                continue
            pts = [
                (float(x), y) for x, y in zip(c.xs, ys, strict=True) if y is not None
            ]
            if pts:
                ax.plot(*zip(*pts, strict=True), color=f"C{i}", marker="o", ms=3,
                        label=label)  # fmt: skip
        if v.relative_to is not None:
            ax.axhline(0.0, color="0.35", lw=0.8)
            ax.set_ylabel(f"{v.metric.name} vs {v.relative_to} ({_unit(v)})")
        else:
            ax.set_ylabel(_metric_heading(v.metric))
        ax.set_xlabel(xlabel)
        if a.sweep.spacing == "log":
            ax.set_xscale("log")
        for r in refused:
            if r in per:
                continue  # refused by the impedance views only
            ax.plot([], [], linestyle="None", marker="x", color="0.5",
                    label=f"{r}: refused")  # fmt: skip
        ax.legend(frameon=False, fontsize=7)
        ax.grid(alpha=0.3)
    fig.suptitle(a.name, fontsize=11)
    fig.tight_layout()


def _grid_words(s: an.Sweep, builder, xs) -> str:
    """The frequencies a run sweeps, and where they came from."""
    if s.values is not None:
        where = "the analysis's own values"
    else:
        r = frequency_range(s, builder)
        where = (
            "the analysis's own range"
            if r.level == "analysis"
            else f"{fr.level_words(r)} range"
        )
    return f"frequency {xs[0]:.6g}..{xs[-1]:.6g} MHz, {len(xs)} points ({where})"


def _print_frequency_table(curves, ground_label, z0):
    """The `Table` view of a frequency sweep: MHz, R, X and SWR per curve."""
    for name, xs, zs in curves:
        swr = swr_of(zs, z0)
        print(f"== frequency sweep: {name} ==")
        print(f"ground: {ground_label[name]}")
        print(f"{'MHz':>12} {'R (Ω)':>9} {'X (Ω)':>9} {'SWR':>8}")
        for x, z, v in zip(xs, zs, swr, strict=True):
            print(f"{x:>12.6g} {z.real:>9.3f} {z.imag:>+9.3f} {v:>8.3f}")


# ── SWR: its scales, and the band below a threshold ─────────────────────────


def swr_of(zs, z0: float) -> np.ndarray:
    """SWR of Z against ``z0``: ``sweep.swr_of``, the formula behind
    ``sweep --swr``."""
    return _sweep_module().swr_of(np.asarray(zs), z0)


# The workbench's whole-range VSWR scales (``lib/sweepAxis.ts``), labelled in
# SWR with ∞ at the top. "auto" is "reciprocal": VSWR has no Auto there, and
# a VSWR Auto reads as the 1–∞ scale (Steve, 2026-09-26).
_SWR_TICKS = (1, 1.5, 2, 3, 5, 10)


def swr_scale_y(swr, scale: str) -> np.ndarray:
    """SWR on the ``scale`` axis, 0 (SWR 1) to 1 (∞): 1 − 1/SWR
    ("reciprocal", "auto"), or ρ = (SWR − 1)/(SWR + 1) ("rho", EZNEC's).
    Anything not above 1 reads as 1; ∞ or NaN (|Γ| ≥ 1) is the top."""
    v = np.asarray(swr, dtype=float)
    top = ~np.isfinite(v)
    v = np.where(top | (v <= 1), 1.0, v)
    y = (v - 1) / (v + 1) if scale == "rho" else 1 - 1 / v
    return np.where(top, 1.0, y)


@dataclasses.dataclass(frozen=True)
class SwrBand:
    """One run of the sweep with SWR below the threshold: ``lo``/``hi`` the
    interpolated crossings, or the sweep's own end where the run meets it
    (``open_lo`` / ``open_hi``: the true band may extend past it)."""

    lo: float
    hi: float
    open_lo: bool
    open_hi: bool


def swr_bands(xs, swr, threshold: float) -> list[SwrBand]:
    """Every run of ``swr`` below ``threshold``, each edge linearly
    interpolated between the two samples straddling it. The workbench's
    ``swrBands`` (``lib/sweepAxis.ts``), the same rule: a sample AT the
    threshold is not below it, and a non-finite one counts as above."""
    xs = [float(x) for x in xs]
    v = [float(x) for x in swr]
    n = min(len(xs), len(v))

    def below(i):
        return math.isfinite(v[i]) and v[i] < threshold

    def cross(i):
        f0, v0, f1, v1 = xs[i - 1], v[i - 1], xs[i], v[i]
        return f0 if v1 == v0 else f0 + (threshold - v0) / (v1 - v0) * (f1 - f0)

    out = []
    start = None
    for i in range(n):
        if below(i) and start is None:
            if i == 0:
                start = (xs[0], True)
            else:
                start = (cross(i) if math.isfinite(v[i - 1]) else xs[i - 1], False)
        elif not below(i) and start is not None:
            hi = cross(i) if math.isfinite(v[i]) else xs[i]
            out.append(SwrBand(start[0], hi, start[1], False))
            start = None
    if start is not None and n:
        out.append(SwrBand(start[0], xs[n - 1], start[1], True))
    return out


def _span(mhz: float) -> str:
    # lib/sweepAxis.ts formatSpan: kHz below 1 MHz, else MHz.
    return f"{mhz * 1000:.0f} kHz" if mhz < 1 else f"{mhz:.3f} MHz"


def bandwidth_line(label, xs, swr, bands, threshold: float, freq: float) -> str:
    """The readout: the band holding the operating frequency ``freq``, else
    the widest (``primaryBand``), its edges, whether it runs off an end of
    the sweep, the others' count, and where the minimum is."""
    t = f"{threshold:g}:1"
    finite = [(v, x) for x, v in zip(xs, swr, strict=True) if math.isfinite(v)]
    low = min(finite) if finite else None
    minimum = "no finite SWR"
    if low:
        minimum = f"minimum SWR {low[0]:.3g} at {low[1]:.6g} MHz"
        if low[1] in (xs[0], xs[-1]):
            minimum += " (an end of the sweep: the true minimum may lie past it)"
    if not bands:
        return (
            f"{label}: {t} BW none: SWR stays at or above {t} over "
            f"{xs[0]:.6g}..{xs[-1]:.6g} MHz; {minimum}"
        )
    holding = [b for b in bands if b.lo <= freq <= b.hi]
    b = holding[0] if holding else max(bands, key=lambda b: b.hi - b.lo)
    ends = [e for e, o in (("low", b.open_lo), ("high", b.open_hi)) if o]
    width = ("≥ " if ends else "") + _span(b.hi - b.lo)
    text = f"{label}: {t} BW {width}, {b.lo:.6g}..{b.hi:.6g} MHz"
    if ends:
        text += (
            f" (runs off the {' and '.join(ends)} end"
            f"{'s' if len(ends) > 1 else ''} of the sweep)"
        )
    if len(bands) > 1:
        text += f" (1 of {len(bands)} bands below {t})"
    return text + f"; {minimum}"


def _views_figure(curves, views, *, xlabel, log_x, title, z0, threshold, refused):
    """The Swr, S11 and Smith views as panels of one figure, in the order
    the analysis names them. SWR is drawn on its view's scale with the
    threshold line; S11 is 20·log₁₀|Γ| with the threshold's return loss."""
    import matplotlib.pyplot as plt

    from .smith_chart import draw_smith_chart, plot_reflection

    fig, axs = plt.subplots(
        1, len(views), figsize=(5.4 * len(views), 4.8), squeeze=False
    )
    for ax, view in zip(axs[0], views, strict=True):
        for i, (name, x, z) in enumerate(curves):
            z = np.asarray(z)
            color = f"C{i}"
            gamma = (z - z0) / (z + z0)
            if isinstance(view, an.Smith):
                plot_reflection(ax, gamma, color=color, linewidth=1.6, label=name)
            elif isinstance(view, an.Swr):
                y = swr_scale_y(swr_of(z, z0), view.scale)
                ax.plot(x, y, color=color, marker="o", ms=3, label=name)
            else:
                ax.plot(
                    x,
                    20 * np.log10(np.abs(gamma)),
                    color=color,
                    marker="o",
                    ms=3,
                    label=name,
                )
        if isinstance(view, an.Smith):
            draw_smith_chart(ax, z0=z0)
            ax.set_title(f"Smith (z0 = {z0:g} Ω)", fontsize=10)
        elif isinstance(view, an.Swr):
            scale = "rho" if view.scale == "rho" else "reciprocal"
            ax.set_ylim(0, 1)
            ticks = list(swr_scale_y(_SWR_TICKS, scale)) + [1.0]
            ax.set_yticks(ticks, [f"{t:g}" for t in _SWR_TICKS] + ["∞"])
            if threshold is not None:
                ax.axhline(
                    float(swr_scale_y([threshold], scale)[0]),
                    color="0.35",
                    linestyle="-.",
                    lw=0.8,
                )
            ax.set_ylabel(
                "SWR (ρ scale)" if scale == "rho" else "SWR (1 − 1/SWR scale)"
            )
            ax.set_title(f"SWR (z0 = {z0:g} Ω)", fontsize=10)
        else:
            if threshold is not None:
                ax.axhline(
                    20 * math.log10((threshold - 1) / (threshold + 1)),
                    color="0.35",
                    linestyle="-.",
                    lw=0.8,
                )
            ax.set_ylabel("S11 20·log₁₀|Γ| (dB)")
            ax.set_title(f"S11 (z0 = {z0:g} Ω)", fontsize=10)
        if not isinstance(view, an.Smith):
            ax.set_xlabel(xlabel)
            if log_x:
                ax.set_xscale("log")
        for name in refused:
            ax.plot([], [], linestyle="None", marker="x", color="0.5",
                    label=f"{name}: refused")  # fmt: skip
        if len(curves) > 1 or refused:
            ax.legend(frameon=False, fontsize=7)
    fig.suptitle(title, fontsize=11)
    fig.tight_layout()


def _report_refused(refused: dict[str, str]) -> None:
    for label, why in refused.items():
        print(f"{label}: refused: {why}")

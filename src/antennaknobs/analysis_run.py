"""Running an `analyses.Analysis` from the command line (``antennaknobs
analyze``, AK#1757): step 2 of the sweep framework, CLI first.

Nothing here solves or draws on its own account. A knob sweep solves through
``sweep._solve_at`` and a density sweep through ``sweep._convergence_rows``,
the same functions ``antennaknobs sweep --param`` calls, so an analysis and
the equivalent ``sweep`` command are the same numbers by construction; the
chart is ``sweep._rx_overlay`` and the table ``sweep._print_convergence_table``.

What step 2 runs: a sweep over a knob, `analyses.DENSITY` or
`analyses.HEIGHT`; crosses over engines and grounds (their product, one curve
per cell); the `Rx` and `Table` views; `Ref` lines on R and X. Everything else
is refused by name, with the step it is planned for, when the analysis is
listed and when it is asked to run. A view the CLI cannot draw beside one it
can is left out with a note, and the rest runs.

A cross cell an engine cannot serve (an engine not on this machine's roster,
or one that refuses the design) is a REFUSED cell: named in the output and in
the legend, while the other cells run.
"""

from __future__ import annotations

import argparse
import itertools
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from . import analyses as an

# The sweep-framework step each refused piece is planned for (Steve,
# 2026-09-28): 3 the workbench lists and runs analyses in today's views; 4
# the frequency sweep and the SWR/S11/Smith views; 5 planes, designs,
# families and the map; 6 hold; 7 the UI writes the Python, and the deck
# stub.
_VIEW_STEP = {an.Swr: 4, an.S11: 4, an.Smith: 4, an.Map: 5, an.Knobs: 6}
_CROSS_STEP = {"planes": 5, "designs": 5, "step": 5}
_FREQUENCY_STEP = 4
_HOLD_STEP = 6
_RUNS = (an.Rx, an.Table)


def _later(what: str, step: int) -> str:
    return f"{what}: not in the CLI yet (sweep-framework step {step})"


def cli_gaps(a: an.Analysis) -> list[str]:
    """What refuses ``a`` as a whole in step 2's CLI."""
    out = []
    if len(a.sweeps) > 1:
        out.append(_later("a two-sweep map", _VIEW_STEP[an.Map]))
    elif a.sweep.knob == an.FREQUENCY:
        out.append(_later("a frequency sweep", _FREQUENCY_STEP))
    for c in a.crosses:
        if c.kind in _CROSS_STEP:
            out.append(_later(f"a cross over {c.kind}", _CROSS_STEP[c.kind]))
    if a.hold is not None:
        out.append(_later("hold (optimise at each point)", _HOLD_STEP))
    if not any(isinstance(v, _RUNS) for v in a.views):
        out += [
            _later(f"the {type(v).__name__} view", _VIEW_STEP[type(v)]) for v in a.views
        ]
    return out


def skipped_views(a: an.Analysis) -> list[str]:
    """Views left out of a run that draws at least one view."""
    if not any(isinstance(v, _RUNS) for v in a.views):
        return []
    return [
        _later(f"the {type(v).__name__} view", _VIEW_STEP[type(v)])
        for v in a.views
        if not isinstance(v, _RUNS)
    ]


def _fmt(v) -> str:
    return f"{v:g}" if isinstance(v, (int, float)) else str(v)


def _cross_words(c: an.Cross) -> str:
    if c.step is not None:
        knob = c.step.knob.name if isinstance(c.step.knob, an.Role) else c.step.knob
        return f"{c.size} values of {knob}"
    return f"{c.size} {c.kind}"


def summary(a: an.Analysis, builder) -> str:
    """One line: what is swept, over what, into how many curves."""
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
        if s.points is not None:
            what += f", {s.points} points"
        if s.spacing == "log":
            what += ", log"
        parts.append(what)
    text = " x ".join(parts)
    crosses = " x ".join(_cross_words(c) for c in a.crosses)
    n = a.curves
    text += f"; {n} curve{'s' if n != 1 else ''}" + (f" ({crosses})" if crosses else "")
    if a.hold is not None:
        held = ", ".join(an._knob_name(k) for k in a.hold.adjust)
        text += f"; hold {a.hold.objective} on {held}"
    return text + f"; views {', '.join(type(v).__name__ for v in a.views)}"


def list_lines(builder) -> list[str]:
    """``analyze --list``: one line per offered analysis, with every reason
    it cannot run here."""
    offered = an.offered(builder)
    width = max((len(a.name) for a in offered), default=0)
    lines = []
    for a in offered:
        probs = an.problems(a, builder) + cli_gaps(a)
        lines.append(f"{a.name:<{width}}  {summary(a, builder)}")
        for p in probs:
            lines.append(f"{'':<{width}}    {p}")
        if not probs:
            for p in skipped_views(a):
                lines.append(f"{'':<{width}}    (runs without {p})")
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
    """One curve: its label, its engine spec and ground spec (None: the
    session's own)."""

    label: str
    engine: str
    ground: str | None


def cells(a: an.Analysis, session_engine: str) -> list[Cell]:
    """The product of ``a``'s crosses, in the order they are written. A
    label names what varies: the engine, the ground, or both."""
    axes = [c for c in a.crosses if c.kind in ("engines", "grounds")]
    out = []
    for combo in itertools.product(*(getattr(c, c.kind) for c in axes)):
        chosen = dict(zip((c.kind for c in axes), combo, strict=True))
        engine = chosen.get("engines", a.engine or session_engine)
        ground = chosen.get("grounds", a.ground)
        label = ", ".join(chosen.values()) if chosen else engine
        out.append(Cell(label, engine, ground))
    return out


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


def run(
    a: an.Analysis,
    builder_factory: Callable,
    *,
    factory_for: FactoryFor,
    ground_label_for: Callable[[str | None], str],
    session_engine: str,
    z0: float = 50.0,
    fn: str | None = None,
) -> dict:
    """Run ``a`` on the design ``builder_factory`` makes. Returns what was
    computed, ``{"curves": {label: (xs, zs)}, "refused": {label: reason},
    "estimates": {label: ZInfEstimate}}`` (estimates on a density sweep only),
    for the tests; the table goes to stdout and the chart to ``fn``."""
    import matplotlib.pyplot as plt

    from .core import save_or_show

    sw = _sweep_module()

    builder = builder_factory()
    probs = an.problems(a, builder) + cli_gaps(a)
    if probs:
        raise SystemExit(f"analysis {a.name!r}: " + "; ".join(probs))
    knob = an.resolve(a.sweep.knob, builder).knob
    density = knob == "nominal_nsegs" or knob == an.density_knob(builder)
    print(f"analysis {a.name!r}: {summary(a, builder)}")
    for p in skipped_views(a):
        print(f"  runs without {p}")
    views = {type(v) for v in a.views}

    refused: dict[str, str] = {}
    factories = []
    ground_label = {}
    for cell in cells(a, session_engine):
        ground_label[cell.label] = ground_label_for(cell.ground)
        try:
            factories.append(
                (cell.label, factory_for(cell.engine, cell.ground, density))
            )
        except argparse.ArgumentTypeError as e:
            refused[cell.label] = str(e)

    s = a.sweep
    out: dict = {"curves": {}, "refused": refused}
    # A refusal is the engine declining the design (NEC-2 and a vertex feed),
    # which every engine raises as ValueError / NotImplementedError; any other
    # failure is a real error and propagates.
    if density:
        rungs, ladder, _marked, drawn = density_rungs(s)
        per, fed, nports = {}, {}, 1
        for label, factory in factories:
            try:
                rows, lens, n = sw._convergence_rows(builder, factory, rungs, knob)
            except (ValueError, NotImplementedError) as e:
                refused[label] = str(e)
                continue
            per[label], fed[label] = rows, lens
            nports = max(nports, n)
            out["curves"][label] = ([r[0] for r in rows], [r[2] for r in rows])
        if not per:
            _report_refused(refused)
            raise SystemExit(f"analysis {a.name!r}: every curve was refused")
        estimates, reasons = sw._convergence_estimates(per, fed, ladder)
        out["estimates"] = estimates
        if an.Table in views:
            sw._print_convergence_table(
                per,
                estimates,
                z0,
                ground_label={k: ground_label[k] for k in per},
                reasons=reasons,
                knob=knob,
            )
        _report_refused(refused)
        if an.Rx in views:
            axes = sw._rx_overlay(
                sw._convergence_panels(per, estimates, drawn),
                xlabel="segments achieved (log)",
                title=sw._convergence_title(knob, nports),
                log_x=True,
                xname="N",
                refused=list(refused),
            )
            _references(axes, a.references)
    else:
        log = s.spacing == "log"
        xs = knob_xs(s, builder, knob)
        curves = []
        nports = 1
        for label, factory in factories:
            try:
                zs = np.array(sw._solve_at(builder, knob, xs, factory))
            except (ValueError, NotImplementedError) as e:
                refused[label] = str(e)
                continue
            nports = max(nports, zs.shape[1])
            curves.append((label, xs, zs[:, 0]))
            out["curves"][label] = (list(xs), list(zs[:, 0]))
        if not curves:
            _report_refused(refused)
            raise SystemExit(f"analysis {a.name!r}: every curve was refused")
        if an.Table in views:
            _print_sweep_table(knob, curves, ground_label)
        _report_refused(refused)
        if an.Rx in views:
            title = sw._z_title(builder, knob)
            if nports > 1:
                title += f" (port 1 of {nports})"
            axes = sw._rx_overlay(
                [(name, x, z, [], None) for name, x, z in curves],
                xlabel=sw._param_label(knob),
                title=title,
                log_x=log,
                xname=knob,
                refused=list(refused),
            )
            _references(axes, a.references)
    if an.Rx in views:
        save_or_show(plt, fn)
    return out


def _report_refused(refused: dict[str, str]) -> None:
    for label, why in refused.items():
        print(f"{label}: refused: {why}")

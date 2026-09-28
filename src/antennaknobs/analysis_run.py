"""Running an `analyses.Analysis` from the command line (``antennaknobs
analyze``, AK#1757): step 2 of the sweep framework, CLI first.

Nothing here solves or draws on its own account. A knob sweep solves through
``sweep._solve_at`` and a density sweep through ``sweep._convergence_rows``,
the same functions ``antennaknobs sweep --param`` calls, so an analysis and
the equivalent ``sweep`` command are the same numbers by construction; the
chart is ``sweep._rx_overlay`` and the table ``sweep._print_convergence_table``.

What runs: a sweep over a knob, `analyses.DENSITY`, `analyses.HEIGHT` or
`analyses.FREQUENCY` (step 4); crosses over engines and grounds (their
product, one curve per cell); the `Rx`, `Table`, `Swr`, `S11` and `Smith`
views; `Ref` lines on R and X and the SWR threshold. A frequency sweep solves
through ``sweep.swr_curve``, the solve behind ``sweep --swr``, over
`frequency_range.design_range` when the spec gives no range: the rule
``sweep --swr`` and the workbench read. Everything else is refused by name,
with the step it is planned for, when the analysis is listed and when it is
asked to run.

One chart per run: `Rx` is ``sweep._rx_overlay``'s chart, as ``sweep``
draws it; `Swr`, `S11` and `Smith` are panels of one figure beside it
(`_views_figure`), written to ``fn`` when there is no `Rx`, else to
``<stem>-views<suffix>``.

A cross cell an engine cannot serve (an engine not on this machine's roster,
or one that refuses the design) is a REFUSED cell: named in the output and in
the legend, while the other cells run.
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

# The sweep-framework step each refused piece is planned for (Steve,
# 2026-09-28): 5 planes, designs, families and the map; 6 hold; 7 the UI
# writes the Python, and the deck stub.
_VIEW_STEP = {an.Map: 5, an.Knobs: 6}
_CROSS_STEP = {"planes": 5, "designs": 5, "step": 5}
_HOLD_STEP = 6
_RUNS = (an.Rx, an.Table, an.Swr, an.S11, an.Smith)
# The views drawn as panels of one figure (`_views_figure`).
_PANELS = (an.Swr, an.S11, an.Smith)


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


def _view_later(v: an.View) -> str:
    return not_a_view(v) or _later(f"the {type(v).__name__} view", view_step(v))


def cli_gaps(a: an.Analysis) -> list[str]:
    """What refuses ``a`` as a whole in the CLI."""
    out = []
    if len(a.sweeps) > 1:
        out.append(_later("a two-sweep map", _VIEW_STEP[an.Map]))
    for c in a.crosses:
        if c.kind in _CROSS_STEP:
            out.append(_later(f"a cross over {c.kind}", _CROSS_STEP[c.kind]))
    if a.hold is not None:
        out.append(_later("hold (optimise at each point)", _HOLD_STEP))
    if not any(isinstance(v, _RUNS) for v in a.views):
        out += [_view_later(v) for v in a.views]
    return out


def skipped_views(a: an.Analysis) -> list[str]:
    """Views left out of a run that draws at least one view."""
    if not any(isinstance(v, _RUNS) for v in a.views):
        return []
    return [_view_later(v) for v in a.views if not isinstance(v, _RUNS)]


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
        elif s.knob == an.FREQUENCY and r.knob is not None:
            what += _own_range_words(s, builder)
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
    frequency = s.knob == an.FREQUENCY
    # One (label, xs, Z at port 0) per curve that solved: what the Swr, S11
    # and Smith panels draw, whatever was swept.
    curves = []
    nports = 1
    # A refusal is the engine declining the design (NEC-2 and a vertex feed),
    # which every engine raises as ValueError / NotImplementedError; any other
    # failure is a real error and propagates.
    if density:
        rungs, ladder, _marked, drawn = density_rungs(s)
        per, fed = {}, {}
        for label, factory in factories:
            try:
                rows, lens, n = sw._convergence_rows(builder, factory, rungs, knob)
            except (ValueError, NotImplementedError) as e:
                refused[label] = str(e)
                continue
            per[label], fed[label] = rows, lens
            nports = max(nports, n)
            out["curves"][label] = ([r[0] for r in rows], [r[2] for r in rows])
            curves.append((label, [r[1] for r in rows], [r[2] for r in rows]))
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
        xlabel, log, title = (
            "segments achieved (log)",
            True,
            sw._convergence_title(knob, nports),
        )
        if an.Rx in views:
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
            xs = frequency_xs(s, builder)
            print(f"  {_grid_words(s, builder, xs)}")
        else:
            xs = knob_xs(s, builder, knob)
        for label, factory in factories:
            try:
                if frequency:
                    zs, _swr = sw.swr_curve(builder, "freq", xs, factory, z0)
                    zs = np.asarray(zs)
                else:
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
            if frequency:
                _print_frequency_table(curves, ground_label, z0)
            else:
                _print_sweep_table(knob, curves, ground_label)
        _report_refused(refused)
        xlabel = sw._param_label(knob)
        title = sw._z_title(builder, knob)
        if nports > 1:
            title += f" (port 1 of {nports})"
        if an.Rx in views:
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
    if an.Rx in views:
        save_or_show(plt, fn)
    panels = [v for v in a.views if isinstance(v, _PANELS)]
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
        save_or_show(plt, _views_fn(fn) if an.Rx in views else fn)
    return out


def _views_fn(fn: str | None) -> str | None:
    """Where the panels go beside an Rx chart written to ``fn``."""
    if fn is None or fn == "/dev/null":
        return fn
    from pathlib import Path

    p = Path(fn)
    return str(p.with_name(f"{p.stem}-views{p.suffix}"))


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

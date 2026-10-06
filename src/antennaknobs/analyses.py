"""Analyses: what a design offers to sweep, declared as values (AK#1757).

Imported as ``an`` (``from antennaknobs import analyses as an``). The shape is
the decided spec, ``docs/design/sweep-framework-spec.md``:

- an `Analysis` is a frozen value a design's ``build_analyses()`` returns.
  Nothing solves when it is built, so a list of them can be shown without
  running any;
- it has ONE `Sweep` (the x axis: a knob, or a `Role`), zero or more `Cross`
  values (the curves compared: their PRODUCT, capped at `CURVE_CAP`), the
  views it draws (`Rx`, `Swr`, `S11`, `Smith`, `Map`, `Table`, `Knobs`:
  objects with their own options), and the `Ref` lines drawn on them;
- or it has no sweep (``sweep=None``): a PATTERN, one far-field solve per
  cell at the measurement frequency, drawn by the pattern views
  (`Elevation`, `Azimuth`, `PatternTable`) and crossed like any other
  (AK#1757 step 7);
- a `State` is a named setting of a design, knob overrides over its
  defaults (its variant's, ``variant=``; a group knob's value a tuple of its
  entries); ``an.Cross(states=(...))`` crosses them like any other kind,
  one cell per state (AK#1757 step 7);
- ``an.Cross(cells=(an.Cell(...), ...))`` lists whole cells instead, each
  naming its own state, engine, ground and plane: a UNION, not a product,
  which is what a set of pins is (AK#1757 step 7, unit 4);
- a METRIC is a number read off a far-field pattern (AK#1828, step 8):
  `ElevationWindow`, `GainAt`, `TakeOff`, `PeakGain`, the pattern table's
  own columns (`TABLE_METRICS`), or the user's own function (`Metric`, called
  with a `Cut`). A pattern's `PatternTable(metrics=...)` adds a column per
  metric, and the swept view `MetricPlot` draws one against x, a far-field
  cut per sweep point, optionally relative to a named cell;
- an optional `Hold` optimises at every sweep point: the knobs it adjusts
  are re-solved for one of the optimizer's objectives as x moves;
- an analysis's ``group`` is the heading a long list shows it under
  (AK#1907): the design's list order sets the groups' order and the order
  inside each, and the generic analyses go last, under `GENERAL` (`grouped`);
- `convergence`, `band_swr`, `knob` and `patterns` are the library: generic
  analyses any design composes. `offered` is a design's own list plus the library's
  generic ones that resolve on it.

Every value prints back as the Python that constructs it (`to_code`), and
``eval`` of that text with ``an`` in scope equals the original: that is what
the workbench's "suggest the commands" and ``analyze --code`` read.

A role says what a knob MEANS, so a generic analysis finds it on any design.
It is declared in the knob's ``ui_params`` entry beside ``min`` / ``max``
(``{"base": {"min": 1.0, "max": 16.0, "role": "height"}}``). `resolve` maps a
sweep's knob or role to a knob name, or to the reason the design cannot
serve it: a missing role makes an analysis UNAVAILABLE on that design, by
name, never an exception.
"""

from __future__ import annotations

import dataclasses
import json
import keyword
import math
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import ClassVar

#: The most curves one analysis may draw: the product of its crosses.
#: Enforced when an analysis is LISTED (`problems`), not when it is built, so
#: one over-cap analysis cannot take down a design's whole list.
CURVE_CAP = 6

#: A knob or role sweep's point count when the spec gives none.
DEFAULT_POINTS = 11


# ── roles ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Role:
    """What a knob means. ``name`` is the ``ui_params`` ``role`` value."""

    name: str


FREQUENCY = Role("frequency")
DENSITY = Role("density")
HEIGHT = Role("height")

_ROLE_CONSTANTS = {FREQUENCY: "FREQUENCY", DENSITY: "DENSITY", HEIGHT: "HEIGHT"}


# ── the types ──────────────────────────────────────────────────────────────


def _as_tuple(value, what: str) -> tuple:
    # A bare string would iterate as characters: `engines="nec5"` is a
    # one-engine cross spelled wrong, not five engines.
    if isinstance(value, str):
        raise TypeError(f"{what} takes a tuple, got the string {value!r}")
    return tuple(value)


def _set(obj, name: str, value) -> None:
    object.__setattr__(obj, name, value)


@dataclass(frozen=True)
class Sweep:
    """The x axis: ``knob`` is a knob name or a `Role`. ``lo`` / ``hi`` /
    ``points`` None is the design's own (the knob's ``ui_params`` range, or
    the density ladder); ``values`` replaces the range. ``spacing`` None is
    the sweep's own: geometric for `DENSITY` (a convergence ladder, whose
    Z∞ reads a power law), linear otherwise (Steve, 2026-09-28). A linear
    density ladder is refused: Z∞ cannot be read from one."""

    knob: str | Role
    lo: float | None = None
    hi: float | None = None
    points: int | None = None
    values: tuple[float, ...] | None = None
    spacing: str | None = None

    _positional: ClassVar[tuple[str, ...]] = ("knob", "lo", "hi")

    def __post_init__(self):
        if not isinstance(self.knob, Role) and not (
            isinstance(self.knob, str) and self.knob
        ):
            raise TypeError(f"Sweep: knob is a knob name or a role, got {self.knob!r}")
        if self.spacing not in (None, "lin", "log"):
            raise ValueError(
                f"Sweep: spacing is 'lin', 'log' or None (the sweep's own), "
                f"got {self.spacing!r}"
            )
        if self.knob == DENSITY and self.spacing == "lin":
            raise ValueError(
                "Sweep: a density ladder is geometric (Z∞ reads a power law); "
                "drop spacing, or give 'log'"
            )
        if (self.lo is None) != (self.hi is None):
            raise ValueError("Sweep: give lo and hi together, or neither")
        if self.values is not None:
            _set(self, "values", _as_tuple(self.values, "Sweep values"))
            if self.lo is not None or self.points is not None:
                raise ValueError("Sweep: values replace lo/hi/points; give one")
            if not self.values:
                raise ValueError("Sweep: values is empty")
        if self.points is not None and (
            not isinstance(self.points, int) or self.points < 1
        ):
            raise ValueError(f"Sweep: points is a count >= 1, got {self.points!r}")
        if self.spacing == "log" and self.lo is not None and min(self.lo, self.hi) <= 0:
            raise ValueError("Sweep: a log sweep needs lo and hi above zero")

    @property
    def count(self) -> int | None:
        """How many points, when the spec says; None for the design's own."""
        if self.values is not None:
            return len(self.values)
        return self.points


# `step` stays last: every other kind is a tuple (`Cross.__post_init__`).
_CROSS_KINDS = ("engines", "grounds", "planes", "designs", "states", "cells", "step")

# What a state may set a knob to: the scalars a knob holds and ``to_code``
# prints back exactly, or a GROUP knob's value (fan_dipole's ``bands``): a
# tuple of its entries, each a mapping of the group's leaves to scalars
# (AK#1757 step 7, unit 4), or a tuple of scalars.
_STATE_VALUE = (bool, int, float, str)


def _scalar(v) -> bool:
    # bool is an int: both are fine, a finite number is required.
    return isinstance(v, _STATE_VALUE) and not (
        isinstance(v, float) and not math.isfinite(v)
    )


class Entry(Mapping):
    """One entry of a group knob's value in a `State` (a band of
    fan_dipole's ``bands``): a read-only mapping of the group's leaves to
    scalars, kept in the order written and hashable, so a state holding one
    stays a frozen, hashable spec value like any other. It prints back as
    the dict literal it was written as (`to_code`)."""

    __slots__ = ("_items",)

    def __init__(self, items: Mapping):
        self._items = tuple(items.items())

    def __getitem__(self, k):
        for key, v in self._items:
            if key == k:
                return v
        raise KeyError(k)

    def __iter__(self) -> Iterator:
        return (k for k, _ in self._items)

    def __len__(self) -> int:
        return len(self._items)

    def __hash__(self) -> int:
        return hash(frozenset(self._items))

    def __repr__(self) -> str:
        return repr(dict(self._items))


def _knob_value(owner: str, k: str, v):
    """``v`` as a state stores it: a scalar as given, a group's tuple with
    each entry an `Entry`; a TypeError naming the knob otherwise."""
    if _scalar(v):
        return v
    what = (
        f"{owner}: {k} takes a number, bool or string, or a group knob's "
        f"tuple of entries (dicts of numbers, bools or strings); got {v!r}"
    )
    # A str is a scalar (above); any other sequence is a group's value.
    if not isinstance(v, (tuple, list)) or not v:
        raise TypeError(what)
    if all(_scalar(e) for e in v):
        return tuple(v)
    out = []
    for e in v:
        if not isinstance(e, Mapping) or not e:
            raise TypeError(what)
        if not all(isinstance(key, str) and key for key in e) or not all(
            _scalar(x) for x in e.values()
        ):
            raise TypeError(what)
        out.append(Entry(e))
    return tuple(out)


def plain(v):
    """A state's knob value as plain data: an `Entry` as a dict, a group as
    a tuple of them. What a builder is set to and what ``/analyses`` serves:
    the shape a design's own ``default_params`` writes a group in."""
    if isinstance(v, tuple):
        return tuple(dict(e) if isinstance(e, Entry) else e for e in v)
    return v


@dataclass(frozen=True, init=False)
class State:
    """A named setting of a design (AK#1757 step 7): knob overrides applied
    over the design's DEFAULTS (its variant's, where one is named), not over
    whatever the knobs happen to be, so a state means the same curve in
    every session and on every machine. ``an.State("as built")`` is the
    defaults themselves. ``design`` names the state's design (a registry
    name): a study can compare specific settings of different designs;
    None is the design the analysis runs on (the tab's, ``--builder``'s),
    or each design of a ``designs=`` cross it multiplies with.

    ``variant`` (unit 4) builds the state's design at that variant's
    defaults (``dipoles.invvee:apex``, as the registry spells it), which is
    how a pin taken on a non-default variant is kept. It names a variant OF
    ``design``, so it needs ``design=``: a variant name means nothing until
    its design is named, and one design's variant set on every design of a
    cross would be refused on most of them.

    ``an.State("tall", base=12.0)``: the knobs are keyword arguments, kept
    in the order written, so `to_code` prints the state back as it was
    typed. A group knob takes a tuple of its entries, ``bands=({"freq":
    14.3, "length_factor": 0.49}, ...)``. Which knobs a design has is not
    known here: a knob the design lacks, one the analysis sweeps, steps or
    holds, or a value that does not fit the knob's shape (a group given a
    number, a number given a tuple) is refused when the analysis is listed
    (`problems`) or its cell prepared, by name."""

    name: str
    design: str | None
    variant: str | None
    knobs: tuple[tuple[str, object], ...]

    def __init__(
        self,
        name: str,
        design: str | None = None,
        *,
        variant: str | None = None,
        **knobs,
    ):
        if not isinstance(name, str) or not name:
            raise TypeError(f"State: name is a non-empty string, got {name!r}")
        if design is not None and not (isinstance(design, str) and design):
            raise TypeError(
                f"State {name!r}: design is a registry name or None, got {design!r}"
            )
        if variant is not None:
            if not (isinstance(variant, str) and variant) or ":" in variant:
                raise TypeError(
                    f"State {name!r}: variant is a variant's name or None, "
                    f"got {variant!r}"
                )
            if design is None:
                raise ValueError(
                    f"State {name!r}: variant= names a variant of the state's "
                    "design; give design= too"
                )
        values = []
        for k, v in knobs.items():
            if k == "ui_params":
                raise ValueError(f"State {name!r}: ui_params is not a knob")
            # `to_code` prints a knob as a keyword argument, so its name must
            # be one: anything else could not be written back, and would
            # carry text into the generated file (unit 4 writes it to disk).
            if not k.isidentifier() or keyword.iskeyword(k):
                raise ValueError(
                    f"State {name!r}: {k!r} is not a knob name (a Python identifier)"
                )
            values.append((k, _knob_value(f"State {name!r}", k, v)))
        _set(self, "name", name)
        _set(self, "design", design)
        _set(self, "variant", variant)
        _set(self, "knobs", tuple(values))

    @property
    def spec(self) -> str | None:
        """The state's design as the registry spells it (``name:variant``),
        or None: what ``cli.get_builder`` and a design seam take."""
        if self.design is None:
            return None
        return self.design if self.variant is None else f"{self.design}:{self.variant}"

    @property
    def label(self) -> str:
        """The state's part of a cell label: its name, after its design (and
        variant) when it names one, as a ``designs x states`` cell would
        read."""
        return self.name if self.design is None else f"{self.spec}, {self.name}"

    @property
    def settings(self) -> dict:
        """The knobs as plain data (`plain`): what a builder is set to."""
        return {k: plain(v) for k, v in self.knobs}


@dataclass(frozen=True, init=False)
class Cell:
    """One whole cell of an ``an.Cross(cells=...)`` (AK#1757 step 7, unit
    4): its `State` (and through it its design and variant), its engine
    spec, its ground spec and its plane. What a cell leaves out follows the
    analysis, as a cross cell's does: no state is the analysis's design at
    the knobs it runs on, no engine the analysis's (else the session's), no
    ground the analysis's (else the session's), no plane the design's own.

    A cell names its design THROUGH its state, one rule with no second
    spelling to disagree with it: ``an.Cell(an.State("as built",
    design="beams.yagi"), engine="nec5")``. ``design=`` on the cell itself is
    refused by name, pointing at that spelling."""

    state: State | None = None
    engine: str | None = None
    ground: str | None = None
    plane: str | None = None

    _positional: ClassVar[tuple[str, ...]] = ("state",)

    def __init__(
        self,
        state: State | None = None,
        *,
        engine: str | None = None,
        ground: str | None = None,
        plane: str | None = None,
        design: str | None = None,
    ):
        if design is not None:
            raise TypeError(
                "Cell: a cell names its design through its state, "
                f"an.Cell(an.State('as built', design={design!r}), ...); "
                "give the state design= instead"
            )
        if state is not None and not isinstance(state, State):
            raise TypeError(f"Cell: state is an an.State or None, got {state!r}")
        for field, v in (("engine", engine), ("ground", ground), ("plane", plane)):
            if v is not None and not (isinstance(v, str) and v):
                raise TypeError(f"Cell: {field} is a spec string or None, got {v!r}")
        _set(self, "state", state)
        _set(self, "engine", engine)
        _set(self, "ground", ground)
        _set(self, "plane", plane)

    @property
    def parts(self) -> tuple[str, ...]:
        """What the cell sets, as its label names it: the state's label, the
        engine, the ground and the plane, each as the spec spells it."""
        head = (self.state.label,) if self.state is not None else ()
        return head + tuple(v for v in (self.engine, self.ground, self.plane) if v)

    @property
    def label(self) -> str:
        """The cell's legend label, its `parts` joined by ", " as a product
        cell's are; "" for a cell that sets nothing (the analysis's own,
        which the runner names by its engine)."""
        return ", ".join(self.parts)


@dataclass(frozen=True)
class Cross:
    """The curves compared: exactly one of engine specs (as ``--engine``
    takes them), ground specs (as ``--ground`` takes them), measurement
    planes, designs, named knob settings (`State`, step 7), whole cells
    (`Cell`, step 7 unit 4: a union, never multiplied with another cross),
    or a second knob's values (``step``, a family)."""

    engines: tuple[str, ...] = ()
    grounds: tuple[str, ...] = ()
    planes: tuple[str, ...] = ()
    designs: tuple[str, ...] = ()
    states: tuple[State, ...] = ()
    cells: tuple[Cell, ...] = ()
    step: Sweep | None = None

    _positional: ClassVar[tuple[str, ...]] = ()

    def __post_init__(self):
        for f in _CROSS_KINDS[:-1]:
            _set(self, f, _as_tuple(getattr(self, f), f"Cross {f}"))
        if self.step is not None and not isinstance(self.step, Sweep):
            raise TypeError(f"Cross: step is a Sweep, got {self.step!r}")
        if not all(isinstance(s, State) for s in self.states):
            raise TypeError(f"Cross: states holds an.State values, got {self.states!r}")
        if not all(isinstance(c, Cell) for c in self.cells):
            raise TypeError(f"Cross: cells holds an.Cell values, got {self.cells!r}")
        given = [f for f in _CROSS_KINDS if getattr(self, f)]
        if len(given) != 1:
            raise ValueError(
                "Cross: give exactly one of engines, grounds, planes, designs, "
                f"states, cells or step (got {', '.join(given) or 'none'}); "
                "several Cross values multiply"
            )

    @property
    def kind(self) -> str:
        return next(f for f in _CROSS_KINDS if getattr(self, f))

    @property
    def size(self) -> int:
        """Curves this cross contributes to the product."""
        if self.step is not None:
            return self.step.count or DEFAULT_POINTS
        return len(getattr(self, self.kind))


@dataclass(frozen=True)
class Ref:
    """Reference lines: R = each of ``r``, X = each of ``x`` (ohms), and an
    SWR threshold. z0 is the session's own."""

    r: tuple[float, ...] = ()
    x: tuple[float, ...] = ()
    swr: float | None = None

    _positional: ClassVar[tuple[str, ...]] = ()

    def __post_init__(self):
        _set(self, "r", _as_tuple(self.r, "Ref r"))
        _set(self, "x", _as_tuple(self.x, "Ref x"))


@dataclass(frozen=True)
class View:
    """What an analysis draws. Each view is its own class, with its own
    options; `Analysis.views` holds instances."""

    _positional: ClassVar[tuple[str, ...]] = ()


@dataclass(frozen=True)
class Rx(View):
    """R and X against the swept value."""


@dataclass(frozen=True)
class Swr(View):
    """SWR against the swept value. ``scale`` is the workbench's SWR axis:
    ``"auto"``, ``"reciprocal"`` (1 − 1/SWR) or ``"rho"`` (EZNEC's |Γ|)."""

    scale: str = "auto"

    def __post_init__(self):
        if self.scale not in ("auto", "reciprocal", "rho"):
            raise ValueError(
                f"Swr: scale is 'auto', 'reciprocal' or 'rho', got {self.scale!r}"
            )


@dataclass(frozen=True)
class S11(View):
    """|S11| in dB against the swept value."""


@dataclass(frozen=True)
class Smith(View):
    """The trajectory on a Smith chart."""


@dataclass(frozen=True)
class Map(View):
    """A two-sweep map (the sweep is a pair): |Γ| on the session's z0 over
    (x, y), with the `Ref` lines as contours of R and X."""


@dataclass(frozen=True)
class Table(View):
    """The numbers, printed."""


@dataclass(frozen=True)
class Knobs(View):
    """The held knobs' values against the swept value (a `Hold`'s
    solution at each point)."""


# ── metrics (AK#1828, sweep-framework step 8) ──────────────────────────────
#
# A METRIC is a number read off a far-field pattern: a figure of merit the
# user defines (M0AGP's "DX gain", the power average of gain over 2-10 degrees
# of elevation), or one of the pattern table's own columns, which are metrics
# too (`TABLE_METRICS`), so the table has one path. A metric is a frozen value
# like every other spec object: it prints back (`to_code`), goes to data and
# back (`to_data` / `from_data`), and declares only WHAT it reads; the numbers
# are `antennaknobs.metrics`', which this module never imports (a design
# imports this one to declare its analyses).
#
# Angles are degrees: elevation above the horizon (0..90), azimuth from +x
# (as the workbench's cut dial reads). ``az=`` picks the elevation cut a
# metric reads: a number fixes it, `PEAK_AZ` is the azimuth of the pattern's
# peak gain (the pattern table's azimuth column: the cut through the main
# lobe, what an EZNEC/AutoEZ elevation plot usually shows), and `MEAN_AZ`
# power-averages each elevation over azimuth (1-degree steps round the
# circle) instead of reading one cut.


@dataclass(frozen=True)
class AzMode:
    """How a metric picks its azimuth when no number fixes it: `PEAK_AZ`
    or `MEAN_AZ`, the only two."""

    name: str

    def __post_init__(self):
        if self.name not in ("peak", "mean"):
            raise ValueError(
                f"AzMode: an.PEAK_AZ or an.MEAN_AZ, got AzMode({self.name!r})"
            )


PEAK_AZ = AzMode("peak")
MEAN_AZ = AzMode("mean")

_AZ_CONSTANTS = {PEAK_AZ: "PEAK_AZ", MEAN_AZ: "MEAN_AZ"}


def _is_number(v) -> bool:
    # bool is an int, and never an angle or a step.
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _check_az(owner: str, az) -> None:
    if isinstance(az, AzMode):
        return
    if not _is_number(az) or not 0 <= az < 360:
        raise ValueError(
            f"{owner}: az is an azimuth in degrees, 0 <= az < 360, or an.PEAK_AZ "
            f"or an.MEAN_AZ; got {az!r}"
        )


def _check_el(owner: str, field: str, el) -> None:
    if not _is_number(el) or not 0 <= el <= 90:
        raise ValueError(
            f"{owner}: {field} is an elevation in degrees, 0..90; got {el!r}"
        )


def _check_name(owner: str, name) -> None:
    if not isinstance(name, str) or not name.strip():
        raise TypeError(f"{owner}: name is a non-empty string, got {name!r}")


def _check_step(owner: str, step, lo: float, hi: float) -> None:
    """A positive step that lands on ``hi`` from ``lo`` (to 1e-9 degrees):
    the metric reads exactly the angles ``lo + i * step``, ends included."""
    if not _is_number(step) or step <= 0:
        raise ValueError(f"{owner}: step is a positive number of degrees, got {step!r}")
    n = round((hi - lo) / step)
    if abs(lo + n * step - hi) > 1e-9 * max(1.0, abs(hi)):
        raise ValueError(
            f"{owner}: step {step!r} does not divide {lo!r}..{hi!r}; the "
            "angles are lo + i*step, ends included"
        )


@dataclass(frozen=True)
class PatternMetric:
    """A number read off a far-field pattern (the module comment above).
    ``unit`` names what it reads in, for a table's heading and a plot's
    axis; ``key`` is the pattern table's own key for a column it computes
    (`TABLE_METRICS`), None for a metric only the user asks for."""

    _positional: ClassVar[tuple[str, ...]] = ("name",)
    unit = "dBi"
    key: ClassVar[str | None] = None

    @property
    def table_key(self) -> str | None:
        """The pattern table's key this metric IS, or None: a fixed
        column's, and `PeakGain` / `TakeOff` at `PEAK_AZ` (the cut through
        the peak holds the peak)."""
        return self.key


@dataclass(frozen=True)
class ElevationWindow(PatternMetric):
    """Gain over elevations ``lo``..``hi`` (degrees, ``step`` apart, ends
    included) on the cut ``az`` picks, reduced by ``mean``: "power" averages
    the power ratios and converts back to dB (M0AGP's DX gain: averaging dB
    values is meaningless), "db" averages the dB values, "max" takes the
    largest. ``an.ElevationWindow("DX gain", 2, 10, step=0.1)``."""

    name: str
    lo: float
    hi: float
    step: float = 1.0
    mean: str = "power"
    az: float | AzMode = PEAK_AZ

    _positional: ClassVar[tuple[str, ...]] = ("name", "lo", "hi")

    def __post_init__(self):
        who = f"ElevationWindow {self.name!r}"
        _check_name(who, self.name)
        _check_el(who, "lo", self.lo)
        _check_el(who, "hi", self.hi)
        if self.lo > self.hi:
            raise ValueError(f"{who}: lo {self.lo!r} is above hi {self.hi!r}")
        _check_step(who, self.step, self.lo, self.hi)
        if self.mean not in ("power", "db", "max"):
            raise ValueError(
                f"{who}: mean is 'power', 'db' or 'max', got {self.mean!r}"
            )
        _check_az(who, self.az)


@dataclass(frozen=True)
class GainAt(PatternMetric):
    """The gain at elevation ``el`` (degrees) on the cut ``az`` picks."""

    name: str
    el: float
    az: float | AzMode = PEAK_AZ

    _positional: ClassVar[tuple[str, ...]] = ("name", "el")

    def __post_init__(self):
        who = f"GainAt {self.name!r}"
        _check_name(who, self.name)
        _check_el(who, "el", self.el)
        _check_az(who, self.az)


@dataclass(frozen=True)
class PeakGain(PatternMetric):
    """The peak gain. At `PEAK_AZ` (the default) the pattern's own, the
    pattern table's column; at a fixed azimuth or `MEAN_AZ`, the largest
    gain on that cut, over 0..90 degrees ``step`` apart."""

    name: str = "peak gain"
    az: float | AzMode = PEAK_AZ
    step: float = 1.0

    key: ClassVar[str | None] = "peak_gain_dbi"

    def __post_init__(self):
        who = f"PeakGain {self.name!r}"
        _check_name(who, self.name)
        _check_az(who, self.az)
        _check_step(who, self.step, 0.0, 90.0)

    @property
    def table_key(self) -> str | None:
        return self.key if self.az == PEAK_AZ else None


@dataclass(frozen=True)
class TakeOff(PeakGain):
    """The take-off angle: the elevation of `PeakGain` on the same cut."""

    name: str = "take-off"

    unit = "deg"
    key: ClassVar[str | None] = "takeoff_deg"


@dataclass(frozen=True)
class PeakAzimuth(PatternMetric):
    """The azimuth of the pattern's peak gain: `PEAK_AZ` as a number."""

    name: str = "azimuth"

    _positional: ClassVar[tuple[str, ...]] = ()
    unit = "deg"
    key: ClassVar[str | None] = "azimuth_deg"

    def __post_init__(self):
        _check_name("PeakAzimuth", self.name)


@dataclass(frozen=True)
class FrontToBack(PeakAzimuth):
    """The peak gain less the gain 180 degrees round in azimuth, at the
    peak's elevation."""

    name: str = "F/B"

    unit = "dB"
    key: ClassVar[str | None] = "front_to_back_db"


@dataclass(frozen=True)
class AzBeamwidth(PeakAzimuth):
    """The -3 dB width through the peak in the azimuth ring at its
    elevation."""

    name: str = "az beamwidth"

    unit = "deg"
    key: ClassVar[str | None] = "az_beamwidth_deg"


@dataclass(frozen=True)
class ElBeamwidth(PeakAzimuth):
    """The -3 dB width through the peak in the elevation column at its
    azimuth (a lower bound when the lobe meets the horizon or zenith)."""

    name: str = "el beamwidth"

    unit = "deg"
    key: ClassVar[str | None] = "el_beamwidth_deg"


@dataclass(frozen=True)
class Rdf(PeakAzimuth):
    """The receiving directivity factor at the peak (`far_field.rdf_db`)."""

    name: str = "RDF"

    unit = "dB"
    key: ClassVar[str | None] = "rdf_db"


#: The pattern table's columns, as metrics, in the order the workbench's
#: compare table and ``/pattern_metrics`` key them: ONE path, so a column
#: the table shows and the same metric asked for by name are one number.
TABLE_METRICS = (
    PeakGain(),
    TakeOff(),
    PeakAzimuth(),
    FrontToBack(),
    AzBeamwidth(),
    ElBeamwidth(),
    Rdf(),
)


@dataclass(frozen=True, eq=False, init=False)
class Metric(PatternMetric):
    """A metric the user writes (the escape hatch): ``fn(cut) -> float``, a
    NAMED MODULE-LEVEL function, called with an `Cut`. A lambda or a
    nested function is refused by name: `to_code` writes the function by
    reference (``module.qualname``, the import with it), and has no text for
    one with no name.

    ``over="elevation"``: the cut is elevations ``lo``..``hi`` (default
    0..90) ``step`` apart at the azimuth ``az`` picks (None: `PEAK_AZ`).
    ``over="azimuth"``: azimuths 0..360-``step`` at elevation ``el``.
    ``unit`` is what ``fn`` returns, for a table heading and a plot axis.

    Equal when everything but the function is, and the function is the same
    one by reference: what `from_data` resolves a served function to."""

    name: str
    fn: object
    over: str = "elevation"
    step: float = 1.0
    az: float | AzMode | None = None
    el: float | None = None
    lo: float | None = None
    hi: float | None = None
    unit: str = "dBi"

    _positional: ClassVar[tuple[str, ...]] = ("name", "fn")

    def __init__(
        self,
        name: str,
        fn,
        *,
        over: str = "elevation",
        step: float = 1.0,
        az: float | AzMode | None = None,
        el: float | None = None,
        lo: float | None = None,
        hi: float | None = None,
        unit: str = "dBi",
    ):
        who = f"Metric {name!r}"
        _check_name(who, name)
        why = function_refusal(fn)
        if why:
            raise TypeError(f"{who}: {why}")
        if over not in ("elevation", "azimuth"):
            raise ValueError(
                f"{who}: over is 'elevation' or 'azimuth' (a whole-pattern "
                f"metric is not in v1), got {over!r}"
            )
        if over == "elevation":
            if el is not None:
                raise ValueError(
                    f"{who}: el= is an azimuth cut's elevation; an elevation "
                    "cut takes lo= / hi= and az="
                )
            if az is not None:
                _check_az(who, az)
            a, b = 0.0 if lo is None else lo, 90.0 if hi is None else hi
            _check_el(who, "lo", a)
            _check_el(who, "hi", b)
            if a > b:
                raise ValueError(f"{who}: lo {a!r} is above hi {b!r}")
            _check_step(who, step, a, b)
        else:
            if az is not None or lo is not None or hi is not None:
                raise ValueError(
                    f"{who}: an azimuth cut runs all the way round at el=; "
                    "az=, lo= and hi= are an elevation cut's"
                )
            if el is None:
                raise ValueError(f"{who}: an azimuth cut needs el= (degrees)")
            _check_el(who, "el", el)
            if el == 90:
                raise ValueError(
                    f"{who}: el=90 is the zenith, one direction, not a cut"
                )
            _check_step(who, step, 0.0, 360.0)
        if not isinstance(unit, str):
            raise TypeError(f"{who}: unit is a string, got {unit!r}")
        for f, v in (
            ("name", name),
            ("fn", fn),
            ("over", over),
            ("step", step),
            ("az", az),
            ("el", el),
            ("lo", lo),
            ("hi", hi),
            ("unit", unit),
        ):
            _set(self, f, v)

    @property
    def ref(self) -> str:
        """The function by reference: ``module.qualname``."""
        return function_ref(self.fn)

    def _key(self) -> tuple:
        return (
            self.name,
            self.ref,
            self.over,
            self.step,
            self.az,
            self.el,
            self.lo,
            self.hi,
            self.unit,
        )

    def __eq__(self, other):
        if not isinstance(other, Metric):
            return NotImplemented
        return self._key() == other._key()

    def __hash__(self):
        return hash(self._key())

    def __repr__(self) -> str:
        return f"Metric({self.name!r}, {self.ref}, over={self.over!r})"


def function_ref(fn) -> str:
    """``fn`` by reference, ``module.qualname``."""
    return f"{fn.__module__}.{fn.__qualname__}"


def function_refusal(fn) -> str | None:
    """Why ``fn`` cannot be a `Metric`'s function, or None: it must be a
    named, module-level Python function, since `to_code` writes it by
    reference and a lambda or a nested function has none."""
    import types

    if not isinstance(fn, types.FunctionType):
        return f"fn is a named module-level function (def f(cut): ...), got {fn!r}"
    qual = fn.__qualname__
    if fn.__name__ == "<lambda>":
        return (
            "fn is a lambda, which has no name to write back; define it with "
            "def at module level and pass it by name"
        )
    if "<locals>" in qual or "." in qual:
        return (
            f"fn {qual} is defined inside another function or a class; a "
            "metric's function is a module-level def, which to_code writes "
            "by reference"
        )
    if not isinstance(fn.__module__, str) or not fn.__module__:
        return f"fn {qual} has no module to be imported from"
    return None


#: The modules a function written by reference can never be imported from by
#: name: a user design or study is loaded by its path under a synthetic name.
_UNIMPORTABLE = ("__main__", "antennaknobs._user_designs", "antennaknobs._user_studies")


def importable(fn) -> bool:
    """Whether ``fn`` can be imported by its qualified name in another
    process (`to_code` writes ``module.qualname`` with ``import module``):
    not a script's ``__main__``, nor a user design or study file, which is
    loaded by path; a keep of one writes a comment saying to copy it."""
    mod = fn.__module__
    return not any(mod == p or mod.startswith(p + ".") for p in _UNIMPORTABLE)


def is_catalog_function(fn) -> bool:
    """Whether ``fn`` ships with antennaknobs (the catalog's, ours): the only
    callable metrics the hosted instance offers."""
    return fn.__module__.startswith("antennaknobs.") and importable(fn)


class Cut:
    """What a `Metric`'s function is called with: one cut of the pattern.

    - ``over``: "elevation" or "azimuth"; ``angles`` the cut's angles in
      degrees (``el`` / ``az`` name them by what they are);
    - ``gain_dbi``: total gain, dBi, at each angle; ``gain_v_dbi`` /
      ``gain_h_dbi`` its vertically and horizontally polarised parts,
      computed when first read (None where the engine cannot split them);
    - ``freq_mhz``: the frequency the pattern was solved at;
    - ``fixed_deg``: the cut's fixed angle, the azimuth of an elevation cut
      (`PEAK_AZ` resolved to its number) or the elevation of an azimuth cut;
      None for `MEAN_AZ`, which averages over azimuth instead of cutting.

    The arrays are numpy arrays; ``10 ** (cut.gain_dbi / 10)`` is the power
    ratio at each angle."""

    __slots__ = (
        "over",
        "angles",
        "gain_dbi",
        "freq_mhz",
        "fixed_deg",
        "_split",
        "_parts",
    )

    def __init__(
        self,
        *,
        over: str,
        angles,
        gain_dbi,
        freq_mhz: float,
        fixed_deg: float | None,
        polarized=None,
    ):
        self.over = over
        self.angles = angles
        self.gain_dbi = gain_dbi
        self.freq_mhz = freq_mhz
        self.fixed_deg = fixed_deg
        # A thunk for the two polarised parts: read only when a function asks,
        # since they cost another evaluation of the whole cut.
        self._split = polarized
        self._parts = None

    def _polarized(self):
        if self._parts is None:
            got = self._split() if self._split is not None else None
            self._parts = got if got is not None else (None, None)
        return self._parts

    @property
    def gain_v_dbi(self):
        return self._polarized()[0]

    @property
    def gain_h_dbi(self):
        return self._polarized()[1]

    @property
    def el(self):
        if self.over != "elevation":
            raise AttributeError("an azimuth cut's angles are cut.az")
        return self.angles

    @property
    def az(self):
        if self.over != "azimuth":
            raise AttributeError("an elevation cut's angles are cut.el")
        return self.angles


# ── the pattern views (AK#1757 step 7) ─────────────────────────────────────
#
# What the pattern pins draw, as views of an analysis with no swept x. The
# angles are WHOLE degrees, and each on the range both tools can sample: the
# CLI's engines return NEC's far-field grid (`far_field.compare_patterns`'s:
# theta 0..89 from the zenith, phi 0..360, 1-degree steps), which has no
# horizon row (elevation 0 is theta 90) and whose zenith is one direction, not
# a cut; the workbench's azimuth-cut dial runs 0..89. So an azimuth cut is at
# an elevation of 1..89, and an elevation cut at an azimuth of 0..359.


def _whole_degrees(owner: str, field: str, value, lo: int, hi: int) -> None:
    # bool is an int, and never an angle.
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or not float(value).is_integer()
        or not lo <= value <= hi
    ):
        raise ValueError(
            f"{owner}: {field} is a whole number of degrees, {lo}..{hi} (the "
            f"far-field grid's 1-degree steps), got {value!r}"
        )


@dataclass(frozen=True, kw_only=True)
class Elevation(View):
    """An elevation cut: the vertical great circle through azimuth ``az``
    (degrees from +x, as the workbench's cut dial reads), from that horizon
    over the zenith to the opposite one."""

    az: int

    def __post_init__(self):
        _whole_degrees("Elevation", "az", self.az, 0, 359)


@dataclass(frozen=True, kw_only=True)
class Azimuth(View):
    """An azimuth cut: the cone at elevation ``el`` degrees above the
    horizon, all the way round."""

    el: int

    def __post_init__(self):
        _whole_degrees("Azimuth", "el", self.el, 1, 89)


@dataclass(frozen=True)
class PatternTable(View):
    """The pattern metrics per cell: the pattern-pin compare table's (peak
    gain, take-off angle, azimuth, F/B, both beamwidths, RDF: `TABLE_METRICS`),
    then a column per metric in ``metrics`` (AK#1828): the user's own,
    ``an.PatternTable(metrics=(an.ElevationWindow("DX gain", 2, 10,
    step=0.1),))``."""

    metrics: tuple[PatternMetric, ...] = ()

    def __post_init__(self):
        metrics = (
            (self.metrics,) if isinstance(self.metrics, PatternMetric) else self.metrics
        )
        metrics = _as_tuple(metrics, "PatternTable metrics")
        if not all(isinstance(m, PatternMetric) for m in metrics):
            raise TypeError(
                "PatternTable: metrics holds metrics (an.ElevationWindow(...), "
                f"an.Metric(...), ...), got {metrics!r}"
            )
        _check_metric_names("PatternTable", metrics)
        _set(self, "metrics", metrics)


def _check_metric_names(owner: str, metrics) -> None:
    """A metric is found by its name (a column, a curve's label): two alike
    would be two columns the reader cannot tell apart."""
    names = [m.name for m in metrics]
    twice = sorted({n for n in names if names.count(n) > 1})
    if twice:
        raise ValueError(f"{owner}: two metrics are named {twice[0]!r}")


@dataclass(frozen=True)
class MetricPlot(View):
    """A metric against the swept x (AK#1828): one far-field cut per sweep
    point, per cell. ``relative_to`` names a cell, by its state's name, its
    design or its label, and the plot is each curve LESS that cell's (in the
    metric's unit: dB for a gain), M0AGP's "vertical = 0". A curve's
    reference is the named cell that matches it on everything else the cells
    vary over (engine, ground, plane, family step).

    A reference whose state sets the swept knob, or whose design has no such
    knob, is a FIXED reference: solved once at its own setting and drawn
    flat. That is how a new antenna is compared with a standard one while
    one of its knobs moves (a full vertical against shortening inverted
    Ls)."""

    metric: PatternMetric
    relative_to: str | None = None

    _positional: ClassVar[tuple[str, ...]] = ("metric",)

    def __post_init__(self):
        if not isinstance(self.metric, PatternMetric):
            raise TypeError(
                "MetricPlot: metric is a metric (an.ElevationWindow(...), "
                f"an.Metric(...), ...), got {self.metric!r}"
            )
        if self.relative_to is not None and not (
            isinstance(self.relative_to, str) and self.relative_to
        ):
            raise TypeError(
                "MetricPlot: relative_to names a cell (a state's name, a design, "
                f"or a cell's label), got {self.relative_to!r}"
            )


#: The views of a pattern (``sweep=None``); every other view draws against a
#: swept x.
PATTERN_VIEWS = (Elevation, Azimuth, PatternTable)


def is_pattern(analysis) -> bool:
    """Whether ``analysis`` is a pattern: no swept x (AK#1757 step 7)."""
    return analysis.sweep is None


# The square systems the optimizer solves as roots (`web.optimize`, the
# scalar-root and two-component Newton paths): as many knobs as equations.
_SQUARE = {
    "resonance": (
        1,
        "resonance is one equation (X = 0); give it one knob, or hold match_z0 "
        "with two",
    ),
    "match_z0": (
        2,
        "match_z0 is two equations (R = Z0, X = 0); give it two knobs, or hold "
        "resonance with one",
    ),
}


@dataclass(frozen=True)
class Hold:
    """Optimise at every sweep point: re-solve the ``adjust`` knobs (names or
    roles) for ``objective``, one of the optimizer's own
    (``web.optimize.OBJECTIVES``). ``z0`` None is the session's;
    ``warm_start`` seeds each point from the previous point's solution
    (continuation, as the workbench's track-while-drag does)."""

    objective: str
    adjust: tuple[str | Role, ...]
    z0: float | None = None
    warm_start: bool = True

    _positional: ClassVar[tuple[str, ...]] = ("objective",)

    def __post_init__(self):
        # On use, not at module import: the optimizer module pulls in scipy,
        # and a design imports this module to declare its analyses.
        from .web.optimize import OBJECTIVES

        if self.objective not in OBJECTIVES:
            raise ValueError(
                f"Hold: objective is one of the optimizer's {', '.join(OBJECTIVES)}; "
                f"got {self.objective!r}"
            )
        adjust = _as_tuple(self.adjust, "Hold adjust")
        if not adjust:
            raise ValueError("Hold: adjust names at least one knob")
        if not all(isinstance(k, Role) or (isinstance(k, str) and k) for k in adjust):
            raise TypeError(f"Hold: adjust holds knob names or roles, got {adjust!r}")
        if len(set(adjust)) != len(adjust):
            raise ValueError(f"Hold: adjust names a knob twice: {adjust!r}")
        _set(self, "adjust", adjust)
        square = _SQUARE.get(self.objective)
        if square is not None and len(adjust) != square[0]:
            raise ValueError(f"Hold: {square[1]} (got {len(adjust)})")


@dataclass(frozen=True)
class Analysis:
    """One analysis. ``sweep`` is a `Sweep`, or a pair of them for a map,
    or None for a pattern (one solve per cell, drawn by `PATTERN_VIEWS`);
    ``cross`` a `Cross` or a tuple of them (their product); ``ground`` /
    ``engine`` None is the session's own. ``group`` is the heading it is
    listed under (AK#1907, `grouped`); None is `GENERAL`."""

    name: str
    sweep: Sweep | tuple[Sweep, Sweep] | None
    cross: Cross | tuple[Cross, ...] = ()
    views: tuple[View, ...] = (Rx(),)
    references: Ref = Ref()
    ground: str | None = None
    engine: str | None = None
    hold: Hold | None = None
    group: str | None = None

    _positional: ClassVar[tuple[str, ...]] = ("name", "sweep")

    def __post_init__(self):
        if not isinstance(self.name, str) or not self.name:
            raise TypeError(f"Analysis: name is a non-empty string, got {self.name!r}")
        if self.group is not None and (
            not isinstance(self.group, str) or not self.group.strip()
        ):
            raise TypeError(
                f"Analysis {self.name!r}: group is a non-empty string or None, "
                f"got {self.group!r}"
            )
        sweeps = self.sweeps
        if self.sweep is not None and (
            not 1 <= len(sweeps) <= 2 or not all(isinstance(s, Sweep) for s in sweeps)
        ):
            raise TypeError(
                f"Analysis {self.name!r}: sweep is a Sweep, a pair of them, or "
                "None (a pattern)"
            )
        cross = (self.cross,) if isinstance(self.cross, Cross) else self.cross
        cross = _as_tuple(cross, f"Analysis {self.name!r} cross")
        if not all(isinstance(c, Cross) for c in cross):
            raise TypeError(f"Analysis {self.name!r}: cross holds Cross values")
        kinds = [c.kind for c in cross]
        twice = sorted({k for k in kinds if kinds.count(k) > 1})
        if twice:
            raise ValueError(
                f"Analysis {self.name!r}: crosses over {', '.join(twice)} twice; "
                "one Cross per kind"
            )
        if "cells" in kinds and len(kinds) > 1:
            # A cell is whole: its state, engine, ground and plane are all
            # its own. Crossed with anything, each cell would be multiplied
            # into several, which is the product cells= exists to avoid (a
            # set of pins is not one), and the cells' own engine or ground
            # would fight the other cross's. So one or the other, by name.
            others = ", ".join(k for k in kinds if k != "cells")
            raise ValueError(
                f"Analysis {self.name!r}: cells= lists whole cells, a union, and "
                f"does not multiply with another cross (got cells and {others}); "
                "give each cell its own engine, ground, plane and state instead"
            )
        # One Cross is stored bare, as written: it prints back the same way.
        _set(self, "cross", cross[0] if len(cross) == 1 else cross)
        views = (self.views,) if isinstance(self.views, View) else self.views
        views = _as_tuple(views, f"Analysis {self.name!r} views")
        if not views or not all(isinstance(v, View) for v in views):
            raise TypeError(
                f"Analysis {self.name!r}: views holds view objects (an.Rx(), ...)"
            )
        _set(self, "views", views)
        self._check_pattern_views(views)
        if not isinstance(self.references, Ref):
            raise TypeError(f"Analysis {self.name!r}: references is an an.Ref")
        if self.hold is not None:
            if not isinstance(self.hold, Hold):
                raise TypeError(f"Analysis {self.name!r}: hold is an an.Hold")
            swept = {s.knob for s in sweeps}
            clash = [k for k in self.hold.adjust if k in swept]
            if clash:
                raise ValueError(
                    f"Analysis {self.name!r}: the hold adjusts the swept knob "
                    f"{_knob_name(clash[0])}; a knob is swept or held, not both"
                )
        elif any(isinstance(v, Knobs) for v in views):
            raise ValueError(
                f"Analysis {self.name!r}: the Knobs view draws a hold's knobs; "
                "give a hold, or drop the view"
            )

    def _check_pattern_views(self, views: tuple[View, ...]) -> None:
        """A pattern view needs a pattern, and a pattern only pattern views
        (AK#1757 step 7): the two kinds of view draw against different axes
        (an angle round a cut, or a swept x), so a view of the other kind
        has nothing to draw, and is refused by name when the value is built.
        So is a hold on a pattern: it optimises at every sweep point, and a
        pattern has none."""
        who = f"Analysis {self.name!r}"
        if self.sweep is None:
            wrong = [v for v in views if not isinstance(v, PATTERN_VIEWS)]
            if wrong:
                raise ValueError(
                    f"{who}: the {type(wrong[0]).__name__} view draws against a "
                    "swept x, and this analysis sweeps nothing (sweep=None, a "
                    "pattern); a pattern's views are an.Elevation(az=...), "
                    "an.Azimuth(el=...) and an.PatternTable()"
                )
            if self.hold is not None:
                raise ValueError(
                    f"{who}: a hold optimises at every sweep point, and a "
                    "pattern (sweep=None) has none"
                )
            return
        wrong = [v for v in views if isinstance(v, PATTERN_VIEWS)]
        if wrong:
            raise ValueError(
                f"{who}: the {type(wrong[0]).__name__} view draws a far-field "
                "pattern, one solve per cell with no swept x; give sweep=None "
                "for a pattern, or drop the view"
            )

    @property
    def crosses(self) -> tuple[Cross, ...]:
        return (self.cross,) if isinstance(self.cross, Cross) else self.cross

    @property
    def sweeps(self) -> tuple[Sweep, ...]:
        """The swept axes: one, a map's pair, or none for a pattern."""
        if self.sweep is None:
            return ()
        return self.sweep if isinstance(self.sweep, tuple) else (self.sweep,)

    @property
    def curves(self) -> int:
        """The product of the crosses: how many curves the analysis draws."""
        return math.prod(c.size for c in self.crosses)


def _knob_name(k: str | Role) -> str:
    return k.name if isinstance(k, Role) else k


# ── the library ──────────────────────────────────────────────────────────


def convergence(**kw) -> Analysis:
    """The density ladder: does the answer stop moving as the mesh refines?"""
    return Analysis(
        **{
            "name": "convergence",
            "sweep": Sweep(DENSITY),
            "views": (Rx(), Table(), Smith()),
            **kw,
        }
    )


def band_swr(**kw) -> Analysis:
    """SWR across the design's measurement range, with a 2:1 threshold."""
    return Analysis(
        **{
            "name": "band SWR",
            "sweep": Sweep(FREQUENCY),
            "views": (Swr(),),
            "references": Ref(swr=2.0),
            **kw,
        }
    )


def knob(name: str, **kw) -> Analysis:
    """R/X and the Smith trail against one knob, over its own range."""
    return Analysis(
        **{"name": name, "sweep": Sweep(name), "views": (Rx(), Smith()), **kw}
    )


def patterns(**kw) -> Analysis:
    """The far field at the measurement frequency (AK#1757 step 7): the
    elevation cut along +x, the azimuth cut at 10 degrees, and the metrics
    the pattern pins' compare table shows, one solve per cell."""
    return Analysis(
        **{
            "name": "patterns",
            "sweep": None,
            "views": (Elevation(az=0), Azimuth(el=10), PatternTable()),
            **kw,
        }
    )


# ── roles on a design ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class Resolved:
    """A sweep's knob on one design: ``knob`` set, or ``reason`` why not."""

    knob: str | None
    reason: str | None = None


def _params(builder) -> Mapping:
    params = getattr(builder, "_params", None)
    return params if isinstance(params, Mapping) else {}


def _ui(params: Mapping) -> Mapping:
    ui = params.get("ui_params")
    return ui if isinstance(ui, Mapping) else {}


def role_knobs(builder, role: Role) -> list[str]:
    """The knobs whose ``ui_params`` entry declares ``role``."""
    params = _params(builder)
    return [
        k
        for k, meta in _ui(params).items()
        if isinstance(meta, Mapping) and meta.get("role") == role.name and k in params
    ]


def resolve(target: str | Role, builder) -> Resolved:
    """The knob ``target`` (a knob name, or a `Role`) sweeps on ``builder``
    (an instance): a declared role knob; for `DENSITY` with none declared,
    ``nominal_nsegs``, unless the design's segment counts are its file's
    own; for `FREQUENCY`, ``freq``. Two knobs claiming one role is a reason
    too: a role names one knob."""
    params = _params(builder)
    if isinstance(target, str):
        if target in params and target != "ui_params":
            return Resolved(target)
        return Resolved(None, f"this design has no knob {target!r}")
    if target == FREQUENCY:
        return (
            Resolved("freq")
            if "freq" in params
            else Resolved(None, "this design has no measurement frequency")
        )
    claimed = role_knobs(builder, target)
    if len(claimed) == 1:
        return Resolved(claimed[0])
    if claimed:
        return Resolved(
            None,
            f"this design declares {len(claimed)} {target.name} knobs "
            f"({', '.join(claimed)}); a role names one knob",
        )
    if target == DENSITY:
        if _ui(params).get("fixed_segment_counts"):
            return Resolved(
                None,
                "this design's segment counts are its file's own, and it "
                "declares no density knob",
            )
        return Resolved("nominal_nsegs")
    return Resolved(
        None,
        f"this design declares no {target.name} knob "
        f'(a ui_params entry with role: "{target.name}")',
    )


def density_knob(builder) -> str | None:
    """The knob playing the density role on ``builder``, or None."""
    return resolve(DENSITY, builder).knob


def offered(builder) -> tuple[Analysis, ...]:
    """A design's analyses: its own ``build_analyses()``, then the library's
    generic ones that resolve on it -- `convergence` and `band_swr` always, a
    height sweep when a height knob is declared. A design's own analysis
    shadows a generic one of the same name. In `grouped` order: each group
    together, the design's own order kept inside it."""
    own = tuple(builder.build_analyses())
    names = {a.name for a in own}
    generic = [convergence(), band_swr()]
    if resolve(HEIGHT, builder).knob is not None:
        generic.append(Analysis("height", Sweep(HEIGHT)))
    listed = own + tuple(a for a in generic if a.name not in names)
    return tuple(a for _, members in grouped(listed) for a in members)


# ── groups (AK#1907) ───────────────────────────────────────────────────────

#: The heading of an analysis that names no group: the library's generic
#: ones, unless a design lists one of them under a group of its own.
GENERAL = "General"

#: A list this long or shorter is shown without headings: one heading per
#: entry or two is noise, and it keeps most of the catalog as it was.
GROUPS_FROM = 4


def group_of(analysis: Analysis) -> str:
    """The heading ``analysis`` is listed under: its ``group``, else
    `GENERAL`."""
    return analysis.group or GENERAL


def grouped(analyses) -> list[tuple[str, list]]:
    """``analyses`` as ``[(heading, [analysis, ...]), ...]``: the groups in
    the order the list first names them (the first is the most important),
    each holding its members in list order. `GENERAL` goes last unless an
    analysis names it explicitly, which places it where it is named: the
    generic analyses are what every design has, so they follow what is the
    design's own."""
    order: list[str] = []
    for a in analyses:
        if a.group is not None and a.group not in order:
            order.append(a.group)
    if GENERAL not in order:
        order.append(GENERAL)
    out = [(g, [a for a in analyses if group_of(a) == g]) for g in order]
    return [(g, members) for g, members in out if members]


def shows_groups(analyses) -> bool:
    """Whether a list of ``analyses`` is shown with its headings: at least
    `GROUPS_FROM` of them, in more than one group."""
    analyses = list(analyses)
    return len(analyses) >= GROUPS_FROM and len(grouped(analyses)) > 1


def cells_of(analysis: Analysis) -> tuple[Cell, ...]:
    """The analysis's listed cells (its ``cells=`` cross), or ()."""
    return next((c.cells for c in analysis.crosses if c.kind == "cells"), ())


def states_of(analysis: Analysis) -> tuple[State, ...]:
    """The analysis's states, in order: its cross over states, or the states
    its listed cells name (unit 4), or ()."""
    cells = cells_of(analysis)
    if cells:
        return tuple(c.state for c in cells if c.state is not None)
    return next((c.states for c in analysis.crosses if c.kind == "states"), ())


def crosses_designs(analysis: Analysis) -> bool:
    return any(c.kind == "designs" for c in analysis.crosses)


def named_designs(analysis: Analysis) -> tuple[str, ...]:
    """The designs ``analysis`` names: its ``designs=`` cross, else the
    designs its states name (a ``states=`` cross's, or its listed cells'),
    each once, in the order written, without their variants (a variant is a
    setting of its design, and a tab lists a study by design). A study names
    its designs one of these ways (AK#1757 step 7)."""
    for c in analysis.crosses:
        if c.kind == "designs":
            return c.designs
    return tuple(dict.fromkeys(s.design for s in states_of(analysis) if s.design))


def state_refusal(
    state: State, analysis: Analysis, builder, *, fixed: bool = False
) -> str | None:
    """Why ``state`` cannot be set on ``builder`` (an instance of the design
    it is set on) in ``analysis``, or None. Each is a setting the run would
    silently undo or never make, so each is refused by name:

    - a knob the design does not have (a typo, or another design's knob);
    - the density knob: on a ladder it is the swept knob, and on any other
      sweep the engine holds the solve at its own density (#1543), so the
      state's value would be overwritten at every solve;
    - the knob the analysis sweeps (a state is one setting, the sweep moves
      it through many), the one its family steps, or one its hold adjusts.

    Roles resolve on ``builder``: a height sweep's knob is ``base`` on one
    design and something else on another, so a clash is a property of the
    (state, design) pair, not of the spec alone.

    ``fixed``: the state is a `MetricPlot`'s fixed reference (AK#1828),
    solved once at its own setting, outside the sweep, the family and the
    hold, so a knob any of them moves is its own to set."""
    params = _params(builder)
    who = f"state {state.name!r}"
    dens = density_knob(builder)
    for k, v in state.knobs:
        if k == "nominal_nsegs" or k == dens:
            ladder = any(resolve(s.knob, builder).knob == k for s in analysis.sweeps)
            return f"{who} sets {k}, the density knob: " + (
                "the ladder sweeps it; a state is one setting of the other knobs"
                if ladder
                else "the engine holds a sweep at its own density, so the "
                "setting would be undone at every solve"
            )
        if k not in params:
            return f"{who} sets {k}, and this design has no knob {k!r}"
        why = _shape_refusal(k, v, params[k])
        if why:
            return f"{who} sets {why}"
    if fixed:
        return None
    for s in analysis.sweeps:
        swept = resolve(s.knob, builder).knob
        if swept in state.settings:
            return (
                f"{who} sets {swept}, which the analysis sweeps; a knob is "
                "swept or set by a state, not both"
            )
    for c in analysis.crosses:
        if c.step is not None:
            stepped = resolve(c.step.knob, builder).knob
            if stepped in state.settings:
                return (
                    f"{who} sets {stepped}, which the family steps; a knob is "
                    "stepped or set by a state, not both"
                )
    if analysis.hold is not None:
        for k in analysis.hold.adjust:
            held = resolve(k, builder).knob
            if held in state.settings:
                return (
                    f"{who} sets {held}, which the hold adjusts at every point; "
                    "a knob is held or set by a state, not both"
                )
    return None


def metric_plots(analysis: Analysis) -> tuple[MetricPlot, ...]:
    """The analysis's `MetricPlot` views, in order (AK#1828)."""
    return tuple(v for v in analysis.views if isinstance(v, MetricPlot))


def reference_matches(
    name: str, *, state: State | None, design: str | None, label: str
) -> bool:
    """Whether a cell is the one a `MetricPlot`'s ``relative_to`` names: by
    its state's name or label, its design (as a designs cross or a state
    names it, with or without its variant), or its whole label."""
    if name == label:
        return True
    if state is not None and name in (state.name, state.label):
        return True
    return design is not None and name in (design, design.partition(":")[0])


def _cell_names(analysis: Analysis) -> list[tuple]:
    """``(state, design, label)`` for every value a reference can name: each
    listed cell, each state, each design of a designs cross."""
    cells = cells_of(analysis)
    if cells:
        return [(c.state, c.state.spec if c.state else None, c.label) for c in cells]
    out = []
    for c in analysis.crosses:
        if c.kind == "states":
            out += [(st, st.spec, st.label) for st in c.states]
        elif c.kind == "designs":
            out += [(None, d, d) for d in c.designs]
    return out


def _metric_problems(analysis: Analysis) -> list[str]:
    """A `MetricPlot` whose ``relative_to`` names no cell of the analysis,
    or names more than one on the axis it picks from (AK#1828)."""
    out = []
    names = _cell_names(analysis)
    for v in metric_plots(analysis):
        if v.relative_to is None:
            continue
        hits = [
            label
            for st, d, label in names
            if reference_matches(v.relative_to, state=st, design=d, label=label)
        ]
        if not hits:
            out.append(
                f"REFUSED: the MetricPlot of {v.metric.name!r} is relative to "
                f"{v.relative_to!r}, and no state, design or cell of the "
                "analysis is named that"
            )
        elif len(hits) > 1:
            out.append(
                f"REFUSED: the MetricPlot of {v.metric.name!r} is relative to "
                f"{v.relative_to!r}, which names {len(hits)} cells "
                f"({', '.join(repr(h) for h in hits)}); name one by its label"
            )
    return out


def _shape_refusal(k: str, value, default) -> str | None:
    """Why ``value`` does not fit knob ``k`` whose default is ``default``, or
    None (unit 4). A group knob (a tuple of entries, fan_dipole's ``bands``)
    takes a tuple of entries with exactly the group's leaves, at most as many
    as the design's own tuple holds (the group's ``max_repeats``: the
    workbench preallocates that many); a scalar knob takes a scalar. The
    builder would take either shape without a word and fail, or quietly
    misread it, deep inside the geometry, so the shape is refused here, by
    name."""
    group = isinstance(default, (tuple, list))
    if not isinstance(value, tuple):
        if group:
            return (
                f"{k} to {value!r}, and {k} is a group knob: give a tuple of its "
                "entries"
            )
        return None
    if not group:
        return f"{k} to a tuple, and {k} is a single value, not a group knob"
    if len(value) > len(default):
        return (
            f"{k} to {len(value)} entries, and the design's {k} holds at most "
            f"{len(default)}"
        )
    first = default[0] if default else None
    if isinstance(first, Mapping):
        want = list(first)
        for i, e in enumerate(value, start=1):
            if not isinstance(e, Mapping):
                return (
                    f"{k} entry {i} to {e!r}; each entry is a dict of {', '.join(want)}"
                )
            if sorted(e) != sorted(want):
                return (
                    f"{k} entry {i} with the leaves {', '.join(e)}; the group's "
                    f"leaves are {', '.join(want)}"
                )
    elif any(isinstance(e, Entry) for e in value):
        return f"{k} to entries of leaves, and {k} is a tuple of plain values"
    return None


def _states_problems(analysis: Analysis, builder) -> list[str]:
    """The states' own refusals (`problems`): a named design re-multiplied by
    a ``designs=`` cross, and, for the states set on ``builder`` itself,
    `state_refusal`. A state on another design (its ``design=``, or a design
    of a ``designs=`` cross) is refused per cell, when that design is built
    (`analysis_run._prepare`, the workbench's ``/analyses``)."""
    states = states_of(analysis)
    if not states:
        return []
    named = [s for s in states if s.design is not None]
    if named and crosses_designs(analysis):
        # Two readings, neither safe: a named state as its own cell (then
        # the product is not a product), or its design crossed again with
        # every design of the cross (then "apex, tall" is also drawn on the
        # invvee). Refused, so the spec says which it means.
        return [
            f"REFUSED: the states {', '.join(repr(s.label) for s in named)} name "
            "their design, and the analysis also crosses designs=, which would "
            "multiply them again; give every state its design= and drop the "
            "designs cross, or drop design= and let the cross carry the designs"
        ]
    if crosses_designs(analysis):
        return []
    return [
        f"REFUSED: {why}"
        for s in states
        if s.design is None
        and (
            why := state_refusal(s, analysis, builder, fixed=is_reference(s, analysis))
        )
    ]


def is_reference(state: State, analysis: Analysis) -> bool:
    """Whether ``state`` is a cell some `MetricPlot` of ``analysis`` is drawn
    relative to (AK#1828): then a knob it sets is its own, even one the
    sweep moves (a fixed reference, solved once)."""
    return any(
        v.relative_to is not None
        and reference_matches(
            v.relative_to, state=state, design=state.spec, label=state.label
        )
        for v in metric_plots(analysis)
    )


def problems(analysis: Analysis, builder) -> list[str]:
    """Why ``analysis`` cannot run on ``builder``, as listed: an unresolved
    sweep (UNAVAILABLE), a product over `CURVE_CAP`, a cross naming one
    value twice, and a knob both swept and stepped. Empty: it can."""
    out = []
    same = sum(1 for a in builder.build_analyses() if a.name == analysis.name)
    if same > 1:
        # Names pick one analysis (`analyze --analysis NAME`); two alike is
        # a spec to fix, not a choice to make silently (Steve, 2026-09-28).
        # A library analysis of the same name is not counted: a design's
        # own one replaces it on purpose (`offered`).
        out.append(
            f"REFUSED: {same} analyses are named {analysis.name!r}; give one "
            f'a name= (e.g. an.convergence(name="…", …))'
        )
    for s in analysis.sweeps:
        r = resolve(s.knob, builder)
        if r.knob is None:
            out.append(f"UNAVAILABLE: {r.reason}")
        elif (
            s.spacing == "lin" and s.knob != DENSITY and r.knob == density_knob(builder)
        ):
            out.append(
                f"REFUSED: {r.knob} plays the density role, whose ladder is "
                "geometric; drop spacing='lin'"
            )
    swept = [resolve(s.knob, builder).knob for s in analysis.sweeps]
    if len(swept) == 2 and swept[0] is not None and swept[0] == swept[1]:
        out.append(f"REFUSED: the map sweeps {swept[0]} on both axes")
    for c in analysis.crosses:
        # A curve is found by its label, which is the value that makes it:
        # a value named twice is two curves drawn over each other as one.
        if c.step is not None:
            values = c.step.values or ()
        elif c.kind == "states":
            # A state is found by its label (its design and name), whatever
            # knobs it sets: two alike are one legend entry for two curves.
            values = tuple(s.label for s in c.states)
        elif c.kind == "cells":
            # A listed cell too (unit 4): its label is everything it sets, so
            # two alike are the same cell listed twice, or two cells the
            # legend could not tell apart.
            values = tuple(cell.label or "(the analysis's own)" for cell in c.cells)
        else:
            values = getattr(c, c.kind)
        twice = sorted({v for v in values if values.count(v) > 1}, key=str)
        if twice:
            out.append(
                f"REFUSED: the cross over {c.kind} names "
                f"{', '.join(repr(v) for v in twice)} twice"
            )
        if c.step is not None:
            r = resolve(c.step.knob, builder)
            if r.knob is None:
                out.append(f"UNAVAILABLE: {r.reason}")
            elif r.knob in swept:
                out.append(
                    f"REFUSED: the family steps {r.knob}, which is the swept knob"
                )
    if analysis.hold is not None:
        for k in analysis.hold.adjust:
            r = resolve(k, builder)
            if r.knob is None:
                out.append(f"UNAVAILABLE: {r.reason}")
            elif r.knob in swept:
                # A role and a name can meet only once they resolve.
                out.append(
                    f"REFUSED: the hold adjusts {r.knob}, which is the swept knob"
                )
    out += _states_problems(analysis, builder)
    out += _metric_problems(analysis)
    if analysis.curves > CURVE_CAP:
        sizes = " x ".join(
            f"{c.size} {'values' if c.kind == 'step' else c.kind}"
            for c in analysis.crosses
        )
        out.append(
            f"REFUSED: {sizes} = {analysis.curves} curves, over the cap of {CURVE_CAP}"
        )
    return out


# ── printing back as code ────────────────────────────────────────────────────

_WIDTH = 88


def _node(value):
    """``value`` as a render tree: a str leaf, or ``(head, open, close,
    [(prefix, node), ...], single)``, a prefix being ``"key="`` for a
    keyword argument, ``'"key": '`` for a dict entry, or "" positionally."""
    if isinstance(value, Role):
        name = _ROLE_CONSTANTS.get(value)
        return f"an.{name}" if name else f"an.Role({json.dumps(value.name)})"
    if isinstance(value, AzMode):
        return f"an.{_AZ_CONSTANTS[value]}"
    if isinstance(value, Metric):
        # The function by reference (AK#1828): ``module.qualname``, its
        # import listed by `imports`; one that cannot be imported by name (a
        # user design's or study's) as its bare name, which a keep says to
        # copy into the file (`keep.render`).
        call = _call("an.Metric", value, _METRIC_DEFAULTS, skip=("fn",))
        fn = value.ref if importable(value.fn) else value.fn.__qualname__
        args = list(call[3])
        args.insert(1, ("", fn))
        return (call[0], call[1], call[2], args, False)
    if isinstance(value, bool) or value is None:
        return repr(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, int):
        return repr(int(value))
    if isinstance(value, float):
        return repr(float(value))
    if isinstance(value, tuple):
        items = [("", _node(v)) for v in value]
        return ("", "(", ")", items, len(items) == 1)
    if isinstance(value, Mapping):
        # A group knob's entry (`Entry`): the dict literal it was written as.
        items = [
            (f"{json.dumps(k, ensure_ascii=False)}: ", _node(v))
            for k, v in value.items()
        ]
        return ("", "{", "}", items, False)
    if isinstance(value, State):
        # Its own form: the knobs are keyword arguments of their own, not a
        # field (`State.__init__`), in the order written.
        items = [("", _node(value.name))]
        if value.design is not None:
            items.append(("design=", _node(value.design)))
        if value.variant is not None:
            items.append(("variant=", _node(value.variant)))
        items += [(f"{k}=", _node(v)) for k, v in value.knobs]
        return ("an.State", "(", ")", items, False)
    if dataclasses.is_dataclass(value) and type(value).__module__ == __name__:
        return _call(f"an.{type(value).__name__}", value, _defaults(type(value)))
    raise TypeError(f"no code form for {value!r}")


def _defaults(cls) -> dict:
    return {
        f.name: f.default
        for f in dataclasses.fields(cls)
        if f.default is not dataclasses.MISSING
    }


# `Metric` takes its options by keyword in a constructor of its own, so the
# dataclass fields carry no defaults: these are the constructor's.
_METRIC_DEFAULTS = {
    "over": "elevation",
    "step": 1.0,
    "az": None,
    "el": None,
    "lo": None,
    "hi": None,
    "unit": "dBi",
}


def metrics_of(value) -> list[Metric]:
    """Every callable `Metric` inside ``value`` (an analysis, a view, a
    metric), in the order met."""
    out: list[Metric] = []

    def walk(v):
        if isinstance(v, Metric):
            if v not in out:
                out.append(v)
        elif isinstance(v, tuple):
            for x in v:
                walk(x)
        elif dataclasses.is_dataclass(v) and not isinstance(v, type):
            for f in dataclasses.fields(v):
                walk(getattr(v, f.name))

    walk(value)
    return out


def imports(value) -> list[str]:
    """The import lines `to_code`'s text of ``value`` needs beyond ``an``:
    one per module a callable metric's function is written from (AK#1828),
    sorted. A function that cannot be imported by name needs none: its
    bare name is written, and it must be copied in."""
    return sorted(
        {f"import {m.fn.__module__}" for m in metrics_of(value) if importable(m.fn)}
    )


def code_with_imports(value, indent: int = 0) -> str:
    """`to_code` of ``value`` after the imports it needs (`imports`), as the
    analysis panel and ``analyze --code`` print it: paste-ready."""
    head = imports(value)
    code = to_code(value, indent)
    return "\n".join([*head, "", code]) if head else code


def _call(head: str, value, defaults: Mapping, positional=None, skip=()):
    """A constructor call: fields equal to ``defaults`` are left out; the
    class's leading positional fields print positionally while unbroken."""
    positional = positional if positional is not None else value._positional
    args = []
    as_kw = False
    for f in dataclasses.fields(value):
        if f.name in skip:
            continue
        v = getattr(value, f.name)
        if f.name in defaults and v == defaults[f.name]:
            as_kw = True
            continue
        if f.name in positional and not as_kw:
            args.append(("", _node(v)))
        else:
            as_kw = True
            args.append((f"{f.name}=", _node(v)))
    return (head, "(", ")", args, False)


def _render(node, indent: int = 0) -> str:
    if isinstance(node, str):
        return node
    head, open_, close, items, single = node
    parts = [k + _render(v, indent + 4) for k, v in items]
    flat = head + open_ + ", ".join(parts) + ("," if single else "") + close
    if "\n" not in flat and indent + len(flat) <= _WIDTH:
        return flat
    pad = " " * (indent + 4)
    body = "".join(f"{pad}{p},\n" for p in parts)
    return f"{head}{open_}\n{body}{' ' * indent}{close}"


def to_code(value, indent: int = 0) -> str:
    """``value`` as the Python that constructs it, ``an`` being this module.
    An `Analysis` prints as whichever of ``an.Analysis(...)`` or a library
    call (``an.convergence(...)``, ``an.band_swr(...)``, ``an.patterns(...)``,
    ``an.knob(...)``) is shortest: each passes only what differs from its own
    defaults, so ``eval`` of any of them is the same value. ``indent`` is the
    column the text starts at (a study file's list, unit 4): its lines are
    wrapped to fit the width from there."""
    if not isinstance(value, Analysis):
        return _render(_node(value), indent)
    # A pattern's sweep is None, which reads as nothing positionally: it is
    # printed by name, as the spec spells it (``sweep=None``).
    positional = ("name",) if value.sweep is None else None
    forms = [_call("an.Analysis", value, _defaults(Analysis), positional=positional)]
    for fn in (convergence, band_swr, patterns):
        base = fn()
        forms.append(_call(f"an.{fn.__name__}", value, _fields(base), positional=()))
    base = knob(value.name)
    k = _call("an.knob", value, _fields(base), positional=(), skip=("name",))
    forms.append((k[0], k[1], k[2], [("", _node(value.name)), *k[3]], False))
    texts = [_render(f, indent) for f in forms]
    return min(texts, key=len)


def _fields(a: Analysis) -> dict:
    return {f.name: getattr(a, f.name) for f in dataclasses.fields(a)}


# ── as data (AK#1757 step 7, unit 4) ─────────────────────────────────────────
#
# The workbench keeps what it built by sending the spec back as JSON: it edits
# the analysis ``/analyses`` served (`to_data`) or builds one from its pins,
# and the server rebuilds the VALUE (`from_data`) and prints it (`to_code`).
# So the file the workbench saves is always ``to_code`` of a spec value, never
# text the page sent: `from_data` constructs only this module's own classes,
# through their own constructors (every refusal they make applies), from
# strings, numbers, booleans and None. That is what lets the saved file be
# trusted as written (design note, ruling 4).

#: The classes `from_data` may construct, by the name `to_data` writes.
_DATA_CLASSES = {
    c.__name__: c
    for c in (
        Analysis,
        Sweep,
        Cross,
        Cell,
        State,
        Ref,
        Hold,
        Role,
        Rx,
        Swr,
        S11,
        Smith,
        Map,
        Table,
        Knobs,
        Elevation,
        Azimuth,
        PatternTable,
        MetricPlot,
        AzMode,
        ElevationWindow,
        GainAt,
        PeakGain,
        TakeOff,
        PeakAzimuth,
        FrontToBack,
        AzBeamwidth,
        ElBeamwidth,
        Rdf,
        Metric,
    )
}


def to_data(value):
    """``value`` as JSON-ready data: a spec value as ``{"an": <class>,
    <field>: ...}``, a `State` with its knobs as ``[[name, value], ...]`` (in
    the order written; a group's entries as dicts), a tuple as a list.
    `from_data` reads it back to an equal value."""
    if isinstance(value, Role):
        return {"an": "Role", "name": value.name}
    if isinstance(value, Metric):
        # The function by reference only: `from_data` resolves it through
        # the functions its caller says it served, never by importing.
        out = {"an": "Metric", "name": value.name, "fn": value.ref}
        for k in _METRIC_DEFAULTS:
            out[k] = to_data(getattr(value, k))
        return out
    if isinstance(value, State):
        return {
            "an": "State",
            "name": value.name,
            "design": value.design,
            "variant": value.variant,
            "knobs": [[k, _plain_data(v)] for k, v in value.knobs],
        }
    if isinstance(value, tuple):
        return [to_data(v) for v in value]
    if dataclasses.is_dataclass(value) and type(value).__module__ == __name__:
        out = {"an": type(value).__name__}
        for f in dataclasses.fields(value):
            out[f.name] = to_data(getattr(value, f.name))
        return out
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    raise TypeError(f"no data form for {value!r}")


def _plain_data(v):
    if isinstance(v, tuple):
        return [dict(e) if isinstance(e, Mapping) else e for e in v]
    return v


def _knob_data(v):
    """A state's knob value from data: a list is a group's tuple (its
    entries dicts, which `State` validates); anything else as given."""
    if isinstance(v, list):
        return tuple(dict(e) if isinstance(e, dict) else e for e in v)
    return v


def from_data(data, functions: Mapping | None = None):
    """The spec value `to_data` wrote (module comment above): a ValueError or
    TypeError, by name, for anything that is not one.

    A callable `Metric`'s function is data as its reference
    (``module.qualname``), and is resolved ONLY through ``functions``, the
    caller's map of the references it served (the workbench's: the functions
    of the analyses ``/analyses`` listed): never by importing what the data
    names. So data can name only a function this process already offered
    from a file it trusts, and a reference it did not is refused by name."""
    if isinstance(data, list):
        return tuple(from_data(v, functions) for v in data)
    if not isinstance(data, dict):
        if data is None or isinstance(data, (bool, int, float, str)):
            return data
        raise TypeError(f"spec data: no value of type {type(data).__name__}")
    kind = data.get("an")
    cls = _DATA_CLASSES.get(kind) if isinstance(kind, str) else None
    if cls is None:
        raise ValueError(f"spec data: {kind!r} is not a spec value (an.{kind})")
    fields = {k: v for k, v in data.items() if k != "an"}
    if cls is Role:
        if set(fields) != {"name"}:
            raise ValueError("spec data: a Role has one field, name")
        return Role(fields["name"])
    if cls is Metric:
        extra = set(fields) - {"name", "fn", *_METRIC_DEFAULTS}
        if extra:
            raise ValueError(f"spec data: Metric has no field {sorted(extra)[0]!r}")
        ref = fields.get("fn")
        fn = (functions or {}).get(ref) if isinstance(ref, str) else None
        if fn is None:
            raise ValueError(
                f"spec data: the metric {fields.get('name')!r} calls {ref!r}, "
                "which is not a function this workbench served; a callable "
                "metric comes from a design or study file, never from data"
            )
        return Metric(
            fields.get("name"),
            fn,
            **{
                k: from_data(fields[k], functions)
                for k in _METRIC_DEFAULTS
                if k in fields
            },
        )
    if cls is State:
        extra = set(fields) - {"name", "design", "variant", "knobs"}
        if extra:
            raise ValueError(f"spec data: State has no field {sorted(extra)[0]!r}")
        knobs = fields.get("knobs") or []
        if not isinstance(knobs, list) or not all(
            isinstance(kv, list) and len(kv) == 2 and isinstance(kv[0], str)
            for kv in knobs
        ):
            raise ValueError("spec data: a State's knobs are [[name, value], ...]")
        names = [k for k, _ in knobs]
        if len(set(names)) != len(names):
            raise ValueError("spec data: a State sets a knob twice")
        reserved = [k for k in names if k in ("name", "design", "variant")]
        if reserved:
            raise ValueError(f"spec data: {reserved[0]!r} is not a knob name")
        return State(
            fields.get("name"),
            fields.get("design"),
            variant=fields.get("variant"),
            **{k: _knob_data(v) for k, v in knobs},
        )
    names = {f.name for f in dataclasses.fields(cls)}
    extra = set(fields) - names
    if extra:
        raise ValueError(f"spec data: an.{kind} has no field {sorted(extra)[0]!r}")
    return cls(**{k: from_data(v, functions) for k, v in fields.items()})

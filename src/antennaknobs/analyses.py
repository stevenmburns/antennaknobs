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
- an optional `Hold` optimises at every sweep point: the knobs it adjusts
  are re-solved for one of the optimizer's objectives as x moves;
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
    gain, take-off angle, azimuth, F/B, both beamwidths, RDF)."""


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
    ``engine`` None is the session's own."""

    name: str
    sweep: Sweep | tuple[Sweep, Sweep] | None
    cross: Cross | tuple[Cross, ...] = ()
    views: tuple[View, ...] = (Rx(),)
    references: Ref = Ref()
    ground: str | None = None
    engine: str | None = None
    hold: Hold | None = None

    _positional: ClassVar[tuple[str, ...]] = ("name", "sweep")

    def __post_init__(self):
        if not isinstance(self.name, str) or not self.name:
            raise TypeError(f"Analysis: name is a non-empty string, got {self.name!r}")
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
    shadows a generic one of the same name."""
    own = tuple(builder.build_analyses())
    names = {a.name for a in own}
    generic = [convergence(), band_swr()]
    if resolve(HEIGHT, builder).knob is not None:
        generic.append(Analysis("height", Sweep(HEIGHT)))
    return own + tuple(a for a in generic if a.name not in names)


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


def state_refusal(state: State, analysis: Analysis, builder) -> str | None:
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
    (state, design) pair, not of the spec alone."""
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
        if s.design is None and (why := state_refusal(s, analysis, builder))
    ]


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
    )
}


def to_data(value):
    """``value`` as JSON-ready data: a spec value as ``{"an": <class>,
    <field>: ...}``, a `State` with its knobs as ``[[name, value], ...]`` (in
    the order written; a group's entries as dicts), a tuple as a list.
    `from_data` reads it back to an equal value."""
    if isinstance(value, Role):
        return {"an": "Role", "name": value.name}
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


def from_data(data):
    """The spec value `to_data` wrote (module comment above): a ValueError or
    TypeError, by name, for anything that is not one."""
    if isinstance(data, list):
        return tuple(from_data(v) for v in data)
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
    return cls(**{k: from_data(v) for k, v in fields.items()})

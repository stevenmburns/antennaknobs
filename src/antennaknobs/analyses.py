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
- an optional `Hold` optimises at every sweep point: the knobs it adjusts
  are re-solved for one of the optimizer's objectives as x moves;
- `convergence`, `band_swr` and `knob` are the library: generic analyses any
  design composes. `offered` is a design's own list plus the library's
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
import math
from collections.abc import Mapping
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
    the density ladder); ``values`` replaces the range."""

    knob: str | Role
    lo: float | None = None
    hi: float | None = None
    points: int | None = None
    values: tuple[float, ...] | None = None
    spacing: str = "lin"

    _positional: ClassVar[tuple[str, ...]] = ("knob", "lo", "hi")

    def __post_init__(self):
        if not isinstance(self.knob, Role) and not (
            isinstance(self.knob, str) and self.knob
        ):
            raise TypeError(f"Sweep: knob is a knob name or a role, got {self.knob!r}")
        if self.spacing not in ("lin", "log"):
            raise ValueError(f"Sweep: spacing is 'lin' or 'log', got {self.spacing!r}")
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


_CROSS_KINDS = ("engines", "grounds", "planes", "designs", "step")


@dataclass(frozen=True)
class Cross:
    """The curves compared: exactly one of engine specs (as ``--engine``
    takes them), ground specs (as ``--ground`` takes them), measurement
    planes, designs, or a second knob's values (``step``, a family)."""

    engines: tuple[str, ...] = ()
    grounds: tuple[str, ...] = ()
    planes: tuple[str, ...] = ()
    designs: tuple[str, ...] = ()
    step: Sweep | None = None

    _positional: ClassVar[tuple[str, ...]] = ()

    def __post_init__(self):
        for f in _CROSS_KINDS[:-1]:
            _set(self, f, _as_tuple(getattr(self, f), f"Cross {f}"))
        if self.step is not None and not isinstance(self.step, Sweep):
            raise TypeError(f"Cross: step is a Sweep, got {self.step!r}")
        given = [f for f in _CROSS_KINDS if getattr(self, f)]
        if len(given) != 1:
            raise ValueError(
                "Cross: give exactly one of engines, grounds, planes, designs or "
                f"step (got {', '.join(given) or 'none'}); several Cross values "
                "multiply"
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
    """A two-sweep map (the sweep is a pair)."""


@dataclass(frozen=True)
class Table(View):
    """The numbers, printed."""


@dataclass(frozen=True)
class Knobs(View):
    """The held knobs' values against the swept value (a `Hold`'s
    solution at each point)."""


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
    """One analysis. ``sweep`` is a `Sweep`, or a pair of them for a map;
    ``cross`` a `Cross` or a tuple of them (their product); ``ground`` /
    ``engine`` None is the session's own."""

    name: str
    sweep: Sweep | tuple[Sweep, Sweep]
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
        sweeps = self.sweep if isinstance(self.sweep, tuple) else (self.sweep,)
        if not 1 <= len(sweeps) <= 2 or not all(isinstance(s, Sweep) for s in sweeps):
            raise TypeError(
                f"Analysis {self.name!r}: sweep is a Sweep or a pair of them"
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
        # One Cross is stored bare, as written: it prints back the same way.
        _set(self, "cross", cross[0] if len(cross) == 1 else cross)
        views = (self.views,) if isinstance(self.views, View) else self.views
        views = _as_tuple(views, f"Analysis {self.name!r} views")
        if not views or not all(isinstance(v, View) for v in views):
            raise TypeError(
                f"Analysis {self.name!r}: views holds view objects (an.Rx(), ...)"
            )
        _set(self, "views", views)
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

    @property
    def crosses(self) -> tuple[Cross, ...]:
        return (self.cross,) if isinstance(self.cross, Cross) else self.cross

    @property
    def sweeps(self) -> tuple[Sweep, ...]:
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


def problems(analysis: Analysis, builder) -> list[str]:
    """Why ``analysis`` cannot run on ``builder``, as listed: an unresolved
    sweep (UNAVAILABLE) and a product over `CURVE_CAP`. Empty: it can."""
    out = []
    for s in analysis.sweeps:
        r = resolve(s.knob, builder)
        if r.knob is None:
            out.append(f"UNAVAILABLE: {r.reason}")
    for c in analysis.crosses:
        if c.step is not None:
            r = resolve(c.step.knob, builder)
            if r.knob is None:
                out.append(f"UNAVAILABLE: {r.reason}")
    if analysis.hold is not None:
        swept = {resolve(s.knob, builder).knob for s in analysis.sweeps}
        for k in analysis.hold.adjust:
            r = resolve(k, builder)
            if r.knob is None:
                out.append(f"UNAVAILABLE: {r.reason}")
            elif r.knob in swept:
                # A role and a name can meet only once they resolve.
                out.append(
                    f"REFUSED: the hold adjusts {r.knob}, which is the swept knob"
                )
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
    [(key, node), ...])``."""
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
        items = [(None, _node(v)) for v in value]
        return ("", "(", ")", items, len(items) == 1)
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
            args.append((None, _node(v)))
        else:
            as_kw = True
            args.append((f.name, _node(v)))
    return (head, "(", ")", args, False)


def _render(node, indent: int = 0) -> str:
    if isinstance(node, str):
        return node
    head, open_, close, items, single = node
    parts = [(f"{k}=" if k else "") + _render(v, indent + 4) for k, v in items]
    flat = head + open_ + ", ".join(parts) + ("," if single else "") + close
    if "\n" not in flat and indent + len(flat) <= _WIDTH:
        return flat
    pad = " " * (indent + 4)
    body = "".join(f"{pad}{p},\n" for p in parts)
    return f"{head}{open_}\n{body}{' ' * indent}{close}"


def to_code(value) -> str:
    """``value`` as the Python that constructs it, ``an`` being this module.
    An `Analysis` prints as whichever of ``an.Analysis(...)`` or a library
    call (``an.convergence(...)``, ``an.band_swr(...)``, ``an.knob(...)``)
    is shortest: each passes only what differs from its own defaults, so
    ``eval`` of any of them is the same value."""
    if not isinstance(value, Analysis):
        return _render(_node(value))
    forms = [_call("an.Analysis", value, _defaults(Analysis))]
    for fn in (convergence, band_swr):
        base = fn()
        forms.append(_call(f"an.{fn.__name__}", value, _fields(base), positional=()))
    base = knob(value.name)
    k = _call("an.knob", value, _fields(base), positional=(), skip=("name",))
    forms.append((k[0], k[1], k[2], [(None, _node(value.name)), *k[3]], False))
    texts = [_render(f) for f in forms]
    return min(texts, key=len)


def _fields(a: Analysis) -> dict:
    return {f.name: getattr(a, f.name) for f in dataclasses.fields(a)}

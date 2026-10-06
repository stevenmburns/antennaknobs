"""Keeping what you built: "copy as analysis" and "keep as study" (AK#1757,
sweep-framework step 7, unit 4; docs/design/sweep-framework-step7.md § 4,
rulings 1 and 4, and the ``cells=`` ruling).

The workbench never saves a format of its own: it writes Python, the only
thing that persists (the step-5 ruling). What it sends is DATA, and this
module builds a spec VALUE from it and prints that (`analyses.to_code`), so a
kept study is always ``to_code`` of an `an.Analysis`, never text the page
sent. That is why ruling 4 can save it trusted: "a file the app wrote from
the user's own chart" is not a stranger's ``.py``.

Three things can be kept (`build`):

- **a chart** (``origin="chart"``): the analysis ``/analyses`` served, as
  data (`analyses.to_data`), with what the chart changed on it: the engines
  and grounds it draws (read off its curves' solve requests), and the x
  values when the viewer edited the range, and a map's edited axes
  (``axes``), each written as a range. A knob chart showing a pattern
  family (AK#1935) has no analysis to send: it sends ``family``, the knob
  and range it drew, kept as ``an.patterns(cross=an.Cross(step=...))``.
  "Copy as analysis" is its ``to_code`` alone, to paste into the design's
  ``build_analyses()``, and is only for a chart about the tab's design. "Keep
  as study" also names the tab's design, since a study has no "this design"
  (`_as_study`): the tab's knobs, where they differ from its variant's
  defaults, become a state.
- **sweep pins** and **pattern pins** (``origin="sweep pins"`` / ``"pattern
  pins"``): each pin carries the solve request its curve was solved with,
  and that request is the whole of what it says. A pin becomes one CELL
  (`pin_cell`): its design and variant, the knobs that differ from that
  variant's defaults, its engine and ground in the CLI's ``--engine`` /
  ``--ground`` spelling (`engine_of`, `ground_of`), and its plane. The cells are written as a plain
  cross when they are a product, and as ``cells=`` when they are not
  (`analysis_from_pins`, the ruling).

and then written (`render`) as the analysis alone, or as a study file: a
header saying what wrote it, the notes, and a module-level ``build_studies()``.
`save` writes that file under the studies folder and records it trusted with
edits allowed (the ``allow --edits`` state).
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as _dt
import itertools
import math
import re
from collections.abc import Callable, Mapping
from pathlib import Path

from . import analyses as an
from . import studies

#: What each keep was made from, in the header's words.
ORIGINS = {
    "chart": "your own analysis chart",
    "sweep pins": "your own pinned sweeps",
    "pattern pins": "your own pinned patterns",
    "optimize": "your own multi-band optimize run",
}

FORMS = ("analysis", "study")

#: What a sweep pin sweeps, as the page names it (lib/sweepPins.ts PinXKind).
_X_KINDS = ("frequency", "knob", "density")

# One name part of a study file's path: a plain name, as `studies._user_source`
# requires (no '.', which is the catalog's family.design; no ':', which splits
# a study's source from its name), not starting with '_' or '.' (discovery
# skips those as private, so the file would never be listed), and nothing a
# shell or another OS reads specially.
_PART = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")
_MAX_DEPTH = 8

# An engine spec as ``--engine`` spells one (``momwire:bspline-d1``). A kept
# spec is checked against this before it is written into a file; whether the
# engine is on this machine is the run's question, not the keep's.
_ENGINE = re.compile(r"[a-z][a-z0-9]*(:[a-z0-9][a-z0-9-]*)?")


class KeepError(ValueError):
    """A keep that cannot be made, in words for the page."""


class StudyExists(KeepError):
    """The study file is there already, and the request did not say to
    replace it."""


def _fields(a: an.Analysis) -> dict:
    return {f.name: getattr(a, f.name) for f in dataclasses.fields(a)}


def _analysis(**fields) -> an.Analysis:
    """An `an.Analysis`, its constructor's refusal a `KeepError`."""
    try:
        return an.Analysis(**fields)
    except (TypeError, ValueError) as e:
        raise KeepError(str(e)) from None


def analysis_of(data) -> an.Analysis:
    """The `an.Analysis` ``data`` describes (`analyses.from_data`), or a
    `KeepError` in the constructor's own words. A callable metric's function
    is resolved only through the functions the workbench served (AK#1828,
    `analyses_offer.SERVED_FUNCTIONS`): a kept file names no function the
    workbench did not offer from a file it trusts."""
    from .web.analyses_offer import SERVED_FUNCTIONS

    try:
        value = an.from_data(data, SERVED_FUNCTIONS)
    except (TypeError, ValueError) as e:
        raise KeepError(str(e)) from None
    if not isinstance(value, an.Analysis):
        raise KeepError("the spec is not an an.Analysis")
    return value


def _named(a: an.Analysis, name) -> an.Analysis:
    """``a`` under the name the viewer typed, or its own."""
    if name is None or (isinstance(name, str) and not name.strip()):
        return a
    if not isinstance(name, str):
        raise KeepError("name is a string")
    return _analysis(**{**_fields(a), "name": name.strip()})


# ── a design and its knobs, from a solve request ────────────────────────────


def _builder_cls(design: str):
    from .web.examples import UnknownGeometryError, example_for

    try:
        cls = getattr(example_for(design), "builder_cls", None)
    except UnknownGeometryError as e:
        raise KeepError(str(e)) from None
    if cls is None:
        raise KeepError(f"{design!r} has no builder to keep")
    return cls


def _variant(cls, design: str, variant) -> str | None:
    """The request's variant as a state writes it: None for the default."""
    if variant in (None, "", "default"):
        return None
    if not isinstance(variant, str):
        raise KeepError(f"{design}: variant is a string, got {variant!r}")
    from .web.analyses_offer import _has_variant

    if not _has_variant(cls, variant):
        raise KeepError(f"{design} has no variant {variant!r}")
    return variant


def _plain(v):
    """A knob value as a state holds it: a group (a list or tuple of
    entries) as a tuple of dicts, anything else as it is."""
    if isinstance(v, (list, tuple)):
        return tuple(dict(e) if isinstance(e, Mapping) else e for e in v)
    return v


def _same(a, b) -> bool:
    """Equal as knob values: a group entry by entry, a number EXACTLY (a pin
    is a solve, bit for bit), an int and the float it equals alike, a bool
    only as a bool."""
    a, b = _plain(a), _plain(b)
    if isinstance(a, tuple) or isinstance(b, tuple):
        return (
            isinstance(a, tuple)
            and isinstance(b, tuple)
            and len(a) == len(b)
            and all(_same(x, y) for x, y in zip(a, b, strict=True))
        )
    if isinstance(a, Mapping) or isinstance(b, Mapping):
        return (
            isinstance(a, Mapping)
            and isinstance(b, Mapping)
            and set(a) == set(b)
            and all(_same(a[k], b[k]) for k in a)
        )
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b
    return a == b


def _solved_builder(cls, req: Mapping):
    """The builder the server solved ``req`` on: its variant's params and
    the request's knobs (`analyses_offer.builder_for`), then the two
    frequencies the request carries in fields of their own, set as every
    solve sets them (`adapter.momwire_solve`: ``freq`` is the measurement
    frequency, ``design_freq`` the design frequency)."""
    from .web.analyses_offer import builder_for

    try:
        b = builder_for(cls, req)
    except (TypeError, ValueError) as e:
        raise KeepError(str(e)) from None
    params = an._params(b)
    for field, knob in (
        ("measurement_freq_mhz", "freq"),
        ("design_freq_mhz", "design_freq"),
    ):
        v = req.get(field)
        if knob in params and isinstance(v, (int, float)) and not isinstance(v, bool):
            setattr(b, knob, float(v))
    return b


def changed_knobs(req: Mapping, skip=()) -> tuple[str, str | None, list]:
    """``(design, variant, knobs)`` for the solve request ``req``: its
    design, its variant (None for the default) and every knob whose value
    differs from that variant's defaults, in the design's own order, as
    ``(name, value)`` pairs of plain data. Never the density knob (a run's
    density is the run's own, ``--nominal-nsegs``), nor a knob in ``skip``
    (what the analysis moves)."""
    design = req.get("geometry")
    if not isinstance(design, str) or not design:
        raise KeepError("the request names no design (geometry)")
    cls = _builder_cls(design)
    variant = _variant(cls, design, req.get("variant"))
    solved = _solved_builder(cls, req)
    base = _solved_builder(cls, {"geometry": design, "variant": variant or "default"})
    dens = an.density_knob(base)
    got = an._params(solved)
    out = []
    for k, v0 in an._params(base).items():
        if k in ("ui_params", "nominal_nsegs") or k == dens or k in skip:
            continue
        v = got.get(k, v0)
        if not _same(v, v0):
            out.append((k, _plain(v)))
    return design, variant, out


def _fmt(v) -> str:
    if isinstance(v, float):
        return str(int(v)) if v.is_integer() else repr(v)
    return str(v)


def state_name(knobs) -> str:
    """A state's name from its knobs: "as built" at the defaults, else each
    knob and its value ("base 12, angle_deg 20"); a group knob by its name
    ("bands set"), since its value has no one-word form."""
    parts = [f"{k} set" if isinstance(v, tuple) else f"{k} {_fmt(v)}" for k, v in knobs]
    return ", ".join(parts) or "as built"


def _state(
    design: str, variant: str | None, knobs, name: str | None = None
) -> an.State:
    reserved = [k for k, _ in knobs if k in ("name", "design", "variant")]
    if reserved:
        raise KeepError(
            f"{design}: the knob {reserved[0]!r} cannot be written as a state's "
            "keyword argument"
        )
    try:
        return an.State(
            name or state_name(knobs), design, variant=variant, **dict(knobs)
        )
    except (TypeError, ValueError) as e:
        raise KeepError(str(e)) from None


# ── pins ─────────────────────────────────────────────────────────────────────


#: The CLI's default soil (``cli.parse_ground`` and the server's
#: ``DEFAULT_GROUND``): a finite ground on it is written without constants.
_CLI_SOIL = (13.0, 0.005)

#: The request's ground model as the CLI's ``--ground`` kind.
_GROUND_KINDS = {"fast": "finite-fast", "sommerfeld": "finite", "mininec": "mininec"}


def engine_of(req: Mapping, who: str, notes: list[str] | None = None) -> str:
    """The ``--engine`` spec the solve request ``req`` was solved on: its
    ``solver``, and for momwire its model (a B-spline at degree 1 is
    ``bspline-d1``, the CLI's spelling). An engine option the request sets
    off its default has no ``--engine`` spelling: the spec is still the
    engine's, and ``notes`` says which options a run leaves at defaults."""
    from .cli import MOMWIRE_BASES, MOMWIRE_BASIS_VARIANTS

    solver = req.get("solver") or "momwire"
    opts = req.get("model_options") or {}
    if not isinstance(solver, str) or not isinstance(opts, Mapping):
        raise KeepError(f"{who}: the request's solver is not one to keep")
    skip = set()
    if solver != "momwire":
        spec = solver
    else:
        model = req.get("momwire_model") or "bspline"
        degree = opts.get("degree")
        if model == "bspline" and degree in (None, 2):
            spec, skip = "momwire:bspline", {"degree"}
        elif model == "bspline" and degree == 1:
            spec, skip = "momwire:bspline-d1", {"degree"}
        elif model == "bspline":
            raise KeepError(
                f"{who}: a B-spline of degree {degree} has no --engine spelling "
                "(bspline is degree 2, bspline-d1 degree 1)"
            )
        elif model in MOMWIRE_BASES or model in MOMWIRE_BASIS_VARIANTS:
            spec = f"momwire:{model}"
        else:
            raise KeepError(
                f"{who}: the momwire model {model!r} has no --engine spelling"
            )
    if not _ENGINE.fullmatch(spec):
        raise KeepError(f"{who}: {spec!r} is not an engine spec")
    if notes is not None:
        from .web.adapter import model_option_specs

        specs = model_option_specs()
        # A deck that defaults the extended kernel on (AK#1891 / AK#1893)
        # makes "on" the default and "off" the setting a run must be told.
        ek_on = solver == "momwire" and _ek_default_on(req)
        off = [
            k
            for k, v in opts.items()
            if k not in skip
            and not (k in specs and _same(v, specs[k].get("default")))
            and not (k == "extended_kernel" and (v is False or ek_on))
        ]
        if off:
            notes.append(
                f"{who} was solved with {', '.join(sorted(off))} set on its slot; "
                f"--engine {spec} runs the engine's defaults for them."
            )
        _note_ek_off(req, who, notes)
    return spec


def _note_ek_off(req: Mapping, who: str, notes: list[str]) -> None:
    """Add the note a run needs when ``req`` turned off the extended kernel
    its deck defaults on (AK#1895): no ``--engine`` spelling says it, and a
    run left alone takes the deck's default."""
    opts = req.get("model_options") or {}
    if not (
        (req.get("solver") or "momwire") == "momwire"
        and isinstance(opts, Mapping)
        and opts.get("extended_kernel") is False
        and _ek_default_on(req)
    ):
        return
    note = (
        f"{who} was solved with the extended kernel off on its slot, where "
        "its deck defaults it on: run with --no-extended-kernel."
    )
    if note not in notes:
        notes.append(note)


def _ek_default_on(req: Mapping) -> bool:
    """Whether ``req``'s design solves with the extended kernel unless told
    otherwise: a deck read as NEC-4 or NEC-5 (AK#1891) or a NEC-2 deck with
    an EK card (AK#1893), what the slot's toggle shows. A run takes that
    default too (`cli.deck_extended_kernel_flag`), so only turning it off
    needs saying."""
    from .web.examples import UnknownGeometryError, example_for

    design = req.get("geometry")
    if not isinstance(design, str) or not design:
        return False
    try:
        return bool(getattr(example_for(design), "extended_kernel_default", False))
    except UnknownGeometryError:
        return False


def ground_of(req: Mapping, who: str) -> str:
    """The ``--ground`` spec the solve request ``req`` was solved over:
    free space when it asked for none (or its engine took none), else its
    model, with its soil unless that is the CLI's default. A terrain ground
    has no ``--ground`` spelling and is refused by name."""
    from .web.adapter import _requested_ground_model, _soil_from_request

    model = _requested_ground_model(dict(req))
    if model is None:
        return "free"
    if model == "pec":
        return "pec"
    kind = _GROUND_KINDS.get(model)
    if kind is None:
        raise KeepError(
            f"{who}: a {model} ground has no --ground spelling; pin it over "
            "free space, PEC or a finite ground to keep it"
        )
    soil = _soil_from_request(req)
    if soil == _CLI_SOIL:
        return kind
    return f"{kind}:{_fmt(soil[0])},{_fmt(soil[1])}"


def pin_cell(
    pin: Mapping,
    *,
    swept: str | None,
    who: str,
    notes: list[str],
    moved: set | None = None,
) -> an.Cell:
    """One pin as one cell (module docstring): ``pin["req"]`` is the solve
    request its curve was solved with, and everything the cell says comes
    from it: the design, variant and changed knobs (`changed_knobs`), the
    engine (`engine_of`), the ground (`ground_of`) and the plane. ``swept``
    is the knob the pins sweep, left out of the state (the sweep sets it);
    ``moved`` every knob the analysis moves (the swept one, a hold's), when
    given in its place."""
    req = pin.get("req")
    if not isinstance(req, Mapping):
        raise KeepError(f"{who}: no solve request to keep")
    skip = moved if moved is not None else ({swept} if swept else set())
    design, variant, knobs = changed_knobs(req, skip)
    plane = req.get("plane")
    if plane is not None and not (isinstance(plane, str) and plane):
        raise KeepError(f"{who}: plane is a port name, got {plane!r}")
    radius = req.get("wire_radius")
    if isinstance(radius, (int, float)) and radius != _CLI_RADIUS:
        notes.append(
            f"{who} was solved at a wire radius of {_fmt(float(radius))} m "
            "(its slot's); a run uses the engine's own."
        )
    try:
        return an.Cell(
            _state(design, variant, knobs),
            engine=engine_of(req, who, notes),
            ground=ground_of(req, who),
            plane=plane or None,
        )
    except (TypeError, ValueError) as e:
        raise KeepError(f"{who}: {e}") from None


#: The server's wire radius when a request sends none (``adapter._slot_wire_radius``).
_CLI_RADIUS = 0.0005


def _pin_x(pins) -> tuple[str, str]:
    """The kind and name every pin sweeps: one, the same for all."""
    xs = set()
    for p in pins:
        x = p.get("x")
        if not isinstance(x, Mapping) or x.get("kind") not in _X_KINDS:
            raise KeepError("a sweep pin says what it sweeps: x {kind, name}")
        name = x.get("name")
        if x["kind"] == "knob" and not (isinstance(name, str) and name):
            raise KeepError("a knob pin names its knob")
        xs.add((x["kind"], name if x["kind"] == "knob" else x["kind"]))
    if len(xs) != 1:
        raise KeepError(
            "the pins sweep different things ("
            + ", ".join(sorted(n for _, n in xs))
            + "); a study sweeps one: keep each set on its own"
        )
    return xs.pop()


def _pin_values(pins, kind: str) -> tuple:
    """Every x any pin was solved at, ascending, each once: the study solves
    each cell at all of them, so every pinned point is among them."""
    vals: set = set()
    for p in pins:
        xs = p.get("xs")
        if (
            not isinstance(xs, list)
            or not xs
            or not all(
                isinstance(v, (int, float))
                and not isinstance(v, bool)
                and math.isfinite(v)
                for v in xs
            )
        ):
            raise KeepError("a sweep pin carries the x values it was solved at")
        vals.update(xs)
    if kind == "density":
        if not all(float(v).is_integer() for v in vals):
            raise KeepError("a density pin's values are whole segment counts")
        return tuple(sorted({int(v) for v in vals}))
    return tuple(sorted({float(v) for v in vals}))


def _pattern_views(pins, notes: list[str]) -> tuple[an.View, ...]:
    """The cuts the first pin was drawn at, on NEC's whole-degree grid
    (azimuth 0-359, elevation 1-89), and the metrics table."""
    req = pins[0].get("req") or {}

    def num(v, default):
        return (
            float(v)
            if isinstance(v, (int, float)) and not isinstance(v, bool)
            else default
        )

    az_raw, el_raw = num(req.get("az_elev_deg"), 0.0), num(req.get("elev_az_deg"), 10.0)
    az = round(az_raw) % 360
    el = min(89, max(1, round(el_raw)))
    if el != el_raw:
        notes.append(
            f"The azimuth cut was at elevation {_fmt(el_raw)} deg; a pattern "
            f"view takes a whole degree from 1 to 89, so it is {el}."
        )
    if az != az_raw:
        notes.append(
            f"The elevation cut was at azimuth {_fmt(az_raw)} deg; a pattern "
            f"view takes a whole degree from 0 to 359, so it is {az}."
        )
    return (an.Elevation(az=az), an.Azimuth(el=el), an.PatternTable())


def _densities(pins, notes: list[str]) -> None:
    """A note naming the density the pins were solved at: a run's own
    (``--nominal-nsegs``), not the spec's, so the study says what it needs
    to reproduce them."""
    ns = []
    for p in pins:
        n = (p.get("req") or {}).get("n_per_wire")
        if isinstance(n, int) and not isinstance(n, bool) and n not in ns:
            ns.append(n)
    if len(ns) == 1:
        notes.append(
            f"The pins were solved at {ns[0]} segments per wire: run it with "
            f"--nominal-nsegs {ns[0]} to reproduce them exactly."
        )
    elif ns:
        notes.append(
            "The pins were solved at "
            + ", ".join(str(n) for n in ns)
            + " segments per wire (their slots'); one run takes one --nominal-nsegs."
        )


def is_product(cells) -> bool:
    """Whether ``cells`` are exactly the product of their distinct states,
    engines, grounds and planes, each once: then they are a plain cross,
    and otherwise a list (the ``cells=`` ruling)."""
    axes = [
        list(dict.fromkeys(getattr(c, f) for c in cells))
        for f in ("state", "engine", "ground", "plane")
    ]
    # A plane cross cannot say "the design's own plane" beside a named one.
    if None in axes[3] and len(axes[3]) > 1:
        return False
    whole = {
        an.Cell(s, engine=e, ground=g, plane=p)
        for s, e, g, p in itertools.product(*axes)
    }
    return len(cells) == len(whole) and set(cells) == whole


def _bare(st: an.State) -> bool:
    return not st.knobs and st.variant is None


def _cross_of(cells) -> dict:
    """The analysis's cross, engine and ground for ``cells``: a plain cross
    when they are a product (`is_product`), ``cells=`` otherwise. An engine
    or ground every cell shares is the analysis's own either way (what a
    cell leaves out follows the analysis)."""
    engines = list(dict.fromkeys(c.engine for c in cells))
    grounds = list(dict.fromkeys(c.ground for c in cells))
    out: dict = {
        "engine": engines[0] if len(engines) == 1 else None,
        "ground": grounds[0] if len(grounds) == 1 else None,
    }
    if is_product(cells):
        states = list(dict.fromkeys(c.state for c in cells))
        planes = [p for p in dict.fromkeys(c.plane for c in cells) if p is not None]
        # Designs at their defaults read as a designs cross, as E7 does; a
        # knob or a variant makes them states.
        cross = [
            an.Cross(designs=tuple(s.design for s in states))
            if all(_bare(s) for s in states)
            else an.Cross(states=tuple(states))
        ]
        if len(engines) > 1:
            cross.append(an.Cross(engines=tuple(engines)))
        if len(grounds) > 1:
            cross.append(an.Cross(grounds=tuple(grounds)))
        if planes:
            cross.append(an.Cross(planes=tuple(planes)))
        out["cross"] = tuple(cross)
        return out
    out["cross"] = an.Cross(
        cells=tuple(
            an.Cell(
                c.state,
                engine=None if out["engine"] else c.engine,
                ground=None if out["ground"] else c.ground,
                plane=c.plane,
            )
            for c in cells
        )
    )
    return out


def _unique_names(cells: list[an.Cell]) -> list[an.Cell]:
    """Two different settings of one design never share a name (two group
    knob edits are both "bands set"): the later ones gain " (2)", " (3)"."""
    seen: dict[tuple, list] = {}
    out = []
    for c in cells:
        st = c.state
        others = seen.setdefault((st.spec, st.name), [])
        if st not in others:
            others.append(st)
        k = others.index(st)
        if k:
            st = an.State(
                f"{st.name} ({k + 1})", st.design, variant=st.variant, **dict(st.knobs)
            )
        out.append(an.Cell(st, engine=c.engine, ground=c.ground, plane=c.plane))
    return out


def analysis_from_pins(pins, *, kind: str, name) -> tuple[an.Analysis, list[str]]:
    """The study a set of pins is (module docstring), and the notes on how
    it was made. ``kind`` is "sweep" or "pattern"."""
    if (
        not isinstance(pins, list)
        or not pins
        or not all(isinstance(p, Mapping) for p in pins)
    ):
        raise KeepError("give the pins to keep")
    notes: list[str] = []
    x_kind = x_name = None
    if kind == "sweep":
        x_kind, x_name = _pin_x(pins)
        values = _pin_values(pins, x_kind)
        swept = {"frequency": "freq", "density": None, "knob": x_name}[x_kind]
    elif kind == "pattern":
        swept = None
    else:
        raise KeepError(f"pins are sweep or pattern pins, got {kind!r}")
    held = _pins_hold(pins, x_kind)
    moved = {swept} if swept else set()
    if held is not None:
        # The held knobs move at every point (and start from the design's
        # defaults), so they are no part of a pin's state either.
        moved |= {k for k in held.adjust if isinstance(k, str)}
    cells: list[an.Cell] = []
    for i, p in enumerate(pins, start=1):
        label = p.get("label")
        who = f"pin {i}" + (f" ({label})" if isinstance(label, str) and label else "")
        cell = pin_cell(p, swept=swept, who=who, notes=notes, moved=moved)
        if cell in cells:
            notes.append(f"{who} is the same cell as an earlier pin; it is kept once.")
            continue
        cells.append(cell)
    if len(cells) > an.CURVE_CAP:
        raise KeepError(
            f"{len(cells)} pins is over the cap of {an.CURVE_CAP} curves; keep "
            "at most that many"
        )
    cells = _unique_names(cells)
    if x_kind != "density":
        _densities(pins, notes)
    if kind == "sweep":
        target = {"frequency": an.FREQUENCY, "density": an.DENSITY}.get(x_kind, x_name)
        sweep = an.Sweep(target, values=values)
        views = (an.Swr(), an.Rx()) if x_kind == "frequency" else (an.Rx(),)
        if held is not None:
            views = (an.Rx(), an.Knobs())
        default = "pinned sweeps"
    else:
        sweep = None
        views = _pattern_views(pins, notes)
        default = "pinned patterns"
    if name is not None and not isinstance(name, str):
        raise KeepError("name is a string")
    a = _analysis(
        name=(name or "").strip() or default,
        sweep=sweep,
        views=views,
        hold=held,
        **_cross_of(cells),
    )
    return a, notes


def _pins_hold(pins, x_kind) -> an.Hold | None:
    """The hold the pins were drawn under (AK#1757 step 6): a pin of a held
    curve carries it in its request (``req["hold"]``, as ``/analyses``
    served it), and its Z at each x is the optimum's, not the request's
    knobs'. Kept as a plain knob sweep it would be another curve, silently;
    so every pin holds the same, or the keep is refused by name."""
    holds = [
        p["req"].get("hold") if isinstance(p.get("req"), Mapping) else None
        for p in pins
    ]
    if all(h is None for h in holds):
        return None
    if any(h != holds[0] for h in holds):
        raise KeepError(
            "some pins were drawn under a hold and some not, or under different "
            "holds; a study holds one way: keep each set on its own"
        )
    if x_kind != "knob":
        raise KeepError("a held pin sweeps a knob; these sweep " + str(x_kind))
    try:
        h = an.from_data(holds[0])
    except (TypeError, ValueError) as e:
        raise KeepError(f"the pins' hold: {e}") from None
    if not isinstance(h, an.Hold):
        raise KeepError("the pins' hold is not an an.Hold")
    return h


# ── a chart ──────────────────────────────────────────────────────────────────


def _drawn(
    reqs, notes: list[str] | None = None
) -> tuple[tuple[str, ...], tuple[str, ...]] | None:
    """The engines and grounds a chart drew, in its cells' order, each
    once: the specs of the requests its curves were solved with
    (`engine_of`, `ground_of`), and in ``notes`` an extended kernel a cell
    turned off (`_note_ek_off`). None: the page sent none (the chart draws
    what the analysis lists, or the session's slots)."""
    if reqs is None:
        return None
    if (
        not isinstance(reqs, list)
        or not reqs
        or not all(isinstance(r, Mapping) for r in reqs)
    ):
        raise KeepError("cells is a list of the chart's solve requests")
    engines = tuple(dict.fromkeys(engine_of(r, "the chart") for r in reqs))
    if notes is not None:
        for r in reqs:
            _note_ek_off(r, "the chart", notes)
    grounds = tuple(dict.fromkeys(ground_of(r, "the chart") for r in reqs))
    return engines, grounds


def _norm(field: str, spec: str):
    """A spec as what it solves on, so two spellings of one engine or
    ground compare equal (bare ``momwire`` is the B-spline, ``razor-nec5``
    is ``razor-2p``; a finite ground's default soil written or not)."""
    if field == "grounds":
        from .cli import parse_ground

        try:
            return parse_ground(spec)
        except argparse.ArgumentTypeError:
            return spec
    return {"momwire": "momwire:bspline", "momwire:razor-nec5": "momwire:razor-2p"}.get(
        spec, spec
    )


def _with_axis(a: an.Analysis, field: str, specs) -> an.Analysis:
    """``a`` drawing exactly ``specs`` for ``field`` ("engines" / "grounds"):
    one is the analysis's own engine or ground, several a cross, written
    where the analysis wrote it or else last. What the analysis lists
    already, in any spelling of it, stays as written (a bare ``momwire``
    keeps its own density); a ``cells=`` analysis keeps its own, since its
    cells are whole."""
    if specs is None or an.cells_of(a):
        return a
    one = field[:-1]
    own = next((c for c in a.crosses if c.kind == field), None)
    listed = (
        own and getattr(own, field) or ((getattr(a, one),) if getattr(a, one) else ())
    )
    if [_norm(field, x) for x in listed] == [_norm(field, x) for x in specs]:
        return a
    f = _fields(a)
    f[one] = specs[0] if len(specs) == 1 else None
    new = an.Cross(**{field: specs}) if len(specs) > 1 else None
    crosses = [new if c.kind == field else c for c in a.crosses]
    if new is not None and own is None:
        crosses.append(new)
    f["cross"] = tuple(c for c in crosses if c is not None)
    return _analysis(**f)


def _with_values(a: an.Analysis, values) -> an.Analysis:
    """``a`` swept at exactly ``values``: the chart's edited range, as the
    points it solved."""
    if values is None:
        return a
    if a.sweep is None or isinstance(a.sweep, tuple):
        raise KeepError("only a one-sweep chart has x values to keep")
    if (
        not isinstance(values, list)
        or not values
        or not all(
            isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
            for v in values
        )
    ):
        raise KeepError("values is a list of numbers")
    vals = tuple(sorted(set(values)))
    if a.sweep.knob == an.DENSITY:
        vals = tuple(int(v) for v in vals)
    return _analysis(**{**_fields(a), "sweep": an.Sweep(a.sweep.knob, values=vals)})


_AXES = ("x", "y")


def _axis_sweep(s: an.Sweep, edit, name: str) -> an.Sweep:
    """Map axis ``s`` with the chart's edit ``{lo, hi, points, spacing}``:
    ``Sweep(knob, lo, hi, points=)`` on the analysis's own knob (the page
    names no knob), log spacing written only when it is log."""
    if not isinstance(edit, Mapping):
        raise KeepError(f"axes.{name} is {{lo, hi, points, spacing}}")

    def num(k):
        v = edit.get(k)
        if (
            isinstance(v, bool)
            or not isinstance(v, (int, float))
            or not math.isfinite(v)
        ):
            raise KeepError(f"axes.{name}.{k} is a finite number")
        return float(v)

    lo, hi = num("lo"), num("hi")
    points = edit.get("points")
    if isinstance(points, bool) or not isinstance(points, int) or points < 2:
        raise KeepError(f"axes.{name}.points is a count of at least 2")
    spacing = edit.get("spacing", "lin")
    if spacing not in ("lin", "log"):
        raise KeepError(f"axes.{name}.spacing is 'lin' or 'log'")
    if lo == hi:
        raise KeepError(f"axes.{name}: lo and hi are the same value")
    try:
        return an.Sweep(
            s.knob,
            min(lo, hi),
            max(lo, hi),
            points=points,
            spacing="log" if spacing == "log" else None,
        )
    except (TypeError, ValueError) as e:
        raise KeepError(f"axes.{name}: {e}") from None


def _with_axes(a: an.Analysis, axes) -> an.Analysis:
    """Map ``a`` with the chart's edited axes (map note, decision 12): each
    edited axis as ``Sweep(knob, lo, hi, points=)``, never a list of values,
    and an axis the chart left as the analysis's own unchanged."""
    if axes is None:
        return a
    if not isinstance(a.sweep, tuple):
        raise KeepError("only a map has x and y axes to keep")
    if not isinstance(axes, Mapping) or not axes or set(axes) - set(_AXES):
        raise KeepError("axes is {x?, y?}, each {lo, hi, points, spacing}")
    sweeps = tuple(
        _axis_sweep(s, axes[k], k) if k in axes else s
        for k, s in zip(_AXES, a.sweep, strict=True)
    )
    return _analysis(**{**_fields(a), "sweep": sweeps})


def _as_study(a: an.Analysis, tab: Mapping) -> an.Analysis:
    """A chart as a study, which names its designs. One that already does
    (a designs cross, states naming theirs) is kept as it is; otherwise its
    unnamed states are set on the tab's design (at the tab's variant), its
    cells with no design are given the tab's, and an analysis with neither
    gains one state of the tab's own: its knobs where they differ from its
    variant's defaults (the chart drew the live knobs), less every knob the
    analysis moves itself."""
    unnamed = [s for s in an.states_of(a) if s.design is None]
    bare_cells = [c for c in an.cells_of(a) if c.state is None]
    if an.named_designs(a) and not unnamed and not bare_cells:
        return a
    design = tab.get("geometry")
    if not isinstance(design, str) or not design:
        raise KeepError("the chart's tab names no design")
    cls = _builder_cls(design)
    variant = _variant(cls, design, tab.get("variant"))
    probe = _solved_builder(cls, tab)
    moved = {an.resolve(s.knob, probe).knob for s in a.sweeps}
    if a.hold is not None:
        moved |= {an.resolve(k, probe).knob for k in a.hold.adjust}
    moved |= {
        an.resolve(c.step.knob, probe).knob for c in a.crosses if c.step is not None
    }
    if any(s.knob == an.FREQUENCY for s in a.sweeps):
        moved.add("freq")
    moved.discard(None)

    def own(st: an.State | None) -> an.State:
        if st is None:
            _, _, knobs = changed_knobs(tab, moved)
            return _state(design, variant, knobs)
        if st.design is not None:
            return st
        return an.State(st.name, design, variant=variant, **dict(st.knobs))

    f = _fields(a)
    if an.cells_of(a):
        f["cross"] = an.Cross(
            cells=tuple(
                an.Cell(own(c.state), engine=c.engine, ground=c.ground, plane=c.plane)
                for c in an.cells_of(a)
            )
        )
    elif an.states_of(a):
        f["cross"] = tuple(
            an.Cross(states=tuple(own(s) for s in c.states))
            if c.kind == "states"
            else c
            for c in a.crosses
        )
    else:
        f["cross"] = (an.Cross(states=(own(None),)), *a.crosses)
    return _analysis(**f)


#: The knob a family over the measurement frequency names (AK#1935): the
#: page's ``freq``, written back as the role, as `analyses.resolve` reads it.
_FREQ_KNOB = "freq"


def _grid(lo: float, hi: float, points: int, log: bool) -> list[float]:
    """The values ``Sweep(knob, lo, hi, points=)`` steps (`sweep.gen_xs`'s
    linear or geometric grid, before any integer rounding)."""
    if points == 1:
        return [lo]
    t = [k / (points - 1) for k in range(points)]
    if log:
        return [lo * (hi / lo) ** x for x in t]
    return [lo + (hi - lo) * x for x in t]


def analysis_from_family(family) -> an.Analysis:
    """The pattern family the knob chart drew (AK#1935): ``{knob, lo, hi,
    points, spacing, values?}`` as ``an.patterns(cross=an.Cross(step=
    an.Sweep(knob, lo, hi, points=n)))``, a log grid with ``spacing="log"``
    and a frequency family over `an.FREQUENCY`. The page's ``values`` are
    the values it solved: written as ``values=`` only where they are not
    that grid (an integer knob's ladder, rounded to whole values), so the
    kept analysis steps exactly what was drawn."""
    if not isinstance(family, Mapping):
        raise KeepError("family is {knob, lo, hi, points, spacing}")
    knob = family.get("knob")
    if not isinstance(knob, str) or not knob:
        raise KeepError("family.knob is a knob name")
    lo = _number(family.get("lo"), "family.lo")
    hi = _number(family.get("hi"), "family.hi")
    points = family.get("points")
    if isinstance(points, bool) or not isinstance(points, int) or points < 1:
        raise KeepError("family.points is a count of at least 1")
    if points > an.CURVE_CAP:
        raise KeepError(
            f"family.points: {points} values is over the cap of {an.CURVE_CAP} patterns"
        )
    spacing = family.get("spacing", "lin")
    if spacing not in ("lin", "log"):
        raise KeepError("family.spacing is 'lin' or 'log'")
    lo, hi = min(lo, hi), max(lo, hi)
    target = an.FREQUENCY if knob == _FREQ_KNOB else knob
    log = spacing == "log"
    values = family.get("values")
    grid = _grid(lo, hi, points, log)
    kw: dict = {"lo": lo, "hi": hi, "points": points, "spacing": "log" if log else None}
    if values is not None:
        if not isinstance(values, list) or not values:
            raise KeepError("family.values is a list of numbers")
        vals = [_number(v, "a family value") for v in values]
        on_grid = len(vals) == len(grid) and all(
            math.isclose(v, g, rel_tol=1e-9, abs_tol=1e-12)
            for v, g in zip(vals, grid, strict=True)
        )
        if not on_grid:
            kw = {"values": tuple(vals)}
    try:
        sweep = an.Sweep(target, **kw)
    except (TypeError, ValueError) as e:
        raise KeepError(f"family: {e}") from None
    return an.patterns(cross=an.Cross(step=sweep))


def analysis_from_chart(
    req: Mapping, *, form: str, notes: list[str] | None = None
) -> an.Analysis:
    """The chart's analysis as it drew it (module docstring); ``notes``
    collects an extended kernel its cells turned off (`_drawn`). A knob
    chart's pattern family (AK#1935) sends ``family`` in place of ``spec``:
    no analysis was picked, so the analysis is the family it drew
    (`analysis_from_family`)."""
    family = req.get("family")
    a = analysis_of(req.get("spec")) if family is None else analysis_from_family(family)
    drawn = _drawn(req.get("cells"), notes)
    if drawn is not None:
        a = _with_axis(a, "engines", drawn[0])
        a = _with_axis(a, "grounds", drawn[1])
    a = _with_values(a, req.get("values"))
    a = _with_axes(a, req.get("axes"))
    if form == "analysis":
        if an.named_designs(a):
            raise KeepError(
                "this chart compares named designs: keep it as a study; an "
                "analysis in a design's build_analyses() is about that design"
            )
        return _named(a, req.get("name"))
    tab = req.get("tab")
    if not isinstance(tab, Mapping):
        raise KeepError("keeping a chart as a study needs the tab's request (tab)")
    return _named(_as_study(a, tab), req.get("name"))


# ── the entry point ──────────────────────────────────────────────────────────


def _number(v, what: str) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        raise KeepError(f"{what} is a finite number, got {v!r}")
    return float(v)


def optimize_from_run(
    req: Mapping, deck_name: Callable[[str], str | None] | None = None
) -> tuple[an.Optimize, list[str]]:
    """A finished multi-band run as an `an.Optimize` (AK#1906; the
    workbench's Keep on a band result): ``{tab, free, bands, mean_weight?,
    result, name?}``, ``tab`` the tab's solve request, ``free`` the knobs
    the run moved (``[{name, min, max}]``), ``bands`` the band list it sent
    (``/optimize``'s), ``result`` its answer. The start is the tab's design
    and knobs with the moved ones put back at the run's own start
    (``result.params_before``), so what is kept is where the run began.
    ``deck_name(key)`` spells an opened deck's design as ``@<its file
    name>``, the only name a command line can find it by."""
    from . import optimize_study as ost
    from .opt import _set_path
    from .web.optimize_bands import BandsRefused, parse_bands

    tab, res = req.get("tab"), req.get("result")
    if not isinstance(tab, Mapping) or not isinstance(res, Mapping):
        raise KeepError("an optimize keep sends the tab's request and the run's result")
    free = req.get("free")
    if (
        not isinstance(free, list)
        or not free
        or not all(isinstance(f, Mapping) for f in free)
    ):
        raise KeepError("free is the run's knobs, [{name, min, max}, ...]")
    names = [f.get("name") for f in free]
    if not all(isinstance(n, str) and n for n in names):
        raise KeepError("each free knob has a name")
    params, before = res.get("params"), res.get("params_before")
    if not isinstance(params, Mapping) or not isinstance(before, Mapping):
        raise KeepError("the result carries the run's params and params_before")
    for n in names:
        _number(params.get(n), f"the result's {n}")
        _number(before.get(n), f"the start's {n}")
    try:
        bands = parse_bands(req.get("bands"))
    except BandsRefused as e:
        raise KeepError(str(e)) from None
    design = tab.get("geometry")
    if not isinstance(design, str) or not design:
        raise KeepError("the request names no design (geometry)")
    cls = _builder_cls(design)
    variant = _variant(cls, design, tab.get("variant"))
    solved = _solved_builder(cls, tab)
    fresh = _solved_builder(cls, {"geometry": design, "variant": variant or "default"})
    for n in names:
        try:
            _set_path(solved, n, float(before[n]))
        except (AttributeError, KeyError, IndexError, TypeError, ValueError):
            raise KeepError(f"{design} has no knob {n!r}") from None
    alias = deck_name(design) if deck_name is not None else None
    spec = alias or (design if variant is None else f"{design}:{variant}")
    notes: list[str] = []
    if alias:
        notes.append(
            f"The deck is named by its file name, {alias}: run it from the folder "
            "that holds the deck, or write its path there."
        )
    rows = res.get("bands_before") or []
    z0 = rows[0].get("z0_ohms") if rows and isinstance(rows[0], Mapping) else None
    name = req.get("name")
    if name is not None and not isinstance(name, str):
        raise KeepError("name is a string")
    mhz = "/".join(f"{b.freq_mhz:g}" for b in bands)
    try:
        o = ost.from_run(
            (name or "").strip() or f"optimize across {mhz} MHz",
            start=ost.start_state(spec, solved, fresh),
            free=[
                {
                    "name": n,
                    "min": _number(f.get("min"), f"{n}'s min"),
                    "max": _number(f.get("max"), f"{n}'s max"),
                }
                for n, f in zip(names, free, strict=True)
            ],
            bands=bands,
            res=res,
            mean_weight=req.get("mean_weight"),
            z0=_number(z0, "the run's Z0") if z0 is not None else 50.0,
            engine=engine_of(tab, "the run", notes),
            ground=ground_of(tab, "the run"),
        )
    except (TypeError, ValueError, KeyError) as e:
        raise KeepError(str(e)) from None
    return o, notes


def build(
    req: Mapping, deck_name: Callable[[str], str | None] | None = None
) -> tuple[an.Analysis | an.Optimize, str, str, list[str]]:
    """``(analysis, form, origin, notes)`` for a keep request (``/keep``,
    ``/studies/save``): ``{origin, form, name?, notes?}`` and, for a chart,
    ``{spec, tab, cells?, values?, axes?}`` (``cells`` its curves' solve
    requests, ``axes`` a map's edited axes), for pins ``{pins: [{req, x?,
    xs?, label?}]}``, for a band run (``"optimize"``, AK#1906) what
    `optimize_from_run` reads. Pins and band runs are only ever kept as a
    study: they name their designs."""
    if not isinstance(req, Mapping):
        raise KeepError("a keep request is an object")
    origin = req.get("origin")
    if origin not in ORIGINS:
        raise KeepError(f"origin is one of {', '.join(ORIGINS)}, got {origin!r}")
    form = req.get("form") or "study"
    if form not in FORMS:
        raise KeepError(f"form is one of {', '.join(FORMS)}, got {form!r}")
    notes = _notes(req.get("notes") or [])
    if origin == "optimize":
        if form != "study":
            raise KeepError("a band run is kept as a study: it names its design")
        o, made = optimize_from_run(req, deck_name)
        return o, form, origin, notes + made
    if origin == "chart":
        made: list[str] = []
        a = analysis_from_chart(req, form=form, notes=made)
        return a, form, origin, notes + made
    if form != "study":
        raise KeepError("pins are kept as a study: they name their designs")
    a, made = analysis_from_pins(
        req.get("pins"), kind=origin.split()[0], name=req.get("name")
    )
    return a, form, origin, notes + made


# ── the text ─────────────────────────────────────────────────────────────────

# Anything that could end a comment line or trouble the tokenizer: control
# characters (a newline, a NUL, which makes the file unimportable) and the
# Unicode line and paragraph separators.
_BREAKS = re.compile(r"[\x00-\x1f\x7f-\x9f  ]")
#: At most this many notes, each at most this long: they are remarks, and a
#: page sending a novel is not one.
_NOTES, _NOTE_LEN = 24, 400


def _comment(lines) -> list[str]:
    """``lines`` as comment lines. Each note is ONE line: any character that
    could end the comment and start code (`_BREAKS`) is a space, so page
    text in a note stays a comment whatever it holds."""
    return [f"# {_BREAKS.sub(' ', str(t))[:_NOTE_LEN]}".rstrip() for t in lines]


def _notes(notes) -> list[str]:
    if not isinstance(notes, (list, tuple)) or not all(
        isinstance(n, str) for n in notes
    ):
        raise KeepError("notes are a list of strings")
    if len(notes) > _NOTES:
        raise KeepError(f"at most {_NOTES} notes")
    return list(notes)


def render(
    a: an.Analysis,
    *,
    form: str,
    origin: str,
    notes=(),
    saved: bool = False,
    today: _dt.date | None = None,
) -> str:
    """The text a keep puts on the clipboard or in a file (module
    docstring). ``notes`` are remarks on how the spec was made, written as
    comments, never as code. ``saved``: the file the workbench writes,
    whose header says it is trusted; a copied study says how to allow it."""
    if form not in FORMS:
        raise KeepError(f"form is one of {', '.join(FORMS)}, got {form!r}")
    if origin not in ORIGINS:
        raise KeepError(f"origin is one of {', '.join(ORIGINS)}, got {origin!r}")
    notes = _notes(notes)
    copy = _copy_notes(a)
    if form == "analysis":
        return (
            "\n".join([*_comment(notes), *_comment(copy), an.code_with_imports(a)])
            + "\n"
        )
    day = (today or _dt.datetime.now(_dt.UTC).astimezone().date()).isoformat()
    head = [
        f"Written by the antennaknobs workbench on {day}, from {ORIGINS[origin]}",
        '("keep as study", AK#1757 step 7).',
        *(
            [
                "Saved trusted, with your edits allowed: edit it freely, it will not ask again."
            ]
            if saved
            else [
                "Save it as a .py under ~/.antennaknobs/studies/, then allow it:",
                "antennaknobs allow <its path under that folder> --edits",
            ]
        ),
    ]
    lines = _comment(head)
    if notes or copy:
        lines += ["#", *_comment(notes), *_comment(copy)]
    return "\n".join(
        [
            *lines,
            "",
            "import antennaknobs.analyses as an",
            *an.imports(a),
            "",
            "",
            "def build_studies():",
            "    return [",
            f"        {an.to_code(a, indent=8)},",
            "    ]",
            "",
        ]
    )


def _copy_notes(a: an.Analysis) -> list[str]:
    """A note per callable metric whose function cannot be imported by name
    (AK#1828): one from a user design or study file, loaded by its path. The
    text calls it by its bare name, so it must be copied into the file."""
    out = []
    for m in an.metrics_of(a):
        if an.importable(m.fn):
            continue
        out.append(
            f"The metric {m.name!r} calls {m.fn.__qualname__}() from "
            f"{_where(m.fn)}, which cannot be imported by name: copy the "
            "function into this file, above the code that calls it."
        )
    return out


def _where(fn) -> str:
    """Where a function that cannot be imported by name is defined: its
    file when it has one."""
    import inspect

    try:
        path = inspect.getsourcefile(fn)
    except TypeError:
        path = None
    return path or fn.__module__


# ── the file ─────────────────────────────────────────────────────────────────


def study_path(text: str, root: Path | None = None) -> tuple[Path, str]:
    """The file a user-typed relative path names under the studies folder,
    and its study source (``feeds/e7``): ``feeds/e7`` or ``feeds/e7.py``.
    Refused by name: an absolute path, a ``..`` (or any part that is not a
    plain name, `_PART`), a backslash, and an empty one."""
    root = studies.default_studies_dir() if root is None else root
    raw = str(text or "").strip()
    if not raw:
        raise KeepError("give the study a file name")
    if "\\" in raw:
        raise KeepError("a study's path separates folders with '/', not '\\'")
    if raw.startswith("/") or re.match(r"^[A-Za-z]:", raw):
        raise KeepError(
            f"{raw!r} is absolute; a study's path is relative to the studies folder"
        )
    raw = raw.removesuffix(".py")
    parts = raw.split("/")
    if ".." in parts:
        raise KeepError(f"{raw!r} climbs out of the studies folder ('..')")
    if len(parts) > _MAX_DEPTH:
        raise KeepError(f"{raw!r} nests more than {_MAX_DEPTH} folders deep")
    bad = [p for p in parts if not _PART.fullmatch(p)]
    if bad:
        raise KeepError(
            f"{bad[0]!r} is not a plain name: each part of a study's path is "
            "letters, digits, '_' and '-', starting with a letter or digit"
        )
    path = root.joinpath(*parts).with_suffix(".py")
    # Belt and braces over the rules above: the file lands inside the folder.
    if root.resolve() not in path.resolve().parents:
        raise KeepError(f"{raw!r} is not inside the studies folder")
    return path, "/".join(parts)


def save(
    a: an.Analysis,
    rel: str,
    *,
    origin: str,
    notes=(),
    overwrite: bool = False,
    today: _dt.date | None = None,
) -> dict:
    """Write ``a`` as a study file at ``rel`` under the studies folder and
    record it trusted with edits allowed (ruling 4: the ``allow --edits``
    state, `design_trust`'s ``always`` mode, in the studies folder's own
    store). Refused, with nothing written: a spec that would be refused as a
    study when found (`studies.refusal`), a bad path (`study_path`), and a
    file already there unless ``overwrite`` (`StudyExists`). Returns
    ``{path, source, name}``, ``name`` the study's full name, as the picker
    and ``analyze --study`` take it."""
    from . import design_trust

    why = studies.refusal(a)
    if why:
        raise KeepError(why)
    path, source = study_path(rel)
    if path.exists() and not overwrite:
        raise StudyExists(
            f"{source}.py is there already; replace it, or pick another name"
        )
    text = render(a, form="study", origin=origin, notes=notes, saved=True, today=today)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    design_trust.trust(path, mode="always")
    return {
        "path": str(path),
        "source": source,
        "name": f"{source}{studies.SEP}{a.name}",
    }

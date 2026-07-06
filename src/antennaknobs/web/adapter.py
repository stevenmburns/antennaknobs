"""Bridge antennaknobs's Builder idiom into momwire's web AntennaExample.

Each `designs/<name>.py` exposes a `Builder` class with `default_params`
(a MappingProxyType of physics knobs). We walk that registry, derive a
`ParamSpec` schema from `default_params` (with optional per-design
overrides under the reserved `ui_params` key), and register one
`AntennaExample` per design so the existing momwire web frontend can
drive it without per-design glue.

Reserved keys inside `ui_params`:
  default_view     : "xy" | "yz" | "xz"  — initial 2D projection
  target_z0        : float — reference impedance for SWR (default 50)
  meas_freq_range  : (lo, hi)  — measurement-freq slider span override
  bands            : tuple[BandSpec] — band tabs (default HF amateur set)
  sweep_policy     : (anchor, lo_factor, hi_factor)
  multi_feed       : bool — declare multi-feed response shape
  layout           : dict {columns: int} — pin the knob grid to a fixed
                     column count so per-param `layout` col positions are
                     stable (default: responsive auto-flow packing)
  <param_name>     : dict of {min, max, step, unit, label, precision,
                              kind, sweepable, enum_options, layout, hidden}
                     — slider-bounds + metadata overrides for one param.
                     `layout` is {row, col, row_span, col_span} (1-indexed
                     CSS grid lines, all optional) to place this knob
                     explicitly. `hidden: True` suppresses the control
                     entirely (the param stays pinned at its default value
                     through solves) — for a knob that's degenerate with
                     another. Anything missing falls back to auto-derived
                     defaults.

Everything else in `default_params` becomes a `ParamSpec`. Numeric
defaults become float sliders with auto bounds (±50% around default);
ints become int sliders; bools become checkboxes; complex defaults are
skipped (no UI yet — the request can still override via re/im dict).
"""

from __future__ import annotations

import importlib
import math
import pathlib
import time
from functools import lru_cache
from typing import Any

import numpy as np

from antennaknobs.builder import (
    Array1x2Builder,
    Array1x4Builder,
    Array1x4GroupedBuilder,
    Array2x2Builder,
    Array2x4Builder,
    diff_params,
    resolve_variant_params,
)

try:
    from antennaknobs.engines.pynec import DEFAULT_GROUND, PyNECEngine
except ImportError:
    PyNECEngine = None
    DEFAULT_GROUND = ("finite", 10.0, 0.002)
from antennaknobs.engines.momwire import MomwireEngine
from momwire import (
    ArrayBlockSolver,
    BSplineSolver,
    HMatrixSolver,
    SinusoidalSolver,
    TriangularSolver,
)

from .examples import register
from .examples._base import (
    DEFAULT_HF_BANDS,
    DEFAULT_SWEEP_POLICY,
    AntennaExample,
    BandSpec,
    ParamGroupSpec,
    ParamSpec,
    SweepPolicy,
)

C_LIGHT = 299_792_458.0

DESIGNS_PKG = "antennaknobs.designs"
# Resolve the designs directory from the installed package, never a path relative
# to this file: web/ and src/antennaknobs/ are siblings in a source checkout, but
# once installed from a wheel they are separate top-level packages with no `src/`
# in between. __path__ points at the real location in both layouts.
DESIGNS_DIR = pathlib.Path(importlib.import_module(DESIGNS_PKG).__path__[0])

_MOMWIRE_MODELS = {
    "triangular": TriangularSolver,
    "sinusoidal": SinusoidalSolver,
    "bspline": BSplineSolver,
    # Hierarchical (H-matrix / ACA) accelerator — same B-spline basis as
    # bspline; model_options forward verbatim (degree, aca_eta,
    # aca_leaf_size, aca_tol, solve_tol, …). Ground/enrichment fall back to
    # the dense bspline solve inside HMatrixSolver.
    "hmatrix": HMatrixSolver,
    # Element-aware array-block accelerator (sibling of hmatrix) for arrays of
    # identical/few-shape elements: dense per-shape self-blocks + low-rank
    # coupling, block-Jacobi GMRES. Same B-spline basis and model_options as
    # bspline/hmatrix (degree, aca_tol, solve_tol, …); on a single connected
    # structure it degrades to one element and matches the dense bspline solve.
    "arrayblock": ArrayBlockSolver,
}


# ---------------------------------------------------------------------------
# Schema derivation
# ---------------------------------------------------------------------------


def _strip_ui(params: dict) -> dict:
    """Return a copy of the params dict with the reserved `ui_params` key
    removed — what gets passed into Builder construction."""
    return {k: v for k, v in params.items() if k != "ui_params"}


def _nice_step(raw: float) -> float:
    """Snap a raw step to the 1-2-5 series (… 0.001, 0.002, 0.005, 0.01 …)
    so auto-derived sliders advance in familiar increments instead of odd
    grids like 0.003 or 0.0007. Picks the nearest 1/2/5·10ⁿ using the
    conventional log-spaced thresholds (1.5, 3, 7)."""
    if raw <= 0.0:
        return raw
    exp = math.floor(math.log10(raw))
    mant = raw / 10.0**exp  # in [1, 10)
    nice = 1.0 if mant < 1.5 else 2.0 if mant < 3.0 else 5.0 if mant < 7.0 else 10.0
    return nice * 10.0**exp


def _precision_for_step(step: float) -> int:
    """Decimal places to display a value stepped by `step`, with one digit
    of headroom so an off-grid default still reads meaningfully. Capped at
    6 to keep labels sane for very small factors."""
    if step <= 0.0:
        return 3
    return min(6, max(0, -math.floor(math.log10(step))) + 1)


def _is_degree_param(name: str) -> bool:
    """True for the standardized angle params (keys carry a `_deg` token,
    e.g. `angle_deg`, `slant_deg`, `angle_deg_itop`, `gap_angle_deg`)."""
    return name.endswith("_deg") or "_deg_" in name


def _display_label(name: str) -> str:
    """Default knob label for a param key. Angle params drop the redundant
    `_deg` token (the degree unit is shown on the slider instead), so
    `angle_deg_itop` reads as `angle_itop` and the panel stays compact. The
    underlying param *name* is unchanged — the frontend surfaces it via the
    knob tooltip so the displayed and program names never silently diverge."""
    if _is_degree_param(name):
        return name.replace("_deg_", "_").removesuffix("_deg")
    return name


def _auto_paramspec(name: str, default: Any, override: dict | None) -> ParamSpec | None:
    """Build a ParamSpec from a default value plus optional UI overrides.

    Returns None when the value type has no UI representation (complex,
    string-non-enum, etc.) and no override was supplied — the param is
    still settable via the API, it just doesn't appear in the UI.
    """
    override = dict(override or {})
    label = override.pop("label", _display_label(name))
    unit = override.pop("unit", None)
    # Optional explicit grid placement for this knob (row/col/spans). Only a
    # dict is meaningful; anything else is ignored so a typo can't crash the
    # registry. Passed verbatim to ParamSpec.layout for every kind.
    layout_raw = override.pop("layout", None)
    layout = dict(layout_raw) if isinstance(layout_raw, dict) else None
    # Precision (decimal places shown on the slider label) defaults to None
    # here so the numeric branch can derive it from the resolved step. Any
    # non-numeric path falls back to 3, matching the historical default.
    explicit_precision = override.pop("precision", None)
    precision = 3 if explicit_precision is None else int(explicit_precision)
    sweepable = bool(override.pop("sweepable", name == "freq"))

    if isinstance(default, bool):
        kind = override.pop("kind", "bool")
        return ParamSpec(
            name=name,
            label=label,
            default=default,
            kind=kind,
            unit=unit,
            precision=precision,
            layout=layout,
        )

    if isinstance(default, (int, float)) and not isinstance(default, bool):
        is_int = isinstance(default, int) and override.get("kind") != "float"
        kind = override.pop("kind", "int" if is_int else "float")
        d = float(default)
        # Auto bounds: a generous ±50% window. The step gives 0.1%
        # *relative* resolution (window / 1000) so any scaling factor,
        # fraction, length, or angle is fine-tunable by hand regardless of
        # its magnitude — a flat absolute step would be too coarse for
        # sub-unity fractions and needlessly fine for large values. Snapped
        # to the 1-2-5 series for clean slider stops. For an int
        # default of 0 the multiplicative window collapses, so fall back to
        # a small absolute range.
        if d == 0.0:
            lo, hi, step = -1.0, 1.0, 0.1
        else:
            lo = d * 0.5 if d > 0 else d * 1.5
            hi = d * 1.5 if d > 0 else d * 0.5
            step = _nice_step(max((hi - lo) / 1000.0, 1e-9))
        if kind == "int":
            lo = float(int(round(lo)))
            hi = float(int(round(hi)))
            step = 1.0
        # Phase params (phase_lr, phase_tb, ...) are degrees, converted
        # to a phasor by the array builders via exp(j π · phase / 180).
        # ±180° covers the full unit circle; signed range puts the
        # zero-phase reference at slider centre with positive = lead,
        # negative = lag. The auto-derived (-1, 1) fallback for
        # default=0 would otherwise give a useless 2° span.
        if name.startswith("phase_"):
            lo, hi, step = -180.0, 180.0, 1.0
            unit = unit or "°"
        # `design_freq` is the geometry-sizing frequency for
        # geometry-from-design_freq designs (wavelength = c / design_freq, then
        # dimensions are wavelength × factors). Wire it into the
        # global designFreq state on the frontend so the slider
        # actually retunes the geometry AND the meas-freq slider
        # follows when linkMeas is on. Top-level designs don't have a
        # design_freq param — their geometry is hand-tuned in absolute
        # meters and the measurement freq slider (at the top of the
        # UI) is the only thing that needs to move per solve.
        if name == "design_freq":
            unit = unit or "MHz"
            override["linked_to_design_freq"] = True  # keep around
        # Angle params read in degrees; show the ° unit on the slider so the
        # label can drop the redundant `_deg` token (see _display_label), and
        # default to a 0.5° step (finer than the auto 1-2-5 step is overkill,
        # coarser loses the half-degree tuning hams expect). A design's
        # ui_params `step` still overrides; int-typed angles keep whole steps.
        if _is_degree_param(name):
            unit = unit or "°"
            if kind != "int":
                step = 0.5
        final_step = float(override.pop("step", step))
        # Derive display precision from the resolved step (matching its
        # decimals plus one digit of headroom), unless the design pinned a
        # precision or this is an int / phase param fixed to whole units.
        if explicit_precision is not None:
            resolved_precision = int(explicit_precision)
        elif kind == "int" or name.startswith("phase_"):
            resolved_precision = 0
        else:
            resolved_precision = _precision_for_step(final_step)
        spec_kwargs = dict(
            name=name,
            label=label,
            default=int(d) if kind == "int" else d,
            kind=kind,
            min=float(override.pop("min", lo)),
            max=float(override.pop("max", hi)),
            step=final_step,
            precision=resolved_precision,
            unit=unit,
            sweepable=sweepable,
            layout=layout,
        )
        if "linked_to_design_freq" in override:
            spec_kwargs["linked_to_design_freq"] = bool(
                override.pop("linked_to_design_freq")
            )
        if "link_meas_freq_to_param" in override:
            spec_kwargs["link_meas_freq_to_param"] = str(
                override.pop("link_meas_freq_to_param")
            )
        return ParamSpec(**spec_kwargs)

    if isinstance(default, str):
        opts = override.pop("enum_options", None)
        if opts is None:
            return None
        return ParamSpec(
            name=name,
            label=label,
            default=default,
            kind="enum",
            enum_options=tuple(opts),
            precision=precision,
            unit=unit,
            layout=layout,
        )

    # complex, None, or anything exotic — skip the auto-UI; the request
    # body can still override via {"re": ..., "im": ...}.
    return None


def _group_spec_from_default(
    name: str,
    default_value: tuple | list,
    ui_override: dict,
    all_default_params: dict,
) -> ParamGroupSpec | None:
    """Build a ParamGroupSpec from a tuple/list-of-dicts default value.

    The default value's length seeds default_overrides for the group's
    instances; the inner ParamSpecs come from auto-deriving each key of
    the first instance dict (with optional per-leaf overrides supplied
    under the same ui_override dict, keyed by leaf name).

    `ui_override` is the dict stored under `ui_params[<group_name>]`.
    Recognised keys: label_template, repeat_count, max_repeats,
    link_meas_freq_to_param, plus any leaf-name → override-dict pairs.
    Falls back to sensible defaults when missing.
    """
    if not default_value or not all(isinstance(d, dict) for d in default_value):
        return None
    template = default_value[0]
    if not template:
        return None

    repeat_count = ui_override.get("repeat_count")
    if repeat_count is None:
        # Heuristic: prefer n_<name> (n_bands for bands), then n_<singular>.
        for cand in (f"n_{name}", f"n_{name.rstrip('s')}"):
            if cand in all_default_params:
                repeat_count = cand
                break
    if not isinstance(repeat_count, str):
        # No count param → can't render a repeating group.
        return None

    max_repeats = int(ui_override.get("max_repeats", len(default_value)))
    label_template = str(ui_override.get("label_template", f"{name} {{i}}"))
    link = ui_override.get("link_meas_freq_to_param")

    inner_params: list[ParamSpec] = []
    for leaf_name, leaf_default in template.items():
        leaf_override = ui_override.get(leaf_name)
        if leaf_override is None or not isinstance(leaf_override, dict):
            leaf_override = {}
        spec = _auto_paramspec(leaf_name, leaf_default, dict(leaf_override))
        if spec is not None:
            inner_params.append(spec)
    if not inner_params:
        return None

    default_overrides = tuple(dict(d) for d in default_value)

    return ParamGroupSpec(
        name=name,
        label_template=label_template,
        repeat_count=repeat_count,
        max_repeats=max_repeats,
        params=tuple(inner_params),
        default_overrides=default_overrides,
        link_meas_freq_to_param=str(link) if isinstance(link, str) else None,
    )


def _derive_schema(default_params: dict) -> tuple:
    ui = dict(default_params.get("ui_params") or {})
    specs: list[ParamSpec] = []
    for key, default in default_params.items():
        if key == "ui_params":
            continue
        # `freq` is measurement frequency only — driven by the dedicated
        # meas-freq slider at the top of the UI, never by a schema
        # slider. The Builder's default_params['freq'] value is still
        # used as the initial measurement freq when the example loads;
        # the adapter just doesn't expose a redundant slider for it.
        #
        # `design_freq` is the geometry-sizing frequency for
        # design_freq-sized designs, driven by the "design freq" band-tab
        # row + slider in the UI (which sends design_freq_mhz on the
        # request). Skipping it here too prevents the auto-derived
        # schema slider from duplicating that control.
        if key in ("freq", "design_freq"):
            continue
        # `hidden`: the design pins this param at its default and suppresses its
        # control. The value still flows through every solve (it's in
        # default_params, which _build_builder seeds from), so this is a
        # display-only override — used to drop a knob that's degenerate with
        # another (e.g. a `_frac` that only ever multiplies `length_factor`).
        # Checked before the group/scalar branches so it applies to any kind.
        override_raw = ui.get(key)
        if isinstance(override_raw, dict) and override_raw.get("hidden"):
            continue
        # Repeating-group default: tuple/list of dicts → ParamGroupSpec.
        # The ui_params override (if any) carries the group-level
        # config (label_template, repeat_count, max_repeats,
        # link_meas_freq_to_param) plus per-leaf override dicts.
        if (
            isinstance(default, (tuple, list))
            and default
            and all(isinstance(x, dict) for x in default)
        ):
            group_override = ui.get(key)
            if not isinstance(group_override, dict):
                group_override = {}
            group_spec = _group_spec_from_default(
                key, default, group_override, default_params
            )
            if group_spec is not None:
                specs.append(group_spec)
            continue
        override = ui.get(key)
        if override is not None and not isinstance(override, dict):
            # Reserved scalar (e.g. `target_z0`) — not a per-param spec.
            continue
        spec = _auto_paramspec(key, default, override)
        if spec is not None:
            specs.append(spec)
    return tuple(specs)


# ---------------------------------------------------------------------------
# Builder construction from a request dict
# ---------------------------------------------------------------------------


def _rehydrate_param(default_value: Any, raw: Any) -> Any:
    if isinstance(default_value, complex) and isinstance(raw, dict):
        return complex(float(raw.get("re", 0.0)), float(raw.get("im", 0.0)))
    if isinstance(default_value, bool):
        return bool(raw)
    if isinstance(default_value, int) and not isinstance(default_value, bool):
        return int(raw)
    if isinstance(default_value, float):
        return float(raw)
    return raw


def _build_builder(cls, req: dict):
    """Construct a Builder from default_params overlaid with request fields.

    The momwire frontend assembles its solve request by Object.assign'ing
    every live slider value as a *top-level* key on the request dict
    (App.tsx:buildRequest), so we read each Builder param off the request
    directly. A nested `params` dict is also accepted as a fallback for
    other clients.
    """
    # Seed from the named variant (e.g. `opt_params`, `z50_params`).
    # Unrecognised / absent → fall back to default_params.
    base = _strip_ui(_variant_params(cls, req.get("variant")))
    nested = req.get("params") or {}
    for k in list(base.keys()):
        if k in req:
            base[k] = _rehydrate_param(base[k], req[k])
        elif k in nested:
            base[k] = _rehydrate_param(base[k], nested[k])
    builder = cls(params=base)
    # n_per_wire drives the per-Builder nominal_nsegs (the convergence
    # sweep at /converge overrides this value per N). Each generator
    # decides which per-edge segment counts scale with it and which stay
    # fixed (feed gaps). See AntennaBuilder.FRAMEWORK_PARAMS.
    n_per_wire = req.get("n_per_wire")
    if n_per_wire is not None:
        builder.nominal_nsegs = int(n_per_wire)
    return builder


def _ground_for_engine(req: dict, ground_z: float):
    ground_on = bool(req.get("ground", False))
    if not ground_on:
        return None
    # momwire only models a PEC ground in the impedance solve, so ground=True
    # maps to the PEC image method here. (PyNEC's finite-ground mapping lives
    # in _pynec_ground_spec.)
    return "pec"


def _pynec_ground_spec(req: dict):
    """Map the frontend's ground knobs to PyNECEngine's ground spec, matching
    the UI labels: ground=True gives the Sommerfeld-Norton finite ground with
    DEFAULT_GROUND's eps_r=10, sigma=0.002; ground_fast=True downgrades to
    NEC's reflection-coefficient approximation; ground off is free space."""
    if not req.get("ground", False):
        return "free"
    if req.get("ground_fast", False):
        return ("finite-fast",) + DEFAULT_GROUND[1:]
    return DEFAULT_GROUND


def _make_momwire_engine(req: dict, builder, cancel=None):
    model = req.get("momwire_model", "triangular")
    solver_cls = _MOMWIRE_MODELS.get(model, TriangularSolver)
    wire_radius = float(req.get("wire_radius", 0.0005))
    ground = _ground_for_engine(req, 0.0)
    solver_kwargs = req.get("model_options") or None
    return MomwireEngine(
        builder,
        solver=solver_cls,
        wire_radius=wire_radius,
        solver_kwargs=solver_kwargs,
        ground=ground,
        cancel=cancel,
    )


def _make_pynec_engine(req: dict, builder):
    return PyNECEngine(builder, ground=_pynec_ground_spec(req))


# ---------------------------------------------------------------------------
# Response packing
# ---------------------------------------------------------------------------


# Frontend Fresnel reflection treats this as the real part of the
# complex permittivity. For PEC the reflection coefficient ρ_h → −1 as
# eps_r → ∞; 1e10 is large enough to be numerically indistinguishable
# while staying away from float overflow. Matches momwire/web/server.py.
_PEC_GROUND_EPS_R = 1.0e10
_PEC_GROUND_SIGMA = 0.0


def _pack_wires(currents) -> list[dict]:
    return [
        {
            "label": f"wire{idx}",
            "knot_positions": w.knot_positions.tolist(),
            "knot_currents_re": w.knot_currents.real.tolist(),
            "knot_currents_im": w.knot_currents.imag.tolist(),
        }
        for idx, w in enumerate(currents)
    ]


def _primary_feed(engine):
    """(polyline_idx, arclength) of the driven feed, or None.

    MomwireEngine exposes `_feeds = [(polyline_idx, arclength, voltage)]`
    post-translator. For network-spec designs the geometry translator
    registers a feed for every named edge — including non-driven ports
    like trap stubs — so `_feeds[0]` is whichever named tuple appears
    first in `build_wires()`, not necessarily the driven feed. Look up
    the driven port's `_feeds` entry by index when a Network is present.
    """
    feeds = getattr(engine, "_feeds", None) or []
    feed_names = getattr(engine, "_feed_names", None) or []
    if not feeds:
        return None
    feed_idx = 0
    network = getattr(engine, "_network", None)
    if network is not None and network.sources:
        # The first Driven source is the primary feed. If it resolves to a
        # real (PortAtEdge) port, use its position; otherwise (virtual port,
        # e.g. delta_looparray_network's "driver"), fall back to feeds[0].
        driven_name = network.sources[0].port
        if driven_name in feed_names:
            feed_idx = feed_names.index(driven_name)
    pl_idx, arclen, _v = feeds[feed_idx]
    return int(pl_idx), float(arclen)


def _interp_polyline(knots, cum, arclen):
    """3D point at `arclen` along a polyline (knots + cumulative arclength)."""
    arclen = min(max(arclen, 0.0), float(cum[-1]))
    seg = int(np.searchsorted(cum, arclen, side="right")) - 1
    seg = min(max(seg, 0), len(knots) - 2)
    span = cum[seg + 1] - cum[seg]
    t = 0.0 if span <= 0 else (arclen - cum[seg]) / span
    return (knots[seg] + t * (knots[seg + 1] - knots[seg])).tolist()


def _feed_indices(engine, currents) -> tuple[int, int]:
    """Pick a (wire, knot) for the feed marker — the knot nearest the feed.

    Kept for the feed_knot_index the frontend uses to read feed current and
    split the current envelope. The visible marker dot uses `_feed_position`
    instead (exact, not snapped to a knot).
    """
    pf = _primary_feed(engine)
    if pf is None:
        return 0, 0
    pl_idx, arclen = pf
    if pl_idx >= len(currents):
        return 0, 0
    knots = currents[pl_idx].knot_positions
    if knots.shape[0] < 2:
        return pl_idx, 0
    # Cumulative arclength along the polyline.
    deltas = np.linalg.norm(np.diff(knots, axis=0), axis=1)
    cum = np.concatenate([[0.0], np.cumsum(deltas)])
    j = int(np.argmin(np.abs(cum - arclen)))
    return pl_idx, j


def _feed_position(engine, currents):
    """Exact 3D feed point for the primary feed — the physical location the
    solver actually feeds, independent of where segment knots fall. Avoids
    the half-segment marker shift from snapping to the nearest knot, which
    lands on an endpoint when the feed edge has no interior knot (e.g. a
    1-segment driven stub under odd-parity bases like sinusoidal/Bspline=2).
    """
    pf = _primary_feed(engine)
    if pf is None:
        return None
    pl_idx, arclen = pf
    if pl_idx >= len(currents):
        return None
    knots = currents[pl_idx].knot_positions
    if knots.shape[0] < 2:
        return knots[0].tolist() if knots.shape[0] else None
    deltas = np.linalg.norm(np.diff(knots, axis=0), axis=1)
    cum = np.concatenate([[0.0], np.cumsum(deltas)])
    return _interp_polyline(knots, cum, arclen)


def _pynec_feed_indices(builder, currents) -> tuple[int, int]:
    """PyNECEngine returns one WireCurrents per build_wires() tuple in
    the same order, so the feed wire index is the position of the tuple
    that carries the driven port. Place the marker on that wire's centre
    knot — close enough to NEC's per-segment feed for a UI dot.

    Network-spec designs route excitation through build_network() rather
    than the per-tuple `ev` field. Network-spec named tuples include
    non-driven ports (trap stubs, TL endpoints), so we look up the driven
    port's name and pick the tuple that matches.
    """
    tuples = list(builder.build_wires())
    driven_name = None
    if hasattr(builder, "build_network"):
        net = builder.build_network()
        if net is not None and net.sources:
            driven_name = net.sources[0].port
    for i, t in enumerate(tuples):
        ev = t[3]
        name = t[4] if len(t) >= 5 else None
        # Network-spec path: only the named tuple matching the Driven port.
        # Legacy path (no network): first `ev` is the feed.
        if driven_name is not None:
            if name != driven_name:
                continue
        elif ev is None:
            continue
        if i >= len(currents):
            return 0, 0
        k = currents[i].knot_positions.shape[0]
        return i, k // 2
    return 0, 0


def _pynec_feed_position(builder, currents):
    """Exact 3D feed point for PyNEC: the midpoint of the driven segment.
    NEC feeds at segment (n_seg+1)//2, so on a 1-segment feed edge the feed
    sits at the edge midpoint — not the wire's centre knot (`k//2`), which
    lands on an endpoint for a 2-knot wire. Mirrors `_pynec_feed_indices`'
    driven-tuple selection.
    """
    tuples = list(builder.build_wires())
    driven_name = None
    if hasattr(builder, "build_network"):
        net = builder.build_network()
        if net is not None and net.sources:
            driven_name = net.sources[0].port
    for i, t in enumerate(tuples):
        ev = t[3]
        name = t[4] if len(t) >= 5 else None
        if driven_name is not None:
            if name != driven_name:
                continue
        elif ev is None:
            continue
        if i >= len(currents):
            return None
        knots = currents[i].knot_positions
        n_seg = knots.shape[0] - 1
        if n_seg < 1:
            return knots[0].tolist() if knots.shape[0] else None
        mid_seg = (n_seg + 1) // 2  # 1-indexed driven segment
        return (0.5 * (knots[mid_seg - 1] + knots[mid_seg])).tolist()
    return None


# ---------------------------------------------------------------------------
# Example factory
# ---------------------------------------------------------------------------


def _discover_variants(cls) -> tuple[str, ...]:
    """Names of every class-level `<name>_params` attribute (the variant
    convention used across the design library — e.g. `default_params`,
    `opt_params`, `z50_params`, `current_physical_params`). The
    returned list is suitable for a UI selector; the bare names (no
    `_params` suffix) are what the frontend sends back in the request.

    `default` is always first if present, so the UI lists it as the
    canonical starting point regardless of class attribute order.
    """
    suffix = "_params"
    found: list[str] = []
    for attr in dir(cls):
        if not attr.endswith(suffix) or attr.startswith("_"):
            continue
        v = getattr(cls, attr, None)
        # MappingProxyType / dict only — skip e.g. a method that happens
        # to end in _params.
        if not hasattr(v, "keys"):
            continue
        name = attr[: -len(suffix)]
        if name:
            found.append(name)
    # `default` first, rest in stable (alphabetical) order.
    found.sort(key=lambda n: (n != "default", n))
    return tuple(found)


def _serialize_param_values(params: dict) -> dict:
    """JSON-encode a params dict for shipping to the frontend.

    Complex values become {"re": ..., "im": ...} (matches the same
    shape `_rehydrate_param` accepts on the way back). Bool/int/float
    pass through. Anything exotic (None, strings that aren't enum
    options, etc.) passes through too — the frontend just ignores
    keys it doesn't have sliders for.
    """
    out: dict = {}
    for k, v in params.items():
        if isinstance(v, complex):
            out[k] = {"re": float(v.real), "im": float(v.imag)}
        else:
            out[k] = v
    return out


def _variant_params(cls, variant: str | None) -> dict:
    """Return the seed params dict for the named variant, overlaid on
    `default_params` (see `resolve_variant_params`). A variant need only
    list the keys it overrides — including nested `ui_params` hints, which
    deep-merge — and missing keys come from `default_params`. Falls back to
    `default_params` when variant is None, "default", or doesn't resolve to
    an attribute (stale frontend, unknown name)."""
    return resolve_variant_params(cls, variant)


def _ui_scalar(default_params: dict, key: str, default):
    ui = default_params.get("ui_params") or {}
    if key in ui and not isinstance(ui[key], dict):
        return ui[key]
    return default


_ARRAY_BASES = (
    Array1x2Builder,
    Array2x2Builder,
    Array1x4Builder,
    Array1x4GroupedBuilder,
    Array2x4Builder,
)


def _auto_target_z0(cls) -> float:
    """Default reference impedance for the SWR readout.

    Array designs scale 50 Ω by the element count (1×2 → 100, 2×2 → 200,
    2×4 → 400, ...) — the convention that each branch in the splitter
    sees 50 Ω after the chain of impedance transformers, so the
    combined driving point lands at N × 50.

    Everything else defaults to 50 Ω. Designs that violate either
    convention (turnstiles with per-port 50 Ω matching, designs tuned
    to 75 Ω, etc.) override via `ui_params["target_z0"]`.
    """
    if not issubclass(cls, _ARRAY_BASES):
        return 50.0
    try:
        b = cls()
        n_feeds = sum(1 for *_, ev in b.build_wires() if ev is not None)
    except Exception:
        return 50.0
    return 50.0 * max(1, n_feeds)


def _auto_multi_feed(cls) -> bool:
    """Detect whether the design has more than one excited wire.

    Builders that drive >1 feed wire in `build_wires()` get multi_feed=True
    by default — the response shape switches to include a `feeds` array
    (per-port Z + V) and the frontend renders the per-feed table.

    Designs can still force the flag via `ui_params["multi_feed"]` — set
    False to suppress the per-feed table even when multiple excitations
    exist (e.g. mirror-symmetric arrays where the per-port Z is identical
    by construction and the extra column adds no information).
    """
    try:
        b = cls()
        n_feeds = sum(1 for *_, ev in b.build_wires() if ev is not None)
    except Exception:
        return False
    return n_feeds > 1


def _auto_default_view(cls) -> str:
    """Pick a 2D projection from the spans of the antenna's wires.

    Rule: if x_span is small (the antenna lies in the y-z plane —
    typical for dipoles, V's, loops, fan/bowtie variants), default to
    `yz`. Otherwise return the plane of the two largest spans (xy / yz
    / xz). The 0.5 m threshold catches feed-gap micro-offsets like
    fan_dipole's 0.22 m without flipping to xy.

    Hand-overridden via ui_params['default_view']; designs whose axis
    layout doesn't match this rule (vertical, moxonarray) supply the
    explicit value.
    """
    try:
        b = cls()
        pts = []
        for p0, p1, _n, _e in b.build_wires():
            pts.append(p0)
            pts.append(p1)
        a = np.asarray(pts, dtype=float)
    except Exception:
        return "xy"
    sx = float(a[:, 0].max() - a[:, 0].min())
    sy = float(a[:, 1].max() - a[:, 1].min())
    sz = float(a[:, 2].max() - a[:, 2].min())
    if sx < 0.5:
        return "yz"
    spans = sorted([("x", sx), ("y", sy), ("z", sz)], key=lambda t: t[1], reverse=True)
    return "".join(sorted(s[0] for s in spans[:2]))


@lru_cache(maxsize=None)
def _recommended_backend(cls) -> str | None:
    """Recommend a default solver for the design, or None to let the UI keep
    its own default (the dense Triangular path).

    Returns "arrayblock" for true grid arrays — multiple electrically separate
    elements with at least one repeated shape — where the element-aware block
    solver is dramatically faster than the dense default (e.g. bowtiearray2x4:
    ~1 s vs ~8 s). Single-element designs, and multi-element designs whose
    elements are all distinct (Yagi-style), keep the dense default so their
    basis/results are unchanged. Detection is geometry-only (no solve) and any
    failure falls back to None.

    Memoised per design class: it already runs only once per design at registry
    build (the result is baked into the immutable `AntennaExample`, which the
    /examples endpoint and the frontend read at runtime — a slider change never
    re-runs it), but `lru_cache` makes that a hard guarantee regardless of
    call site.
    """
    try:
        from momwire.array_block import _wire_to_element

        builder = _build_builder(cls, {})
        eng = _make_momwire_engine({}, builder)
        polylines = [np.asarray(p, dtype=float) for p in eng._polylines]
    except Exception:
        return None
    if len(polylines) < 2:
        return None
    wire_elem, n_elem = _wire_to_element(polylines)
    # array-block only pays off for a genuine grid array: several elements where
    # ONE shape repeats many times (so per-shape block reuse dominates). Require
    # at least 4 elements — below that the speedup is marginal and 2-element
    # symmetric things (a split dipole, a 1x2) are ambiguous.
    if n_elem < 4:
        return None
    # Signature each element by its points recentred on its own centroid, then
    # require repetition to *dominate*: at least half the elements must be
    # duplicates of another (len(sigs) * 2 <= n_elem). The earlier test
    # (len(sigs) < n_elem) fired on a single repeated pair, which wrongly tagged
    # Yagis (their equal-length directors collapse to one signature while the
    # driven element and reflector stay distinct) as arrays.
    sigs = set()
    for e in range(n_elem):
        pts = np.vstack(
            [polylines[w] for w in range(len(polylines)) if wire_elem[w] == e]
        )
        pts = pts - pts.mean(axis=0)
        key = np.round(pts / 1e-4).astype(np.int64)
        key = key[np.lexsort(key.T)]
        sigs.add(key.tobytes())
    return "arrayblock" if len(sigs) * 2 <= n_elem else None


def _derive_sweep_policy(ui: dict) -> SweepPolicy:
    """Build a SweepPolicy from a `ui_params` dict's `sweep_policy` entry.

    Accepts the positional 3-tuple `(anchor, lo_factor, hi_factor)` form or the
    dict form (which can opt into named fields like `band_locked` without
    supplying every positional; missing fields fall back to the dataclass
    defaults). Anything else yields the default policy. Takes any ui dict, so
    the same derivation runs for the default's ui_params and for each variant's
    deep-merged ui_params (see `variant_ui` in `_make_example`)."""
    raw = ui.get("sweep_policy")
    if isinstance(raw, (tuple, list)) and len(raw) == 3:
        return SweepPolicy(
            anchor=str(raw[0]),
            lo_factor=float(raw[1]),
            hi_factor=float(raw[2]),
        )
    if isinstance(raw, dict):
        d = DEFAULT_SWEEP_POLICY
        return SweepPolicy(
            anchor=str(raw.get("anchor", d.anchor)),
            lo_factor=float(raw.get("lo_factor", d.lo_factor)),
            hi_factor=float(raw.get("hi_factor", d.hi_factor)),
            band_locked=bool(raw.get("band_locked", d.band_locked)),
        )
    return DEFAULT_SWEEP_POLICY


def _make_example(name: str, cls, *, defer_hints: bool = False) -> AntennaExample:
    dp = dict(cls.default_params)
    ui = dict(dp.get("ui_params") or {})

    # UI hints that need the built geometry — multi_feed, default_view, the
    # array target_z0, and the recommended array-block backend — are derived
    # by running the builder. They're computed once and memoised in `hints()`.
    #
    # Built-in designs prime them eagerly at registration (defer_hints=False)
    # so /examples and the array-block seed are correct up front. User designs
    # defer them (defer_hints=True): a slow or hanging build_wires never runs at
    # startup or on a page refresh — only when that design is actually selected
    # and solved, where the builder runs anyway and the closures fold the hints
    # into the solve/geometry response. A design can pin any hint statically in
    # ui_params to override the derived value.
    view_override = _ui_scalar(dp, "default_view", None)
    z0_override = _ui_scalar(dp, "target_z0", None)
    multi_feed_override = _ui_scalar(dp, "multi_feed", None)

    _hints: dict[str, Any] = {}

    def hints() -> dict[str, Any]:
        if not _hints:
            _hints["default_view"] = (
                str(view_override)
                if view_override is not None
                else _auto_default_view(cls)
            )
            _hints["target_z0"] = float(
                z0_override if z0_override is not None else _auto_target_z0(cls)
            )
            _hints["multi_feed"] = bool(
                multi_feed_override
                if multi_feed_override is not None
                else _auto_multi_feed(cls)
            )
            _hints["default_backend"] = _recommended_backend(cls)
        return _hints

    # Grid-level layout config (reserved ui_params["layout"]). A dict today
    # carrying {"columns": int}; ignore non-dicts so a stray value can't
    # break registration. None keeps the responsive auto-flow grid.
    layout_raw = ui.get("layout")
    grid_layout = dict(layout_raw) if isinstance(layout_raw, dict) else None

    meas_range = (
        ui.get("meas_freq_range")
        if not isinstance(ui.get("meas_freq_range"), dict)
        else None
    )
    bands_override = ui.get("bands") if not isinstance(ui.get("bands"), dict) else None
    sweep_policy = _derive_sweep_policy(ui)

    # Band tabs default to the HF amateur set in canonical order. The
    # frontend snaps to whichever band contains the design's native
    # `freq` (looked up from the param schema's freq default) — see
    # the useEffect on currentExample in App.tsx. Designs can still
    # override via ui_params['bands'].
    if bands_override is not None:
        bands = tuple(BandSpec(*b) for b in bands_override)
    else:
        bands = DEFAULT_HF_BANDS

    param_schema = _derive_schema(dp)
    has_design_freq = "design_freq" in dp
    variants = _discover_variants(cls)

    # Per-variant UI hints. A variant's `ui_params` deep-merges over the
    # default's (resolve_variant_params), so a variant can flip a single nested
    # hint (e.g. sweep_policy.band_locked) without restating the subtree. We
    # emit only the variants whose derived hints differ from the design-level
    # (default) value; the frontend falls back to the top-level field otherwise.
    # Extensible per-variant map so more hints can move per-variant later
    # without another /examples contract change.
    variant_ui: dict[str, dict[str, Any]] = {}
    for v in variants:
        if v == "default":
            continue
        v_ui = dict(resolve_variant_params(cls, v).get("ui_params") or {})
        v_sweep = _derive_sweep_policy(v_ui)
        if v_sweep != sweep_policy:
            variant_ui[v] = {"sweep_policy": v_sweep}

    def _design_freq_default(req: dict) -> float:
        # The active variant's `freq` is the right fallback when the
        # request hasn't supplied design_freq_mhz yet — different
        # variants of one design can target different bands (e.g.
        # hexbeam's opt vs default).
        vp = _variant_params(cls, req.get("variant"))
        return float(vp.get("freq", 14.0))

    def count_basis(req: dict):
        """Total wire segments (≈ MoM basis functions, the N×N matrix dim) the
        request would build. Geometry-only (cheap) — runs build_wires but no
        solve. Returns None if the geometry can't be built; the real solve then
        surfaces the underlying error instead of a spurious size rejection."""
        try:
            builder = _build_builder(cls, req)
            return sum(int(w[2]) for w in builder.build_wires())
        except Exception:
            return None

    def momwire_solve(req: dict, cancel=None) -> dict:
        design_freq = float(req.get("design_freq_mhz", _design_freq_default(req)))
        meas_freq = float(req.get("measurement_freq_mhz", design_freq))
        builder = _build_builder(cls, req)
        builder.freq = meas_freq
        # For design_freq-sized designs the geometry computes from
        # design_freq via build_wires(); apply the request's
        # design_freq_mhz so dragging the design-freq slider actually
        # retunes the antenna. Top-level designs don't carry the
        # parameter so the attribute write would be silently absorbed
        # into _params and never read — guard on has_design_freq.
        if has_design_freq:
            builder.design_freq = design_freq
        eng = _make_momwire_engine(req, builder, cancel=cancel)
        t0 = time.perf_counter()
        zs = eng.impedance()
        currents = eng.current_distribution()
        solve_ms = (time.perf_counter() - t0) * 1e3
        feed_wire_idx, feed_knot_idx = _feed_indices(eng, currents)
        z_primary = zs[0] if zs else complex(0.0, 0.0)
        out = {
            "geometry": name,
            "wires": _pack_wires(currents),
            "feed_wire_index": feed_wire_idx,
            "feed_knot_index": feed_knot_idx,
            "feed_position": _feed_position(eng, currents),
            "z_in_re": float(z_primary.real),
            "z_in_im": float(z_primary.imag),
            "design_freq_mhz": design_freq,
            "measurement_freq_mhz": meas_freq,
            "lambda_design_m": C_LIGHT / (design_freq * 1e6),
            "solve_ms": solve_ms,
            "ground": bool(req.get("ground", False)),
            "height_m": 0.0,
            "ground_eps_r": _PEC_GROUND_EPS_R,
            "ground_sigma": _PEC_GROUND_SIGMA,
            "z0_ohms": hints()["target_z0"],
            # Geometry-derived UI hints, folded into the response so user
            # designs (which defer them) get correct values the moment they're
            # selected, without running the builder at registration.
            "multi_feed": hints()["multi_feed"],
            "default_view": hints()["default_view"],
            # Fraction of input power actually radiated (1.0 unless the design
            # has resistive loads, e.g. a terminated rhombic / T2FD);
            # current_distribution() above populated it on the engine.
            "radiation_efficiency": float(getattr(eng, "_excited_efficiency", 1.0)),
            # Source input power in watts: the server's gain normaliser is
            # η₀k²/(8π·P_in), which is what makes the plot GAIN (load and
            # ground losses live inside P_in, so no efficiency multiply).
            "input_power_w": float(eng.input_power()),
        }
        if hints()["multi_feed"] and len(zs) > 1:
            # Pull per-feed drive voltages off the engine so the frontend
            # can render each feed's phase indicator. MomwireEngine stores
            # _feeds = [(polyline_idx, arclength, voltage)]; fall back to
            # 1+0j (the canonical unit drive) when missing.
            voltages = [f[2] for f in (getattr(eng, "_feeds", None) or [])]
            voltages += [complex(1.0, 0.0)] * (len(zs) - len(voltages))
            out["feeds"] = [
                {
                    "z_re": float(z.real),
                    "z_im": float(z.imag),
                    "v_re": float(v.real),
                    "v_im": float(v.imag),
                }
                for z, v in zip(zs, voltages)
            ]
        return out

    def momwire_geometry(req: dict) -> dict:
        # Geometry-only snapshot: build the engine (cheap — geometry is
        # resolved in the constructor) and read its wire knot positions
        # without solving. The frontend draws this immediately on antenna
        # selection so a large design's shape shows up right away instead of
        # waiting tens of seconds for the MoM solve. Mirrors momwire_solve's
        # builder setup but returns zero currents and omits impedance / far
        # field (the live solve fills those in).
        design_freq = float(req.get("design_freq_mhz", _design_freq_default(req)))
        meas_freq = float(req.get("measurement_freq_mhz", design_freq))
        builder = _build_builder(cls, req)
        builder.freq = meas_freq
        if has_design_freq:
            builder.design_freq = design_freq
        eng = _make_momwire_engine(req, builder)
        geom = eng.geometry_distribution()
        feed_wire_idx, feed_knot_idx = _feed_indices(eng, geom)
        return {
            "geometry": name,
            "wires": _pack_wires(geom),
            "feed_wire_index": feed_wire_idx,
            "feed_knot_index": feed_knot_idx,
            "feed_position": _feed_position(eng, geom),
            "design_freq_mhz": design_freq,
            "measurement_freq_mhz": meas_freq,
            "lambda_design_m": C_LIGHT / (design_freq * 1e6),
            "ground": bool(req.get("ground", False)),
            "z0_ohms": hints()["target_z0"],
            # Carry the geometry-derived hints on the fast preview too: it's the
            # first request fired on selection, so a deferred user design gets
            # its multi_feed / default_view here, before the live solve lands.
            # default_backend lets the frontend seed the array-block solver from
            # the preview and then fire the first solve — no /examples-descriptor
            # dependency, so this stays correct if a design's hints go lazy.
            "multi_feed": hints()["multi_feed"],
            "default_view": hints()["default_view"],
            "default_backend": hints()["default_backend"],
            "preview": True,
        }

    def pynec_build(req: dict) -> dict:
        # web.pynec_backend.pattern() expects this to return a build
        # dict with at least:
        #   context      — a nec_context with geometry built, ground
        #                  card applied, and excitation cards in place
        #   feed_seg     — 1-indexed segment number of the source
        #                  (only consulted by the default _run_solve()
        #                  excite path; ours supplies pynec_pattern_excite
        #                  so it's only present for parity)
        #   feed_tag     — NEC wire tag carrying the feed
        #   n_per_wire   — historical, _run_solve threads it through
        #                  but doesn't actually use it
        #   ground       — bool (informational; gn_card already on the
        #                  context)
        #   ground_fast  — bool (same)
        #   z_offset     — antenna height above ground, surfaced in
        #                  the pattern response
        #   _engine      — keep the PyNECEngine alive so the
        #                  underlying nec_context isn't released
        #                  before rp_card runs
        design_freq = float(req.get("design_freq_mhz", _design_freq_default(req)))
        meas_freq = float(req.get("measurement_freq_mhz", design_freq))
        builder = _build_builder(cls, req)
        builder.freq = meas_freq
        if has_design_freq:
            builder.design_freq = design_freq
        eng = _make_pynec_engine(req, builder)
        # Find the first excited wire to fill the feed_seg / feed_tag
        # parity fields. PyNECEngine.excitation_pairs is (tag, sub_seg,
        # voltage); take the first.
        feed_tag, feed_seg, _v = (eng.excitation_pairs or [(1, 1, 0)])[0]
        return {
            "context": eng.c,
            "feed_seg": int(feed_seg),
            "feed_tag": int(feed_tag),
            "n_per_wire": 1,
            "ground": bool(req.get("ground", False)),
            "ground_fast": bool(req.get("ground_fast", False)),
            "z_offset": 0.0,
            "_engine": eng,
        }

    def pynec_pattern_excite(b: dict, freq_mhz: float) -> None:
        # PyNECEngine already applied the gn_card and ex_card during
        # _build_geometry, so the pattern endpoint only needs to set
        # the frequency and execute. Reusing _run_solve() would add a
        # second ex_card on top of the one already in place.
        c = b["context"]
        c.fr_card(0, 1, float(freq_mhz), 0)
        c.xq_card(0)

    def pynec_solve(req: dict) -> dict:
        # Mirror momwire_solve but route through PyNECEngine. Response
        # shape is identical so the frontend renders the result the
        # same way; the `solver` field gets stamped to "pynec" by
        # server.solve()'s outer wrapper.
        design_freq = float(req.get("design_freq_mhz", _design_freq_default(req)))
        meas_freq = float(req.get("measurement_freq_mhz", design_freq))
        builder = _build_builder(cls, req)
        builder.freq = meas_freq
        if has_design_freq:
            builder.design_freq = design_freq
        eng = _make_pynec_engine(req, builder)
        t0 = time.perf_counter()
        zs = eng.impedance()
        currents = eng.current_distribution()
        solve_ms = (time.perf_counter() - t0) * 1e3
        feed_wire_idx, feed_knot_idx = _pynec_feed_indices(builder, currents)
        z_primary = zs[0] if zs else complex(0.0, 0.0)
        out = {
            "geometry": name,
            "wires": _pack_wires(currents),
            "feed_wire_index": feed_wire_idx,
            "feed_knot_index": feed_knot_idx,
            "feed_position": _pynec_feed_position(builder, currents),
            "z_in_re": float(z_primary.real),
            "z_in_im": float(z_primary.imag),
            "design_freq_mhz": design_freq,
            "measurement_freq_mhz": meas_freq,
            "lambda_design_m": C_LIGHT / (design_freq * 1e6),
            "solve_ms": solve_ms,
            "ground": bool(req.get("ground", False)),
            "height_m": 0.0,
            # The engine solved over the Sommerfeld finite ground, so ship its
            # real eps_r/sigma: the frontend's far-field cut applies PEC image
            # + Fresnel with these, which tracks NEC's finite-ground rp_card
            # pattern to ~0.2 dB. (momwire keeps the PEC constants — its
            # impedance solve genuinely is PEC-image.)
            "ground_eps_r": (
                DEFAULT_GROUND[1] if req.get("ground", False) else _PEC_GROUND_EPS_R
            ),
            "ground_sigma": (
                DEFAULT_GROUND[2] if req.get("ground", False) else _PEC_GROUND_SIGMA
            ),
            "z0_ohms": hints()["target_z0"],
            "multi_feed": hints()["multi_feed"],
            "default_view": hints()["default_view"],
            # Same fields as the momwire path, so switching engines in the UI
            # keeps the far-field plot meaning GAIN. current_distribution()
            # set both from the solved feed/load currents.
            "radiation_efficiency": float(getattr(eng, "_excited_efficiency", 1.0)),
            "input_power_w": float(getattr(eng, "_excited_p_in", None) or 0.0),
        }
        if hints()["multi_feed"] and len(zs) > 1:
            # PyNECEngine.excitation_pairs is [(tag, sub_seg, voltage)];
            # pull the voltage off each so per-feed phase comes through.
            voltages = [v for _t, _s, v in (eng.excitation_pairs or [])]
            voltages += [complex(1.0, 0.0)] * (len(zs) - len(voltages))
            out["feeds"] = [
                {
                    "z_re": float(z.real),
                    "z_im": float(z.imag),
                    "v_re": float(v.real),
                    "v_im": float(v.imag),
                }
                for z, v in zip(zs, voltages)
            ]
        return out

    def params_source(req: dict) -> str:
        # Overlay the request's live knob values onto the chosen variant's
        # params (which still carry ui_params and the design's real nesting —
        # bands tuples etc.), then serialise. Knob-values-only by default
        # (include_ui), matching the manual "copy the printed values" workflow
        # this replaces; pass include_ui=true to emit a wholesale block.
        from antennaknobs.serialize import _precision_map
        from antennaknobs.serialize import params_source as _emit

        variant = req.get("variant")
        base = dict(_variant_params(cls, variant))  # retains ui_params
        ui = base.get("ui_params")
        nested = req.get("params") or {}
        for k in list(base.keys()):
            if k == "ui_params":
                continue
            if k in req:
                base[k] = _rehydrate_param(base[k], req[k])
            elif k in nested:
                base[k] = _rehydrate_param(base[k], nested[k])
        # A variant is stored as an *overlay* on default_params (only the keys it
        # changes — see resolve_variant_params), so emit its block that way too:
        # trim to just the deltas from default_params. This matches the minimal
        # hand-authored form and keeps a copied variant paste-ready as a
        # <variant>_params overlay. default_params itself is the baseline, so it
        # is always emitted in full. A stale / unknown variant name (one with no
        # <variant>_params attribute) resolves to default_params, where a delta
        # would be an empty, misleading block — so fall back to the full block.
        v_attr = (
            getattr(cls, f"{variant}_params", None)
            if variant and variant != "default"
            else None
        )
        if v_attr is not None and hasattr(v_attr, "keys"):
            name = f"{variant}_params"
            emit = diff_params(dict(_variant_params(cls, "default")), base)
        else:
            name = (
                f"{variant}_params"
                if variant and variant != "default"
                else "default_params"
            )
            emit = base
        return _emit(
            emit,
            name=name,
            precision=_precision_map(ui),
            include_ui=bool(req.get("include_ui", False)),
            wrap="mappingproxy" if req.get("wrap") == "mappingproxy" else "dict",
        )

    def far_field_metrics(req: dict) -> dict:
        # Scalar metrics for the pattern-compare table. Uses the same builder
        # setup as momwire_solve and the momwire engine (so the numbers match
        # the client-derived lobe on screen), then summarises the full grid.
        from antennaknobs.far_field import pattern_metrics

        design_freq = float(req.get("design_freq_mhz", _design_freq_default(req)))
        meas_freq = float(req.get("measurement_freq_mhz", design_freq))
        builder = _build_builder(cls, req)
        builder.freq = meas_freq
        if has_design_freq:
            builder.design_freq = design_freq
        eng = _make_momwire_engine(req, builder)
        ff = eng.far_field(n_theta=90, n_phi=360, del_theta=1, del_phi=1)
        metrics = pattern_metrics(ff)
        metrics["measurement_freq_mhz"] = meas_freq
        return metrics

    def nec_export(req: dict) -> str:
        # Same builder construction as pynec_solve, then serialise to a NEC2
        # card deck. Ground/freq mirror what the live solve uses so the
        # downloaded deck matches the antenna the user is viewing.
        from antennaknobs.nec_export import export_nec as _export_nec

        design_freq = float(req.get("design_freq_mhz", _design_freq_default(req)))
        meas_freq = float(req.get("measurement_freq_mhz", design_freq))
        builder = _build_builder(cls, req)
        builder.freq = meas_freq
        if has_design_freq:
            builder.design_freq = design_freq
        ground = _ground_for_engine(req, 0.0) or "free"
        return _export_nec(builder, ground=ground, freq=meas_freq)

    def momwire_sweep(req: dict, freqs_mhz: list[float]):
        builder = _build_builder(cls, req)
        # MomwireEngine reads builder.freq only for the initial wavelength
        # passed to _make_solver — impedance_sweep overrides k per point.
        builder.freq = float(freqs_mhz[0]) if freqs_mhz else float(builder.freq)
        # Geometry is fixed across the sweep; honour the request's
        # design_freq so the sweep sees the same antenna the live
        # solve sees. See momwire_solve for the rationale.
        if has_design_freq:
            builder.design_freq = float(
                req.get("design_freq_mhz", _design_freq_default(req))
            )
        eng = _make_momwire_engine(req, builder)
        zs = np.asarray(eng.impedance_sweep(list(freqs_mhz)))
        # MomwireEngine.impedance_sweep returns (n_freqs, n_feeds).
        primary = zs[:, 0]
        re = primary.real.tolist()
        im = primary.imag.tolist()
        if hints()["multi_feed"] and zs.shape[1] > 1:
            feeds_re = zs.real.tolist()  # (n_freqs, n_feeds) list of lists
            feeds_im = zs.imag.tolist()
            return re, im, feeds_re, feeds_im
        return re, im

    # Static fields served by /examples. Built-ins prime hints() now (eager,
    # unchanged behaviour); user designs ship provisional values — overrides if
    # declared, else neutral defaults — and the real values arrive with the
    # first solve/geometry response (see the closures above).
    if defer_hints:
        field_multi_feed = (
            bool(multi_feed_override) if multi_feed_override is not None else False
        )
        # No view override and hints deferred → leave it None rather than
        # guessing "xy". The frontend keeps the current camera until the first
        # geometry/solve response carries the real auto-detected view, instead
        # of snapping to a wrong "xy" and then flipping when the preview lands.
        field_default_view = str(view_override) if view_override is not None else None
        field_default_backend = None
    else:
        h = hints()
        field_multi_feed = h["multi_feed"]
        field_default_view = h["default_view"]
        field_default_backend = h["default_backend"]

    return AntennaExample(
        name=name,
        label=name.replace("_", " "),
        momwire_solve=momwire_solve,
        momwire_sweep=momwire_sweep,
        momwire_geometry=momwire_geometry,
        count_basis=count_basis,
        default_backend=field_default_backend,
        pynec_solve=pynec_solve,
        pynec_build=pynec_build,
        pynec_pattern_excite=pynec_pattern_excite,
        nec_export=nec_export,
        params_source=params_source,
        far_field_metrics=far_field_metrics,
        multi_feed=field_multi_feed,
        param_schema=param_schema,
        bands=bands,
        meas_freq_range_mhz=tuple(meas_range) if meas_range else None,
        sweep_policy=sweep_policy,
        default_view=field_default_view,
        default_freq_mhz=float(dp["freq"]) if "freq" in dp else None,
        has_design_freq=has_design_freq,
        variants=variants,
        variant_values={
            v: _serialize_param_values(_strip_ui(_variant_params(cls, v)))
            for v in variants
        },
        variant_ui=variant_ui,
        layout=grid_layout,
    )


# ---------------------------------------------------------------------------
# Registration entrypoint
# ---------------------------------------------------------------------------


def list_designs() -> list[str]:
    """Discover every Builder file under designs/.

    Every design lives in a family subpackage (`dipoles/`, `loops/`,
    `arrays/`, …) and registers under the dotted path the user sees in
    the UI (`dipoles.invvee`) — the same convention as the Python import
    path, minus the leading `antennaknobs.designs.`. The dotted name
    is what `register_all` feeds back to importlib too. Any bare top-level
    `*.py` (none today) would register under its stem.
    """
    names: list[str] = []
    for p in sorted(DESIGNS_DIR.glob("*.py")):
        if p.stem.startswith("_"):
            continue
        names.append(p.stem)
    for sub in sorted(d for d in DESIGNS_DIR.iterdir() if d.is_dir()):
        if sub.name.startswith("_") or sub.name == "__pycache__":
            continue
        for p in sorted(sub.glob("*.py")):
            if p.stem.startswith("_"):
                continue
            names.append(f"{sub.name}.{p.stem}")
    return names


def register_all() -> list[str]:
    """Walk designs/ and register one AntennaExample per Builder class.

    Returns the list of design names that registered successfully. Any
    individual failure is swallowed and logged (a single broken design
    must not take down the whole web UI).
    """
    registered: list[str] = []
    for name in list_designs():
        try:
            mod = importlib.import_module(f"{DESIGNS_PKG}.{name}")
        except Exception as exc:
            print(f"[adapter] skip {name}: import error: {exc!r}")
            continue
        cls = getattr(mod, "Builder", None)
        if cls is None:
            continue
        try:
            cls()  # smoke-test that default_params constructs cleanly
            register(_make_example(name, cls))
            registered.append(name)
        except Exception as exc:
            print(f"[adapter] skip {name}: {exc!r}")
    return registered

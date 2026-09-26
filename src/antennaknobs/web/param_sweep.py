"""The Z-vs-parameter sweep's pure half (docs/design/z-vs-param-view.md).

``POST /param_sweep`` solves one design at a list of values of ONE parameter:
the mesh density (the request's ``n_per_wire``) or a numeric design knob (a
top-level request field). This module holds what the endpoint needs that is
not HTTP: which parameters may be swept and how a value is coerced, and the
gap-fed advisory. Framework-free, so it is tested without a server.
"""

from __future__ import annotations

import math
from collections.abc import Mapping

#: The density parameter: the request field every engine meshes from
#: (``AntennaBuilder.nominal_nsegs``, segments per λ/4 at the design
#: frequency). The same name on the wire and in the request.
DENSITY = "n_per_wire"

# Request fields that are never a knob, even when a design's params happen to
# share the name: the frequencies (a knob sweep holds the measurement
# frequency fixed; sweeping either is a frequency sweep) and the framework's
# own mesh field, which is DENSITY's.
_NOT_KNOBS = frozenset({"design_freq", "freq", "nominal_nsegs"})


class ParamSweepError(ValueError):
    """The request names a parameter or values that cannot be swept."""


def _knob_defaults(req: Mapping) -> dict:
    """The design's own params for the request's variant, ui hints stripped."""
    from .adapter import _strip_ui, _variant_params
    from .examples import example_for

    ex = example_for(req.get("geometry") or "")
    cls = getattr(ex, "builder_cls", None)
    if cls is None:
        return {}
    return _strip_ui(_variant_params(cls, req.get("variant")))


def _is_number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def sweep_values(req: Mapping, param, values) -> list:
    """``values`` coerced for ``param``, or ParamSweepError.

    Density takes positive integers. A knob must be one of the design's own
    numeric params (not a frequency); an ``int`` knob's values are rounded
    to integers, so a geometric ladder over a segment knob solves whole
    counts. Duplicates are kept in order: the client decides the ladder.
    """
    if not isinstance(param, str) or not param:
        raise ParamSweepError("param must be a parameter name")
    if not isinstance(values, list):
        raise ParamSweepError("values must be a list of numbers")
    out = []
    for v in values:
        if not _is_number(v) or not math.isfinite(v):
            raise ParamSweepError(f"values must be finite numbers (got {v!r})")
        out.append(v)
    if param == DENSITY:
        ints = [int(round(v)) for v in out]
        if any(n < 1 for n in ints):
            raise ParamSweepError("a density must be at least 1 segment")
        return ints
    defaults = _knob_defaults(req)
    default = defaults.get(param)
    if param in _NOT_KNOBS or not _is_number(default):
        numeric = sorted(
            k for k, v in defaults.items() if _is_number(v) and k not in _NOT_KNOBS
        )
        raise ParamSweepError(
            f"{param!r} is not a numeric knob of this design; sweepable: "
            + ", ".join([DENSITY, *numeric])
        )
    if isinstance(default, int):
        return [int(round(v)) for v in out]
    return [float(v) for v in out]


def request_at(req: Mapping, param: str, value) -> dict:
    """The request with ``param`` set to ``value`` — every point's request."""
    out = dict(req)
    out[param] = value
    return out


def _is_delta_gap(req: Mapping, solver_name: str) -> str | None:
    """The engine's display name when it models the source as a delta gap
    (a segment-wide gap), else None."""
    if solver_name == "nec2":
        return "NEC-2"
    if solver_name == "pynec":
        return "PyNEC"
    if solver_name != "momwire":
        return None
    opts = req.get("model_options")
    if isinstance(opts, Mapping) and opts.get("feed_model") == "segment":
        return f"{req.get('momwire_model') or 'momwire'} (segment gap)"
    if req.get("momwire_model") == "sinusoidal":
        return "Sinusoidal"
    return None


def _length(w) -> float:
    return math.dist(tuple(w.p0), tuple(w.p1))


def gap_feed_wire(req: Mapping, n_lo: int) -> tuple[float, float] | None:
    """``(feed wire length, segment length at n_lo)`` when the design is fed
    across a feed wire SHORTER THAN ONE SEGMENT at the coarsest density
    swept, else None.

    That is what makes a design gap-fed for this purpose: the excited wire
    is a dedicated gap, not part of the antenna's conductor, so as the
    density climbs its segment goes from much shorter than its neighbours
    to their size and beyond, and a delta-gap source reads that ratio (the
    catalog dipole's 0.1 m wire against 0.33 m segments at N = 8). A dipole
    fed at the middle of one wire, or a loop fed on a whole side, is never
    gap-fed. Geometry only, at the request's knobs; None when the geometry
    cannot be built (the solve surfaces that) or has no design frequency.
    """
    from ..wire_catalog import as_wire
    from .adapter import _build_builder
    from .examples import example_for

    try:
        cls = getattr(example_for(req.get("geometry") or ""), "builder_cls", None)
        if cls is None:
            return None
        builder = _build_builder(cls, dict(req))
        segment = 0.25 * float(builder.design_wavelength) / n_lo
        wires = [as_wire(t) for t in builder.build_wires()]
    except Exception:  # noqa: BLE001 — advisory only; the solve reports a bad geometry
        return None
    fed = [_length(w) for w in wires if w.ex is not None and w.ex != 0]
    short = [f for f in fed if f < segment]
    if not short or not math.isfinite(segment):
        return None
    return min(short), segment


def gap_fed_advisory(
    req: Mapping, param: str, values: list, solver_name: str
) -> dict | None:
    """The density sweep's warning (docs/design/z-vs-param-view.md): on a
    gap-fed design a delta-gap engine's density sweep mostly measures the
    feed-gap model. Measured on the catalog dipole over the 8…68 ladder:
    NEC-2 and sinusoidal R 59.9 → 71.7 Ω, B-spline 70.72 → 70.8 Ω."""
    if param != DENSITY or not values:
        return None
    engine = _is_delta_gap(req, solver_name)
    if engine is None:
        return None
    n_lo = min(values)
    gap = gap_feed_wire(req, n_lo)
    if gap is None:
        return None
    feed, segment = gap
    return {
        "category": "DeltaGapFeedConvergence",
        "text": (
            f"Density here mostly measures the delta-gap feed, not the "
            f"antenna: the source sits on a {feed:.2f} m feed wire, shorter "
            f"than one segment at N = {n_lo} ({segment:.2f} m), so the gap "
            f"segment's size against its neighbours changes along the sweep, "
            f"and {engine}'s delta-gap impedance moves with it. Read "
            f"convergence from a point-gap engine (B-spline)."
        ),
    }

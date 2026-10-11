"""How a design says its knob should be swept (AK#1975).

A knob sweep (the workbench's "Sweep this knob…", `antennaknobs sweep
--param`) defaults to the knob's whole slider range in a few linear points.
For most knobs that is right. For a tuner's coil or capacitor it is not: the
MFJ-926B capacitor runs 0–3961 pF, so 11 linear points step 396 pF, and the
20 m answer (39 pF) falls between the first two (Steve, 2026-10-10, tuning
`wire.doublet_remote_tuner` by hand on the Smith chart).

So a design may add a ``sweep`` entry to a knob's ``ui_params``:

    "tuner_c_pF": {"min": 0.0, "max": 3961.0,
                   "sweep": {"lo": 1.0, "log": True, "points": 81}},

any subset of ``lo``, ``hi`` (default: the knob's min / max), ``points`` and
``log``. The workbench's knob sweep and the command line's ``--param`` sweep
both start from it; an explicit range, point count or ``--log`` still wins.
A hint is distrusted like any authored value: one that cannot be swept (a
log range not above zero, a point count out of range, lo not below hi) is
dropped whole, never half-applied.
"""

from __future__ import annotations

from collections.abc import Mapping

# The workbench's own bounds on a sweep's points (lib/paramSweep.ts
# MIN_POINTS / MAX_POINTS).
MIN_POINTS = 2
MAX_POINTS = 201

# A matching network's part (a tuner's coil or capacitor): log-spaced, finely
# enough that one sweep traces the part's whole path on the Smith chart. A
# part's reactance runs over decades of its value, so even steps in the value
# would crowd one end; 81 points put about 40 a decade on a 1-100 pF range.
TUNER_PART_SWEEP = {"log": True, "points": 81}


def sanitize_sweep_hint(raw, lo_default=None, hi_default=None) -> dict | None:
    """The usable part of a ``ui_params`` ``sweep`` entry, or None.

    Returns only the keys the design gave, so a front end can tell "the
    design says linear" from "the design says nothing". ``lo_default`` /
    ``hi_default`` (the knob's min / max) are only used to check that the
    range it implies can be swept."""
    if not isinstance(raw, Mapping):
        return None
    out: dict = {}
    for key in ("lo", "hi"):
        if key in raw:
            v = raw[key]
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                return None
            out[key] = float(v)
    if "points" in raw:
        n = raw["points"]
        if isinstance(n, bool) or not isinstance(n, int):
            return None
        if not MIN_POINTS <= n <= MAX_POINTS:
            return None
        out["points"] = n
    if "log" in raw:
        if not isinstance(raw["log"], bool):
            return None
        out["log"] = raw["log"]
    lo = out.get("lo", lo_default)
    hi = out.get("hi", hi_default)
    if lo is not None and hi is not None:
        if not float(lo) < float(hi):
            return None
        if out.get("log") and not float(lo) > 0.0:
            return None
    return out or None


def knob_sweep_hint(builder, name: str) -> dict | None:
    """A knob's sanitised sweep hint, read off its builder's ``ui_params``."""
    # Lazy: band_opt pulls scipy (via opt), and the web adapter imports this
    # module at startup for `sanitize_sweep_hint` alone.
    from .band_opt import _ui_meta

    meta = _ui_meta(builder, name)
    if meta is None:
        return None
    return sanitize_sweep_hint(meta.get("sweep"), meta.get("min"), meta.get("max"))

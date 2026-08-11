"""NEC-5 drop-in backend for the web UI (issue #825 follow-up).

Mirrors the response shape of `web.server`'s momwire solver paths so the
frontend can swap a slot to NEC-5 via the `solver` request field, exactly
like the PyNEC backend.

NEC-5 is licensed, user-supplied software: the backend exists in the
roster only when the serving machine resolves ``$NEC5_EXE`` (see
`engines.nec5.find_nec5`). The hosted simulator never defines it, so the
slot chooser can never offer NEC-5 hosted — running a local web instance
against a personally licensed binary is the supported use, and network
exposure of that instance is the operator's responsibility. Availability
is a runtime binary probe, not an import probe, so it is re-checked per
request (`have_nec5()`), unlike PyNEC's import-time ``HAVE_PYNEC``.
"""

from __future__ import annotations

from ..engines.nec5 import find_nec5
from .examples import REGISTRY as EXAMPLES


def have_nec5() -> bool:
    """True when a licensed NEC-5 binary is resolvable right now."""
    return find_nec5() is not None


def solve(req: dict) -> dict:
    geometry = req.get("geometry", next(iter(EXAMPLES)))
    ex = EXAMPLES.get(geometry) or next(iter(EXAMPLES.values()))
    if ex.nec5_solve is None:
        raise ValueError(f"NEC-5 solve not implemented for geometry {ex.name!r}")
    return ex.nec5_solve(req)


def pattern(req: dict) -> dict:
    geometry = req.get("geometry", next(iter(EXAMPLES)))
    ex = EXAMPLES.get(geometry) or next(iter(EXAMPLES.values()))
    if ex.nec5_pattern is None:
        raise ValueError(f"NEC-5 pattern not implemented for geometry {ex.name!r}")
    return ex.nec5_pattern(req)


def _sweep_at(req: dict, freq_mhz: float) -> complex:
    """Single-frequency Z, one binary run per point (the streamed sweep
    endpoints call per-point; NEC5Engine's batched FR stepping is a future
    optimisation for uniform grids)."""
    req2 = dict(req)
    req2["measurement_freq_mhz"] = freq_mhz
    res = solve(req2)
    return complex(res["z_in_re"], res["z_in_im"])


def _sweep_at_multifeed(req: dict, freq_mhz: float):
    """(primary_z, per-feed z list) at one frequency — the multi-feed
    NDJSON contract, same as the PyNEC twin."""
    req2 = dict(req)
    req2["measurement_freq_mhz"] = freq_mhz
    res = solve(req2)
    primary = complex(res["z_in_re"], res["z_in_im"])
    feeds_z = [complex(f["z_re"], f["z_im"]) for f in res.get("feeds", [])]
    return primary, feeds_z

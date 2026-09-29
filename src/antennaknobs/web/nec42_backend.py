"""NEC-4.2 drop-in backend for the web UI (AK#1603).

`nec2_backend`'s twin: the frontend swaps a slot to NEC-4.2 with the `solver`
request field and the response shape is unchanged. The binary is user-supplied
because NEC-4.2 is licensed (LLNL, per-user), which is NEC-5's reason and not
NEC-2's — so, like NEC-5, it appears only where the machine running the server
resolves `$NEC42_EXE` (or ``[engines] nec42_exe``), never on the hosted box, and
nothing antennaknobs distributes carries it.

Availability is a runtime binary PROBE, re-checked per request
(`have_nec42()`): a path that resolves is not evidence the file is a NEC (#1339).
"""

from __future__ import annotations

from ..engines.nec42 import probe_nec42
from .examples import REGISTRY as EXAMPLES
from .examples import example_for


def have_nec42() -> bool:
    """True when a NEC-4.2 binary is resolvable AND actually runs."""
    return probe_nec42() is not None


def solve(req: dict) -> dict:
    geometry = req.get("geometry", next(iter(EXAMPLES)))
    ex = example_for(geometry)
    if ex.nec42_solve is None:
        raise ValueError(f"NEC-4.2 solve not implemented for geometry {ex.name!r}")
    return ex.nec42_solve(req)


def pattern(req: dict) -> dict:
    geometry = req.get("geometry", next(iter(EXAMPLES)))
    ex = example_for(geometry)
    if ex.nec42_pattern is None:
        raise ValueError(f"NEC-4.2 pattern not implemented for geometry {ex.name!r}")
    return ex.nec42_pattern(req)


def _sweep_at(req: dict, freq_mhz: float) -> complex:
    """Single-frequency Z, one binary run per point, as NEC-2's lane does."""
    req2 = dict(req)
    req2["measurement_freq_mhz"] = freq_mhz
    res = solve(req2)
    return complex(res["z_in_re"], res["z_in_im"])


def _sweep_at_multifeed(req: dict, freq_mhz: float):
    """(primary_z, per-feed z list) at one frequency — the multi-feed NDJSON
    contract, same as the PyNEC, NEC-5 and NEC-2 twins."""
    req2 = dict(req)
    req2["measurement_freq_mhz"] = freq_mhz
    res = solve(req2)
    primary = complex(res["z_in_re"], res["z_in_im"])
    feeds_z = [complex(f["z_re"], f["z_im"]) for f in res.get("feeds", [])]
    return primary, feeds_z

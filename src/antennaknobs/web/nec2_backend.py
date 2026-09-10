"""NEC-2 drop-in backend for the web UI (issue #1354).

Mirrors `nec5_backend` exactly, which mirrors `pynec_backend`: the frontend
swaps a slot to NEC-2 with the `solver` request field and the response shape is
unchanged. What differs is only WHY the binary is user-supplied.

NEC-5 is user-supplied because it is licensed. NEC-2 is user-supplied because it
is GPL: `pynec-accel` wraps nec2++, so linking it into anything antennaknobs
DISTRIBUTES — the frozen workbench, the published Docker image — would make that
artefact a combined work. Driving a console binary over a subprocess carries no
such term, which is why the frozen bundle can offer this engine and cannot offer
the in-process PyNEC one. Most users already have a binary: 4nec2 installs one.

Availability is a runtime binary PROBE and not an import probe, so it is
re-checked per request (`have_nec2()`), the same as NEC-5's — a path that
resolves is not evidence the file is a NEC-2 (#1339).
"""

from __future__ import annotations

from ..engines.nec2 import probe_nec2
from .examples import REGISTRY as EXAMPLES
from .examples import example_for


def have_nec2() -> bool:
    """True when a NEC-2 binary is resolvable AND actually runs.

    Resolving is not enough, which the NEC-5 lane paid to learn: `$NEC5_EXE`
    pointing at any executable produced a solver tab that failed only at the
    first solve, with the wrong program's error text (#1339). `probe_nec2` runs
    a one-wire deck once per (path, mtime, size) and logs the path on failure,
    so a wrong binary is absent from the roster with a sentence naming the file.
    """
    return probe_nec2() is not None


def solve(req: dict) -> dict:
    geometry = req.get("geometry", next(iter(EXAMPLES)))
    ex = example_for(geometry)
    if ex.nec2_solve is None:
        raise ValueError(f"NEC-2 solve not implemented for geometry {ex.name!r}")
    return ex.nec2_solve(req)


def pattern(req: dict) -> dict:
    geometry = req.get("geometry", next(iter(EXAMPLES)))
    ex = example_for(geometry)
    if ex.nec2_pattern is None:
        raise ValueError(f"NEC-2 pattern not implemented for geometry {ex.name!r}")
    return ex.nec2_pattern(req)


def _sweep_at(req: dict, freq_mhz: float) -> complex:
    """Single-frequency Z, one binary run per point — the streamed sweep
    endpoints call per point. NEC-2's FR card can step a uniform grid in one
    run; batching that is an optimisation, not a correctness change."""
    req2 = dict(req)
    req2["measurement_freq_mhz"] = freq_mhz
    res = solve(req2)
    return complex(res["z_in_re"], res["z_in_im"])


def _sweep_at_multifeed(req: dict, freq_mhz: float):
    """(primary_z, per-feed z list) at one frequency — the multi-feed NDJSON
    contract, same as the PyNEC and NEC-5 twins."""
    req2 = dict(req)
    req2["measurement_freq_mhz"] = freq_mhz
    res = solve(req2)
    primary = complex(res["z_in_re"], res["z_in_im"])
    feeds_z = [complex(f["z_re"], f["z_im"]) for f in res.get("feeds", [])]
    return primary, feeds_z

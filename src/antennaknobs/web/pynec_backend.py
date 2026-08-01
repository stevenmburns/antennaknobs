"""PyNEC drop-in backend for the web UI.

Mirrors the response shape of `web.server`'s momwire solver paths so the
frontend can swap between solvers via a `solver` field on every request.

PyNEC is optional: `HAVE_PYNEC` is False if the import fails, and the
server falls back to momwire with a one-time warning.
"""

from __future__ import annotations

import time

import numpy as np

try:
    import PyNEC as nec  # type: ignore

    HAVE_PYNEC = True
except ImportError:
    HAVE_PYNEC = False
    nec = None

from ..network_reduce import SingularNetworkError
from .examples import REGISTRY as EXAMPLES


C_LIGHT = 299_792_458.0

# Typical "average" earth, matching antennaknobs/sim.py.
GROUND_DIELECTRIC = 10.0
GROUND_CONDUCTIVITY = 0.002


def _segment_centers_to_knot_currents(
    cur_per_seg: np.ndarray,
    n_knots: int,
    junction_at_start: bool = False,
    junction_at_end: bool = False,
) -> np.ndarray:
    """Map NEC's per-segment-center currents onto the (n_knots,)-knot array
    the UI expects.

    Interior knot k sits between segments k-1 and k, so we average. The
    boundary knots default to zero (open-wire BC), but at a junction with
    another wire the current is continuous through the endpoint — pass
    junction_at_start/end=True to carry the adjacent segment-center value
    onto the boundary knot instead.
    """
    full = np.zeros(n_knots, dtype=np.complex128)
    if cur_per_seg.shape[0] != n_knots - 1:
        raise RuntimeError(
            f"segment-current length {cur_per_seg.shape[0]} doesn't match "
            f"n_knots-1 = {n_knots - 1}"
        )
    full[1:-1] = 0.5 * (cur_per_seg[:-1] + cur_per_seg[1:])
    if junction_at_start:
        full[0] = cur_per_seg[0]
    if junction_at_end:
        full[-1] = cur_per_seg[-1]
    return full


def _run_solve(
    c,
    n_seg_total: int,
    feed_seg: int,
    freq_mhz: float,
    ground: bool = False,
    feed_tag: int = 1,
    ground_fast: bool = False,
):
    if ground:
        # ITYPE=2: Sommerfeld-Norton, full kernel integration — accurate for
        # antennas a fraction of a wavelength above ground, ~100x slower per
        # solve than free space.
        # ITYPE=0: reflection-coefficient approximation — applies a Fresnel
        # reflection on the image current rather than evaluating Sommerfeld
        # integrals. Cheap (~10x faster than ITYPE=2) and accurate enough
        # away from grazing angles; degrades for very low antennas.
        itype = 0 if ground_fast else 2
        c.gn_card(itype, 0, GROUND_DIELECTRIC, GROUND_CONDUCTIVITY, 0, 0, 0, 0)
    else:
        c.gn_card(-1, 0, 0, 0, 0, 0, 0, 0)  # free space
    c.ex_card(0, feed_tag, feed_seg, 0, 1.0, 0.0, 0, 0, 0, 0)
    c.fr_card(0, 1, freq_mhz, 0)
    c.xq_card(0)
    sc = c.get_structure_currents(0)
    cur_arr = np.asarray(sc.get_current(), dtype=np.complex128)
    tag_arr = np.asarray(sc.get_current_segment_tag())
    return cur_arr, tag_arr


def solve(req: dict) -> dict:
    geometry = req.get("geometry", next(iter(EXAMPLES)))
    ex = EXAMPLES.get(geometry) or next(iter(EXAMPLES.values()))
    if ex.pynec_solve is None:
        raise ValueError(f"PyNEC solve not implemented for geometry {ex.name!r}")
    return ex.pynec_solve(req)


def pattern(req: dict) -> dict:
    """NEC's `rp_card`-computed gain pattern over the upper hemisphere.

    Returns a (n_theta × n_phi) gain grid in dBi at θ ∈ [0°, 90°], full φ.
    With ground off, the lower hemisphere is symmetric to the upper for the
    flat geometries supported here, but we only ship the upper half — the
    UI mirrors as needed.

    Multi-feed examples (bowtie 1×2 array) supply their own
    `pynec_pattern_excite` so the pattern reflects the combined-excitation
    radiation matching what `solve()` reports in `feeds`. Single-feed
    examples fall back to one ex_card via `_run_solve()`.
    """
    geometry = req.get("geometry", next(iter(EXAMPLES)))
    ex = EXAMPLES.get(geometry) or next(iter(EXAMPLES.values()))
    if ex.pynec_build is None:
        raise ValueError(f"PyNEC pattern not implemented for geometry {ex.name!r}")
    b = ex.pynec_build(req)
    c = b["context"]
    meas_freq_mhz = float(
        req.get("measurement_freq_mhz", req.get("design_freq_mhz", 14.3))
    )

    t0 = time.perf_counter()
    if ex.pynec_pattern_excite is not None:
        ex.pynec_pattern_excite(b, meas_freq_mhz)
    else:
        feed_seg = b["feed_seg"]
        n_per_wire = b["n_per_wire"]
        feed_tag = b.get("feed_tag", 1)
        _run_solve(
            c,
            2 * n_per_wire,
            feed_seg,
            meas_freq_mhz,
            ground=b["ground"],
            feed_tag=feed_tag,
            ground_fast=b["ground_fast"],
        )

    # 2°×5° grid: 46 thetas (0..90), 73 phis (0..360 inclusive). At ~3.4k
    # rays this runs in tens of ms — fine for a debounced overlay request.
    n_theta = 46
    n_phi = 73
    del_theta = 90.0 / (n_theta - 1)
    del_phi = 360.0 / (n_phi - 1)
    c.rp_card(0, n_theta, n_phi, 0, 5, 0, 0, 0.0, 0.0, del_theta, del_phi, 0.0, 0.0)
    gains = [
        [float(c.get_gain(0, ti, pi)) for pi in range(n_phi)] for ti in range(n_theta)
    ]
    pattern_ms = (time.perf_counter() - t0) * 1e3

    return {
        "available": True,
        "geometry": geometry,
        "ground": b["ground"],
        "ground_fast": b["ground_fast"],
        "height_m": b["z_offset"],
        "measurement_freq_mhz": meas_freq_mhz,
        "theta_deg": [ti * del_theta for ti in range(n_theta)],
        "phi_deg": [pi * del_phi for pi in range(n_phi)],
        "gain_dbi": gains,
        "pattern_ms": pattern_ms,
    }


def _sweep_at(req: dict, freq_mhz: float) -> complex:
    """Single-frequency Z via PyNEC, used to build the swept Z array.

    Returns the primary feed's Z for back-compat. Multi-feed callers that
    need per-feed data should use `_sweep_at_multifeed`.
    """
    req2 = dict(req)
    req2["measurement_freq_mhz"] = freq_mhz
    try:
        res = solve(req2)
    except SingularNetworkError:
        # One frequency landing on a lossless line's pole (issue #647) must
        # not break the stream; the sentinel is what the momwire path's
        # non-finite samples already clamp to. Imported here, not at module
        # scope: adapter imports the examples registry, which imports this.
        from .adapter import Z_OPEN_OHMS

        return complex(Z_OPEN_OHMS, 0.0)
    return complex(res["z_in_re"], res["z_in_im"])


def _sweep_at_multifeed(req: dict, freq_mhz: float):
    """Single-frequency multi-feed sweep point. Returns (primary_z,
    feeds_z_list) — feeds_z_list is the per-feed driving-point Z list
    matching the multi-feed `feeds[]` order.

    Used for the bowtie 1×2 array sweep so the streamed NDJSON can carry
    per-feed Z alongside the legacy `z_re` / `z_im` (primary) fields.
    """
    req2 = dict(req)
    req2["measurement_freq_mhz"] = freq_mhz
    try:
        res = solve(req2)
    except SingularNetworkError:  # see _sweep_at
        from .adapter import Z_OPEN_OHMS

        return complex(Z_OPEN_OHMS, 0.0), []
    primary = complex(res["z_in_re"], res["z_in_im"])
    feeds_z = [complex(f["z_re"], f["z_im"]) for f in res.get("feeds", [])]
    return primary, feeds_z


def sweep(req: dict, freqs_mhz: list[float]) -> tuple[list[float], list[float]]:
    """Loop-based sweep. PyNEC has no batched API, so we run one solve per
    frequency. At N=30 each solve is ~1.5 ms — 41 points * 1.5 ms = ~60 ms,
    fine for an interactive sweep."""
    z_re, z_im = [], []
    for f in freqs_mhz:
        z = _sweep_at(req, f)
        z_re.append(float(z.real))
        z_im.append(float(z.imag))
    return z_re, z_im

"""OpenNEC drop-in backend for the web UI, through pyopennec's porty.

`pynec_backend`'s twin: the same request/response contracts, served by
`OpenNECEngine`, which solves through pyopennec's port-admittance interface
(`pyopennec.porty`) and never its PyNEC-shaped pybind module. The frontend
swaps a slot to it with ``solver: "opennec"``, exactly as it does to PyNEC.

pyopennec is optional and not on PyPI yet, so `HAVE_OPENNEC` is False when
porty does not import and the entry is absent from the served roster. The
server also withholds it on the hosted instance (`server._have_opennec`): the
hosted image does not install it, and offering an engine there is a separate
call.
"""

from __future__ import annotations

import time

import numpy as np

try:
    from pyopennec import porty  # type: ignore

    HAVE_OPENNEC = True
except ImportError:
    HAVE_OPENNEC = False
    porty = None

from . import pynec_backend as _pynec
from .examples import REGISTRY as EXAMPLES
from .examples import example_for


def solve(req: dict) -> dict:
    geometry = req.get("geometry", next(iter(EXAMPLES)))
    ex = example_for(geometry)
    if ex.opennec_solve is None:
        raise ValueError(f"OpenNEC solve not implemented for geometry {ex.name!r}")
    return ex.opennec_solve(req)


def pattern(req: dict) -> dict:
    """`pynec_backend.pattern`'s grid and response, read off the engine's
    cached porty solve: total gain per source watt, as PyNEC's RP gives it."""
    geometry = req.get("geometry", next(iter(EXAMPLES)))
    ex = example_for(geometry)
    if ex.opennec_build is None:
        raise ValueError(f"OpenNEC pattern not implemented for geometry {ex.name!r}")
    b = ex.opennec_build(req)
    meas_freq_mhz = float(
        req.get("measurement_freq_mhz", req.get("design_freq_mhz", 14.3))
    )
    t0 = time.perf_counter()
    n_theta, n_phi, del_theta, del_phi = _pynec.PATTERN_GRID
    gains, _valid = b["_engine"].gain_grid_dbi(
        np.arange(n_theta) * del_theta, np.arange(n_phi) * del_phi, meas_freq_mhz
    )
    return _pynec.pattern_payload(
        req, b, [[float(g) for g in row] for row in gains], meas_freq_mhz, t0
    )


def _sweep_at(req: dict, freq_mhz: float) -> complex:
    return _pynec._sweep_point(solve, req, freq_mhz)


def _sweep_at_multifeed(req: dict, freq_mhz: float):
    return _pynec._sweep_point_multifeed(solve, req, freq_mhz)

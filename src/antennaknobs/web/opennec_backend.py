"""OpenNEC drop-in backend for the web UI, through pyopennec.

`pynec_backend`'s twin: the same request/response contracts, served by
`OpenNECEngine` (PyNECEngine on the pyopennec binding). The frontend swaps a
slot to it with ``solver: "opennec"``, exactly as it does to PyNEC.

pyopennec is optional and not on PyPI yet, so `HAVE_OPENNEC` is False when it
does not import and the entry is absent from the served roster. The server
also withholds it on the hosted instance (`server._have_opennec`): the hosted
image does not install it, and offering an engine there is a separate call.
"""

from __future__ import annotations

try:
    import pyopennec  # type: ignore

    HAVE_OPENNEC = True
except ImportError:
    HAVE_OPENNEC = False
    pyopennec = None

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
    """`pynec_backend.pattern` on OpenNEC's build: the same 46 x 73 RP grid."""
    geometry = req.get("geometry", next(iter(EXAMPLES)))
    ex = example_for(geometry)
    if ex.opennec_build is None:
        raise ValueError(f"OpenNEC pattern not implemented for geometry {ex.name!r}")
    return _pynec.pattern_from_build(req, ex, ex.opennec_build(req))


def _sweep_at(req: dict, freq_mhz: float) -> complex:
    return _pynec._sweep_point(solve, req, freq_mhz)


def _sweep_at_multifeed(req: dict, freq_mhz: float):
    return _pynec._sweep_point_multifeed(solve, req, freq_mhz)

"""Antenna example registry.

Each antenna geometry exposed by the web UI is defined in its own module
under this package and registered via `register(EXAMPLE)`. The dispatchers
in `web.server` and `web.pynec_backend` look up the example by its `name`
field, so removing an antenna is a two-line change: delete the module file
and the matching `from . import <name>` line below.

The registry is intentionally web-layer (not solver-core) — each example
parses the request dict, calls shared helpers in `web.server` /
`web.pynec_backend`, and produces the JSON-shaped response the frontend
consumes. The solver package `momwire/` stays free of UI concerns.
"""

from __future__ import annotations

from ._base import AntennaExample, ParamSpec

REGISTRY: dict[str, AntennaExample] = {}


class UnknownGeometryError(ValueError):
    """A request named a design the registry does not hold (issue #1343).

    Raised instead of quietly answering for the first registered design,
    which is what every `EXAMPLES.get(key) or next(iter(EXAMPLES.values()))`
    used to do: a request for ``invvee`` instead of ``dipoles.invvee`` came
    back with solved numbers for ``arrays.bowtie16x1`` and no error, and the
    Windows box session nearly reported the invvee as broken on NEC-5 on the
    strength of it (2026-09-09). The server maps this to a 400 naming the
    key and the nearest registered names; the solve channel formats it like
    any other solve error.
    """


def example_for(geometry) -> AntennaExample:
    """The registered design for ``geometry``, or UnknownGeometryError.

    An ABSENT key is a different thing from an unknown one: callers that
    default a missing key to the first design (``req.get("geometry",
    next(iter(REGISTRY)))``) keep that convention; this only refuses a key
    that was given and does not resolve.
    """
    ex = REGISTRY.get(geometry)
    if ex is not None:
        return ex
    import difflib

    near = difflib.get_close_matches(str(geometry), list(REGISTRY), n=3, cutoff=0.4)
    tail = f"; did you mean {', '.join(repr(n) for n in near)}?" if near else ""
    raise UnknownGeometryError(
        f"unknown geometry {geometry!r}: not a registered design{tail} "
        f"(the registry holds {len(REGISTRY)} designs, named like 'dipoles.invvee')"
    )


def register(example: AntennaExample) -> AntennaExample:
    if example.name in REGISTRY:
        raise ValueError(f"duplicate antenna example: {example.name}")
    REGISTRY[example.name] = example
    return example


# Examples are auto-generated from antennaknobs's designs/ package via
# the adapter, which derives a ParamSpec schema from each Builder's
# default_params and wraps MomwireEngine + PyNECEngine in the SolveFn /
# SweepFn contract above. See web/adapter.py for the bridge and what each
# Builder can opt into via its `ui_params` dict.
from .. import adapter  # noqa: E402

adapter.register_all()

__all__ = ["AntennaExample", "ParamSpec", "REGISTRY", "register"]

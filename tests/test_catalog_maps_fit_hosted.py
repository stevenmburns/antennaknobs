"""Every catalog design's maps fit the hosted map cap.

dipoles.two_wire_doublet shipped its resonance map at 41 x 34 = 1394 points,
over the hosted app's 1000-point live limit (`web.cost.MAX_MAP_POINTS`), so
the analysis a QRZ post linked to with run=1 refused on the hosted app. The
catalog is what the hosted app offers, so a map there must run there.
Analyses only -- nothing solves.
"""

from __future__ import annotations

import math

from antennaknobs import analyses as an
from antennaknobs.web.cost import MAX_MAP_POINTS
from test_catalog_momwire_predicates_1299 import _catalog_builders


def _maps():
    for name, builder in _catalog_builders():
        try:
            analyses = builder().build_analyses()
        except Exception:  # noqa: BLE001 - a design that will not build is gated elsewhere
            continue
        for a in analyses:
            if isinstance(a.sweep, tuple) and any(
                isinstance(v, an.Map) for v in a.views
            ):
                yield name, a.name, math.prod(s.points for s in a.sweep)


def test_every_catalog_map_fits_the_hosted_map_cap():
    maps = list(_maps())
    assert any(n == "dipoles.two_wire_doublet" for n, _a, _p in maps), maps
    over = [(n, a, p) for n, a, p in maps if p > MAX_MAP_POINTS]
    assert not over, f"over the hosted {MAX_MAP_POINTS}-point map cap: {over}"

"""The ``bundle`` variant of `verticals.buried_radial_vertical` solves as the
hub (momwire#1042, narrowed by momwire#1333).

The bundle is the pre-#1108 spelling: N coincident rises, each an exact copy
of the hub's single rise, all joined at the same hub junction and the same
interface node. A momwire with the duplicate-wire merge drops the copies,
says so with a `DuplicateWire` advisory, and solves the conductor once, which
is the hub. Wire for wire, the two spellings only agreed at converged
quadrature (5.2e-06 ohm at n_qp_pair = 256, the design's docstring); merged,
they agree at the design's shipped quadrature.

The bar is 1e-9 relative: measured ~2.5e-11 ohm. Not bit for bit, because
the merged bundle keeps its wires in a different order from the hub, and the
fill and the factorisation round differently in that order.
"""

from __future__ import annotations

import warnings

import numpy as np
import pytest
from momwire._wire_spec import DuplicateWire

from antennaknobs import resolve_variant_params
from antennaknobs.designs.verticals.buried_radial_vertical import (
    Builder as BuriedRadialVertical,
)
from antennaknobs.engines.momwire import MomwireEngine

SOIL_A = ("finite", 13.0, 0.005)


def _z(params=None):
    builder = BuriedRadialVertical(params=params) if params else BuriedRadialVertical()
    engine = MomwireEngine(builder, ground=SOIL_A, ground_z=0.0)
    return complex(np.atleast_1d(np.asarray(engine.impedance()))[0])


def test_the_bundle_solves_as_the_hub_and_says_so():
    with warnings.catch_warnings():
        warnings.simplefilter("error", DuplicateWire)
        z_hub = _z()
    with pytest.warns(DuplicateWire, match="momwire#1042"):
        z_bundle = _z(resolve_variant_params(BuriedRadialVertical, "bundle"))
    assert z_bundle == pytest.approx(z_hub, rel=1e-9, abs=0.0), (z_bundle, z_hub)

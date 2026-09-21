"""PyNEC's own pattern on the multiport-Y route is gain per SOURCE watt (AK#1637).

NEC normalises gain by the power into the STRUCTURE, the sum over its EX
cards. On the multiport-Y route (a TL / transformer / virtual-port network the
reducer solves) the network sits between the sources and those cards, and a
lossy one burns its share first, so the unscaled pattern read high by the
network's loss: 1.64 dB on `dipoles.invvee_coax_station`, whose coax takes
31 %. NEC-5's twin is in `test_nec5_network_drive_1627.py`.

The app's NEC rp trace on this lane never got that far: `pynec_build` handed
the pattern the engine's `c`, which the reducer route never builds, and every
network design's trace raised AttributeError.
"""

from __future__ import annotations

import copy
import importlib

import numpy as np
import pytest
from conftest import needs_pynec

pytestmark = needs_pynec

LOSSY = "dipoles.invvee_coax_station"


def _req(name):
    f = importlib.import_module(f"antennaknobs.designs.{name}").Builder().freq
    return {
        "geometry": name,
        "measurement_freq_mhz": f,
        "design_freq_mhz": f,
        "ground": False,
    }


def _engine(name):
    import antennaknobs.web.examples  # noqa: F401  (before the adapter)
    from antennaknobs.web import adapter

    req = _req(name)
    cls = importlib.import_module(f"antennaknobs.designs.{name}").Builder
    builder = adapter._build_builder(cls, dict(req))
    builder.freq = req["measurement_freq_mhz"]
    return adapter._make_pynec_engine(dict(req), builder)


def test_the_native_route_is_not_shifted():
    from antennaknobs import resolve_variant_params
    from antennaknobs.designs.dipoles.invvee import Builder
    from antennaknobs.engines.pynec import PyNECEngine

    eng = PyNECEngine(Builder(resolve_variant_params(Builder, "dipole")))
    assert not eng._use_reducer
    assert eng._source_gain_shift_db(None) == 0.0


def test_a_lossless_network_is_not_shifted():
    """The control: with nothing to burn, structure power IS source power."""
    eng = _engine("beams.hb9cv")
    assert eng._use_reducer
    from antennaknobs.engines.pynec import C_LIGHT

    eng.c, p_source = eng._excited_for_pattern(C_LIGHT / (eng.builder.freq * 1e6))
    eng._set_freq_and_execute()
    assert eng._source_gain_shift_db(p_source) == pytest.approx(0.0, abs=1e-3)


def test_a_lossy_network_pattern_is_per_source_watt():
    """The engine's own pattern, the app's NEC rp trace and the app's cut
    (normalised by the circuit-side source power) agree once rescaled; the
    unscaled pattern sat 1.64 dB above the cut."""
    import antennaknobs.web.examples as examples
    from antennaknobs.web import pynec_backend, server

    eng = _engine(LOSSY)
    assert eng._use_reducer
    ff = eng.far_field()

    pat = pynec_backend.pattern(_req(LOSSY))
    web_peak = float(np.max(pat["gain_dbi"]))
    # Two grids (1-degree engine, 2x5-degree web) over one smooth pattern.
    assert web_peak == pytest.approx(ff.max_gain, abs=0.01)

    out = examples.example_for(LOSSY).pynec_solve(_req(LOSSY))
    o = copy.deepcopy(out)
    server._attach_derived_em_fields(o)
    server._attach_gain_norm(o)
    cut = np.asarray(server._pattern_cuts(o, 0.5, 0.0)["azimuth"])
    assert out["radiation_efficiency"] < 0.75  # the network does burn power
    assert float(cut.max()) == pytest.approx(web_peak, abs=0.05)

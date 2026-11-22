"""PyNEC and OpenNEC reduce their multiport route in the DESIGN's c (AK#2323).

AK#2226 held the card-deck engines (NEC-5, NEC-2, NEC-4.2) to the rule the
momwire engine already kept (AK#1685): the multiport-Y route hands the
reducer a wavelength made with the design's ``c_light_mhz_m`` and reads the
frequency back in the same c. PyNEC and OpenNEC built theirs with SI c, so a
deck-loaded design (c = 299.8) read a lossy line's phase 25 ppm off.

The gates need no solve: `_compute_y_matrix` is replaced on the instance by
a fixed antenna Y, so the reducer is the only arithmetic in play, exactly as
in tests/test_nec_engines_design_c_2226.py (whose design and hand reduction
this file reuses).
"""

from __future__ import annotations

import numpy as np
import pytest

from antennaknobs.builder import C_LIGHT_MHZ_M
from antennaknobs.engines import _multiport

from test_nec_engines_design_c_2226 import F_MHZ, NEC_C, Z_ANT, _builder, _want

pytestmark = pytest.mark.filterwarnings("ignore")


def _engine(kind, builder):
    if kind == "pynec":
        pytest.importorskip("PyNEC")
        from antennaknobs.engines.pynec import PyNECEngine

        return PyNECEngine(builder, ground=None)
    pytest.importorskip("pyopennec")
    from antennaknobs.engines.opennec import OpenNECEngine

    return OpenNECEngine(builder, ground=None)


def _with_fixed_y(eng):
    """Replace the solve's Y with `Z_ANT`, recording the frequency each Y run
    would have solved at."""
    seen = []

    def y(wl):
        seen.append(_multiport.frequency(eng, wl))
        return np.array([[1.0 / Z_ANT]])

    eng._compute_y_matrix = y
    return seen


ENGINES = ["pynec", "opennec"]


@pytest.mark.parametrize("kind", ENGINES)
def test_a_deck_loaded_design_reduces_in_its_own_c(kind):
    b, net, feed = _builder(NEC_C)
    eng = _engine(kind, b)
    assert eng._use_reducer
    assert eng._reducer.c_light_mhz_m == NEC_C
    seen = _with_fixed_y(eng)
    z = complex(np.atleast_1d(eng.impedance())[0])
    assert z == pytest.approx(_want(net, feed, NEC_C), rel=1e-12)
    # the miss is real at this size, so the gate is not passing on nothing
    assert abs(z - _want(net, feed, C_LIGHT_MHZ_M)) / abs(z) > 1e-5
    zs = eng.impedance_sweep([F_MHZ])
    assert complex(zs[0][0]) == pytest.approx(z, rel=1e-14)
    # every Y run solves at the design's own frequency
    assert seen and all(f == pytest.approx(F_MHZ, rel=1e-14) for f in seen)


@pytest.mark.parametrize("kind", ENGINES)
def test_an_si_design_is_bit_identical_to_the_si_reduction(kind):
    b, net, feed = _builder(C_LIGHT_MHZ_M)
    eng = _engine(kind, b)
    assert _multiport.reducer_c_light(eng) is None
    assert eng._reducer.c_light_mhz_m is None
    _with_fixed_y(eng)
    z = complex(np.atleast_1d(eng.impedance())[0])
    assert z == _want(net, feed, C_LIGHT_MHZ_M)


def test_the_wire_loss_reads_omega_in_the_wavelengths_own_c():
    """`_wire_loss_from_currents` turns the wavelength back into omega: on the
    multiport route that wavelength is the design's c, so it is told so."""
    pytest.importorskip("PyNEC")
    from antennaknobs.engines import pynec

    b, _net, _feed = _builder(NEC_C)
    eng = pynec.PyNECEngine(b, ground=None)
    # a copper wire, so the loss is computed (the design's own carries none)
    eng._wire_spec = type("Copper", (), {"conductivity": 5.8e7})()
    got = []
    real = pynec.wire_internal_impedance

    def spy(omega, a, sigma):
        got.append(omega)
        return real(omega, a, sigma)

    class _SC:
        def get_current_segment_tag(self):
            return []

        def get_current(self):
            return []

    pynec.wire_internal_impedance = spy
    try:
        eng._wire_loss_from_currents(_SC(), NEC_C * 1e6 / (F_MHZ * 1e6), NEC_C)
        eng._wire_loss_from_currents(_SC(), 299_792_458.0 / (F_MHZ * 1e6))
    finally:
        pynec.wire_internal_impedance = real
    assert len(got) == 2
    want = 2 * np.pi * F_MHZ * 1e6
    assert got[0] == pytest.approx(want, rel=1e-14)
    assert got[1] == pytest.approx(want, rel=1e-14)

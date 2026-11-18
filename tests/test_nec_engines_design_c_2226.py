"""The card-deck engines' multiport route reduces in the DESIGN's c (AK#2226).

`NEC5Engine` and `NEC2Engine` (and `NEC42Engine`, its subclass) serve a line,
a transformer or a two-port through the multiport-Y route: Y from the binary,
then the shared `NetworkReducer`. That reduction used to hand the reducer a
wavelength made with SI c and read the frequency back with SI c, whatever the
design's ``c_light_mhz_m``. A NEC evaluates a line in its own cards at its own
c (299.8), so on a deck-loaded design a lossy line's phase sat 25 ppm off and
the composite 1.6e-4 off what NEC-5 computes for the same circuit.

The momwire engine already reduces in the design's c (AK#1685); these gates
hold the card-deck engines to the same rule. The unit gates need no binary:
they replace `_compute_y_matrix` on the instance with a fixed antenna Y, so
the reducer is the only thing under test. The licensed NEC-5 comparison is
skip-guarded.
"""

from __future__ import annotations

import math
import os
import pathlib
import subprocess
import tempfile
from types import MappingProxyType

import numpy as np
import pytest

import antennaknobs.web.server  # noqa: F401 — resolves the adapter import cycle
from antennaknobs import network as N
from antennaknobs.builder import C_LIGHT_MHZ_M, AntennaBuilder
from antennaknobs.engines import _multiport
from antennaknobs.engines.nec2 import NEC2Engine
from antennaknobs.engines.nec42 import NEC42Engine
from antennaknobs.engines.nec5 import NEC5Engine, find_nec5
from antennaknobs.mw.networks import NetworkReducer
from antennaknobs.nec_import import parse_nec

pytestmark = pytest.mark.filterwarnings("ignore")

F_MHZ = 7.0
NEC_C = 299.8

DIPOLE = (
    "CM a 7 MHz dipole\nCE\nGW 1 21 0 -10.7 10 0 10.7 10 0.001\nGE 0\n"
    f"EX 0 1 11 0 1 0\nFR 0 1 0 0 {F_MHZ} 0\nEN\n"
)

# A synthetic antenna admittance at the one port: what the engine's Y would
# be, fixed so the reducer is the only arithmetic in play.
Z_ANT = 71.3 + 18.6j


def _builder(c_light):
    deck = parse_nec(DIPOLE, network=True)
    ant = deck.network()
    (feed,) = ant.ports
    net = N.Network(
        ports={**ant.ports, "rig": N.PortVirtual("rig")},
        branches=[N.TL("rig", feed, z0=50.0, length=12.0, vf=0.66, k1=0.44, k2=0.009)],
        sources=[N.Driven(port="rig")],
    )
    wires = deck.wire_tuples(specs=True)

    class Design(AntennaBuilder):
        default_params = MappingProxyType({"freq": F_MHZ})
        c_light_mhz_m = c_light

        def build_wires(self):
            return wires

        def build_network(self):
            return net

    return Design(), net, feed


def _want(net, feed, c_light):
    """The station reduced by hand at `c_light`: the wavelength NEC solves at,
    and the frequency read back from it in the same c."""
    red = NetworkReducer(
        net,
        {feed: 0, "rig": 1},
        2,
        c_light_mhz_m=None if c_light == C_LIGHT_MHZ_M else c_light,
    )
    wl = c_light * 1e6 / (F_MHZ * 1e6)
    y = np.array([[1.0 / Z_ANT]])
    return complex(np.atleast_1d(red.driven_impedance(y, wl))[0])


@pytest.fixture(scope="module")
def stub_exe(tmp_path_factory):
    """An executable that is never executed: the engines resolve their binary
    at construction, and every Y below is replaced on the instance."""
    p = tmp_path_factory.mktemp("nec") / "necstub"
    p.write_text("#!/bin/sh\nexit 1\n")
    p.chmod(0o755)
    return str(p)


def _engine(kind, builder, exe):
    if kind == "nec5":
        return NEC5Engine(builder, nec5_exe=exe)
    if kind == "nec2":
        return NEC2Engine(builder, ground=None, nec2_exe=exe)
    return NEC42Engine(builder, ground=None, nec42_exe=exe)


def _with_fixed_y(eng):
    """Replace the binary's Y with `Z_ANT`, recording the frequency each run
    would have been written at."""
    seen = []

    def y(wl):
        seen.append(_multiport.frequency(eng, wl))
        return np.array([[1.0 / Z_ANT]])

    eng._compute_y_matrix = y
    return seen


ENGINES = ["nec5", "nec2", "nec42"]


@pytest.mark.parametrize("kind", ENGINES)
def test_a_deck_loaded_design_reduces_in_its_own_c(kind, stub_exe):
    b, net, feed = _builder(NEC_C)
    eng = _engine(kind, b, stub_exe)
    assert eng._use_reducer
    seen = _with_fixed_y(eng)
    z = complex(np.atleast_1d(eng.impedance())[0])
    want = _want(net, feed, NEC_C)
    assert z == pytest.approx(want, rel=1e-12)
    # The miss the issue describes is real at this size, so the gate above is
    # not passing on a difference too small to see.
    assert abs(z - _want(net, feed, C_LIGHT_MHZ_M)) / abs(z) > 1e-5
    # Every Y run is still written at the design's own frequency.
    assert seen and all(f == pytest.approx(F_MHZ, rel=1e-14) for f in seen)


@pytest.mark.parametrize("kind", ENGINES)
def test_an_si_design_is_bit_identical_to_the_si_reduction(kind, stub_exe):
    """None for an SI design: the reducer's SI expression, bit for bit."""
    b, net, feed = _builder(C_LIGHT_MHZ_M)
    eng = _engine(kind, b, stub_exe)
    assert _multiport.reducer_c_light(eng) is None
    assert _multiport.wavelength(eng, F_MHZ) == 299_792_458.0 / (F_MHZ * 1e6)
    _with_fixed_y(eng)
    z = complex(np.atleast_1d(eng.impedance())[0])
    assert z == _want(net, feed, C_LIGHT_MHZ_M)


def test_the_route_hands_the_reducer_the_design_c(stub_exe):
    b, _net, _feed = _builder(NEC_C)
    eng = _engine("nec5", b, stub_exe)
    assert eng._reducer.c_light_mhz_m == NEC_C
    assert _multiport.wavelength(eng, F_MHZ) == pytest.approx(NEC_C / F_MHZ)


# --- the licensed binary ------------------------------------------------------


def _licensed():
    exe = find_nec5(os.environ.get("NEC5_EXE"))
    if exe is None and os.access(os.path.expanduser("~/bin/nec5-licensed"), os.X_OK):
        exe = os.path.expanduser("~/bin/nec5-licensed")
    return exe


def _run_exe(exe, text):
    with tempfile.TemporaryDirectory() as td:
        p = pathlib.Path(td)
        (p / "m.nec").write_text(text)
        subprocess.run(
            [exe],
            input="m.nec\nm.out\n\n",
            cwd=td,
            capture_output=True,
            text=True,
            timeout=600,
        )
        out = (p / "m.out").read_text(errors="replace")
    return NEC5Engine._parse_input_parameters(out)[0][0][2]


def _printout_rounding(z):
    """Half a unit in the fifth significant figure of each part, over |Z|."""

    def half(x):
        return 0.0 if x == 0 else 0.5 * 10 ** (math.floor(math.log10(abs(x))) - 4)

    return math.hypot(half(z.real), half(z.imag)) / abs(z)


@pytest.mark.skipif(_licensed() is None, reason="no licensed NEC-5 (NEC5_EXE)")
def test_nec5_engine_reads_what_nec5_computes_in_its_own_cards():
    """The deck-loaded design with its lossy line, two ways on the licensed
    binary: `NEC5Engine`'s multiport route (Y from the binary, the line
    reduced here) and the station deck, where NEC-5 runs the line in its own
    NT cards. Within the deck's derived knot bound plus the printouts'
    rounding: the antenna Y's (one port, five figures) and the answer's."""
    from antennaknobs.nec5_station import station_deck

    exe = _licensed()
    b, _net, _feed = _builder(NEC_C)
    eng = NEC5Engine(b, nec5_exe=exe)
    assert eng._use_reducer
    z_engine = complex(np.atleast_1d(eng.impedance())[0])
    sd = station_deck(b, engine=eng)
    z_cards = _run_exe(exe, sd.text)
    tol = sd.tolerance + 2 * _printout_rounding(z_cards)
    assert abs(z_engine - z_cards) / abs(z_cards) <= tol

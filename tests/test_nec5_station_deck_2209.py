"""A stitched antenna + SimNEC station as ONE NEC-5 deck, at one frequency
(AK#2209).

The station is synthetic: a 7 MHz antenna deck (a centre-fed dipole, or an
inverted V fed at its vertex knot) with a SimNEC chain hung on it by
`SsnStation.network` (AK#2200): an ideal transformer at the antenna, a shunt
C, a series L, a lossless line, an S block whose ``.s2p`` is stored in the
``.ssn`` itself, and 12 m of RG-58 as the Johnson line.

The tolerance every comparison uses is DERIVED, not chosen: each phantom
knot carries an open pin whose residual conductance (measured on the
licensed binary: 1/R per pinned knot) moves the driving-point impedance by
a measured amount, `station_deck` reports it per knot, and the bound is
their sum. A comparison through a NEC-5 printout adds that printout's own
rounding (five significant figures per part). The licensed binary's run is
skip-guarded; `scratch/2209-station-deck/gates_by_engine.out` holds it.
"""

from __future__ import annotations

import base64
import gzip
import math
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from types import MappingProxyType, SimpleNamespace

import numpy as np
import pytest

from antennaknobs import network as N
from antennaknobs.builder import AntennaBuilder
from antennaknobs.cli import make_engine_factory
from antennaknobs.nec5_export import export_nec5
from antennaknobs.nec5_station import (
    NEC5_C_LIGHT_MHZ_M,
    NODE_EFFECT_LIMIT,
    PIN_OHMS,
    StationDeckRefusal,
    quarter_wave_pair,
    station_deck,
)
from antennaknobs.nec_import import parse_nec
from antennaknobs.simnec_import import parse_ssn_station
from momwire.networks import NetworkReducer
from momwire.networks._reduce import tl_abcd

F_MHZ = 7.0

DIPOLE = (
    "CM a 7 MHz dipole\nCM NEC-5\nCE\nGW 1 20 0 -10.7 10 0 10.7 10 0.001\nGE 0\n"
    f"EX 0 1 10 2 1 0\nFR 0 1 0 0 {F_MHZ} 0\nEN\n"
)
# Fed at the knot where its two legs meet: NEC-5's EX at a segment END,
# which the importer reads as a `PortAtVertex`.
VEE = (
    "CM a 7 MHz inverted V\nCM NEC-5\nCE\nGW 1 10 0 -10 5 0 0 10 0.001\n"
    "GW 2 10 0 0 10 0 10 5 0.001\nGE 0\n"
    f"EX 0 1 10 2 1 0\nFR 0 1 0 0 {F_MHZ} 0\nEN\n"
)

S11, S21, S22 = 0.08 + 0.05j, 0.93 - 0.21j, -0.03 + 0.12j
S2P = "\n".join(
    ["# MHz S RI R 50"]
    + [
        f"{f} {S11.real} {S11.imag} {S21.real} {S21.imag} "
        f"{S21.real} {S21.imag} {S22.real} {S22.imag}"
        for f in (6.9, 7.0, 7.1)
    ]
)
RG58 = {"Zo": "50", "VFnom": "0.66", "k0": "0.12942", "k1": "0.436326"}
RG58["k2"] = "0.009218"
LOSSLESS = {"Zo": "75", "VFnom": "0.8", "k0": "0", "k1": "0", "k2": "0"}

# Antenna side first, as SimNEC saves a station.
CHAIN = (
    ("TRANSFORMER2", "X1", {"Mdl": "ideal", "N": "1.5"}),
    ("SHUNT_CAP", "C1", {"F": "1e-10", "Q": "0", "@MHz": "0"}),
    ("SERIES_IND", "L1", {"H": "1.2e-6", "Q": "0", "@MHz": "0"}),
    ("SERIES_TLINE", "T1", {**LOSSLESS, "mtrs": "3"}),
    ("SCATTERING", "S2", {"dir": "2 <> 1", "Zref": "50", "file": ".\\choke.s2p"}),
    ("SERIES_TLINE", "T2", {**RG58, "mtrs": "12"}),
)


def _ssn(chain=CHAIN) -> str:
    root = ET.Element("SimNEC1p0")
    top = ET.SubElement(root, "SmithChartCircuit")
    fa = ET.SubElement(ET.SubElement(top, "FILEARCHIVE"), "element")
    ET.SubElement(fa, "name").text = "choke.s2p"
    ET.SubElement(fa, "compressed").text = base64.b64encode(
        gzip.compress(S2P.encode())
    ).decode()
    circuit = ET.SubElement(top, "CIRCUIT")

    def element(typ, label, params):
        el = ET.SubElement(circuit, "element")
        ET.SubElement(el, "type").text = typ
        ET.SubElement(el, "sweeperLabel").text = label
        for n, v in params.items():
            p = ET.SubElement(el, "p")
            ET.SubElement(p, "n").text = n
            ET.SubElement(p, "v").text = v

    element("LOAD", "L", {"ohms": "50", "johms": "0", "file": "<none>"})
    for typ, label, params in chain:
        element(typ, label, params)
    element("GENERATOR", "G", {"MHz": str(F_MHZ), "Zo": "50"})
    return ET.tostring(root, encoding="unicode")


def _builder(wires, net):
    class Design(AntennaBuilder):
        default_params = MappingProxyType({"freq": F_MHZ})
        # A deck-loaded antenna, as the app builds one: NEC's own c.
        c_light_mhz_m = 299.8

        def build_wires(self):
            return wires

        def build_network(self):
            return net

    return Design()


def _station(antenna=DIPOLE, chain=CHAIN):
    deck = parse_nec(antenna, network=True)
    st = parse_ssn_station(_ssn(chain), name="station.ssn")
    return _builder(deck.wire_tuples(specs=True), st.network(deck.network()))


def _read_back(text):
    deck = parse_nec(text, network=True)
    return _builder(deck.wire_tuples(specs=True), deck.network())


def _z(builder):
    return complex(make_engine_factory("momwire:bspline", None)(builder).impedance()[0])


def _cards(text, mnemonic):
    return [ln for ln in text.splitlines() if ln.split()[:1] == [mnemonic]]


def _rel(a, b):
    return abs(a - b) / abs(b)


# --- the λ/4 pair IS the ideal transformer --------------------------------------


@pytest.mark.parametrize("n", [2.0, 0.5, 1 / 1.5, 7.0, -3.0])
def test_the_quarter_wave_pair_is_the_ideal_transformer(n):
    """Chain matrices, with momwire's own line stamp: λ/4 of Z1 then λ/4 of
    Z2 (one of them transposed, which negates its port b) is
    ``Transformer(a, b, n)``'s [[n, 0], [0, 1/n]] to machine precision."""
    wl = NEC5_C_LIGHT_MHZ_M / F_MHZ
    (z1, t1), (z2, t2) = quarter_wave_pair(n)
    m = np.eye(2, dtype=complex)
    for z0, transposed in ((z1, t1), (z2, t2)):
        a, b, c, d = tl_abcd(z0, wl / 4.0, wl)
        m = m @ (np.array([[a, b], [c, d]]) * (-1.0 if transposed else 1.0))
    want = np.array([[n, 0.0], [0.0, 1.0 / n]])
    # cos(π/2) is 6e-17, not 0: the off-diagonals are Z0·cos(π/2)-sized.
    assert np.allclose(m, want, rtol=1e-14, atol=1e-13 * max(z1, z2))


def test_the_quarter_wave_pair_reduces_to_the_transformer_on_a_load():
    """The same identity through the reducer: a load behind the pair reads
    what it reads behind the ideal transformer."""
    wl = NEC5_C_LIGHT_MHZ_M / F_MHZ
    zl = 37.0 - 12.0j
    n = 1 / 1.5
    (z1, t1), (z2, t2) = quarter_wave_pair(n)

    def z(branches, nodes):
        net = N.Network(
            ports={k: N.PortVirtual(k) for k in nodes},
            branches=[*branches, N.Admittance(ports=("ant",), y=((1 / zl,),))],
            sources=[N.Driven(port="rig")],
        )
        red = NetworkReducer(net, {k: i for i, k in enumerate(nodes)}, len(nodes))
        return complex(np.atleast_1d(red.driven_impedance(np.zeros((0, 0)), wl))[0])

    pair = z(
        [
            N.TL("rig", "m", z0=z1, length=wl / 4, transposed=t1),
            N.TL("m", "ant", z0=z2, length=wl / 4, transposed=t2),
        ],
        ("rig", "m", "ant"),
    )
    ideal = z([N.Transformer("rig", "ant", n=n)], ("rig", "ant"))
    assert pair == pytest.approx(ideal, rel=1e-13)
    assert pair == pytest.approx(n * n * zl, rel=1e-13)


# --- the deck ------------------------------------------------------------------


@pytest.fixture(scope="module")
def dipole_deck():
    return station_deck(_station())


def test_a_stitched_station_writes_one_nec5_deck(dipole_deck):
    text = dipole_deck.text
    assert text.splitlines()[1] == "CM NT/TL station cards valid at 7 MHz only"
    assert "CM NEC-5" in text.splitlines()
    assert len(_cards(text, "FR")) == 1 and _cards(text, "FR")[0].split()[2] == "1"
    # The Johnson line, the S block and the series L (with the shunt C folded
    # into its diagonal) are NT cards; the lossless line and the transformer's
    # λ/4 pair are TL cards; the generator is one EX on the phantom wire.
    assert len(_cards(text, "NT")) == 3
    assert len(_cards(text, "TL")) == 3
    (ex,) = _cards(text, "EX")
    assert ex.split()[1:5] == ["0", "2", "1", "2"]
    # One pin per phantom knot: rig+T2, S2, T1, L1, C1+X1 and the λ/4 knot.
    pins = [ln for ln in _cards(text, "LD") if ln.split()[1:3] == ["4", "2"]]
    assert len(pins) == len(dipole_deck.knots) == 6
    assert {float(ln.split()[5]) for ln in pins} == {PIN_OHMS}
    # Every TL before every NT (momwire's drop-in reads that order only),
    # and every network card before the source.
    order = [ln.split()[0] for ln in text.splitlines()]
    assert max(i for i, c in enumerate(order) if c == "TL") < order.index("NT")
    assert max(i for i, c in enumerate(order) if c == "NT") < order.index("EX")


def test_the_cards_rebuilt_as_a_circuit_are_the_station(dipole_deck):
    """The writer's own check: its cards on the antenna's Y solve to the
    station network on the same Y, to rounding."""
    assert dipole_deck.z_cards == pytest.approx(dipole_deck.z_composite, rel=1e-12)
    assert dipole_deck.z_composite == pytest.approx(_z(_station()), rel=1e-12)


def test_every_knot_is_measured_and_the_tolerance_is_their_sum(dipole_deck):
    effects = [k.effect for k in dipole_deck.knots]
    assert all(0.0 < e < NODE_EFFECT_LIMIT for e in effects)
    assert dipole_deck.tolerance == pytest.approx(sum(effects))
    # A 50 ohm-ish node's pin is ~1e-10 S x |Z|: a few parts in 1e8.
    assert 1e-9 < dipole_deck.tolerance < 1e-7
    names = [k.nodes for k in dipole_deck.knots]
    assert ("rig", "T2") in names  # an ideal through joins them into one knot
    header = "\n".join(_cards(dipole_deck.text, "CM"))
    for k in dipole_deck.knots:
        assert f"knot 2/{k.segment}: node {', '.join(k.nodes)}" in header


@pytest.mark.parametrize("antenna", [DIPOLE, VEE], ids=["centre-knot", "vertex-knot"])
def test_the_deck_reads_back_as_the_same_station(antenna):
    """AK's importer reads the deck back (the phantom wire as circuit nodes,
    its pins as their 1/R) and solves within the derived tolerance."""
    sd = station_deck(_station(antenna))
    back = _z(_read_back(sd.text))
    assert _rel(back, sd.z_composite) <= sd.tolerance


def test_a_vertex_fed_antenna_takes_its_line_at_the_vertex_knot():
    """NEC-5 addresses a network end by knot (positive segment field = end
    2): the antenna's line lands on end 2 of wire 1's last segment, the knot
    its EX names."""
    text = station_deck(_station(VEE)).text
    assert _cards(text, "TL")[-1].split()[3:5] == ["1", "10"]


# --- the same deck on two NEC-5 engines ------------------------------------------


def _run_exe(exe, text):
    from antennaknobs.engines.nec5 import NEC5Engine

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


def _dropin():
    exe = pathlib.Path(sys.executable).parent / "momwire-nec5-bspline"
    return str(exe) if exe.is_file() else shutil.which("momwire-nec5-bspline")


@pytest.mark.skipif(_dropin() is None, reason="momwire-nec5-bspline not installed")
def test_momwires_nec5_drop_in_runs_the_deck():
    """The drop-in's answer against the station reduced on the drop-in's own
    antenna (its antenna-only deck's Z), so the field solver is the same on
    both sides: within the knots' bound plus two printouts' rounding."""
    exe = _dropin()
    deck = parse_nec(DIPOLE, network=True)
    antenna = _builder(deck.wire_tuples(specs=True), deck.network())
    z_ant = _run_exe(exe, export_nec5(antenna, design="a", rung="r", ground_name="g"))
    (feed,) = deck.network().ports
    engine = SimpleNamespace(
        _reducer=SimpleNamespace(port_to_idx={feed: 0}),
        _compute_y_matrix=lambda _wl: np.array([[1.0 / z_ant]]),
    )
    sd = station_deck(_station(), engine=engine)
    z = _run_exe(exe, sd.text)
    tol = sd.tolerance + _printout_rounding(z) + _printout_rounding(z_ant)
    assert _rel(z, sd.z_composite) <= tol


def _licensed():
    from antennaknobs.engines.nec5 import find_nec5

    exe = find_nec5(os.environ.get("NEC5_EXE"))
    if exe is None and os.access(os.path.expanduser("~/bin/nec5-licensed"), os.X_OK):
        exe = os.path.expanduser("~/bin/nec5-licensed")
    return exe


@pytest.mark.skipif(_licensed() is None, reason="no licensed NEC-5 (NEC5_EXE)")
@pytest.mark.parametrize("antenna", [DIPOLE, VEE], ids=["centre-knot", "vertex-knot"])
def test_the_licensed_nec5_runs_the_deck(antenna):
    """The binary's answer against the station reduced on the binary's own
    antenna Y (NEC5Engine's multiport route): the knots' bound, measured on
    that Y, plus the printout's rounding."""
    from antennaknobs.engines.nec5 import NEC5Engine

    b = _station(antenna)
    sd = station_deck(b, engine=NEC5Engine(b, nec5_exe=_licensed()))
    z = _run_exe(_licensed(), sd.text)
    assert _rel(z, sd.z_composite) <= sd.tolerance + _printout_rounding(z)


# --- what is refused, by name ----------------------------------------------------


def test_a_high_impedance_phantom_node_is_refused_by_name():
    """A quarter-wave inverter's middle: λ/4 of 2 kΩ into a ~77 Ω dipole
    puts the virtual node near 5e4 Ω, where the pin's 1e-10 S moves the
    answer past `NODE_EFFECT_LIMIT`. Such a node belongs on a real segment."""
    deck = parse_nec(DIPOLE, network=True)
    ant = deck.network()
    (feed,) = ant.ports
    wl = 299.8 / F_MHZ
    net = N.Network(
        ports={**ant.ports, "rig": N.PortVirtual("rig"), "hi": N.PortVirtual("hi")},
        branches=[
            N.TL("rig", "hi", z0=50.0, length=wl / 4),
            N.TL("hi", feed, z0=2000.0, length=wl / 4),
        ],
        sources=[N.Driven(port="rig")],
    )
    with pytest.raises(StationDeckRefusal, match=r"node 'hi' is a high-impedance"):
        station_deck(_builder(deck.wire_tuples(specs=True), net))


def test_a_sweep_is_refused_by_name():
    with pytest.raises(StationDeckRefusal, match="ONE frequency"):
        station_deck(_station(), freq=[7.0, 7.1])


def test_a_current_source_is_refused_by_name():
    deck = parse_nec(DIPOLE, network=True)
    ant = deck.network()
    (feed,) = ant.ports
    net = N.Network(
        ports={**ant.ports, "rig": N.PortVirtual("rig")},
        branches=[N.TwoPort("rig", feed, r=10.0)],
        sources=[N.DrivenCurrent(port="rig")],
    )
    with pytest.raises(StationDeckRefusal, match="current source on 'rig'"):
        station_deck(_builder(deck.wire_tuples(specs=True), net))

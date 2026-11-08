"""The synthetic stitched station of AK#2209: a 7 MHz dipole deck with a
SimNEC chain (Johnson line, S block from an inline .s2p, shunt C, series L,
lossless line, ideal transformer). Shared by the scratch scripts."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from types import MappingProxyType

from antennaknobs.builder import AntennaBuilder
from antennaknobs.nec_import import parse_nec
from antennaknobs.simnec_import import parse_ssn_station

F_MHZ = 7.0
S11, S21, S22 = 0.08 + 0.05j, 0.93 - 0.21j, -0.03 + 0.12j
S2P = "\n".join(
    ["# MHz S RI R 50"]
    + [
        f"{f} {S11.real} {S11.imag} {S21.real} {S21.imag} "
        f"{S21.real} {S21.imag} {S22.real} {S22.imag}"
        for f in (6.9, 7.0, 7.1)
    ]
)
LINE = {
    "Zo": "50",
    "VFnom": "0.66",
    "k0": "0.12942",
    "k1": "0.436326",
    "k2": "0.009218",
}
LOSSLESS = {"Zo": "75", "VFnom": "0.8", "k0": "0", "k1": "0", "k2": "0"}

DIPOLE = (
    "CM dipole\nCM NEC-5\nCE\nGW 1 20 0 -10.7 10 0 10.7 10 0.001\nGE 0\n"
    f"EX 0 1 10 2 1 0\nFR 0 1 0 0 {F_MHZ} 0\nEN\n"
)
VEE = (
    "CM NEC-5\nCE\nGW 1 10 0 -10 5 0 0 10 0.001\nGW 2 10 0 0 10 0 10 5 0.001\nGE 0\n"
    f"EX 0 1 10 2 1 0\nFR 0 1 0 0 {F_MHZ} 0\nEN\n"
)


def _element(circuit, typ, label, params):
    el = ET.SubElement(circuit, "element")
    ET.SubElement(el, "type").text = typ
    ET.SubElement(el, "sweeperLabel").text = label
    for n, v in params.items():
        p = ET.SubElement(el, "p")
        ET.SubElement(p, "n").text = n
        ET.SubElement(p, "v").text = str(v)


def ssn(*chain_from_antenna):
    root = ET.Element("SimNEC1p0")
    circuit = ET.SubElement(ET.SubElement(root, "SmithChartCircuit"), "CIRCUIT")
    _element(circuit, "LOAD", "L", {"ohms": "50", "johms": "0", "file": "<none>"})
    for typ, label, params in chain_from_antenna:
        _element(circuit, typ, label, params)
    _element(circuit, "GENERATOR", "G", {"MHz": str(F_MHZ), "Zo": "50"})
    return ET.tostring(root, encoding="unicode")


FULL_CHAIN = (
    ("TRANSFORMER2", "X1", {"Mdl": "ideal", "N": "1.5"}),
    ("SHUNT_CAP", "C1", {"F": "1e-10", "Q": "0", "@MHz": "0"}),
    ("SERIES_IND", "L1", {"H": "1.2e-6", "Q": "0", "@MHz": "0"}),
    ("SERIES_TLINE", "T1", {**LOSSLESS, "mtrs": "3"}),
    ("SCATTERING", "S2", {"dir": "2 <> 1", "Zref": "50", "file": ".\\choke.s2p"}),
    ("SERIES_TLINE", "T2", {**LINE, "mtrs": "12"}),
)


def station(chain=FULL_CHAIN, antenna=DIPOLE):
    deck = parse_nec(antenna, network=True)
    st = parse_ssn_station(
        ssn(*chain), name="t.ssn", files={"choke.s2p": S2P}.__getitem__
    )
    net = st.network(deck.network())

    class Station(AntennaBuilder):
        default_params = MappingProxyType({"freq": F_MHZ})
        c_light_mhz_m = 299.8  # a deck-loaded antenna, as the app builds one

        def build_wires(self):
            return deck.wire_tuples(specs=True)

        def build_network(self):
            return net

    return Station()

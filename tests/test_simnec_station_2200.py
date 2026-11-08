"""A SimNEC station chain hung on an antenna from elsewhere (AK#2200).

`parse_ssn_station` reads the chain between a ``.ssn``'s GENERATOR and its
antenna end (a LOAD reading an impedance table, or a NEC-portal block), and
`SsnStation.network` hangs it on any antenna's network: a native builder's,
a ``.nec`` deck's, or the table itself. Every fixture is synthetic.

The oracle is a hand cascade of chain (ABCD) matrices, generator first, built
here from each block's own definition: the line from AC6LA's Johnson model in
SI per-metre elements, the S block from its S-parameters, the capacitor from
jωC. The engine's answer is the impedance at ``rig`` with the chain stamped
by the reducer, so the two sides share nothing but the antenna.
"""

from __future__ import annotations

import cmath
import math
import xml.etree.ElementTree as ET
from types import MappingProxyType

import numpy as np
import pytest

from antennaknobs import network as N
from antennaknobs.builder import AntennaBuilder
from antennaknobs.cli import make_engine_factory
from antennaknobs.nec_import import parse_nec
from antennaknobs.network import TL, Wire
from antennaknobs.simnec_import import parse_generic_table, parse_ssn_station

C0 = 299792458.0
F_MHZ = 7.0

# The antenna end's table: Generic, frequency in MHz (scale 1e6), R, X.
TABLE = """! a synthetic antenna
Generic 1 1e6 2 3
6.9 41.0 -18.0
7.0 44.0 -9.0
7.1 47.5 2.5
"""
Z_ANT = 44.0 - 9.0j

# A reciprocal but asymmetric S block at 50 ohm (a lossy choke-like two-port),
# so its orientation matters.
S11, S21, S22 = 0.08 + 0.05j, 0.93 - 0.21j, -0.03 + 0.12j

LINE = {"Zo": "50", "VFnom": "0.66", "k0": "0.12942", "k1": "0.436326"}
LINE.update({"k2": "0.009218", "Mdl": "Belden 8259 (RG-58A/U) AC6LA (50.0 ohm)"})


def _element(circuit, typ, label, params):
    el = ET.SubElement(circuit, "element")
    ET.SubElement(el, "type").text = typ
    ET.SubElement(el, "sweeperLabel").text = label
    for n, v in params.items():
        p = ET.SubElement(el, "p")
        ET.SubElement(p, "n").text = n
        ET.SubElement(p, "v").text = str(v)


def _cx(z):
    return f"({z.real!r}{'+' if z.imag >= 0 else '-'}j{abs(z.imag)!r})"


def _s_params(direction, file="<none>"):
    return {
        "dir": direction,
        "s11r": _cx(S11),
        "s11i": "0",
        "s21r": _cx(S21),
        "s21i": "0",
        "s12r": _cx(S21),
        "s12i": "0",
        "s22r": _cx(S22),
        "s22i": "0",
        "Zref": "50",
        "file": file,
    }


def _station(*chain_from_antenna, antenna=True):
    """A chain-only ``.ssn``: the antenna LOAD first, then the chain from the
    antenna side, then the GENERATOR, as SimNEC saves a station."""
    root = ET.Element("SimNEC1p0")
    circuit = ET.SubElement(ET.SubElement(root, "SmithChartCircuit"), "CIRCUIT")
    if antenna:
        _element(
            circuit, "LOAD", "L", {"ohms": "50", "johms": "0", "file": ".\\ant.txt"}
        )
    for typ, label, params in chain_from_antenna:
        _element(circuit, typ, label, params)
    _element(circuit, "GENERATOR", "G", {"MHz": str(F_MHZ), "Zo": "50"})
    return ET.tostring(root, encoding="unicode")


S2P = "\n".join(
    [
        "# MHz S RI R 50",
        *(
            f"{f} {S11.real} {S11.imag} {S21.real} {S21.imag} "
            f"{S21.real} {S21.imag} {S22.real} {S22.imag}"
            for f in (6.9, 7.0, 7.1)
        ),
    ]
)
FILES = {"ant.txt": TABLE, "choke.s2p": S2P}


def _files(path):
    return FILES[path]


# --- the oracle ---------------------------------------------------------------


def _line_abcd(length_m, f_mhz, z0=50.0, vf=0.66, k0=0.12942, k1=0.436326, k2=0.009218):
    w = 2 * math.pi * f_mhz * 1e6
    per_m = lambda db: db / (20 / math.log(10)) / 30.48  # noqa: E731
    r_dc, r_hf = 2 * z0 * per_m(k0), 2 * z0 * per_m(k1 * math.sqrt(f_mhz))
    g = 2 * per_m(k2 * f_mhz) / z0
    zs = cmath.sqrt(r_dc**2 + (r_hf * (1 + 1j)) ** 2) + 1j * w * z0 / (vf * C0)
    ys = g + 1j * w / (z0 * vf * C0)
    gamma, zc = cmath.sqrt(zs * ys), cmath.sqrt(zs / ys)
    ch, sh = cmath.cosh(gamma * length_m), cmath.sinh(gamma * length_m)
    return np.array([[ch, zc * sh], [sh / zc, ch]])


def _s_abcd(s11, s12, s21, s22, z0=50.0):
    """Chain matrix of a two-port from its S-parameters, port 1 on the left."""
    d = 2 * s21
    return np.array(
        [
            [
                ((1 + s11) * (1 - s22) + s12 * s21) / d,
                z0 * ((1 + s11) * (1 + s22) - s12 * s21) / d,
            ],
            [
                ((1 - s11) * (1 - s22) - s12 * s21) / (z0 * d),
                ((1 - s11) * (1 + s22) + s12 * s21) / d,
            ],
        ]
    )


def _shunt_c_abcd(c, f_mhz):
    return np.array([[1, 0], [1j * 2 * math.pi * f_mhz * 1e6 * c, 1]])


def _z_in(chain_gen_first, z_load):
    m = np.eye(2, dtype=complex)
    for blk in chain_gen_first:
        m = m @ blk
    (a, b), (c, d) = m
    return (a * z_load + b) / (c * z_load + d)


# --- the engine side -----------------------------------------------------------


def _rig_z(net, f_mhz=F_MHZ):
    """Z at the station's ``rig`` with ``net`` stamped: the antenna is the
    table, and a far, tiny parasitic wire carries the field solve, which the
    chain cannot see."""
    net = N.Network(
        ports={**net.ports, "d": N.PortOnWire("d")},
        branches=[*net.branches, N.Load("d", r=1e9)],
        sources=net.sources,
    )

    class B(AntennaBuilder):
        default_params = MappingProxyType({"freq": f_mhz})

        def build_wires(self):
            return [Wire((500, 500, 50), (500, 500, 50.3), 3, name="d")]

        def build_network(self):
            return net

    return complex(make_engine_factory("momwire:razor-2p", None)(B()).impedance()[0])


def _on_table(station):
    table = station.antenna_table()
    ant = N.Network(
        ports={"feed": N.PortVirtual("feed")},
        branches=[N.TouchstoneLoad("feed", table)],
        sources=[N.Driven(port="feed", voltage=1 + 0j)],
    )
    return station.network(ant)


# --- tests ---------------------------------------------------------------------


def test_the_antenna_table_reads_as_the_station_saw_it():
    st = parse_ssn_station(_station(), name="t.ssn", files=_files)
    assert st.chain == ()
    assert _rig_z(_on_table(st)) == pytest.approx(Z_ANT, rel=1e-12)
    table = parse_generic_table(TABLE, name="ant.txt")
    assert table.freqs.tolist() == [6.9e6, 7.0e6, 7.1e6]


def test_a_line_s_block_and_shunt_c_cascade_as_their_chain_matrices():
    """Generator → 12 m of RG-58 → S block (port 1 to the generator) → 4 m of
    RG-58 → 100 pF shunt → antenna, the shape of a real EFHW station."""
    st = parse_ssn_station(
        _station(
            ("SHUNT_CAP", "C1", {"F": "1e-10", "Q": "0", "@MHz": "0"}),
            ("SERIES_TLINE", "T1", {**LINE, "mtrs": "4"}),
            ("SCATTERING", "S2", _s_params("2 <> 1")),
            ("SERIES_TLINE", "T2", {**LINE, "mtrs": "12"}),
        ),
        name="t.ssn",
        files=_files,
    )
    assert [e.label for e in st.chain] == ["T2", "S2", "T1", "C1"]
    want = _z_in(
        [
            _line_abcd(12.0, F_MHZ),
            _s_abcd(S11, S21, S21, S22),
            _line_abcd(4.0, F_MHZ),
            _shunt_c_abcd(1e-10, F_MHZ),
        ],
        Z_ANT,
    )
    assert _rig_z(_on_table(st)) == pytest.approx(want, rel=1e-9)


@pytest.mark.parametrize(
    ("direction", "gen_side_port"), [("2 <> 1", 1), ("1 <> 2", 2), ("2<>1", 1)]
)
def test_an_s_blocks_orientation_picks_which_port_faces_the_generator(
    direction, gen_side_port
):
    """``2 <> 1`` puts port 1 on the generator side (SimNEC's normal layout
    has the generator on the right); ``1 <> 2`` reverses it."""
    st = parse_ssn_station(
        _station(("SCATTERING", "S", _s_params(direction))), name="t.ssn", files=_files
    )
    s = (S11, S21, S21, S22) if gen_side_port == 1 else (S22, S21, S21, S11)
    want = _z_in([_s_abcd(*s)], Z_ANT)
    assert _rig_z(_on_table(st)) == pytest.approx(want, rel=1e-9)
    other = (S22, S21, S21, S11) if gen_side_port == 1 else (S11, S21, S21, S22)
    assert abs(_z_in([_s_abcd(*other)], Z_ANT) - want) > 0.05 * abs(want)


def test_an_s_block_reads_its_s2p_beside_the_ssn():
    inline = parse_ssn_station(
        _station(("SCATTERING", "S", _s_params("2 <> 1"))), name="t.ssn", files=_files
    )
    from_file = parse_ssn_station(
        _station(("SCATTERING", "S", _s_params("2 <> 1", file=".\\choke.s2p"))),
        name="t.ssn",
        files=_files,
    )
    assert _rig_z(_on_table(from_file)) == pytest.approx(
        _rig_z(_on_table(inline)), rel=1e-12
    )


def test_a_named_cable_is_the_johnson_line_with_its_saved_coefficients():
    st = parse_ssn_station(
        _station(("SERIES_TLINE", "T", {**LINE, "ft": str(12 / 0.3048)})),
        name="t.ssn",
        files=_files,
    )
    (tl,) = [b for b in _on_table(st).branches if isinstance(b, TL)]
    assert (tl.z0, tl.vf, tl.k0, tl.k1, tl.k2, tl.skin) == (
        50.0,
        0.66,
        0.12942,
        0.436326,
        0.009218,
        True,
    )
    assert tl.length == pytest.approx(12.0, rel=1e-12)
    in_metres = parse_ssn_station(
        _station(("SERIES_TLINE", "T", {**LINE, "mtrs": "12"})),
        name="t.ssn",
        files=_files,
    )
    assert _rig_z(_on_table(st)) == pytest.approx(
        _rig_z(_on_table(in_metres)), rel=1e-12
    )


def test_a_chain_hangs_on_a_nec_decks_own_feed():
    """The ``.nec`` + ``.ssn`` stitch: the chain sits between a new ``rig``
    and the deck's fed port, which keeps reading the antenna alone."""
    deck = parse_nec(
        "CM dipole\nCE\nGW 1 21 0 0 -10.7 0 0 10.7 0.001\nGE 0\n"
        f"EX 0 1 11 0 1 0\nFR 0 1 0 0 {F_MHZ} 0\nEN\n",
        network=True,
    )
    st = parse_ssn_station(
        _station(
            ("SCATTERING", "S", _s_params("2 <> 1")),
            ("SERIES_TLINE", "T", {**LINE, "mtrs": "12"}),
        ),
        name="t.ssn",
        files=_files,
    )
    station_net = st.network(deck.network())

    def solve(net):
        class B(AntennaBuilder):
            default_params = MappingProxyType({"freq": F_MHZ})

            def build_wires(self):
                return deck.wire_tuples()

            def build_network(self):
                return net

        return complex(
            make_engine_factory("momwire:razor-2p", None)(B()).impedance()[0]
        )

    z_ant = solve(deck.network())
    want = _z_in([_line_abcd(12.0, F_MHZ), _s_abcd(S11, S21, S21, S22)], z_ant)
    assert solve(station_net) == pytest.approx(want, rel=1e-9)
    assert [s.port for s in station_net.sources] == ["rig"]


def test_a_named_cable_without_coefficients_is_refused_by_name():
    bare = {k: v for k, v in LINE.items() if k not in ("k0", "k1", "k2")}
    st = parse_ssn_station(
        _station(("SERIES_TLINE", "T", {**bare, "mtrs": "4"})),
        name="t.ssn",
        files=_files,
    )
    with pytest.raises(ValueError, match="saved without its k0/k1/k2"):
        _on_table(st)


def test_a_line_with_no_length_is_refused_by_name():
    st = parse_ssn_station(
        _station(("SERIES_TLINE", "T", dict(LINE))), name="t.ssn", files=_files
    )
    with pytest.raises(ValueError, match="needs its length"):
        _on_table(st)


def test_a_table_antenna_read_without_its_folder_is_refused_by_name():
    st = parse_ssn_station(_station(), name="t.ssn")
    with pytest.raises(ValueError, match="read_ssn_station"):
        st.antenna_table()

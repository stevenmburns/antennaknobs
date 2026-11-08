"""A SimNEC station chain's values as design knobs (AK#2222).

`SsnStation.values` lists the numbers the chain reader turns into physics,
keyed ``label.param``, and `SsnStation.with_values` sets them. The oracle for
every edit is the same ``.ssn`` saved with the edited value: a value set
through `with_values` must build exactly the network that file builds. Every
fixture is synthetic.
"""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from types import MappingProxyType

import pytest

from antennaknobs import network as N
from antennaknobs.builder import AntennaBuilder
from antennaknobs.cli import make_engine_factory
from antennaknobs.network import Wire
from antennaknobs.simnec_import import parse_ssn_station

F_MHZ = 7.0

TABLE = """! a synthetic antenna
Generic 1 1e6 2 3
6.9 41.0 -18.0
7.0 44.0 -9.0
7.1 47.5 2.5
"""

LINE = {
    "~deg": "78.3",
    "@MHz": "3.55",
    "Mdl": "Belden 8259 (RG-58A/U) AC6LA (50.0 ohm)",
    "VFnom": "0.66",
    "Zo": "50",
    "k0": "0.12942",
    "k1": "0.436326",
    "k2": "0.009218",
}


def _element(circuit, typ, label, params):
    el = ET.SubElement(circuit, "element")
    ET.SubElement(el, "type").text = typ
    ET.SubElement(el, "sweeperLabel").text = label
    for n, v in params.items():
        p = ET.SubElement(el, "p")
        ET.SubElement(p, "n").text = n
        ET.SubElement(p, "v").text = str(v)


def _ssn(t2_m="12", c1_f="100p", t1_ft=None, c1_label="C1"):
    """Generator → T2 (metres) → T1 (feet) → shunt C1 → series L1 → the
    antenna table, saved antenna first as SimNEC saves a station."""
    root = ET.Element("SimNEC1p0")
    circuit = ET.SubElement(ET.SubElement(root, "SmithChartCircuit"), "CIRCUIT")
    _element(circuit, "LOAD", "L", {"ohms": "50", "johms": "0", "file": ".\\ant.txt"})
    _element(circuit, "SERIES_IND", "L1", {"H": "1.2u", "Q": "200", "@MHz": "7"})
    _element(circuit, "SHUNT_CAP", c1_label, {"F": c1_f, "Q": "0"})
    _element(circuit, "SERIES_TLINE", "T1", {**LINE, "ft": t1_ft or "13.12"})
    _element(circuit, "SERIES_TLINE", "T2", {**LINE, "mtrs": t2_m})
    _element(circuit, "GENERATOR", "G", {"MHz": str(F_MHZ), "Zo": "50"})
    return ET.tostring(root, encoding="unicode")


def _files(path):
    return {"ant.txt": TABLE}[path]


def _station(**kw):
    return parse_ssn_station(_ssn(**kw), name="t.ssn", files=_files)


def _on_table(station):
    ant = N.Network(
        ports={"feed": N.PortVirtual("feed")},
        branches=[N.TouchstoneLoad("feed", station.antenna_table())],
        sources=[N.Driven(port="feed", voltage=1 + 0j)],
    )
    return station.network(ant)


def _rig_z(net):
    """Z at ``rig`` with ``net`` stamped; a far, tiny parasitic wire carries
    the field solve, which the chain cannot see."""
    net = N.Network(
        ports={**net.ports, "d": N.PortOnWire("d")},
        branches=[*net.branches, N.Load("d", r=1e9)],
        sources=net.sources,
    )

    class B(AntennaBuilder):
        default_params = MappingProxyType({"freq": F_MHZ})

        def build_wires(self):
            return [Wire((500, 500, 50), (500, 500, 50.3), 3, name="d")]

        def build_network(self):
            return net

    return complex(make_engine_factory("momwire:razor-2p", None)(B()).impedance()[0])


def test_values_lists_what_the_chain_reader_reads_in_saved_units():
    v = _station().values()
    assert list(v) == [
        "T2.VFnom",
        "T2.Zo",
        "T2.k0",
        "T2.k1",
        "T2.k2",
        "T2.mtrs",
        "T1.VFnom",
        "T1.Zo",
        "T1.k0",
        "T1.k1",
        "T1.k2",
        "T1.ft",
        "C1.F",
        "C1.Q",
        "L1.H",
        "L1.Q",
    ]
    assert v["T2.mtrs"] == 12.0
    assert v["T1.ft"] == 13.12
    # SI suffixes applied: 100p and 1.2u.
    assert v["C1.F"] == pytest.approx(1e-10, rel=1e-15)
    assert v["L1.H"] == pytest.approx(1.2e-6, rel=1e-15)


@pytest.mark.parametrize(
    ("values", "saved"),
    [
        ({"T2.mtrs": 20.0}, {"t2_m": "20"}),
        ({"T1.ft": 30.0}, {"t1_ft": "30"}),
        ({"C1.F": 2.5e-10}, {"c1_f": "250p"}),
        ({"T2.mtrs": 7.5, "C1.F": 5e-11}, {"t2_m": "7.5", "c1_f": "50p"}),
    ],
)
def test_a_value_set_is_the_file_saved_with_it(values, saved):
    edited = _station().with_values(values)
    want = _rig_z(_on_table(_station(**saved)))
    got = _rig_z(_on_table(edited))
    assert got == pytest.approx(want, rel=1e-12)
    assert abs(got - _rig_z(_on_table(_station()))) > 1e-3 * abs(want)


def test_the_station_itself_is_unchanged():
    st = _station()
    before = st.values()
    st.with_values({"T2.mtrs": 20.0, "C1.F": 1e-9})
    assert st.values() == before
    assert st.with_values({}) is st


@pytest.mark.parametrize(
    ("values", "match"),
    [
        ({"T2mtrs": 1.0}, r"keys are '<label>\.<param>'"),
        (
            {"T9.mtrs": 1.0},
            r"no chain element is labelled 'T9'.*labels: C1, L1, T1, T2",
        ),
        ({"T1.mtrs": 4.0}, r"T1 carries no 'mtrs'; its adjustable values are .*ft"),
        ({"T2.~deg": 90.0}, r"'~deg' is not a value the SERIES_TLINE reader uses"),
        ({"T2.Mdl": 1.0}, r"'Mdl' is not a value"),
        ({"T2.mtrs": "long"}, r"'long' is not a number"),
        ({"T2.mtrs": math.inf}, r"is not finite"),
        ({"T2.mtrs": math.nan}, r"is not finite"),
    ],
)
def test_a_value_it_cannot_set_is_refused_by_name(values, match):
    with pytest.raises(ValueError, match=match):
        _station().with_values(values)


def test_a_shared_label_has_no_key_and_is_refused_by_name():
    st = _station(c1_label="T1")  # the shunt C now shares T1's label
    assert not any(k.startswith("T1.") for k in st.values())
    with pytest.raises(ValueError, match=r"2 chain elements are labelled 'T1'"):
        st.with_values({"T1.ft": 20.0})


class _Hybrid(AntennaBuilder):
    """A design whose knob is a coax run, the way a hybrid design uses it."""

    default_params = MappingProxyType({"freq": F_MHZ, "coax_m": 12.0})

    def build_wires(self):
        return [Wire((500, 500, 50), (500, 500, 50.3), 3, name="d")]

    def build_network(self):
        st = _station().with_values({"T2.mtrs": float(self.coax_m)})
        net = _on_table(st)
        return N.Network(
            ports={**net.ports, "d": N.PortOnWire("d")},
            branches=[*net.branches, N.Load("d", r=1e9)],
            sources=net.sources,
        )


def test_a_design_knob_drives_the_station_value():
    eng = make_engine_factory("momwire:razor-2p", None)
    for coax_m in (12.0, 20.0):
        b = _Hybrid({**_Hybrid.default_params, "coax_m": coax_m})
        got = complex(eng(b).impedance()[0])
        want = _rig_z(_on_table(_station(t2_m=str(coax_m))))
        assert got == pytest.approx(want, rel=1e-12)

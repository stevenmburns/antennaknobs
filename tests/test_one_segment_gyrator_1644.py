"""A current source spelled on a ONE-segment virtual wire is read as the
current source it is (AK#1644).

NEC-2 has no current-source card, so the idiom puts a voltage source on a
phantom segment far from the antenna and ties it to the real feed with a
GYRATOR `NT` (Y11 = Y22 = 0, Y12 = Y21 = jB). AK#1595 reads that pair as a
`DrivenCurrent`, but only when the phantom sits on a wire the AK#1577 detector
calls virtual, and that detector requires MORE than one segment. AC6LA's
SimNEC `Bydipole1` (QRZ post #117) parks a ONE-segment wire, so the gyrator
stayed a component and the driving point read where the source sits:
0.009 + j0.007 ohms, the reciprocal of the antenna's 70.38 - j52.27.

A one-segment remote wire is virtual only in this exact shape: driven, and
the end of a pure gyrator. A driven one-segment remote wire that terminates a
`TL` stays real (issue #427's negative, `test_nec_import_anchor.py`), and so
does one behind any other `NT`.
"""

import pytest

from antennaknobs.engines import MomwireEngine
from antennaknobs.file_designs import builder_from_file
from antennaknobs.nec_import import parse_nec
from antennaknobs.network import Admittance, DrivenCurrent, PortOnWire, PortVirtual

# AC6LA's Bydipole1, the cards of `snBydipole1.ssn`: an 11-segment dipole over
# average ground, and a current source on a 1-segment wire 100 wavelengths off.
DIPOLE = (
    "CE\n"
    "GW 1,11,0.,0.,9.144,0.,10.18946,9.144,.0010262\n"
    "GW 2,{n},2141.375,2141.375,2141.375,2141.396,2141.396,2141.396,.00214137\n"
    "GE 1\n"
    "FR 0,1,0,0,14.\n"
    "GN 2,0,0,0,20.,.0303\n"
    "EX 0,2,1,0,0.,1.414214\n"
    "{nt}\n"
    "EN\n"
)
GYRATOR = "NT 2,1,1,6,0.,0.,0.,1.,0.,0."
# The same antenna fed by a plain voltage source (`snBydipole1-Vsrc.ssn`).
VOLTAGE_FED = (
    "CE\n"
    "GW 1,11,0.,0.,9.144,0.,10.18946,9.144,.0010262\n"
    "GE 1\n"
    "FR 0,1,0,0,14.\n"
    "GN 2,0,0,0,20.,.0303\n"
    "EX 0,1,6,0,0.,1.414214\n"
    "EN\n"
)


def _deck(n=1, nt=GYRATOR):
    return parse_nec(DIPOLE.format(n=n, nt=nt), name="bydipole.nec", network=True)


def _z(text, tmp_path, name):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    cls = builder_from_file(str(path))
    return complex(MomwireEngine(cls(), ground=cls.file_ground).impedance()[0])


def test_a_one_segment_phantom_is_a_current_source():
    net = _deck(n=1).network()
    (src,) = net.sources
    assert isinstance(src, DrivenCurrent)
    assert src.current == pytest.approx(1.414214)
    assert isinstance(net.ports[src.port], PortOnWire)
    assert not [p for p in net.ports.values() if isinstance(p, PortVirtual)]
    assert not [b for b in net.branches if isinstance(b, Admittance)]


def test_one_segment_and_two_import_to_one_network():
    one, two = _deck(n=1).network(), _deck(n=2).network()
    assert [type(s).__name__ for s in one.sources] == ["DrivenCurrent"]
    assert [s.current for s in one.sources] == [s.current for s in two.sources]
    assert sorted(
        (type(p).__name__, getattr(p, "at", None)) for p in one.ports.values()
    ) == sorted((type(p).__name__, getattr(p, "at", None)) for p in two.ports.values())


def test_it_reads_the_antenna_not_its_reciprocal(tmp_path):
    """The user-visible claim: the driving point is the antenna's, the same
    number the voltage-fed deck reads, not 1/Z."""
    z_current = _z(DIPOLE.format(n=1, nt=GYRATOR), tmp_path, "isrc.nec")
    z_voltage = _z(VOLTAGE_FED, tmp_path, "vsrc.nec")
    assert z_current == pytest.approx(z_voltage, rel=1e-9)
    assert abs(z_current) > 10.0  # not the 0.011 + j0.006 it read


@pytest.mark.parametrize(
    "nt",
    [
        # a transformer: an all-real Y, not a gyrator
        "NT 2,1,1,6,.02,0.,-.02,0.,.02,0.",
        # a lossy two-port: a nonzero diagonal
        "NT 2,1,1,6,0.,.1,0.,1.,0.,.1",
    ],
)
def test_a_one_segment_remote_wire_behind_any_other_nt_stays_real(nt):
    """Only the gyrator makes a one-segment remote wire virtual. Behind any
    other two-port, a driven remote wire is left as the deck wrote it."""
    net = _deck(n=1, nt=nt).network()
    assert not [s for s in net.sources if isinstance(s, DrivenCurrent)]
    assert not [p for p in net.ports.values() if isinstance(p, PortVirtual)]

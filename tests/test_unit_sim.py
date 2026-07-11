from antennaknobs import Antenna
from antennaknobs.designs.dipoles.invvee import Builder

from unittest.mock import patch

from conftest import needs_pynec


class FakeInputParameters:
    """Stands in for nec_antenna_input: one row per ex_card, in emission
    order — V=1 into 0.02 A → 50 Ω at tag 2, V=0.5 into 0.02 A → 25 Ω at
    tag 4 (the mock_geometry excitation_pairs below)."""

    def get_tag(self):
        return [2, 4]

    def get_impedance(self):
        return [50 + 0j, 25 + 0j]


class FakePyNEC:
    def fr_card(self, *args, **kargs):
        pass

    def xq_card(self, *args, **kargs):
        pass

    def get_input_parameters(self, freq_index):
        return FakeInputParameters()


def mock_geometry(self):
    self.c = FakePyNEC()
    self.excitation_pairs = [(2, 1, 1 + 0j), (4, 2, 0.5 + 0j)]


@needs_pynec
@patch("antennaknobs.Antenna._build_geometry", new=mock_geometry)
def test_impedence_with_mock_Antenna():

    a = Antenna(Builder())
    zs = a.impedance()
    assert len(zs) == 2
    assert abs(zs[0] - 50) < 0.001 and abs(zs[1] - 25) < 0.001

    zs = a.impedance(sum_currents=1)
    assert len(zs) == 1
    assert abs(zs[0] - 16.6666667) < 0.001

"""`antennaknobs.Antenna` — the quick start's first name.

It used to be `PyNECEngine`, which is `None` without the optional
`pynec-accel` extra, so `Antenna(Builder())` raised "'NoneType' object is not
callable" on every plain install (antennaknobs#1323, 2026-09-10). The alias
is the momwire engine now, and the first test here is the one that would have
caught it: it runs WITHOUT PyNEC and solves.
"""

import sys

from unittest.mock import patch

from antennaknobs import Antenna
from antennaknobs.designs.dipoles.invvee import Builder
from antennaknobs.engines.momwire import MomwireEngine

from conftest import needs_pynec


def test_the_antenna_alias_is_the_momwire_engine_and_solves_without_pynec():
    """The documented first example, verbatim, on the solver every install
    has. `Antenna` must never be None whether or not pynec-accel is present."""
    assert Antenna is MomwireEngine
    z = Antenna(Builder()).impedance()
    assert len(z) == 1
    assert 40.0 < z[0].real < 60.0 and -20.0 < z[0].imag < 5.0, z


def test_the_alias_does_not_depend_on_pynec_being_importable(monkeypatch):
    """Re-import `antennaknobs.sim` with the PyNEC engine module blocked: the
    alias must still resolve to a callable engine."""
    import importlib

    monkeypatch.setitem(sys.modules, "antennaknobs.engines.pynec", None)
    monkeypatch.delitem(sys.modules, "antennaknobs.sim", raising=False)
    sim = importlib.import_module("antennaknobs.sim")
    assert sim.Antenna is MomwireEngine


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
@patch("antennaknobs.engines.pynec.PyNECEngine._build_geometry", new=mock_geometry)
def test_impedance_with_a_mocked_pynec_engine():
    """The PyNEC readout path, on the PyNEC engine by its own name — this
    test used to reach it through `Antenna`, which is no longer PyNEC."""
    from antennaknobs.engines.pynec import PyNECEngine

    a = PyNECEngine(Builder())
    zs = a.impedance()
    assert len(zs) == 2
    assert abs(zs[0] - 50) < 0.001 and abs(zs[1] - 25) < 0.001

    zs = a.impedance(sum_currents=1)
    assert len(zs) == 1
    assert abs(zs[0] - 16.6666667) < 0.001

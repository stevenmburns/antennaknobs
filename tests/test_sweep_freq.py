import antennaknobs as ant
from antennaknobs.designs.dipoles.invvee import Builder
from antennaknobs.designs.dipoles.invvee_coax_station import (
    Builder as StationBuilder,
)
from antennaknobs.sweep import _z_title

from conftest import needs_pynec


@needs_pynec
def test_fandipole_sweep_freq():
    ant.sweep_freq(Builder(), z0=50, rng=(10, 30), npoints=2, fn="/dev/null")


def test_impedance_title_names_the_driven_plane():
    """ "feedpoint" is only true for a bare antenna (issue #652): a station
    design is solved at the port its source sits on, and titling that chart
    "feedpoint" invites comparing a VNA calibrated at the wrong plane."""
    assert _z_title(Builder(), "freq") == "feedpoint impedance vs freq"
    assert _z_title(StationBuilder(), "freq") == "impedance at rig vs freq"

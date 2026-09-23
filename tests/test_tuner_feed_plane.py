"""Reading the plane on the antenna side of a self-tuning tuner.

AC6LA's LC1 file (SimNEC's automatic LC match, imported as the self-tuning L
tuner) solved at `rig` and at the tuner's own plane, but momwire raised an
IndexError at `feed`: re-rooting the network at the antenna terminals drops
the generator side, tuner included, while the flattened network still listed
the tuner's composite. Seen from `feed` the tuner has nothing to tune, so the
answer is the antenna's own impedance, which is what NEC-5 and NEC-2 read.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from antennaknobs.auto_match import find_tuners
from antennaknobs.engines import MomwireEngine
from antennaknobs.file_designs import builder_from_file
from antennaknobs.plane import driven_at

LC1 = Path(__file__).parent / "fixtures" / "simnec_ac6la_1679" / "snBydipole1-LC1.ssn"


def _at(cls, plane):
    b = cls()
    net = driven_at(b.build_network(), plane)
    object.__setattr__(b, "build_network", lambda: net)
    return b


def test_a_tuner_outside_the_rerooted_circuit_is_not_found():
    cls = builder_from_file(str(LC1))
    assert len(find_tuners(cls().build_network())) == 1
    assert find_tuners(driven_at(cls().build_network(), "feed")) == []


def test_momwire_reads_the_antenna_at_feed_behind_a_self_tuning_tuner():
    cls = builder_from_file(str(LC1))
    z_feed = MomwireEngine(_at(cls, "feed"), ground=cls.file_ground).impedance()[0]
    # The tuner still tunes the rig to 50 ohms...
    z_rig = MomwireEngine(cls(), ground=cls.file_ground).impedance()[0]
    assert abs(z_rig - 50.0) < 1e-6
    # ...and `feed` is the antenna alone: a finite, un-matched impedance.
    assert np.isfinite(z_feed) and abs(z_feed - 50.0) > 5.0

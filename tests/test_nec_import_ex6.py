"""EX 6 current-source excitation (4nec2 dialect, issue #442).

Deck-level contract: ``EX 6`` parses in network mode into a ``NecFeed``
with ``current=True`` and a ``DrivenCurrent`` source in ``network()``.
Engine-level oracle: a one-port's driving-point impedance is independent
of the ideal-source kind, so the same dipole driven by ``EX 6`` and by
``EX 0`` must report identical Z — through the full deck → builder →
MomwireEngine → NetworkReducer stack.
"""

import pytest

from antennaknobs import AntennaBuilder, WireSpec
from antennaknobs.engines import MomwireEngine
from antennaknobs.nec_import import parse_nec
from antennaknobs.network import Driven, DrivenCurrent
from momwire import SinusoidalSolver

FREQ = 14.1


def _deck_builder(deck, freq=FREQ):
    class B(AntennaBuilder):
        default_params = {"freq": freq}

        def build_wires(self):
            return deck.wire_tuples()

        def build_network(self):
            return deck.network()

        def build_wire_material(self):
            return WireSpec(radius=deck.dominant_radius())

    return B()


def _z(deck):
    eng = MomwireEngine(_deck_builder(deck), solver=SinusoidalSolver, ground=None)
    return eng.impedance()


DIPOLE_EX6 = "GW 1 11 0 -5 10 0 5 10 0.001\nGE\nEX 6 1 6 0 1 0\nEN\n"
DIPOLE_EX0 = "GW 1 11 0 -5 10 0 5 10 0.001\nGE\nEX 0 1 6 0 1 0\nEN\n"


def test_ex6_parses_to_driven_current():
    deck = parse_nec(DIPOLE_EX6, name="t", network=True)
    (feed,) = deck.feeds
    assert feed.current is True
    assert feed.voltage == 1 + 0j  # the field carries amps for EX 6
    (src,) = deck.network().sources
    assert isinstance(src, DrivenCurrent)
    assert src.current == 1 + 0j


def test_ex0_still_voltage():
    deck = parse_nec(DIPOLE_EX0, name="t", network=True)
    assert deck.feeds[0].current is False
    (src,) = deck.network().sources
    assert isinstance(src, Driven)


def test_ex6_needs_network_mode():
    with pytest.raises(ValueError, match="network=True"):
        parse_nec(DIPOLE_EX6, name="t", network=False)


def test_mixed_ex0_and_ex6_feeds():
    deck = parse_nec(
        "GW 1 11 0 -5 10 0 5 10 0.001\nGW 2 11 3 -5 10 3 5 10 0.001\nGE\n"
        "EX 0 1 6 0 1 0\nEX 6 2 6 0 -0.86 0.508\nEN\n",
        name="t",
        network=True,
    )
    kinds = [type(s) for s in deck.network().sources]
    assert kinds == [Driven, DrivenCurrent]
    assert deck.network().sources[1].current == -0.86 + 0.508j


def test_impedance_is_source_kind_independent():
    """The physics oracle: same dipole, EX 6 vs EX 0, identical Z through
    the full engine stack (a one-port's Z doesn't depend on the source)."""
    z_i = _z(parse_nec(DIPOLE_EX6, name="i", network=True))[0]
    z_v = _z(parse_nec(DIPOLE_EX0, name="v", network=True))[0]
    assert z_i == pytest.approx(z_v, rel=1e-9)


def test_phased_pair_scales_with_drive_ratio():
    """Two current-driven elements: doubling BOTH drive currents must leave
    every port impedance unchanged (linearity), while the mutual coupling
    makes each Z differ from the isolated element's."""
    base = (
        "GW 1 11 0 -5 10 0 5 10 0.001\nGW 2 11 3 -5 10 3 5 10 0.001\nGE\n"
        "EX 6 1 6 0 {a_re} {a_im}\nEX 6 2 6 0 1 0\nEN\n"
    )
    z1 = _z(parse_nec(base.format(a_re=-0.86, a_im=0.508), name="p1", network=True))
    z2 = _z(
        parse_nec(
            "GW 1 11 0 -5 10 0 5 10 0.001\nGW 2 11 3 -5 10 3 5 10 0.001\nGE\n"
            "EX 6 1 6 0 -1.72 1.016\nEX 6 2 6 0 2 0\nEN\n",
            name="p2",
            network=True,
        )
    )
    assert z1[0] == pytest.approx(z2[0], rel=1e-9)
    assert z1[1] == pytest.approx(z2[1], rel=1e-9)
    z_iso = _z(parse_nec(DIPOLE_EX6, name="iso", network=True))[0]
    assert abs(z1[1] - z_iso) > 1.0  # coupling actually shows up in Z


def test_pynec_takes_reducer_path_and_matches():
    """PyNEC has no native current excitation, so an EX 6 network must
    divert to the multiport-Y reducer path — and agree with the voltage
    drive on the one-port oracle just like momwire."""
    from antennaknobs.engines.pynec import PyNECEngine

    z_i = PyNECEngine(
        _deck_builder(parse_nec(DIPOLE_EX6, name="i", network=True)), ground=None
    ).impedance()[0]
    z_v = PyNECEngine(
        _deck_builder(parse_nec(DIPOLE_EX0, name="v", network=True)), ground=None
    ).impedance()[0]
    assert z_i == pytest.approx(z_v, rel=1e-9)

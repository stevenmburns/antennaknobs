"""Issue #414: EK extended thin-wire kernel — importer flag + PyNEC plumbing.

NEC's EK card switches the kernel from the thin-wire (filament) current
approximation to the extended kernel, which matters for fat wires (radius
comparable to segment length). nec2c applies EK; dropping it made fat-wire
deck comparisons kernel-inconsistent (the `1MHz_tower` five-way scatter,
momwire#156). The importer now records the card on
``NecDeck.extended_kernel`` and ``PyNECEngine(extended_thin_wire_kernel=
True)`` emits it via PyNEC's ``set_extended_thin_wire_kernel``.
"""

from types import MappingProxyType

import pytest

from antennaknobs import AntennaBuilder, Wire, WireSpec
from antennaknobs.nec_import import parse_nec

FREQ = 300.0  # MHz -> ~1 m wavelength


DECK_TEMPLATE = """CE fat dipole
GW 1 15 -0.25 0 0 0.25 0 0 {radius}
GE 0
{ek}FR 0 1 0 0 300.0
EX 0 1 8 0 1.0 0.0
EN
"""


def test_importer_records_ek():
    deck = parse_nec(DECK_TEMPLATE.format(radius=0.008, ek="EK\n"), name="t")
    assert deck.extended_kernel
    assert "EK" not in deck.ignored


def test_importer_ek_off_and_absent():
    off = parse_nec(DECK_TEMPLATE.format(radius=0.008, ek="EK -1\n"), name="t")
    assert not off.extended_kernel
    plain = parse_nec(DECK_TEMPLATE.format(radius=0.008, ek=""), name="t")
    assert not plain.extended_kernel


def _fat_dipole_builder():
    """Half-wave dipole with a/h ~ 0.24 (8 mm radius, ~33 mm segments) —
    deliberately fat so the two kernels visibly disagree."""
    spec = WireSpec(radius=0.008)

    class _B(AntennaBuilder):
        default_params = MappingProxyType({"freq": FREQ})

        def build_wires(self):
            return [
                Wire((-0.25, 0.0, 0.0), (0.0, 0.0, 0.0), 7, None, None, spec),
                Wire((0.0, 0.0, 0.0), (0.25, 0.0, 0.0), 8, 1 + 0j, None, spec),
            ]

    return _B()


def test_extended_kernel_changes_fat_wire_reactance():
    pytest.importorskip("PyNEC")
    from antennaknobs.engines.pynec import PyNECEngine

    z_std = PyNECEngine(_fat_dipole_builder(), ground=None).impedance()[0]
    z_ext = PyNECEngine(
        _fat_dipole_builder(), ground=None, extended_thin_wire_kernel=True
    ).impedance()[0]
    # The kernels must actually differ on a fat wire (ohms — here ~4.7 Ω in
    # R and ~0.9 Ω in X at a/h ≈ 0.24), while staying the same antenna.
    assert abs(z_ext - z_std) > 2.0
    assert abs(z_ext - z_std) < 0.3 * abs(z_std)

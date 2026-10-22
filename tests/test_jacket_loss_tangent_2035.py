"""A jacket's dielectric loss tangent, read from a file and solved (AK#2035).

The .ez and SimNEC readers used to refuse any jacket with a loss tangent,
because the app's jacket was lossless. momwire serves the loss since
momwire#765 (`insulation_loss_tangent`), so the readers now carry tan δ to the
wire spec and the momwire engine passes it per wire. No NEC card holds a lossy
jacket (the a'+L' pair is lossless), so the NEC engines and writers refuse it
by name rather than solve it as lossless. AK#1997 is the wider issue.
"""

from __future__ import annotations

import dataclasses

import pytest
from test_ez_import_1958 import DIPOLE, _open, _z, ez_file, insulation_block

from antennaknobs.engines._nec_wire import nec_wire_material
from antennaknobs.ez_import import read_ez
from antennaknobs.wire_catalog import wire_from_catalog

PVC = (3.5, 0.001)  # eps_r, radial thickness m


def _raw(tand: float) -> bytes:
    return ez_file(DIPOLE, blocks=[insulation_block([(*PVC, tand)])])


def test_the_ez_reader_carries_the_loss_tangent_to_the_wire_spec():
    deck = read_ez(_raw(0.05)).deck
    assert deck.wire_insulation == ((0, (pytest.approx(0.002), pytest.approx(3.5))),)
    assert deck.wire_insulation_loss_tangent == ((0, pytest.approx(0.05)),)
    (wire,) = deck.wire_tuples(specs=True)
    assert wire.spec.insulation_loss_tangent == pytest.approx(0.05)


def test_a_lossless_jacket_carries_no_loss_tangent():
    deck = read_ez(_raw(0.0)).deck
    assert deck.wire_insulation
    assert deck.wire_insulation_loss_tangent == ()
    (wire,) = deck.wire_tuples(specs=True)
    assert wire.spec.insulation_loss_tangent is None


def test_the_lossy_jacket_raises_r_and_nothing_else_moves():
    """The loss is the only difference between the two files, so the solve
    must move R up; a lossless file must solve exactly as before."""
    lossless = _z(_open(_raw(0.0)))
    lossy = _z(_open(_raw(0.05)))
    assert lossy.real > lossless.real + 0.05
    assert abs(lossy.imag - lossless.imag) < 0.05 * abs(lossless.imag) + 1.0
    assert _z(_open(_raw(0.0))) == lossless


def test_a_loss_tangent_out_of_range_is_malformed():
    with pytest.raises(ValueError, match="loss tangent -0.1"):
        read_ez(_raw(-0.1))


def test_the_nec_cards_refuse_a_lossy_jacket_by_name():
    pvc = dataclasses.replace(
        wire_from_catalog("18-awg-pvc"), insulation_loss_tangent=0.05
    )
    with pytest.raises(ValueError, match="loss tangent 0.05 has no NEC cards"):
        nec_wire_material(pvc.radius, pvc.conductivity, pvc)
    # The inductance-only spelling (SimNEC's portal) carries the loss in its
    # own W7EL directive, so it is not refused here.
    assert nec_wire_material(pvc.radius, pvc.conductivity, pvc, pair=False)


def test_a_lossy_jacket_round_trips_through_simnecs_w7el(tmp_path):
    """SimNEC's W7EL directive has a loss-tangent field; the export writes the
    spec's tan δ there and the reader brings it back."""
    from antennaknobs.designs.dipoles.pota_invvee import Builder
    from antennaknobs.file_designs import builder_from_file
    from antennaknobs.simnec_export import export_ssn
    from antennaknobs.wire_catalog import as_wire

    class Lossy(Builder):
        def build_wire_material(self):
            return dataclasses.replace(
                super().build_wire_material(), insulation_loss_tangent=0.02
            )

    ssn = export_ssn(Lossy(), ground=None)
    assert 'NECOptions.Insulation("W7EL", 0.000479, 3.5, 0.02);' in ssn
    path = tmp_path / "lossy.ssn"
    path.write_text(ssn)
    for t in builder_from_file(str(path))().build_wires():
        assert as_wire(t).spec.insulation_loss_tangent == pytest.approx(0.02)

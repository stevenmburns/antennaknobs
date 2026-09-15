"""A jacket as NEC cards (issue #1523): the NEC writers give NEC momwire's
coated-wire pair — the equivalent radius on GW, LD 2 for the jacket's
inductance, and LD 5's conductivity rescaled for the larger radius.

The rescaling is what the GW radius forces. NEC evaluates a conductor's
internal impedance at the GW radius, so a' there with the spec's own
conductivity would cut the copper's resistance by 41-80 % on the catalog's PVC
wires. These tests pin the identity that puts it back, and hold each engine's
spelling of the pair equal to one built another way.
"""

import dataclasses

import numpy as np
import pytest
from momwire import equivalent_radius, insulation_inductance, wire_internal_impedance

from antennaknobs.designs.dipoles.invvee import Builder
from antennaknobs.engines import NEC5Engine, PyNECEngine
from antennaknobs.engines._nec_wire import NecWireMaterial, nec_wire_material
from antennaknobs.network import WIRES, WireSpec

from conftest import needs_nec5, needs_pynec, pair_pynec

PVC = ("28-awg-pvc", "22-awg-pvc", "18-awg-pvc")


def _z(engine):
    return complex(np.asarray(engine.impedance()).ravel()[0])


def _rel(z, ref):
    return abs(z - ref) / abs(ref)


def _builder(wire_type):
    b = Builder()
    b.wire_type = wire_type
    return b


def _pec(wire_type, monkeypatch):
    """The catalog wire with conductor loss switched off, registered for one
    test only: `test_catalog_entries_consistent` walks every WIRES entry."""
    spec = dataclasses.replace(WIRES[wire_type], conductivity=None)
    monkeypatch.setitem(WIRES, f"_pec_{wire_type}", spec)
    return _builder(f"_pec_{wire_type}")


class _InductanceOnly(PyNECEngine):
    """A jacket as LD 2 alone, on the bare radius — not the pair."""

    _jacket_pair = False


@pytest.mark.parametrize("wire_type", PVC)
def test_rescaled_conductivity_keeps_the_conductor(wire_type):
    """Z_int(a', sigma·(a/a')²) is Z_int(a, sigma) at every frequency, from DC
    through deep skin effect, while the spec's own conductivity at a' is a
    different wire."""
    spec = WIRES[wire_type]
    mat = nec_wire_material(spec.radius, spec.conductivity, spec)
    assert mat.radius == equivalent_radius(
        spec.radius, spec.insulation_radius, spec.insulation_eps_r
    )
    omega = 2 * np.pi * np.array([1e3, 1.8e6, 14.2e6, 50e6])
    z_conductor = wire_internal_impedance(omega, spec.radius, spec.conductivity)
    z_card = wire_internal_impedance(omega, mat.radius, mat.conductivity)
    np.testing.assert_allclose(z_card, z_conductor, rtol=1e-12)
    z_unscaled = wire_internal_impedance(omega, mat.radius, spec.conductivity)
    assert np.all(z_unscaled.real < 0.65 * z_conductor.real)


def test_bare_pec_and_inductance_only_spellings():
    bare = WireSpec(radius=5e-4, conductivity=5.8e7)
    assert nec_wire_material(5e-4, 5.8e7, bare) == NecWireMaterial(5e-4, 5.8e7, None)
    assert nec_wire_material(5e-4, None, None) == NecWireMaterial(5e-4, None, None)

    jacket = WireSpec(
        radius=5e-4, conductivity=5.8e7, insulation_radius=9e-4, insulation_eps_r=3.5
    )
    l_ins = insulation_inductance(5e-4, 9e-4, 3.5)
    assert nec_wire_material(5e-4, 5.8e7, jacket, pair=False) == NecWireMaterial(
        5e-4, 5.8e7, l_ins
    )
    pec = nec_wire_material(5e-4, None, jacket)
    assert pec == NecWireMaterial(equivalent_radius(5e-4, 9e-4, 3.5), None, l_ins)


@needs_pynec
@pytest.mark.parametrize("wire_type", PVC)
def test_pynec_engine_writes_the_pair(wire_type, monkeypatch):
    """PyNECEngine's pair (LD 5 rescaled) against `pair_pynec`'s (the conductor
    folded into LD 2 at the design frequency). Measured 7.6e-6 to 1.9e-5 with
    copper, and identical cards without it. The inductance-only spelling sits
    4.6-5.7 % away, so the bar cannot pass without the pair."""
    z_oracle = _z(pair_pynec(_builder(wire_type), lossy=True))
    assert _rel(_z(PyNECEngine(_builder(wire_type), ground=None)), z_oracle) < 1e-4
    assert _rel(_z(_InductanceOnly(_builder(wire_type), ground=None)), z_oracle) > 0.03

    z_pec = _z(PyNECEngine(_pec(wire_type, monkeypatch), ground=None))
    z_pec_oracle = _z(pair_pynec(_pec(wire_type, monkeypatch), lossy=False))
    assert _rel(z_pec, z_pec_oracle) < 1e-12


@needs_nec5
def test_nec5_rescaled_ld5_is_the_folded_conductor():
    """NEC-5's LD 5 honours the rescaling. The engine's deck against the same
    deck with the conductor folded into LD 2 at that frequency: measured
    <= 1.6e-5 at 0.5x, 1x and 1.5x the design frequency, the printout's own
    resolution. The unscaled conductivity on the same GW radius is the
    control, and must miss."""
    from antennaknobs.engines.nec5 import find_nec5, run_deck

    spec = WIRES["28-awg-pvc"]
    b = _builder("28-awg-pvc")
    engine = NEC5Engine(b, ground=None)
    l_ins = insulation_inductance(
        spec.radius, spec.insulation_radius, spec.insulation_eps_r
    )

    def solve(deck):
        text = run_deck(find_nec5(), deck, timeout=120)
        return NEC5Engine._parse_input_parameters(text)[0][0][2]

    for f in (b.freq, 1.5 * b.freq):
        deck = engine.deck([f])
        lines = deck.splitlines()
        omega = 2 * np.pi * f * 1e6
        z_int = wire_internal_impedance(omega, spec.radius, spec.conductivity)
        folded = [ln for ln in lines if not ln.startswith(("LD 5", "LD 2"))]
        at = next(i for i, ln in enumerate(folded) if ln.startswith("GE")) + 1
        folded.insert(
            at, f"LD 2 0 0 0 {z_int.real:.9E} {l_ins + z_int.imag / omega:.9E} 0."
        )
        unscaled = [
            f"LD 5 0 0 0 {spec.conductivity:.6E} 0. 0." if ln.startswith("LD 5") else ln
            for ln in lines
        ]
        z_scaled = solve(deck)
        z_folded = solve("\n".join(folded) + "\n")
        z_unscaled = solve("\n".join(unscaled) + "\n")
        assert _rel(z_scaled, z_folded) < 1e-4, (f, z_scaled, z_folded)
        assert _rel(z_unscaled, z_folded) > 1e-3, (f, z_unscaled, z_folded)


@needs_nec5
def test_nec5_matches_razor_2p_on_a_jacketed_catalog_design(monkeypatch):
    """The catalog's worst razor-2p vs NEC-5 row was dipoles.pota_invvee, and
    the jacket drove it. razor-2p is momwire's formulation matched to NEC-5, so
    given the same pair the two agree: measured 0.10 % in free space (0.09 %
    over the default ground), against 14.4 % with the inductance-only
    spelling."""
    import functools

    from momwire import RazorSolver

    import antennaknobs.engines.nec5 as nec5
    from antennaknobs.designs.dipoles.pota_invvee import Builder as PotaInvVee
    from antennaknobs.engines import MomwireEngine

    z_razor = _z(
        MomwireEngine(
            PotaInvVee(),
            ground=None,
            solver=RazorSolver,
            solver_kwargs={"nec5_quadrature": True},
        )
    )
    assert _rel(_z(NEC5Engine(PotaInvVee(), ground=None)), z_razor) < 0.005
    monkeypatch.setattr(
        nec5, "nec_wire_material", functools.partial(nec_wire_material, pair=False)
    )
    assert _rel(_z(NEC5Engine(PotaInvVee(), ground=None)), z_razor) > 0.05

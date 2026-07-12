"""Wire material plumbing (issue #316): WIRES catalog, the
`build_wire_material` hook, and both engines consuming the spec.

The engine-level oracle is momwire#131's distributed loading vs PyNEC's
native NEC-2 wire-loss card (ld_card type 5) — two independent
implementations of skin-effect conductor loss on the same geometry.
"""

import numpy as np
import pytest

from antennaknobs.designs.dipoles.invvee import Builder
from antennaknobs.engines import MomwireEngine, PyNECEngine
from antennaknobs.network import COPPER_CONDUCTIVITY, WIRES, wire_from_catalog

from conftest import needs_pynec


def _z(engine):
    z = engine.impedance()
    return complex(z[0]) if isinstance(z, (list, tuple)) else complex(z)


def _builder(wire_type=None):
    b = Builder()
    if wire_type is not None:
        b.wire_type = wire_type
    return b


# ----------------------------------------------------------------------
# Catalog
# ----------------------------------------------------------------------


def test_catalog_entries_consistent():
    """Radii are AWG (each ~3 gauge steps ≈ ×√2 diameter), copper weights
    match the cross-section, insulated variants share the conductor."""
    rho_cu = 8.96  # g/cm³
    for name, w in WIRES.items():
        assert w.conductivity == COPPER_CONDUCTIVITY
        base = WIRES[name.removesuffix("-pvc")]
        assert w.radius == base.radius
        w_cu = rho_cu * np.pi * (w.radius * 100) ** 2 * 100  # g/m
        if name.endswith("-pvc"):
            assert w.insulation_radius > w.radius
            assert w.insulation_eps_r >= 1.0
            assert w.weight_g_per_m > base.weight_g_per_m
        else:
            assert w.insulation_radius is None
            assert w.weight_g_per_m == pytest.approx(w_cu, rel=0.02)
    # 28 → 22 → 18 AWG: 6 gauge steps ≈ diameter ×2 each
    assert WIRES["22-awg"].radius / WIRES["28-awg"].radius == pytest.approx(
        2.0, rel=0.02
    )
    assert WIRES["18-awg"].radius / WIRES["22-awg"].radius == pytest.approx(
        1.6, rel=0.02
    )


def test_catalog_lookup_error_ergonomics():
    with pytest.raises(KeyError, match="unknown wire.*available"):
        wire_from_catalog("12-awg")


def test_builder_hook_default_and_wire_type():
    assert _builder().build_wire_material() is None
    assert _builder("28-awg") is not None
    assert _builder("28-awg").build_wire_material() is WIRES["28-awg"]
    with pytest.raises(KeyError):
        _builder("no-such-wire").build_wire_material()


# ----------------------------------------------------------------------
# MomwireEngine consumption
# ----------------------------------------------------------------------


def test_momwire_ideal_solve_unchanged():
    """No wire_type → today's idealization, bit-for-bit."""
    z_a = _z(MomwireEngine(_builder(), ground=None))
    z_b = _z(MomwireEngine(_builder(), ground=None))
    assert z_a == z_b  # determinism sanity for the comparisons below


def test_momwire_spec_radius_and_loss():
    z0 = _z(MomwireEngine(_builder(), ground=None))
    z1 = _z(MomwireEngine(_builder("28-awg"), ground=None))
    # Thinner + lossy wire: R must rise. (The shift includes both the real
    # 28 AWG radius and the copper loading.)
    assert z1.real > z0.real + 1.0


def test_momwire_insulation_shifts_reactance():
    z_bare = _z(MomwireEngine(_builder("28-awg"), ground=None))
    z_pvc = _z(MomwireEngine(_builder("28-awg-pvc"), ground=None))
    # Same conductor, added jacket: electrically longer → X rises; the
    # jacket is lossless so R moves only via the resonance shift.
    assert z_pvc.imag > z_bare.imag + 10.0


def test_momwire_explicit_radius_overrides_spec():
    """A non-default wire_radius (the web model-options control) wins over
    the spec radius; the stock 0.0005 defers to the spec."""
    e_auto = MomwireEngine(_builder("28-awg"), ground=None)
    assert e_auto._wire_radius == WIRES["28-awg"].radius
    e_explicit = MomwireEngine(_builder("28-awg"), ground=None, wire_radius=0.001)
    assert e_explicit._wire_radius == 0.001
    e_ideal = MomwireEngine(_builder(), ground=None)
    assert e_ideal._wire_radius == 0.0005


def test_momwire_sinusoidal_drops_loading_keeps_radius(caplog):
    """SinusoidalSolver can't model the loading: warn, solve with the real
    radius but ideal metal — NOT a crash, NOT a silent identical solve."""
    from momwire import SinusoidalSolver

    with caplog.at_level("WARNING"):
        e = MomwireEngine(_builder("28-awg"), ground=None, solver=SinusoidalSolver)
    assert "doesn't model distributed wire loading" in caplog.text
    assert e._loading_kwargs == {}
    assert e._wire_radius == WIRES["28-awg"].radius


# ----------------------------------------------------------------------
# PyNEC consumption + the cross-engine loss oracle
# ----------------------------------------------------------------------


@needs_pynec
def test_pynec_ld5_and_radius_from_spec(caplog):
    z0 = _z(PyNECEngine(_builder(), ground=None))
    z1 = _z(PyNECEngine(_builder("28-awg"), ground=None))
    assert z1.real > z0.real + 1.0
    # Insulation: no NEC-2 card — warned, solved as the bare variant.
    with caplog.at_level("WARNING"):
        z2 = _z(PyNECEngine(_builder("28-awg-pvc"), ground=None))
    assert "no insulated-wire card" in caplog.text
    assert z2 == pytest.approx(z1, rel=1e-12)


@needs_pynec
def test_nec_export_carries_spec():
    """The exported deck is a text twin of what PyNECEngine solves: spec
    radius on the GW cards, the global LD 5 when the design's wire is
    lossy, and neither for the ideal default."""
    from antennaknobs.nec_export import export_nec

    deck = export_nec(_builder("28-awg"), ground=None)
    assert "LD 5 0 0 0  5.800000E+07" in deck
    assert " 1.600000E-04" in deck  # 28 AWG radius on the GW cards
    deck0 = export_nec(_builder(), ground=None)
    assert "LD 5" not in deck0
    assert " 5.000000E-04" in deck0


@needs_pynec
def test_cross_engine_skin_loss_oracle():
    """momwire's distributed loading vs NEC's native ld_card type 5 on the
    same free-space invvee: the ideal→28-awg ΔR (radius + copper) from two
    independent implementations must agree to a few percent."""
    dr_momwire = (
        _z(MomwireEngine(_builder("28-awg"), ground=None)).real
        - _z(MomwireEngine(_builder(), ground=None)).real
    )
    dr_pynec = (
        _z(PyNECEngine(_builder("28-awg"), ground=None)).real
        - _z(PyNECEngine(_builder(), ground=None)).real
    )
    assert dr_momwire == pytest.approx(dr_pynec, rel=0.05)

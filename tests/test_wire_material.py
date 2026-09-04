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

from conftest import needs_pynec, pair_pynec


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


def test_momwire_sinusoidal_carries_loading():
    """SinusoidalSolver models the loading since momwire 0.11.0
    (momwire#134): the kwargs thread through and the lossy solve shifts R
    like the BSpline one — no warning, no silent ideal-metal solve."""
    from momwire import SinusoidalSolver

    e = MomwireEngine(_builder("28-awg"), ground=None, solver=SinusoidalSolver)
    assert e._loading_kwargs["wire_conductivity"] == COPPER_CONDUCTIVITY
    assert e._wire_radius == WIRES["28-awg"].radius
    z0 = _z(MomwireEngine(_builder(), ground=None, solver=SinusoidalSolver))
    z1 = _z(e)
    assert z1.real > z0.real + 1.0


# ----------------------------------------------------------------------
# PyNEC consumption + the cross-engine loss oracle
# ----------------------------------------------------------------------


@needs_pynec
def test_pynec_ld5_and_radius_from_spec():
    z0 = _z(PyNECEngine(_builder(), ground=None))
    z1 = _z(PyNECEngine(_builder("28-awg"), ground=None))
    assert z1.real > z0.real + 1.0
    # Insulation: LD 2 distributed series L' — electrically longer, X
    # rises (mirrors test_momwire_insulation_shifts_reactance). NEC stacks
    # LD cards in series, so the LD 5 copper loss must survive alongside:
    # R stays elevated over the ideal wire.
    z2 = _z(PyNECEngine(_builder("28-awg-pvc"), ground=None))
    assert z2.imag > z1.imag + 10.0
    assert z2.real > z0.real + 1.0


@needs_pynec
def test_nec_export_carries_spec():
    """The exported deck is a text twin of what PyNECEngine solves: spec
    radius on the GW cards, the global LD 5 when the design's wire is
    lossy, and neither for the ideal default."""
    from antennaknobs.nec_export import export_nec

    deck = export_nec(_builder("28-awg"), ground=None)
    assert "LD 5 0 0 0  5.800000E+07" in deck
    assert " 1.600000E-04" in deck  # 28 AWG radius on the GW cards
    assert "LD 2" not in deck  # bare wire: no insulation card
    deck0 = export_nec(_builder(), ground=None)
    assert "LD 5" not in deck0
    assert " 5.000000E-04" in deck0
    # Insulated variant additionally carries the distributed-L' card.
    deck2 = export_nec(_builder("28-awg-pvc"), ground=None)
    assert "LD 5 0 0 0  5.800000E+07" in deck2
    assert "LD 2 0 0 0 0. " in deck2


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


# ----------------------------------------------------------------------
# The coated-wire oracles (momwire#874)
# ----------------------------------------------------------------------
#
# momwire models a jacketed wire as the Popovic-Nesic PAIR: the kernel takes
# an equivalent radius a' = a·(b/a)^((eps_r-1)/eps_r), and the series
# inductance L = (mu0/2pi)·ln(a'/a) puts back what enlarging the radius
# removed. NEC's LD 2 is the L half ALONE — same velocity to first order,
# but the wrong characteristic impedance (C unchanged, L raised, rather than
# C raised, L unchanged). The two are different models, so a same-model
# comparison needs NEC given the pair too.
#
# GIVING NEC THE PAIR TAKES THREE COUPLED DETAILS, and getting any one wrong
# reproduces a ~5 % gap that looks like a momwire defect:
#
#   1. GW radius = a'  (not the conductor's a)
#   2. LD 2 carries L PLUS the conductor's internal REACTANCE X_int/omega
#   3. LD 5 is dropped and the conductor's R folded into that same LD 2 card,
#      because LD 5 derives R from the GW radius, which is no longer the
#      conductor's
#
# Detail 2 is the one that bites: momwire's skin loading is the exact Bessel
# internal impedance, so it carries R + jX_int, and deep in the skin regime
# X_int ~= R (measured 1.4399 and 1.3830 ohm/m here, X/R = 0.961). Dropping
# it costs several ohms of reactance and reads as a model error.
#
# THAT IS WHY THE TIGHT ORACLE BELOW IS PEC: with no conductor loss there is
# nothing to fold, no LD 5 to drop, and detail 2 cannot be got wrong. Do not
# "improve" it back into the lossy form.


def _pec(wire_type):
    """The catalog wire with conductor loss switched off, both engines."""
    import dataclasses

    spec = dataclasses.replace(WIRES[wire_type], conductivity=None)
    WIRES.setdefault(f"_pec_{wire_type}", spec)
    return _builder(f"_pec_{wire_type}")


@needs_pynec
def test_cross_engine_coated_pair_oracle():
    """THE tight cross-engine pin for a jacketed wire: momwire (a'+L) against
    NEC given the SAME pair, PEC on both sides.

    PEC deliberately — see the module note above. With no conductor loss the
    comparison has one moving part (the jacket), and it lands at the engines'
    own noise floor: measured 0.61 % on the bare->PVC dX against a bare-deck
    baseline of 0.47 % (at a) and 0.56 % (at a'), and 0.80 % absolute.
    """
    dx_m = (
        _z(MomwireEngine(_pec("28-awg-pvc"), ground=None)).imag
        - _z(MomwireEngine(_pec("28-awg"), ground=None)).imag
    )
    dx_n = (
        _z(pair_pynec(_pec("28-awg-pvc"), lossy=False)).imag
        - _z(PyNECEngine(_pec("28-awg"), ground=None)).imag
    )
    assert dx_m == pytest.approx(dx_n, rel=0.015)


@needs_pynec
def test_the_pair_and_LD2_alone_differ_by_the_equivalent_radius():
    """The LOOSE assertion, and the sign of its failure matters more than
    its size.

    momwire's a'+L against NEC's LD-2-alone is a comparison of two DIFFERENT
    models, so a residual is expected and correct: the pair raises C and
    leaves L, LD 2 alone raises L and leaves C. Measured 7.5 % on the
    bare->PVC dX for 28 AWG under PVC (a'/a = 2.26), which is the a'
    end-effect.

    **A residual near ZERO would be the alarm**, not a success: it would mean
    momwire had silently lost the equivalent radius and gone back to being
    NEC's velocity-matching approximation. The lower bound below is the real
    content of this test; the upper bound only catches a wild divergence.
    """
    dx_m = (
        _z(MomwireEngine(_builder("28-awg-pvc"), ground=None)).imag
        - _z(MomwireEngine(_builder("28-awg"), ground=None)).imag
    )
    dx_n = (
        _z(PyNECEngine(_builder("28-awg-pvc"), ground=None)).imag
        - _z(PyNECEngine(_builder("28-awg"), ground=None)).imag
    )
    rel = abs(dx_m - dx_n) / abs(dx_n)
    assert rel < 0.10, f"the two models diverged further than the a' end-effect: {rel}"
    assert rel > 0.03, (
        f"momwire and NEC-LD2-only agree to {rel:.4f} — the equivalent radius "
        "looks LOST (momwire#874); these are different models and should differ"
    )


@needs_pynec
def test_matched_basis_lossy_oracle():
    """The strongest cross-engine pin (momwire#134): SAME basis family
    (sinusoidal = NEC's) and SAME wire physics on both engines — the
    absolute lossy-PVC impedance, not just deltas, must agree tightly.

    Now a same-model comparison (momwire#874): NEC is given the pair,
    lossily, which needs all three details in the module note — including
    X_int, without which this reads 5.6 % instead of 0.1 %. Kept LOSSY rather
    than made PEC like the tight oracle above, because conductor loss on the
    matched basis is exactly what momwire#134 put here, and it clears the
    1 % bar by a factor of ten.
    """
    from momwire import SinusoidalSolver

    z_m = _z(
        MomwireEngine(_builder("28-awg-pvc"), ground=None, solver=SinusoidalSolver)
    )
    z_n = _z(pair_pynec(_builder("28-awg-pvc"), lossy=True))
    assert abs(z_m - z_n) / abs(z_m) < 0.01

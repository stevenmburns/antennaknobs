"""Two-wire line parameters from physical geometry (issue #596).

`two_wire_params` turns "#14 wire, six inches apart" into the ``zdiff``/``vf``
a `BalancedLine` wants. The bare-conductor case has a closed form, so most of
these are exact-identity tests; the insulated cases are approximations, and the
tests say which claims are exact and which are engineering tolerances.
"""

import math

import numpy as np
import pytest

from antennaknobs.network import (
    ETA0,
    BalancedLine,
    WireSpec,
    balanced_line_from_geometry,
    two_wire_params,
)

# Handy conductors: bare #12, #14 and #18 copper (radii in metres).
AWG12, AWG14, AWG18 = 1.024e-3, 0.815e-3, 0.512e-3
INCH = 0.0254


# ---------------------------------------------------------------------------
# bare conductors — the exact part
# ---------------------------------------------------------------------------
def test_matches_the_textbook_acosh_form():
    d, a = 6 * INCH, AWG14
    z, vf = two_wire_params(d, a)
    assert z == pytest.approx((ETA0 / math.pi) * math.acosh(d / (2 * a)), rel=1e-15)
    assert vf == 1.0  # no dielectric, no slowing — exactly


def test_equal_radii_agree_with_the_general_unequal_form():
    """The two branches are the identity acosh(2x²−1) = 2·acosh(x).

    The equal-radius path exists for conditioning, not for a different answer.
    """
    d, a = 3 * INCH, AWG18
    general = (ETA0 / (2 * math.pi)) * math.acosh((d * d - 2 * a * a) / (2 * a * a))
    assert two_wire_params(d, a)[0] == pytest.approx(general, rel=1e-12)


def test_matches_the_handbook_log10_approximation_when_widely_spaced():
    """276·log₁₀(2D/d) is the same constant in base-10 clothing."""
    d, a = 12 * INCH, AWG14
    handbook = 276.0 * math.log10(d / a)  # = 276·log10(2D/diameter)
    assert two_wire_params(d, a)[0] == pytest.approx(handbook, rel=2e-3)


def test_unequal_conductors_sit_between_their_equal_pair_cases():
    z_thin = two_wire_params(6 * INCH, AWG18)[0]
    z_fat = two_wire_params(6 * INCH, AWG12)[0]
    z_mixed = two_wire_params(6 * INCH, AWG18, AWG12)[0]
    assert z_fat < z_mixed < z_thin


def test_wider_spacing_raises_impedance():
    zs = [two_wire_params(s * INCH, AWG14)[0] for s in (1, 3, 6, 12)]
    assert np.all(np.diff(zs) > 0)


# ---------------------------------------------------------------------------
# insulation — the approximate part
# ---------------------------------------------------------------------------
def test_shell_model_reduces_to_bare_at_unit_permittivity():
    bare = two_wire_params(INCH, AWG18)
    clad = two_wire_params(INCH, AWG18, insulation_radius=1.0e-3, eps_r=1.0)
    assert clad[0] == pytest.approx(bare[0], rel=1e-12)
    assert clad[1] == pytest.approx(1.0, rel=1e-12)


def test_insulation_slows_and_lowers_by_the_same_factor():
    """Z and vf both scale by 1/√ε_eff — the jacket adds C, not L."""
    bare_z = two_wire_params(INCH, AWG18)[0]
    z, vf = two_wire_params(INCH, AWG18, insulation_radius=1.0e-3, eps_r=2.3)
    assert vf < 1.0
    assert z == pytest.approx(bare_z * vf, rel=1e-12)


def test_a_thicker_jacket_slows_the_line_further():
    vfs = [
        two_wire_params(INCH, AWG18, insulation_radius=b, eps_r=2.3)[1]
        for b in (0.6e-3, 0.8e-3, 1.2e-3, 2.0e-3)
    ]
    assert np.all(np.diff(vfs) < 0)


def test_fill_rule_spans_air_to_solid():
    bare_z, _ = two_wire_params(INCH, AWG18)
    z0, vf0 = two_wire_params(INCH, AWG18, eps_r=2.25, fill=0.0)
    z1, vf1 = two_wire_params(INCH, AWG18, eps_r=2.25, fill=1.0)
    assert (z0, vf0) == pytest.approx((bare_z, 1.0), rel=1e-12)
    # Fully immersed: the classic vf = 1/√εᵣ.
    assert vf1 == pytest.approx(1.0 / math.sqrt(2.25), rel=1e-12)
    assert z1 == pytest.approx(bare_z / math.sqrt(2.25), rel=1e-12)


# ---------------------------------------------------------------------------
# real spools — engineering tolerances, stated as such
# ---------------------------------------------------------------------------
def test_600_ohm_open_wire_lands_on_its_nameplate():
    """#12 bare at 6 inches is the textbook 600 Ω line — and this one is exact
    physics, so it earns a tight tolerance."""
    z, vf = two_wire_params(6 * INCH, AWG12)
    assert z == pytest.approx(600.0, rel=0.01)
    assert vf == 1.0


def test_450_ohm_window_line_is_within_a_few_percent():
    """#18 jacketed at ~1 inch. The nameplate is a round number over a range of
    real constructions, so a few percent is the honest claim."""
    z, vf = two_wire_params(INCH, AWG18, insulation_radius=1.05e-3, eps_r=3.5)
    assert z == pytest.approx(450.0, rel=0.05)
    assert 0.88 < vf < 0.97


def test_300_ohm_twinlead_needs_the_fill_rule():
    """Solid-web twinlead has no air path, so the shell model refuses it and
    the mixing rule (fill ≈ 0.5 for a solid web) is the available estimator."""
    z, vf = two_wire_params(0.3 * INCH, 0.406e-3, eps_r=2.25, fill=0.5)
    assert z == pytest.approx(300.0, rel=0.10)
    assert 0.75 < vf < 0.85


# ---------------------------------------------------------------------------
# refusals — each one is a case the model genuinely cannot describe
# ---------------------------------------------------------------------------
def test_overlapping_conductors_are_refused():
    with pytest.raises(ValueError, match="overlap"):
        two_wire_params(1.0e-3, 0.6e-3)


def test_touching_jackets_are_refused_with_the_way_out():
    """The shell model's whole premise is air between the conductors."""
    with pytest.raises(ValueError, match="jackets touch") as exc:
        two_wire_params(2.0e-3, 0.4e-3, insulation_radius=1.05e-3, eps_r=2.25)
    assert "fill" in str(exc.value)  # names the estimator that does apply


def test_insulation_inside_the_conductor_is_refused():
    with pytest.raises(ValueError, match="must exceed the conductor radius"):
        two_wire_params(INCH, AWG18, insulation_radius=0.2e-3, eps_r=2.25)


def test_permittivity_is_required_with_either_estimator():
    with pytest.raises(ValueError, match="eps_r"):
        two_wire_params(INCH, AWG18, insulation_radius=1.0e-3)
    with pytest.raises(ValueError, match="eps_r"):
        two_wire_params(INCH, AWG18, fill=0.3)


def test_fill_must_be_a_fraction():
    with pytest.raises(ValueError, match="fraction"):
        two_wire_params(INCH, AWG18, eps_r=2.25, fill=1.4)


def test_nonpositive_radius_is_refused():
    with pytest.raises(ValueError, match="radii must be positive"):
        two_wire_params(INCH, 0.0)


# ---------------------------------------------------------------------------
# the BalancedLine constructor
# ---------------------------------------------------------------------------
def test_from_geometry_is_exactly_the_element_it_computes():
    """It's a constructor, not a new element: same fields, same stamp."""
    z, vf = two_wire_params(6 * INCH, AWG12)
    made = balanced_line_from_geometry(
        "t1", "t2", "a1", "a2", spacing=6 * INCH, length=20.0, conductor=AWG12
    )
    hand = BalancedLine("t1", "t2", "a1", "a2", zdiff=z, length=20.0, vf=vf)
    assert made == hand


def test_from_geometry_takes_a_catalog_wire_with_its_jacket():
    made = balanced_line_from_geometry(
        "t1", "t2", "a1", "a2", spacing=INCH, length=20.0, conductor="18-awg-pvc"
    )
    bare = balanced_line_from_geometry(
        "t1", "t2", "a1", "a2", spacing=INCH, length=20.0, conductor=0.512e-3
    )
    # The catalog entry carries insulation_radius + eps_r, so the constructed
    # line is slower and lower-Z than the same bare conductor.
    assert bare.vf == 1.0
    assert made.vf < 1.0
    assert made.zdiff < bare.zdiff


def test_from_geometry_takes_a_wire_spec():
    spec = WireSpec(radius=AWG14)
    made = balanced_line_from_geometry(
        "t1", "t2", "a1", "a2", spacing=6 * INCH, length=10.0, conductor=spec
    )
    assert made.zdiff == pytest.approx(two_wire_params(6 * INCH, AWG14)[0])


def test_from_geometry_supports_an_unequal_pair():
    made = balanced_line_from_geometry(
        "t1", "t2", "a1", "a2", spacing=6 * INCH, length=10.0,
        conductor=AWG18, conductor2=AWG12,
    )  # fmt: skip
    assert made.zdiff == pytest.approx(two_wire_params(6 * INCH, AWG18, AWG12)[0])


def test_from_geometry_refuses_two_different_jackets():
    with pytest.raises(ValueError, match="different insulation radii"):
        balanced_line_from_geometry(
            "t1", "t2", "a1", "a2", spacing=INCH, length=10.0,
            conductor="18-awg-pvc", conductor2="22-awg-pvc",
        )  # fmt: skip


def test_from_geometry_passes_loss_and_common_mode_through():
    """Geometry says nothing about matched loss or the CM path — those stay
    the caller's explicit choice."""
    made = balanced_line_from_geometry(
        "t1", "t2", "a1", "a2", spacing=6 * INCH, length=12.5,
        conductor=AWG12, k1=0.02, k2=0.0001, zcomm=300.0,
    )  # fmt: skip
    assert (made.k1, made.k2, made.zcomm, made.length) == (0.02, 0.0001, 300.0, 12.5)
    assert (made.a1, made.a2, made.b1, made.b2) == ("t1", "t2", "a1", "a2")


def test_from_geometry_line_stamps_like_any_other():
    """End to end: the constructed line reduces through the shared reducer."""
    from antennaknobs.network_reduce import balanced_admittance_4x4

    made = balanced_line_from_geometry(
        "t1", "t2", "a1", "a2", spacing=6 * INCH, length=5.0, conductor=AWG12
    )
    y = balanced_admittance_4x4(made.zdiff, made.length, 20.0, vf=made.vf)
    assert y.shape == (4, 4)
    # Differential stamp: rank 2, common mode structurally open.
    assert np.linalg.matrix_rank(y) == 2

"""verticals.collinear_stub: which stub substitutes co-phase a λ/4 + λ/2 collinear.

Small and synthetic, per the catalog policy: every variant builds, the two
`PortAtEnd` variants are refused by PyNEC at construction, and the one physics
claim the design exists for is held in free space on the default mesh — the
hairpin co-phases the sections, the differential-only BalancedLine does not,
and the differential-only line IS the open circuit. The docstring's full table
(ground, gains, lobe angles) is a study record, not a CI gate.
"""

import cmath
import math

import numpy as np
import pytest

from antennaknobs.builder import resolve_variant_params
from antennaknobs.designs.verticals.collinear_stub import Builder
from antennaknobs.engines import MomwireEngine
from antennaknobs.network import PortAtEnd
from antennaknobs.web import server  # noqa: F401 — loads the adapter in order
from antennaknobs.web.adapter import _discover_variants

from conftest import needs_pynec

VARIANTS = (
    "default",
    "bl_stub",
    "bl_stub_diffonly",
    "open_circuit",
    "lc_trap",
    "coax_sleeve",
)


def _builder(variant, **over):
    p = resolve_variant_params(Builder, variant)
    p.update(over)
    return Builder(p)


def _axis_current(dist, z):
    """The upward current on the vertical axis at height ``z``."""
    for wc in dist:
        p = np.asarray(wc.knot_positions)
        cur = np.asarray(wc.knot_currents)
        on = (np.abs(p[:, 0]) < 1e-9) & (np.abs(p[:, 1]) < 1e-9)
        for k in range(len(p) - 1):
            z0, z1 = p[k, 2], p[k + 1, 2]
            if on[k] and on[k + 1] and z0 != z1 and min(z0, z1) <= z <= max(z0, z1):
                t = (z - z0) / (z1 - z0)
                return math.copysign(1.0, z1 - z0) * ((1 - t) * cur[k] + t * cur[k + 1])
    raise AssertionError(f"no axis knot pair brackets z = {z}")


def _phase_difference(variant):
    """Δφ (degrees): λ/2-section centre current less λ/4-section centre current."""
    b = _builder(variant)
    dist = MomwireEngine(b, ground=None).current_distribution()
    z_low, z_up = b.section_centres()
    return math.degrees(
        cmath.phase(_axis_current(dist, z_up) / _axis_current(dist, z_low))
    )


def test_every_variant_is_listed_and_builds():
    assert set(_discover_variants(Builder)) == set(VARIANTS)
    for v in VARIANTS:
        b = _builder(v)
        assert b.build_wires()
        assert b.build_network().ports["feed"]


def test_the_vertical_geometry_is_the_same_in_every_variant():
    """Only what sits at A differs, so a pattern difference is the stub's."""

    def axis(v):
        # The vertical conductors, less the one-segment bridge the trap and
        # the sleeve hang their element on.
        return sorted(
            (w[0], w[1])
            for w in _builder(v).build_wires()
            if w[0][:2] == w[1][:2] == (0, 0) and w[4] != "gap"
        )

    ref = axis("default")
    assert all(axis(v) == ref for v in VARIANTS)


@pytest.mark.parametrize("n", (2, 3, 4))
def test_radials_are_quarter_waves_evenly_spread(n):
    b = _builder("default", n_radials=n)
    base = b.base
    radials = [w for w in b.build_wires() if w[0] == (0, 0, base) and w[1][2] == base]
    assert len(radials) == n
    q = 0.25 * b.design_wavelength
    angles = sorted(math.atan2(w[1][1], w[1][0]) % (2 * math.pi) for w in radials)
    assert angles[0] == pytest.approx(0.0, abs=1e-12)  # the first along +x
    assert np.allclose(np.diff(angles), 2 * math.pi / n)
    assert all(math.hypot(w[1][0], w[1][1]) == pytest.approx(q) for w in radials)


def test_the_bl_variants_are_junction_ported():
    for v in ("bl_stub", "bl_stub_diffonly"):
        ports = _builder(v).build_network().ports
        assert isinstance(ports["a1"], PortAtEnd)
        assert isinstance(ports["a2"], PortAtEnd)


@needs_pynec
@pytest.mark.parametrize("variant", ("bl_stub", "bl_stub_diffonly"))
def test_pynec_refuses_the_junction_port_variants_at_construction(variant):
    from antennaknobs.engines import PyNECEngine

    with pytest.raises(ValueError, match="PortAtEnd"):
        PyNECEngine(_builder(variant), ground=None)


def test_the_hairpin_co_phases_and_the_differential_only_line_does_not():
    """The design's claim, measured in free space on the default mesh
    (docstring: +10° and −162°)."""
    hairpin = _phase_difference("default")
    diff_only = _phase_difference("bl_stub_diffonly")
    assert abs(hairpin) < 30.0
    assert abs(diff_only) > 150.0


def test_the_common_mode_path_restores_co_phasing():
    """bl_stub (zcomm on) tracks the hairpin (docstring: +14° vs +10°)."""
    assert abs(_phase_difference("bl_stub")) < 30.0


def test_differential_only_is_the_open_circuit():
    """A shorted λ/4 differential line is an open at resonance: the
    differential-only stub adds nothing an open circuit does not."""
    z_open = MomwireEngine(_builder("open_circuit"), ground=None).impedance()[0]
    z_dm = MomwireEngine(_builder("bl_stub_diffonly"), ground=None).impedance()[0]
    assert abs(z_dm - z_open) < 1e-3 * abs(z_open)

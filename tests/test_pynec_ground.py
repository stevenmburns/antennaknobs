"""PyNEC finite-ground handling.

("finite", eps_r, sigma) must select NEC's Sommerfeld-Norton ground (IPERF 2)
and ("finite-fast", eps_r, sigma) the reflection-coefficient approximation
(IPERF 0). The numerical test pins the two apart at a height where they
genuinely diverge, guarding against both specs silently mapping to the same
gn_card again (the pre-fix behaviour: "finite" emitted IPERF 0).
"""

import argparse

import pytest

pytest.importorskip("PyNEC")

from antennaknobs import resolve_variant_params  # noqa: E402
from antennaknobs.cli import parse_ground  # noqa: E402
from antennaknobs.designs.dipoles.invvee import Builder as InvVee  # noqa: E402
from antennaknobs.engines import PyNECEngine  # noqa: E402
from antennaknobs.engines.momwire import _normalise_ground  # noqa: E402


def _flat_dipole(height_m):
    params = dict(resolve_variant_params(InvVee, "dipole"))
    params["base"] = height_m
    return InvVee(params)


def test_parse_ground_finite_variants():
    assert parse_ground("finite") == ("finite", 10.0, 0.002)
    assert parse_ground("finite:13,0.005") == ("finite", 13.0, 0.005)
    assert parse_ground("finite-fast") == ("finite-fast", 10.0, 0.002)
    assert parse_ground("finite-fast:13,0.005") == ("finite-fast", 13.0, 0.005)
    with pytest.raises(argparse.ArgumentTypeError):
        parse_ground("finite-slow")


def test_momwire_preserves_the_finite_variant():
    """Since momwire 0.6.0 the two finite specs mean different physics
    (true Sommerfeld vs reflection-coefficient), so normalisation must
    keep the variant instead of folding to a single model."""
    assert _normalise_ground(("finite-fast", 10.0, 0.002)) == (
        "finite-fast",
        10.0,
        0.002,
    )
    assert _normalise_ground(("finite", 10.0, 0.002)) == ("finite", 10.0, 0.002)


def test_sommerfeld_and_reflection_coefficient_diverge_when_low():
    # At 0.05λ height the Sommerfeld and reflection-coefficient grounds
    # disagree on R by ~15 Ω (they agree within ~1 Ω above ~0.2λ, so a low
    # antenna is what tells them apart).
    lam = 299.792458 / 28.47
    height = 0.05 * lam
    z_somm = PyNECEngine(
        _flat_dipole(height), ground=("finite", 10.0, 0.002)
    ).impedance()[0]
    z_fast = PyNECEngine(
        _flat_dipole(height), ground=("finite-fast", 10.0, 0.002)
    ).impedance()[0]
    z_pec = PyNECEngine(_flat_dipole(height), ground="pec").impedance()[0]
    assert abs(z_somm - z_fast) > 5.0
    # and neither finite model is the PEC image in disguise
    assert abs(z_somm - z_pec) > 5.0
    assert abs(z_fast - z_pec) > 5.0


class _GroundedMonopole:
    """Minimal grounded quarter-wave monopole: bottom end at exactly z=0."""

    def __new__(cls):
        from types import MappingProxyType

        from antennaknobs import AntennaBuilder

        class Mono(AntennaBuilder):
            default_params = MappingProxyType({"freq": 28.57, "design_freq": 28.57})

            def build_wires(self):
                h = 0.25 * 299.792458 / 28.57
                return [
                    ((0.0, 0.0, 0.0), (0.0, 0.0, 0.3), 1, 1 + 0j),
                    ((0.0, 0.0, 0.3), (0.0, 0.0, h), 15, None),
                ]

        return Mono()


def test_ge_flag_connects_z0_wire_ends_to_pec_ground():
    """A wire ending at exactly z=0 over a ground plane must be CONNECTED to
    it (NEC GE flag 1: touching segments' currents interpolate onto their
    images). A bottom-fed grounded quarter-wave then reads the textbook
    monopole ~36 +j21; with the old unconditional GE flag 0 the same feed
    saw an insulated free end and thousands of ohms capacitive."""
    z = PyNECEngine(_GroundedMonopole(), ground="pec").impedance()[0]
    assert 25.0 < z.real < 55.0
    assert -20.0 < z.imag < 60.0


def test_ge_flag_stays_zero_when_nothing_touches_ground():
    """Elevated geometry keeps GE flag 0 (no behaviour change for the whole
    existing catalog), and free space never sets it even with a z=0 end."""
    eng = PyNECEngine(_flat_dipole(10.0), ground="pec")
    assert eng._ge_flag() == 0
    eng_free = PyNECEngine(_GroundedMonopole(), ground=None)
    assert eng_free._ge_flag() == 0
    eng_gnd = PyNECEngine(_GroundedMonopole(), ground="pec")
    assert eng_gnd._ge_flag() == 1


# ---------------------------------------------------------------------------
# gn 2 near-ground defect warning (issue #448)
# ---------------------------------------------------------------------------
#
# Before pynec-accel 1.7.6, nec2++'s Sommerfeld solve was unreliable for
# near-ground conductors that aren't plain grounded verticals (measured
# against nec2c/nec2dxs/momwire agreement on the wild corpus; root cause
# was the INTRP cell-cache inversion fixed by stevenmburns/necpp#5). The
# engine warns on the calibrated risk predicate only when the installed
# pynec-accel predates the fix. The legacy-warn tests below force the
# old-version path so the predicate stays pinned for users on <1.7.6;
# separate tests cover the fixed-install behaviour (no warning, and the
# solve itself lands on the three-way-agreed value).

_GN2 = ("finite", 10.0, 0.002)


def _force_legacy(monkeypatch):
    """Pretend the installed pynec-accel predates the 1.7.6 fix."""
    from antennaknobs.engines import pynec as _p

    monkeypatch.setattr(_p, "_pynec_somm_fixed", lambda: False)


def _warns_gn2(builder, ground):
    import warnings as _w

    with _w.catch_warnings(record=True) as rec:
        _w.simplefilter("always")
        PyNECEngine(builder, ground=ground).impedance()
    return sum(
        1
        for x in rec
        if issubclass(x.category, RuntimeWarning) and "gn 2" in str(x.message)
    )


def test_somm_low_horizontal_wire_warns_once(monkeypatch):
    """A flat dipole at 0.03 wavelength over gn 2 is squarely in the broken
    class (the golden capture's own minimal repro); one warning per engine
    instance even across repeated solves."""
    import warnings as _w

    _force_legacy(monkeypatch)
    eng = PyNECEngine(_flat_dipole(0.3), ground=_GN2)
    with _w.catch_warnings(record=True) as rec:
        _w.simplefilter("always")
        eng.impedance()
        eng.impedance()
    hits = [x for x in rec if "gn 2" in str(x.message)]
    assert len(hits) == 1
    assert "#448" in str(hits[0].message)


def test_somm_low_hanging_open_end_warns(monkeypatch):
    """Half-square/bobtail/sloper class: a vertical whose open end hangs
    near the plane without touching it (connectivity path of the risk
    predicate — no horizontal wire anywhere near the ground)."""
    from types import MappingProxyType

    from antennaknobs import AntennaBuilder

    _force_legacy(monkeypatch)

    class HalfSquareish(AntennaBuilder):
        default_params = MappingProxyType({"freq": 28.57})

        def build_wires(self):
            lam = 299.792458 / 28.57
            top = 0.3 * lam
            return [
                ((0.0, 0.0, 0.3), (0.0, 0.0, top), 15, 1 + 0j),  # hangs at 0.3 m
                ((0.0, 0.0, top), (0.0, 0.5 * lam, top), 21, None),
                ((0.0, 0.5 * lam, top), (0.0, 0.5 * lam, 0.3), 15, None),
            ]

    assert _warns_gn2(HalfSquareish(), _GN2) == 1


def test_somm_warning_exemptions(monkeypatch):
    """No warning for: elevated structure on gn 2; the same low structure on
    the reflection-coefficient ground (gn 0 stays faithful); and a plain
    ground-connected vertical — even split into wires with an interior
    joint below 0.1 wavelength (the connectivity analysis, not a naive
    endpoint-height test, is what exempts it)."""
    _force_legacy(monkeypatch)
    assert _warns_gn2(_flat_dipole(4.0), _GN2) == 0
    assert _warns_gn2(_flat_dipole(0.3), ("finite-fast", 10.0, 0.002)) == 0
    assert _warns_gn2(_GroundedMonopole(), _GN2) == 0


def _pynec_fixed_installed():
    from antennaknobs.engines.pynec import _pynec_somm_fixed

    return _pynec_somm_fixed()


@pytest.mark.skipif(
    not _pynec_fixed_installed(), reason="installed pynec-accel predates 1.7.6"
)
def test_somm_fixed_install_no_warning_and_accurate():
    """With pynec-accel >= 1.7.6 (the necpp#5 INTRP fix), the risk class is
    solved correctly and the #448 warning stays silent. Oracle: the low flat
    dipole (~0.03λ, squarely the geometry class that used to land ~7×
    off) must agree with momwire's sinusoidal basis — the same NEC-2 basis
    family, so this is the matched-basis cross-engine check — on the
    reflection coefficient to within 2%. The unfixed engine failed this by
    an order of magnitude."""
    from antennaknobs.engines import MomwireEngine
    from momwire import SinusoidalSolver

    assert _warns_gn2(_flat_dipole(0.3), _GN2) == 0

    z_pynec = PyNECEngine(_flat_dipole(0.3), ground=_GN2).impedance()[0]
    z_sin = MomwireEngine(
        _flat_dipole(0.3), ground=_GN2, solver=SinusoidalSolver
    ).impedance()[0]

    def gamma(z):
        return (z - 50.0) / (z + 50.0)

    assert abs(gamma(z_pynec) - gamma(z_sin)) < 0.02

"""Phase-2 tests for issue #388: engines consuming per-wire WireSpecs.

PyNEC honors per-wire radius natively (one radius per GW card) and emits
per-tag LD cards for per-wire conductivity/insulation. momwire honors
per-wire conductivity/insulation through its per-wire loading arrays, and
— since momwire#147 — per-wire radius arrays on BSplineSolver and
SinusoidalSolver (the H-matrix family still collapses mixed radii to the
length-dominant one with a warning until its block fills are ported).

The bit-identical guard: a design whose per-wire specs all equal the old
whole-antenna spec must produce identical results to the global-spec path.
"""

import logging
from types import MappingProxyType

import pytest

from antennaknobs import AntennaBuilder, Wire, WireSpec
from antennaknobs.engines import MomwireEngine, PyNECEngine

COPPER = 5.8e7
FREQ = 14.1
ARM = 5.0
EPS = 0.05
Z0 = 10.0


def _dipole_builder(spec_left=None, spec_feed=None, spec_right=None, default=None):
    """A horizontal dipole at z=10 m: left arm, 1-seg feed edge, right arm,
    each optionally carrying its own WireSpec; `default` becomes the
    design's build_wire_material()."""

    class _Dip(AntennaBuilder):
        default_params = MappingProxyType({"freq": FREQ})

        def build_wires(self):
            def entry(p0, p1, n, ex, spec):
                if spec is None:
                    return (p0, p1, n, ex)
                return Wire(p0, p1, n, ex, None, spec)

            return [
                entry((0, -ARM, Z0), (0, -EPS, Z0), 21, None, spec_left),
                entry((0, -EPS, Z0), (0, EPS, Z0), 1, 1 + 0j, spec_feed),
                entry((0, EPS, Z0), (0, ARM, Z0), 21, None, spec_right),
            ]

        def build_wire_material(self):
            return default

    return _Dip()


def _z(engine_cls, builder, **kw):
    return engine_cls(builder, **kw).impedance()[0]


# ------------------------------------------------------------- radius


@pytest.mark.parametrize("engine_cls", [PyNECEngine, MomwireEngine])
def test_uniform_per_wire_radius_equals_global_spec(engine_cls):
    """Per-wire specs that all equal the whole-antenna spec: identical Z."""
    s = WireSpec(radius=2e-3)
    z_global = _z(engine_cls, _dipole_builder(default=s))
    z_perwire = _z(engine_cls, _dipole_builder(s, s, s))
    assert z_perwire == z_global


def test_pynec_honors_mixed_per_wire_radius():
    """NEC takes a radius per GW card: fat left arm + thin right arm must
    move Z off both uniform answers (and stay finite/sane)."""
    thin, fat = WireSpec(radius=0.5e-3), WireSpec(radius=8e-3)
    z_thin = _z(PyNECEngine, _dipole_builder(default=thin))
    z_fat = _z(PyNECEngine, _dipole_builder(default=fat))
    z_mixed = _z(PyNECEngine, _dipole_builder(fat, thin, thin))
    assert z_mixed != z_thin and z_mixed != z_fat
    # The mixed reactance lands between the two uniform extremes.
    lo, hi = sorted((z_thin.imag, z_fat.imag))
    assert lo < z_mixed.imag < hi


def test_momwire_mixed_radius_passes_per_wire_array(caplog):
    """With the momwire#147 kernels landed, mixed radii reach the solver as
    a per-wire list — no dominant-collapse, no warning."""
    thin, fat = WireSpec(radius=0.5e-3), WireSpec(radius=8e-3)
    with caplog.at_level(logging.WARNING):
        eng = MomwireEngine(_dipole_builder(fat, thin, thin))
    assert not any("length-dominant" in r.message for r in caplog.records)
    # flat_wires_to_polylines merges the spec-uniform thin feed edge with
    # the thin right arm: two polylines, one radius each.
    assert sorted(eng._wire_radius) == pytest.approx([0.5e-3, 8e-3])


def test_momwire_sinusoidal_mixed_radius_shift_matches_pynec():
    """Cross-engine agreement on the mixed-radius EFFECT: the shift
    z_mixed − z_uniform_thin agrees with PyNEC to ~2 Ω (measured 1.7 Ω;
    fattening one arm moves Z by ~18 Ω here, so the shift is well
    resolved). The shift — not absolute Z — is compared because this
    tiny-feed-edge geometry carries a pre-existing ~8 Ω cross-engine
    reactance offset from the differing feed models, present for uniform
    radii too. SinusoidalSolver is the parity solver: it implements NEC's
    basis and tracks PyNEC through mixed-radius solves (momwire's
    test_per_wire_radius.py pins the direct absolute parity on clean
    geometries); the resistance, which the feed-model offset barely
    touches, is also asserted absolutely."""
    from momwire.sinusoidal import SinusoidalSolver

    thin, fat = WireSpec(radius=0.5e-3), WireSpec(radius=8e-3)
    kw = {"solver": SinusoidalSolver}
    z_thin_nec = _z(PyNECEngine, _dipole_builder(default=thin))
    z_mix_nec = _z(PyNECEngine, _dipole_builder(fat, thin, thin))
    z_thin_mw = _z(MomwireEngine, _dipole_builder(default=thin), **kw)
    z_mix_mw = _z(MomwireEngine, _dipole_builder(fat, thin, thin), **kw)
    shift_nec = z_mix_nec - z_thin_nec
    shift_mw = z_mix_mw - z_thin_mw
    assert abs(shift_nec) > 10.0  # the effect being tracked is large...
    assert abs(shift_mw - shift_nec) < 3.0  # ...and matched
    assert z_mix_mw.real == pytest.approx(z_mix_nec.real, abs=1.5)


def test_momwire_bspline_mixed_radius_honored():
    """The default (BSpline) engine feeds mixed radii to its kernels: Z
    moves well off both uniform-radius answers instead of silently equaling
    the dominant-radius solve. (Cross-engine absolute parity at an IN-LINE
    radius step is deliberately not asserted for the Galerkin basis: NEC-2
    itself is non-convergent at radius steps and the two formulations
    disagree there — see momwire docs/sinusoidal_basis_design.md
    "Per-wire radius". Junction-type mixed-radius geometries, e.g. fat
    vertical + thin radials, are pinned against PyNEC in momwire's own
    suite.)"""
    thin, fat = WireSpec(radius=0.5e-3), WireSpec(radius=8e-3)
    z_thin = _z(MomwireEngine, _dipole_builder(default=thin))
    z_fat = _z(MomwireEngine, _dipole_builder(default=fat))
    z_mixed = _z(MomwireEngine, _dipole_builder(fat, thin, thin))
    assert abs(z_mixed - z_thin) > 5.0
    assert abs(z_mixed - z_fat) > 5.0


def test_momwire_hmatrix_mixed_radius_still_warns_and_collapses(caplog):
    """The H-matrix family's block fills still take one radius: mixed radii
    keep the loud length-dominant collapse until momwire#147's remaining
    increment lands."""
    from momwire.hmatrix import HMatrixSolver

    thin, fat = WireSpec(radius=0.5e-3), WireSpec(radius=8e-3)
    with caplog.at_level(logging.WARNING):
        eng = MomwireEngine(_dipole_builder(fat, thin, thin), solver=HMatrixSolver)
    assert any("length-dominant" in r.message for r in caplog.records)
    # Arms have equal length; the feed edge tips the thin total over.
    assert eng._wire_radius == pytest.approx(0.5e-3)


def test_per_wire_spec_beats_web_radius_override():
    """Issue #388 precedence: the web wire_radius override moves the
    DEFAULT only; an explicit per-wire spec wins."""
    s = WireSpec(radius=2e-3)
    eng = MomwireEngine(_dipole_builder(s, s, s), wire_radius=1e-3)
    assert eng._wire_radius == pytest.approx(2e-3)
    # ...while a design with only a global spec still yields to the override
    eng2 = MomwireEngine(_dipole_builder(default=s), wire_radius=1e-3)
    assert eng2._wire_radius == pytest.approx(1e-3)


# -------------------------------------------------------- conductivity


@pytest.mark.parametrize("engine_cls", [PyNECEngine, MomwireEngine])
def test_uniform_per_wire_conductivity_equals_global_spec(engine_cls):
    s = WireSpec(radius=1e-3, conductivity=COPPER)
    z_global = _z(engine_cls, _dipole_builder(default=s))
    z_perwire = _z(engine_cls, _dipole_builder(s, s, s))
    assert z_perwire == pytest.approx(z_global, rel=1e-9)


@pytest.mark.parametrize("engine_cls", [PyNECEngine, MomwireEngine])
def test_one_lossy_arm_sits_between_pec_and_all_lossy(engine_cls):
    """Per-wire conductivity really is per wire: one copper arm adds about
    half the loss resistance of two copper arms."""
    pec = WireSpec(radius=1e-3)
    lossy = WireSpec(radius=1e-3, conductivity=1e5)  # poor conductor: visible R
    r_pec = _z(engine_cls, _dipole_builder(pec, pec, pec)).real
    r_all = _z(engine_cls, _dipole_builder(lossy, pec, lossy)).real
    r_one = _z(engine_cls, _dipole_builder(lossy, pec, pec)).real
    assert r_pec < r_one < r_all
    added_one, added_all = r_one - r_pec, r_all - r_pec
    assert added_one == pytest.approx(added_all / 2, rel=0.15)


# ------------------------------------------------------------- insulation


def test_momwire_per_wire_insulation_tunes_long():
    """A jacket adds distributed series L, so at fixed frequency X RISES
    (the antenna behaves electrically longer; resonance moves down).
    Insulating one arm adds half the reactance shift of insulating both,
    and uniform per-wire insulation matches the global-spec path exactly."""
    bare = WireSpec(radius=1e-3)
    ins = WireSpec(radius=1e-3, insulation_radius=3e-3, insulation_eps_r=3.5)
    assert _z(MomwireEngine, _dipole_builder(ins, ins, ins)) == _z(
        MomwireEngine, _dipole_builder(default=ins)
    )
    x_bare = _z(MomwireEngine, _dipole_builder(bare, bare, bare)).imag
    x_all = _z(MomwireEngine, _dipole_builder(ins, bare, ins)).imag
    x_one = _z(MomwireEngine, _dipole_builder(ins, bare, bare)).imag
    assert x_bare < x_one < x_all
    assert x_one - x_bare == pytest.approx((x_all - x_bare) / 2, rel=0.05)

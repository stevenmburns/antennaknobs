"""AntennaBuilder.auto_mesh — the design-density meshing contract.

The rulebook (issues #521/#522, deliberately per-wire with no
interactions): a ``None`` count means "mesh me at the design density"
— ``nominal_nsegs`` segments per quarter-wavelength at ``design_freq``
— and an integer count is taken verbatim (the legacy path; allowed,
not recommended). ``design_freq`` anchors the scale, never the
measurement ``freq``, so sweeping frequency can never remesh geometry.
"""

from types import MappingProxyType

import pytest

from antennaknobs import AntennaBuilder

C = 299.792458


class _Design(AntennaBuilder):
    default_params = MappingProxyType({"freq": 21.0, "design_freq": 29.9792458})


class _NoDesignFreq(AntennaBuilder):
    default_params = MappingProxyType({"freq": 21.0})


def _wire(length, ns, ex=None):
    return ((0.0, 0.0, 0.0), (length, 0.0, 0.0), ns, ex)


def test_none_counts_mesh_at_quarter_wave_density():
    # design_freq chosen so lambda/4 = 2.5 m exactly.
    b = _Design()
    b.nominal_nsegs = 20  # -> segment length 0.125 m
    out = b.auto_mesh([_wire(2.5, None), _wire(1.25, None), _wire(0.05, None)])
    assert [t[2] for t in out] == [20, 10, 1]  # 0.05 m floors at 1


def test_integer_counts_taken_verbatim_and_extras_preserved():
    b = _Design()
    b.nominal_nsegs = 20
    tagged = ((0.0, 0.0, 0.0), (1.25, 0.0, 0.0), None, 1 + 0j, "feed")
    out = b.auto_mesh([_wire(2.5, 7), tagged])
    assert out[0][2] == 7  # legacy explicit count untouched
    assert out[1][2] == 10  # None resolved at the same density
    assert out[1][3] == 1 + 0j and out[1][4] == "feed"  # payload intact


def test_all_explicit_is_a_pure_passthrough_without_design_freq():
    b = _NoDesignFreq()
    b.nominal_nsegs = 20
    tups = [_wire(2.5, 7), _wire(1.0, 3)]
    assert b.auto_mesh(tups) == tups  # no design_freq needed, no change


def test_none_count_without_design_freq_raises():
    b = _NoDesignFreq()
    b.nominal_nsegs = 20
    with pytest.raises(ValueError, match="design_freq"):
        b.auto_mesh([_wire(2.5, None)])


def test_measurement_freq_does_not_affect_the_mesh():
    """Sweeping freq must never remesh the antenna — density is anchored
    to design_freq only."""
    b = _Design()
    b.nominal_nsegs = 20
    ref = [t[2] for t in b.auto_mesh([_wire(2.5, None), _wire(0.7, None)])]
    b.freq = 3.5
    assert [t[2] for t in b.auto_mesh([_wire(2.5, None), _wire(0.7, None)])] == ref


def test_density_is_the_same_across_designs():
    """N means one physical density everywhere: two designs at the same
    design_freq give the same segment length to same-length wires."""

    class Other(AntennaBuilder):
        default_params = MappingProxyType({"freq": 7.0, "design_freq": 29.9792458})

    a, o = _Design(), Other()
    a.nominal_nsegs = o.nominal_nsegs = 15
    wa = a.auto_mesh([_wire(1.9, None)])
    wo = o.auto_mesh([_wire(1.9, None)])
    assert wa[0][2] == wo[0][2]


def test_auto_mesh_is_part_of_the_stack():
    """Builders never call auto_mesh: build_wires results resolve
    automatically, so every consumer sees integer counts."""

    class Dipole(_Design):
        def build_wires(self):
            return [_wire(2.5, None), _wire(1.25, None, 1 + 0j)]

    b = Dipole()
    b.nominal_nsegs = 20
    assert [t[2] for t in b.build_wires()] == [20, 10]


def test_explicit_auto_mesh_call_is_idempotent():
    """Legacy builders that still call auto_mesh themselves get the
    identical mesh — the wrap resolves an already-resolved list to
    itself."""

    class Dipole(_Design):
        def build_wires(self):
            return self.auto_mesh([_wire(2.5, None), _wire(1.25, 3)])

    b = Dipole()
    b.nominal_nsegs = 20
    assert [t[2] for t in b.build_wires()] == [20, 3]


def test_missing_design_freq_raises_at_build_wires():
    class Bad(_NoDesignFreq):
        def build_wires(self):
            return [_wire(2.5, None)]

    b = Bad()
    b.nominal_nsegs = 20
    with pytest.raises(ValueError, match="design_freq"):
        b.build_wires()


def test_drone_edges_resolve_through_the_stack():
    """A Drone with no meshing args emits None counts; inside a builder
    they resolve at the design density like any other wire."""
    from antennaknobs.drone import Drone

    class Loop(_Design):
        def build_wires(self):
            d = Drone(position=(0.0, 0.0, 0.0))
            d.pay_out().forward(2.5).yaw(90).forward(1.25, nsegs=3)
            return d.edges

    b = Loop()
    b.nominal_nsegs = 20  # lambda/4 = 2.5 m for _Design's design_freq
    assert [t[2] for t in b.build_wires()] == [20, 3]


def test_drone_legacy_meshing_args_unchanged():
    from antennaknobs.drone import Drone

    d = Drone(nominal_nsegs=21, ref=1.0)
    d.pay_out().forward(2.0)
    assert d.edges[0][2] == 42  # resolved in-drone, exactly as before


def test_wire_keyword_construction_is_the_brief_spelling():
    """Wire(a, b) / Wire(t, s, ex=...) / Wire(ti, to, name=...) — every
    field after the endpoints defaults, n_seg to None (design density),
    and resolution preserves the Wire type (names/specs stay named)."""
    from antennaknobs.network import Wire

    class Dipole(_Design):
        def build_wires(self):
            return [
                Wire((0.0, -2.5, 0.0), (0.0, -0.05, 0.0)),
                Wire((0.0, 0.05, 0.0), (0.0, 2.5, 0.0)),
                Wire((0.0, -0.05, 0.0), (0.0, 0.05, 0.0), ex=1 + 0j, name="feed"),
            ]

    b = Dipole()
    b.nominal_nsegs = 20  # lambda/4 = 2.5 m
    out = b.build_wires()
    assert [w.n_seg for w in out] == [20, 20, 1]
    assert all(isinstance(w, Wire) for w in out)
    assert out[2].ex == 1 + 0j and out[2].name == "feed"


def test_short_plain_tuples_stay_rejected():
    """The brevity lives in Wire keywords, not in 2/3-tuples — a bare
    third element would be ambiguous between a count and an excitation."""
    from antennaknobs.network import as_wire

    with pytest.raises(ValueError, match="4-6"):
        as_wire(((0.0, 0.0, 0.0), (1.0, 0.0, 0.0)))


# ======================================================================
# The lower medium (issue #983): below the z = 0 interface the wave is
# shorter by |n|, so the design density has to be read against lambda_m.
# ======================================================================
#
# The refractive index is momwire's to own (momwire#553 U4 shipped
# `_sommerfeld_below.lambda_medium` as its ONE spelling), so nothing here
# re-derives it — these gates pin that antennaknobs ASKS, that it asks only
# for wires that are actually buried, and that the answer never silently
# degrades into the lossless shortcut.


class _Buried(AntennaBuilder):
    """Soil A at 7 MHz — the cell momwire pins |n| = 4.27452 for."""

    default_params = MappingProxyType(
        {
            "freq": 7.0,
            "design_freq": 7.0,
            "design_eps_r": 13.0,
            "design_sigma": 0.005,
        }
    )


def _at(z, length, ns=None):
    return ((0.0, 0.0, z), (length, 0.0, z), ns, None)


def test_medium_wavelength_matches_momwires_pinned_refractive_index():
    """The cross-link, not a re-derivation: |n| read back off the builder
    must equal the value momwire's own G-U4-1 table pins for soil A at
    7 MHz. If momwire's spelling ever moves, this fails here rather than
    quietly meshing to a different density."""
    b = _Buried()
    n_index = b.design_wavelength / b.design_medium_wavelength
    assert n_index == pytest.approx(4.27452, rel=1e-4)


def test_the_lossless_shortcut_is_not_what_we_mesh_against():
    """1/sqrt(eps_r) drops the conduction term and under-meshes in the
    direction that looks fine — 3.606 against a true 4.275 at soil A.
    This gate exists so nobody 'simplifies' the property into it."""
    b = _Buried()
    n_index = b.design_wavelength / b.design_medium_wavelength
    lossless = 13.0**0.5
    assert lossless == pytest.approx(3.6056, rel=1e-4)
    assert n_index > lossless * 1.15


def test_buried_wires_mesh_denser_by_exactly_the_refractive_index():
    """Same wire, same length, one above the interface and one below: the
    segment counts differ by |n| and nothing else."""
    b = _Buried()
    b.nominal_nsegs = 20
    above, below = b.auto_mesh([_at(+1.0, 5.0), _at(-1.0, 5.0)])
    n_index = b.design_wavelength / b.design_medium_wavelength
    # The ratio is exact on the DENSITIES; the counts themselves are each
    # independently rounded, so compare before the rounding rather than
    # composing round(round(x) * n).
    dens_above = 20 * 5.0 / (0.25 * b.design_wavelength)
    dens_below = 20 * 5.0 / (0.25 * b.design_medium_wavelength)
    assert dens_below == pytest.approx(dens_above * n_index, rel=1e-12)
    assert (above[2], below[2]) == (round(dens_above), round(dens_below))
    assert (above[2], below[2]) == (9, 40)


def test_a_wire_that_straddles_the_interface_counts_as_below():
    """One n_seg cannot express two densities, so a straddling wire takes
    the denser in-medium one over its whole length."""
    b = _Buried()
    b.nominal_nsegs = 20
    (straddle,) = b.auto_mesh([((0.0, 0.0, -1.0), (0.0, 0.0, 2.0), None, None)])
    (fully_below,) = b.auto_mesh([_at(-1.0, 3.0)])
    assert straddle[2] == fully_below[2]


def test_a_wire_resting_on_the_interface_is_not_below():
    """z = 0 is a ground CONTACT, not a burial: it meshes against
    free space, which is what every existing catalog design does."""
    b = _Buried()
    b.nominal_nsegs = 20
    (contact,) = b.auto_mesh([_at(0.0, 5.0)])
    b2 = _Design()
    b2.nominal_nsegs = 20
    assert contact[2] == b.segs_for(5.0, 0.25 * b.design_wavelength)


def test_without_a_soil_declaration_nothing_changes():
    """The regression gate for every non-buried design in the catalog: no
    declaration, no medium, buried-looking wires included."""
    b = _Design()
    b.nominal_nsegs = 20
    assert b.design_medium_wavelength is None
    above, below = b.auto_mesh([_at(+1.0, 2.5), _at(-1.0, 2.5)])
    assert above[2] == below[2] == 20


@pytest.mark.parametrize("missing", ["design_eps_r", "design_sigma"])
def test_half_a_soil_declaration_is_no_declaration(missing):
    """Both constants or neither — |n| needs the conduction term, so a
    lone eps_r must NOT quietly mesh against the lossless shortcut."""
    b = _Buried()
    setattr(b, missing, None)
    assert b.design_medium_wavelength is None


def test_soil_is_declared_not_swept():
    """The mesh is a property of the geometry: it is read off the design's
    stated soil, so it cannot move when the solve-time ground moves. The
    builder never sees `--ground` at all, and this pins that it stays that
    way — a future `terrain`/ground attribute must not reach auto_mesh."""
    b = _Buried()
    b.nominal_nsegs = 20
    before = b.auto_mesh([_at(-1.0, 5.0)])[0][2]
    b.terrain = ("finite", 5.0, 0.001)  # a different half-space, solve-side
    b.ground = ("finite", 5.0, 0.001)
    assert b.auto_mesh([_at(-1.0, 5.0)])[0][2] == before

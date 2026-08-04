"""dipoles.invvee_catenary (issue #698, unit 2): the sagging inv-vee arm.

Engine-agnostic impedance checks follow the `tests/test_pota_invvee.py`
precedent — build a `MomwireEngine` directly over the default (finite)
ground and read `.impedance()`.
"""

import math

import pytest

from antennaknobs.designs.dipoles.invvee_catenary import Builder
from antennaknobs.engines.momwire import MomwireEngine
from antennaknobs.engines.pynec import DEFAULT_GROUND
from antennaknobs.network import Wire

_EPS = 0.05


def _builder(**params):
    b = Builder()
    for k, v in params.items():
        setattr(b, k, v)
    return b


def _z(builder):
    return MomwireEngine(builder, ground=DEFAULT_GROUND).impedance()[0]


# ---------------------------------------------------------------------------
# 1. Taut-limit regression vs a hand-built straight-arm oracle
# ---------------------------------------------------------------------------


def test_taut_limit_matches_straight_arm_oracle():
    """As tension_n -> infinity, `solve_tensioned` converges to the straight
    chord of the same arc length running from the apex toward the stake
    (the module docstring's built-in regression oracle). Build that straight
    chord BY HAND -- not by calling the catenary solver -- so the comparison
    is independent of the solver's own numerics, then chord it into the same
    number of straight segments (`chords_per_arm`) that `build_wires()` uses,
    so both geometries get the identical auto_mesh segment counts per chord
    and the comparison isolates the sag physics, not a mesh-density delta.
    """
    b = _builder(tension_n=1.0e5)
    z_catenary = _z(b)

    n = int(b.chords_per_arm)
    apex_x, apex_z = _EPS, b.base
    dx = b.stake_dist - apex_x
    dz = b.stake_height - apex_z
    reach = math.hypot(dx, dz)
    ux, uz = dx / reach, dz / reach
    arm_length_m = 0.25 * b.design_wavelength * b.length_factor

    class StraightArmOracle(Builder):
        """Same feed wire + chord count as invvee_catenary, but each arm is
        the exact analytic straight chord of `arm_length_m` toward the
        stake -- the T -> infinity limit, computed without touching
        catenary.py at all."""

        def build_wires(self):
            plane_points = []
            for i in range(n + 1):
                s = arm_length_m * i / n
                plane_points.append((apex_x + s * ux, apex_z + s * uz))
            wires = [Wire((0.0, -_EPS, apex_z), (0.0, _EPS, apex_z), ex=1 + 0j)]
            for sign in (1.0, -1.0):
                arm_pts = [(0.0, sign * h, z) for h, z in plane_points]
                wires.extend(Wire(p0, p1) for p0, p1 in zip(arm_pts[:-1], arm_pts[1:]))
            return wires

    z_oracle = _z(StraightArmOracle(dict(b._params)))

    rel_err = abs(z_catenary - z_oracle) / abs(z_oracle)
    assert rel_err < 0.01, (z_catenary, z_oracle, rel_err)


# ---------------------------------------------------------------------------
# 2. Chord-count convergence
# ---------------------------------------------------------------------------


def test_chord_count_convergence():
    """More chords per arm means a finer polyline approximation of the same
    smooth catenary curve, so impedance should settle down as chords_per_arm
    grows, at a fixed electrical mesh density (nominal_nsegs untouched).

    16/32/64 (doubling, well above the UI slider's 6-32 sticker range) are
    used rather than the UI's own 8/16/24 window: at very low absolute
    per-chord segment counts (1-3 segments, since auto_mesh rounds each
    short chord's own count independently -- issue #630's per-wire auto_mesh
    contract), integer rounding on individual chords aliases the *total*
    electrical segment count non-monotonically with chords_per_arm (e.g.
    8 chords can auto-mesh to MORE total segments than 16 chords, because
    each of the 8 longer chords rounds up to 3 segments while each of the 16
    shorter ones rounds down to 1). That is a mesh-density artifact, not the
    curve-fidelity convergence this test is after, and it clears up once the
    per-chord segment counts are comfortably above 1 -- doubling from 16
    confirms strictly shrinking steps.
    """
    zs = {n: _z(_builder(chords_per_arm=n)) for n in (16, 32, 64)}
    step1 = abs(zs[32] - zs[16])
    step2 = abs(zs[64] - zs[32])
    assert step2 < step1, (step1, step2)
    assert step2 < 1.0, step2


# ---------------------------------------------------------------------------
# 3. Physics smoke: sag vs tension, reactance vs tension
# ---------------------------------------------------------------------------


def test_sag_decreases_monotonically_with_tension():
    sags = [_builder(tension_n=t).rig_solutions().max_sag_m for t in (5.0, 40.0, 300.0)]
    assert sags[0] > sags[1] > sags[2] > 0.0


def test_reactance_moves_monotonically_with_tension():
    """Direction, determined by actually running the solve (not assumed):
    reactance INCREASES with tension. A slacker (lower-tension) arm sags
    into a shape that folds more of its fixed wire length into a smaller
    net horizontal reach from the feed -- the same total conductor length
    packed into a physically shorter span, which behaves like *shortening*
    the antenna (moving it away from the taut straight-arm's tuning) and
    pulls the reactance down/capacitive. As tension climbs toward the taut
    limit the arm straightens back out toward the full-reach straight-arm
    geometry (see the taut-limit oracle test above, ~+20.36 ohm), and the
    reactance climbs back up toward that value.
    """
    freqs = (5.0, 40.0, 300.0)
    reactances = [_z(_builder(tension_n=t)).imag for t in freqs]
    assert reactances[0] < reactances[1] < reactances[2]


def test_emitted_arm_bows_off_its_chord_by_the_solved_sag():
    """The EMITTED wires must carry the catenary's curve, not just its
    endpoints. Geometry-level on purpose: at hand-tension scales the
    curve-vs-chord impedance delta is fractions of an ohm, so no electrical
    assertion in this file can tell a correctly sagged arm from its straight
    chord (a straight-chord mutation of build_wires survived exactly that
    way in review) — but a flattened plane->3D mapping is still a real bug
    the moment anything reads the geometry. Pin the interior nodes' max
    perpendicular deviation from the arm's own chord to the solver's
    reported max_sag_m."""
    b = _builder(tension_n=5.0)
    sol = b.rig_solutions()
    wires = b.build_wires()
    # The +y arm's chords, in emission order (apex-first).
    arm = [w for w in wires if w.ex is None and w.p0[1] > 0]
    nodes = [(w.p0[1], w.p0[2]) for w in arm] + [(arm[-1].p1[1], arm[-1].p1[2])]
    (y0, z0), (y1, z1) = nodes[0], nodes[-1]
    cy, cz = y1 - y0, z1 - z0
    chord = math.hypot(cy, cz)
    devs = [abs((cy * (z - z0) - cz * (y - y0)) / chord) for y, z in nodes[1:-1]]
    # Discrete nodes sample near, not exactly at, the continuous maximum.
    assert max(devs) == pytest.approx(sol.max_sag_m, rel=0.05)
    assert max(devs) > 1.0e-3  # and the bow is real, not round-off


# ---------------------------------------------------------------------------
# 4. Cut-length invariance
# ---------------------------------------------------------------------------


def test_cut_length_invariant_under_tension():
    b = _builder()
    expected_arm_length = 0.25 * b.design_wavelength * b.length_factor

    for t in (5.0, 40.0, 300.0, 1.0e4):
        solution = _builder(tension_n=t).rig_solutions()
        assert solution.segments[0].arc_length_m == pytest.approx(
            expected_arm_length, rel=1e-12
        )

    # Total emitted polyline length ~= 2 arms + the short feed wire.
    wires = b.build_wires()
    total = sum(math.dist(w.p0, w.p1) for w in wires)
    expected_total = 2.0 * expected_arm_length + 2.0 * _EPS
    assert total == pytest.approx(expected_total, rel=1e-6)


# ---------------------------------------------------------------------------
# 5. Weightless wire rejected
# ---------------------------------------------------------------------------


def test_weightless_wire_raises():
    class WeightlessVariant(Builder):
        def build_wire_material(self):
            return None

    b = WeightlessVariant()
    with pytest.raises(ValueError, match="WireSpec"):
        b.rig_solutions()
    with pytest.raises(ValueError, match="WireSpec"):
        b.build_wires()


# ---------------------------------------------------------------------------
# 6. Wires stay above ground
# ---------------------------------------------------------------------------


def test_wires_stay_above_ground_at_defaults():
    wires = Builder().build_wires()
    zs = [w.p0[2] for w in wires] + [w.p1[2] for w in wires]
    assert min(zs) > 0.0


# ---------------------------------------------------------------------------
# 7. Catalog smoke
# ---------------------------------------------------------------------------


def test_builds_meshes_and_solves_at_defaults():
    b = Builder()
    wires = b.build_wires()
    assert len(wires) == 1 + 2 * int(b.chords_per_arm)

    feed = [w for w in wires if w.ex is not None]
    assert len(feed) == 1
    assert feed[0].ex == 1 + 0j

    for w in wires:
        assert isinstance(w, Wire)
        assert w.n_seg is not None and w.n_seg >= 1

    z = _z(b)
    assert math.isfinite(z.real) and math.isfinite(z.imag)
    assert z.real > 0.0

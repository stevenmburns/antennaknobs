"""The `surface` convention of `verticals.buried_radial_vertical` (momwire#865).

Radials lying ON the ground, the way most amateurs build a screen. momwire
refuses a wire IN the plane and always will — a conductor on the interface is
not a physical configuration — so a surface radial is served as the ELEVATED
family at the conductor's own centre height. For an insulated wire that height
is `b`, the jacket's outer radius: the jacket rests on the soil and the copper
sits a jacket thickness above it.

## The guard is a FEATURE check, and that is the whole point

momwire's pointer runs ahead of its PyPI version by convention, so the
submodule and the released 0.47.0 both DECLARE 0.47.0. A version comparison
therefore cannot tell a momwire that has the coated-wire pair from one that
does not — and the older build does not refuse this deck, it answers it:

    momwire 0.47.0 (PyPI)        221.712 - 144.270j    NO warning
    momwire with #872/#874/#875  159.184 -  35.308j    advisory fires

62 ohm apart in R, 109 in X, in silence. That is the one failure mode this
design must not have, so it checks for the two names it actually depends on
(`equivalent_radius`, `_surface_height`) and refuses by name without them.
Same rule as the buried capability gate took from #1103/#966: ask about the
thing you depend on, because absence is "cannot be asked", never "served".

## Every catalog wire clears the BARE floor

18 / 22 / 28 AWG PVC are b/a = 2.05 / 2.49 / 3.12, so h = b is always at or
above momwire's bare h/a >= 2 bound — and a thinner conductor under the same
jacket has a LARGER ratio, not a smaller one. This variant is therefore served
by the older, stricter bound today; momwire#875's jacketed relaxation is what
would keep it served if an enamel-class wire (b/a ~ 1.05) were ever added.
Worth pinning so nobody "simplifies" the guard on the belief that #875 is
load-bearing here.

## What is gated, following AK#1131's shape

The banked per-corner answers, tight enough that a real change in the
geometry, the mesher or the fill moves them; the degree pair being
NON-DEGENERATE as well as bounded; and the refusals firing BY NAME.

WHAT IS NOT PROVEN, stated so the omission is not read as a claim: these are
driving-point impedances, and #1131 measured that on this deck family a 7x
coarsening moves Z only 0.362 ohm. So "the mesh is fine enough" is not what
these gates show, and asserting it would pass for a badly meshed deck too.

Marked `antenna_computation_check`: the N = 16 corner is ~54 s, past the
suite's 5 s unmarked ceiling, and that marker is the main-only CI lane.
"""

from __future__ import annotations

import sys
import warnings

import pytest

from antennaknobs import as_wire, resolve_variant_params
from antennaknobs.designs.verticals.buried_radial_vertical import Builder
from antennaknobs.engines.momwire import MomwireEngine
from antennaknobs.network import WIRES

GROUND = dict(ground=("finite", 13.0, 0.005), ground_z=0.0)
Z_TOL = 0.10  # ohm, AK#1131's tolerance on this design family


def _params(**over):
    p = dict(resolve_variant_params(Builder, "surface"))
    p.update(over)
    return p


def _builder(**over):
    return Builder(params=_params(**over))


def _z(**over):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return MomwireEngine(_builder(**over), **GROUND).impedance()[0]


# ---------------------------------------------------------------------------
# Geometry — free, so PR-lane
# ---------------------------------------------------------------------------


def test_the_radials_lie_on_the_ground_and_nothing_is_buried():
    """The interface is never pierced: no wire goes below z = 0, and the
    radials sit at exactly the jacket's outer radius."""
    b = _builder()
    spec = WIRES[b.wire_type]
    wires = [as_wire(t) for t in b.build_wires()]
    assert all(w.p0[2] >= 0.0 and w.p1[2] >= 0.0 for w in wires)
    radials = [w for w in wires if w.p0[2] == w.p1[2]]
    assert len(radials) == b.n_radials
    for w in radials:
        assert w.p0[2] == pytest.approx(spec.insulation_radius)


def test_the_jacket_rides_the_RADIALS_ONLY():
    """The mast is bare aluminium in every real build of this antenna, and a
    SCALAR insulation would jacket it too — worth ~15-30 ohm of spurious
    reactance, and the trap that sent momwire#874's first reading the wrong
    way. Per-wire specs make that structurally impossible; pinned anyway."""
    wires = [as_wire(t) for t in _builder().build_wires()]
    jacketed = [w for w in wires if w.spec is not None and w.spec.insulation_radius]
    bare = [w for w in wires if w.spec is None or not w.spec.insulation_radius]
    assert len(jacketed) == _builder().n_radials
    assert bare, "the mast and feed gap must carry no jacket"
    # ...and every jacketed wire is horizontal, every bare one vertical.
    assert all(w.p0[2] == w.p1[2] for w in jacketed)
    assert all(w.p0[0] == w.p1[0] == 0.0 for w in bare)


def _without_the_coated_pair(monkeypatch):
    """Make `momwire._surface_height` unimportable, which is what a momwire
    from before #872 looks like to the guard (a `None` entry in sys.modules
    raises ImportError on import)."""
    monkeypatch.setitem(sys.modules, "momwire._surface_height", None)


def test_the_guard_refuses_by_name_on_a_momwire_without_the_pair(monkeypatch):
    """The pinned-build path: the deck must NOT solve into the silent
    221.7 - 144.3j; it names the missing model and says why a version check
    would not have helped."""
    _without_the_coated_pair(monkeypatch)
    with pytest.raises(ValueError, match="equivalent-radius PAIR"):
        MomwireEngine(_builder(), **GROUND)


def test_the_guard_is_silent_over_free_space(monkeypatch):
    """Over free space there is no interface for the jacket to rest on, so
    the same deck on the same old momwire constructs normally. This pins the
    engine passing its NORMALISED ground_z (None for free space) rather than
    the raw argument, whose default is 0.0 whatever the ground."""
    _without_the_coated_pair(monkeypatch)
    MomwireEngine(_builder(), ground=None)  # must not raise


def test_a_bare_wire_type_refuses_by_name():
    """The jacket is what holds the conductor off the soil; without one this
    is a wire in the plane, which momwire refuses."""
    with pytest.raises(ValueError, match="needs an INSULATED wire_type"):
        _builder(wire_type="18-awg").build_wires()
    with pytest.raises(ValueError, match="needs an INSULATED wire_type"):
        _builder(wire_type=None).build_wires()


def test_every_catalog_jacket_clears_the_bare_floor():
    """So the guard cannot be "simplified" on the belief that momwire#875's
    jacketed relaxation is load-bearing here. It is not, today: a thinner
    conductor under the same jacket has a LARGER b/a, not a smaller one."""
    for name, w in WIRES.items():
        if w.insulation_radius:
            assert w.insulation_radius / w.radius >= 2.0, name


def test_the_note_carries_the_advisory_and_admits_the_gap():
    """The app has no runtime warnings channel yet, so this static note is
    the stand-in — and it says so, rather than implying the live advisory is
    surfaced."""
    note = _params()["ui_params"]["notes"]
    assert "INDICATIVE RATHER THAN PREDICTIVE" in note
    assert "41" in note and "10" in note  # the +-1 mm figures at N=4 and N=16
    assert "does not surface solver advisories yet" in note


# ---------------------------------------------------------------------------
# Knob corners — banked answers (AK#1131's shape)
# ---------------------------------------------------------------------------
#
# Measured on momwire 1e19482, auto mesh, quadrature omitted — exactly the call
# the web makes. See the module docstring for what these do NOT prove.

BANKED = {
    "default": ({}, 60.621 + 60.949j),
    "n16": ({"n_radials": 16}, 48.747 + 42.560j),
    "n1": ({"n_radials": 1}, 148.238 + 153.062j),
    "rf1": ({"radial_factor": 1.0}, 120.125 + 53.495j),
    "28awg": ({"wire_type": "28-awg-pvc"}, 68.762 + 86.881j),
    "22awg": ({"wire_type": "22-awg-pvc"}, 63.058 + 71.366j),
    "grass3mm": ({"surface_h_m": 0.003}, 55.098 + 39.753j),
    "lf08": ({"length_factor": 0.8}, 37.898 - 133.084j),
}


@pytest.mark.antenna_computation_check
@pytest.mark.parametrize("key", sorted(BANKED))
def test_the_corner_answer_is_banked(key):
    over, expect = BANKED[key]
    got = _z(**over)
    assert abs(got - expect) < Z_TOL, (key, got, expect)


@pytest.mark.antenna_computation_check
def test_the_degree_pair_is_bounded_AND_non_degenerate():
    """Same trunk, second reading. The lower bound is the load-bearing half:
    a bug that silently ignored `degree` would collapse the separation to
    zero, which a one-sided bound would wave through."""
    from momwire import BSplineSolver

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        kw = dict(solver=BSplineSolver, **GROUND)
        d2 = MomwireEngine(_builder(), solver_kwargs={"degree": 2}, **kw).impedance()[0]
        d1 = MomwireEngine(_builder(), solver_kwargs={"degree": 1}, **kw).impedance()[0]
    assert abs(d1 - d2) < 1.5, (d1, d2)
    assert abs(d1 - d2) > 0.01, ("degree kwarg ignored?", d1, d2)


@pytest.mark.antenna_computation_check
def test_raising_the_wire_out_of_the_grass_moves_the_answer():
    """The class is ill-conditioned in h, which is the whole content of the
    note — and a vacuity guard: if `surface_h_m` stopped reaching the
    geometry, every banked corner above would still pass."""
    assert abs(_z(surface_h_m=0.003) - _z()) > 1.0

"""Catalog-wide Δ/a lint (issue #484): no builder may mesh a wire so
densely that fine-mesh refinement drives segment length under ~2× the
wire radius — the reduced-kernel thin-wire floor (NEC-2 guideline: Δ/a > 8
for <1 % error, "reasonable solutions" down to ~2; below ~1 the discretized
equation is ill-posed and the sin/pulse/pynec family produces garbage).

The folded_invvee family shipped exactly this defect: a 0.1 m link carrying
the full nominal count hit Δ/a = 0.62 at N=321, and the folded element's
stub antiresonance amplified the localized error into a wildly wrong
impedance (280−1188j vs the true 223−30j) that LOOKED like a convergence
class of its own — see the #484 mechanism comments. Geometry-only check
(no solves), so it sweeps every catalog design cheaply.
"""

import math

import pytest

from antennaknobs.cli import list_builtin_designs

# The refinement rung the #484 breakdowns surfaced at — well past any
# default, deep enough to expose density defects on short wires.
N_FINE = 321
FLOOR = 2.0
DEFAULT_RADIUS = 0.0005

# Audited exceptions (design name -> why it is allowed under the floor).
EXEMPT = {
    # W8IO measurement-fidelity whip: deliberately deck-faithful dense mesh
    # on a fat tube; audited in #435, solve quality tracked against the
    # published deck. Δ/a ≈ 1.05 at N=321.
    "verticals.elt_whip": "deck-faithful dense mesh on fat tube (#435 audit)",
    # Fat-element OWA yagi: long tube element whose builder doubles the
    # driven element's count; falls to Δ/a ≈ 0.65 at N=321. Latent —
    # tracked in #484's audit comment; needs its own meshing decision.
    "beams.owa_yagi": "fat tube element, tracked in #484 audit",
}


def _min_delta_a(builder_cls):
    b = builder_cls()
    b.nominal_nsegs = N_FINE
    try:
        mat = b.build_wire_material()
        default_r = getattr(mat, "radius", DEFAULT_RADIUS) or DEFAULT_RADIUS
    except Exception:
        default_r = DEFAULT_RADIUS
    worst = math.inf
    worst_wire = None
    for i, w in enumerate(b.build_wires()):
        p0, p1, ns = w[0], w[1], w[2]
        spec = getattr(w, "spec", None)
        r = getattr(spec, "radius", None) or default_r
        length = math.dist(p0, p1)
        if ns <= 0 or length == 0:
            continue
        ratio = (length / ns) / r
        if ratio < worst:
            worst, worst_wire = ratio, i
    return worst, worst_wire


@pytest.mark.parametrize("name", sorted(list_builtin_designs()))
def test_no_wire_under_delta_a_floor_at_fine_mesh(name):
    import importlib

    mod = importlib.import_module(f"antennaknobs.designs.{name}")
    worst, wire = _min_delta_a(mod.Builder)
    if name in EXEMPT:
        pytest.skip(f"exempt: {EXEMPT[name]} (measured Δ/a = {worst:.2f})")
    assert worst >= FLOOR, (
        f"{name} wire {wire} hits Δ/a = {worst:.2f} at N={N_FINE} — under "
        f"the thin-wire floor ({FLOOR}). Give short wires proportional "
        "density via segs_for (issue #484); do not carry the full nominal "
        "count on a wire much shorter than the reference arm."
    )


def test_folded_invvee_sin_ladder_stays_flat():
    """The #484 repro rung: before the density fix the sin basis broke to
    232.9−230.2j at N=161 (and −1188j at 321). With wire 3 at arm density
    the ladder holds the basis-agreed 223−30j."""
    from antennaknobs.engines.momwire import MomwireEngine
    from momwire import SinusoidalSolver

    from antennaknobs.designs.dipoles.folded_invvee import Builder

    b = Builder()
    b.nominal_nsegs = 161
    z = MomwireEngine(b, solver=SinusoidalSolver).impedance()[0]
    assert abs(z - (223 - 30j)) < 5.0, z

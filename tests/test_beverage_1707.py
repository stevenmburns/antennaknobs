"""`wire.beverage` — a Beverage with a ground rod at each end (AK#1707).

Two lanes, for the reason `test_buried_catalog.py` gives: a rod in the soil
is a mixed-medium fill that takes minutes, which the suite's ~2 s-per-test
rule exists to keep out.

PER-PR (no buried solve). The geometry and network, checked on
`build_wires()` / `build_network()`; the served scope, asked of the solvers
themselves by constructing them (which is what raises a by-name refusal) and
of the web adapter's coverage table; and the traveling-wave behaviour the
issue asks to pin — the terminator absorbs a measurable share, and removing
it degrades F/B — measured on the `contact` variant with PyNEC over a
Sommerfeld ground, where a solve takes about a second.

HEAVY (`heavy_mesh`, run manually). The same questions asked of the rod
design itself on razor-2p, the only momwire lane that serves it, plus the
rods-versus-contact difference and the RDF. The first solve builds the
below-ground tables (~90 s, ~350 MB); the rest reuse them, and the lane
takes about two minutes.
"""

from __future__ import annotations

import math
import warnings

import numpy as np
import pytest

import antennaknobs.web.server  # noqa: F401 — resolves the adapter import cycle
from antennaknobs import as_wire, resolve_variant_params
from antennaknobs.designs.wire.beverage import Builder
from antennaknobs.engines.momwire import MomwireEngine
from antennaknobs.network import Load, Transformer
from antennaknobs.web.adapter import design_backend_coverage
from momwire import BSplineSolver, RazorSolver, SinusoidalGalerkinSolver

C_LIGHT = 299792458.0
AVERAGE = ("finite", 13.0, 0.005)
POOR = ("finite", 13.0, 0.002)
RAZOR_2P = {"solver": RazorSolver, "solver_kwargs": {"nec5_quadrature": True}}


def _wires(b):
    return [as_wire(w) for w in b.build_wires()]


def _contact():
    return Builder(resolve_variant_params(Builder, "contact"))


def _named(ws, name):
    (w,) = [w for w in ws if w.name == name]
    return w


# ---------------------------------------------------------------------------
# geometry and network
# ---------------------------------------------------------------------------


def test_the_run_is_the_issues_beverage():
    """~1.5 wl of #14 copper at 2.5 m over the 160 m band: 1.83 MHz makes
    it ~246 m, and every segment is horizontal or vertical (the crossing
    serve's corner is measured for a right angle only)."""
    b = Builder()
    ws = _wires(b)
    wl = C_LIGHT / (b.design_freq * 1e6)
    (run,) = [w for w in ws if w.p0[2] == w.p1[2]]
    assert run.p0[2] == pytest.approx(2.5)
    assert abs(run.p1[0] - run.p0[0]) / wl == pytest.approx(1.5)
    assert 240.0 < abs(run.p1[0] - run.p0[0]) < 250.0
    for w in ws:
        vertical = w.p0[:2] == w.p1[:2]
        assert vertical or w.p0[2] == w.p1[2], w
    assert b.build_wire_material().radius == pytest.approx(1.628e-3 / 2, rel=1e-3)


def test_each_end_stands_on_a_rod_that_crosses_into_the_soil():
    """A rod at each end runs from the interface to `rod_depth` below it, and
    the only wire meeting it at z = 0 is that end's feed or termination edge:
    ONE above member per crossing node, the served shape."""
    b = Builder()
    ws = _wires(b)
    rods = [w for w in ws if min(w.p0[2], w.p1[2]) < 0.0]
    assert len(rods) == 2
    for rod in rods:
        assert sorted((rod.p0[2], rod.p1[2])) == [-b.rod_depth, 0.0]
        top = rod.p0 if rod.p0[2] == 0.0 else rod.p1
        above = [
            w for w in ws if w is not rod and top in (w.p0, w.p1) and w.name is not None
        ]
        assert len(above) == 1 and above[0].name in ("feed", "term")
    xs = sorted(r.p0[0] for r in rods)
    assert xs[0] == 0.0 and xs[1] > 200.0


def test_the_contact_variant_has_no_rods_and_touches_the_plane():
    """`rods=False` (the `contact` variant, AK#1707's NEC-2 decision): the
    same down-leads stop ON the plane, the way `terminated_longwire` does,
    and nothing goes below it."""
    ws = _wires(_contact())
    assert all(min(w.p0[2], w.p1[2]) >= 0.0 for w in ws)
    ends_on_plane = [p for w in ws for p in (w.p0, w.p1) if p[2] == 0.0]
    assert len(ends_on_plane) == 2
    # Everything above the plane is the rod design's, wire for wire.
    above = [w for w in _wires(Builder()) if min(w.p0[2], w.p1[2]) >= 0.0]
    assert [(w.p0, w.p1) for w in ws] == [(w.p0, w.p1) for w in above]


def test_the_network_terminates_the_far_end_and_steps_the_feed_down():
    b = Builder()
    net = b.build_network()
    (load,) = [br for br in net.branches if isinstance(br, Load)]
    assert load.port == "term" and load.r == b.term_r == 500.0
    (xf,) = [br for br in net.branches if isinstance(br, Transformer)]
    # n is the rig:feed voltage ratio; the impedance ratio is 1/n^2 = 9.
    assert (xf.a, xf.b) == ("rig", "feed")
    assert 1.0 / xf.n**2 == pytest.approx(9.0)
    (src,) = net.sources
    assert src.port == "rig"


def test_the_deck_is_one_radius_unless_the_rods_are_given_their_own():
    """momwire refuses a TWO-RADIUS crossing deck with more than one crossing
    node (plan U5 x U9, never measured together), so by default the rods are
    the wire's own #14. `rod_radius_m` gives them a real rod's radius, which
    NEC-5 takes and momwire refuses by name."""
    assert all(w.spec is None for w in _wires(Builder()))
    b = Builder()
    b.rod_radius_m = 0.008
    rods = [w for w in _wires(b) if min(w.p0[2], w.p1[2]) < 0.0]
    assert [r.spec.radius for r in rods] == [0.008, 0.008]
    with pytest.raises(NotImplementedError, match="TWO-RADIUS crossing deck"):
        _razor_solver(b)


# ---------------------------------------------------------------------------
# served scope: asked of the solvers, never restated
# ---------------------------------------------------------------------------


def _razor_solver(b, ground=AVERAGE):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        eng = MomwireEngine(b, ground=ground, **RAZOR_2P)
        return eng._make_solver(wavelength=C_LIGHT / (b.freq * 1e6))


@pytest.mark.parametrize("ground", [AVERAGE, POOR], ids=["average", "poor"])
def test_razor_2p_serves_the_rod_deck(ground):
    """razor-2p's own buried pre-flight — the check that runs before a fill
    — passes the default deck over both soils the docstring quotes."""
    assert _razor_solver(Builder(), ground).buried_serve_refusal() is None


@pytest.mark.parametrize(
    "solver", [BSplineSolver, SinusoidalGalerkinSolver], ids=lambda c: c.__name__
)
def test_bspline_and_galerkin_refuse_the_rod_deck_by_name(solver):
    """These lanes' quadrature reaches within a centimetre of the interface,
    so their below/below pair between the two rod tops, ~246 m apart, is far
    under the 1-arc-minute grazing floor the tables start at (momwire#1149
    measures bspline reaching the floor at 12 m on its own two-node deck).
    Pinned so the day either serves, this fails and the docstring's engine
    list is revisited."""
    with pytest.raises(ValueError, match="grazing floor"):
        MomwireEngine(Builder(), ground=AVERAGE, solver=solver)


def test_nec2_family_is_refused_by_name_on_the_rod_deck():
    """The rod variant needs a wire in the soil. PyNEC and NEC-2 have no
    below-ground medium and would solve it as if the rods were in air, so
    the app withholds both with their own sentences (AK#1167)."""
    cov = design_backend_coverage("wire.beverage")
    assert "buried" in cov["needs"] and "crossing_junction" in cov["needs"]
    for backend in ("pynec", "nec2"):
        refusal = cov["refusals"][backend]
        assert refusal["capability"] == "buried"
        assert "below" in refusal["reason"]
    assert "razor-2p" not in cov["refusals"]


# ---------------------------------------------------------------------------
# traveling-wave behaviour, on the contact variant (PyNEC, ~1 s a solve)
#
# A signature, not a number. NEC-2 joins a wire ending on a Sommerfeld ground
# to a perfectly conducting point, which is outside its formulation, and its
# feed impedance here (1085 - 387j ohm) is nothing like the 532 ohm momwire
# and NEC-5 agree on. What any ground connection does show is the terminated
# traveling wave: power into the resistor, and F/B that goes when it does.
# The same two questions are asked of the ROD design on razor-2p below.
# ---------------------------------------------------------------------------


def _pynec(b):
    from antennaknobs.engines.pynec import PyNECEngine

    return PyNECEngine(b, ground=AVERAGE)


def _fb(ff):
    """Peak gain and front-to-back toward +x (the terminated end) at the
    strongest elevation in that direction."""
    rings = np.asarray(ff.rings, float)
    phis = np.asarray(ff.phis, float)
    fwd = int(np.argmin(np.abs(phis - 0.0)))
    back = int(np.argmin(np.abs(phis - 180.0)))
    ti = int(np.argmax(rings[:, fwd]))
    return rings[ti, fwd], rings[ti, fwd] - rings[ti, back]


def _coarse_ff(eng):
    return eng.far_field(n_theta=30, n_phi=72, del_theta=3, del_phi=5)


def test_contact_terminator_absorbs_a_measurable_share():
    pytest.importorskip("PyNEC")
    eng = _pynec(_contact())
    eng.current_distribution()
    budget = dict(eng._excited_power_budget)
    (term_row,) = [w for label, w in budget.items() if "term" in label.lower()]
    share = term_row / eng._excited_p_in
    assert 0.05 < share < 0.9, budget


def test_contact_removing_the_termination_degrades_fb():
    pytest.importorskip("PyNEC")
    b = _contact()
    _, fb_term = _fb(_coarse_ff(_pynec(b)))
    b_open = _contact()
    b_open.term_r = 1e9
    _, fb_open = _fb(_coarse_ff(_pynec(b_open)))
    assert fb_term > 8.0
    assert fb_term - fb_open > 5.0


# ---------------------------------------------------------------------------
# HEAVY: the rod design on razor-2p (~2 min for the lane, ~350 MB)
# ---------------------------------------------------------------------------


def _razor(b, ground=AVERAGE):
    from antennaknobs.far_field import refined_pattern_metrics

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        eng = MomwireEngine(b, ground=ground, **RAZOR_2P)
        z = complex(eng.impedance()[0])
        m = refined_pattern_metrics(eng.gain_evaluator())
    return eng, z, m


@pytest.mark.heavy_mesh
def test_heavy_rods_beverage_on_razor_2p():
    """The headline numbers the module docstring quotes, over average soil:
    the beam off the terminated end, a terminator burning a measurable share,
    RDF in the range a 1.5 wl Beverage should read, and a feed near the
    termination value (its 9:1 step-down putting the rig side near 75 ohm)."""
    eng, z, m = _razor(Builder())
    assert m["azimuth_deg"] == pytest.approx(0.0, abs=1.0)
    assert m["front_to_back_db"] == pytest.approx(19.1, abs=0.5)
    assert m["rdf_db"] == pytest.approx(11.95, abs=0.1)
    assert m["peak_gain_dbi"] == pytest.approx(-9.10, abs=0.1)
    budget = dict(eng._excited_power_budget)
    (term_row,) = [w for label, w in budget.items() if "term" in label.lower()]
    assert term_row / eng._excited_p_in == pytest.approx(0.329, abs=0.01), budget
    # Rig side; NEC-5 at the same mesh reads 75.106 - 11.036j.
    assert abs(z - (75.098 - 11.058j)) < 0.1, z


@pytest.mark.heavy_mesh
def test_heavy_unterminated_rods_beverage_loses_its_fb():
    b = Builder()
    _, _, m_term = _razor(b)
    b_open = Builder()
    b_open.term_r = 1e9
    _, _, m_open = _razor(b_open)
    assert m_term["front_to_back_db"] - m_open["front_to_back_db"] > 5.0


@pytest.mark.heavy_mesh
def test_heavy_rods_are_not_a_pec_contact():
    """Rods in lossy soil against the same leads touching the plane: the
    contact spelling models a perfect connection to the interface, the rods
    a real, lossy one, so the feed impedance moves by more than a few ohms
    at the rig side."""
    _, z_rods, _ = _razor(Builder())
    _, z_contact, _ = _razor(_contact())
    assert abs(z_rods - z_contact) > 3.0, (z_rods, z_contact)
    assert math.isfinite(abs(z_contact))

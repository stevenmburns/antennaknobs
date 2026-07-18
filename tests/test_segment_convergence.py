"""Convergence-flow plumbing: nominal_nsegs on the Builder, segment_parity
on the SimulationEngine. The momwire version had a working convergence
sweep; this exercises the equivalent path through antennaknobs."""

from __future__ import annotations

import pytest

from antennaknobs.designs.specialty.bowtie import Builder as BowtieBuilder
from antennaknobs.designs.dipoles.invvee import Builder as InvVeeBuilder
from antennaknobs.engine import SimulationEngine

pytest.importorskip("PyNEC")
from antennaknobs.engines.pynec import PyNECEngine  # noqa: E402
from antennaknobs.engines.momwire import MomwireEngine  # noqa: E402


def test_coerce_n_seg_any_passes_through():
    assert SimulationEngine.coerce_n_seg(7, "any") == 7
    assert SimulationEngine.coerce_n_seg(8, "any") == 8


@pytest.mark.parametrize("n,expected", [(1, 1), (2, 3), (3, 3), (20, 21), (21, 21)])
def test_coerce_n_seg_odd_bumps_even_up(n, expected):
    assert SimulationEngine.coerce_n_seg(n, "odd") == expected


@pytest.mark.parametrize("n,expected", [(1, 2), (2, 2), (3, 4), (20, 20), (21, 22)])
def test_coerce_n_seg_even_bumps_odd_up(n, expected):
    assert SimulationEngine.coerce_n_seg(n, "even") == expected


@pytest.mark.parametrize("parity,expected", [("any", 1), ("odd", 1), ("even", 2)])
def test_coerce_n_seg_floors_at_minimum(parity, expected):
    """Guard against ZeroDivisionError in momwire's _build_geometry when the
    slider lands at N=0 — the engine still produces a runnable mesh."""
    assert SimulationEngine.coerce_n_seg(0, parity) == expected


def test_builder_default_nominal_nsegs():
    """Framework param is injected at construction time without showing up
    in default_params (so the param panel ignores it)."""
    b = BowtieBuilder()
    assert b.nominal_nsegs == 21
    assert "nominal_nsegs" not in BowtieBuilder.default_params


def test_builder_nominal_nsegs_scales_per_edge_counts():
    """The hardcoded n_seg literals are now expressions in nominal_nsegs.
    Verifies major edges scale 1:1 while minor edges keep their floor."""
    b = BowtieBuilder()
    b.nominal_nsegs = 41
    seg_counts = sorted({t[2] for t in b.build_wires()})
    assert 41 in seg_counts  # major radiator scaled with N
    b.nominal_nsegs = 7
    seg_counts = sorted({t[2] for t in b.build_wires()})
    assert min(seg_counts) >= 3  # floor on minor edges holds at small N


# Parity coercion lands an engine attachment on a wire's middle segment, so it
# applies to the FED wire only; unfed wires keep their exact segment count
# (issue #450 — coercing unfed, tightly-coupled wires like capacity hats shifts
# their modelled coupling enough to flip the impedance sign). These check the
# per-solver parity is right AND that the fed/unfed split is honoured.
_P0, _P1 = (0, 0, 0.0), (0, 0, 1.0)


def test_momwire_default_coerces_fed_odd_preserves_unfed():
    """The default solver (BSplineSolver degree=2) wants odd so the feed lands
    on a segment midpoint. The fed even wire is bumped to odd; an unfed even
    wire is preserved (issue #450)."""
    eng = MomwireEngine(BowtieBuilder())  # default BSplineSolver d=2
    assert eng.segment_parity == "odd"
    out = eng._coerce_wire_tuples([(_P0, _P1, 4, None), (_P0, _P1, 4, 1 + 0j, "feed")])
    assert out[0][2] == 4  # unfed even wire preserved
    assert out[1][2] == 5  # fed even wire bumped to odd


def test_momwire_bspline_d1_coerces_fed_even_preserves_unfed():
    """BSplineSolver degree=1 (tent basis) wants even. Fed odd wire → even;
    unfed odd wire preserved."""
    eng = MomwireEngine(BowtieBuilder(), solver_kwargs={"degree": 1})
    assert eng.segment_parity == "even"
    out = eng._coerce_wire_tuples([(_P0, _P1, 5, None), (_P0, _P1, 5, 1 + 0j, "feed")])
    assert out[0][2] == 5  # unfed odd wire preserved
    assert out[1][2] == 6  # fed odd wire bumped to even


def test_pynec_engine_segment_parity_is_odd():
    """PyNECEngine declares odd parity (feed lands at (n+1)//2)."""
    assert PyNECEngine.segment_parity == "odd"


def test_momwire_sinusoidal_coerces_fed_odd_preserves_unfed():
    from momwire import SinusoidalSolver

    eng = MomwireEngine(InvVeeBuilder(), solver=SinusoidalSolver)
    assert eng.segment_parity == "odd"
    out = eng._coerce_wire_tuples(
        [(_P0, _P1, 20, None), (_P0, _P1, 20, 1 + 0j, "feed")]
    )
    assert out[0][2] == 20  # unfed even wire preserved (would have been 21)
    assert out[1][2] == 21  # fed even wire bumped to odd


def test_nominal_nsegs_changes_solver_geometry():
    """Sanity check that the convergence-sweep mechanic works end-to-end:
    different N values produce different total segment counts in the
    flat_wires_to_polylines output."""

    def total_segs(N):
        b = InvVeeBuilder()
        b.nominal_nsegs = N
        eng = MomwireEngine(b)
        return sum(sum(w) for w in eng._edge_segments)

    assert total_segs(11) < total_segs(21) < total_segs(41)


# ------------------------------------------------- segs_for clip (issue #457)


def test_segs_for_scales_proportionally_and_clips_at_one():
    """The count tracks length/ref so segment length stays roughly constant;
    the old floor of 3 over-meshed short wires (segment length could fall
    below a fat wire's radius). Clip is 1 — a wire always gets a mesh."""
    b = BowtieBuilder()
    assert b.nominal_nsegs == 21
    ref = 10.0
    assert b.segs_for(ref, ref) == 21  # reference length → nominal
    assert b.segs_for(0.5 * ref, ref) == 10  # proportional, no parity forcing
    assert b.segs_for(0.05 * ref, ref) == 1  # was 3 pre-#457
    assert b.segs_for(0.0, ref) == 1  # degenerate stays a valid mesh


def test_short_unfed_edges_solve_consistently_across_engines():
    """Validity oracle for 1- and 2-segment unfed edges (issue #457): with
    the floor gone (and #450 no longer re-bumping unfed wires), every basis
    must handle a 1-seg and a 2-seg edge. A dipole with two short unmarked
    stubs must land all four engines on the same driving-point impedance."""
    from types import MappingProxyType

    from momwire import BSplineSolver, SinusoidalSolver

    from antennaknobs import AntennaBuilder

    class B(AntennaBuilder):
        default_params = MappingProxyType({"freq": 14.0})

        def build_wires(self):
            return [
                ((0, 0, 10.0), (0, 0, 20.0), 21, 1 + 0j),
                ((0, 0, 20.0), (0.4, 0, 20.0), 1, None),  # 1-seg stub
                ((0, 0, 10.0), (0.8, 0, 10.0), 2, None),  # 2-seg stub
            ]

    z_ref = PyNECEngine(B(), ground=None).impedance()[0]
    engines = {
        "sin": MomwireEngine(B(), solver=SinusoidalSolver, ground=None),
        "bs1": MomwireEngine(B(), solver_kwargs={"degree": 1}, ground=None),
        "bs2": MomwireEngine(B(), solver=BSplineSolver, ground=None),
    }
    for name, eng in engines.items():
        z = eng.impedance()[0]
        assert abs(z - z_ref) / abs(z_ref) < 0.05, (
            f"{name} diverged on short unfed edges: {z:.2f} vs PyNEC {z_ref:.2f}"
        )

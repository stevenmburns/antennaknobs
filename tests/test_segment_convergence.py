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


def test_momwire_default_coerces_to_odd_parity():
    """The default solver (BSplineSolver degree=2) wants odd-segment counts;
    the engine bumps any even build_wires() output up to odd before the
    solver sees it."""
    b = BowtieBuilder()
    b.nominal_nsegs = 20  # even
    eng = MomwireEngine(b)  # default BSplineSolver d=2 → parity="odd"
    seg_lists = eng._edge_segments
    all_segs = [n for wire in seg_lists for n in wire]
    assert all(n % 2 == 1 for n in all_segs), (
        f"default engine left even segs: {all_segs}"
    )


def test_momwire_bspline_d1_coerces_to_even_parity():
    """BSplineSolver degree=1 (tent basis) wants even-segment counts."""
    b = BowtieBuilder()
    b.nominal_nsegs = 21  # odd
    eng = MomwireEngine(b, solver_kwargs={"degree": 1})
    seg_lists = eng._edge_segments
    all_segs = [n for wire in seg_lists for n in wire]
    assert all(n % 2 == 0 for n in all_segs), f"d=1 engine left odd segs: {all_segs}"


def test_pynec_engine_segment_parity_is_odd():
    """PyNECEngine declares odd parity (feed lands at (n+1)//2)."""
    assert PyNECEngine.segment_parity == "odd"


def test_momwire_sinusoidal_uses_odd_parity():
    from momwire import SinusoidalSolver

    b = InvVeeBuilder()
    b.nominal_nsegs = 20  # even, will get bumped to 21 by sinusoidal
    eng = MomwireEngine(b, solver=SinusoidalSolver)
    assert eng.segment_parity == "odd"
    all_segs = [n for wire in eng._edge_segments for n in wire]
    assert all(n % 2 == 1 for n in all_segs), (
        f"sinusoidal engine left even segs: {all_segs}"
    )


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

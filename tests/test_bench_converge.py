"""Unit tests for the segment-refinement convergence sweep (issue #408).

Exercises the pure plumbing of ``scripts/bench_converge.py`` — design loading,
the nominal_nsegs ladder, the convergence-rate metric, the nec2c-anchor deck
emission, and one real in-process solve — without dispatching the full
subprocess sweep.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

# bench_converge lives in scripts/, not on the package path — load it by file.
_BC_PATH = Path(__file__).resolve().parent.parent / "scripts" / "bench_converge.py"
_spec = importlib.util.spec_from_file_location("bench_converge", _BC_PATH)
bc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bc)


# --------------------------------------------------------------------------
# design loading
# --------------------------------------------------------------------------
def test_load_design_resolves_dotted_name():
    from antennaknobs import AntennaBuilder

    cls = bc.load_design("loops.quad")
    assert issubclass(cls, AntennaBuilder)


def test_load_design_unknown_raises():
    with pytest.raises((ImportError, ModuleNotFoundError)):
        bc.load_design("loops.not_a_real_design")


# --------------------------------------------------------------------------
# nominal_nsegs ladder
# --------------------------------------------------------------------------
def test_default_ladder_is_increasing_and_odd_friendly():
    ladder = bc.DEFAULT_LADDER
    assert ladder == tuple(sorted(ladder))
    assert len(set(ladder)) == len(ladder)
    assert ladder[0] >= 3  # never a degenerate mesh


def test_total_nominal_segs_scales_with_ladder():
    """The mesh the user dials (sum of build_wires seg counts, pre-coercion)
    grows monotonically with nominal_nsegs — the sweep's x-axis is real."""
    cls = bc.load_design("loops.quad")
    small = bc.total_nominal_segs(cls, 7)
    big = bc.total_nominal_segs(cls, 45)
    assert 0 < small < big


# --------------------------------------------------------------------------
# convergence-rate metric
# --------------------------------------------------------------------------
def test_nseg_to_converge_finds_first_within_tol():
    # Climbs 100 -> 130 and plateaus; finest = 130. Within 2% (127.4..132.6)
    # first at N=45.
    series = [(7, 100 + 0j), (15, 120 + 0j), (45, 129 + 0j), (85, 130 + 0j)]
    assert bc.nseg_to_converge(series, tol=0.02) == 45


def test_nseg_to_converge_none_when_still_moving():
    # Every coarse point is >2% from the finest — never settles on this ladder.
    series = [(7, 100 + 0j), (15, 110 + 0j), (45, 125 + 0j), (85, 136 + 0j)]
    assert bc.nseg_to_converge(series, tol=0.02) is None


def test_nseg_to_converge_flat_series_converges_at_coarsest():
    # A higher-order basis flat from the start settles at the coarsest mesh.
    series = [(7, 130.4 + 0j), (15, 130.1 + 0j), (85, 130.0 + 0j)]
    assert bc.nseg_to_converge(series, tol=0.02) == 7


def test_nseg_to_converge_needs_two_points():
    assert bc.nseg_to_converge([(7, 130 + 0j)], tol=0.02) is None


# --------------------------------------------------------------------------
# nec2c anchor: matched-dimension deck at a given mesh
# --------------------------------------------------------------------------
def test_anchor_deck_scales_segments_with_nseg():
    """export_nec on the builder at nominal_nsegs=N emits GW cards whose
    segment counts grow with N — the anchor tracks the same mesh the engines
    solve, so nec2c anchors the convergence curve, not a fixed geometry."""
    cls = bc.load_design("loops.quad")
    coarse = bc.anchor_deck(cls, 7)
    fine = bc.anchor_deck(cls, 45)

    def total_gw_segs(deck: str) -> int:
        return sum(
            int(ln.split()[2]) for ln in deck.splitlines() if ln.startswith("GW ")
        )

    assert "GW " in coarse and "FR " in coarse
    assert total_gw_segs(coarse) < total_gw_segs(fine)


# --------------------------------------------------------------------------
# one real in-process solve (needs momwire) — the sweep's actual measurement
# --------------------------------------------------------------------------
def test_solve_design_returns_impedance_and_mesh():
    pytest.importorskip("momwire")
    cls = bc.load_design("loops.quad")
    res = bc.solve_design(cls, nseg=11, engine="sin", ground="free")
    assert res["error"] is None
    z = complex(*res["z"][0])
    # A ~1 wl driven quad loop near resonance: R is well into the tens-to-low
    # hundreds of ohms, not degenerate.
    assert 20.0 < z.real < 400.0
    assert res["total_nominal_segs"] == bc.total_nominal_segs(cls, 11)

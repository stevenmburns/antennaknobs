"""Unit tests for the full-catalog runtime + peak-RSS benchmark.

Exercises the pure plumbing of ``scripts/bench_catalog.py`` — catalog
enumeration, per-design default-mesh lookup, the ground-model specs, worker-
result cell extraction, and the load-error / finite-ground-guard paths —
without dispatching the (already bench_converge-tested) subprocess worker for
every design.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

# bench_catalog lives in scripts/, not on the package path — load it by file.
# (It inserts scripts/ on sys.path itself so its bench_converge import resolves.)
_BC_PATH = Path(__file__).resolve().parent.parent / "scripts" / "bench_catalog.py"
_spec = importlib.util.spec_from_file_location("bench_catalog", _BC_PATH)
bc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bc)


def test_all_designs_enumerates_the_catalog():
    designs = bc.all_designs()
    assert designs == sorted(designs)  # stable, sorted order
    assert len(set(designs)) == len(designs)  # no dups
    for staple in ("loops.quad", "beams.yagi", "verticals.vertical"):
        assert staple in designs
    assert all("." in d and " " not in d for d in designs)


def test_default_nseg_reads_the_builders_own_value():
    cls = bc.cvg.load_design("loops.quad")  # reused from bench_converge
    assert bc.default_nseg("loops.quad") == cls().nominal_nsegs


def test_ground_specs_match_the_four_models():
    """The ground specs must be the same the web adapter / profile tool use, so
    the numbers are comparable: free, pec, and the two finite models sharing
    eps_r/sigma and differing only in solve method (fast refl-coef vs somm)."""
    from antennaknobs.engines.pynec import DEFAULT_GROUND

    assert bc.GROUNDS["free"] == "free"
    assert bc.GROUNDS["pec"] == "pec"
    assert bc.GROUNDS["fast"] == ("finite-fast",) + tuple(DEFAULT_GROUND[1:])
    assert bc.GROUNDS["somm"] == tuple(DEFAULT_GROUND)
    # fast and somm share the material, differ only in the method label.
    assert bc.GROUNDS["fast"][1:] == bc.GROUNDS["somm"][1:]
    assert bc.GROUNDS["fast"][0] != bc.GROUNDS["somm"][0]
    assert bc.FINITE_GROUNDS == ("fast", "somm")


def test_cell_extracts_ms_and_rss_from_a_worker_result():
    assert bc._cell({"error": None, "solve_s": 0.012, "peak_rss_mb": 137.5}) == (
        12.0,
        137.5,
    )


def test_cell_is_none_on_error_or_missing():
    assert bc._cell(None) is None
    assert bc._cell({"error": "boom"}) is None
    assert bc._cell({}) is None


def test_tag_maps_error_kinds():
    assert bc._tag({"error_kind": "skip"}) == "skip"
    assert bc._tag({"error_kind": "mem"}) == "MEM"
    assert bc._tag({"error_kind": "timeout"}) == "TIME"
    assert bc._tag({"error": "x"}) == "ERR"  # unknown/absent kind
    assert bc._tag(None) == "ERR"


def test_bench_one_reports_load_error_without_dispatching_a_worker():
    """A design that won't construct is caught at mesh lookup and returned as a
    load_error, so one bad design never aborts the sweep — and no subprocess is
    spawned (no grounds dict)."""
    row = bc.bench_one(
        "loops.not_a_real_design",
        ["pynec"],
        ["free"],
        timeout=5.0,
        mem_gb=0,
        nseg_override=None,
        max_seg_finite=2000,
    )
    assert row["design"] == "loops.not_a_real_design"
    assert "load_error" in row
    assert "grounds" not in row


def test_bench_one_guard_skips_finite_grounds_for_oversized_meshes():
    """With a tiny Σseg cap, the finite grounds (fast/somm) are guard-skipped
    without spawning a worker, while free/pec are unaffected. loops.quad's
    default Σseg (172) exceeds a cap of 1, so fast/somm skip; free would still
    run — so we pass only finite grounds here to prove the skip needs no
    subprocess (a real solve would be far slower than this test's budget)."""
    row = bc.bench_one(
        "loops.quad",
        ["pynec", "sin"],
        ["fast", "somm"],
        timeout=5.0,
        mem_gb=0,
        nseg_override=None,
        max_seg_finite=1,
    )
    assert row["total_nominal_segs"] > 1
    for g in ("fast", "somm"):
        for e in ("pynec", "sin"):
            cell = row["grounds"][g][e]
            assert cell["error_kind"] == "skip"
            assert "skipped" in cell["error"]


def test_engine_keys_cover_all_four_solvers():
    assert set(bc.ENGINE_KEYS) == {"pynec", "sin", "bs1", "bs2"}
    assert all(k in bc.ENGINE_LABEL for k in bc.ENGINE_KEYS)

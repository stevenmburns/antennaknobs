"""The workbench's fill report (AK#2327): momwire's own `fill_report()`, read
after a real solve and carried to the browser, bounded and unembellished."""

from __future__ import annotations

import json
import warnings

import momwire
import numpy as np
import pytest
from fastapi.testclient import TestClient

import antennaknobs.web.server as server
from antennaknobs import fill_report as fr
from antennaknobs.engines.momwire import MomwireEngine, clear_z_cache
from antennaknobs.web import adapter

YAGI = "beams.owa_yagi"
SCREEN = "verticals.buried_radial_vertical"

# Whether the installed momwire reports its fill. The recorded pointer
# (momwire 0.94.0) does not; the tests that need a report skip there for this
# one reason, which tests/test_fill_report_skips_2327.py pins.
HAVE_REPORT = fr.reads_fill_report(momwire.BSplineSolver)
SKIP_REASON = (
    "the installed momwire has no fill_report (momwire#2016): "
    "BSplineSolver.fill_report is missing"
)
needs_report = pytest.mark.skipif(not HAVE_REPORT, reason=SKIP_REASON)


def _req(geometry, model, options, **extra):
    return {
        "geometry": geometry,
        "solver": "momwire",
        "momwire_model": model,
        "model_options": options,
        **extra,
    }


def _solve(req):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return server._solve_uncached(req)


def _screen(**options):
    return _req(
        SCREEN,
        "bspline",
        {"degree": 2, "rotational_symmetry": True, **options},
        n_per_wire=9,
        ground=True,
        ground_model="sommerfeld",
    )


@pytest.fixture(autouse=True)
def _fresh_caches():
    clear_z_cache()
    server._SOLVE_CACHE.clear()
    yield
    clear_z_cache()
    server._SOLVE_CACHE.clear()


@needs_report
@pytest.mark.parametrize("model", ["razor-2p", "sinusoidal", "bspline"])
def test_reuse_off_reports_times_and_no_analysis(model):
    report = _solve(_req(YAGI, model, {"pair_reuse": False}))["fill_report"]
    assert report["reuse"] is None and report["map"] is None
    assert report["reuse_asked"] is False
    assert report["times"]["census_s"] == 0.0
    assert report["times"]["fill_s"] > 0.0
    assert report["fills"] == 1


def _served_engine(model):
    """A real Yagi, meshed past the size reuse declines under, solved once."""
    req = _req("beams.yagi", model, {"pair_reuse": True}, n_per_wire=81)
    builder = adapter._build_builder(adapter.REGISTRY["beams.yagi"].builder_cls, req)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        engine = adapter._make_momwire_engine(req, builder)
        engine.impedance()
    return engine


@needs_report
@pytest.mark.parametrize("model", ["razor-2p", "sinusoidal", "bspline"])
def test_the_payload_agrees_with_the_solver(model):
    """The served numbers are the solver's own, through each engine."""
    engine = _served_engine(model)
    raw = engine._solved_cache[1][0].fill_report()
    served = engine.fill_report()
    assert raw["reuse"]["state"] == "served", "this gate needs a served fill"
    assert served["reuse"]["state"] == "served"
    for key in ("pairs", "computed", "reused", "near", "kernel_evals"):
        assert served["reuse"][key] == raw["reuse"][key]
    assert served["reuse"]["families"] == raw["reuse"]["families"]
    assert served["times"]["census_s"] == raw["times"]["census_s"]
    grid = served["map"]
    wires = raw["reuse"]["wires"]
    assert len(wires["labels"]) <= fr.MAX_MAP_ROWS, "this gate needs an unbinned map"
    assert grid["computed"] == wires["computed"]
    assert grid["reused"] == wires["reused"]
    assert grid["near"] == wires["near"]


@needs_report
def test_reading_the_report_runs_no_census(monkeypatch):
    """Reads add no census. The counter is proved live first: sinusoidal's
    census goes through `timed_census`, so a count of zero could not pass here
    by the instrument having missed it."""
    calls = []
    real = momwire._fill_report.timed_census

    def counted(solver, build):
        calls.append(type(solver).__name__)
        return real(solver, build)

    monkeypatch.setattr(momwire._fill_report, "timed_census", counted)
    engine = _served_engine("sinusoidal")
    assert calls, "the census counter never fired, so it proves nothing"
    solver = engine._solved_cache[1][0]
    before = (len(calls), solver.fill_report(wires=False)["times"]["census_s"])
    for _ in range(3):
        engine.fill_report()
        solver.fill_report()
    after = (len(calls), solver.fill_report(wires=False)["times"]["census_s"])
    assert after == before


@needs_report
@pytest.mark.parametrize("model", ["razor-2p", "sinusoidal", "bspline"])
def test_reuse_off_never_reads_the_wire_map(model, monkeypatch):
    """With reuse off the tally asks momwire for no wire map at all."""
    req = _req(YAGI, model, {"pair_reuse": False})
    builder = adapter._build_builder(adapter.REGISTRY[YAGI].builder_cls, req)
    engine = adapter._make_momwire_engine(req, builder)
    asked = []
    cls = engine._solver
    real = cls.fill_report

    def spy(self, wires=True):
        asked.append(wires)
        return real(self, wires=wires)

    monkeypatch.setattr(cls, "fill_report", spy)
    engine.impedance()
    assert asked == [False]
    assert engine.fill_report()["times"]["census_s"] == 0.0


def test_the_report_does_not_move_the_answer():
    plain = MomwireEngine(
        adapter.REGISTRY[YAGI].builder_cls(), solver=momwire.BSplineSolver
    )
    z_plain = plain.impedance()
    read = MomwireEngine(
        adapter.REGISTRY[YAGI].builder_cls(), solver=momwire.BSplineSolver
    )
    z_read = read.impedance()
    read.fill_report()
    assert z_plain == z_read


@needs_report
def test_a_cached_answer_says_so():
    req = _req(YAGI, "bspline", {"pair_reuse": True})
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        first = server.solve(req)
        again = server.solve(req)
    assert first["fill_report"]["source"] == "fresh"
    assert again["cache_hit"] is True
    assert again["fill_report"]["source"] == "cached"
    assert again["fill_report"]["solved_at"] == first["fill_report"]["solved_at"]


@needs_report
def test_a_matrix_from_memory_reports_no_fill():
    req = _req("wire.edz", "bspline", {})
    assert _solve(req)["fill_report"]["no_fill"] is False
    again = _solve(req)["fill_report"]
    assert again["no_fill"] is True
    assert again["fills"] == 0 and again["route"] is None


@needs_report
def test_the_sector_route_reports_sectors_and_blocks():
    report = _solve(_screen())["fill_report"]
    assert report["route"] == "sector"
    sector = report["sector"]
    assert sector["n_sectors"] >= 2
    assert sector["blocks"] and all(b["count"] >= 1 for b in sector["blocks"])
    assert sector["computed_pairs"] < sector["pairs"]
    roles = {row["role"] for row in report["map"]["rows"]}
    assert roles == {"computed", "rotation"}


@needs_report
def test_a_refused_deck_reports_the_workbench_sentence():
    req = _req(YAGI, "bspline", {"rotational_symmetry": True})
    with pytest.raises(NotImplementedError) as caught:
        _solve(req)
    report = adapter.fill_refusal_of(caught.value)["fill_report"]
    assert report["source"] == "refused"
    assert "Untick 'rotational symmetry" in report["sector"]["declined"]
    assert "rotational_symmetry=True" not in report["sector"]["declined"]


@needs_report
def test_the_live_channel_carries_the_refusal_and_keeps_serving():
    """Through the real socket: the refusal arrives beside the error, and the
    next solve on the same socket still answers."""
    with TestClient(server.app) as client, client.websocket_connect("/ws") as ws:
        ws.send_json(
            {**_req(YAGI, "bspline", {"rotational_symmetry": True}), "_seq": 1}
        )
        refused = ws.receive_json()
        assert "error" in refused
        report = refused["fill_report"]
        assert report["source"] == "refused"
        assert report["sector"]["declined"] in refused["error"]
        ws.send_json({**_req(YAGI, "bspline", {}), "_seq": 2})
        solved = ws.receive_json()
        assert "error" not in solved
        assert solved["fill_report"]["source"] == "fresh"


def _sweep_closing(client, req):
    response = client.post("/sweep", json=req)
    assert response.status_code == 200
    return [json.loads(line) for line in response.text.splitlines()][-1]


@needs_report
def test_a_sweep_closes_with_its_totals():
    freqs = [28.0, 28.2, 28.4, 28.6]
    req = {**_req(YAGI, "bspline", {"pair_reuse": True}), "freqs_mhz": freqs}
    with TestClient(server.app) as client:
        done = _sweep_closing(client, req)
    assert done["done"] is True
    report = done["fill_report"]
    assert report["scope"] == "sweep"
    assert report["frequencies"] == len(freqs)
    assert report["points_cached"] == 0
    assert report["times"]["fill_s"] > 0.0
    assert report["reuse"]["state"] in ("served", "partial", "declined")


def test_any_other_error_is_no_refusal():
    assert adapter.fill_refusal_of(ValueError("no")) == {}


def test_a_sweep_adds_its_chunks_and_keeps_the_last_fill():
    def chunk(fill_s, route):
        return {
            "version": 1,
            "scope": "solve",
            "source": "fresh",
            "solved_at": fill_s,
            "solver": "S",
            "fills": 1,
            "frequencies": 2,
            "times": {"fill_s": fill_s, "factor_s": 1.0, "census_s": 0.0},
            "no_fill": False,
            "points_cached": 0,
            "route": route,
            "reuse_asked": False,
            "reuse": None,
            "sector": None,
            "map": None,
        }

    total = fr.merge_sweep(None, chunk(1.0, "dense"))
    total = fr.merge_sweep(total, chunk(2.0, "sector"))
    assert total["scope"] == "sweep"
    assert total["fills"] == 2 and total["frequencies"] == 4
    assert total["times"]["fill_s"] == 3.0
    assert total["route"] == "sector"


def test_a_sweep_chunk_is_still_the_tuple_it_was():
    chunk = adapter.SweepChunk(([1.0], [2.0]), {"fills": 1})
    z_re, z_im = chunk
    assert (z_re, z_im) == ([1.0], [2.0]) and len(chunk) == 2
    assert chunk.fill_report == {"fills": 1}


def _worst_wires(n):
    grid = np.full((n, n), 123_456, dtype=np.int64).tolist()
    return {
        "labels": list(range(n)),
        "pairs": grid,
        "computed": grid,
        "reused": grid,
        "near": grid,
    }


def test_the_map_is_bounded_and_keeps_its_counts():
    n = fr.MAX_MAP_WIRES
    names = [f"wire {i + 1}" for i in range(n)]
    mapped = fr._pack_map(
        {"sector": None, "reuse": {"wires": _worst_wires(n)}}, names, [9] * n
    )
    assert len(mapped["rows"]) == fr.MAX_MAP_ROWS
    assert sum(row["wires"] for row in mapped["rows"]) == n
    assert sum(row["segments"] for row in mapped["rows"]) == 9 * n
    assert np.sum(mapped["computed"]) == 123_456 * n * n


def test_the_payload_stays_small_at_the_hosted_cap():
    """3000 segments, as many wires as the map will read, every count large."""
    n = fr.MAX_MAP_WIRES
    names = [f"a long wire name {i}" for i in range(n)]
    mapped = fr._pack_map(
        {"sector": None, "reuse": {"wires": _worst_wires(n)}}, names, [8] * n
    )
    assert len(json.dumps(mapped)) < 48 * 1024


def test_a_screen_of_many_wires_groups_by_sector():
    wire_sector = [-1] + [s for s in range(150) for _ in range(2)]
    n = len(wire_sector)
    mapped = fr._sector_map(wire_sector, [f"wire {i}" for i in range(n)], [5] * n)
    rows = mapped["rows"]
    assert len(rows) <= fr.MAX_MAP_ROWS
    assert sum(row["wires"] for row in rows) == n
    assert rows[0]["label"] == "axis" and rows[0]["role"] == "computed"
    assert rows[1]["label"] == "sector 1" and rows[1]["role"] == "computed"
    assert all(row["role"] == "rotation" for row in rows[2:])


def test_wire_names_come_from_the_design_or_its_number():
    polylines = [
        np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [2.0, 0.0, 0.0]]),
        np.array([[0.0, 1.0, 0.0], [1.0, 1.0, 0.0]]),
        np.array([[0.0, 2.0, 0.0], [1.0, 2.0, 0.0]]),
    ]
    authored = [
        ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), "driver", None),
        ((1.0, 0.0, 0.0), (2.0, 0.0, 0.0), "driver", None),
        ((1.0, 1.0, 0.0), (0.0, 1.0, 0.0), None, 7),
    ]
    assert fr.polyline_names(polylines, authored) == ["driver", "tag 7", "wire 3"]


@pytest.mark.skipif(HAVE_REPORT, reason="this momwire reports its fill")
def test_at_the_recorded_pointer_nothing_is_sent():
    """momwire 0.94.0: no report on a solve, a sweep's closing record or a
    refusal, and the Fill view reads that the engine does not report."""
    out = _solve(_req(YAGI, "bspline", {"pair_reuse": True}))
    assert "fill_report" not in out
    with TestClient(server.app) as client:
        done = _sweep_closing(
            client, {**_req(YAGI, "bspline", {}), "freqs_mhz": [28.0, 28.4]}
        )
    assert done["done"] is True and "fill_report" not in done
    assert (
        MomwireEngine(
            adapter.REGISTRY[YAGI].builder_cls(), solver=momwire.BSplineSolver
        ).fill_report()
        is None
    )


def test_a_momwire_without_the_report_sends_none():
    class Older:
        pass

    assert fr.reads_fill_report(Older) is False
    assert fr.FillTally().payload(reuse_asked=False) is None


@pytest.mark.parametrize("solver", ["pynec"])
def test_another_engine_sends_no_report(solver):
    pytest.importorskip("PyNEC")
    out = _solve({"geometry": YAGI, "solver": solver})
    assert "fill_report" not in out


def test_an_unnamed_solved_wire_reads_by_the_design_wires_it_holds():
    """The walk solves a run of wires joined end to end as one wire, so a
    Sterba curtain's 20 wires solve as 2. The map's rows read by the design's
    wire numbers they hold, not "wire 1" / "wire 2", which read as if the
    design had two wires."""
    polylines = [
        np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [2.0, 0.0, 0.0], [3.0, 0.0, 0.0]]),
        np.array([[0.0, 1.0, 0.0], [1.0, 1.0, 0.0]]),
    ]
    authored = [
        ((0.0, 1.0, 0.0), (1.0, 1.0, 0.0), None, None),
        ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), None, None),
        ((2.0, 0.0, 0.0), (1.0, 0.0, 0.0), None, None),
        ((2.0, 0.0, 0.0), (3.0, 0.0, 0.0), None, None),
    ]
    assert fr.polyline_names(polylines, authored) == ["wires 2–4", "wire 1"]
    assert fr._wire_numbers([9, 2, 3, 4, 11, 12]) == "wires 2–4, 9, 11–12"


def test_the_sterba_curtain_names_its_design_wires():
    """`wire.sterba` itself: 20 design wires, solved as 2. Built only, no
    solve: the names come from the walk and the design."""
    from antennaknobs.cli import get_builder

    eng = MomwireEngine(get_builder("wire.sterba")())
    names = fr.polyline_names(eng._polylines, eng._fill_authored)
    # Wire 15 is solved on its own; the other 19 are one solved wire.
    assert names == ["wire 15", "wires 1–14, 16–20"]

"""AK#1901: optimise one design across several frequencies at once.

Stub engines pin the algorithms (each eval one build solved at every band,
the root form's honest verdicts, the minimax's reported terms); the workbench
path is driven through ``POST /optimize`` on the two-band fan and on a small
synthetic deck whose SY constants are the knobs (UR0GT's deck, Dan's real
case, is a third-party file and lives in the slow lane, skipped without it).
"""

from __future__ import annotations

import json
import math

import numpy as np
import pytest
from fastapi.testclient import TestClient

from antennaknobs.web import server
from antennaknobs.web.optimize import DegenerateObjective, optimize
from antennaknobs.web.optimize_bands import (
    DEFAULT_MEAN_WEIGHT,
    BandsRefused,
    objective_terms,
    optimize_bands,
    parse_bands,
)

# --- parsing ---------------------------------------------------------------


def test_cli_string_defaults_to_swr_at_feed_0():
    bands = parse_bands("7.1,3.6:res,1.83:z0:feed=1:z0=75:knobs=a+b")
    assert [b.freq_mhz for b in bands] == [7.1, 3.6, 1.83]
    assert [b.objective for b in bands] == ["swr", "resonance", "match_z0"]
    assert [b.feed for b in bands] == [0, 0, 1]
    assert bands[2].z0 == 75.0
    assert bands[2].knobs == ("a", "b")


def test_json_form_is_the_request_shape():
    spec = [{"freq": 24.97, "objective": "resonance", "knobs": ["bands.0.length"]}]
    assert parse_bands(json.dumps(spec)) == parse_bands(spec)


@pytest.mark.parametrize(
    "spec, words",
    [
        ("0", "positive"),
        ("7.1:wiggle", "unknown objective"),
        ("7.1:feed=-1", "feed"),
        ("7.1,7.1", "repeats band 0"),
        (",".join(["7"] * 1) + "," + ",".join(str(f) for f in range(8, 16)), "at most"),
        ([{"freq": 7.1, "colour": "red"}], "unknown field"),
        ([], "non-empty"),
    ],
)
def test_malformed_bands_are_refused_by_name(spec, words):
    with pytest.raises(BandsRefused, match=words):
        parse_bands(spec)


# --- the algorithms, on stub engines --------------------------------------


class LinearStub:
    """Z_b = R_b + j (A x - c)_b: a band's X is linear in the knobs, so the
    root is A^-1 c. X also rises 50 ohm/MHz through each band (a SERIES
    resonance), read at the nearest band for a frequency beside one. Records
    every sweep_fn call (the request, the freqs)."""

    def __init__(self, A, c, freqs, R=50.0, feeds=1):
        self.A = np.asarray(A, float)
        self.c = np.asarray(c, float)
        self.freqs = list(freqs)
        self.R = R
        self.feeds = feeds
        self.calls: list[tuple[dict, list[float]]] = []

    def x_of(self, req):
        return np.array([req["k"][i] for i in range(self.A.shape[1])])

    def __call__(self, req, freqs):
        self.calls.append((req, list(freqs)))
        X = self.A @ self.x_of(req) - self.c
        rows = []
        for f in freqs:
            b = int(np.argmin([abs(f - fb) for fb in self.freqs]))
            x = X[b] + 50.0 * (f - self.freqs[b])
            rows.append([complex(self.R, x)] * self.feeds)
        return {"zs": np.array(rows), "z0_ohms": 50.0}


def _free(n, lo=-10.0, hi=10.0):
    return [{"name": f"k.{i}", "min": lo, "max": hi} for i in range(n)]


def test_root_finds_the_root_and_every_eval_is_one_build_at_every_band():
    A = [[3.0, 1.0, 0.0], [1.0, 4.0, 1.0], [0.0, 1.0, 5.0]]
    stub = LinearStub(A, [1.0, 2.0, 3.0], [1.8, 3.6, 7.1])
    bands = parse_bands("1.8:res,3.6:res,7.1:res")
    res = optimize_bands(
        {"k": [0.0, 0.0, 0.0], "measurement_freq_mhz": 7.0},
        _free(3),
        bands,
        sweep_fn=stub,
        mode="root",
    )
    assert res["root_status"] == "root" and res["converged"]
    want = np.linalg.solve(np.array(A), [1.0, 2.0, 3.0])
    got = [res["params"][f"k.{i}"] for i in range(3)]
    assert got == pytest.approx(want, abs=1e-6)
    assert res["residual_after"] < 1e-3
    for req, freqs in stub.calls:
        # One build per call, every band's frequency (or a slope check's
        # pair either side of each resonance band) -- never one band alone.
        assert len(freqs) in (3, 6)
        # The request's measurement frequency is never moved to reach a band.
        assert req["measurement_freq_mhz"] == 7.0


def test_a_root_outside_the_box_is_reported_as_none_not_a_near_miss():
    # The root is at x = 20, the box stops at 10.
    stub = LinearStub([[1.0]], [20.0], [7.1])
    res = optimize_bands(
        {"k": [0.0]}, _free(1), parse_bands("7.1:res"), sweep_fn=stub, mode="root"
    )
    assert not res["converged"]
    assert res["root_status"] == "no root in the box"
    assert res["residual_after"] > 1.0


def test_a_range_that_excludes_the_start_is_refused_with_its_unit_1909():
    # AK#1909: a pF capacitor bounded in farads used to be clipped into the
    # range (an open circuit) and "optimised".
    stub = LinearStub([[1.0]], [1.0], [7.1])
    with pytest.raises(BandsRefused) as e:
        optimize_bands(
            {"k": [340.0]},
            [{"name": "k.0", "min": 100e-12, "max": 1000e-12}],
            parse_bands("7.1:res"),
            sweep_fn=stub,
            knob_units={"k.0": "pF"},
        )
    words = str(e.value)
    assert "k.0 = 340 pF is outside its range 1e-10..1e-09" in words
    assert "1e12 times the range" in words
    assert stub.calls == []


def test_a_knob_pinned_at_its_range_is_named_1909():
    # The root is at x = 20, the box stops at 10: the answer sits on the max.
    stub = LinearStub([[1.0]], [20.0], [7.1])
    res = optimize_bands(
        {"k": [0.0]}, _free(1), parse_bands("7.1:res"), sweep_fn=stub, mode="root"
    )
    assert res["at_bound"] == [{"name": "k.0", "bound": "max", "value": 10.0}]
    assert res["stopped"] is None and res["time_budget_s"] is None
    assert not res["far_from_match"]


def test_no_band_near_a_match_is_said_plainly_1909():
    # R = 1e5 ohm on a 50 ohm line: SWR 2000 wherever the knob goes.
    stub = LinearStub([[1.0]], [0.0], [7.1], R=1e5)
    res = optimize_bands({"k": [3.0]}, _free(1), parse_bands("7.1"), sweep_fn=stub)
    assert res["worst_swr_after"] > 100
    assert res["far_from_match"]


class _SlowStub(LinearStub):
    def __call__(self, req, freqs):
        import time

        time.sleep(0.05)
        return super().__call__(req, freqs)


@pytest.mark.parametrize("mode", ["minimax", "root"])
def test_the_time_budget_answers_with_the_best_point_so_far(mode):
    A = [[3.0, 1.0], [1.0, 4.0]]
    stub = _SlowStub(A, [1.0, 2.0], [3.6, 7.1])
    spec = "3.6:res,7.1:res" if mode == "root" else "3.6,7.1"
    res = optimize_bands(
        {"k": [-9.0, 9.0]},
        _free(2),
        parse_bands(spec),
        sweep_fn=stub,
        mode=mode,
        time_budget_s=0.12,
    )
    assert res["stopped"] == "time" and res["time_budget_s"] == 0.12
    assert not res["converged"]
    if mode == "root":
        assert res["root_status"] == "out of time"
    # Stopped well short of the eval budget: 3 fresh solves start inside 0.12 s,
    # plus the answer's own read-back and checks once the budget is spent.
    assert res["n_fresh"] < 20
    # The answer is a point the run solved, never worse than the start.
    assert res["objective_after"] <= res["objective_before"]


def test_a_knob_that_moves_nothing_is_singular_by_name():
    stub = LinearStub([[1.0, 0.0], [2.0, 0.0]], [1.0, 1.0], [3.6, 7.1])
    res = optimize_bands(
        {"k": [0.0, 0.0]},
        _free(2),
        parse_bands("3.6:res,7.1:res"),
        sweep_fn=stub,
        mode="root",
    )
    assert res["root_status"] == "singular" and not res["converged"]
    assert "k.1" in res["root_reason"]


def test_root_mode_needs_a_square_system():
    stub = LinearStub([[1.0], [2.0]], [1.0, 1.0], [3.6, 7.1])
    with pytest.raises(BandsRefused, match="as many equations as knobs"):
        optimize_bands(
            {"k": [0.0]},
            _free(1),
            parse_bands("3.6:res,7.1:res"),
            sweep_fn=stub,
            mode="root",
        )


def test_an_unknown_feed_is_refused_by_name():
    stub = LinearStub([[1.0]], [0.0], [7.1], feeds=2)
    with pytest.raises(BandsRefused, match="feed 2.*2 feeds"):
        optimize_bands({"k": [0.0]}, _free(1), parse_bands("7.1:feed=2"), sweep_fn=stub)


def test_a_tuner_holding_a_band_is_degenerate():
    def sweep(req, freqs):
        held = {"name": "T1", "f_mhz": 7.1}
        return {
            "zs": np.full((len(freqs), 1), 50 + 0j),
            "tuner": [held if f == 7.1 else None for f in freqs],
        }

    with pytest.raises(DegenerateObjective, match="tuner T1"):
        optimize_bands({"k": [0.0]}, _free(1), parse_bands("3.6,7.1"), sweep_fn=sweep)


def test_swr_and_ohm_bands_do_not_share_a_run():
    stub = LinearStub([[1.0], [1.0]], [0.0, 0.0], [3.6, 7.1])
    with pytest.raises(BandsRefused, match="one unit"):
        optimize_bands(
            {"k": [0.0]}, _free(1), parse_bands("3.6:res,7.1"), sweep_fn=stub
        )


def _quadratic_swr_stub():
    """Two bands, one shared knob: band 0 is matched at x = -1, band 1 at
    x = +2, so no x matches both and the minimax is a compromise."""

    def sweep(req, freqs):
        x = req["k"][0]
        rows = []
        for f in freqs:
            centre = -1.0 if f == 3.6 else 2.0
            rows.append([complex(50.0 + 15.0 * (x - centre) ** 2, 0.0)])
        return {"zs": np.array(rows), "z0_ohms": 50.0}

    return sweep


@pytest.mark.parametrize("w", [0.0, 0.2, DEFAULT_MEAN_WEIGHT, 0.8])
def test_minimax_reports_the_worst_band_it_actually_read(w):
    res = optimize_bands(
        {"k": [0.5]},
        _free(1, -5.0, 5.0),
        parse_bands("3.6,7.1"),
        sweep_fn=_quadratic_swr_stub(),
        mean_weight=w,
    )
    per = [b["swr"] for b in res["bands_after"]]
    # No cherry-picking: the worst-band SWR IS the max of the bands read.
    assert res["worst_swr_after"] == max(per)
    assert res["objective_worst_after"] == max(per)
    assert res["objective_mean_after"] == pytest.approx(sum(per) / len(per))
    J, mx, mn = objective_terms(res["bands_after"], w)
    assert res["objective_after"] == pytest.approx(J)
    assert res["mean_weight"] == w
    # The symmetric compromise sits midway between the two matches.
    assert res["params"]["k.0"] == pytest.approx(0.5, abs=2e-2)


def test_the_default_form_is_the_swr_minimax():
    res = optimize_bands(
        {"k": [0.0]},
        _free(1, -5.0, 5.0),
        parse_bands("3.6,7.1"),
        sweep_fn=_quadratic_swr_stub(),
    )
    assert res["form"] == "minimax"
    assert res["unit"] == "swr"
    assert res["mean_weight"] == DEFAULT_MEAN_WEIGHT == 0.5
    assert res["root_status"] is None


def test_an_unreadable_band_serialises_as_valid_json():
    """A band the engine cannot read (Z NaN, SWR inf) goes out as null, never
    a bare Infinity / NaN a browser's JSON.parse rejects."""

    def sweep(req, freqs):
        x = req["k"][0]
        rows = []
        for f in freqs:
            if f == 7.1 and x != 0.0:  # readable only at the start
                rows.append([complex(math.nan, math.nan)])
            else:
                rows.append([complex(50.0 + 20.0 * (x - 1.0) ** 2, 0.0)])
        return {"zs": np.array(rows), "z0_ohms": 50.0}

    frames = []
    res = optimize_bands(
        {"k": [0.0]},
        _free(1, -2.0, 2.0),
        parse_bands("3.6,7.1"),
        sweep_fn=sweep,
        on_progress=frames.append,
    )
    for payload in [*frames, res]:
        json.loads(json.dumps(payload, allow_nan=False))
    unread = [b for f in frames for b in f["bands"] if b["swr"] is None]
    assert unread and all(b["z_re"] is None for b in unread)


def test_result_band_records_carry_their_index():
    res = optimize_bands(
        {"k": [0.5]},
        _free(1, -5.0, 5.0),
        parse_bands("3.6,7.1"),
        sweep_fn=_quadratic_swr_stub(),
    )
    for key in ("bands_before", "bands_after"):
        assert [b["index"] for b in res[key]] == [0, 1]
        assert [b["freq_mhz"] for b in res[key]] == [3.6, 7.1]


def test_sequential_tunes_each_band_by_its_own_knob():
    A = [[4.0, 0.5], [0.3, 3.0]]
    stub = LinearStub(A, [2.0, -1.0], [3.6, 7.1])
    res = optimize_bands(
        {"k": [0.0, 0.0]},
        _free(2),
        parse_bands("3.6:res:knobs=k.0,7.1:res:knobs=k.1"),
        sweep_fn=stub,
        mode="sequential",
    )
    assert res["converged"] and res["residual_after"] < 0.5
    assert res["passes"] >= 1


def test_sequential_needs_every_knob_owned_once():
    stub = LinearStub([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]], [0.0, 0.0], [3.6, 7.1])
    with pytest.raises(BandsRefused, match="k.2 is free but no band tunes it"):
        optimize_bands(
            {"k": [0.0, 0.0, 0.0]},
            _free(3),
            parse_bands("3.6:res:knobs=k.0,7.1:res:knobs=k.1"),
            sweep_fn=stub,
            mode="sequential",
        )
    with pytest.raises(BandsRefused, match="names none"):
        optimize_bands(
            {"k": [0.0, 0.0]},
            _free(2),
            parse_bands("3.6:res:knobs=k.0+k.1,7.1:res"),
            sweep_fn=stub,
            mode="sequential",
        )


def test_x_equals_zero_at_a_parallel_resonance_is_not_a_root():
    """X falls through zero with frequency at a parallel resonance: the root
    form must not call that a root."""

    def sweep(req, freqs):
        x = req["k"][0]
        # X(f) = -(f - f0) * 100 + 10 * x: zero at x = 0 for f = f0, with a
        # NEGATIVE slope in frequency (the parallel-resonance signature).
        rows = [[complex(3000.0, -(f - 7.1) * 100.0 + 10.0 * x)] for f in freqs]
        return {"zs": np.array(rows), "z0_ohms": 50.0}

    res = optimize_bands(
        {"k": [3.0]}, _free(1), parse_bands("7.1:res"), sweep_fn=sweep, mode="root"
    )
    assert res["antiresonant_bands"] == [0]
    assert res["root_status"] == "parallel resonance" and not res["converged"]


# --- the single-band path: a dotted group leaf is a knob (#1901) ----------


def test_single_band_optimize_varies_a_group_leaf_without_touching_the_request():
    seen = []

    def solve(req):
        seen.append(req)
        length = req["bands"][1]["length"]
        return {"z_in_re": 50.0, "z_in_im": 400.0 * (length - 5.0), "z0_ohms": 50.0}

    base = {"bands": [{"length": 6.0}, {"length": 5.2}]}
    res = optimize(
        base,
        [{"name": "bands.1.length", "min": 4.0, "max": 6.0}],
        "resonance",
        solve_fn=solve,
    )
    assert res["params"]["bands.1.length"] == pytest.approx(5.0, abs=1e-4)
    assert base == {"bands": [{"length": 6.0}, {"length": 5.2}]}
    assert all(r["bands"][0]["length"] == 6.0 for r in seen)
    assert "bands.1.length" not in seen[-1]


# --- the workbench: POST /optimize with a band list ------------------------

_FAN = "multiband.twoband_fan_dipole"


def _fan_body(**opt) -> dict:
    v = server.EXAMPLES[_FAN].builder_cls.current_physical_params
    bands = [dict(b) for b in v["bands"]]
    bands[0]["length"] *= 1.05
    bands[1]["length"] *= 0.95
    return {
        "geometry": _FAN,
        "variant": "current_physical",
        "bands": bands,
        "optimize": opt,
    }


_LENGTHS = [
    {"name": "bands.0.length", "min": 3.0, "max": 7.0},
    {"name": "bands.1.length", "min": 3.0, "max": 7.0},
]


def test_two_band_fan_root_through_the_workbench():
    """Gate 1, fast: the two band lengths to resonance at both of
    current_physical's frequencies, from +5 % / -5 % off the variant."""
    body = _fan_body(
        free=_LENGTHS,
        bands=[
            {"freq": 26.6, "objective": "resonance"},
            {"freq": 29.3, "objective": "resonance"},
        ],
        mode="root",
    )
    out = TestClient(server.app).post("/optimize", json=body).json()
    assert "error" not in out, out
    assert out["root_status"] == "root" and out["converged"]
    assert all(abs(b["z_im"]) < 0.5 for b in out["bands_after"])
    assert out["n_fresh"] <= 30
    assert out["solver"] == "momwire"
    # The variant's own lengths, give or take: the root is the one nearby.
    assert out["params"]["bands.0.length"] == pytest.approx(5.494, abs=0.05)
    assert out["params"]["bands.1.length"] == pytest.approx(5.0517, abs=0.05)


def test_one_shared_knob_minimax_through_the_workbench_streams_every_band():
    """Gate 5, fast: one knob (the feed split) for two SWR bands. The worst
    SWR reported is the max of the per-band SWRs read, and every progress
    frame carries each band's Z and SWR."""
    body = _fan_body(
        free=[{"name": "s", "min": 0.05, "max": 0.8}],
        bands=[{"freq": 26.6}, {"freq": 29.3}],
    )
    body["s"] = 0.4
    text = (
        TestClient(server.app)
        .post("/optimize", json=body, headers={"Accept": "text/event-stream"})
        .text
    )
    frames = [f for f in text.split("\n\n") if f.strip()]
    kinds = [f.split("\n", 1)[0] for f in frames]
    assert kinds[-1] == "event: result"
    out = json.loads(frames[-1].split("data: ", 1)[1])
    per = [b["swr"] for b in out["bands_after"]]
    assert out["worst_swr_after"] == max(per)
    assert out["worst_swr_after"] < out["worst_swr_before"]
    progress = [
        json.loads(f.split("data: ", 1)[1])
        for f in frames
        if f.startswith("event: progress")
    ]
    assert progress and all(
        {"freq_mhz", "z_re", "z_im", "swr"} <= set(b)
        for p in progress
        for b in p["bands"]
    )


@pytest.mark.parametrize(
    "opt, words",
    [
        (
            {"free": _LENGTHS, "bands": [{"freq": 26.6, "feed": 3}]},
            "feed 3",
        ),
        (
            {"free": [{"name": "nope", "min": 0, "max": 1}], "bands": [{"freq": 26.6}]},
            "unknown knob 'nope'",
        ),
        ({"free": _LENGTHS, "bands": [{"freq": -1}]}, "positive"),
        ({"free": _LENGTHS, "bands": [{"freq": 26.6}], "mode": "auto"}, "mode"),
        (
            {"free": _LENGTHS, "bands": [{"freq": 26.6}], "mean_weight": 2},
            "mean_weight",
        ),
    ],
)
def test_workbench_refusals_are_by_name(opt, words):
    out = TestClient(server.app).post("/optimize", json=_fan_body(**opt)).json()
    assert words in out.get("error", ""), out


def test_a_group_the_request_leaves_out_is_seeded_from_the_design():
    body = _fan_body(
        free=_LENGTHS,
        bands=[{"freq": 26.6, "objective": "res"}, {"freq": 29.3, "objective": "res"}],
        mode="root",
        max_evals=1,
    )
    del body["bands"]
    out = TestClient(server.app).post("/optimize", json=body).json()
    assert "error" not in out, out
    v = server.EXAMPLES[_FAN].builder_cls.current_physical_params
    assert out["params_before"]["bands.0.length"] == v["bands"][0]["length"]


@pytest.fixture()
def fresh_decks(monkeypatch):
    """A clean deck store, and every opened deck unregistered afterwards:
    `server.EXAMPLES` is module-global, and a deck left in it shows up in
    every later test that reads the catalog (as test_opened_decks does)."""
    from antennaknobs.web import decks

    st = server._DECK_SETTINGS
    monkeypatch.setattr(server, "_DECK_OPENS", decks.RateLimiter(st.opens_per_min))
    monkeypatch.setattr(server, "_DECK_GATE", decks.DeckGate(st))
    store = decks.DeckStore(st, server._register_deck, server._unregister_deck)
    monkeypatch.setattr(server, "_DECK_STORE", store)
    yield store
    for key in list(server.EXAMPLES):
        if decks.is_deck(key):
            del server.EXAMPLES[key]


# A small two-band fan as a NEC deck: its SY constants are the knobs, read
# by the opened-deck path (`POST /deck`), never by editing the deck's text.
SYNTHETIC_DECK = """CM synthetic two-band fan dipole with SY knobs (AK#1901)
CE
SY L1 = 10.2
SY L2 = 6.6
GW 1 1 0 -.01 10 0 .01 10 .001
GW 2 9 0 .01 10 0 L1/2 10 .001
GW 3 9 0 -.01 10 0 -L1/2 10 .001
GW 4 7 0 .01 10 0 L2/2 9 .001
GW 5 7 0 -.01 10 0 -L2/2 9 .001
GE 0
EX 0 1 1 0 1 0
FR 0 1 0 0 14.1
EN
"""


def test_an_opened_decks_sy_knobs_are_the_free_knobs(fresh_decks):
    c = TestClient(server.app)
    key = c.post("/deck", json={"name": "syn.nec", "text": SYNTHETIC_DECK}).json()[
        "key"
    ]
    out = c.post(
        "/optimize",
        json={
            "geometry": key,
            "optimize": {
                "free": [
                    {"name": "sy_l1", "min": 8.0, "max": 12.0},
                    {"name": "sy_l2", "min": 5.0, "max": 8.0},
                ],
                "bands": [
                    {"freq": 14.1, "objective": "resonance"},
                    {"freq": 21.2, "objective": "resonance"},
                ],
                "mode": "root",
            },
        },
    ).json()
    assert "error" not in out, out
    # Started at the deck's own SY values, not mid-range.
    assert out["params_before"] == {"sy_l1": 10.2, "sy_l2": 6.6}
    assert out["root_status"] == "root"
    assert all(abs(b["z_im"]) < 0.5 for b in out["bands_after"])


# --- the command line -----------------------------------------------------


def test_cli_optimize_bands_root_on_the_two_band_fan(capsys):
    """`optimize --bands` on a builder: one engine per eval, every band."""
    import antennaknobs as ant

    ant.cli(
        [
            "optimize",
            "--builder",
            "multiband.twoband_fan_dipole:current_physical",
            "--engine",
            "momwire",
            "--bands",
            "26.6:res,29.3:res",
            "--mode",
            "root",
            "--params",
            "bands.0.length",
            "bands.1.length",
            "--bound",
            "bands.0.length=5.2:5.8",
        ]
    )
    out = capsys.readouterr().out
    assert "root: root" in out, out
    assert "current_physical_params" in out
    import re

    lengths = [float(v) for v in re.findall(r"'length': ([0-9.]+)", out)]
    assert lengths == pytest.approx([5.50, 5.05], abs=0.03)


def test_cli_bounds_parse_and_refuse_by_name():
    from antennaknobs.band_opt import parse_bounds

    assert parse_bounds(["a=1:2", "b.0.c=-1:3.5"]) == {
        "a": (1.0, 2.0),
        "b.0.c": (-1.0, 3.5),
    }
    for bad in ("a=2:1", "a1:2", "a=1"):
        with pytest.raises(ValueError, match="NAME=LO:HI"):
            parse_bounds([bad])


def test_cli_free_reads_a_group_leafs_ui_range():
    from antennaknobs.band_opt import free_for
    from antennaknobs.designs.multiband.fandipole import Builder

    free = free_for(Builder(), ["bands.2.length_factor"])
    assert free == [{"name": "bands.2.length_factor", "min": 0.40, "max": 0.55}]

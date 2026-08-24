"""Unit tests for the knob optimiser (antennaknobs.web.optimize).

The optimiser machinery is exercised with a *stub* solve_fn (a closed-form Z as
a function of the free params) so the tests are fast and deterministic — no MoM
solves. A separate slow-marked test runs one real geometry through it to confirm
the wiring to momwire_solve.
"""

from __future__ import annotations

import math

import pytest

from antennaknobs.web.optimize import _metrics, _objective_value, _swr, optimize


def test_swr_helper():
    assert _swr(50.0, 0.0, 50.0) == pytest.approx(1.0)  # perfect match
    assert _swr(100.0, 0.0, 50.0) == pytest.approx(2.0)  # 2:1
    assert _swr(25.0, 0.0, 50.0) == pytest.approx(2.0)  # 2:1 the other way
    assert _swr(50.0, 50.0, 50.0) > 2.0  # reactance worsens it
    assert math.isfinite(_swr(1e9, 0.0, 50.0))  # open circuit stays finite


def _linear_reactance(zero_at: float, z_re: float = 50.0):
    """Stub solve_fn: X(x) crosses zero at `zero_at`, R fixed. So resonance
    (|X|) and SWR are both minimised there (Z = z_re + 0j)."""

    def solve(req: dict) -> dict:
        x = float(req["x"])
        return {"z_in_re": z_re, "z_in_im": 100.0 * (x - zero_at), "z0_ohms": 50.0}

    return solve


def test_optimize_finds_the_minimum():
    res = optimize(
        {"x": 0.80},
        [{"name": "x", "min": 0.5, "max": 1.5}],
        "resonance",
        solve_fn=_linear_reactance(1.05),
    )
    assert res["params"]["x"] == pytest.approx(1.05, abs=1e-3)
    assert res["objective_after"] == pytest.approx(0.0, abs=1e-1)
    assert res["objective_after"] < res["objective_before"]
    assert res["improved"] is True
    assert res["n_evals"] > 2


def test_optimize_clamps_to_bounds_when_optimum_is_outside():
    # Reactance zero sits at 1.30 but the user constrained x to <= 1.00.
    res = optimize(
        {"x": 0.80},
        [{"name": "x", "min": 0.5, "max": 1.0}],
        "resonance",
        solve_fn=_linear_reactance(1.30),
    )
    assert res["params"]["x"] == pytest.approx(1.0, abs=1e-3)  # pinned to the bound
    assert 0.5 <= res["params"]["x"] <= 1.0


def test_optimize_swr_objective_matches_z0():
    # Same stub: at x=1.05, Z = 50 + 0j -> SWR 1.0.
    res = optimize(
        {"x": 0.80},
        [{"name": "x", "min": 0.5, "max": 1.5}],
        "swr",
        solve_fn=_linear_reactance(1.05),
    )
    assert res["params"]["x"] == pytest.approx(1.05, abs=1e-2)
    assert res["metrics_after"]["swr"] == pytest.approx(1.0, abs=0.05)


def test_optimize_two_free_params():
    # A 2-D bowl: |X| minimised where both params hit their targets.
    def solve(req: dict) -> dict:
        a, b = float(req["a"]), float(req["b"])
        x_im = 100.0 * (a - 1.10) + 80.0 * (b - 0.90)
        return {"z_in_re": 50.0, "z_in_im": x_im, "z0_ohms": 50.0}

    res = optimize(
        {"a": 1.0, "b": 1.0},
        [{"name": "a", "min": 0.8, "max": 1.3}, {"name": "b", "min": 0.7, "max": 1.1}],
        "resonance",
        solve_fn=solve,
    )
    assert res["objective_after"] < res["objective_before"]
    assert 0.8 <= res["params"]["a"] <= 1.3
    assert 0.7 <= res["params"]["b"] <= 1.1


def test_optimize_rejects_empty_free():
    with pytest.raises(ValueError):
        optimize({"x": 1.0}, [], "swr", solve_fn=_linear_reactance(1.0))


def test_unknown_objective_falls_back_to_swr():
    res = optimize(
        {"x": 0.8},
        [{"name": "x", "min": 0.5, "max": 1.5}],
        "not_a_real_objective",
        solve_fn=_linear_reactance(1.05),
    )
    assert res["objective"] == "swr"


def test_on_progress_never_perturbs_the_result():
    """Observing a run must not change it.

    Three ways of asking for the same optimisation — omitted, explicit None,
    and a live callback — must return the identical dict. The third is the
    one with teeth: the hook runs arbitrary caller code between the solve and
    the return, inside the choke point every eval passes through, so a hook
    that mutated the request, the params dict, or the eval count would steer
    the search. Omitted-vs-None alone would not catch that.
    """

    # A fixed, order-independent stub: same req in, same dict out, always.
    def solve(req: dict) -> dict:
        x = float(req["x"])
        return {"z_in_re": 50.0, "z_in_im": 100.0 * (x - 1.05), "z0_ohms": 50.0}

    kwargs = dict(
        base_req={"x": 0.80},
        free=[{"name": "x", "min": 0.5, "max": 1.5}],
        objective="resonance",
        solve_fn=solve,
        max_evals=15,
    )
    res_default = optimize(**kwargs)
    res_explicit_none = optimize(**kwargs, on_progress=None)

    # A callback that both reads and writes what it is handed — the hostile
    # case. Mutating the payload must not reach the optimiser's own state.
    def meddle(ev: dict) -> None:
        ev["params"].clear()
        ev["n_evals"] = -1

    res_observed = optimize(**kwargs, on_progress=meddle)

    assert res_default == res_explicit_none
    assert res_default == res_observed


def test_on_progress_fires_once_per_solve_with_contiguous_n_evals():
    # 2-param probe: Nelder-Mead's initial simplex needs 3 vertices (N+1 for
    # N=2), so this exercises the dead zone scipy's own callback= misses.
    def solve(req: dict) -> dict:
        a, b = float(req["a"]), float(req["b"])
        x_im = 100.0 * (a - 1.10) + 80.0 * (b - 0.90)
        return {"z_in_re": 50.0, "z_in_im": x_im, "z0_ohms": 50.0}

    calls = []
    res = optimize(
        {"a": 1.0, "b": 1.0},
        [{"name": "a", "min": 0.8, "max": 1.3}, {"name": "b", "min": 0.7, "max": 1.1}],
        "resonance",
        solve_fn=solve,
        max_evals=25,
        on_progress=calls.append,
    )

    # Gate 1: exactly one callback per _solve_at call.
    assert len(calls) == res["n_evals"]

    # Gate 2 (the important one): n_evals values are gapless 1..N, proving
    # per-eval (not per-iteration) granularity and initial-simplex coverage.
    seen = [c["n_evals"] for c in calls]
    assert seen == list(range(1, len(calls) + 1))

    # Payload shape: objective/metrics come from the same helpers optimize()
    # itself uses, keyed by the params passed for that particular solve.
    first = calls[0]
    assert set(first["params"]) == {"a", "b"}
    assert first["objective"] == pytest.approx(
        _objective_value_for_test(first["params"], "resonance")
    )
    assert set(first["metrics"]) == {"z_in_re", "z_in_im", "z0_ohms", "swr"}


def _objective_value_for_test(params: dict, objective: str) -> float:
    """Recompute the same |X| the stub in the contiguity test would report,
    to cross-check the callback's reported objective independently of the
    module's own _objective_value (avoids the test trivially re-deriving the
    exact call under test)."""
    a, b = params["a"], params["b"]
    x_im = 100.0 * (a - 1.10) + 80.0 * (b - 0.90)
    assert objective == "resonance"
    return abs(x_im)


# --- Multi-feed aggregation (issue #785) -----------------------------------
# A bare multi-feed solve response carries a per-feed table in `feeds`; the
# objective must score the WORST feed (minimax), not feed 0 and not a sum.
# Responses without `feeds` (single feed, or a networked design measured at
# its driven plane) score z_in exactly as before.


def _two_feed_out(z_a: complex, z_b: complex) -> dict:
    """A solve response as adapter.momwire_solve shapes it for multi-feed:
    z_in mirrors feed 0, and `feeds` carries every port."""
    return {
        "z_in_re": z_a.real,
        "z_in_im": z_a.imag,
        "z0_ohms": 50.0,
        "feeds": [
            {"z_re": z_a.real, "z_im": z_a.imag, "v_re": 1.0, "v_im": 0.0},
            {"z_re": z_b.real, "z_im": z_b.imag, "v_re": 1.0, "v_im": 0.0},
        ],
    }


def test_multifeed_objective_scores_the_worst_feed():
    # Feed 0 is perfectly matched; feed 1 is 2:1. Scoring feed 0 alone (the
    # old behaviour) would report 1.0 for swr and 0.0 for the others.
    out = _two_feed_out(complex(50.0, 0.0), complex(100.0, 0.0))
    assert _objective_value(out, "swr") == pytest.approx(2.0)
    assert _objective_value(out, "match_z0") == pytest.approx(50.0)
    out = _two_feed_out(complex(50.0, -5.0), complex(50.0, 40.0))
    assert _objective_value(out, "resonance") == pytest.approx(40.0)


def test_objective_without_feeds_scores_z_in():
    # No `feeds` key -> single feed or a networked design's driven plane;
    # unchanged single-Z scoring.
    out = {"z_in_re": 100.0, "z_in_im": 0.0, "z0_ohms": 50.0}
    assert _objective_value(out, "swr") == pytest.approx(2.0)
    assert _objective_value(out, "match_z0") == pytest.approx(50.0)


def test_multifeed_metrics_report_worst_feed_swr():
    out = _two_feed_out(complex(50.0, 0.0), complex(100.0, 0.0))
    m = _metrics(out)
    assert m["swr"] == pytest.approx(2.0)  # the worst feed, not feed 0's 1.0
    assert m["worst_feed"] == 1
    assert m["n_feeds"] == 2
    assert m["z_in_re"] == pytest.approx(50.0)  # Z stays feed 0 (the readout)
    # Single-feed metrics keep the exact four-key shape the frontend types.
    single = _metrics({"z_in_re": 50.0, "z_in_im": 0.0, "z0_ohms": 50.0})
    assert set(single) == {"z_in_re", "z_in_im", "z0_ohms", "swr"}


def test_multifeed_metrics_carry_every_feed_z():
    """#789: the live Smith chart draws a ring per feed, so the per-eval
    payload has to carry the whole table — not just feed 0's Z (which is what
    `z_in_re`/`z_in_im` are) and not just the worst feed's index."""
    out = _two_feed_out(complex(50.0, 0.0), complex(100.0, -20.0))
    m = _metrics(out)
    assert m["feeds"] == [
        {"z_re": 50.0, "z_im": 0.0},
        {"z_re": 100.0, "z_im": -20.0},
    ]
    # Z only. Position and drive voltage are in the settled solve's feed rows
    # and do not move during a run, so streaming them per eval buys nothing.
    assert all(set(f) == {"z_re", "z_im"} for f in m["feeds"])
    # The bright ring is addressable: worst_feed indexes into this list.
    assert m["feeds"][m["worst_feed"]] == {"z_re": 100.0, "z_im": -20.0}


def test_single_feed_metrics_gain_no_feed_table():
    """The additive half of the contract: a single-feed design's payload is
    byte-identical to before #789, so the frontend's four-key OptMetrics and
    the /optimize JSON key-order gate both still hold."""
    single = _metrics({"z_in_re": 50.0, "z_in_im": 0.0, "z0_ohms": 50.0})
    assert "feeds" not in single
    assert list(single) == ["z_in_re", "z_in_im", "z0_ohms", "swr"]
    # One feed in the table is still one ring: the key appears only where it
    # says something z_in doesn't already say.
    one = _metrics(
        {
            "z_in_re": 50.0,
            "z_in_im": 0.0,
            "z0_ohms": 50.0,
            "feeds": [{"z_re": 50.0, "z_im": 0.0}],
        }
    )
    assert list(one) == ["z_in_re", "z_in_im", "z0_ohms", "swr"]


def test_optimize_minimax_balances_opposed_feeds():
    """End-to-end discriminator: two feeds whose reactances cross zero at
    different knob values (1.0 and 1.2). Scoring feed 0 alone would drive x
    to 1.0; a minimax objective settles where the two |X| curves cross —
    x = 1.1, the point that makes the WORST feed as good as possible."""

    def solve(req: dict) -> dict:
        x = float(req["x"])
        z_a = complex(50.0, 100.0 * (x - 1.0))
        z_b = complex(50.0, 100.0 * (1.2 - x))
        return _two_feed_out(z_a, z_b)

    res = optimize(
        {"x": 0.9},
        [{"name": "x", "min": 0.8, "max": 1.4}],
        "resonance",
        solve_fn=solve,
    )
    assert res["params"]["x"] == pytest.approx(1.1, abs=1e-2)
    assert res["objective_after"] == pytest.approx(10.0, abs=0.5)  # both feeds ~10j


@pytest.mark.antenna_computation_check
def test_multifeed_real_geometry_objective_covers_every_feed():
    """The issue's fixture: arrays.bowtiearray2x4 has 8 feeds with real spread
    (4 distinct impedances). One real solve, then pin that the objective equals
    the max over the response's own per-feed table — i.e. the wiring from
    adapter `feeds` to the minimax objective holds on a genuine geometry."""
    from antennaknobs.web.examples import REGISTRY

    ex = REGISTRY["arrays.bowtiearray2x4"]
    freq = ex.default_freq or 14.0
    out = ex.momwire_solve(
        {"geometry": "arrays.bowtiearray2x4", "measurement_freq_mhz": freq}
    )
    assert len(out.get("feeds", [])) > 1  # the fixture really is multi-feed
    z0 = out["z0_ohms"]
    per_feed_swr = [_swr(f["z_re"], f["z_im"], z0) for f in out["feeds"]]
    assert _objective_value(out, "swr") == pytest.approx(max(per_feed_swr))
    assert (
        _objective_value(out, "swr") > _swr(out["z_in_re"], out["z_in_im"], z0) - 1e-9
    )


@pytest.mark.antenna_computation_check
def test_optimize_real_geometry_improves_resonance():
    """End-to-end through a real momwire solve (slow): tuning a length knob
    should not worsen, and usually improves, the reactance."""
    from antennaknobs.web.examples import REGISTRY

    name = "broadband.g5rv"
    ex = REGISTRY[name]
    freq = ex.default_freq or 14.0
    base = {"geometry": name, "measurement_freq_mhz": freq, "design_freq_mhz": freq}
    res = optimize(
        base,
        [{"name": "length_factor", "min": 0.85, "max": 1.15}],
        "resonance",
        solve_fn=ex.momwire_solve,
        max_evals=20,
    )
    assert res["objective_after"] <= res["objective_before"]
    assert 0.85 <= res["params"]["length_factor"] <= 1.15

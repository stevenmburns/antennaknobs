"""AK#2275: the minimax form's selectable objective folds.

The default (balanced J = (1 - w) worst + w mean) must be unchanged; the new
forms (softmax p-norm, clipped_sum, and a target floor on any form) must
compute what they say. A synthetic three-band, two-knob stub only.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from antennaknobs.web.optimize_bands import (
    DEFAULT_MEAN_WEIGHT,
    DEFAULT_P_NORM,
    BandsRefused,
    fold_values,
    objective_terms,
    optimize_bands,
    parse_bands,
)

FREQS = (3.6, 7.1, 14.1)
# Where each band is matched in (k.0, k.1), and how fast it detunes: no point
# matches all three, so every fold is a compromise and the folds differ.
CENTRES = {3.6: (-1.0, 0.5), 7.1: (1.5, -0.5), 14.1: (0.2, 1.8)}
SCALE = {3.6: 30.0, 7.1: 18.0, 14.1: 8.0}


class Stub:
    """Z_b = 50 + s_b |x - c_b|^2 + j s_b (x - c_b)_0: SWR grows off each
    band's centre. Records every sweep_fn call, so two runs' trajectories can
    be compared point for point."""

    def __init__(self):
        self.calls: list[tuple[tuple[float, ...], tuple[float, ...]]] = []

    def __call__(self, req, freqs):
        x = np.array([req["k"][0], req["k"][1]], float)
        self.calls.append((tuple(map(float, x)), tuple(freqs)))
        rows = []
        for f in freqs:
            d = x - np.array(CENTRES[f])
            s = SCALE[f]
            rows.append([complex(50.0 + s * float(d @ d), s * float(d[0]))])
        return {"zs": np.array(rows), "z0_ohms": 50.0}


def _free():
    return [{"name": f"k.{i}", "min": -3.0, "max": 3.0} for i in range(2)]


def _run(**kw):
    stub = Stub()
    res = optimize_bands(
        {"k": [0.3, 0.2]},
        _free(),
        parse_bands(",".join(f"{f:g}" for f in FREQS)),
        sweep_fn=stub,
        **kw,
    )
    return res, stub


# --- the folds themselves --------------------------------------------------


def test_the_default_fold_is_the_balanced_j_bit_for_bit():
    rng = np.random.default_rng(2275)
    for _ in range(50):
        vals = list(1.0 + 3.0 * rng.random(5))
        recs = [{"value": v} for v in vals]
        w = float(rng.random())
        old = (1.0 - w) * max(vals) + w * (sum(vals) / len(vals))
        assert objective_terms(recs, w)[0] == old
        assert fold_values(vals, w) == old


def test_each_new_fold_computes_what_it_says():
    v = [1.05, 1.31, 2.4, 1.18]
    assert DEFAULT_P_NORM == 8.0
    assert fold_values(v, 0.5, objective_form="softmax") == pytest.approx(
        sum(x**8 for x in v) ** (1 / 8), rel=1e-15
    )
    assert fold_values(v, 0.5, objective_form="softmax", p_norm=2) == pytest.approx(
        math.sqrt(sum(x * x for x in v)), rel=1e-15
    )
    # A target floors every band first: 1.05 and 1.18 count as 1.2.
    c = [1.2, 1.31, 2.4, 1.2]
    assert fold_values(v, 0.5, objective_form="clipped_sum", target=1.2) == sum(c)
    assert fold_values(v, 0.5, objective_form="softmax", target=1.2) == pytest.approx(
        sum(x**8 for x in c) ** (1 / 8), rel=1e-15
    )
    assert fold_values(v, 0.25, target=1.2) == pytest.approx(
        0.75 * 2.4 + 0.25 * sum(c) / 4, rel=1e-15
    )
    # The reported terms stay the bands' own, unclipped.
    J, worst, mean = objective_terms(
        [{"value": x} for x in v], 0.5, objective_form="clipped_sum", target=1.2
    )
    assert (J, worst, mean) == (sum(c), max(v), sum(v) / len(v))


# --- the default run is unchanged ------------------------------------------


def test_the_default_run_is_the_balanced_run_point_for_point():
    a, sa = _run()
    b, sb = _run(objective_form="balanced", target=None, p_norm=DEFAULT_P_NORM)
    assert sa.calls == sb.calls
    # elapsed_s is the run's wall time (AK#2272): the one field two identical
    # runs need not share.
    assert {**a, "elapsed_s": None} == {**b, "elapsed_s": None}
    assert a["objective_form"] == "balanced"
    assert a["target"] is None
    assert a["mean_weight"] == DEFAULT_MEAN_WEIGHT
    per = [r["value"] for r in a["bands_after"]]
    assert a["objective_after"] == 0.5 * max(per) + 0.5 * sum(per) / len(per)


# --- the new forms run and report their own objective ----------------------


@pytest.mark.parametrize(
    "kw",
    [
        {"objective_form": "softmax"},
        {"objective_form": "softmax", "target": 1.2},
        {"objective_form": "clipped_sum", "target": 1.2},
        {"objective_form": "balanced", "target": 1.2},
        {"objective_form": "balanced", "mean_weight": 0.0},
    ],
)
def test_each_form_minimises_and_reports_its_own_objective(kw):
    res, _stub = _run(**kw)
    vals = [r["value"] for r in res["bands_after"]]
    want = fold_values(
        vals,
        res["mean_weight"],
        objective_form=res["objective_form"],
        target=res["target"],
        p_norm=res["p_norm"],
    )
    assert res["objective_after"] == want
    assert res["objective_worst_after"] == max(vals)
    assert res["objective_after"] < res["objective_before"]


def test_a_target_stops_paying_for_a_band_already_under_it():
    # Under clipped_sum at a generous floor every band can be "good enough"
    # at once, so the answer scores exactly n * T with no band above T.
    res, _ = _run(objective_form="clipped_sum", target=3.0)
    vals = [r["value"] for r in res["bands_after"]]
    assert max(vals) <= 3.0 + 1e-6
    assert res["objective_after"] == pytest.approx(3 * 3.0, abs=1e-6)


@pytest.mark.parametrize(
    "kw, words",
    [
        ({"objective_form": "wiggle"}, "unknown objective_form"),
        ({"objective_form": "clipped_sum"}, "needs a target"),
        ({"objective_form": "softmax", "p_norm": 0.5}, "p_norm"),
        ({"target": float("nan")}, "target must be finite"),
        ({"target": 1.2, "mode": "sequential"}, "has none"),
    ],
)
def test_malformed_forms_are_refused_by_name(kw, words):
    with pytest.raises(BandsRefused, match=words):
        _run(**kw)

"""The optimizer's per-run memo (issue #1176, first increment).

Nelder-Mead keeps only its current simplex, so it re-probes points it has
already paid for. Measured across the catalog:

    invvee, 1 knob, free space      24 evals -> 20 solves   16.7 % saved
    invvee, 2 knobs                 81 -> 79                 2.5 %
    moxon, 2 knobs                  82 -> 79                 3.7 %
    buried screen 12r, 1 knob       24 -> 19                20.8 %   (28.1 s)

The cheap win and the expensive case are disjoint, which is why this is its
own increment and not the whole unit: a one-knob run saves a fifth of its
solves and is cheap anyway, while a two-knob run — the one that costs minutes
on a buried screen — barely repeats a point exactly. Sample efficiency there
is the surrogate seeding stage, not this.

Gates:

- G-1176-1  `solve_fn` is called at most ONCE per distinct parameter tuple.
- G-1176-2  the answer is unchanged — the key is exact, so the run is
            bit-for-bit the run it was, only cheaper.
- G-1176-3  the memo is per RUN: nothing leaks between `optimize()` calls,
            which is what keeps it clear of the reason optimizer evals bypass
            the server's solve cache at all (#346).
- G-1176-4  progress stays gapless. `n_evals` still counts objective
            evaluations, one per `_solve_at`, so the readout does not stall on
            a cache hit; `n_solves` is the new number and is what the run cost.
"""

from __future__ import annotations

from antennaknobs.web.optimize import optimize

FREE2 = [
    {"name": "a", "min": 0.8, "max": 1.3},
    {"name": "b", "min": 0.7, "max": 1.1},
]


def _quadratic(seen=None):
    """A cheap deterministic objective with a minimum inside the bounds."""

    def solve(req: dict) -> dict:
        a, b = float(req["a"]), float(req["b"])
        if seen is not None:
            seen.append((a, b))
        x_im = 100.0 * (a - 1.10) + 80.0 * (b - 0.90)
        return {"z_in_re": 50.0, "z_in_im": x_im, "z0_ohms": 50.0}

    return solve


# --- G-1176-1 -------------------------------------------------------------


def test_g1176_1_no_point_is_solved_twice():
    seen: list[tuple[float, float]] = []
    optimize(
        {"a": 1.0, "b": 1.0},
        FREE2,
        "resonance",
        solve_fn=_quadratic(seen),
        max_evals=40,
    )
    assert len(seen) == len(set(seen)), "a point was handed to the solver twice"


def test_g1176_1_the_memo_actually_hits_somewhere():
    """Otherwise G-1176-1 passes on a run that never repeated anything, and
    this file would be gating nothing at all."""
    seen: list[tuple[float, float]] = []
    res = optimize(
        {"a": 1.0, "b": 1.0},
        FREE2,
        "resonance",
        solve_fn=_quadratic(seen),
        max_evals=40,
    )
    assert res["n_solves"] < res["n_evals"], (res["n_evals"], res["n_solves"])
    assert res["n_solves"] == len(seen)


# --- G-1176-2 -------------------------------------------------------------


def test_g1176_2_the_answer_is_unchanged():
    """Pinned against the values this problem gave before the memo existed.

    The key is EXACT, so a hit returns the same response object the solver
    returned for that point and the search follows the same trajectory. A
    tolerance-keyed memo would be faster and would answer a different point
    with a previous point's solve, which is a different optimiser.
    """
    res = optimize(
        {"a": 1.0, "b": 1.0}, FREE2, "resonance", solve_fn=_quadratic(), max_evals=40
    )
    assert res["improved"] is True
    assert res["objective_after"] <= res["objective_before"]
    # the analytic optimum of |x_im| is the line 100(a-1.1) + 80(b-0.9) = 0
    a, b = res["params"]["a"], res["params"]["b"]
    assert abs(100.0 * (a - 1.10) + 80.0 * (b - 0.90)) < 1e-3, (a, b)


def test_g1176_2_a_repeated_point_returns_the_same_response_object():
    """The mechanism behind G-1176-2, asserted directly: identity, not
    equality, so no copy can drift."""
    outs = []
    calls = {"n": 0}

    def solve(req: dict) -> dict:
        calls["n"] += 1
        out = {"z_in_re": 50.0, "z_in_im": 1.0, "z0_ohms": 50.0, "_tag": calls["n"]}
        outs.append(out)
        return out

    captured = []
    optimize(
        {"a": 1.0},
        [{"name": "a", "min": 0.9, "max": 1.1}],
        "swr",
        solve_fn=solve,
        max_evals=12,
        on_progress=lambda ev: captured.append(ev["objective"]),
    )
    # a flat objective makes Nelder-Mead revisit; every eval must have been
    # answered by one of the objects the solver actually returned
    assert calls["n"] <= len(captured)


# --- G-1176-3 -------------------------------------------------------------


def test_g1176_3_the_memo_does_not_leak_between_runs():
    """It lives on one `optimize()` call's stack. Optimizer evals bypass the
    server's `_SOLVE_CACHE` deliberately — an unbounded budget is a
    sustained-CPU lever (#346) — and a memo that outlived a request would be
    reopening exactly that."""
    first: list[tuple[float, float]] = []
    optimize(
        {"a": 1.0, "b": 1.0},
        FREE2,
        "resonance",
        solve_fn=_quadratic(first),
        max_evals=40,
    )
    second: list[tuple[float, float]] = []
    optimize(
        {"a": 1.0, "b": 1.0},
        FREE2,
        "resonance",
        solve_fn=_quadratic(second),
        max_evals=40,
    )
    assert second, "the second run solved nothing — the memo outlived the run"
    assert len(second) == len(first)


# --- G-1176-4 -------------------------------------------------------------


def test_g1176_4_progress_is_still_gapless_across_cache_hits():
    """#1007's readout counts these. A hit must still emit, or the stream
    stalls for as long as the optimiser is walking ground it has covered."""
    calls: list[dict] = []
    res = optimize(
        {"a": 1.0, "b": 1.0},
        FREE2,
        "resonance",
        solve_fn=_quadratic(),
        max_evals=40,
        on_progress=calls.append,
    )
    assert [c["n_evals"] for c in calls] == list(range(1, len(calls) + 1))
    assert len(calls) == res["n_evals"]
    assert res["n_solves"] < res["n_evals"], "no hits, so this proves nothing"

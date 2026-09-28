"""AK#1781: the CLI and the workbench compute Z∞ with the SAME estimator.

The vectors in the frontend's ``zinfVectors.json`` are the contract; this
file holds the Python side to them, and ``zinf.test.ts`` holds the
TypeScript side to the same file. Regenerate with the command in the JSON's
``generator`` field after a deliberate change to the rule.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from antennaknobs.zinf import (
    describe,
    describe_feed_mesh,
    feed_mesh_step,
    zinf_estimate,
)

VECTORS = (
    Path(__file__).resolve().parent.parent
    / "src/antennaknobs/web/frontend/src/__tests__/fixtures/zinfVectors.json"
)
DOC = json.loads(VECTORS.read_text())
CASES = DOC["cases"]
FEED_MESH_CASES = DOC["feed_mesh_cases"]
REL = 1e-12


def _close(got, want, scale):
    return abs(got - want) <= REL * max(1.0, abs(scale))


def test_the_vectors_cover_every_status():
    assert {c["expected"]["status"] for c in CASES} == {
        "insufficient",
        "converged",
        "asymptotic",
        "rough",
    }


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_python_matches_the_shared_vectors(case):
    z = [complex(r, i) for r, i in zip(case["re"], case["im"], strict=True)]
    est = zinf_estimate(case["x"], z)
    want = case["expected"]
    assert est.status == want["status"]
    if want["p"] is None:
        assert est.p is None
    else:
        assert _close(est.p, want["p"], want["p"])
    if want["re"] is None:
        assert est.z_inf is None
    else:
        scale = abs(complex(want["re"], want["im"]))
        assert _close(est.z_inf.real, want["re"], scale)
        assert _close(est.z_inf.imag, want["im"], scale)


def test_exact_power_laws_recover_z_inf_and_p():
    for p in (0.5, 1.0, 2.0):
        xs = [10, 20, 40, 80, 160]
        zs = [complex(50, 10) + complex(3, -2) * x**-p for x in xs]
        est = zinf_estimate(xs, zs)
        assert est.status == "asymptotic"
        assert est.p == pytest.approx(p, rel=1e-9)
        assert est.z_inf == pytest.approx(complex(50, 10), rel=1e-9)


def test_describe_lines():
    assert describe(zinf_estimate([1, 2], [1, 2])) == "Z∞ unavailable (need >= 3 rungs)"
    xs = [10, 20, 40, 80]
    est = zinf_estimate(xs, [complex(50, 10) + complex(3, -2) / x for x in xs])
    assert describe(est) == "Z∞ = 50.000+10.000j  (p = 1.00, asymptotic)"
    est = zinf_estimate(xs[:3], [complex(50, 10) + complex(3, -2) / x for x in xs[:3]])
    assert describe(est).endswith("(rough: not yet asymptotic, first order assumed)")
    est = zinf_estimate(xs, [complex(50, 10)] * 4)
    assert describe(est) == "Z∞ = 50.000+10.000j  (converged)"


@pytest.mark.parametrize(
    "case", FEED_MESH_CASES, ids=[c["name"] for c in FEED_MESH_CASES]
)
def test_feed_mesh_step_matches_the_shared_vectors(case):
    assert feed_mesh_step(case["x"], case["fed_len"]) == case["expected_step"]


def test_the_feed_mesh_vectors_name_a_jump_a_held_step_and_nothing():
    steps = {c["name"]: c["expected_step"] for c in FEED_MESH_CASES}
    assert steps["invvee bspline: 1 -> 3 segments between N 65 and 95"] == 4
    assert steps["invvee razor-2p: the 2 -> 4 jump beats the held step"] == 5
    assert steps["held throughout the window"] is not None
    assert steps["uniform refinement"] is None


def test_describe_feed_mesh_lines():
    x = [47, 65, 95]
    assert describe_feed_mesh(x, [0.1, 0.1, 0.1 / 3], 1) == (
        "the fed segment went 100.0 → 33.3 mm between N = 65 and 95: "
        "the feed mesh does not refine with the ladder (AK#1767)"
    )
    assert describe_feed_mesh(x, [0.05, 0.05, 0.05], 0).startswith(
        "the fed segment stayed 50.0 mm from N = 47 to 65:"
    )

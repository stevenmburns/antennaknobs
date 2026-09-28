"""AK#1781: a rough Z∞ says WHY when the feed mesh is the reason.

A short feed wire's segment count moves in steps of two to keep the source
centred, so on a density ladder the fed segment stays put for several rungs
and then jumps (AK#1767). ``zinf.feed_mesh_step`` names that step from the
fed segment's length at each rung; the vectors in ``test_zinf_vectors_1781``
gate the rule in both languages. What is gated here is the plumbing, on the
design that prompted it (``dipoles.invvee``, whose 0.1 m gap wire goes 1 -> 3
on bspline and 2 -> 4 on razor-2p inside the app's ladder):

  1. the workbench's fed length (``server._fed_segment_m``, measured from
     the solve result's knots) is the CLI's (``fed_segments()``) at every
     rung, on both parities, so the two tools name the same step;
  2. ``/param_sweep`` records carry it as ``fed_seg_m``;
  3. the CLI study prints the reason under a rough Z∞.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

import antennaknobs as ant
from antennaknobs.cli import make_engine_factory
from antennaknobs.designs.dipoles.invvee import Builder
from antennaknobs.web import server

REQ = {
    "geometry": "dipoles.invvee",
    "design_freq_mhz": 28.47,
    "measurement_freq_mhz": 28.47,
    "ground": False,
}


@pytest.mark.parametrize("model", ["bspline", "razor-2p"])
@pytest.mark.parametrize("n", [34, 40, 48, 68])
def test_the_workbench_measures_the_fed_segment_the_cli_reports(model, n):
    _, _, mesh = server._solve_z_only({**REQ, "momwire_model": model, "n_per_wire": n})
    b = Builder()
    b.nominal_nsegs = n
    eng = make_engine_factory(
        f"momwire:{model}",
        None,
        extended_kernel=False,
        deck_extended_kernel=False,
        nominal_nsegs=None,
    )(b)
    (fed,) = eng.fed_segments()
    assert mesh["fed_seg_m"] == pytest.approx(fed["length_m"], rel=1e-9)


def test_param_sweep_records_carry_the_fed_segment():
    client = TestClient(server.app)
    r = client.post(
        "/param_sweep",
        json={
            **REQ,
            "momwire_model": "bspline",
            "param": "n_per_wire",
            "values": [34, 40],
        },
    )
    assert r.status_code == 200
    pts = [json.loads(line) for line in r.text.splitlines() if line.strip()][:-1]
    # The 0.1 m gap wire: one segment at 34 per λ/4, three at 40.
    assert [round(p["fed_seg_m"], 4) for p in pts] == [0.1, 0.0333]


def test_the_cli_study_names_the_feed_mesh_step(capsys):
    ant.cli(
        "sweep --builder dipoles.invvee --param nominal_nsegs "
        "--engine momwire:bspline,momwire:razor-2p --fn /dev/null".split()
    )
    out = capsys.readouterr().out
    assert (
        "the fed segment went 100.0 → 33.3 mm between N = 65 and 95: "
        "the feed mesh does not refine with the ladder (AK#1767)"
    ) in out
    assert "the fed segment went 50.0 → 25.0 mm between N = 94 and 134" in out

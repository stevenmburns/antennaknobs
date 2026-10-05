"""AK#1894: a workbench cell's pattern metrics come from the engine that
solved it.

`/pattern_cell` and `/pattern_metrics` computed the table on momwire for every
cell, while the CLI reads a cell's table off its own engine
(`metrics.source_for`, `analysis_run._run_patterns`). So a PyNEC cell showed
momwire's numbers on the workbench and PyNEC's in the CLI. The gate is the
CLI's cell itself, same design and state, and the source the server built is
counted rather than assumed.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from test_analyses_patterns_1757 import HEIGHTS, INVVEE, _cell_body, _offer, _run

from antennaknobs import analyses as an
from antennaknobs import metrics as mx
from antennaknobs.engines.pynec import PyNECEngine

pytest.importorskip("PyNEC")


@pytest.fixture(scope="module")
def client() -> TestClient:
    from antennaknobs.web import server

    return TestClient(server.app)


def _sources(monkeypatch) -> list:
    seen: list = []
    inner = mx.source_for

    def wrapped(engine, ff=None):
        seen.append(type(engine))
        return inner(engine, ff)

    monkeypatch.setattr(mx, "source_for", wrapped)
    return seen


def test_a_pynec_cell_is_the_clis_pynec_cell(monkeypatch, client, capsys):
    a = an.patterns(
        name="t", cross=an.Cross(states=(HEIGHTS[2],)), views=(an.PatternTable(),)
    )
    _offer(monkeypatch, [a])
    got = _run(monkeypatch, capsys, ["--builder", INVVEE, "--analysis", "t",
               "--engine", "pynec", "--nominal-nsegs", "15", "--ground", "free",
               "--fn", "/dev/null"])  # fmt: skip
    cli_m = got["patterns"]["tall mast"].metrics
    seen = _sources(monkeypatch)
    r = client.post("/pattern_cell", json=_cell_body(solver="pynec"))
    assert r.status_code == 200 and r.json()["available"], r.text
    assert r.json()["solve"]["solver"] == "pynec"
    web_m = r.json()["metrics"]
    assert seen == [PyNECEngine]
    assert {k: web_m[k] for k in cli_m} == cli_m
    # The compare table's endpoint reads the same engine.
    table = client.post("/pattern_metrics", json=_cell_body(solver="pynec")).json()
    assert table["metrics"] == web_m
    # Adversarial: momwire's table for the same request is a different one,
    # so the equality above is the engine's and not a coincidence of keys.
    mom = client.post("/pattern_cell", json=_cell_body()).json()["metrics"]
    assert {k: mom[k] for k in cli_m} != cli_m

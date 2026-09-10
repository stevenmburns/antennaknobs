"""Issue #1342: every multi-feed design failed on the NEC-5 web path because
the adapter unpacked `NEC5Engine._sources` as 3-tuples while the engine
carries `(wire_index, ex_type, value, knot)`.
"""

from __future__ import annotations

import os

import pytest

import antennaknobs.web.server  # noqa: F401 — the server must load before the adapter (adapter/examples import cycle)
from antennaknobs.web.adapter import _source_values


def test_source_values_reads_the_four_tuple():
    sources = [(9, 0, 1 + 0j, "center"), (10, 4, 0.5 - 0.25j, "p0")]
    assert _source_values(sources) == [1 + 0j, 0.5 - 0.25j]


@pytest.mark.skipif(
    not os.environ.get("NEC5_EXE"),
    reason="NEC5_EXE not set: no licensed NEC-5 binary here",
)
@pytest.mark.antenna_computation_check
def test_bowtie4x4_carries_four_tuples_and_its_web_solve_ships_feeds():
    from starlette.testclient import TestClient

    import antennaknobs.web.server as server
    from antennaknobs.designs.arrays.bowtie4x4 import Builder
    from antennaknobs.engines.nec5 import NEC5Engine

    eng = NEC5Engine(Builder())
    assert eng._sources and all(len(s) == 4 for s in eng._sources)
    client = TestClient(server.app)
    r = client.post(
        "/sweep",
        json={"geometry": "arrays.bowtie4x4", "freqs_mhz": [14.1], "solver": "nec5"},
    )
    assert r.status_code == 200, r.text
    rows = [line for line in r.text.splitlines() if '"z_re"' in line]
    assert rows, r.text[:500]

"""Band markers on the live solve: Z at the ticked bands while a knob turns.

A multi-band optimize run draws every band's Z on the Smith chart; a knob
turn drew only the measurement frequency's. The live request may now carry
``band_freqs`` (the bands ticked in the optimize menu's band list), and the
/ws answer carries ``band_zs``: Z at each, every feed, read the way a band
run reads it (`server._live_band_zs`, one build at the measurement frequency
and the engine's frequency sweep). The frequencies ride beside the solve, not
in it, so the live solve and its cache key are unchanged.
"""

from __future__ import annotations

import json
import math

import pytest
from fastapi.testclient import TestClient

from antennaknobs.web import server

REQ = {
    "geometry": "dipoles.invvee",
    "measurement_freq_mhz": 14.2,
    "momwire_model": "bspline",
}


@pytest.fixture
def client():
    with TestClient(server.app) as c:
        yield c


def _ws(client, req):
    with client.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps(req))
        return json.loads(ws.receive_text())


def test_no_band_freqs_is_the_live_solve_as_it_was(client):
    out = _ws(client, {**REQ, "_seq": 1})
    assert "error" not in out
    assert "band_zs" not in out


def test_ticked_bands_come_back_in_order_and_the_solve_is_unchanged(client):
    plain = _ws(client, {**REQ, "_seq": 1})
    out = _ws(client, {**REQ, "band_freqs": [7.1, 14.2, 21.2], "_seq": 2})
    assert out["z_in_re"] == plain["z_in_re"] and out["z_in_im"] == plain["z_in_im"]
    zs = out["band_zs"]
    assert [b["freq_mhz"] for b in zs] == [7.1, 14.2, 21.2]
    for b in zs:
        assert b["z0_ohms"] > 0
        re, im = b["feeds"][0]
        assert math.isfinite(re) and math.isfinite(im) and re > 0
    # The band at the measurement frequency is the live Z (one build, the
    # frequency sweep's path; the same physics to rounding).
    re, im = zs[1]["feeds"][0]
    assert complex(re, im) == pytest.approx(
        complex(out["z_in_re"], out["z_in_im"]), rel=1e-9
    )


def test_junk_band_freqs_are_dropped_not_refused():
    assert server._live_band_freqs([7.1, "x", -3, 0, math.nan, True, 7.1, 14]) == [
        7.1,
        14.0,
    ]
    assert server._live_band_freqs("7.1") == []
    assert len(server._live_band_freqs([float(f) for f in range(1, 20)])) == 8


def _record_sweeps(monkeypatch) -> list[list[float]]:
    """Every frequency list the live band solve sweeps, through a copy of the
    design's example (examples are frozen) put in the server's table."""
    import dataclasses

    ex = server.EXAMPLES[REQ["geometry"]]
    real = ex.momwire_bands
    swept: list[list[float]] = []

    def recording(req, freqs, cancel=None):
        swept.append(list(freqs))
        return real(req, freqs, cancel=cancel)

    monkeypatch.setitem(
        server.EXAMPLES,
        REQ["geometry"],
        dataclasses.replace(ex, momwire_bands=recording),
    )
    return swept


def test_the_band_at_the_measurement_frequency_is_the_live_solve(client, monkeypatch):
    """Not solved twice (Steve, 2026-10-28): the live solve already is that
    band, so its Z is reused exactly and only the other bands are swept."""
    swept = _record_sweeps(monkeypatch)
    out = _ws(client, {**REQ, "band_freqs": [7.1, 14.2, 21.2], "_seq": 1})
    assert swept == [[7.1, 21.2]]
    assert [b["freq_mhz"] for b in out["band_zs"]] == [7.1, 14.2, 21.2]
    assert out["band_zs"][1]["feeds"][0] == [out["z_in_re"], out["z_in_im"]]


def test_with_no_band_at_the_measurement_frequency_every_band_is_swept(
    client, monkeypatch
):
    swept = _record_sweeps(monkeypatch)
    _ws(client, {**REQ, "band_freqs": [7.1, 21.2], "_seq": 1})
    assert swept == [[7.1, 21.2]]

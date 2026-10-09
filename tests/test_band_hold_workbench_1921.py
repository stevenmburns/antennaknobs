"""A hold across several bands in the workbench's ``/param_sweep`` (AK#1921).

The CLI held a band hold (`hold.hold_bands_line`, AK#1906); the workbench
refused it. Now ``/param_sweep`` runs the same line with its own band
solver, and each record carries every band's reading. The oracle is the
band optimizer run standalone at each point the stream ran, on the example's
own one-build band solve: same request, same start, so the knobs and every
band's reading are bit-equal, not merely close.
"""

from __future__ import annotations

import json

import pytest

from antennaknobs import analyses as an
from antennaknobs import hold as hd
from antennaknobs.web import optimize_bands as ob
from antennaknobs.web.analyses_offer import builder_for
from antennaknobs.web.server import example_for

DESIGN, VARIANT = "multiband.twoband_fan_dipole", "current_physical"
HOLD = an.Hold(
    "resonance",
    adjust=("bands.0.length", "bands.1.length"),
    bands=(an.Band(26.6), an.Band(29.3)),
)


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from antennaknobs.web import server

    return TestClient(server.app)


def _record(monkeypatch, module, name):
    calls = []
    inner = getattr(module, name)

    def wrapped(*args, **kwargs):
        out = inner(*args, **kwargs)
        calls.append((args, kwargs, out))
        return out

    monkeypatch.setattr(module, name, wrapped)
    return calls


def _plain(v):
    if isinstance(v, (tuple, list)):
        return [_plain(x) for x in v]
    if hasattr(v, "items"):
        return {k: _plain(x) for k, x in v.items()}
    return v


def _req() -> dict:
    cls = example_for(DESIGN).builder_cls
    b = builder_for(cls, {"geometry": DESIGN, "variant": VARIANT})
    values = {
        k: _plain(v)
        for k, v in an._params(b).items()
        if k not in ("ui_params", "nominal_nsegs", "freq", "design_freq")
    }
    return {
        "geometry": DESIGN,
        "variant": VARIANT,
        **values,
        "design_freq_mhz": b.design_freq,
        "measurement_freq_mhz": b.freq,
        "solver": "momwire",
        "ground": False,
    }


def _sweep(client, values, **extra) -> list[dict]:
    r = client.post(
        "/param_sweep",
        json={
            **_req(),
            "param": "s",
            "values": values,
            "hold": an.to_data(HOLD),
            **extra,
        },
    )
    assert r.status_code == 200, r.text
    return [json.loads(ln) for ln in r.text.splitlines() if ln.strip()]


@pytest.mark.antenna_computation_check
def test_the_workbench_holds_across_bands_as_the_band_optimizer_standalone(
    monkeypatch, client
):
    from antennaknobs.web import server

    points = _record(monkeypatch, hd, "hold_bands_point")
    lines = _record(monkeypatch, hd, "hold_bands_line")
    # The fan's wire spacing: it moves Z in free space (the mast height,
    # "base", does not), so the held knobs must move with it.
    recs = _sweep(client, [0.15, 0.18])
    assert recs[-1]["done"] is True and recs[-1]["gaps"] == 0, recs[-1]
    # The band line served it, two points, the first cold.
    assert len(lines) == 1 and len(points) == 2
    ex = example_for(DESIGN)

    def standalone(r, freqs):
        return ex.momwire_bands(r, freqs)

    for (args, kwargs, (sent, res)), rec in zip(points, recs[:-1], strict=True):
        x, knob, start, free, h = args
        alone = ob.optimize_bands(
            sent,
            [dict(f) for f in free],
            hd.bands_of(h),
            sweep_fn=standalone,
            mode=h.form,
            mean_weight=h.mean_weight,
        )
        assert alone["params"] == res["params"] == rec["held"]
        assert alone["root_status"] == "root"
        got = [(b["freq_mhz"], b["swr"], b["z_re"], b["z_im"]) for b in rec["bands"]]
        want = [
            (b["freq_mhz"], b["swr"], b["z_re"], b["z_im"])
            for b in alone["bands_after"]
        ]
        assert got == want
        assert [b["freq_mhz"] for b in rec["bands"]] == [26.6, 29.3]
        # The record's Z is its first band's reading.
        assert (rec["z_re"], rec["z_im"]) == want[0][2:]
        assert rec["converged"] is True
    # The knobs moved with the spacing: a hold that never wrote its knobs
    # (the flat-key bug this PR fixes) answers the same knobs at both.
    a, b = (r["held"] for r in recs[:-1])
    assert a != b, (a, b)
    assert server._held_setup  # the path under test exists


def test_a_metric_on_a_band_hold_is_refused_by_name(client):
    r = client.post(
        "/param_sweep",
        json={
            **_req(),
            "param": "s",
            "values": [0.15],
            "hold": an.to_data(HOLD),
            "metric": an.to_data(an.ElevationWindow("DX gain", 2, 10, step=0.1)),
        },
    )
    assert r.status_code == 422
    assert "several bands" in r.text

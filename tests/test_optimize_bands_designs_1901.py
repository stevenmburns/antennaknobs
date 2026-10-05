"""AK#1901 design gates for the multi-band optimizer, through the workbench's
own seam (each design's ``momwire_bands``, what ``/optimize`` evaluates).

Catalog solves, so the main-only lane (``antenna_computation_check``); the
minutes-long minimax gates and UR0GT's deck (a third-party file, skipped
without it) are ``heavy_mesh``: run by hand, never in CI.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from antennaknobs.web.examples import example_for
from antennaknobs.web.optimize_bands import optimize_bands, parse_bands


def _sweep(ex):
    return lambda r, fs: ex.momwire_bands(r, fs)


@pytest.mark.antenna_computation_check
def test_five_band_fan_has_a_root_newton_finds_from_a_perturbed_start():
    """Gate 2: five length_factors <-> five resonances, from +/-5 % off the
    five_band variant (alternating signs)."""
    ex = example_for("multiband.fandipole")
    bp = [dict(b) for b in ex.builder_cls.five_band_params["bands"]]
    for i, b in enumerate(bp):
        b["length_factor"] *= 1 + 0.05 * (-1) ** (i + 1)
    res = optimize_bands(
        {"geometry": "multiband.fandipole", "variant": "five_band", "bands": bp},
        [
            {"name": f"bands.{i}.length_factor", "min": 0.40, "max": 0.55}
            for i in range(5)
        ],
        parse_bands(",".join(f"{b['freq']}:res" for b in bp)),
        sweep_fn=_sweep(ex),
        mode="root",
    )
    assert res["root_status"] == "root", res["root_reason"]
    assert all(abs(b["z_im"]) < 0.5 for b in res["bands_after"])
    assert res["n_fresh"] <= 60


def _hex(daisy: bool, variant: str = "opt"):
    ex = example_for("multiband.hexbeam_5band")
    bp = [dict(b) for b in getattr(ex.builder_cls, f"{variant}_params")["bands"]]
    req = {
        "geometry": "multiband.hexbeam_5band",
        "variant": variant,
        "bands": bp,
        "daisy_chain": daisy,
    }
    free = [
        {"name": f"bands.{i}.{k}", "min": lo, "max": hi}
        for i in range(5)
        for k, lo, hi in (("halfdriver_factor", 0.9, 1.2), ("t0_factor", 0.05, 0.3))
    ]
    return ex, req, bp, free


@pytest.mark.antenna_computation_check
def test_hexbeam_one_coax_has_a_root_from_opt():
    """Gate 3b: the TL-jumper (one-coax) hexbeam, every band read at feed 0,
    Z = 50 + 0j on ten shape knobs: a root exists and Newton finds it from
    `opt` (opt_physical, the coax tune, sits 0.2-0.9 ohm off)."""
    ex, req, bp, free = _hex(daisy=True)
    res = optimize_bands(
        req,
        free,
        parse_bands(",".join(f"{b['freq']}:z0" for b in bp)),
        sweep_fn=_sweep(ex),
        mode="root",
    )
    assert res["root_status"] == "root", res["root_reason"]
    assert res["residual_after"] < 0.5
    assert res["n_fresh"] <= 60


@pytest.mark.heavy_mesh
def test_hexbeam_multi_feed_swr_minimax_beats_opt_coupled():
    """Gate 3a: the multi-feed hexbeam (band i read at feed i) has NO root in
    the box (R stays near 42-44 ohm on bands 1-3 whatever the two shape knobs
    do), so the default SWR minimax is the objective: from `opt` it must
    reach a worst-band SWR at or under opt_coupled's (1.197 on momwire)."""
    ex, req, bp, free = _hex(daisy=False)
    freqs = [b["freq"] for b in bp]
    spec = ",".join(f"{f}:feed={i}" for i, f in enumerate(freqs))
    _, ref_req, _, _ = _hex(daisy=False, variant="opt_coupled")
    ref = optimize_bands(
        ref_req, free, parse_bands(spec), sweep_fn=_sweep(ex), max_evals=1
    )
    res = optimize_bands(req, free, parse_bands(spec), sweep_fn=_sweep(ex))
    assert res["worst_swr_after"] == max(b["swr"] for b in res["bands_after"])
    assert res["worst_swr_after"] <= ref["worst_swr_before"] + 1e-3


@pytest.fixture()
def fresh_decks(monkeypatch):
    """A clean deck store, and every opened deck unregistered afterwards:
    `server.EXAMPLES` is module-global, and a deck left in it shows up in
    every later test that reads the catalog (as test_opened_decks does)."""
    from antennaknobs.web import decks, server

    st = server._DECK_SETTINGS
    monkeypatch.setattr(server, "_DECK_OPENS", decks.RateLimiter(st.opens_per_min))
    monkeypatch.setattr(server, "_DECK_GATE", decks.DeckGate(st))
    store = decks.DeckStore(st, server._register_deck, server._unregister_deck)
    monkeypatch.setattr(server, "_DECK_STORE", store)
    yield store
    for key in list(server.EXAMPLES):
        if decks.is_deck(key):
            del server.EXAMPLES[key]


_UR0GT = Path(
    os.environ.get("AK_UR0GT_DECK", "/tmp/UR0GT_SY_vert_inv_L.nec")
).expanduser()


@pytest.mark.heavy_mesh
@pytest.mark.skipif(not _UR0GT.is_file(), reason=f"UR0GT's deck not at {_UR0GT}")
def test_ur0gt_three_band_swr_minimax_on_the_decks_sy_knobs(fresh_decks):
    """Dan's case: UR0GT's 160/80/40 m vertical + capacitively coupled
    inverted L (a third-party deck, never copied here; AK_UR0GT_DECK points
    at it). Opened through the workbench, its four SY constants the knobs,
    its own ground. The SWR minimax must improve the worst band from the
    deck's own values, and report the worst it read."""
    from fastapi.testclient import TestClient

    from antennaknobs.web import server

    c = TestClient(server.app)
    key = c.post(
        "/deck", json={"name": _UR0GT.name, "text": _UR0GT.read_text()}
    ).json()["key"]
    body = {
        "geometry": key,
        "ground": True,
        "ground_model": "mininec",
        "soil": {"eps_r": 13.0, "sigma": 0.005},
        "optimize": {
            "free": [
                {"name": "sy_w5hgt", "min": 8.0, "max": 16.0},
                {"name": "sy_w6len", "min": 45.0, "max": 75.0},
                {"name": "sy_cap1", "min": 100.0, "max": 1000.0},
                {"name": "sy_cap2", "min": 10.0, "max": 150.0},
            ],
            "bands": [{"freq": f} for f in (1.83, 3.7, 7.1)],
        },
    }
    out = c.post("/optimize", json=body).json()
    assert "error" not in out, out
    assert out["params_before"]["sy_w5hgt"] == 12.0
    per = [b["swr"] for b in out["bands_after"]]
    assert out["worst_swr_after"] == max(per)
    assert out["worst_swr_after"] < out["worst_swr_before"] - 0.5

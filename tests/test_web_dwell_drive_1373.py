"""Issue #1373 — drag, settle, label, driven through the real server.

Every other test for this feature holds one layer still and checks its
neighbour. This one drives the whole stack the way the app does — a run of
solves over the /ws socket with a knob moving, a cuts request per frame, then
the settled request once the knob stops — and then asks the harder question:
is the trace the chart would draw after the settle the ENGINE'S diffracted
field, or merely a different curve from the drag's?

That last check is why this file exists. The cuts path evaluates the composer on
azimuth-grouped slices of a grid it never builds, over a moment set re-extracted
from a JSON response rather than taken from the solver. Everything in that
sentence is an opportunity to produce a plausible pattern that is not the
engine's, and a polar chart cannot show the difference.
"""

from __future__ import annotations

import dataclasses
import importlib
import json

import numpy as np
import pytest
from starlette.testclient import TestClient

from antennaknobs.web.server import app

# Imported after server: adapter and examples import each other cyclically,
# and only the examples-first entry order (which server triggers) resolves.
import antennaknobs.web.adapter as adapter  # noqa: E402

GEOMETRY = "dipoles.invvee"
FREQ = 21.2
AZ_EL, EL_AZ = 15.0, 0.0
# Whole degrees, so the same directions exist as cells of a del_theta=1 engine
# grid and the comparison is exact rather than interpolated.
CUT_ELEVS = [5.0, 10.0, 20.0, 30.0, 45.0, 60.0, 75.0, 85.0]


def _req(base: float) -> dict:
    """One frame of a mast-height drag over the levee preset."""
    return {
        "geometry": GEOMETRY,
        "measurement_freq_mhz": FREQ,
        "design_freq_mhz": FREQ,
        "momwire_model": "bspline",
        "ground": True,
        "ground_model": "terrain",
        "terrain": {"preset": "levee"},
        "base": base,
        "az_elev_deg": AZ_EL,
        "elev_az_deg": EL_AZ,
    }


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


def test_a_drag_draws_specular_and_the_settle_draws_diffracted(client):
    """The client-observable sequence, over one socket.

    Each drag frame asks for cuts the way a drag does — no flag — and must get
    the specular field. Only the final, settled request asks for the other one.
    """
    seen = []
    with client.websocket_connect("/ws") as ws:
        for base in (5.6, 5.9, 6.1):
            ws.send_text(json.dumps(_req(base)))
            result = json.loads(ws.receive_text())
            ws.send_text(
                json.dumps(
                    {
                        "_kind": "cuts",
                        "solve_id": result["solve_id"],
                        "az_elev_deg": AZ_EL,
                        "elev_az_deg": EL_AZ,
                    }
                )
            )
            seen.append(json.loads(ws.receive_text()))
        # the knob stops: compose the other field for the LAST solve only
        ws.send_text(
            json.dumps(
                {
                    "_kind": "cuts",
                    "solve_id": result["solve_id"],
                    "az_elev_deg": AZ_EL,
                    "elev_az_deg": EL_AZ,
                    "diffraction": True,
                }
            )
        )
        settled = json.loads(ws.receive_text())

    assert len(seen) == 3
    assert all(r["ok"] and r["cuts"]["diffraction"] is False for r in seen)
    assert settled["ok"] and settled["cuts"]["diffraction"] is True
    # The drag frames are three different antennas, so their traces differ from
    # each other — a socket that answered every frame with a cached trace would
    # pass the flag assertions above and be useless.
    assert seen[0]["cuts"]["elevation"] != seen[-1]["cuts"]["elevation"]
    # And the settle is a different FIELD of the last frame, not a fourth frame.
    assert settled["cuts"]["elevation"] != seen[-1]["cuts"]["elevation"]


def _engine_grid(req: dict, monkeypatch, *, diffraction: bool):
    """The engine's own field for `req` at `CUT_ELEVS`, one bearing, and the
    knots of the antenna it solved.

    Built through the adapter's own factory, with `_terrain_from_request`
    monkeypatched when the diffracted field is wanted — the app pins it specular
    there, and reaching around that seam with a hand-rolled engine would make
    this a comparison of two guesses about what the server builds.

    Both frequencies are set the way the socket's solve sets them.
    `_build_builder` reads a design's parameters by their own names, so the
    request's `design_freq_mhz` never reaches the builder's `design_freq`.
    Without the second assignment below this is the inverted V cut for the
    design's default 28.47 MHz, solved at 21.2: a different antenna, whose
    pattern differs from the socket's by up to 3.16 dB (#1501). The knots come
    back so the caller checks it is the same antenna instead of assuming it.
    """
    real = adapter._terrain_from_request
    if diffraction:
        monkeypatch.setattr(
            adapter,
            "_terrain_from_request",
            lambda r: dataclasses.replace(real(r), diffraction=True),
        )
    cls = importlib.import_module(f"antennaknobs.designs.{GEOMETRY}").Builder
    builder = adapter._build_builder(cls, req)
    builder.freq = FREQ
    builder.design_freq = FREQ
    eng = adapter._make_momwire_engine(req, builder)
    if req.get("ground_model") == "terrain":
        assert eng._ground[0] == "terrain"
        assert eng._ground[1].diffraction is diffraction, (
            "the engine was built with the wrong field — this test would compare "
            "one field's cut against the other's grid and call the gap a defect"
        )
    # ONE azimuth column, the cut's own bearing. `far_field` requires
    # del_phi * n_phi == 360, so n_phi=1 asks for phi=0 alone — 90 directions
    # instead of 32400, which is what keeps a diffracted grid inside the
    # suite's per-test time budget.
    assert EL_AZ == 0.0, "the single-column grid below is phi = 0"
    ff = eng.far_field(n_theta=90, n_phi=1, del_theta=1, del_phi=360)
    phis = np.asarray(ff.phis, dtype=float)
    # n_phi=1 closes the circle, so the grid comes back with phi = 0 and 360.
    # Column 0 is the bearing asked for; assert it rather than assume it.
    assert abs(phis[0]) < 1e-9, phis
    # `thetas` is already in DEGREES (see tests/test_terrain_utd_engine_1373.py) —
    # converting again silently lands every lookup on the same row.
    els = 90.0 - np.asarray(ff.thetas, dtype=float)
    rows = [int(np.argmin(np.abs(els - e))) for e in CUT_ELEVS]
    # Whole-degree elevations on a del_theta=1 grid: the nearest row IS the
    # angle, so the comparison is exact and not a nearest-neighbour read.
    assert np.allclose(els[rows], CUT_ELEVS), (els[rows], CUT_ELEVS)
    knots = np.concatenate([w.knot_positions for w in eng.current_distribution()])
    return np.asarray(ff.rings)[rows, 0], knots


def _settled_cut(client, req: dict, *, diffraction: bool):
    """The elevation cut the socket serves for `req`, and the knots of the
    antenna it solved."""
    with client.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps(req))
        result = json.loads(ws.receive_text())
        msg = {
            "_kind": "cuts",
            "solve_id": result["solve_id"],
            "az_elev_deg": AZ_EL,
            "elev_az_deg": EL_AZ,
            "elev_angles_deg": CUT_ELEVS,
        }
        if diffraction:
            msg["diffraction"] = True
        ws.send_text(json.dumps(msg))
        reply = json.loads(ws.receive_text())
    assert reply["ok"] and reply["cuts"]["diffraction"] is diffraction
    assert reply["cuts"]["elev_angles_deg"] == pytest.approx(CUT_ELEVS)
    knots = np.concatenate([np.asarray(w["knot_positions"]) for w in result["wires"]])
    return np.asarray(reply["cuts"]["elevation"]), knots


# The cut ships dBi rounded to three decimals (`_pattern_cuts`); the engine grid
# is unrounded. Measured 2026-09-15 on the same antenna: at most 0.001 dB, for
# both fields over the levee, and over flat ground, PEC and free space.
CUT_TOL_DB = 0.005


def _report(name, cut, grid):
    return f"{name}: " + ", ".join(
        f"{e:g} deg {c:+.3f} vs {g:+.3f}"
        for e, c, g in zip(CUT_ELEVS, cut, grid, strict=True)
    )


def test_the_settled_cut_is_the_engines_diffracted_field(client, monkeypatch):
    """Both fields' elevation cuts against the engine's own grids, sample by
    sample.

    The cuts path evaluates the composer over a moment set re-extracted from the
    JSON response, on azimuth-grouped slices of a grid it never builds; the
    engine takes the solver's own segment dipoles on its own grid. On the same
    antenna those are the same field, so the bar is the cut's rounding and not a
    tolerance for a second implementation.
    """
    req = _req(6.1)
    diff_cut, knots = _settled_cut(client, req, diffraction=True)
    spec_cut, _ = _settled_cut(client, req, diffraction=False)
    spec_grid, spec_knots = _engine_grid(req, monkeypatch, diffraction=False)
    diff_grid, diff_knots = _engine_grid(req, monkeypatch, diffraction=True)
    assert np.array_equal(knots, spec_knots) and np.array_equal(knots, diff_knots), (
        "the engine solved a different antenna from the socket's, so any gap "
        "below would be geometry and not the composer"
    )

    spec_gap = np.max(np.abs(spec_cut - spec_grid))
    diff_gap = np.max(np.abs(diff_cut - diff_grid))
    assert spec_gap < CUT_TOL_DB, _report("specular", spec_cut, spec_grid)
    assert diff_gap < CUT_TOL_DB, _report("diffracted", diff_cut, diff_grid)

    # Not vacuous: the specular cut is nowhere near the diffracted grid, so this
    # is a test of WHICH FIELD was composed and not only of the plumbing.
    assert np.max(np.abs(spec_cut - diff_grid)) > 1.0


def test_the_flat_ground_cut_is_the_engines_field(client, monkeypatch):
    """The same check over flat finite ground, where the specular composer draws
    the cuts all the time rather than only while a knob moves."""
    req = {k: v for k, v in _req(6.1).items() if k != "terrain"}
    req["ground_model"] = "fast"
    cut, knots = _settled_cut(client, req, diffraction=False)
    grid, eng_knots = _engine_grid(req, monkeypatch, diffraction=False)
    assert np.array_equal(knots, eng_knots)
    assert np.max(np.abs(cut - grid)) < CUT_TOL_DB, _report("flat ground", cut, grid)

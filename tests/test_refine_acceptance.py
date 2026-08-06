"""Acceptance scenarios for adaptive refinement (issue #744).

The showcase failures from the issue, measured end to end against the real
solver rather than against synthetic curves:

  (a) the elevation cut of ``dipoles.invvee`` 15 m up on the 10 m band —
      ~1.4λ, a 5–6 lobe pattern whose nulls a fixed 180-point circle draws
      with visible corners;
  (b) a sharp series resonance on the freq sweep, where the fixed 41-point
      grid steps straight past the VSWR minimum.

Both are measured in DISPLAY space, with the chart's own maps, as the
worst chord deviation of the drawn polyline — how far the picture is from
the curve, in fractions of the plot extent. See lib/refine.ts's
DEVIATION_TOLERANCE for why that, and not the turn angle, is the criterion:
a resolved VSWR notch still turns ~177° at its vertex because the true
curve genuinely spikes there, so a turn-angle target is unreachable on
exactly the features that motivate refinement.

The planner below MIRRORS src/lib/refine.ts (planRefinement). That file and
its vitest suite are authoritative for the criterion; this mirror exists so
the acceptance can be measured against real physics, which only the Python
side can produce.
"""

from __future__ import annotations

import json
import math

import numpy as np
import pytest
from starlette.testclient import TestClient

from antennaknobs.web.server import app

DEVIATION_TOLERANCE = 0.003
MIN_SEGMENT = 0.004


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


# ---- display-space measurement (mirrors lib/refine.ts) ---------------------


def chord_deviations(pts: np.ndarray, closed: bool) -> np.ndarray:
    """Perpendicular distance from each vertex to its neighbours' chord —
    the error the drawn polyline carries there."""
    prev = np.roll(pts, 1, axis=0)
    nxt = np.roll(pts, -1, axis=0)
    chord = nxt - prev
    a = pts - prev
    length = np.hypot(chord[:, 0], chord[:, 1])
    cross = np.abs(a[:, 0] * chord[:, 1] - a[:, 1] * chord[:, 0])
    dev = np.where(length > 0, cross / np.maximum(length, 1e-300), np.hypot(*a.T))
    if not closed:
        dev[0] = dev[-1] = 0.0
    return dev


def max_deviation(pts: np.ndarray, closed: bool) -> float:
    return float(np.max(chord_deviations(pts, closed)))


def plan_refinement(
    t: list[float],
    projections: list[np.ndarray],
    budget: int,
    closed: bool = False,
    period: float = 0.0,
) -> list[float]:
    """Greedy midpoint insertion into the worst intervals, children scored
    by the smooth-curve estimate "deviation is O(h²)"."""
    n = len(t)
    if budget <= 0 or n < 3:
        return []
    devs = np.zeros(n)
    for p in projections:
        devs = np.maximum(devs, chord_deviations(p, closed))
    work = []
    for j in range(n if closed else n - 1):
        k = (j + 1) % n
        b = t[0] + period if k == 0 else t[k]
        length = max(float(np.hypot(*(p[k] - p[j]))) for p in projections)
        work.append([t[j], b, max(devs[j], devs[k]), length])
    out: list[float] = []
    while len(out) < budget:
        best, best_score = -1, 0.0
        for i, (_, _, dev, length) in enumerate(work):
            if dev <= DEVIATION_TOLERANCE or length <= MIN_SEGMENT:
                continue
            if dev > best_score:
                best, best_score = i, dev
        if best < 0:
            break
        a, b, dev, length = work[best]
        mid = 0.5 * (a + b)
        out.append(mid % period if period > 0 else mid)
        work[best] = [a, mid, dev / 4, length / 2]
        work.append([mid, b, dev / 4, length / 2])
    return sorted(out)


def cut_projection(dbi, angles_deg) -> np.ndarray:
    """FarFieldChart's polar map, normalized to a plot extent of 1."""
    dbi = np.asarray(dbi, dtype=float)
    top = max(10.0, math.ceil(float(np.max(dbi)) + 1.0))
    frac = np.clip((dbi - (-20.0)) / (top - (-20.0)), 0.0, 1.0) * 0.5
    t = np.radians(np.asarray(angles_deg, dtype=float))
    return np.stack([frac * np.cos(t), frac * np.sin(t)], axis=-1)


def sweep_projections(freqs, z_re, z_im, z0=50.0) -> list[np.ndarray]:
    """SweepChart's linear-MHz x axis with both y domains, plus the Smith
    Γ locus — the union of everything one sweep array has to draw well."""
    f = np.asarray(freqs, dtype=float)
    r = np.asarray(z_re, dtype=float)
    x = np.asarray(z_im, dtype=float)
    denom = (r + z0) ** 2 + x**2
    g_re = (r * r - z0 * z0 + x * x) / denom
    g_im = (2 * x * z0) / denom
    g_mag = np.hypot(g_re, g_im)
    px = (f - f[0]) / (f[-1] - f[0])
    vswr = np.where(g_mag >= 1, 99.0, np.minimum((1 + g_mag) / (1 - g_mag), 99.0))
    with np.errstate(divide="ignore"):
        s11 = np.where(g_mag <= 0, -60.0, np.maximum(20 * np.log10(g_mag), -60.0))
    return [
        np.stack([px, np.clip((vswr - 1) / 9, 0, 1)], axis=-1),
        np.stack([px, np.clip((s11 + 30) / 30, 0, 1)], axis=-1),
        np.stack([(g_re + 1) / 2, (g_im + 1) / 2], axis=-1),
    ]


# ---- (a) high inverted vee: multi-lobe elevation cut -----------------------

# The frontend's per-cut budget (components/charts/cuts.ts).
CUT_REFINE_BUDGET = 120
CUT_REFINE_ROUND_BUDGET = 40

_INVVEE_15M = {
    "geometry": "dipoles.invvee",
    "base": 15.0,
    "measurement_freq_mhz": 28.5,
    "momwire_model": "bspline",
    "ground": True,
    "az_elev_deg": 15.0,
    "elev_az_deg": 0.0,
}


def _ws_solve(client: TestClient, req: dict) -> dict:
    """Solves arrive over /ws, not a POST route — same shape the workbench
    uses, so the cuts the benchmark reads are the ones the UI would draw."""
    with client.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps(req))
        return json.loads(ws.receive_text())


def test_invvee_15m_elevation_cut_is_multi_lobed(client: TestClient):
    """Sanity: the benchmark really is the pattern the issue describes."""
    out = _ws_solve(client, _INVVEE_15M)
    el = np.asarray(out["cuts"]["elevation"])
    upper = el[:90]  # t in [0, 180): the above-horizon half
    lobes = sum(
        1
        for i in range(1, len(upper) - 1)
        if upper[i] > upper[i - 1] and upper[i] > upper[i + 1]
    )
    assert 4 <= lobes <= 8, f"expected the 5-6 lobe fan, saw {lobes}"


def test_invvee_15m_elevation_cut_refines_under_budget(client: TestClient):
    solve = _ws_solve(client, _INVVEE_15M)
    solve_id = solve["solve_id"]

    angles = [(360.0 * i) / 180 for i in range(180)]
    dbi = solve["cuts"]["elevation"]
    before = max_deviation(cut_projection(dbi, angles), closed=True)

    spent = 0
    while spent < CUT_REFINE_BUDGET:
        budget = min(CUT_REFINE_ROUND_BUDGET, CUT_REFINE_BUDGET - spent)
        added = plan_refinement(
            angles,
            [cut_projection(dbi, angles)],
            budget,
            closed=True,
            period=360.0,
        )
        if not added:
            break
        spent += len(added)
        resp = client.post(
            "/cuts",
            json={
                "solve_id": solve_id,
                "az_elev_deg": 15.0,
                "elev_az_deg": 0.0,
                "elev_angles_deg": sorted(angles + added),
            },
        )
        assert resp.status_code == 200
        cuts = resp.json()
        angles = cuts["elev_angles_deg"]
        dbi = cuts["elevation"]

    after = max_deviation(cut_projection(dbi, angles), closed=True)
    assert spent <= CUT_REFINE_BUDGET
    assert len(angles) <= 180 + CUT_REFINE_BUDGET
    # The acceptance claim: the nulls stop reading as corners. Measured
    # 0.0336 -> 0.0027 of the plot extent for 78 of the 120-point budget
    # (258 samples) — from ~12 px of error on a 350 px chart to under one.
    assert after < before / 5, f"refinement barely helped: {before} -> {after}"
    assert after < 2 * DEVIATION_TOLERANCE


# ---- (b) sharp resonance: the VSWR notch on the freq sweep -----------------

# The frontend's sweep budget (lib/sweep.ts).
SWEEP_REFINE_BUDGET = 48
SWEEP_REFINE_ROUND_BUDGET = 12


def _sweep(client: TestClient, req: dict, freqs: list[float]):
    resp = client.post("/sweep", json={**req, "freqs_mhz": freqs})
    assert resp.status_code == 200
    z_re, z_im = [], []
    for line in resp.text.splitlines():
        if not line.strip():
            continue
        pt = json.loads(line)
        if pt.get("done") or pt.get("error"):
            continue
        z_re.append(pt["z_re"])
        z_im.append(pt["z_im"])
    return z_re, z_im


# A narrow, high-Q feed: the inverted vee's own resonance swept over a wide
# window, so the notch is a small fraction of the span — the shape the fixed
# grid steps past.
_SWEEP_REQ = {
    "geometry": "dipoles.invvee",
    "measurement_freq_mhz": 28.47,
    "momwire_model": "bspline",
}


def _vswr_min(z_re, z_im, z0=50.0) -> float:
    r = np.asarray(z_re)
    x = np.asarray(z_im)
    g = np.hypot(
        (r * r - z0 * z0 + x * x) / ((r + z0) ** 2 + x**2),
        (2 * x * z0) / ((r + z0) ** 2 + x**2),
    )
    return float(np.min(np.where(g >= 1, 99.0, (1 + g) / (1 - g))))


def test_sharp_resonance_sweep_refines_the_vswr_notch(client: TestClient):
    lo, hi = 28.47 * 0.6, 28.47 * 1.6  # deliberately wide: a narrow notch
    freqs = list(np.exp(np.linspace(math.log(lo), math.log(hi), 41)))
    z_re, z_im = _sweep(client, _SWEEP_REQ, freqs)
    before_dev = max(
        max_deviation(p, closed=False) for p in sweep_projections(freqs, z_re, z_im)
    )
    before_vswr = _vswr_min(z_re, z_im)

    spent = 0
    while spent < SWEEP_REFINE_BUDGET:
        budget = min(SWEEP_REFINE_ROUND_BUDGET, SWEEP_REFINE_BUDGET - spent)
        added = plan_refinement(freqs, sweep_projections(freqs, z_re, z_im), budget)
        if not added:
            break
        spent += len(added)
        add_re, add_im = _sweep(client, {**_SWEEP_REQ, "_refine": True}, added)
        merged = sorted(zip(freqs + added, z_re + add_re, z_im + add_im, strict=True))
        freqs = [m[0] for m in merged]
        z_re = [m[1] for m in merged]
        z_im = [m[2] for m in merged]

    after_dev = max(
        max_deviation(p, closed=False) for p in sweep_projections(freqs, z_re, z_im)
    )
    after_vswr = _vswr_min(z_re, z_im)

    assert spent <= SWEEP_REFINE_BUDGET
    assert len(freqs) == 41 + spent
    # Deeper-or-equal minimum: extra points near resonance can only find a
    # better match than the grid stepped past.
    assert after_vswr <= before_vswr + 1e-9
    # And the picture is strictly better where it was worst: measured
    # 0.284 -> 0.0029 of the plot extent for 42 of the 48-point budget, i.e.
    # the notch goes from "not drawn at all" to sub-pixel.
    assert after_dev < before_dev / 10
    assert after_dev < 2 * DEVIATION_TOLERANCE

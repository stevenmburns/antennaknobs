"""AK#1757, sweep framework step 5, unit 4b: the workbench draws an
analysis's crosses over measurement planes, designs and a family, one curve
per cell, as ``antennaknobs analyze`` computes them.

What ``/analyses`` serves for each kind (``web/analyses_offer.py``) is
checked against the CLI's own cells (`analysis_run.cells`: labels, values,
refusals), and then, per kind, the SERVED solve for one cell (the request
the chart sends for it, built from what ``/analyses`` served) against the
CLI's ``analyze`` number for the same cell:

- planes: ``/sweep`` with that ``plane`` on the E5 deck (a user design);
- designs: ``/param_sweep`` of the other design at its own defaults (E7);
- families: ``/param_sweep`` with the step knob set to the cell's value (E2).

Everything solves in free space on both sides (``--ground free`` and
``ground: false``), at one pinned density where the sweep is not a density
ladder.
"""

from __future__ import annotations

import importlib
import itertools
import json
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from antennaknobs import analyses as an
from antennaknobs import analysis_run as ar
from antennaknobs.builder import AntennaBuilder
from antennaknobs.cli import cli, get_builder

sw = importlib.import_module("antennaknobs.sweep")

FIXTURES = Path(__file__).parent / "fixtures"
E5_DECK = FIXTURES / "simnec_ac6la_1679" / "Bydipole-TL-Xfmr-CLC.ssn"
E5_PLANES = ("rig", "C1", "L1", "C2", "B", "R1", "T1", "feed")
INVVEE = "dipoles.invvee"
APEX = "dipoles.invvee_apex"
# The CLI's cells and the served solves agree to the last bits where both
# run the same code; this is the bar the unit-1 oracles hold.
REL = 1e-9


@pytest.fixture(scope="module")
def client() -> TestClient:
    from antennaknobs.web import server

    return TestClient(server.app)


def _offer(monkeypatch, cls, analyses):
    monkeypatch.setattr(cls, "build_analyses", lambda self: list(analyses))


def _invvee_cls():
    return type(get_builder(INVVEE)())


def _capture_run(monkeypatch):
    got = []
    inner = ar.run

    def wrapped(*args, **kwargs):
        out = inner(*args, **kwargs)
        got.append(out)
        return out

    monkeypatch.setattr(ar, "run", wrapped)
    return got


def _served(client, req, name) -> dict:
    r = client.post("/analyses", json=req)
    assert r.status_code == 200, r.text
    (entry,) = [a for a in r.json()["analyses"] if a["name"] == name]
    return entry["workbench"]


def _records(text: str) -> list[dict]:
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def _defaults(client, geometry) -> dict:
    """A fresh session's knobs for ``geometry``: its schema's defaults, as
    the catalog seeds them (``seedDefaults``)."""
    (ex,) = [
        e for e in client.get("/examples").json()["examples"] if e["name"] == geometry
    ]
    return {
        p["name"]: p["default"]
        for p in ex["param_schema"]
        if "default" in p and "params" not in p
    }


def _max_rel(a, b) -> float:
    a, b = np.asarray(a, dtype=complex), np.asarray(b, dtype=complex)
    return float(np.max(np.abs(a - b) / np.abs(b)))


# ── what /analyses serves ─────────────────────────────────────────────────


def test_e7_serves_its_designs_in_written_order_with_their_own_ladders(client):
    w = _served(
        client,
        {"geometry": INVVEE, "design_freq_mhz": 28.47, "measurement_freq_mhz": 28.47},
        "feed spellings",
    )
    assert w["runs"] is True
    # The product's order, as written: designs, then engines.
    assert w["axes"] == ["designs", "engines"]
    assert [d["name"] for d in w["designs"]] == [INVVEE, APEX]
    assert all(d["refused"] is None for d in w["designs"])
    # Each design's own ladder: the CLI's rungs on that design.
    for d in w["designs"]:
        assert d["param"] == "n_per_wire"
        assert d["values"] == list(sw.NOMINAL_NSEGS_LADDER)
    assert w["planes"] is None and w["step"] is None


def test_e2s_family_serves_its_knob_values_and_the_clis_labels(client):
    w = _served(client, {"geometry": INVVEE}, "tuning family")
    assert w["runs"] is True and w["axes"] == ["step"]
    b = get_builder(INVVEE)()
    a = ar.find(b, "tuning family")
    labels = [c.label for c in ar.cells(a, "momwire", b)]
    assert w["step"] == {
        "knob": "angle_deg",
        "values": [0.0, 15.0, 30.0, 45.0, 60.0],
        "labels": labels,
    }
    assert labels[2] == "angle_deg = 30"


def test_a_design_the_catalog_lacks_or_whose_knob_does_not_resolve_is_refused(
    monkeypatch, client
):
    a = an.Analysis(
        "d",
        an.Sweep("length_factor", 0.95, 1.0, points=3),
        cross=an.Cross(designs=(INVVEE, "nope.nope", "beams.yagi")),
    )
    _offer(monkeypatch, _invvee_cls(), [a])
    w = _served(client, {"geometry": INVVEE}, "d")
    got = {d["name"]: d for d in w["designs"]}
    assert got[INVVEE]["refused"] is None
    assert got[INVVEE]["values"] == pytest.approx([0.95, 0.975, 1.0])
    assert got["nope.nope"]["refused"].startswith("unknown geometry 'nope.nope'")
    # The CLI's own reason for the cell (an.resolve on that design).
    yagi = get_builder("beams.yagi")()
    assert got["beams.yagi"]["refused"] == an.resolve("length_factor", yagi).reason


def test_a_density_family_stays_refused_in_the_workbench_as_in_the_cli(
    monkeypatch, client
):
    a = an.Analysis(
        "dens fam",
        an.Sweep("length_factor", 0.95, 1.0, points=3),
        cross=an.Cross(step=an.Sweep(an.DENSITY, values=(8, 12))),
    )
    _offer(monkeypatch, _invvee_cls(), [a])
    w = _served(client, {"geometry": INVVEE}, "dens fam")
    assert w["runs"] is False
    assert "a map axis or family over the density knob" in w["why"]


# ── planes: the E5 deck, as a user design ─────────────────────────────────


@pytest.fixture
def e5_user(tmp_path, monkeypatch):
    import antennaknobs.web.examples as examples
    import antennaknobs.web.user_designs as web_user_designs

    monkeypatch.setenv("ANTENNAKNOBS_USER_DIR", str(tmp_path))
    monkeypatch.delenv("ANTENNAKNOBS_TRUST_USER_DESIGNS", raising=False)
    (tmp_path / E5_DECK.name).write_bytes(E5_DECK.read_bytes())
    web_user_designs.refresh()
    yield f"user.{E5_DECK.stem}"
    for key in [k for k in examples.REGISTRY if k.startswith("user.")]:
        del examples.REGISTRY[key]


PLANES_SWR = an.band_swr(
    name="planes",
    sweep=an.Sweep(an.FREQUENCY, 14.0, 14.3, points=4),
    cross=an.Cross(planes=("rig", "T1", "nowhere")),
    views=(an.Swr(),),
)


def test_planes_serve_each_plane_and_refuse_one_the_deck_lacks_in_the_clis_words(
    monkeypatch, client, e5_user, capsys, tmp_path
):
    _offer(monkeypatch, AntennaBuilder, [PLANES_SWR])
    w = _served(client, {"geometry": e5_user}, "planes")
    assert w["axes"] == ["planes"]
    assert [p["name"] for p in w["planes"]] == ["rig", "T1", "nowhere"]
    assert w["planes"][0]["refused"] is None and w["planes"][1]["refused"] is None
    runs = _capture_run(monkeypatch)
    cli(["analyze", "--builder", f"@{E5_DECK}", "--analysis", "planes",
         "--ground", "free", "--fn", str(tmp_path / "p.png")])  # fmt: skip
    capsys.readouterr()
    assert w["planes"][2]["refused"] == runs[0]["refused"]["nowhere"]
    assert w["planes"][2]["refused"].startswith(
        "no plane 'nowhere' on this design; it offers " + ", ".join(E5_PLANES)
    )


def test_a_served_plane_cell_is_the_clis_curve_at_that_plane(
    monkeypatch, client, e5_user, capsys, tmp_path
):
    _offer(monkeypatch, AntennaBuilder, [PLANES_SWR])
    w = _served(client, {"geometry": e5_user}, "planes")
    runs = _capture_run(monkeypatch)
    cli(["analyze", "--builder", f"@{E5_DECK}", "--analysis", "planes",
         "--ground", "free", "--engine", "momwire:bspline",
         "--nominal-nsegs", "15", "--fn", str(tmp_path / "p.png")])  # fmt: skip
    capsys.readouterr()
    worst = 0.0
    for p in w["planes"]:
        if p["refused"]:
            continue
        xs, want = runs[0]["curves"][p["name"]]
        # The chart's plane cell: the session's request with that plane.
        body = {
            "geometry": e5_user,
            "solver": "momwire",
            "momwire_model": "bspline",
            "n_per_wire": 15,
            "ground": False,
            "freqs_mhz": [float(x) for x in xs],
            "plane": p["name"],
        }
        recs = [
            r for r in _records(client.post("/sweep", json=body).text) if "z_re" in r
        ]
        got = [complex(r["z_re"], r["z_im"]) for r in recs]
        assert [r["freq_mhz"] for r in recs] == pytest.approx(list(xs), rel=0, abs=0)
        worst = max(worst, _max_rel(got, want))
    assert worst <= REL, worst
    # Adversarial: the two planes are different measurements.
    rig, t1 = (runs[0]["curves"][n][1][0] for n in ("rig", "T1"))
    assert abs(rig - t1) > 1.0


# ── designs (E7) ──────────────────────────────────────────────────────────


def test_a_served_design_cell_is_the_clis_curve_for_that_design(
    monkeypatch, client, capsys, tmp_path
):
    ladder = an.Sweep(an.DENSITY, values=(8, 12, 17))
    a = an.convergence(
        name="spellings",
        sweep=ladder,
        cross=(
            an.Cross(designs=(INVVEE, APEX)),
            an.Cross(engines=("momwire:bspline",)),
        ),
    )
    _offer(monkeypatch, _invvee_cls(), [a])  # invvee_apex inherits it
    w = _served(client, {"geometry": INVVEE}, "spellings")
    runs = _capture_run(monkeypatch)
    cli(["analyze", "--builder", INVVEE, "--analysis", "spellings",
         "--ground", "free", "--fn", str(tmp_path / "d.png")])  # fmt: skip
    capsys.readouterr()
    worst = 0.0
    for d in w["designs"]:
        label = f"{d['name']}, momwire:bspline"
        rungs, want = runs[0]["curves"][label]
        assert d["values"] == rungs == [8, 12, 17]
        # The chart's design cell: that design at its own defaults (a fresh
        # session's knobs and design frequency), the session's slot and
        # ground.
        body = {
            "geometry": d["name"],
            "variant": "default",
            **_defaults(client, d["name"]),
            "design_freq_mhz": 28.47,
            "measurement_freq_mhz": 28.47,
            "solver": "momwire",
            "momwire_model": "bspline",
            "ground": False,
            "param": d["param"],
            "values": d["values"],
        }
        recs = _records(client.post("/param_sweep", json=body).text)[:-1]
        got = [complex(r["z_re"], r["z_im"]) for r in recs]
        worst = max(worst, _max_rel(got, want))
    assert worst <= REL, worst
    bridge = runs[0]["curves"][f"{INVVEE}, momwire:bspline"][1][-1]
    apex = runs[0]["curves"][f"{APEX}, momwire:bspline"][1][-1]
    assert abs(bridge - apex) > 1.0, (bridge, apex)


# ── families (E2's family) ────────────────────────────────────────────────


def test_a_served_family_cell_is_the_clis_curve_at_that_step(
    monkeypatch, client, capsys, tmp_path
):
    fam = an.Analysis(
        "fam",
        an.Sweep("length_factor", 0.95, 1.0, points=3),
        cross=an.Cross(step=an.Sweep("angle_deg", values=(0, 30, 60))),
    )
    _offer(monkeypatch, _invvee_cls(), [fam])
    w = _served(client, {"geometry": INVVEE}, "fam")
    runs = _capture_run(monkeypatch)
    cli(["analyze", "--builder", INVVEE, "--analysis", "fam", "--ground", "free",
         "--engine", "momwire:bspline", "--nominal-nsegs", "15",
         "--fn", str(tmp_path / "f.png")])  # fmt: skip
    capsys.readouterr()
    step = w["step"]
    assert step["labels"] == list(runs[0]["curves"])
    worst = 0.0
    for value, label in zip(step["values"], step["labels"], strict=True):
        xs, want = runs[0]["curves"][label]
        assert w["values"] == pytest.approx(list(xs), rel=0, abs=0)
        # The chart's family cell: the session's knobs, the step knob set.
        body = {
            "geometry": INVVEE,
            **_defaults(client, INVVEE),
            step["knob"]: value,
            "design_freq_mhz": 28.47,
            "measurement_freq_mhz": 28.47,
            "solver": "momwire",
            "momwire_model": "bspline",
            "n_per_wire": 15,
            "ground": False,
            "param": w["param"],
            "values": w["values"],
        }
        recs = _records(client.post("/param_sweep", json=body).text)[:-1]
        got = [complex(r["z_re"], r["z_im"]) for r in recs]
        worst = max(worst, _max_rel(got, want))
    assert worst <= REL, worst
    r_mid = [runs[0]["curves"][lab][1][1].real for lab in step["labels"]]
    assert min(abs(a - b) for a, b in itertools.pairwise(r_mid)) > 5.0

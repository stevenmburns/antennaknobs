"""`verticals.m0agp_invl`: M0AGP's 160 m inverted L and his DX-gain study.

The design (QRZ thread 1005128, first post) carries its study as its own
``Builder.build_studies()`` method, so the study is listed on this design's
tab only and resolves as ``verticals.m0agp_invl:DX gain vs the vertical``.

- the geometry: the L, its two radials along +-x, a 0 ft top wire dropped;
- it solves in free space, over finite-fast and over Sommerfeld ground;
- the study is a method study, offered on its own tab only, and offered (and
  runnable) on the hosted instance: it is all declarative, no callable;
- the study's nine points reproduce the table the user design gave, and the
  catalog study equals that same file served as a user design bit for bit.
"""

from __future__ import annotations

import inspect
import json
import os
import subprocess
import sys

import pytest
from starlette.testclient import TestClient

from antennaknobs import analysis_run as ar
from antennaknobs import studies
from antennaknobs.cli import cli, get_builder
from antennaknobs.designs.verticals import m0agp_invl

DESIGN = "verticals.m0agp_invl"
NAME = "DX gain vs the vertical"
STUDY = f"{DESIGN}:{NAME}"
FT = 0.3048

# M0AGP's table as `analyze --study` reads it on momwire (the app's default
# engine) at azimuth 0: each inverted L's DX gain relative to the full-size
# vertical, dB, by vertical section in feet. Two boxes reading the same
# deck differ in the third decimal (the hold stops at a few 1e-5 ohm of
# reactance), so the pin is to 0.01 dB.
TABLE = {
    20.0: -9.495,
    30.0: -5.845,
    40.0: -3.689,
    50.0: -2.367,
    60.0: -1.532,
    70.0: -0.984,
    80.0: -0.615,
    90.0: -0.365,
    100.0: -0.196,
}
TOL_DB = 0.01


@pytest.fixture(scope="module")
def client() -> TestClient:
    from antennaknobs.web import server

    return TestClient(server.app)


def _listing(client, geometry):
    r = client.post("/analyses", json={"geometry": geometry})
    assert r.status_code == 200, r.text
    return {a["name"]: a for a in r.json()["analyses"]}


# ── the antenna ──────────────────────────────────────────────────────────


def _segments(b):
    return [(tuple(w.p0), tuple(w.p1)) for w in b.build_wires()]


def test_the_l_its_radials_and_its_feed():
    b = get_builder(DESIGN)()
    z = b.base
    wires = _segments(b)
    feed, riser, top, *radials = wires
    assert feed == ((0.0, 0.0, z), (0.0, 0.0, z + 0.05))
    assert riser[1] == pytest.approx((0.0, 0.0, z + 70.0 * FT))
    # The top wire runs along +y from the riser's top.
    assert top[1] == pytest.approx((0.0, 63.9 * FT, z + 70.0 * FT))
    # Two quarter-wave radials along +x and -x, perpendicular to the top.
    quarter = 0.25 * b.design_wavelength
    assert [r[1] for r in radials] == [
        pytest.approx((quarter, 0.0, z)),
        pytest.approx((-quarter, 0.0, z), abs=1e-9),
    ]
    assert b.build_wires()[0].ex == 1 + 0j


def test_a_top_wire_of_zero_feet_is_the_plain_vertical():
    b = get_builder(DESIGN)()
    b.horiz_ft = 0.0
    wires = _segments(b)
    # Feed, riser and two radials: no zero-length wire, nothing along y.
    assert len(wires) == 4
    assert max(abs(p[1]) for w in wires for p in w) < 1e-9


def test_the_hold_knob_is_bounded_by_its_ui_range():
    ui = get_builder(DESIGN).default_params["ui_params"]
    assert (ui["horiz_ft"]["min"], ui["horiz_ft"]["max"]) == (1.0, 135.0)
    assert ui["default_view"] == "iso"


# ── it solves on the default engine, over each ground ────────────────────


def _solve(**kw):
    from antennaknobs.web import server

    return server.solve({"geometry": DESIGN, **kw})


@pytest.mark.parametrize(
    "kw, applied",
    [
        ({"ground": False}, "free"),
        ({"ground": True, "ground_model": "fast"}, "refl-coef"),
    ],
)
def test_it_solves_free_and_over_finite_fast(kw, applied):
    r = _solve(**kw)
    assert r["solver"] == "momwire" and r["ground_model_applied"] == applied
    # A short top-loaded monopole on two radials: low R, capacitive off its
    # Sommerfeld resonance (13.9 - j25.8 free, 15.6 - j11.8 fast on momwire).
    assert 5.0 < r["z_in_re"] < 40.0, r["z_in_re"]
    assert -60.0 < r["z_in_im"] < 0.0, r["z_in_im"]


@pytest.mark.antenna_computation_check
def test_it_is_resonant_over_sommerfeld_where_it_was_cut():
    """70 ft of vertical and 63.9 ft of top were cut for resonance over
    Sommerfeld 13/0.005 (the study's ground, the app's default soil): it
    reads 29.81 + j0.12 ohm on momwire. ~6 s, the Sommerfeld table."""
    r = _solve(ground=True, ground_model="sommerfeld")
    assert r["ground_model_applied"] == "sommerfeld"
    assert r["z_in_re"] == pytest.approx(29.8, abs=1.0)
    assert abs(r["z_in_im"]) < 2.0, r["z_in_im"]


# ── the study: a method study, on its own tab only ───────────────────────


def test_the_study_is_this_designs_method_study():
    found = studies.of_builder(DESIGN, get_builder(DESIGN)())
    assert not found.blocked, found.blocked
    (st,) = found.studies
    assert st.name == STUDY and st.host == DESIGN and st.source == DESIGN
    assert st.includes(DESIGN)
    # Not a module-level study: the catalog's studies directory has no copy.
    assert STUDY not in {s.name for s in studies.discover().studies}
    a = st.analysis
    assert a.hold.adjust == ("horiz_ft",)
    (cross,) = a.crosses
    assert [s.name for s in cross.states] == ["inverted L", "vertical"]
    assert {s.design for s in cross.states} == {DESIGN}


def test_the_study_is_listed_under_its_own_design_only(capsys):
    cli(["analyze", "--list-studies", "--builder", DESIGN])
    assert STUDY in capsys.readouterr().out
    for other in ([], ["--builder", "verticals.inverted_l"]):
        cli(["analyze", "--list-studies", *other])
        assert STUDY not in capsys.readouterr().out


def test_the_study_is_served_on_its_own_tab_only(client):
    got = _listing(client, DESIGN)
    e = got[STUDY]
    assert e["study"] == {"source": DESIGN, "name": NAME}
    w = e["workbench"]
    assert w["runs"] is True, w.get("why")
    assert w["param"] == "vert_ft" and w["views"] == ["Metric", "Knobs"]
    assert w["hold"]["knobs"] == ["horiz_ft"]
    assert w["hold"]["bounds"] == {"horiz_ft": [1.0, 135.0]}
    for other in ("verticals.inverted_l", "verticals.vertical"):
        assert STUDY not in _listing(client, other)


def test_the_hosted_instance_offers_and_runs_it():
    """In a fresh interpreter with ANTENNAKNOBS_HOSTED set, as the Fly
    container starts: the study calls no metric function (a declarative
    ElevationWindow), so nothing refuses it."""
    code = f"""
import json
from starlette.testclient import TestClient
from antennaknobs.web import analyses_offer, server
assert server._HOSTED
r = TestClient(server.app).post("/analyses", json={{"geometry": {DESIGN!r}}})
assert r.status_code == 200, r.text
(e,) = [a for a in r.json()["analyses"] if a["name"] == {STUDY!r}]
from antennaknobs.cli import get_builder
from antennaknobs import studies
(st,) = studies.of_builder({DESIGN!r}, get_builder({DESIGN!r})()).studies
print(json.dumps({{"workbench": e["workbench"],
                  "refusal": analyses_offer.hosted_refusal(st.analysis)}}))
"""
    proc = subprocess.run(
        [sys.executable, "-c", code],
        env={**os.environ, "ANTENNAKNOBS_HOSTED": "1"},
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout.strip().splitlines()[-1])
    assert out["refusal"] is None
    assert out["workbench"]["runs"] is True, out["workbench"].get("why")
    assert out["workbench"]["views"] == ["Metric", "Knobs"]


# ── the study's numbers ──────────────────────────────────────────────────


def _run(name, tmp_path) -> dict:
    got = []
    inner = ar.run

    def wrapped(*args, **kwargs):
        out = inner(*args, **kwargs)
        got.append(out)
        return out

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(ar, "run", wrapped)
        cli(["analyze", "--study", name, "--fn", str(tmp_path / "m.png")])
    return got[-1]


@pytest.fixture(scope="module")
def catalog_run(tmp_path_factory):
    """The study through `analyze --study`, all nine points on momwire
    (~8 s on Haswell: 46 solves for the hold plus the reference)."""
    return _run(STUDY, tmp_path_factory.mktemp("m0agp"))


@pytest.mark.antenna_computation_check
def test_the_study_reproduces_the_table(catalog_run, capsys):
    capsys.readouterr()
    dx = catalog_run["metrics"]["DX gain"]
    curve = dx[f"{DESIGN}, inverted L"]
    assert curve.xs == tuple(TABLE)
    assert curve.reference == f"{DESIGN}, vertical"
    for x, want, got in zip(curve.xs, TABLE.values(), curve.relative, strict=True):
        assert got == pytest.approx(want, abs=TOL_DB), (x, got, want)
    # The vertical is a FIXED reference: solved once, drawn flat.
    ref = dx[f"{DESIGN}, vertical"]
    assert ref.fixed and ref.relative == (0.0,)
    # Every point held at resonance on the top wire.
    held = catalog_run["held"][f"{DESIGN}, inverted L"]
    assert len(held) == 9 and all(p.converged for p in held)
    assert all(abs(p.z.imag) < 1e-3 for p in held)
    # The top grows as the vertical shrinks, inside the hold's bounds.
    tops = [p.params["horiz_ft"] for p in held]
    assert tops == sorted(tops, reverse=True) and 1.0 < tops[-1] < tops[0] < 135.0


@pytest.mark.antenna_computation_check
def test_the_catalog_study_equals_the_user_design_bit_for_bit(
    catalog_run, tmp_path, monkeypatch, capsys
):
    """The same file served as a user design (its study's states naming
    ``user.m0agp_invl``, as the user design it was ported from does) gives
    the catalog's numbers exactly: the catalog route changes nothing."""
    import antennaknobs.web.user_designs as web_user_designs

    me = f'me = "{DESIGN}"'
    src = inspect.getsource(m0agp_invl)
    assert src.count(me) == 1
    designs = tmp_path / "designs"
    designs.mkdir()
    (designs / "m0agp_invl.py").write_text(src.replace(me, 'me = "user.m0agp_invl"'))
    monkeypatch.setenv("ANTENNAKNOBS_USER_DIR", str(designs))
    monkeypatch.setenv("ANTENNAKNOBS_STUDIES_DIR", str(tmp_path / "studies"))
    web_user_designs.refresh()
    try:
        user = _run(f"user.m0agp_invl:{NAME}", tmp_path)
    finally:
        monkeypatch.undo()
        web_user_designs.refresh()
    capsys.readouterr()
    ours = catalog_run["metrics"]["DX gain"]
    theirs = user["metrics"]["DX gain"]
    for state in ("inverted L", "vertical"):
        a, b = ours[f"{DESIGN}, {state}"], theirs[f"user.m0agp_invl, {state}"]
        assert (a.xs, a.values, a.relative) == (b.xs, b.values, b.relative)
    ah = catalog_run["held"][f"{DESIGN}, inverted L"]
    bh = user["held"]["user.m0agp_invl, inverted L"]
    assert [(p.params, p.z) for p in ah] == [(p.params, p.z) for p in bh]

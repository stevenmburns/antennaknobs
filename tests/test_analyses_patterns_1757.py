"""AK#1757, sweep framework step 7 unit 3: PATTERNS, an analysis with no
swept x (``sweep=None``), drawn by the pattern views, in the spec, the CLI and
the workbench.

The contract (docs/design/sweep-framework-step7.md, "Proposal §3 Patterns",
ruling 3):

- ``an.Elevation(az=...)``, ``an.Azimuth(el=...)`` and ``an.PatternTable()``
  are the views of a pattern and of nothing else: a pattern view on a swept
  analysis, an impedance view on a pattern and a hold on a pattern are
  refused by name when the value is built; a pattern is crossed like any
  analysis, under the same cap;
- a CLI cell's cut IS the design's pattern, sample for sample: checked
  bit-equal against ``antennaknobs compare_patterns`` (the route that existed
  before patterns) and against the engine's far field with the state's knobs
  set by hand;
- its metrics are the workbench compare table's function on the same solve
  (`far_field.refined_pattern_metrics` off the engine's gain evaluator), and a
  workbench cell's (``/pattern_cell``) are ``/pattern_metrics``' own and, in
  free space, bit-equal to the CLI cell's;
- ``to_code`` prints a pattern back and ``eval`` of that text is the value;
- ``--csv`` writes one block of rows per cut, a gain column per cell;
- a study may be a pattern: the CLI reference's Patterns study runs, and each
  of its cells is ``compare_patterns``' pattern of that design.
"""

from __future__ import annotations

import csv
import importlib
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from antennaknobs import analyses as an
from antennaknobs import analysis_run as ar
from antennaknobs import far_field, studies
from antennaknobs.cli import cli, get_builder, make_engine_factory, parse_ground

INVVEE = "dipoles.invvee"
YAGI = "beams.yagi"
ENGINE = "momwire:bspline"


@pytest.fixture(scope="module")
def client() -> TestClient:
    from antennaknobs.web import server

    return TestClient(server.app)


def _invvee():
    return get_builder(INVVEE)()


def _offer(monkeypatch, analyses):
    monkeypatch.setattr(type(_invvee()), "build_analyses", lambda self: list(analyses))


def _record(monkeypatch, module, name):
    calls = []
    inner = getattr(module, name)

    def wrapped(*args, **kwargs):
        out = inner(*args, **kwargs)
        calls.append((args, kwargs, out))
        return out

    monkeypatch.setattr(module, name, wrapped)
    return calls


def _catalog(name: str) -> an.Analysis:
    (a,) = [x for x in an.offered(_invvee()) if x.name == name]
    return a


HEIGHTS = (
    an.State("as built"),
    an.State("low mast", base=5.0),
    an.State("tall mast", base=12.0),
)


# ── the value ────────────────────────────────────────────────────────────


def test_a_pattern_has_no_sweep_and_the_pattern_views():
    a = an.Analysis(
        "tall vs as-built pattern",
        sweep=None,
        cross=an.Cross(states=(an.State("as built"), an.State("tall", base=12.0))),
        views=(an.Elevation(az=0), an.Azimuth(el=10), an.PatternTable()),
    )
    assert an.is_pattern(a) and a.sweeps == () and a.curves == 2
    assert an.patterns().views == (
        an.Elevation(az=0),
        an.Azimuth(el=10),
        an.PatternTable(),
    )
    assert an.patterns(name="x", cross=a.cross).sweep is None


@pytest.mark.parametrize(
    "view", [an.Rx(), an.Swr(), an.S11(), an.Smith(), an.Map(), an.Table(), an.Knobs()]
)
def test_an_impedance_view_on_a_pattern_is_refused_by_name(view):
    name = type(view).__name__
    with pytest.raises(ValueError, match=f"the {name} view draws against a swept x"):
        an.Analysis("p", sweep=None, views=(an.PatternTable(), view))


@pytest.mark.parametrize(
    "view", [an.Elevation(az=0), an.Azimuth(el=10), an.PatternTable()]
)
def test_a_pattern_view_on_a_swept_analysis_is_refused_by_name(view):
    name = type(view).__name__
    with pytest.raises(
        ValueError, match=f"the {name} view draws a far-field pattern.*give sweep=None"
    ):
        an.Analysis("s", an.Sweep("base"), views=(an.Rx(), view))


def test_the_default_views_and_a_hold_are_refused_on_a_pattern():
    # The Analysis default is the Rx view: a pattern names its own.
    with pytest.raises(ValueError, match="the Rx view draws against a swept x"):
        an.Analysis("p", sweep=None)
    with pytest.raises(ValueError, match="a hold optimises at every sweep point"):
        an.Analysis(
            "p",
            sweep=None,
            views=(an.PatternTable(),),
            hold=an.Hold("resonance", adjust=("length_factor",)),
        )


@pytest.mark.parametrize(
    ("make", "words"),
    [
        (lambda: an.Azimuth(el=0), "el is a whole number of degrees, 1..89"),
        (lambda: an.Azimuth(el=90), "el is a whole number of degrees, 1..89"),
        (lambda: an.Azimuth(el=10.5), "el is a whole number of degrees"),
        (lambda: an.Elevation(az=360), "az is a whole number of degrees, 0..359"),
        (lambda: an.Elevation(az=True), "az is a whole number of degrees"),
        (lambda: an.Elevation(az=float("nan")), "az is a whole number of degrees"),
    ],
)
def test_a_cut_off_the_far_field_grid_is_refused_by_name(make, words):
    with pytest.raises(ValueError, match=words):
        make()


def test_a_cut_is_named_by_keyword():
    with pytest.raises(TypeError):
        an.Elevation(0)  # an angle with no name reads as either axis


def test_a_pattern_over_the_cap_is_refused_when_listed():
    a = an.patterns(
        name="big",
        cross=(
            an.Cross(states=HEIGHTS),
            an.Cross(grounds=("free", "finite-fast", "pec")),
        ),
    )
    assert an.problems(a, _invvee()) == [
        "REFUSED: 3 states x 3 grounds = 9 curves, over the cap of 6"
    ]


@pytest.mark.parametrize(
    "a",
    [
        an.patterns(name="height patterns", cross=an.Cross(states=HEIGHTS)),
        an.Analysis(
            "two cuts",
            sweep=None,
            cross=an.Cross(designs=(INVVEE, YAGI)),
            views=(an.Azimuth(el=15), an.Elevation(az=90)),
            ground="finite-fast",
        ),
        an.patterns(
            name="freq family",
            cross=an.Cross(step=an.Sweep(an.FREQUENCY, values=(28.0, 29.0))),
        ),
    ],
)
def test_a_pattern_prints_back_as_code_and_evals_to_the_same_value(a):
    code = an.to_code(a)
    assert "sweep=None" in code or code.startswith("an.patterns(")
    assert eval(code, {"an": an}) == a


def test_the_catalog_height_patterns_list_runnable_and_print_back():
    a = _catalog("height patterns")
    b = _invvee()
    assert an.problems(a, b) == [] and ar.cli_gaps(a, b) == []
    assert ar.summary(a, b) == (
        "pattern at 28.47 MHz (freq); 3 patterns (3 states); views Elevation, "
        "PatternTable"
    )
    assert an.states_of(a) == HEIGHTS and a.ground == "finite-fast"
    assert eval(an.to_code(a), {"an": an}) == a


# ── the CLI: a cell's cut IS the design's pattern ─────────────────────────


def _run(monkeypatch, capsys, argv) -> dict:
    runs = _record(monkeypatch, ar, "_run_patterns")
    cli(["analyze", *argv])
    capsys.readouterr()
    return runs[-1][2]


def _grid_cut(ff, v) -> np.ndarray:
    """The cut read straight off the rings, as ``plot_patterns`` slices them
    (its duplicated zenith and seam dropped): the oracle's own indexing."""
    rings = np.asarray(ff.rings)
    if isinstance(v, an.Elevation):
        front = [ring[v.az] for ring in rings]
        back = [ring[(v.az + 180) % 360] for ring in rings]
        return np.array(list(reversed(front)) + back[1:])
    theta = 90 - v.el
    return np.asarray(rings[theta][:360])


def test_each_state_cell_is_the_engines_pattern_with_those_knobs_set(
    monkeypatch, capsys, tmp_path
):
    cuts = (an.Elevation(az=0), an.Azimuth(el=20))
    a = an.patterns(name="hp", cross=an.Cross(states=HEIGHTS), views=(*cuts,))
    _offer(monkeypatch, [a])
    metrics = _record(monkeypatch, far_field, "engine_pattern_metrics")
    got = _run(monkeypatch, capsys, ["--builder", INVVEE, "--analysis", "hp",
               "--ground", "finite-fast", "--engine", ENGINE, "--nominal-nsegs", "15",
               "--fn", str(tmp_path / "p.png")])  # fmt: skip
    assert list(got["patterns"]) == ["as built", "low mast", "tall mast"]
    assert got["refused"] == {}
    for (eng, ff), _kw, m in (c for c in metrics):
        # The compare table's function on the same solve (`web.adapter.
        # _metrics_from_gain` is refined_pattern_metrics, plus the freq).
        assert m == far_field.refined_pattern_metrics(eng.gain_evaluator())
    for st in HEIGHTS:
        b = _invvee()
        for k, v in st.knobs:
            setattr(b, k, v)
        eng = make_engine_factory(
            ENGINE, parse_ground("finite-fast"), nominal_nsegs=15
        )(b)
        ff = eng.far_field(**ar.PATTERN_GRID)
        cell = got["patterns"][st.name]
        assert cell.freq == b.freq == 28.47
        for v in cuts:
            angles, dbi = got["cuts"][st.name][ar.cut_name(v)]
            # Bit-equal: the same builder state reaches the same solve.
            assert np.array_equal(dbi, _grid_cut(ff, v)), (st.name, v)
            assert np.array_equal(ar.pattern_cut(ff, v)[1], dbi)
        assert cell.metrics == far_field.refined_pattern_metrics(eng.gain_evaluator())
    # Adversarial: over ground the three heights take off at different angles.
    takeoffs = [got["patterns"][s.name].metrics["takeoff_deg"] for s in HEIGHTS]
    assert len({round(t) for t in takeoffs}) == 3, takeoffs


def test_cut_angles_run_over_the_zenith_and_round_the_circle():
    ff = make_engine_factory(ENGINE, None)(_invvee()).far_field(**ar.PATTERN_GRID)
    angles, dbi = ar.pattern_cut(ff, an.Elevation(az=30))
    assert list(angles) == list(range(1, 180)) and dbi.shape == (179,)
    angles, dbi = ar.pattern_cut(ff, an.Azimuth(el=10))
    assert list(angles) == list(range(360)) and dbi.shape == (360,)


def test_analyze_prints_the_compare_tables_metrics_and_names_each_cell(
    monkeypatch, capsys
):
    a = an.patterns(
        name="pt", cross=an.Cross(states=HEIGHTS[:2]), views=(an.PatternTable(),)
    )
    _offer(monkeypatch, [a])
    table = _record(monkeypatch, far_field, "_print_metrics_table")
    cli(["analyze", "--builder", INVVEE, "--analysis", "pt", "--ground", "finite-fast",
         "--engine", ENGINE, "--fn", "/dev/null"])  # fmt: skip
    out = capsys.readouterr().out
    assert "pattern at 28.47 MHz (freq); 2 patterns (2 states)" in out
    assert "  low mast: 28.47 MHz, ground: finite-fast 13/0.005" in out
    ((names, rows), _kw, _o) = table[0]
    assert names == ["as built", "low mast"] and len(rows) == 2
    assert "peak dBi  takeoff°" in out


def test_analyze_csv_writes_one_block_per_cut_and_a_column_per_cell(
    monkeypatch, capsys, tmp_path
):
    cuts = (an.Elevation(az=0), an.Azimuth(el=15))
    a = an.patterns(name="csv", cross=an.Cross(states=HEIGHTS[:2]), views=cuts)
    _offer(monkeypatch, [a])
    out = tmp_path / "p.csv"
    got = _run(monkeypatch, capsys, ["--builder", INVVEE, "--analysis", "csv",
               "--ground", "finite-fast", "--engine", ENGINE, "--csv", str(out),
               "--fn", "/dev/null"])  # fmt: skip
    with open(out, newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    assert rows[0] == ["cut", "angle_deg", "as built gain_dBi", "low mast gain_dBi"]
    el = [r for r in rows[1:] if r[0] == "elevation az=0"]
    az = [r for r in rows[1:] if r[0] == "azimuth el=15"]
    assert len(el) + len(az) == len(rows) - 1
    assert [int(r[1]) for r in el] == list(range(1, 180))
    assert [int(r[1]) for r in az] == list(range(360))
    # Full precision, and exactly the cell's cut.
    for i, label in enumerate(["as built", "low mast"]):
        for name, block in (("elevation az=0", el), ("azimuth el=15", az)):
            want = got["cuts"][label][name][1]
            assert [float(r[2 + i]) for r in block] == list(want)


def test_csv_of_a_pattern_with_no_cut_is_refused_by_name(monkeypatch, tmp_path):
    a = an.patterns(name="t", views=(an.PatternTable(),))
    _offer(monkeypatch, [a])
    with pytest.raises(
        SystemExit, match="--csv writes the cuts, and this pattern draws none"
    ):
        cli(["analyze", "--builder", INVVEE, "--analysis", "t", "--engine", ENGINE,
             "--csv", str(tmp_path / "t.csv"), "--fn", "/dev/null"])  # fmt: skip


def test_a_frequency_family_solves_each_pattern_at_its_own_frequency(
    monkeypatch, capsys
):
    """The measurement frequency is the ``freq`` knob, as a frequency
    analysis names it: a family over `an.FREQUENCY` is a pattern per band."""
    a = an.patterns(
        name="bands",
        cross=an.Cross(step=an.Sweep(an.FREQUENCY, values=(28.0, 29.0))),
        views=(an.PatternTable(),),
    )
    _offer(monkeypatch, [a])
    got = _run(monkeypatch, capsys, ["--builder", INVVEE, "--analysis", "bands",
               "--engine", ENGINE, "--fn", "/dev/null"])  # fmt: skip
    assert {k: c.freq for k, c in got["patterns"].items()} == {
        "freq = 28": 28.0,
        "freq = 29": 29.0,
    }


# ── a study that is a pattern: the CLI reference's ────────────────────────


def _docs_blocks() -> list[str]:
    page = (
        Path(__file__).resolve().parents[1] / "site/src/content/docs/reference/cli.md"
    )
    text = page.read_text(encoding="utf-8")
    section = text[text.index("### Patterns") :]
    section = section[: section.index("\n### ", 1)]
    return [b.split("```")[0] for b in section.split("```python\n")[1:]]


def test_the_docs_patterns_first_example_is_the_catalogs():
    blocks = _docs_blocks()
    assert blocks[0].strip() == an.to_code(_catalog("height patterns"))


def test_the_docs_pattern_study_runs_and_each_cell_is_compare_patterns(
    tmp_path, monkeypatch, capsys
):
    """The study in the CLI reference, saved to a studies folder and run with
    ``analyze --study``; the oracle is ``antennaknobs compare_patterns`` over
    the same two designs, the far-field route that existed before patterns."""
    root = tmp_path / "studies"
    root.mkdir()
    (root / "vee_vs_yagi.py").write_text(_docs_blocks()[1])
    monkeypatch.setenv("ANTENNAKNOBS_STUDIES_DIR", str(root))
    monkeypatch.setenv("ANTENNAKNOBS_TRUST_USER_DESIGNS", "1")
    study = studies.find("vee_vs_yagi")
    assert an.is_pattern(study.analysis) and study.designs == (INVVEE, YAGI)
    got = _run(monkeypatch, capsys, ["--study", "vee_vs_yagi", "--engine", ENGINE,
               "--fn", str(tmp_path / "s.png")])  # fmt: skip
    assert list(got["patterns"]) == [INVVEE, YAGI] and got["refused"] == {}
    plots = _record(monkeypatch, far_field, "plot_patterns")
    cli(["compare_patterns", "--builders", INVVEE, YAGI, "--engines", ENGINE,
         "--ground", study.analysis.ground, "--fn", str(tmp_path / "c.png")])  # fmt: skip
    capsys.readouterr()
    ((rings_lst, names, thetas, phis, *_), _kw, _o) = plots[0]
    assert list(names) == [INVVEE, YAGI]
    cut_views = [v for v in study.analysis.views if not isinstance(v, an.PatternTable)]
    assert cut_views
    for label, rings in zip(names, rings_lst, strict=True):
        ff = type("FF", (), {"rings": rings, "thetas": thetas, "phis": phis})
        for v in cut_views:
            angles, dbi = got["cuts"][label][ar.cut_name(v)]
            assert np.array_equal(dbi, _grid_cut(ff, v)), (label, v)
    # Adversarial: the Yagi is a beam, the vee is not.
    fb = {k: c.metrics["front_to_back_db"] for k, c in got["patterns"].items()}
    assert fb[YAGI] > 5.0 > fb[INVVEE], fb


# ── the workbench: /analyses and /pattern_cell ────────────────────────────


def _served(client, req, name) -> dict:
    r = client.post("/analyses", json=req)
    assert r.status_code == 200, r.text
    (entry,) = [x for x in r.json()["analyses"] if x["name"] == name]
    return entry


def test_the_catalog_height_patterns_serve_a_pattern_cell_per_state(client):
    e = _served(client, {"geometry": INVVEE}, "height patterns")
    w = e["workbench"]
    assert e["problems"] == [] and e["summary"].startswith("pattern at 28.47 MHz")
    assert eval(e["code"], {"an": an}) == _catalog("height patterns")
    assert w["runs"] is True and w["kind"] == "pattern"
    assert w["views"] == [{"view": "Elevation", "az": 0}, {"view": "PatternTable"}]
    assert w["freq"] == 28.47 and w["grounds"] == ["finite-fast"]
    assert w["axes"] == ["states"]
    assert [(s["label"], s["knobs"], s["refused"]) for s in w["states"]] == [
        ("as built", {}, None),
        ("low mast", {"base": 5.0}, None),
        ("tall mast", {"base": 12.0}, None),
    ]
    # One solve per cell: nothing is swept.
    assert all(s["values"] is None and s["freqs"] is None for s in w["states"])


def test_a_served_pattern_names_a_refused_state_and_design(monkeypatch, client):
    a = an.patterns(
        name="mixed",
        cross=(
            an.Cross(designs=(INVVEE, "dipoles.nonesuch")),
            an.Cross(states=(an.State("long", line_len_m=20.0),)),
        ),
    )
    _offer(monkeypatch, [a])
    w = _served(client, {"geometry": INVVEE}, "mixed")["workbench"]
    assert w["kind"] == "pattern"
    assert [d["name"] for d in w["designs"]] == [INVVEE, "dipoles.nonesuch"]
    assert w["designs"][1]["refused"]
    (s,) = w["states"]
    assert s["on"][0]["refused"] == (
        "state 'long' sets line_len_m, and this design has no knob 'line_len_m'"
    )


def _cell_body(**over) -> dict:
    return {
        "geometry": INVVEE,
        "base": 12.0,
        "length_factor": 0.9719,
        "angle_deg": 31.6846,
        "design_freq_mhz": 28.47,
        "measurement_freq_mhz": 28.47,
        "solver": "momwire",
        "momwire_model": "bspline",
        "n_per_wire": 15,
        "ground": False,
        "elev_az_deg": 0,
        "az_elev_deg": 10,
        **over,
    }


def test_a_pattern_cell_is_the_live_solve_and_the_compare_tables_metrics(client):
    body = _cell_body()
    r = client.post("/pattern_cell", json=body)
    assert r.status_code == 200, r.text
    got = r.json()
    assert got["available"] is True
    # The compare table's own endpoint, on the same request.
    table = client.post("/pattern_metrics", json=body).json()
    assert got["metrics"] == table["metrics"]
    # The live chart's cuts, at the request's angles.
    cuts = got["solve"]["cuts"]
    assert (cuts["elev_az_deg"], cuts["az_elev_deg"]) == (0, 10)
    assert cuts["elevation"] and cuts["azimuth"]
    assert got["solve"]["solve_id"]


def test_a_session_cells_metrics_come_off_its_own_solve(client, monkeypatch):
    """With a session and a generation the solve files its metrics thunk
    (AK#1727) and the cell takes it: the same numbers, no second fill."""
    from antennaknobs.web import server

    looked = _record(monkeypatch, server, "_solved_metrics_for")
    # A height no other test solves: a cached solve files no thunk.
    body = _cell_body(base=11.25, _session="pat-t", _gen=3, _stream="c0r1")
    got = client.post("/pattern_cell", json=body).json()
    assert got["available"] is True
    # Instrumented, so the path is the thunk and not a quiet second fill.
    assert [out is not None for _a, _k, out in looked] == [True]
    # A session-less request (the cache's solve, then a fresh fill).
    plain = client.post("/pattern_cell", json=_cell_body(base=11.25)).json()
    assert [out is not None for _a, _k, out in looked] == [True, False]
    assert got["metrics"] == plain["metrics"]


def test_a_workbench_cell_is_the_clis_cell_in_free_space(monkeypatch, client, capsys):
    """The chart's state cell (the design's defaults, the state's knobs) and
    the CLI's: one builder state, one solve, bit-equal metrics."""
    a = an.patterns(
        name="t", cross=an.Cross(states=(HEIGHTS[2],)), views=(an.PatternTable(),)
    )
    _offer(monkeypatch, [a])
    got = _run(monkeypatch, capsys, ["--builder", INVVEE, "--analysis", "t",
               "--engine", ENGINE, "--nominal-nsegs", "15", "--ground", "free",
               "--fn", "/dev/null"])  # fmt: skip
    cli_m = got["patterns"]["tall mast"].metrics
    web_m = client.post("/pattern_cell", json=_cell_body()).json()["metrics"]
    assert {k: web_m[k] for k in cli_m} == cli_m


def test_a_cell_the_poor_match_gate_withholds_is_a_403(client, monkeypatch):
    from antennaknobs.web import server

    class Warn:
        verdict = "warn"
        reason = "a poor match"

    monkeypatch.setattr(server, "_admit", lambda *a, **k: Warn())
    r = client.post("/pattern_cell", json=_cell_body())
    assert r.status_code == 403 and r.json()["detail"] == "a poor match"
    r = client.post("/pattern_cell", json=_cell_body(_approved=True))
    assert r.status_code == 200 and r.json()["available"] is True


def test_the_lane_schedules_a_pattern_cell_as_its_own_stream():
    lane = importlib.import_module("antennaknobs.web.lane")
    assert lane.PRIORITY["pattern_cell"] == lane.PRIORITY["pattern_metrics"]
    assert "pattern_cell" in lane.SAME_KIND_SUPERSEDES

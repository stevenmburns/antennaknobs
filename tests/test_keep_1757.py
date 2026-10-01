"""AK#1757, sweep framework step 7 unit 4: "copy as analysis" and "keep as
study" (`antennaknobs.keep`, ``POST /keep``, ``POST /studies/save``;
docs/design/sweep-framework-step7.md § 4, rulings 1 and 4, the ``cells=``
ruling).

THE GATE: a kept study, saved, found again and run, reproduces what was
pinned BIT-EQUAL. Each case goes through the production path end to end:
the pins are solved through the workbench's own endpoints (``/param_sweep``,
``/sweep``, ``/pattern_metrics``) on the requests they carry, kept through
``POST /studies/save`` (the file written and trusted by the server), found
by discovery (`studies.discover`, and ``/analyses`` on the tab), and run by
``antennaknobs analyze --study`` (the CLI's own `analysis_run`). Which
branch wrote the cells is asserted, not assumed: a set of pins that is not
a product is ``cells=`` (and the runner's listed-cell branch ran), one that
is a product is the plain cross.

Around it:

- a pin set is a product or a list (`keep.is_product`), each pin one cell:
  its design and variant, the knobs off that variant's defaults (a group
  knob's tuple included), its engine, ground and plane;
- saving writes a new file under the studies folder (subfolders are name
  parts), trusted WITH EDITS ALLOWED (``allow --edits``); a file that merely
  appears there still asks;
- the server refuses to save on the hosted instance (403) and writes
  nothing; a bad path is a 422 and an existing file a 409;
- "copy as analysis" is the ``to_code`` text of a chart about the tab's
  design only; "keep as study" of a chart names the tab's design.
"""

from __future__ import annotations

import datetime as _dt
import json

import pytest
from fastapi.testclient import TestClient

from antennaknobs import analyses as an
from antennaknobs import analysis_run as ar
from antennaknobs import design_trust as dt
from antennaknobs import keep, studies
from antennaknobs.cli import cli
from antennaknobs.web.analyses_offer import builder_for
from antennaknobs.web.examples import example_for

INVVEE = "dipoles.invvee"
APEX = "dipoles.invvee_apex"
FAN = "multiband.fandipole"
BSPLINE = "momwire:bspline"
RAZOR = "momwire:razor-2p"
N = 15


@pytest.fixture(scope="module")
def client() -> TestClient:
    from antennaknobs.web import server

    return TestClient(server.app)


@pytest.fixture
def folder(tmp_path, monkeypatch):
    """An empty studies folder with the trust gate ACTIVE."""
    root = tmp_path / "studies"
    root.mkdir()
    monkeypatch.setenv("ANTENNAKNOBS_STUDIES_DIR", str(root))
    monkeypatch.delenv("ANTENNAKNOBS_TRUST_USER_DESIGNS", raising=False)
    monkeypatch.delenv("ANTENNAKNOBS_TRUST_FILE", raising=False)
    monkeypatch.setenv("ANTENNAKNOBS_USER_DIR", str(tmp_path / "designs"))
    return root


def _record(monkeypatch, module, name):
    calls = []
    inner = getattr(module, name)

    def wrapped(*args, **kwargs):
        out = inner(*args, **kwargs)
        calls.append((args, kwargs, out))
        return out

    monkeypatch.setattr(module, name, wrapped)
    return calls


def _req(design, variant=None, model="bspline", **knobs) -> dict:
    """A solve request as the workbench sends one for a design at its
    variant's defaults with ``knobs`` turned: every knob a top-level field
    (a group as a list of dicts), the two frequencies in fields of their
    own, a momwire model, a density, free space."""
    cls = example_for(design).builder_cls
    b = builder_for(cls, {"geometry": design, "variant": variant or "default"})
    values = {
        k: [dict(e) for e in v] if isinstance(v, tuple) else v
        for k, v in an._params(b).items()
        if k not in ("ui_params", "nominal_nsegs", "freq", "design_freq")
    }
    return {
        "geometry": design,
        "variant": variant or "default",
        **values,
        **knobs,
        "design_freq_mhz": b.design_freq,
        "measurement_freq_mhz": b.freq,
        "solver": "momwire",
        "momwire_model": model,
        "n_per_wire": N,
        "ground": False,
    }


def _lines(text: str) -> list[dict]:
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def _knob_pin(client, req, param, values) -> tuple[dict, list[complex]]:
    """A knob-sweep pin as the chart takes one: its curve solved through
    ``/param_sweep`` on its request, and what the pin carries."""
    r = client.post("/param_sweep", json={**req, "param": param, "values": values})
    assert r.status_code == 200, r.text
    recs = _lines(r.text)[:-1]
    assert [x["value"] for x in recs] == values
    pin = {"req": req, "label": "", "x": {"kind": "knob", "name": param}, "xs": values}
    return pin, [complex(x["z_re"], x["z_im"]) for x in recs]


def _freq_pin(client, req, freqs) -> tuple[dict, list[complex]]:
    """A frequency-sweep pin: its curve solved through ``/sweep``."""
    r = client.post("/sweep", json={**req, "freqs_mhz": freqs})
    assert r.status_code == 200, r.text
    recs = [x for x in _lines(r.text) if "freq_mhz" in x]
    xs = [x["freq_mhz"] for x in recs]
    assert xs == freqs
    pin = {
        "req": req,
        "label": "",
        "x": {"kind": "frequency", "name": "frequency"},
        "xs": xs,
    }
    return pin, [complex(x["z_re"], x["z_im"]) for x in recs]


def _save(client, body: dict, path: str) -> dict:
    r = client.post("/studies/save", json={**body, "path": path})
    assert r.status_code == 200, r.text
    return r.json()


def _run_study(monkeypatch, capsys, tmp_path, name: str) -> dict:
    """``antennaknobs analyze --study NAME`` at the pins' density; what the
    runner computed."""
    runs = _record(monkeypatch, ar, "run")
    cli(["analyze", "--study", name, "--nominal-nsegs", str(N),
         "--fn", str(tmp_path / "chart.png")])  # fmt: skip
    capsys.readouterr()
    return runs[-1][2]


def _bit_equal(curve, pin, z):
    """Every pinned point, looked up by its x in the study's curve: ``==``."""
    xs, zs = curve
    got = dict(zip([float(x) for x in xs], [complex(v) for v in zs], strict=True))
    return [got[float(x)] for x in pin["xs"]] == z


# ── THE GATE ──────────────────────────────────────────────────────────────


def test_sweep_pins_that_are_no_product_keep_as_cells_and_rerun_bit_equal(
    monkeypatch, capsys, tmp_path, client, folder
):
    """Two knob-sweep pins, the second on a VARIANT and another engine: 2
    states x 2 engines would be 4 cells, so they are a list (``cells=``),
    and the rerun's two curves are the pins, bit for bit."""
    a_pin, a_z = _knob_pin(client, _req(INVVEE, base=5.0),
                           "length_factor", [0.95, 0.975, 1.0])  # fmt: skip
    b_pin, b_z = _knob_pin(client, _req(INVVEE, "dipole", "razor-2p", base=12.0),
                           "length_factor", [0.95, 1.0])  # fmt: skip
    body = {"origin": "sweep pins", "name": "two pins", "pins": [a_pin, b_pin]}
    saved = _save(client, body, "feeds/two")
    assert saved["name"] == "feeds/two:two pins" and saved["source"] == "feeds/two"
    path = folder / "feeds" / "two.py"
    assert saved["path"] == str(path) and dt.trust_status(path) == "always"

    # Discovery: the saved file is found, allowed, and is the cells study.
    (st,) = [s for s in studies.discover().studies if s.source == "feeds/two"]
    cells = an.cells_of(st.analysis)
    assert [(c.state, c.engine) for c in cells] == [
        (an.State("base 5", design=INVVEE, base=5.0), BSPLINE),
        (an.State("base 12", design=INVVEE, variant="dipole", base=12.0), RAZOR),
    ]
    assert st.analysis.ground == "free" and st.analysis.sweep == an.Sweep(
        "length_factor", values=(0.95, 0.975, 1.0)
    )

    listed = _record(monkeypatch, ar, "_listed_cell")
    got = _run_study(monkeypatch, capsys, tmp_path, "feeds/two:two pins")
    # The listed-cell branch made both cells (instrumented, not assumed).
    assert len(listed) == 2
    assert got["refused"] == {}
    assert list(got["curves"]) == [
        f"{INVVEE}, base 5, {BSPLINE}",
        f"{INVVEE}:dipole, base 12, {RAZOR}",
    ]
    curves = list(got["curves"].values())
    assert _bit_equal(curves[0], a_pin, a_z)
    assert _bit_equal(curves[1], b_pin, b_z)
    # The variant is not a no-op: the default variant's curve is another.
    _, default_z = _knob_pin(client, _req(INVVEE, None, "razor-2p", base=12.0),
                             "length_factor", [0.95, 1.0])  # fmt: skip
    assert default_z != b_z


def test_frequency_pins_with_a_group_knob_keep_as_a_plain_cross_bit_equal(
    monkeypatch, capsys, tmp_path, client, folder
):
    """fan_dipole as built and with one band's length factor turned (a
    GROUP knob, ``bands``), one engine: 2 states x 1 engine is a product,
    so the plain states cross, and the rerun is the pins bit for bit."""
    turned = _req(FAN)
    turned["bands"][4]["length_factor"] = 0.49
    freqs = [28.0, 28.5, 29.0]
    p1, z1 = _freq_pin(client, _req(FAN), freqs)
    p2, z2 = _freq_pin(client, turned, freqs)
    saved = _save(client, {"origin": "sweep pins", "name": "bands", "pins": [p1, p2]},
                  "fan/bands")  # fmt: skip
    (st,) = [s for s in studies.discover().studies if s.name == saved["name"]]
    a = st.analysis
    assert an.cells_of(a) == ()
    (cross,) = a.crosses
    as_built, bands = cross.states
    assert as_built == an.State("as built", design=FAN)
    assert bands.name == "bands set" and dict(bands.settings)["bands"][4] == {
        "freq": 28.47,
        "length_factor": 0.49,
    }
    assert a.engine == BSPLINE and a.sweep == an.Sweep(
        an.FREQUENCY, values=(28.0, 28.5, 29.0)
    )

    listed = _record(monkeypatch, ar, "_listed_cell")
    got = _run_study(monkeypatch, capsys, tmp_path, "fan/bands")
    assert listed == []  # the product branch, not the listed cells
    curves = list(got["curves"].values())
    assert _bit_equal(curves[0], p1, z1)
    assert _bit_equal(curves[1], p2, z2)
    # The turned band moved the curve: the state is not a no-op.
    assert z1 != z2


def test_pattern_pins_keep_as_a_pattern_study_bit_equal(
    monkeypatch, capsys, tmp_path, client, folder
):
    """Two pattern pins (the tall mast; the dipole variant as built): their
    compare-table metrics (``/pattern_metrics``, what the pin shows) are the
    kept study's metrics bit for bit."""
    tall = {**_req(INVVEE, base=12.0), "az_elev_deg": 0, "elev_az_deg": 10}
    dipole = {**_req(INVVEE, "dipole"), "az_elev_deg": 0, "elev_az_deg": 10}
    pinned = [
        client.post("/pattern_metrics", json=r).json()["metrics"]
        for r in (tall, dipole)
    ]
    pins = [{"req": r} for r in (tall, dipole)]
    saved = _save(client, {"origin": "pattern pins", "name": "pp", "pins": pins}, "pp")
    (st,) = [s for s in studies.discover().studies if s.name == saved["name"]]
    assert an.is_pattern(st.analysis)
    assert st.analysis.views == (
        an.Elevation(az=0),
        an.Azimuth(el=10),
        an.PatternTable(),
    )
    assert an.states_of(st.analysis) == (
        an.State("base 12", design=INVVEE, base=12.0),
        an.State("as built", design=INVVEE, variant="dipole"),
    )

    runs = _record(monkeypatch, ar, "_run_patterns")
    cli(["analyze", "--study", "pp", "--nominal-nsegs", str(N),
         "--fn", str(tmp_path / "p.png")])  # fmt: skip
    capsys.readouterr()
    solved = runs[-1][2]["patterns"]
    assert list(solved) == [f"{INVVEE}, base 12", f"{INVVEE}:dipole, as built"]
    for cell, want in zip(solved.values(), pinned, strict=True):
        assert cell.metrics and {k: want[k] for k in cell.metrics} == cell.metrics


def test_a_kept_study_is_served_on_the_tab_of_every_design_it_names(client, folder):
    """The workbench's discovery: ``/analyses`` on invvee lists the kept
    cells study with one served cell per pin, and a design it does not
    name lists nothing of it."""
    a = keep.analysis_from_pins(
        [
            {"req": _req(INVVEE, base=5.0),
             "x": {"kind": "knob", "name": "length_factor"}, "xs": [0.95, 1.0]},
            {"req": _req(INVVEE, "dipole", "razor-2p", base=12.0),
             "x": {"kind": "knob", "name": "length_factor"}, "xs": [0.95, 1.0]},
        ],
        kind="sweep",
        name="served",
    )[0]  # fmt: skip
    keep.save(a, "served", origin="sweep pins")
    r = client.post("/analyses", json={"geometry": INVVEE})
    (entry,) = [e for e in r.json()["analyses"] if e["name"] == "served:served"]
    assert entry["study"] == {"source": "served", "name": "served"}
    assert an.from_data(entry["spec"]) == a
    w = entry["workbench"]
    assert w["runs"] is True and w["axes"] == ["cells"] and w["engines"] is None
    got = [
        (
            c["label"],
            c["engine"],
            c["state"]["variant"],
            c["state"]["knobs"],
            c["refused"],
        )
        for c in w["cells"]
    ]
    assert got == [
        (f"{INVVEE}, base 5, {BSPLINE}", BSPLINE, None, {"base": 5.0}, None),
        (f"{INVVEE}:dipole, base 12, {RAZOR}", RAZOR, "dipole", {"base": 12.0}, None),
    ]
    assert all(c["values"] == [0.95, 1.0] for c in w["cells"])
    r = client.post("/analyses", json={"geometry": APEX})
    assert "served:served" not in [e["name"] for e in r.json()["analyses"]]


# ── pins as cells ─────────────────────────────────────────────────────────


def test_a_pin_is_its_design_variant_changed_knobs_engine_ground_and_plane():
    req = _req(INVVEE, "dipole", base=12.0, angle_deg=20.0)
    req["plane"] = "feed"
    req.update(ground=True, ground_model="pec")
    cell = keep.pin_cell({"req": req}, swept="angle_deg", who="pin 1", notes=[])
    assert cell == an.Cell(
        an.State("base 12", design=INVVEE, variant="dipole", base=12.0),
        engine=BSPLINE,
        ground="pec",
        plane="feed",
    )
    # The density and the frequencies at their defaults are no knobs; a
    # measurement frequency off the design's is the state's freq.
    moved = {**_req(INVVEE), "measurement_freq_mhz": 28.0, "n_per_wire": 40}
    assert keep.changed_knobs(moved) == (INVVEE, None, [("freq", 28.0)])


@pytest.mark.parametrize(
    ("req", "engine", "ground"),
    [
        ({}, "momwire:bspline", "free"),
        ({"model_options": {"degree": 2}}, "momwire:bspline", "free"),
        ({"model_options": {"degree": 1}}, "momwire:bspline-d1", "free"),
        ({"momwire_model": "razor-2p"}, "momwire:razor-2p", "free"),
        ({"solver": "nec5"}, "nec5", "free"),
        ({"ground": True, "ground_model": "pec"}, "momwire:bspline", "pec"),
        ({"ground": True, "ground_model": "fast"}, "momwire:bspline", "finite-fast"),
        ({"ground": True}, "momwire:bspline", "finite-fast"),
        (
            {"ground": True, "ground_model": "sommerfeld", "soil": {"eps_r": 5, "sigma": 0.001}},
            "momwire:bspline",
            "finite:5,0.001",
        ),
        ({"ground": True, "ground_model": "mininec"}, "momwire:bspline", "mininec"),
    ],
)  # fmt: skip
def test_a_pins_engine_and_ground_are_read_off_its_request(req, engine, ground):
    base = {"geometry": INVVEE, **req}
    assert keep.engine_of(base, "pin 1") == engine
    assert keep.ground_of(base, "pin 1") == ground


def test_an_engine_option_off_its_default_is_noted_not_dropped_silently():
    notes: list[str] = []
    req = {"momwire_model": "bspline", "model_options": {"degree": 2, "n_qp_source": 32,
           "feed_smoothing_factor": None, "extended_kernel": False}}  # fmt: skip
    assert keep.engine_of(req, "pin 2", notes) == BSPLINE
    assert notes == [
        "pin 2 was solved with n_qp_source set on its slot; --engine "
        "momwire:bspline runs the engine's defaults for them."
    ]


@pytest.mark.parametrize(
    ("pin", "words"),
    [
        ({}, "no solve request"),
        ({"req": {"geometry": INVVEE, "model_options": {"degree": 3}}}, "degree 3 has no --engine"),
        ({"req": {"geometry": INVVEE, "momwire_model": "nope"}}, "'nope' has no --engine"),
        ({"req": {"geometry": INVVEE, "ground": True, "ground_model": "terrain"}}, "terrain ground has no --ground"),
        ({"req": {"geometry": INVVEE, "solver": "x; import os"}}, "not an engine spec"),
        ({"req": {"geometry": INVVEE, "variant": "nope"}}, "no variant 'nope'"),
        ({"req": {"geometry": "dipoles.nonesuch"}}, "nonesuch"),
    ],
)  # fmt: skip
def test_a_pin_that_cannot_be_kept_is_refused_by_name(pin, words):
    with pytest.raises(keep.KeepError, match=words):
        keep.pin_cell(pin, swept=None, who="pin 1", notes=[])


def _cell(name, engine=BSPLINE, ground="free", **knobs):
    return an.Cell(an.State(name, design=INVVEE, **knobs), engine=engine, ground=ground)


def test_a_pin_set_is_a_product_only_when_every_combination_is_there_once():
    lo, hi = {"base": 5.0}, {"base": 12.0}
    assert keep.is_product([_cell("lo", **lo), _cell("hi", **hi)])
    assert keep.is_product(
        [
            _cell("lo", **lo),
            _cell("lo", RAZOR, **lo),
            _cell("hi", **hi),
            _cell("hi", RAZOR, **hi),
        ]
    )
    assert not keep.is_product([_cell("lo", **lo), _cell("hi", RAZOR, **hi)])
    assert not keep.is_product(
        [_cell("lo", **lo), _cell("lo", RAZOR, **lo), _cell("hi", **hi)]
    )


def _pin(knobs=None, engine=BSPLINE, design=INVVEE, variant=None, xs=(0.95, 1.0)):
    model = engine.partition(":")[2]
    return {"req": _req(design, variant, model, **(knobs or {})),
            "x": {"kind": "knob", "name": "length_factor"}, "xs": list(xs)}  # fmt: skip


def test_pins_become_a_designs_cross_states_engines_or_cells():
    # Designs at their defaults read as a designs cross (E7's form).
    a, _ = keep.analysis_from_pins(
        [_pin(), _pin(design=APEX)], kind="sweep", name="feeds"
    )
    assert a.crosses == (an.Cross(designs=(INVVEE, APEX)),) and a.engine == BSPLINE
    # A product over states and engines is the two crosses.
    pins = [_pin({"base": 5.0}), _pin({"base": 5.0}, RAZOR), _pin(), _pin(engine=RAZOR)]
    a, _ = keep.analysis_from_pins(pins, kind="sweep", name="p")
    assert [c.kind for c in a.crosses] == ["states", "engines"] and a.engine is None
    assert a.crosses[1].engines == (BSPLINE, RAZOR)
    # Not a product: cells=, the shared ground lifted onto the analysis.
    a, _ = keep.analysis_from_pins(
        [_pin({"base": 5.0}), _pin(engine=RAZOR)], kind="sweep", name="c"
    )
    assert [c.kind for c in a.crosses] == ["cells"] and a.ground == "free"
    assert all(c.ground is None for c in a.cross.cells)


def test_pins_x_values_union_notes_and_refusals():
    a, notes = keep.analysis_from_pins(
        [_pin(xs=(1.0, 0.95)), _pin({"base": 5.0}, xs=(0.975, 1.0))],
        kind="sweep",
        name="",
    )
    assert a.name == "pinned sweeps"
    assert a.sweep == an.Sweep("length_factor", values=(0.95, 0.975, 1.0))
    assert notes == [
        f"The pins were solved at {N} segments per wire: run it with "
        f"--nominal-nsegs {N} to reproduce them exactly."
    ]
    _, notes = keep.analysis_from_pins([_pin(), _pin()], kind="sweep", name="x")
    assert notes[0] == "pin 2 is the same cell as an earlier pin; it is kept once."
    freq = {**_pin(), "x": {"kind": "frequency", "name": "frequency"}}
    with pytest.raises(keep.KeepError, match="the pins sweep different things"):
        keep.analysis_from_pins([_pin(), freq], kind="sweep", name="x")
    seven = [_pin({"base": 5.0 + i}) for i in range(7)]
    with pytest.raises(keep.KeepError, match="7 pins is over the cap of 6"):
        keep.analysis_from_pins(seven, kind="sweep", name="x")


def test_a_pattern_pins_cut_off_the_grid_is_brought_onto_it_with_a_note():
    req = {**_req(INVVEE), "az_elev_deg": 12.4, "elev_az_deg": 0.2}
    a, notes = keep.analysis_from_pins([{"req": req}], kind="pattern", name="p")
    assert a.views == (an.Elevation(az=12), an.Azimuth(el=1), an.PatternTable())
    assert any("elevation 0.2 deg" in n and "so it is 1" in n for n in notes)
    assert any("azimuth 12.4 deg" in n and "so it is 12" in n for n in notes)


# ── the text ──────────────────────────────────────────────────────────────


def test_a_study_file_is_a_header_the_notes_and_build_studies():
    a, notes = keep.analysis_from_pins([_pin({"base": 5.0})], kind="sweep", name="one")
    day = _dt.date(2026, 9, 30)
    text = keep.render(
        a, form="study", origin="sweep pins", notes=notes, saved=True, today=day
    )
    assert text.startswith(
        "# Written by the antennaknobs workbench on 2026-09-30, from your own "
        "pinned sweeps\n"
    )
    ns: dict = {}
    exec(compile(text, "<study>", "exec"), ns)
    assert ns["build_studies"]() == [a]
    copied = keep.render(a, form="study", origin="sweep pins", today=day)
    assert "antennaknobs allow <its path under that folder> --edits" in copied
    assert keep.render(a, form="analysis", origin="chart") == an.to_code(a) + "\n"


def test_a_note_stays_a_comment_whatever_it_holds():
    a, _ = keep.analysis_from_pins([_pin()], kind="sweep", name="n")
    evil = "x\nimport os; os.system('boom') y\x00z"
    text = keep.render(a, form="study", origin="chart", notes=[evil])
    (line,) = [ln for ln in text.splitlines() if "boom" in ln]
    assert line.startswith("# x import os")
    compile(text, "<study>", "exec")
    with pytest.raises(keep.KeepError, match="at most 24 notes"):
        keep.render(a, form="study", origin="chart", notes=["n"] * 25)


# ── the file ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("text", "words"),
    [
        ("", "give the study a file name"),
        ("/etc/x", "is absolute"),
        ("C:x", "is absolute"),
        ("a/../b", "climbs out"),
        ("a\\b", "not '\\\\'"),
        ("_private", "not a plain name"),
        ("a.b", "not a plain name"),
        ("ab:c", "not a plain name"),
        ("/".join("a" * 9), "nests more than 8"),
    ],
)
def test_a_study_path_is_a_plain_relative_name_inside_the_folder(folder, text, words):
    with pytest.raises(keep.KeepError, match=words):
        keep.study_path(text)


def test_nested_folders_are_name_parts(folder):
    assert keep.study_path("feeds/e7.py") == (folder / "feeds" / "e7.py", "feeds/e7")


def test_a_saved_study_is_trusted_with_edits_and_a_dropped_file_is_not(folder):
    a, _ = keep.analysis_from_pins([_pin({"base": 5.0})], kind="sweep", name="mine")
    out = keep.save(a, "deep/er/mine", origin="sweep pins")
    path = folder / "deep" / "er" / "mine.py"
    assert out == {
        "path": str(path),
        "source": "deep/er/mine",
        "name": "deep/er/mine:mine",
    }
    assert dt.trust_status(path) == "always"
    # A hand edit is not asked about again (allow --edits).
    path.write_text(path.read_text().replace('"mine"', '"edited"'))
    assert [
        s.name for s in studies.discover().studies if s.source == "deep/er/mine"
    ] == ["deep/er/mine:edited"]
    # A file that merely appears in the folder still asks.
    (folder / "dropped.py").write_text(path.read_text())
    (b,) = [b for b in studies.discover().blocked if b.source == "dropped"]
    assert b.allow == "antennaknobs allow dropped"
    with pytest.raises(keep.StudyExists, match="is there already"):
        keep.save(a, "deep/er/mine", origin="sweep pins")
    keep.save(a, "deep/er/mine", origin="sweep pins", overwrite=True)


def test_a_spec_that_is_no_study_is_never_written(folder):
    a = an.Analysis("own", an.Sweep("base"))
    with pytest.raises(keep.KeepError, match="a study names its designs"):
        keep.save(a, "own", origin="chart")
    assert list(folder.iterdir()) == []


# ── the server ────────────────────────────────────────────────────────────


def test_saving_a_study_is_refused_on_the_hosted_instance(monkeypatch, client, folder):
    """Local workbench only (ruling 4): hosted, /studies/save is a 403 and
    nothing is written; /keep (the clipboard, nothing written) still serves,
    and /capabilities says save is off."""
    from antennaknobs.web import server

    body = {
        "origin": "sweep pins",
        "name": "h",
        "pins": [_pin({"base": 5.0})],
        "path": "h",
    }
    monkeypatch.setattr(server, "_HOSTED", True)
    r = client.post("/studies/save", json=body)
    assert r.status_code == 403
    assert r.json()["detail"] == (
        "saving a study is disabled on the hosted instance; copy it instead"
    )
    assert list(folder.iterdir()) == []
    assert client.post("/keep", json=body).status_code == 200
    assert client.get("/capabilities").json()["can_save_studies"] is False
    monkeypatch.setattr(server, "_HOSTED", False)
    assert client.get("/capabilities").json()["can_save_studies"] is True
    assert client.post("/studies/save", json=body).status_code == 200
    assert (folder / "h.py").is_file()


def test_the_save_endpoint_names_a_bad_path_and_an_existing_file(client, folder):
    body = {"origin": "sweep pins", "name": "x", "pins": [_pin({"base": 5.0})]}
    r = client.post("/studies/save", json={**body, "path": "../out"})
    assert r.status_code == 422 and "climbs out" in r.json()["detail"]
    assert client.post("/studies/save", json={**body, "path": "x"}).status_code == 200
    r = client.post("/studies/save", json={**body, "path": "x"})
    assert r.status_code == 409 and "is there already" in r.json()["detail"]
    r = client.post("/studies/save", json={**body, "path": "x", "overwrite": True})
    assert r.status_code == 200


# ── a chart ───────────────────────────────────────────────────────────────


def _entry(client, geometry, name, **req) -> dict:
    r = client.post("/analyses", json={"geometry": geometry, **req})
    (entry,) = [e for e in r.json()["analyses"] if e["name"] == name]
    return entry


def test_copy_as_analysis_is_the_charts_code_for_its_own_design(client):
    e = _entry(client, INVVEE, "height states")
    body = {
        "origin": "chart",
        "form": "analysis",
        "spec": e["spec"],
        "tab": _req(INVVEE),
    }
    r = client.post("/keep", json=body)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["code"] == e["code"] + "\n" and out["problems"] == []
    # The engines and grounds its curves were solved on go with it (read
    # off their requests), and an edited range as the points it solved.
    fast = {"ground": True, "ground_model": "fast"}
    cells = [{**_req(INVVEE), **fast}, {**_req(INVVEE, model="razor-2p"), **fast}]
    body = {**body, "cells": cells, "values": [28.5, 28.0]}
    a = eval(client.post("/keep", json=body).json()["code"], {"an": an})
    assert an.Cross(engines=(BSPLINE, RAZOR)) in a.crosses
    assert a.sweep == an.Sweep(an.FREQUENCY, values=(28.0, 28.5))
    # What the analysis lists already stays as written ("finite-fast").
    assert a.ground == "finite-fast" and a.engine is None
    # One engine it did not list becomes the analysis's own engine.
    one = client.post("/keep", json={**body, "cells": cells[1:]}).json()["code"]
    assert eval(one, {"an": an}).engine == RAZOR


def test_copy_as_analysis_is_refused_for_a_chart_of_named_designs(client):
    e = _entry(client, INVVEE, "dipoles.apex_feed_on_invvee:feed spelling (E7)")
    body = {
        "origin": "chart",
        "form": "analysis",
        "spec": e["spec"],
        "tab": _req(INVVEE),
    }
    r = client.post("/keep", json=body)
    assert r.status_code == 422 and "keep it as a study" in r.json()["detail"]
    # As a study it is kept as it is: it names its designs.
    r = client.post("/keep", json={**body, "form": "study"})
    assert (
        'an.Cross(designs=("dipoles.invvee", "dipoles.invvee_apex"))'
        in r.json()["code"]
    )


def test_keep_as_study_of_a_chart_names_the_tabs_design_and_its_knobs(client):
    # A plain analysis, drawn at the tab's live knobs: they become a state.
    e = _entry(client, INVVEE, "band SWR")
    tab = _req(INVVEE, base=9.5)
    out = client.post("/keep", json={"origin": "chart", "form": "study",
                                     "spec": e["spec"], "tab": tab}).json()  # fmt: skip
    assert out["study_refusal"] is None
    ns: dict = {}
    exec(out["code"], ns)
    (a,) = ns["build_studies"]()
    assert a.crosses[0] == an.Cross(
        states=(an.State("base 9.5", design=INVVEE, base=9.5),)
    )
    # Unnamed states are set on the tab's design, at its variant, and keep
    # their own knobs (a state is over the defaults, not the live knobs).
    e = _entry(client, INVVEE, "height states")
    tab = _req(INVVEE, "dipole", base=9.5)
    out = client.post("/keep", json={"origin": "chart", "form": "study", "name": "hs",
                                     "spec": e["spec"], "tab": tab}).json()  # fmt: skip
    ns = {}
    exec(out["code"], ns)
    (a,) = ns["build_studies"]()
    assert a.name == "hs"
    assert [(s.design, s.variant, s.settings) for s in an.states_of(a)] == [
        (INVVEE, "dipole", {}),
        (INVVEE, "dipole", {"base": 5.0}),
        (INVVEE, "dipole", {"base": 12.0}),
    ]


def test_a_keep_request_is_refused_by_name(client):
    for body, words in [
        ({"origin": "mail"}, "origin is one of"),
        ({"origin": "chart", "form": "pdf"}, "form is one of"),
        (
            {"origin": "chart", "spec": {"an": "Sweep", "knob": "base"}},
            "not an an.Analysis",
        ),
        ({"origin": "sweep pins", "form": "analysis", "pins": []}, "kept as a study"),
        ({"origin": "sweep pins", "pins": []}, "give the pins to keep"),
    ]:
        r = client.post("/keep", json=body)
        assert r.status_code == 422 and words in r.json()["detail"], (body, r.text)

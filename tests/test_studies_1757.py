"""AK#1757, sweep framework step 7, unit 1: studies, analyses over several
designs declared by a module-level ``build_studies()`` (`antennaknobs.studies`).

What is pinned:

- discovery from catalog modules (E7 moved out of ``invvee.build_analyses()``
  into that module's ``build_studies()``) and from a NESTED user studies
  folder, whose subfolders are name parts (``feeds/e7.py`` is ``feeds/e7``);
- the trust gate: a user study file not allowed yet is listed as needing
  ``allow`` and is never imported, proven by a sentinel its import would
  write; ``allow`` takes a nested name and keys the record by its path
  relative to the studies folder; an allowed file runs;
- the rule: a study without ``designs=`` is refused by name;
- names: ``source:name``, unique across sources; duplicates in one source
  are refused; a bare name shared by two sources is ambiguous, by name;
- the CLI: ``analyze --list-studies`` (with and without ``--builder``),
  ``--study`` (a study's curves ARE the same analysis offered by a design and
  run with ``--analysis``), ``--study --code`` round-tripping ``to_code``;
- ``/analyses``: the studies crossing the tab's design are served after its
  own analyses, on invvee and invvee_apex and on no other design.
"""

from __future__ import annotations

import json

import pytest
from starlette.testclient import TestClient

from antennaknobs import analyses as an
from antennaknobs import analysis_run as ar
from antennaknobs import design_trust as dt
from antennaknobs import studies
from antennaknobs.cli import cli, get_builder

INVVEE = "dipoles.invvee"
APEX = "dipoles.invvee_apex"
OTHER = "dipoles.ocf_dipole"
E7 = "dipoles.invvee:feed spelling (E7)"

# A small momwire-only study over both feed spellings: two rungs, one engine.
PAIR = f"""
import antennaknobs.analyses as an


def build_studies():
    return [
        an.convergence(
            name="pair",
            sweep=an.Sweep(an.DENSITY, values=(8, 12)),
            cross=(
                an.Cross(designs=({INVVEE!r}, {APEX!r})),
                an.Cross(engines=("momwire:bspline",)),
            ),
            views=(an.Table(),),
        ),
    ]
"""


def _sentinel_study(sentinel) -> str:
    """A study file whose import writes ``sentinel``: the proof it ran."""
    return f"from pathlib import Path\nPath({str(sentinel)!r}).write_text('ran')\n" + (
        PAIR
    )


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


@pytest.fixture(scope="module")
def client() -> TestClient:
    from antennaknobs.web import server

    return TestClient(server.app)


def _write(root, rel, text):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


# ── the catalog: E7 moved ────────────────────────────────────────────────


def test_e7_is_a_study_of_the_invvee_module_and_no_longer_an_analysis():
    found = studies.discover()
    (e7,) = [s for s in found.studies if s.name == E7]
    assert e7.source == INVVEE and e7.path is None
    assert e7.designs == (INVVEE, APEX)
    assert e7.analysis.curves == 6
    names = {a.name for a in get_builder(INVVEE)().build_analyses()}
    assert "feed spelling (E7)" not in names and "feed spellings" not in names
    # invvee_apex inherits invvee's Builder, and so its build_analyses; the
    # study was never a method, so it is on neither design's own list.
    assert "feed spelling (E7)" not in {a.name for a in an.offered(get_builder(APEX)())}


def test_only_modules_that_define_build_studies_are_imported_for_it():
    mods = studies._catalog_modules()
    assert INVVEE in mods
    # invvee_apex imports invvee's Builder, not its function: not a source.
    assert APEX not in mods


@pytest.mark.parametrize(
    ("design", "has"),
    [(INVVEE, True), (APEX, True), (f"{INVVEE}:dipole", True), (OTHER, False)],
)
def test_a_study_is_offered_on_every_design_it_crosses(design, has):
    assert (E7 in {s.name for s in studies.including(design)}) is has


# ── the user folder: nesting, trust ──────────────────────────────────────


def test_an_unallowed_study_file_is_listed_as_needing_allow_and_never_imported(
    folder, tmp_path, capsys
):
    sentinel = tmp_path / "ran.txt"
    _write(folder, "feeds/e7.py", _sentinel_study(sentinel))
    found = studies.discover()
    (blocked,) = [b for b in found.blocked if b.source == "feeds/e7"]
    assert blocked.allow == "antennaknobs allow feeds/e7"
    assert blocked.reason.startswith("NOT ALLOWED")
    assert not any(s.source == "feeds/e7" for s in found.studies)
    cli(["analyze", "--list-studies"])
    out = capsys.readouterr().out
    assert "feeds/e7  (cannot run)" in out
    assert "antennaknobs allow feeds/e7" in out
    for name in ("feeds/e7", "feeds/e7:pair"):
        with pytest.raises(SystemExit, match="NOT ALLOWED"):
            cli(["analyze", "--study", name])
    assert not sentinel.exists()


def test_allow_takes_a_nested_name_and_keys_it_under_the_studies_folder(
    folder, tmp_path, capsys
):
    sentinel = tmp_path / "ran.txt"
    path = _write(folder, "feeds/deep/e7.py", _sentinel_study(sentinel))
    cli(["allow", "feeds/deep/e7"])
    store = json.loads((folder / ".trust.json").read_text())
    assert set(store["designs"]) == {"feeds/deep/e7.py"}
    assert store["designs"]["feeds/deep/e7.py"]["sha256"] == dt.content_hash(path)
    # The designs store is not touched: a study is keyed in its own folder.
    assert not dt.store_path().exists()
    (study,) = [s for s in studies.discover().studies if s.source == "feeds/deep/e7"]
    assert study.name == "feeds/deep/e7:pair" and sentinel.exists()
    # An edit asks again (pinned), and disallow removes the record.
    path.write_text(path.read_text() + "\n# edited\n")
    assert not dt.is_trusted(path)
    cli(["allow", "feeds/deep/e7", "--edits"])
    path.write_text(path.read_text() + "\n# again\n")
    assert dt.is_trusted(path)
    cli(["disallow", "feeds/deep/e7.py"])
    assert not dt.is_trusted(path)
    capsys.readouterr()


def test_a_bare_name_that_is_both_a_design_and_a_study_is_not_guessed(folder):
    import os
    from pathlib import Path

    designs = Path(os.environ["ANTENNAKNOBS_USER_DIR"])
    designs.mkdir()
    (designs / "twin.py").write_text("x = 1\n")
    _write(folder, "twin.py", PAIR)
    with pytest.raises(SystemExit, match="both a user design"):
        cli(["allow", "twin"])


def test_private_names_are_skipped_and_dotted_names_refused(folder):
    _write(folder, "_draft.py", PAIR)
    _write(folder, ".hidden/a.py", PAIR)
    _write(folder, "__pycache__/b.py", PAIR)
    _write(folder, "v1.2/c.py", PAIR)
    listed = studies.study_files()
    assert [(s, p.name) for s, p, _ in listed] == [(None, "c.py")]
    (why,) = [w for _, _, w in listed]
    assert "'v1.2'" in why


# ── the rule and the names ───────────────────────────────────────────────

NO_DESIGNS = """
import antennaknobs.analyses as an


def build_studies():
    return [an.convergence(name="lonely")]
"""


def test_a_study_without_designs_is_refused_by_name(folder, monkeypatch, capsys):
    monkeypatch.setenv("ANTENNAKNOBS_TRUST_USER_DESIGNS", "1")
    _write(folder, "solo.py", NO_DESIGNS)
    found = studies.discover()
    (b,) = [b for b in found.blocked if b.source == "solo"]
    assert b.name == "lonely" and b.label == "solo:lonely"
    assert b.reason.startswith("REFUSED: a study names its designs")
    with pytest.raises(SystemExit, match=r"study 'solo:lonely': REFUSED"):
        studies.find("lonely", found)
    cli(["analyze", "--list-studies"])
    assert "solo:lonely  (cannot run)" in capsys.readouterr().out


TWO_ALIKE = PAIR.replace("    ]\n", "    ] * 2\n")


def test_names_are_unique_across_sources_and_refused_twice_in_one(folder, monkeypatch):
    monkeypatch.setenv("ANTENNAKNOBS_TRUST_USER_DESIGNS", "1")
    _write(folder, "a.py", PAIR)
    _write(folder, "feeds/a.py", PAIR)
    _write(folder, "twice.py", TWO_ALIKE)
    found = studies.discover()
    names = [s.name for s in found.studies]
    assert len(names) == len(set(names))
    assert {"a:pair", "feeds/a:pair"} <= set(names)
    assert [b.reason for b in found.blocked if b.source == "twice"] == [
        "REFUSED: 2 studies in twice are named 'pair'; give one a name="
    ] * 2
    # Lookup: the full name, a source holding one study, else a bare name
    # when only one study has it.
    assert studies.find("feeds/a:pair", found).source == "feeds/a"
    assert studies.find("feeds/a", found).name == "feeds/a:pair"
    with pytest.raises(SystemExit, match="ambiguous.*'a:pair', 'feeds/a:pair'"):
        studies.find("pair", found)
    assert studies.find("feed spelling (E7)", found).name == E7
    with pytest.raises(SystemExit, match="no study 'nope'"):
        studies.find("nope", found)


# ── the CLI ──────────────────────────────────────────────────────────────


def test_list_studies_lists_e7_and_filters_by_builder(capsys):
    cli(["analyze", "--list-studies"])
    out = capsys.readouterr().out
    assert E7 in out
    assert f"crosses {INVVEE}, {APEX}" in out
    assert "density" in out and "6 curves" in out
    cli(["analyze", "--list-studies", "--builder", APEX])
    assert E7 in capsys.readouterr().out
    cli(["analyze", "--list-studies", "--builder", OTHER])
    assert capsys.readouterr().out.strip() == f"no studies crossing {OTHER}"


def test_study_code_prints_the_python_that_evals_equal(capsys):
    cli(["analyze", "--study", "feed spelling (E7)", "--code"])
    code = capsys.readouterr().out
    assert eval(code, {"an": an}) == studies.find(E7).analysis
    assert 'name="feed spelling (E7)"' in code


def test_list_and_study_are_one_or_the_other():
    with pytest.raises(SystemExit, match="give one of --list-studies / --study"):
        cli(["analyze", "--list-studies", "--study", "x"])


def _capture_run(monkeypatch):
    got = []
    inner = ar.run

    def wrapped(*args, **kwargs):
        out = inner(*args, **kwargs)
        got.append(out)
        return out

    monkeypatch.setattr(ar, "run", wrapped)
    return got


def test_a_study_runs_exactly_as_a_design_analysis_with_a_designs_cross(
    folder, monkeypatch, capsys, tmp_path
):
    """The oracle is the route that existed before studies: the same
    analysis offered as invvee's own and run with ``--analysis``."""
    monkeypatch.setenv("ANTENNAKNOBS_TRUST_USER_DESIGNS", "1")
    _write(folder, "feeds/pair.py", PAIR)
    study = studies.find("feeds/pair:pair")
    runs = _capture_run(monkeypatch)
    cli(["analyze", "--study", "feeds/pair", "--ground", "free",
         "--fn", str(tmp_path / "s.png")])  # fmt: skip
    got = runs[-1]
    cls = type(get_builder(INVVEE)())
    monkeypatch.setattr(cls, "build_analyses", lambda self: [study.analysis])
    cli(["analyze", "--builder", INVVEE, "--analysis", "pair", "--ground", "free",
         "--fn", str(tmp_path / "a.png")])  # fmt: skip
    want = runs[-1]
    capsys.readouterr()
    labels = [f"{INVVEE}, momwire:bspline", f"{APEX}, momwire:bspline"]
    assert sorted(got["curves"]) == sorted(labels) and got["refused"] == {}
    for label in labels:
        assert got["curves"][label] == want["curves"][label]
    # Adversarial: the two feed spellings are different curves.
    a, b = (got["curves"][lab][1][-1] for lab in labels)
    assert abs(a - b) > 0.1


# ── /analyses ────────────────────────────────────────────────────────────


def _listing(client, geometry):
    r = client.post("/analyses", json={"geometry": geometry})
    assert r.status_code == 200, r.text
    return r.json()["analyses"]


@pytest.mark.parametrize("geometry", [INVVEE, APEX])
def test_the_listing_serves_e7_after_the_designs_own_on_both_its_designs(
    client, geometry
):
    got = _listing(client, geometry)
    names = [a["name"] for a in got]
    assert names[-1] == E7
    own = [a["name"] for a in got if "study" not in a]
    assert own == names[: len(own)]
    (e7,) = [a for a in got if a["name"] == E7]
    assert e7["study"] == {"source": INVVEE, "name": "feed spelling (E7)"}
    assert e7["problems"] == []
    w = e7["workbench"]
    assert w["runs"] is True and w["axes"] == ["designs", "engines"]
    assert [d["name"] for d in w["designs"]] == [INVVEE, APEX]
    assert eval(e7["code"], {"an": an}) == studies.find(E7).analysis


def test_the_listing_of_another_design_has_no_studies(client):
    assert not [a for a in _listing(client, OTHER) if "study" in a]


def test_a_user_study_is_served_once_allowed(client, folder, tmp_path):
    sentinel = tmp_path / "ran.txt"
    path = _write(folder, "feeds/e7.py", _sentinel_study(sentinel))
    assert "feeds/e7:pair" not in {a["name"] for a in _listing(client, APEX)}
    assert not sentinel.exists()
    dt.trust(path)
    got = {a["name"]: a for a in _listing(client, APEX)}
    assert got["feeds/e7:pair"]["study"] == {"source": "feeds/e7", "name": "pair"}
    assert "feeds/e7:pair" not in {a["name"] for a in _listing(client, OTHER)}


# ── the method form: this design against references ──────────────────────

CMP = """
from antennaknobs import analyses as an
from antennaknobs.designs.dipoles.invvee import Builder as InvVee


class Builder(InvVee):
    def build_studies(self):
        return [
            an.convergence(
                name="vs apex",
                sweep=an.Sweep(an.DENSITY, values=(8, 12)),
                # Self listed too, and last: it is dropped, and stays first.
                cross=(
                    an.Cross(designs=("dipoles.invvee_apex", "user.cmp")),
                    an.Cross(engines=("momwire:bspline",)),
                ),
                views=(an.Table(),),
            ),
            an.convergence(name="alone"),
        ]
"""


@pytest.fixture
def cmp_design(tmp_path, monkeypatch):
    """``user.cmp``: invvee's geometry unchanged, with a method study."""
    import antennaknobs.web.user_designs as web_user_designs

    designs = tmp_path / "designs"
    designs.mkdir()
    (designs / "cmp.py").write_text(CMP)
    monkeypatch.setenv("ANTENNAKNOBS_USER_DIR", str(designs))
    monkeypatch.setenv("ANTENNAKNOBS_STUDIES_DIR", str(tmp_path / "studies"))
    web_user_designs.refresh()
    yield "user.cmp"
    monkeypatch.undo()
    web_user_designs.refresh()


def test_the_base_builder_has_no_studies():
    assert tuple(get_builder(OTHER)().build_studies()) == ()


def test_a_method_study_puts_this_design_first_and_drops_an_explicit_self(cmp_design):
    found = studies.of_builder(cmp_design, get_builder(cmp_design)())
    (st,) = found.studies
    assert st.name == "user.cmp:vs apex" and st.host == "user.cmp"
    assert st.designs == ("user.cmp", APEX)
    # Listed on its own design's tab only, though it crosses invvee_apex.
    assert st.includes("user.cmp") and not st.includes(APEX)
    (refused,) = found.blocked
    assert refused.label == "user.cmp:alone"
    assert refused.reason.startswith(
        "REFUSED: a Builder's study names the designs it compares this one with"
    )


def test_a_method_study_is_listed_under_its_own_design_only(cmp_design, capsys):
    cli(["analyze", "--list-studies", "--builder", cmp_design])
    out = capsys.readouterr().out
    assert "user.cmp:vs apex" in out and f"crosses user.cmp, {APEX}" in out
    assert "user.cmp:alone  (cannot run)" in out
    for other in ([], ["--builder", APEX]):
        cli(["analyze", "--list-studies", *other])
        assert "user.cmp:" not in capsys.readouterr().out


def test_a_method_studys_own_cell_is_this_design(
    cmp_design, monkeypatch, capsys, tmp_path
):
    """user.cmp is invvee's geometry unchanged, so its first cell equals
    invvee's cell of the same ladder, and differs from the apex."""
    runs = _capture_run(monkeypatch)
    cli(["analyze", "--study", "user.cmp:vs apex", "--ground", "free",
         "--fn", str(tmp_path / "m.png")])  # fmt: skip
    got = runs[-1]
    capsys.readouterr()
    assert list(got["curves"]) == [
        "user.cmp, momwire:bspline",
        f"{APEX}, momwire:bspline",
    ]
    _write(tmp_path / "studies", "pair.py", PAIR)
    cli(["analyze", "--study", "pair:pair", "--ground", "free",
         "--fn", str(tmp_path / "p.png")])  # fmt: skip
    want = runs[-1]
    capsys.readouterr()
    ours = got["curves"]["user.cmp, momwire:bspline"]
    assert ours == want["curves"][f"{INVVEE}, momwire:bspline"]
    assert ours[1][-1] != got["curves"][f"{APEX}, momwire:bspline"][1][-1]


def test_a_method_study_is_served_on_its_own_tab_only(client, cmp_design):
    got = {a["name"]: a for a in _listing(client, cmp_design)}
    st = got["user.cmp:vs apex"]
    assert st["study"] == {"source": "user.cmp", "name": "vs apex"}
    assert [d["name"] for d in st["workbench"]["designs"]] == ["user.cmp", APEX]
    assert E7 not in got  # user.cmp is not one of E7's designs
    assert "user.cmp:vs apex" not in {a["name"] for a in _listing(client, APEX)}


def test_a_name_both_forms_give_in_one_source_is_refused_in_both(monkeypatch):
    e7 = studies.find(E7).analysis
    cls = type(get_builder(INVVEE)())
    monkeypatch.setattr(
        cls,
        "build_studies",
        lambda self: [an.convergence(name=e7.name, cross=an.Cross(designs=(APEX,)))],
    )
    found = studies.pool(INVVEE, get_builder(INVVEE)())
    assert E7 not in {s.name for s in found.studies}
    clash = [b for b in found.blocked if b.label == E7]
    assert len(clash) == 2
    assert "its module's build_studies() and its Builder's" in clash[0].reason
    # Another design's tab is untouched: the method study is not its.
    assert E7 in {s.name for s in studies.pool(APEX, get_builder(APEX)()).studies}

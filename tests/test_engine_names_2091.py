"""momwire#2091 in antennaknobs: the engine names, old and new.

momwire 0.97.0 renamed its bases (Steve, 11-21): a short name carries no dash
and names the basis alone (`bspline` -> `bs2`, `bspline-d1` -> `bs1`,
`sinusoidal-galerkin` -> `sg`, `razor-2p` -> `razor2p`), and retired
`razor-nec5`. antennaknobs follows with one alias table,
`antennaknobs.engine_names`. Three claims are held here:

(a) every place antennaknobs READS an engine name still reads the old
    spelling, as the same engine: the CLI's `--engine`, a web request's
    `momwire_model`, a settings.toml slot, the served `backend_aliases`, an
    analysis (a study, a kept file, a shared link's `analyses=`). "The same"
    is measured, not assumed: the old name and the new solve to the same Z,
    bit for bit. `razor-nec5` is refused by name, as momwire refuses it.
(b) nothing antennaknobs SHOWS or WRITES names an old spelling: a census of
    the app's source, the site's docs, README and CLAUDE.md, with a per-file
    allowlist of exact counts (it fails when a count moves either way), plus
    the served /capabilities payload and the CLI's help. Dated records under
    docs/status keep the names they were written with and are not scanned.
(c) the table is momwire's: `DEPRECATED_NAMES` equals momwire's
    `BASIS_ALIASES` and `RETIRED_NAMES` its `RETIRED_BASES`, wherever the
    installed momwire carries them.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import antennaknobs as ant
import antennaknobs.web.server  # noqa: F401 — resolves the adapter import cycle
from antennaknobs import analyses as an
from antennaknobs import analyses_text, engine_names, keep, momwire_bases
from antennaknobs.cli import engine_density, make_engine_factory, parse_engine_spec
from antennaknobs.web import adapter, server
from antennaknobs.web import settings as ui_settings

ROOT = Path(__file__).resolve().parents[1]

OLD_TO_NEW = {
    "bspline": "bs2",
    "bspline-d1": "bs1",
    "sinusoidal-galerkin": "sg",
    "razor-2p": "razor2p",
}
# The web tabs among them (`bs1` is the `bs2` tab at degree 1, not a tab).
WEB_OLD_TO_NEW = {o: n for o, n in OLD_TO_NEW.items() if o != "bspline-d1"}


@pytest.fixture(scope="module")
def client():
    return TestClient(server.app)


# ── (c) the table is momwire's ─────────────────────────────────────────────


def test_the_table_is_the_rename():
    assert dict(engine_names.DEPRECATED_NAMES) == OLD_TO_NEW
    assert dict(engine_names.RETIRED_NAMES) == {"razor-nec5": "razor2p"}


def test_the_table_equals_momwires():
    names = pytest.importorskip(
        "momwire._basis_names",
        reason="the installed momwire predates momwire#2091 (no _basis_names)",
    )
    assert dict(engine_names.DEPRECATED_NAMES) == dict(names.BASIS_ALIASES)
    assert dict(engine_names.RETIRED_NAMES) == dict(names.RETIRED_BASES)
    # The refusal is momwire's sentence, word for word.
    assert engine_names.retired_refusal("razor-nec5") == names.retired_refusal(
        "razor-nec5"
    )


def test_every_new_name_is_a_roster_name_or_alias():
    for new in OLD_TO_NEW.values():
        assert new in momwire_bases.cli_names(), new
    for old in [*OLD_TO_NEW, "razor-nec5"]:
        assert old not in momwire_bases.cli_names(), old


# ── (a) the old names are read, as the same engine ─────────────────────────


@pytest.mark.parametrize(("old", "new"), OLD_TO_NEW.items())
def test_the_cli_reads_an_old_name_as_the_new(old, new):
    assert parse_engine_spec(f"momwire:{old}") == parse_engine_spec(f"momwire:{new}")
    assert engine_density(f"momwire:{old}") == engine_density(f"momwire:{new}")


@pytest.mark.parametrize(
    ("old", "new"), [("bspline-d1", "bs1"), ("razor-2p", "razor2p")]
)
def test_an_old_cli_name_solves_the_same_z(old, new):
    from antennaknobs import resolve_variant_params
    from antennaknobs.designs.dipoles.invvee import Builder

    def z(spec):
        b = Builder(resolve_variant_params(Builder, "dipole"))
        b.nominal_nsegs = 10
        (got,) = make_engine_factory(f"momwire:{spec}", None)(b).impedance()
        return got

    assert z(old) == z(new)


def test_razor_nec5_is_refused_by_name_everywhere_it_is_read():
    import argparse

    words = "basis 'razor-nec5' was renamed and is no longer accepted; use 'razor2p'"
    with pytest.raises(argparse.ArgumentTypeError, match=re.escape(words)):
        parse_engine_spec("momwire:razor-nec5")
    assert engine_density("momwire:razor-nec5") is None
    with pytest.raises(ValueError, match=re.escape(words)):
        an.Cross(engines=("momwire:razor-nec5",))
    with pytest.raises(analyses_text.AnalysesTextError, match="razor2p"):
        analyses_text.read(
            "an.Analysis('a', an.Sweep(an.FREQUENCY, 14.0, 14.3), "
            "engine='momwire:razor-nec5')"
        )


@pytest.mark.parametrize(("old", "new"), WEB_OLD_TO_NEW.items())
def test_an_old_web_request_solves_the_same_z(client, old, new):
    """A stale client (or a request built from an old saved session) that
    sends the old `momwire_model` solves the same basis, bit for bit."""

    def z(model):
        r = client.post(
            "/sweep",
            json={
                "geometry": "dipoles.invvee",
                "freqs_mhz": [28.47],
                "measurement_freq_mhz": 28.47,
                "momwire_model": model,
                "n_per_wire": 10,
            },
        )
        assert r.status_code == 200, r.text
        (rec,) = [json.loads(x) for x in r.text.splitlines() if '"z_re"' in x]
        return rec["z_re"], rec["z_im"]

    assert z(old) == z(new)


def test_an_old_request_binds_the_new_names_kwargs():
    """`razor-2p` must stay the two-point lane: the binding follows the name
    it now is, not the spelling."""
    assert adapter.request_model({"momwire_model": "razor-2p"}) == "razor2p"
    assert adapter.request_model({}) == "bs2"
    assert adapter._MOMWIRE_BOUND["razor2p"] == {"nec5_quadrature": True}


def test_the_served_aliases_carry_every_old_tab_name():
    aliases = adapter.backend_aliases()
    for old, new in WEB_OLD_TO_NEW.items():
        assert aliases[old] == new
    assert aliases["triangular"] == "bs2"


def test_an_old_settings_slot_opens_on_the_new_tab(monkeypatch, tmp_path):
    path = tmp_path / "settings.toml"
    monkeypatch.setenv(ui_settings.SETTINGS_ENV, str(path))
    cat = ui_settings.catalog(have_pynec=False, have_nec5=False, have_nec2=False)
    path.write_text(
        '[slots.A]\nbackend = "razor-2p"\nn_per_wire = 21\n\n'
        '[slots.B]\nbackend = "bspline"\n\n'
        '[slots.C]\nbackend = "sinusoidal-galerkin"\n'
    )
    payload = ui_settings.load(cat, hosted=False)
    assert payload["problems"] == []
    seeds = {
        s["slot"]: s
        for s in ui_settings.overlay_slots(list(cat.stock_slots), payload["slots"])
    }
    assert seeds["A"]["backend"] == "razor2p"
    assert seeds["A"]["n_per_wire"] == 21
    assert seeds["B"]["backend"] == "bs2"
    assert seeds["C"]["backend"] == "sg"


def test_an_old_analysis_reads_as_the_new_names():
    """A study, a kept file and a shared link's `analyses=` all build their
    analyses through these constructors, so an old spelling is read once
    here, and what is written back (`to_code`, `to_data`) is the new name."""
    a = an.Analysis(
        "engines",
        an.Sweep(an.FREQUENCY, 14.0, 14.3),
        cross=an.Cross(engines=("momwire:bspline", "momwire:razor-2p", "nec5")),
        engine="momwire:sinusoidal-galerkin",
    )
    assert a.cross[0].engines == ("momwire:bs2", "momwire:razor2p", "nec5")
    assert a.engine == "momwire:sg"
    cell = an.Cell(engine="momwire:bspline-d1")
    assert cell.engine == "momwire:bs1"
    text = analyses_text.write([a])
    for old in OLD_TO_NEW:
        assert f"momwire:{old}'" not in text and f'momwire:{old}"' not in text
    # A shared link written before the rename opens on the same engines.
    old_link = analyses_text.pack(
        "an.Analysis('engines', an.Sweep(an.FREQUENCY, 14.0, 14.3), "
        "cross=an.Cross(engines=('momwire:bspline', 'momwire:razor-2p')))"
    )
    (got,) = analyses_text.read_link(old_link)
    assert got.cross[0].engines == ("momwire:bs2", "momwire:razor2p")
    # A kept file's data form, written before the rename.
    data = an.to_data(a)
    blob = json.dumps(data).replace("momwire:bs2", "momwire:bspline")
    assert an.from_data(json.loads(blob)) == a


def test_a_kept_request_under_an_old_name_keeps_the_new_spelling():
    assert keep.engine_of({"momwire_model": "bspline"}, "pin") == "momwire:bs2"
    assert (
        keep.engine_of(
            {"momwire_model": "bspline", "model_options": {"degree": 1}}, "pin"
        )
        == "momwire:bs1"
    )
    assert keep.engine_of({"momwire_model": "razor-2p"}, "pin") == "momwire:razor2p"


# ── (b) nothing shown or written names an old spelling ────────────────────

# The old names as words: a module path (`momwire.bspline`, `_accel_bspline`),
# an identifier part, or momwire's axis vocabulary (`bspline-1/2/3`) is not
# one. The bare `bspline` rule is the rename's own.
_OLD = re.compile(
    r"(?<![\w./-])(?:bspline-d1|sinusoidal-galerkin|razor-2p|razor-nec5)(?![\w-])"
    r"|\b(?:nec5|nec42|nec2c)-bspline(?![\w-])"
    r"|(?<![\w./-])bspline(?![\w]|-\d|-\$|\.\w)"
)
# Not engine names: the B-spline PANEL id (served as `panel`, and the
# frontend's panel state), and paths that carry an old name.
_NOT_NAMES = re.compile(
    r'panel(?:=|: | ===? | !==? )"bspline"|opts\.bspline|bsplineOpts'
    r"|import bspline|getattr\(bspline|docs/sinusoidal-galerkin[\w.-]*"
)

# Every file that may still name an old spelling, and how many times: the
# alias table and the notes that explain it. A count that moves either way
# fails, so a new old name is red and so is a stale entry here.
_ALLOWED = {
    "CLAUDE.md": 5,
    "site/src/content/docs/reference/cli.md": 7,
    "src/antennaknobs/engine_names.py": 8,
    "src/antennaknobs/momwire_bases.py": 1,
    "src/antennaknobs/cli.py": 5,
    "src/antennaknobs/keep.py": 1,
    "src/antennaknobs/density.py": 2,
    "src/antennaknobs/analyses.py": 2,
    "src/antennaknobs/web/adapter.py": 4,
    "src/antennaknobs/web/frontend/src/lib/chartCells.ts": 1,
    "src/antennaknobs/web/frontend/src/__tests__/noEngineNames.test.ts": 5,
    "src/antennaknobs/web/frontend/src/__tests__/chartCells.test.ts": 1,
}


def _shown_files():
    yield ROOT / "README.md"
    yield ROOT / "CLAUDE.md"
    for sub, globs in (
        ("site/src/content/docs", ("*.md", "*.mdx")),
        ("docs", ("*.md",)),
        ("src/antennaknobs", ("*.py", "*.ts", "*.tsx", "*.css", "*.json")),
    ):
        for g in globs:
            for p in sorted((ROOT / sub).rglob(g)):
                rel = p.relative_to(ROOT).as_posix()
                if rel.startswith("docs/status/") or "/node_modules/" in rel:
                    continue
                yield p


def _count(text: str) -> int:
    return len(_OLD.findall(_NOT_NAMES.sub("", text)))


def test_no_old_name_in_what_antennaknobs_shows_or_writes():
    found = {}
    for p in _shown_files():
        n = _count(p.read_text(encoding="utf-8", errors="replace"))
        if n:
            found[p.relative_to(ROOT).as_posix()] = n
    assert found == _ALLOWED


def test_the_census_sees_every_old_name():
    """The census regex is the gate: it must see each old spelling as a word
    and leave alone what is not an engine name."""
    for old in [*OLD_TO_NEW, "razor-nec5", "nec5-bspline", "momwire:bspline"]:
        assert _count(f"run `{old}` here") == 1, old
    for not_a_name in (
        "momwire.bspline",
        "from momwire import bspline",
        "_accel_bspline.cpp",
        '"bspline-2"',
        "`bspline-${d}`",
        "getattr(bspline, name)",
        'panel="bspline"',
        "bs2",
        "razor2p",
        "docs/sinusoidal-galerkin-instrument-report.md",
    ):
        assert _count(not_a_name) == 0, not_a_name


def test_the_served_capabilities_name_no_old_spelling(client):
    caps = client.get("/capabilities").json()
    aliases = caps.pop("backend_aliases")
    assert set(WEB_OLD_TO_NEW) <= set(aliases)
    assert _count(json.dumps(caps)) == 0


@pytest.mark.parametrize(
    "command", ["pattern", "sweep", "compare_patterns", "optimize"]
)
def test_the_cli_help_names_no_old_spelling(command, capsys, monkeypatch):
    monkeypatch.setenv("COLUMNS", "1000")
    with pytest.raises(SystemExit):
        ant.cli([command, "--help"])
    assert _count(capsys.readouterr().out) == 0

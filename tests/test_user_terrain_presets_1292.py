"""User terrain presets from the designs folder (issue #1292, "shape 2").

A ``.py`` file in the designs folder that binds a `TerrainPreset` to ``TERRAIN``
and defines no ``Builder`` is a terrain: one per file, named by the file. It
joins the built-in presets on ``/capabilities`` for every design and solves
like one. A user file cannot take a built-in's name, and a file with a
mistake in it reaches the error list instead of leaving the terrain list
without a word.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from starlette.testclient import TestClient

import antennaknobs.terrain as terrain_mod
from antennaknobs import user_designs as core_user_designs
from antennaknobs.terrain import (
    Facet,
    Sector,
    Terrain,
    TerrainField,
    TerrainMarker,
    TerrainPreset,
)
from antennaknobs.web import server as server_mod
from antennaknobs.web.server import app

# Imported after server: adapter and examples import each other cyclically,
# and only the examples-first entry order (which server triggers) resolves.
import antennaknobs.web.adapter as adapter
from antennaknobs.web import user_designs
from antennaknobs.web.examples import REGISTRY

BUILTIN = ["levee", "cliff", "hillside"]

BLUFF = '''"""A bluff over a lake."""

from antennaknobs.terrain import Facet, Sector, Terrain, TerrainField, TerrainPreset

SOIL = (11.0, 0.004)
LAKE = (80.0, 0.001)


def build(v):
    return Terrain(
        (
            Sector(
                0.0,
                360.0,
                (
                    Facet(v["edge_m"], 0.0, *SOIL),
                    Facet(v["edge_m"] + 2 * v["drop_m"], -v["drop_m"], *SOIL),
                    Facet(None, -v["drop_m"], *LAKE),
                ),
            ),
        )
    )


TERRAIN = TerrainPreset(
    tooltip="Flat ground out to a bluff, then lake.",
    media_note="media: lake 80 / 0.001, soil 11 / 0.004",
    fields=(
        TerrainField("edge_m", "edge of the bluff", 15.0, 1.0, 500.0, 1.0, "m"),
        TerrainField("drop_m", "drop to the lake", 6.0, 0.5, 100.0, 0.5, "m"),
    ),
    build=build,
)
'''

DESIGN = """
from types import MappingProxyType
from antennaknobs import AntennaBuilder

class Builder(AntennaBuilder):
    default_params = MappingProxyType({"freq": 14.0, "half_length": 5.0})

    def build_wires(self):
        h = self.half_length
        return [((0.0, -h, 10.0), (0.0, h, 10.0), 11, 1 + 0j)]
"""


@pytest.fixture
def userdir(tmp_path, monkeypatch):
    """A clean, trusted designs folder; nothing of it survives the test."""
    monkeypatch.setenv("ANTENNAKNOBS_USER_DIR", str(tmp_path))
    monkeypatch.setenv("ANTENNAKNOBS_TRUST_USER_DESIGNS", "1")
    monkeypatch.chdir(tmp_path)

    def _clear():
        for k in [k for k in REGISTRY if k.startswith("user.")]:
            del REGISTRY[k]
        adapter.set_user_terrain_presets({})

    _clear()
    yield tmp_path
    _clear()


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


def _names():
    return [p["name"] for p in adapter.terrain_presets_schema()]


def _messages(errors, stem):
    return [e["message"] for e in errors if e["name"] == f"user.{stem}"]


def _req(preset, **fields):
    return {
        "ground": True,
        "ground_model": "terrain",
        "terrain": {"preset": preset, **fields},
    }


# --- the public types -------------------------------------------------------


def test_the_preset_types_are_public_in_antennaknobs_terrain():
    """A user file builds its preset from `antennaknobs.terrain` alone, and
    the adapter's built-ins are the same classes, not private copies."""
    for name in ("TerrainPreset", "TerrainField", "TerrainMarker"):
        assert hasattr(terrain_mod, name)
        assert not hasattr(adapter, f"_{name}")
    assert all(type(p) is TerrainPreset for p in adapter._TERRAIN_PRESETS)
    assert all(type(f) is TerrainField for f in adapter._TERRAIN_PRESETS[0].fields)
    assert type(adapter._TERRAIN_PRESETS[0].marker) is TerrainMarker
    assert tuple(BUILTIN) == terrain_mod.BUILTIN_PRESET_NAMES


@pytest.mark.parametrize(
    ("kwargs", "sentence"),
    [
        (
            {"default": 20.0},
            "terrain field 'edge_m': default (20) must lie between min (1) and max (10)",
        ),
        ({"min": 10.0}, "terrain field 'edge_m': min (10) must be below max (10)"),
        ({"step": 0.0}, "terrain field 'edge_m': step must be positive, got 0"),
        (
            {"default": float("nan")},
            "terrain field 'edge_m': default must be finite, got nan",
        ),
        ({"max": "far"}, "terrain field 'edge_m': max must be a number, got 'far'"),
    ],
)
def test_a_field_with_bad_bounds_is_refused_in_words(kwargs, sentence):
    spec = {"default": 5.0, "min": 1.0, "max": 10.0, "step": 1.0, **kwargs}
    with pytest.raises(ValueError) as exc:
        TerrainField("edge_m", "edge", **spec)
    assert str(exc.value) == sentence


def test_a_preset_is_checked_when_it_is_made():
    field = TerrainField("edge_m", "edge", 5.0, 1.0, 10.0, 1.0)

    def build(v):
        return None

    with pytest.raises(ValueError, match="needs at least one field"):
        TerrainPreset(fields=(), build=build)
    with pytest.raises(ValueError, match="'edge_m' is listed twice"):
        TerrainPreset(fields=(field, field), build=build)
    with pytest.raises(ValueError, match="build must be a function, got 3"):
        TerrainPreset(fields=(field,), build=3)
    with pytest.raises(
        ValueError,
        match=r"marker names field 'bearing', which this preset does not have "
        r"\(fields: edge_m\)",
    ):
        TerrainPreset(
            fields=(field,), build=build, marker=TerrainMarker("bearing", "a", "b")
        )
    # A list of fields is accepted and stored as a tuple.
    assert TerrainPreset(fields=[field], build=build).fields == (field,)


# --- a terrain file is listed, for every design -----------------------------


def test_a_terrain_file_joins_the_served_list_under_its_file_name(userdir, client):
    (userdir / "lake_bluff.py").write_text(BLUFF)
    assert user_designs.refresh() == []
    assert _names() == [*BUILTIN, "lake_bluff"]
    served = client.get("/capabilities").json()["terrain_presets"]
    assert served == adapter.terrain_presets_schema()
    mine = served[-1]
    assert (mine["name"], mine["label"]) == ("lake_bluff", "lake_bluff")
    assert mine["tooltip"] == "Flat ground out to a bluff, then lake."
    assert mine["media_note"] == "media: lake 80 / 0.001, soil 11 / 0.004"
    assert mine["fields"][0] == {
        "key": "edge_m",
        "label": "edge of the bluff",
        "unit": "m",
        "default": 15.0,
        "min": 1.0,
        "max": 500.0,
        "step": 1.0,
    }
    # It is a terrain, not a design: nothing joins the design registry.
    assert not [k for k in REGISTRY if k.startswith("user.")]


def test_deleting_the_file_takes_the_terrain_off_the_list(userdir):
    """The mutation check the issue asks for: no registration, no preset."""
    path = userdir / "lake_bluff.py"
    path.write_text(BLUFF)
    user_designs.refresh()
    assert "lake_bluff" in _names()
    path.unlink()
    assert user_designs.refresh() == []
    assert _names() == BUILTIN


def test_the_built_in_list_is_unchanged_with_no_terrain_file(userdir):
    (userdir / "my_dipole.py").write_text(DESIGN)
    assert user_designs.refresh() == []
    assert _names() == BUILTIN
    assert "user.my_dipole" in REGISTRY


def test_user_terrains_are_listed_after_the_built_ins_in_name_order(userdir):
    for stem in ("zebra_ridge", "alder_flat"):
        (userdir / f"{stem}.py").write_text(BLUFF)
    assert user_designs.refresh() == []
    assert _names() == [*BUILTIN, "alder_flat", "zebra_ridge"]


# --- it solves --------------------------------------------------------------


def test_the_request_builds_the_users_terrain_with_clamped_values(userdir):
    (userdir / "lake_bluff.py").write_text(BLUFF)
    user_designs.refresh()
    t = adapter._terrain_from_request(_req("lake_bluff", edge_m=9999.0, drop_m=4.0))
    assert isinstance(t, Terrain)
    assert t.crest_medium == (11.0, 0.004)  # the file's own soil, not 13/0.005
    edge, bank, lake = t.sectors[0].facets
    assert (edge.x1, bank.x1, bank.z1) == (500.0, 508.0, -4.0)  # edge clamped
    assert (lake.eps_r, lake.sigma) == (80.0, 0.001)
    assert t.diffraction is False  # as the built-ins: specular while live


def test_a_built_in_design_solves_on_the_users_terrain(userdir, client):
    (userdir / "lake_bluff.py").write_text(BLUFF)
    user_designs.refresh()
    req = {
        "geometry": "dipoles.invvee",
        "measurement_freq_mhz": 21.2,
        "momwire_model": "bspline",
        "az_elev_deg": 15.0,
        "elev_az_deg": 0.0,
        **_req("lake_bluff", edge_m=20.0, drop_m=8.0),
    }
    with client.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps(req))
        result = json.loads(ws.receive_text())
    assert "error" not in result
    assert result["ground_model_applied"] == "terrain"
    assert (result["ground_eps_r"], result["ground_sigma"]) == (11.0, 0.004)
    facets = result["ground_terrain"]["sectors"][0]["facets"]
    assert facets == [
        [20.0, 0.0, 11.0, 0.004],
        [36.0, -8.0, 11.0, 0.004],
        [None, -8.0, 80.0, 0.001],
    ]
    assert len(result["cuts"]["elevation"]) == 180


def test_an_edited_terrain_file_is_not_answered_from_the_old_solve(userdir):
    """The request does not change when the file does, so the solve key
    carries the reload count for a user terrain as it does for a user design
    (#1312), and a built-in terrain's key stays put."""
    (userdir / "lake_bluff.py").write_text(BLUFF)
    user_designs.refresh()
    mine = {"geometry": "dipoles.invvee", **_req("lake_bluff")}
    builtin = {"geometry": "dipoles.invvee", **_req("levee")}
    assert server_mod._is_user_geometry(mine)
    assert not server_mod._is_user_geometry(builtin)
    assert not server_mod._is_user_geometry({**mine, "ground": False})
    before = server_mod._canonical_solve_key(mine)
    before_builtin = server_mod._canonical_solve_key(builtin)
    user_designs.refresh()
    assert server_mod._canonical_solve_key(mine) != before
    assert server_mod._canonical_solve_key(builtin) == before_builtin


def test_a_build_that_returns_the_wrong_thing_is_named_at_the_solve(userdir):
    (userdir / "flat_lot.py").write_text(
        BLUFF.replace("    return Terrain(", "    return dict(\n        sectors=")
    )
    assert user_designs.refresh() == []
    with pytest.raises(TypeError) as exc:
        adapter._terrain_from_request(_req("flat_lot"))
    assert str(exc.value) == (
        "terrain 'flat_lot': build must return a Terrain (from "
        "antennaknobs.terrain), and it returned dict"
    )


# --- names ------------------------------------------------------------------


@pytest.mark.parametrize("stem", BUILTIN)
def test_a_file_cannot_take_a_built_in_terrains_name(userdir, stem):
    (userdir / f"{stem}.py").write_text(BLUFF)
    errors = user_designs.refresh()
    assert _messages(errors, stem) == [
        f"ValueError: '{stem}' is a built-in terrain and a file cannot replace "
        f"it; rename {stem}.py (for example to {stem}_mine.py)"
    ]
    assert _names() == BUILTIN
    # The built-in is still the one a request gets.
    built_in = {p.name: p for p in adapter._TERRAIN_PRESETS}[stem]
    preset, _ = adapter._clamped_terrain(_req(stem))
    assert preset is built_in


def test_the_adapter_refuses_a_built_in_name_however_it_arrives():
    preset = TerrainPreset(
        fields=(TerrainField("a", "a", 1.0, 0.0, 2.0, 1.0),), build=lambda v: None
    )
    with pytest.raises(ValueError, match="'cliff' is a built-in terrain"):
        adapter.set_user_terrain_presets({"cliff": preset})


def test_a_name_set_in_the_file_must_be_the_file_name(userdir):
    (userdir / "lake_bluff.py").write_text(
        BLUFF.replace("    build=build,\n)", '    build=build,\n    name="shore",\n)')
    )
    errors = user_designs.refresh()
    assert _messages(errors, "lake_bluff") == [
        "ValueError: `TERRAIN` sets name='shore', but a terrain file is named by "
        "its file name ('lake_bluff'); leave name out, or rename the file"
    ]
    assert _names() == BUILTIN


def test_the_same_terrain_name_in_a_second_folder_is_refused_aloud(userdir):
    """`./antenna_designs` is the second folder scanned. The first file is the
    terrain; the second is reported, not dropped in silence."""
    (userdir / "lake_bluff.py").write_text(BLUFF)
    second = userdir / "antenna_designs"
    second.mkdir()
    (second / "lake_bluff.py").write_text(BLUFF)
    errors = user_designs.refresh()
    assert [(e["file"], e["message"]) for e in errors] == [
        (
            str(second / "lake_bluff.py"),
            f"a terrain named 'lake_bluff' is already loaded from "
            f"{userdir / 'lake_bluff.py'}; this file is not used. Rename one "
            "of them.",
        )
    ]
    assert _names() == [*BUILTIN, "lake_bluff"]


# --- a broken terrain file reaches the error list ----------------------------


@pytest.mark.parametrize(
    ("edit", "message"),
    [
        (
            lambda s: s.replace("15.0, 1.0, 500.0", "15.0, 100.0, 500.0"),
            "ValueError: terrain field 'edge_m': default (15) must lie between "
            "min (100) and max (500) (line 29)",
        ),
        (
            lambda s: s[: s.index("TERRAIN = ")] + "TERRAIN = {'fields': []}\n",
            "TypeError: `TERRAIN` must be a TerrainPreset (from "
            "antennaknobs.terrain), and it is a dict",
        ),
        (
            # A different length from the good file on purpose: the loader
            # reads Python's bytecode cache, which tells two saves apart by
            # size and whole-second time, and this test makes both inside one.
            lambda s: s.replace("build=build,", "build=bild,"),
            "NameError: name 'bild' is not defined (line 32)",
        ),
        (
            lambda s: s + "\nclass Builder:\n    pass\n",
            "ValueError: this file defines both `Builder` and `TERRAIN`; a file "
            "is one antenna design or one terrain, so move one of them to a "
            "file of its own",
        ),
    ],
    ids=["bad-bounds", "not-a-preset", "typo", "builder-and-terrain"],
)
def test_a_broken_terrain_file_is_reported_not_dropped(userdir, edit, message):
    (userdir / "lake_bluff.py").write_text(edit(BLUFF))
    errors = user_designs.refresh()
    assert _messages(errors, "lake_bluff") == [message]
    assert errors[0]["file"] == str(userdir / "lake_bluff.py")
    assert errors[0]["trust_required"] is False
    assert _names() == BUILTIN
    # Fixed, it loads, and the report goes.
    (userdir / "lake_bluff.py").write_text(BLUFF)
    assert user_designs.refresh() == []
    assert _names() == [*BUILTIN, "lake_bluff"]


def test_the_error_reaches_the_page_through_examples(userdir, client):
    (userdir / "lake_bluff.py").write_text(BLUFF.replace("build=build,", ""))
    errors = client.get("/examples").json()["errors"]
    assert [e["name"] for e in errors] == ["user.lake_bluff"]
    assert errors[0]["message"].startswith("TypeError: ")
    assert "build" in errors[0]["message"]


def test_an_untrusted_terrain_file_asks_for_permission_and_does_not_run(
    userdir, monkeypatch
):
    monkeypatch.delenv("ANTENNAKNOBS_TRUST_USER_DESIGNS")
    marker = userdir / "ran.txt"
    (userdir / "lake_bluff.py").write_text(
        f"open({str(marker)!r}, 'w').close()\n" + BLUFF.split('"""\n', 1)[1]
    )
    errors = user_designs.refresh()
    assert [(e["name"], e["trust_required"]) for e in errors] == [
        ("user.lake_bluff", True)
    ]
    assert not marker.exists()
    assert _names() == BUILTIN


def test_a_file_with_neither_is_still_not_a_design_and_leaves_quietly(userdir):
    (userdir / "scratch.py").write_text("x = 1\n")
    assert user_designs.refresh() == []
    with pytest.raises(core_user_designs.NoBuilderError):
        core_user_designs.load_builder(userdir / "scratch.py", trust=True)


# --- the command line -------------------------------------------------------


def test_naming_a_terrain_file_as_a_design_says_what_it_is(userdir):
    (userdir / "lake_bluff.py").write_text(BLUFF)
    with pytest.raises(core_user_designs.NoBuilderError) as exc:
        core_user_designs.resolve_user_design("lake_bluff")
    assert str(exc.value) == (
        "lake_bluff.py defines a terrain (`TERRAIN`), not an antenna design; "
        "pick it as the ground's terrain in the web app"
    )


def test_load_user_file_says_which_kind_a_file_is(userdir):
    (userdir / "lake_bluff.py").write_text(BLUFF)
    (userdir / "my_dipole.py").write_text(DESIGN)
    kind, preset = core_user_designs.load_user_file(userdir / "lake_bluff.py")
    assert kind == "terrain" and preset.name == preset.label == "lake_bluff"
    kind, cls = core_user_designs.load_user_file(userdir / "my_dipole.py")
    assert kind == "design" and cls.__name__ == "Builder"


# --- the scaffold -----------------------------------------------------------


def test_the_scaffold_ships_a_terrain_template_that_loads_and_solves(
    tmp_path, monkeypatch
):
    target = tmp_path / "designs"
    monkeypatch.setenv("ANTENNAKNOBS_USER_DIR", str(target))
    monkeypatch.setenv("ANTENNAKNOBS_TRUST_USER_DESIGNS", "1")
    monkeypatch.chdir(tmp_path)
    user_designs.ensure_scaffold()
    template = target / "TERRAIN_TEMPLATE.py"
    assert template.is_file()
    try:
        # The template itself is reference material, never a terrain.
        assert user_designs.refresh() == []
        assert _names() == BUILTIN
        # Copied under a name of its own, as its header says, it is one.
        (target / "from_template.py").write_text(template.read_text())
        assert user_designs.refresh() == []
        assert _names() == [*BUILTIN, "from_template"]
        one_side = adapter._terrain_from_request(_req("from_template"))
        assert [len(s.facets) for s in one_side.sectors] == [3, 1]
        assert adapter._terrain_marker(_req("from_template")) == {
            "bearing_deg": 0.0,
            "label": "lake",
            "opposite": "land",
        }
        all_round = _req("from_template", width_deg=360.0)
        assert len(adapter._terrain_from_request(all_round).sectors) == 1
        assert adapter._terrain_marker(all_round) is None
    finally:
        adapter.set_user_terrain_presets({})


def test_the_contract_and_the_docs_describe_the_terrain_file():
    """The three places a user is told how: the folder's own contract, the
    designs guide and the web reference. Each must name the binding and the
    template, so a rename of either cannot leave the prose behind."""
    root = Path(__file__).resolve().parents[1]
    docs = root / "site" / "src" / "content" / "docs"
    for path in (
        root / "src/antennaknobs/web/user_design_assets/CLAUDE.md",
        docs / "concepts" / "authoring-with-claude.md",
        docs / "reference" / "web.md",
    ):
        text = path.read_text(encoding="utf-8")
        assert f"`{core_user_designs.TERRAIN_ATTR}`" in text, path
        assert "TERRAIN_TEMPLATE.py" in text, path
        assert "TerrainPreset" in text, path


def test_the_public_types_build_the_terrain_the_doc_example_shows():
    """The example in the guide, run: three facets, lake beyond the bank."""
    t = Terrain(
        (
            Sector(
                0.0,
                360.0,
                (
                    Facet(15.0, 0.0, 13.0, 0.005),
                    Facet(27.0, -6.0, 13.0, 0.005),
                    Facet(None, -6.0, 80.0, 0.001),
                ),
            ),
        )
    )
    assert t.crest_medium == (13.0, 0.005)

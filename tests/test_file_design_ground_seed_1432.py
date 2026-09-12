"""AK#1432 — a deck loaded from the designs folder seeds the app's ground switch
from its own GE/GN cards, and its slot label stops pretending N does anything.

Dan's first folder-route run: Example 2 (`GE 0`, a dipole at z = 0) opened
under the app's default finite ground and NEC-5 refused the wire in the
ground plane. The deck said free space; nothing read it. Now:

- `parse_nec` records `ground_spec` in the CLI's `--ground` shape (None,
  "pec", ("finite", eps_r, sigma)) and `ground_method` ("sommerfeld" for
  GN 2, "fast" for GN 0);
- the file builder publishes `ui_params["ground_seed"]` ("free" / "pec" /
  "sommerfeld" / "fast"), `ui_params["ground_medium"]` for the finite two,
  `ui_params["fixed_segment_counts"] = True`, and a class attribute
  `file_ground` the CLI applies when `--ground` is not given;
- the example descriptor carries all three to the frontend, which seeds the
  switch (its own tests: groundSeed.session.test.tsx).
"""

from __future__ import annotations

import importlib

import antennaknobs.web.server  # noqa: F401  (registers the catalog before the adapter is imported)
from antennaknobs.file_designs import builder_from_file, ground_seed
from antennaknobs.nec_import import parse_nec
from antennaknobs.web.adapter import _ui_medium, _ui_scalar

cli = importlib.import_module(
    "antennaknobs.cli"
)  # `antennaknobs.cli` the module, not the entry function

HEAD = "CM t\nCE\nGW 1 11 -5 0 0 5 0 0 0.001\n"
TAIL = "EX 0 1 6 0 1 0\nFR 0 1 0 0 14.1 0\nXQ 0\nEN\n"


def deck(*cards: str) -> str:
    return HEAD + "".join(c + "\n" for c in cards) + TAIL


# ---------------------------------------------------------------------------
# the importer records what the deck models
# ---------------------------------------------------------------------------


def test_g1432_1_ge0_is_free_space():
    d = parse_nec(deck("GE 0"), name="t.nec")
    assert d.ground is False
    assert d.ground_spec is None and d.ground_method is None


def test_g1432_2_ge1_without_gn_is_necs_perfect_ground():
    d = parse_nec(deck("GE 1"), name="t.nec")
    assert d.ground is True
    assert d.ground_spec == "pec" and d.ground_method is None


def test_g1432_3_gn1_is_pec_whatever_ge_says():
    d = parse_nec(deck("GE 1", "GN 1"), name="t.nec")
    assert d.ground_spec == "pec"


def test_g1432_4_gn2_carries_the_sommerfeld_medium():
    d = parse_nec(deck("GE 1", "GN 2 0 0 0 13 0.005"), name="t.nec")
    assert d.ground_spec == ("finite", 13.0, 0.005)
    assert d.ground_method == "sommerfeld"


def test_g1432_5_gn0_is_the_reflection_coefficient_model():
    d = parse_nec(deck("GE 1", "GN 0 0 0 0 20 0.02"), name="t.nec")
    assert d.ground_spec == ("finite-fast", 20.0, 0.02)  # the CLI's spelling
    assert d.ground_method == "fast"


def test_g1432_6_gn_minus_one_nullifies_back_to_free_space():
    d = parse_nec(deck("GE 1", "GN 2 0 0 0 13 0.005", "GN -1"), name="t.nec")
    assert d.ground is False and d.ground_spec is None and d.ground_method is None


# ---------------------------------------------------------------------------
# the file builder publishes the seed
# ---------------------------------------------------------------------------


def test_g1432_7_ground_seed_pairs():
    assert ground_seed(None) == ("free", None)
    assert ground_seed("pec") == ("pec", None)
    assert ground_seed(("finite", 13, 0.005), "sommerfeld") == (
        "sommerfeld",
        {"eps_r": 13.0, "sigma": 0.005},
    )
    assert ground_seed(("finite-fast", 13, 0.005))[0] == "fast"
    assert ground_seed(("finite", 13, 0.005))[0] == "sommerfeld"  # SSN default


def _builder(tmp_path, text):
    p = tmp_path / "Example2.nec"
    p.write_text(text)
    return builder_from_file(str(p))


def test_g1432_8_free_space_deck_seeds_ground_off_and_fixed_counts(tmp_path):
    B = _builder(tmp_path, deck("GE 0"))
    ui = B.default_params["ui_params"]
    assert ui["ground_seed"] == "free"
    assert "ground_medium" not in ui
    assert ui["fixed_segment_counts"] is True
    assert B.file_ground is None


def test_g1432_9_gn2_deck_seeds_finite_sommerfeld_with_its_medium(tmp_path):
    B = _builder(tmp_path, deck("GE 1", "GN 2 0 0 0 13 0.005"))
    ui = B.default_params["ui_params"]
    assert ui["ground_seed"] == "sommerfeld"
    assert ui["ground_medium"] == {"eps_r": 13.0, "sigma": 0.005}
    assert B.file_ground == ("finite", 13.0, 0.005)


def test_g1432_10_pec_deck_seeds_pec(tmp_path):
    B = _builder(tmp_path, deck("GE 1"))
    assert B.default_params["ui_params"]["ground_seed"] == "pec"
    assert B.file_ground == "pec"


# ---------------------------------------------------------------------------
# the descriptor carries it to the frontend
# ---------------------------------------------------------------------------


def test_g1432_11_the_example_descriptor_carries_seed_medium_and_flag(tmp_path):
    B = _builder(tmp_path, deck("GE 1", "GN 2 0 0 0 13 0.005"))
    dp = dict(B.default_params)
    assert _ui_scalar(dp, "ground_seed", None) == "sommerfeld"
    assert _ui_medium(dp) == {"eps_r": 13.0, "sigma": 0.005}
    assert _ui_scalar(dp, "fixed_segment_counts", False) is True
    # a catalog design carries none of it
    from antennaknobs.designs.dipoles.invvee import Builder as Invvee

    cdp = dict(Invvee.default_params)
    assert _ui_scalar(cdp, "ground_seed", None) is None
    assert _ui_medium(cdp) is None
    assert _ui_scalar(cdp, "fixed_segment_counts", False) is False


def test_g1432_12_malformed_medium_reads_as_none():
    assert _ui_medium({"ui_params": {"ground_medium": {"eps_r": "x"}}}) is None
    assert _ui_medium({"ui_params": {"ground_medium": 13}}) is None
    assert _ui_medium({}) is None


# ---------------------------------------------------------------------------
# the CLI's @file route applies the deck's ground when --ground is not given
# ---------------------------------------------------------------------------


def test_g1432_13_cli_engine_factory_defaults_to_the_files_ground(
    monkeypatch, tmp_path
):
    seen = []

    class Fake:
        def __init__(self, builder, **kw):
            seen.append(kw)

    monkeypatch.setitem(cli.ENGINE_CLASSES, "fake", Fake)
    gn2 = _builder(tmp_path, deck("GE 1", "GN 2 0 0 0 13 0.005"))
    (tmp_path / "free.nec").write_text(deck("GE 0"))
    free = builder_from_file(str(tmp_path / "free.nec"))
    from antennaknobs.designs.dipoles.invvee import Builder as Invvee

    f = cli.make_engine_factory("fake", cli._GROUND_UNSET)
    f(gn2())
    f(free())
    f(Invvee())
    assert seen == [{"ground": ("finite", 13.0, 0.005)}, {"ground": "free"}, {}]
    # an explicit --ground wins over the file
    seen.clear()
    cli.make_engine_factory("fake", "pec")(gn2())
    assert seen == [{"ground": "pec"}]

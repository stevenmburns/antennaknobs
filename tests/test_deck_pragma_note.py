"""The import note for a deck that asks for a momwire feature.

A deck's ``CM momwire: <name>`` card is read by momwire's drop-ins and
executables. antennaknobs does not act on it: the import says so, once per
feature, and names the checkbox that does the same thing. Every deck here is
invented.
"""

from __future__ import annotations

import pytest

from antennaknobs.deck_pragma_note import env_feature, pragma_notes
from antennaknobs.engines.momwire import _takes_pair_reuse, pair_reuse_certified
from antennaknobs.file_designs import builder_from_file
from antennaknobs.web import server  # noqa: F401  (registers the backends)
from antennaknobs.web import adapter

DIPOLE = """CM test dipole, invented
{cards}CE
GW 1 11 -5.0 0 10 5.0 0 10 0.001
GE 0
FR 0 1 0 0 14.2 0
EX 0 1 6 0 1 0
RP 0 1 1 1000 0 0 0 0
EN
"""

bs2 = adapter._BACKENDS_BY_NAME["bs2"]
offered = pytest.mark.skipif(
    not (_takes_pair_reuse(bs2.solver) and pair_reuse_certified(bs2.solver)),
    reason="this momwire does not offer pair_reuse on the bs2 tab here",
)
has_reader = pytest.mark.skipif(
    not pragma_notes("CM momwire: pair_reuse\n", also=[("x", "x")]),
    reason="this momwire has no deck_pragmas reader",
)


def _design(tmp_path, cards: str = "", name: str = "dip.nec"):
    path = tmp_path / name
    path.write_text(DIPOLE.format(cards=cards))
    return builder_from_file(str(path))


def _note(design) -> str:
    return design.default_params["ui_params"].get("notes", "")


@offered
@has_reader
def test_a_card_gives_one_note_with_the_served_label(tmp_path):
    label = adapter._OPTION_SPECS["pair_reuse"].label
    got = pragma_notes("CM momwire: pair_reuse\nCE\n")
    assert got == [
        "This file asks for pair reuse (momwire: pair_reuse). antennaknobs "
        f"does not act on it; tick '{label}' in the speed options "
        "to use it."
    ]
    note = _note(_design(tmp_path, "CM momwire: pair_reuse\n"))
    assert note.count(f"tick '{label}'") == 1


@offered
@has_reader
def test_duplicates_and_momwires_case_and_spacing_collapse_to_one(tmp_path):
    cards = "CM momwire: pair_reuse\ncm   MOMWIRE:\tPair_Reuse  trailing\nCM  momwire:pair_reuse\n"
    assert len(pragma_notes(cards)) == 1
    assert _note(_design(tmp_path, cards)).count("This file asks for") == 1


@has_reader
def test_a_name_that_is_not_offered_is_named_as_not_available(tmp_path):
    got = pragma_notes("CM momwire: no_such_feature\n")
    assert got == [
        "This file asks for no such feature (momwire: no_such_feature), "
        "which is not available here. antennaknobs does not act on it."
    ]
    assert "not available here" in _note(
        _design(tmp_path, "CM momwire: no_such_feature\n")
    )


def test_a_deck_without_cards_gives_no_note(tmp_path):
    assert pragma_notes("CM just a comment\nCE\n") == []
    assert "asks for" not in _note(_design(tmp_path))


@offered
@has_reader
def test_the_card_changes_no_option(tmp_path, monkeypatch):
    """The note is the whole effect: engine keywords, served defaults and the
    design's own parameters are what they are without the card."""
    plain = _design(tmp_path, "", "a.nec")
    asked = _design(tmp_path, "CM momwire: pair_reuse\n", "b.nec")
    assert "asks for" in _note(asked) and "asks for" not in _note(plain)

    def strip(design):
        params = dict(design.default_params)
        ui = {k: v for k, v in params["ui_params"].items() if k != "notes"}
        return {**params, "ui_params": ui}

    # The notes differ only by the sentence; nothing else in the design does.
    assert strip(plain) == strip(asked)

    specs_before = adapter.model_option_specs()
    kwargs = []
    for design in (plain, asked):
        eng = adapter._make_momwire_engine({"momwire_model": "bs2"}, design())
        kwargs.append((eng._pair_reuse, dict(eng._solver_kwargs)))
    assert kwargs[0] == kwargs[1]
    assert kwargs[0][0] is False
    assert adapter.model_option_specs() == specs_before
    assert specs_before["pair_reuse"]["default"] is False


def test_a_momwire_without_the_reader_gives_no_note_and_no_error(tmp_path, monkeypatch):
    import momwire._features as features

    monkeypatch.delattr(features, "deck_pragmas", raising=False)
    assert pragma_notes("CM momwire: pair_reuse\n") == []
    assert "asks for" not in _note(_design(tmp_path, "CM momwire: pair_reuse\n"))


# --- .ssn: NECOptions.OSEnv ---------------------------------------------------


def _ssn(tmp_path, lines: str, name: str = "dip.ssn"):
    from test_simnec_fed_wire_nec5_2091 import _dipole

    from antennaknobs.simnec_export import export_ssn

    text = export_ssn(_dipole(1), ground=None).replace(
        "NECUnits meters, meters;\n", f"NECUnits meters, meters;\n{lines}", 1
    )
    assert lines in text
    path = tmp_path / name
    path.write_text(text)
    return builder_from_file(str(path))


@pytest.mark.parametrize(
    ("name", "value", "feature"),
    [
        ("MOMWIRE_X_PAIR_REUSE", "1", "pair_reuse"),
        ("MOMWIRE_X_PAIR_REUSE", '"true"', "pair_reuse"),
        ("MOMWIRE_X_PAIR_REUSE", "0", None),
        ("MOMWIRE_X_PAIR_REUSE", "off", None),
        ("momwire_x_pair_reuse", "1", None),
        ("OTHER_VAR", "1", None),
        ("MOMWIRE_X_", "1", None),
    ],
)
def test_which_env_assignments_ask_for_a_feature(name, value, feature):
    assert env_feature(name, value) == feature


@offered
@has_reader
def test_an_ssn_osenv_line_gives_the_same_note(tmp_path):
    label = adapter._OPTION_SPECS["pair_reuse"].label
    note = _note(_ssn(tmp_path, 'NECOptions.OSEnv("MOMWIRE_X_PAIR_REUSE", 1);\n'))
    assert note.count("This file asks for pair reuse") == 1
    assert f"tick '{label}'" in note


@has_reader
def test_an_ssn_osenv_line_that_is_off_gives_no_note_and_still_opens(tmp_path):
    lines = 'NECOptions.OSEnv("MOMWIRE_X_PAIR_REUSE", 0);\n'
    assert "asks for" not in _note(_ssn(tmp_path, lines))


def test_an_ssn_osenv_line_for_another_variable_is_refused_as_before(tmp_path):
    """Only a momwire feature's variable is known not to change the model."""
    with pytest.raises(ValueError, match="could not be read"):
        _ssn(tmp_path, 'NECOptions.OSEnv("SOME_OTHER", 1);\n')


@offered
@has_reader
def test_the_same_feature_by_an_ssn_line_and_a_card_is_one_note():
    got = pragma_notes(
        "CM momwire: pair_reuse\n",
        also=[("pair_reuse", 'NECOptions.OSEnv("MOMWIRE_X_PAIR_REUSE", 1)')],
    )
    assert len(got) == 1


def test_a_carded_deck_imports_in_a_fresh_process(tmp_path):
    """The note's roster lookup from a process that has not loaded the web
    app (the CLI's `@file.nec`): the adapter must not be entered half-built."""
    import subprocess
    import sys

    deck = tmp_path / "carded.nec"
    deck.write_text(
        "CM invented long wire\nCM momwire: pair_reuse\nCE\n"
        "GW 1 41 0 0 10 20 0 10 0.001\nGE 0\nEX 0 1 21 0 1 0\n"
        "FR 0 1 0 0 14.2 0\nXQ\nEN\n"
    )
    code = (
        "from pathlib import Path; from antennaknobs.file_designs import "
        "builder_from_file; b = builder_from_file(Path(%r)); "
        "print(b.default_params['ui_params']['notes'])" % str(deck)
    )
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )
    assert "asks for pair reuse" in out.stdout

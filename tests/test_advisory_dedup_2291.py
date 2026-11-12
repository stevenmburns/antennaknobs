"""AK#2291: repeated advisories and a long directives-not-applied list.

The decision pinned here is WHERE the folding happens. The server serves
every advisory it raised, repeats included, and the design note as written;
the panel (`SolverAdvisories.tsx`, `DesignNote.tsx`) shows each distinct
advisory once with its count and folds the note's list. One place, because
every advisory list the app shows renders through that one component, and a
count can only be honest where every occurrence still arrives.

For the note, the server adds the structure the panel needs instead of
leaving it to parse prose: ``note_lists``, each list's lead and items, which
the note carries verbatim. Every name and value here is invented.
"""

from __future__ import annotations

from types import SimpleNamespace

from test_ssn_numericparam_knobs_1716 import _one_wire

import antennaknobs.web.server  # noqa: F401 — resolves the adapter import cycle
from antennaknobs.file_designs import builder_from_text
from antennaknobs.simnec_import import DIRECTIVES_NOT_APPLIED, parse_ssn
from antennaknobs.web.adapter import _advisories_for, _make_example, _note_lists

# Print lines SimNEC shows and the import leaves alone: each is a directive
# not applied.
PRINTS = "pl Top;\npl Top * 2;\npl Top + 1;"


def _with_prints():
    return _one_wire("dcl Top = 7;", "Top", {}, post=PRINTS)


def test_the_note_names_its_directives_list_verbatim():
    cls = builder_from_text("prints.ssn", _with_prints())
    ui = cls.default_params["ui_params"]
    ((entry,),) = [ui["note_lists"]]
    assert entry["lead"] == DIRECTIVES_NOT_APPLIED
    assert entry["items"] == list(parse_ssn(_with_prints()).ignored_directives)
    assert len(entry["items"]) == 3
    # The note is unchanged: the list is written in it, whole.
    assert f"{entry['lead']}: {'; '.join(entry['items'])}" in ui["notes"]


def test_the_examples_descriptor_serves_the_list():
    cls = builder_from_text("prints.ssn", _with_prints())
    ex = _make_example("user.prints", cls, defer_hints=True)
    assert [n["lead"] for n in ex.note_lists] == [DIRECTIVES_NOT_APPLIED]
    assert (
        ex.note_lists[0]["items"]
        == (cls.default_params["ui_params"]["note_lists"][0]["items"])
    )


def test_a_list_the_note_does_not_carry_is_not_served():
    # The panel folds only text it can find, so the server never names a
    # list the note does not write verbatim.
    cls = builder_from_text("prints.ssn", _with_prints())
    ui = dict(cls.default_params["ui_params"])
    ui["note_lists"] = [{"lead": DIRECTIVES_NOT_APPLIED, "items": ["pl Elsewhere"]}]
    assert _note_lists({"ui_params": ui}, ui["notes"]) == ()


def test_a_file_with_no_directives_left_names_no_list():
    cls = builder_from_text("plain.ssn", _one_wire("dcl Top = 7;", "Top", {}))
    assert "note_lists" not in cls.default_params["ui_params"]
    assert _make_example("user.plain", cls, defer_hints=True).note_lists == ()


def test_the_server_serves_every_repeat_of_an_advisory():
    # The count is the panel's to show; a server that collapsed repeats
    # would leave it nothing to count.
    repeat = {"category": "SomethingRepeated", "text": "an invented note"}
    eng = SimpleNamespace(advisories=[repeat, repeat, repeat])
    assert _advisories_for(eng, {}, False, 7.0) == [repeat, repeat, repeat]

"""AK#1935: where an analysis comes from, said wherever it is listed.

Steve (2026-10-06): "I don't like the magical cases". A design's list marks
each analysis as the design's own ("this design": its ``build_analyses()``,
one inherited from a parent Builder included) or generic ("every design":
the library's convergence and band SWR, offered on every design and nowhere
conditionally). The gates: `offered_with_origin` tags them, a design's own
analysis of a generic's name is the design's; ``analyze --list`` prints the
marker and heads the generic ones ``[General]`` even on a short list that
shows no other heading; ``/analyses`` serves ``origin`` ("study" on a
study). Nothing here solves.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from antennaknobs import analyses as an
from antennaknobs import analysis_run
from antennaknobs.cli import get_builder


def _origins(builder) -> dict[str, str]:
    return {a.name: o for a, o in an.offered_with_origin(builder)}


def test_the_generics_are_generic_and_a_designs_own_are_its_own():
    got = _origins(get_builder("dipoles.invvee")())
    # invvee writes its own convergence (three engines): that one is its.
    assert got["convergence"] == "design" and got["band SWR"] == "generic"
    assert {got[n] for n in ("height", "tuning map", "height patterns")} == {"design"}
    # offered is the same list, in the same order.
    b = get_builder("dipoles.invvee")()
    assert [a for a, _ in an.offered_with_origin(b)] == list(an.offered(b))


def test_an_inherited_build_analyses_is_the_designs_own():
    # invvee_apex inherits invvee's analyses from its parent Builder.
    got = _origins(get_builder("dipoles.invvee_apex")())
    assert got["height"] == "design" and got["band SWR"] == "generic"


def test_a_design_with_none_of_its_own_is_offered_only_the_generics():
    got = _origins(get_builder("dipoles.koch_dipole")())
    assert got == {"convergence": "generic", "band SWR": "generic"}


def test_heading_puts_the_generics_under_general_on_any_list():
    own, gen = an.Analysis("x", an.Sweep("base"), group="Tuning"), an.band_swr()
    assert an.heading(own, an.DESIGN_ORIGIN, headed=True) == "Tuning"
    assert an.heading(gen, an.GENERIC_ORIGIN, headed=True) == "General"
    assert an.heading(own, an.DESIGN_ORIGIN, headed=False) is None
    assert an.heading(gen, an.GENERIC_ORIGIN, headed=False) == "General"


@pytest.fixture
def short_own(monkeypatch):
    """koch_dipole with one analysis of its own: a short list."""
    from antennaknobs.designs.dipoles.koch_dipole import Builder

    mine = an.band_swr(name="my band")
    monkeypatch.setattr(Builder, "build_analyses", lambda self: [mine])
    return Builder()


def test_cli_list_marks_each_line_and_heads_the_generics(short_own):
    lines = analysis_run.list_lines(short_own)
    names = [ln.split("  ")[0].strip() for ln in lines if not ln.startswith(("[", " "))]
    assert names == ["my band", "convergence", "band SWR"]
    # The design's own first and unheaded, then [General] over the generics.
    assert lines[0].startswith("my band") and lines[1] == "[General]"
    row = {ln.split("  ")[0].strip(): ln for ln in lines if not ln.startswith("[")}
    assert row["my band"].split()[2:4] == ["this", "design"]
    assert "  every design  " in row["convergence"]
    assert "  every design  " in row["band SWR"]


def test_cli_list_marks_a_long_grouped_list_too():
    lines = analysis_run.list_lines(get_builder("dipoles.invvee")())
    heads = [ln for ln in lines if ln.startswith("[")]
    assert heads == ["[Tuning]", "[Height & ground]", "[Accuracy]", "[General]"]
    band = next(ln for ln in lines if ln.startswith("band SWR"))
    assert "  every design  " in band
    height = next(ln for ln in lines if ln.startswith("height "))
    assert "  this design  " in height


def test_the_analyses_endpoint_serves_the_origin():
    from antennaknobs.web import server

    r = TestClient(server.app).post("/analyses", json={"geometry": "dipoles.invvee"})
    assert r.status_code == 200, r.text
    got = r.json()["analyses"]
    own = {a["name"]: a["origin"] for a in got if not a["study"]}
    assert own["band SWR"] == "generic" and own["height"] == "design"
    assert own["convergence"] == "design"
    # A study is its own: E7 crosses the invvee.
    studies = [a for a in got if a["study"]]
    assert studies and {a["origin"] for a in studies} == {"study"}

"""Analysis groups (AK#1907): one level of headings over a design's list.

The gates: ``an.Analysis(group=...)`` round-trips through ``to_code`` and
``to_data``; ``offered`` holds each group together in the order the design
first names it, the order inside a group unchanged, and the generic
analyses last under ``General``; ``/analyses`` serves the heading; the CLI's
listing prints it only where the workbench shows it (more than three
analyses, more than one group); and every catalog design with a long list
groups it. Nothing here solves.
"""

from __future__ import annotations

import importlib
import pkgutil

import pytest

import antennaknobs.designs as designs_pkg
from antennaknobs import analyses as an
from antennaknobs import analysis_run

INVVEE_GROUPS = [
    (
        "Tuning",
        ["tuning family", "tuning map", "resonance vs angle", "match vs height"],
    ),
    ("Height & ground", ["height", "height states", "height patterns"]),
    ("Accuracy", ["convergence"]),
    ("General", ["band SWR"]),
]


def _invvee():
    from antennaknobs.designs.dipoles.invvee import Builder

    return Builder()


def _ev(code: str):
    return eval(code, {"an": an})


# ── the value ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "a",
    [
        an.Analysis("h", an.Sweep("base"), group="Height & ground"),
        an.convergence(group="Accuracy"),
        an.band_swr(group="Tuning"),
        an.patterns(group="Patterns"),
        an.knob("base", group="Height"),
    ],
    ids=["Analysis", "convergence", "band_swr", "patterns", "knob"],
)
def test_group_round_trips_through_code_and_data(a):
    code = an.to_code(a)
    assert f"group={a.group!r}".replace("'", '"') in code
    assert _ev(code) == a
    assert an.from_data(an.to_data(a)) == a


def test_no_group_prints_nothing_and_reads_back_as_none():
    a = an.convergence()
    assert "group" not in an.to_code(a)
    assert an.to_data(a)["group"] is None
    # A spec written before groups existed (no "group" key) still reads.
    data = an.to_data(a)
    del data["group"]
    assert an.from_data(data) == a


@pytest.mark.parametrize("bad", ["", "  ", 3])
def test_group_is_a_non_empty_string(bad):
    with pytest.raises(TypeError, match="group is a non-empty string"):
        an.Analysis("h", an.Sweep("base"), group=bad)


# ── the order ────────────────────────────────────────────────────────────────


def _a(name, group=None):
    return an.Analysis(name, an.Sweep("base"), group=group)


def test_grouped_keeps_first_mention_order_and_list_order_within():
    listed = [_a("a", "X"), _a("b"), _a("c", "Y"), _a("d", "X"), _a("e", "Y")]
    got = [(g, [a.name for a in ms]) for g, ms in an.grouped(listed)]
    assert got == [("X", ["a", "d"]), ("Y", ["c", "e"]), ("General", ["b"])]


def test_an_explicit_general_places_the_generic_group():
    listed = [_a("a", "X"), _a("b", "General"), _a("c", "Y"), _a("d")]
    got = [(g, [a.name for a in ms]) for g, ms in an.grouped(listed)]
    assert got == [("X", ["a"]), ("General", ["b", "d"]), ("Y", ["c"])]


def test_invvee_lists_its_groups_most_important_first():
    offered = an.offered(_invvee())
    got = [(g, [a.name for a in ms]) for g, ms in an.grouped(offered)]
    assert got == INVVEE_GROUPS
    # `offered` is already in that order: each group together.
    assert [a.name for a in offered] == [n for _, ns in INVVEE_GROUPS for n in ns]
    assert an.shows_groups(offered)


def test_offered_keeps_the_design_order_within_each_group():
    builder = _invvee()
    own = [a.name for a in builder.build_analyses()]
    for _, members in an.grouped(an.offered(builder)):
        names = [a.name for a in members if a.name in own]
        assert names == sorted(names, key=own.index)


def test_three_or_fewer_show_no_headings():
    assert not an.shows_groups([_a("a", "X"), _a("b", "Y"), _a("c")])
    # Long, but one group: a heading would say nothing.
    assert not an.shows_groups([_a(n) for n in "abcde"])
    assert an.shows_groups([_a("a", "X"), _a("b"), _a("c"), _a("d")])


def _catalog():
    for m in pkgutil.walk_packages(designs_pkg.__path__, designs_pkg.__name__ + "."):
        try:
            cls = importlib.import_module(m.name).Builder
        except (ImportError, AttributeError):
            continue
        yield m.name.removeprefix(designs_pkg.__name__ + "."), cls


def test_every_long_catalog_list_is_grouped():
    """A design offering more than three analyses names its groups: the
    census AK#1907 asked for, kept as a rule for the next design."""
    long = {}
    for name, cls in _catalog():
        try:
            offered = an.offered(cls())
        except Exception:  # noqa: BLE001 — a design that will not build is gated elsewhere
            continue
        if len(offered) >= an.GROUPS_FROM:
            long[name] = an.shows_groups(offered)
    assert "dipoles.invvee" in long
    assert all(long.values()), {k: v for k, v in long.items() if not v}


# ── where it is shown ────────────────────────────────────────────────────────


def test_cli_list_prints_the_headings():
    lines = analysis_run.list_lines(_invvee())
    heads = [ln for ln in lines if ln.startswith("[")]
    assert heads == [f"[{g}]" for g, _ in INVVEE_GROUPS]
    # Each heading is followed by its group's first analysis.
    for g, names in INVVEE_GROUPS:
        i = lines.index(f"[{g}]")
        assert lines[i + 1].split("  ")[0].strip() == names[0]


def test_cli_list_heads_only_the_generic_ones_on_a_short_list():
    # A short list shows no group headings; the generic analyses are still
    # under [General] (AK#1935), so it says which every design has.
    from antennaknobs.designs.dipoles.koch_dipole import Builder

    offered = an.offered(Builder())
    assert len(offered) <= 3
    heads = [ln for ln in analysis_run.list_lines(Builder()) if ln.startswith("[")]
    assert heads == ["[General]"]


def test_analyses_endpoint_serves_the_group():
    from fastapi.testclient import TestClient

    from antennaknobs.web import server

    r = TestClient(server.app).post(
        "/analyses",
        json={
            "geometry": "dipoles.invvee",
            "measurement_freq_mhz": 28.47,
            "design_freq_mhz": 28.47,
            "momwire_model": "bspline",
            "n_per_wire": 9,
        },
    )
    assert r.status_code == 200, r.text
    own = [(a["name"], a["group"]) for a in r.json()["analyses"] if not a["study"]]
    assert own == [(n, g) for g, ns in INVVEE_GROUPS for n in ns]

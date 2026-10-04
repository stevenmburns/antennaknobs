"""antennaknobs#1560: one momwire basis roster, read by the app and the CLI.

The CLI's `--engine` names were a hand-kept dict that drifted from the app's
roster and the density table (the app served Pulse, density.py gave `pulse` a
row, the CLI refused the name; the plain `--engine` help still omitted it).
These gates make the next drift red rather than a field report.
"""

from __future__ import annotations

import pytest

import antennaknobs as ant
from antennaknobs import momwire_bases
from antennaknobs.cli import parse_engine_spec
from antennaknobs.density import default_nsegs
import antennaknobs.web.server  # noqa: F401 — resolves the adapter import cycle
from antennaknobs.web import adapter


def _served_momwire():
    return [
        b["name"]
        for b in adapter.backend_roster(have_pynec=False)
        if b["kind"] == "momwire"
    ]


def test_the_app_serves_exactly_the_roster_in_its_order():
    assert _served_momwire() == list(momwire_bases.BASES)


def test_the_app_constructs_each_tab_from_the_roster():
    for spec in adapter._BACKENDS:
        if spec.kind != "momwire":
            continue
        basis = momwire_bases.BASES[spec.name]
        assert spec.solver is basis.solver, spec.name
        assert dict(spec.bound) == dict(basis.bound), spec.name


@pytest.mark.parametrize("name", momwire_bases.cli_names())
def test_the_cli_accepts_every_roster_name_and_alias(name):
    engine, kw = parse_engine_spec(f"momwire:{name}")
    roster, cls, kwargs = momwire_bases.resolve(name)
    assert engine == "momwire" and kw["solver"] is cls
    assert kw.get("solver_kwargs", {}) == kwargs


def test_every_served_tab_is_a_cli_name_and_every_cli_name_a_tab_or_alias():
    served = set(_served_momwire())
    cli = set(momwire_bases.cli_names())
    assert served <= cli
    assert cli - served == set(momwire_bases.ALIASES)
    for alias, (roster, _extra) in momwire_bases.ALIASES.items():
        assert roster in momwire_bases.BASES, alias


def test_every_roster_name_has_a_density_row():
    for name in momwire_bases.BASES:
        assert default_nsegs(name) is not None, name


@pytest.mark.parametrize(
    "command", ["pattern", "sweep", "compare_patterns", "optimize"]
)
def test_every_engine_help_lists_every_name(command, capsys, monkeypatch):
    # Wide enough that argparse wraps only at spaces, never inside the list.
    monkeypatch.setenv("COLUMNS", "1000")
    with pytest.raises(SystemExit):
        ant.cli([command, "--help"])
    # argparse wraps help text; rejoin it before looking for the list.
    text = " ".join(capsys.readouterr().out.split())
    expected = f"momwire[:{'|'.join(momwire_bases.cli_names())}]"
    assert expected in text, command

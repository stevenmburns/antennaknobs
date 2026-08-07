"""``@file`` builder specs: NEC card decks as CLI designs.

``get_builder("@path/to/file.nec")`` synthesizes a frozen-geometry builder on
the fly (``file_designs.builder_from_file``) — pure data, no trust gate — so
every subcommand that takes a builder spec can consume a deck directly, and
decks mix freely with named designs in ``--builders`` lists.
"""

import pytest

import antennaknobs as ant
from antennaknobs.cli import emit_params_name, get_builder
from antennaknobs.network import Load, Wire

DECK = """\
CM a 20 m dipole at 10 m
CE
GW 1 11 0 -5 10 0 5 10 0.001
GE
FR 0 3 0 0 14.0 0.1
EX 0 1 6 0 1 0
LD 0 1 3 3 10 0 0
EN
"""


@pytest.fixture
def deck_path(tmp_path):
    p = tmp_path / "flat_dipole.nec"
    p.write_text(DECK)
    return p


def test_at_nec_builds_and_seeds_from_the_deck(deck_path):
    cls = get_builder(f"@{deck_path}")
    b = cls()
    # FR 3 points from 14.0 step 0.1 -> band (14.0, 14.2), freq at its middle
    assert b.freq == pytest.approx(14.1)
    assert b.ui_params["meas_freq_range"] == (pytest.approx(14.0), pytest.approx(14.2))
    wires = b.build_wires()
    assert wires and all(isinstance(w, Wire) for w in wires)
    assert all(w.spec is not None for w in wires)  # per-wire radius from GW
    net = b.build_network()
    assert net.sources and any(isinstance(br, Load) for br in net.branches)


def test_at_nec_display_identity_is_the_file_stem(deck_path):
    cls = get_builder(f"@{deck_path}")
    assert cls.label == "flat_dipole"
    assert cls.__qualname__ == "flat_dipole"


def test_at_spec_never_splits_a_variant_colon(tmp_path):
    # Colons are legal in POSIX filenames (and in Windows drive letters);
    # an @ spec must consume the whole token as a path.
    p = tmp_path / "de:ck.nec"
    p.write_text(DECK)
    b = get_builder(f"@{p}")()
    assert b.freq == pytest.approx(14.1)
    assert emit_params_name(f"@{p}") == "default_params"


def test_at_nec_without_fr_defaults_and_notes(tmp_path):
    p = tmp_path / "nofr.nec"
    p.write_text("GW 1 11 0 -5 10 0 5 10 0.001\nGE\nEX 0 1 6 0 1 0\nEN\n")
    b = get_builder(f"@{p}")()
    assert b.freq == pytest.approx(14.0)
    assert "names no frequency" in b.ui_params["notes"]


# --- error paths -------------------------------------------------------------


def test_at_unknown_extension_is_a_clear_error(tmp_path):
    p = tmp_path / "foo.yaml"
    p.write_text("wires: []")
    with pytest.raises(SystemExit, match=r"foo\.yaml.*extension"):
        get_builder(f"@{p}")


def test_at_missing_file_is_a_clear_error(tmp_path):
    with pytest.raises(SystemExit, match="no such file"):
        get_builder(f"@{tmp_path}/nope.nec")


def test_at_parse_error_carries_file_and_line(tmp_path):
    p = tmp_path / "bad.nec"
    p.write_text("GW 1 11 0 -5 10 0 5 10 0.001\nQZ 1 2 3\nEN\n")
    with pytest.raises(ValueError, match=r"bad\.nec, line 2"):
        get_builder(f"@{p}")


# --- through the real CLI ----------------------------------------------------


def test_cli_draw_at_nec(deck_path):
    ant.cli(f"draw --builder @{deck_path} --fn /dev/null".split())


def test_cli_params_at_nec(deck_path, capsys):
    ant.cli(f"params --builder @{deck_path}".split())
    out = capsys.readouterr().out
    assert "default_params" in out and "14.1" in out


def test_simnec_export_cli_converts_at_nec(deck_path, capsys):
    """python -m antennaknobs.simnec_export @deck.nec — .nec -> .ssn."""
    import xml.etree.ElementTree as ET

    from antennaknobs.simnec_export import main

    main([f"@{deck_path}"])
    out = capsys.readouterr().out
    root = ET.fromstring(out)
    assert root.find(".//XMLVersionControl") is not None
    assert "//flat_dipole" in out  # block name from the file stem

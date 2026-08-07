"""``@file`` builder specs: NEC decks and SimNEC circuits as CLI designs.

``get_builder("@path/to/file.nec|.ssn")`` synthesizes a frozen-geometry
builder on the fly (``file_designs.builder_from_file``) — pure data, no trust
gate — so every subcommand that takes a builder spec can consume a file
directly, and files mix freely with named designs in ``--builders`` lists.
"""

from types import MappingProxyType

import pytest

import antennaknobs as ant
from antennaknobs.builder import AntennaBuilder
from antennaknobs.cli import emit_params_name, get_builder
from antennaknobs.network import TL, Load, Wire
from antennaknobs.simnec_export import export_ssn


class _Dipole(AntennaBuilder):
    default_params = MappingProxyType({"freq": 14.0, "design_freq": 14.0})

    def build_wires(self):
        return [Wire((0.0, -5.0, 10.0), (0.0, 5.0, 10.0), n_seg=11, ex=1 + 0j)]


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


# --- .ssn specs --------------------------------------------------------------


def test_at_ssn_seeds_from_the_generator(tmp_path):
    p = tmp_path / "dip.ssn"
    p.write_text(export_ssn(_Dipole(), freq_mhz=14.1, ground=None, sweep=(13.0, 15.0)))
    b = get_builder(f"@{p}")()
    assert b.freq == pytest.approx(14.1)  # Generator MHz, not the FR card
    # an armed Generator sweep wins over the FR range
    assert b.ui_params["meas_freq_range"] == (pytest.approx(13.0), pytest.approx(15.0))
    assert b.build_wires()
    assert b.build_network().sources


def test_at_ssn_ground_note_points_at_the_flag(tmp_path):
    p = tmp_path / "dip.ssn"
    p.write_text(export_ssn(_Dipole(), freq_mhz=14.1, ground=("finite", 13.0, 0.005)))
    b = get_builder(f"@{p}")()
    assert "--ground finite:13,0.005" in b.ui_params["notes"]


def test_at_ssn_conductivity_reaches_the_wire_specs(tmp_path):
    ssn = export_ssn(_Dipole(), freq_mhz=14.1, ground=None)
    ssn = ssn.replace(
        "NECOptions.mhosPerMeter = 0;", "NECOptions.mhosPerMeter = 5.8e7;"
    )
    p = tmp_path / "dip.ssn"
    p.write_text(ssn)
    wires = get_builder(f"@{p}")().build_wires()
    assert all(w.spec.conductivity == pytest.approx(5.8e7) for w in wires)


def test_at_ssn_station_chain_acts(tmp_path):
    """A station .ssn's chain lands in build_network(): the Driven moves to
    the rig node and the cascade hangs rig -> ... -> feed."""
    from test_simnec_import import _SCRIPT_M, _el, _ssn

    extra = _el("SERIES_TLINE", {"Zo": 450, "VFnom": 0.91, "ft": 50})
    p = tmp_path / "station.ssn"
    p.write_text(_ssn(_SCRIPT_M, extra_elements=extra))
    net = get_builder(f"@{p}")().build_network()
    (src,) = net.sources
    assert src.port == "rig"
    (tl,) = [br for br in net.branches if isinstance(br, TL)]
    assert tl.z0 == pytest.approx(450.0) and tl.length == pytest.approx(50 * 0.3048)


def test_cli_export_converts_at_ssn(tmp_path, capsys):
    """antennaknobs export --builder @dip.ssn — .ssn -> .nec card deck."""
    p = tmp_path / "dip.ssn"
    p.write_text(export_ssn(_Dipole(), freq_mhz=14.1, ground=None))
    ant.cli(f"export --builder @{p} --ground free".split())
    out = capsys.readouterr().out
    assert "GW " in out and "EX " in out


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

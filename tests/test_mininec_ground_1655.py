"""EZNEC's "Real, MININEC type" ground (AK#1655).

The currents and impedance are a perfect ground's; the far field reflects off
the real medium. AC6LA's 4square, exported from EZNEC as NEC-5, carries it as
a bare ``GD`` after ``GE 1``, and the app used to read that as a perfect
ground: 10.83 dBi on the horizon where licensed NEC-5 prints 5.40 dBi at 25
degrees. The impedance MATCHED throughout, because under this ground it is the
perfect ground's by definition, so a matching Z says nothing here. The pattern
is the gate.

Reference numbers are licensed NEC-5 on `VERT_GD` below (a 6-segment vertical
bonded to the plane, fed at its centre knot, 7.15 MHz, 13 / 0.005), verified
against our licensed materials 2026-09-22:

    GD    Z 64.221 - j17.321   peak -0.05 dBi at elevation 26,
                               -6.37 at 5, -18.22 at 1, a null at 0
    GN 1  Z 64.221 - j17.321   peak  5.15 dBi at elevation 0

The engines here meet NEC-5's PATTERN to 0.06 dB. They do not meet its Z on
this mesh (66.2 - j4.4 on momwire's default basis and on NEC-2), which is the
same under GN 1 and is not this ground's business.
"""

from __future__ import annotations

import sys

import numpy as np
import pytest
from conftest import needs_pynec

from antennaknobs.cli import format_ground, parse_ground
from antennaknobs.file_designs import builder_from_file, ground_seed
from antennaknobs.nec_export import _ground_cards, export_nec, rp_mode
from antennaknobs.nec_import import parse_nec

MININEC = ("mininec", 13.0, 0.005)

VERT_GD = """CM ! Written by EZNEC/Pro+ v. 7.0 in NEC-5 format.
CE
GW 1,6,0.,0.,0.,0.,0.,9.9822,.01905
GE 1
FR 0,1,0,0,7.15
GD 0,0,0,0,13.,.005,1.,0.
EX 0,1,3,2,1.,0.
EN
"""

# NEC-5's elevation cut over VERT_GD: peak, its elevation, and two low angles.
NEC5_PEAK_DBI, NEC5_PEAK_EL = -0.05, 26.0
NEC5_AT = {5.0: -6.37, 1.0: -18.22}


def _nec2(ground_cards: str) -> str:
    return (
        "GW 1 6 0 0 0 0 0 9.9822 .01905\nGE 1\n"
        + ground_cards
        + "EX 0 1 3 0 1 0\nFR 0 1 0 0 7.15 0\nEN\n"
    )


def _vertical(tmp_path):
    path = tmp_path / "vert_gd.nec"
    path.write_text(VERT_GD)
    return builder_from_file(str(path))


# --- the grammar ---------------------------------------------------------


def test_the_cli_spells_it_mininec():
    assert parse_ground("mininec") == MININEC
    assert parse_ground("mininec:20,0.01") == ("mininec", 20.0, 0.01)
    assert "perfect-ground currents" in format_ground(MININEC)


# --- the importer --------------------------------------------------------


def test_a_nec5_bare_gd_is_the_mininec_ground():
    deck = parse_nec(VERT_GD, network=True)
    assert deck.nec5_dialect
    assert deck.ground_spec == MININEC
    assert (deck.ground_method, deck.ground_card) == ("mininec", "GD")
    # Applied, so not in the note that lists what was not (the note used to
    # call it NEC-2's "additional ground medium", #1656).
    assert "GD" not in deck.ignored
    assert "GD" not in (deck.skipped_note() or "")


def test_a_nec5_gd_minus_one_cancels_to_free_space():
    deck = parse_nec(VERT_GD.replace("GD 0,0,0,0", "GD -1,0,0,0"), network=True)
    assert deck.ground_spec is None


def test_in_nec5_the_last_ground_card_wins():
    text = VERT_GD.replace(
        "GD 0,0,0,0,13.,.005,1.,0.", "GD 0,0,0,0,13.,.005,1.,0.\nGN 1"
    )
    assert parse_nec(text, network=True).ground_spec == "pec"


def test_nec2s_gn1_plus_a_gd_cliff_at_zero_is_the_mininec_ground():
    """4nec2's GN 3, as 4nec2 hands it to its engine."""
    deck = parse_nec(_nec2("GN 1\nGD 0 0 0 0 13 .005\n"))
    assert not deck.nec5_dialect
    assert deck.ground_spec == MININEC
    assert deck.ground_card == "GN 1 + GD"


def test_4nec2s_gn3_is_the_mininec_ground():
    deck = parse_nec(_nec2("GN 3 0 0 0 13 0.005 0.0 0.0\n"))
    assert deck.ground_spec == MININEC
    assert deck.ground_card == "GN 3"


@pytest.mark.parametrize(
    "cards, spec",
    [
        # A real cliff: a medium the app does not model, so still not applied.
        ("GN 1\nGD 0 0 0 0 13 .005 10 2\n", "pec"),
        # A GN resets the second medium, so a GD before it is gone.
        ("GD 0 0 0 0 13 .005\nGN 1\n", "pec"),
        # Over a finite ground, the cliff is a second soil and not this idiom.
        ("GN 2 0 0 0 13 .005\nGD 0 0 0 0 5 .001\n", ("finite", 13.0, 0.005)),
        # All zeros is no medium (momwire#490's vacuum cliff).
        ("GN 1\nGD 0 0 0 0 0 0\n", "pec"),
    ],
)
def test_other_nec2_gd_cards_leave_the_ground_alone(cards, spec):
    deck = parse_nec(_nec2(cards))
    assert deck.ground_spec == spec
    if "GD" in deck.ignored:
        assert "GD (additional ground medium)" in deck.skipped_note()


def test_the_file_design_seeds_the_mininec_method(tmp_path):
    cls = _vertical(tmp_path)
    assert cls.file_ground == MININEC
    ui = cls.default_params["ui_params"]
    assert ui["ground_seed"] == "mininec"
    assert ui["ground_medium"] == {"eps_r": 13.0, "sigma": 0.005}
    assert ui["ground_card"] == "NEC-5 GD"
    assert ground_seed(MININEC) == ("mininec", {"eps_r": 13.0, "sigma": 0.005})


# --- the writers ---------------------------------------------------------


def test_nec2_writes_gn1_plus_the_cliff_and_asks_for_it_in_cliff_mode(tmp_path):
    assert _ground_cards(MININEC) == ["GN 1 0 0 0 0 0", "GD 0 0 0 0 13 0.005 0 0"]
    assert rp_mode(MININEC) == 3
    assert rp_mode(("finite", 13.0, 0.005)) == rp_mode("pec") == 0

    b = _vertical(tmp_path)()
    lines = export_nec(b, ground=MININEC, include_rp=True).splitlines()
    assert lines.index("GD 0 0 0 0 13 0.005 0 0") == lines.index("GN 1 0 0 0 0 0") + 1
    assert [ln for ln in lines if ln.startswith("RP")] == ["RP 3 19 37 1000 0 0 10 10"]

    from antennaknobs.engines.nec2 import NEC2Engine

    # Construction never runs the binary; any executable stands in for it.
    eng = NEC2Engine(_vertical(tmp_path)(), ground=MININEC, nec2_exe=sys.executable)
    rp = [
        ln for ln in eng.deck(7.15, rp=(90, 360, 1, 1)).splitlines() if ln[:2] == "RP"
    ]
    assert rp == ["RP 3 90 360 1000 0 0 1 1"]


def test_nec5_writes_ge1_and_a_bare_gd(tmp_path):
    from antennaknobs.engines.nec5 import NEC5Engine

    b = _vertical(tmp_path)()
    lines = NEC5Engine(b, ground=MININEC, require_exe=False).deck([7.15]).splitlines()
    assert "GE 1 0" in lines
    assert not [ln for ln in lines if ln.startswith("GN")]
    [gd] = [ln.split() for ln in lines if ln.startswith("GD")]
    assert [float(x) for x in gd[5:9]] == [13.0, 0.005, 1.0, 0.0]


# --- the physics ---------------------------------------------------------


def _engine(name, builder, ground):
    if name == "momwire":
        from antennaknobs.engines.momwire import MomwireEngine

        return MomwireEngine(builder, ground=ground)
    from antennaknobs.engines.pynec import PyNECEngine

    return PyNECEngine(builder, ground=ground)


def _elevation_cut(eng):
    ff = eng.far_field(n_theta=90, n_phi=360, del_theta=1, del_phi=1)
    gain = np.array([ring[0] for ring in ff.rings])
    return dict(zip(np.round(90.0 - np.asarray(ff.thetas)), gain, strict=True))


@pytest.mark.parametrize("name", ["momwire", pytest.param("pynec", marks=needs_pynec)])
def test_the_impedance_is_the_perfect_grounds_to_every_digit(tmp_path, name):
    cls = _vertical(tmp_path)
    z_mininec = np.atleast_1d(_engine(name, cls(), MININEC).impedance())
    z_pec = np.atleast_1d(_engine(name, cls(), "pec").impedance())
    np.testing.assert_array_equal(z_mininec, z_pec)


@pytest.mark.parametrize("name", ["momwire", pytest.param("pynec", marks=needs_pynec)])
def test_the_pattern_is_nec5s_over_the_real_ground(tmp_path, name):
    cut = _elevation_cut(_engine(name, _vertical(tmp_path)(), MININEC))
    peak_el = max(cut, key=cut.get)
    assert cut[peak_el] == pytest.approx(NEC5_PEAK_DBI, abs=0.1)
    assert abs(peak_el - NEC5_PEAK_EL) <= 1.0
    for el, gain in NEC5_AT.items():
        assert cut[el] == pytest.approx(gain, abs=0.1), el
    # The control: over the perfect ground the peak is on the horizon, which
    # is what the app showed for this deck before (5.15 dBi at 0 in NEC-5).
    pec = _elevation_cut(_engine(name, _vertical(tmp_path)(), "pec"))
    assert max(pec, key=pec.get) <= 1.0
    assert pec[1.0] - cut[1.0] > 20.0


# --- the web lanes -------------------------------------------------------


def _web_req(**over):
    import importlib

    f = (
        importlib.import_module("antennaknobs.designs.verticals.four_square")
        .Builder()
        .freq
    )
    return {
        "geometry": "verticals.four_square",
        "measurement_freq_mhz": f,
        "design_freq_mhz": f,
        "ground": True,
        "ground_model": "mininec",
        **over,
    }


def test_every_web_lane_maps_the_request_to_the_mininec_ground():
    import antennaknobs.web.examples  # noqa: F401  (before the adapter)
    from antennaknobs.web.adapter import (
        _ground_for_engine,
        _nec5_ground_applied,
        _nec5_ground_spec,
        _pynec_ground_applied,
        _pynec_ground_spec,
    )

    req = _web_req(soil={"eps_r": 20.0, "sigma": 0.01})
    for spec in (_ground_for_engine, _pynec_ground_spec, _nec5_ground_spec):
        assert spec(req) == ("mininec", 20.0, 0.01), spec.__name__
    assert _pynec_ground_applied(MININEC) == _nec5_ground_applied(MININEC) == "mininec"


def test_the_momwire_web_solve_ships_the_soil_and_the_pec_impedance():
    import antennaknobs.web.examples as examples

    ex = examples.example_for("verticals.four_square")
    out = ex.momwire_solve(_web_req())
    pec = ex.momwire_solve(_web_req(ground_model="pec"))
    assert out["ground_model_applied"] == "mininec"
    # The server's cut reflects off these, so they must be the soil.
    assert (out["ground_eps_r"], out["ground_sigma"]) == (13.0, 0.005)
    assert (out["z_in_re"], out["z_in_im"]) == (pec["z_in_re"], pec["z_in_im"])


@needs_pynec
def test_the_nec_rp_trace_agrees_with_the_apps_cut():
    """PyNEC's own pattern (rp_card in cliff mode) against the app's cut from
    the same solve's currents and the shipped soil."""
    import copy

    import antennaknobs.web.examples as examples
    from antennaknobs.web import pynec_backend, server

    req = _web_req()
    ex = examples.example_for("verticals.four_square")
    assert ex.pynec_build(req)["rp_mode"] == 3
    pat = pynec_backend.pattern(req)
    out = ex.pynec_solve(req)
    assert out["ground_model_applied"] == "mininec"
    o = copy.deepcopy(out)
    server._attach_derived_em_fields(o)
    server._attach_gain_norm(o)
    # The elevation cut through azimuth 0, on the NEC trace's own 2-degree
    # elevations (its column 0 is phi = 0), from 4 degrees up to 88.
    elevations = np.arange(4.0, 90.0, 2.0)
    cut = np.asarray(
        server._pattern_cuts(o, 0.5, 0.0, elev_angles_deg=list(elevations))["elevation"]
    )
    gains = np.asarray(pat["gain_dbi"])
    thetas = list(np.round(pat["theta_deg"], 6))
    trace = np.array([gains[thetas.index(round(90.0 - el, 6)), 0] for el in elevations])
    np.testing.assert_allclose(cut, trace, atol=0.1)
    # Off the horizon: the soil is what the NEC trace reflected off, too.
    assert 10.0 < elevations[int(np.argmax(trace))] < 45.0

"""antennaknobs#1354: the NEC-2 web lane, riding the shared solve body.

The lane itself is four lines — a `_SolveSeams` and a factory — because #1393
made the body shared. What needed real work is the ONE field a subprocess NEC-2
does not hand over for free: the power budget, and with it the efficiency and
input power the UI shows.

The rule these tests exist to hold: **the budget is never faked.**
`radiation_efficiency` and `input_power_w` are read through
`getattr(eng, "_excited_efficiency", 1.0)` and `... or 0.0`, so a lane that
parsed nothing would report a lossless antenna drawing no power — a confident
wrong answer indistinguishable from a real one, which is the same failure mode
`NEC2Engine` refuses a buried wire to avoid. So a printout with no budget
raises, and a printout carrying the binary's own complaint reports THAT.
"""

from __future__ import annotations

import importlib

import pytest

import antennaknobs.web.server  # noqa: F401 — must load before adapter (import cycle)
from antennaknobs.engines.nec2 import NEC2Engine, NEC2Error
from antennaknobs.web.adapter import _NEC2_SEAMS, backend_roster

# NEC-2's block, with ITS spellings: STRUCTURE LOSS not WIRE LOSS, a NETWORK
# LOSS line NEC-5 has no counterpart for, and no space before `RADIATED POWER=`.
BUDGET = """\
                               ---------- POWER BUDGET ---------
                               INPUT POWER   =  1.0000E-02 Watts
                               RADIATED POWER=  8.7500E-03 Watts
                               STRUCTURE LOSS=  1.0000E-03 Watts
                               NETWORK LOSS  =  2.5000E-04 Watts
                               EFFICIENCY    =  87.50 Percent
"""


def test_the_budget_is_parsed_at_nec2s_own_labels():
    b = NEC2Engine._parse_power_budget(BUDGET)
    assert b == {
        "input_w": 1.0e-02,
        "radiated_w": 8.75e-03,
        "wire_loss_w": 1.0e-03,
        "network_loss_w": 2.5e-04,
        "efficiency_pct": 87.5,
    }


def test_an_efficiency_that_is_not_one_comes_through_as_itself():
    """The test that separates "parsed" from "defaulted": 87.5 %, not 100 %."""
    assert NEC2Engine._parse_power_budget(BUDGET)["efficiency_pct"] == 87.5


@pytest.mark.parametrize(
    ("text", "what"),
    [
        ("nothing here\n", "no block at all"),
        (BUDGET.replace("EFFICIENCY    =  87.50 Percent", ""), "a missing line"),
        (BUDGET.replace("STRUCTURE LOSS=  1.0000E-03 Watts", ""), "a missing loss"),
    ],
)
def test_a_budget_that_cannot_be_read_raises_rather_than_partially_answering(
    text, what
):
    """A partial budget is how a plausible efficiency gets shipped as measured."""
    with pytest.raises(NEC2Error):
        NEC2Engine._parse_power_budget(text)


def test_the_feed_voltages_come_from_the_printouts_own_columns():
    text = """
                        --------- ANTENNA INPUT PARAMETERS ---------
    1     2  1.0000E+00  0.0000E+00  1.8460E-02  1.0173E-02  4.1552E+01 -2.2898E+01  1.8460E-02  1.0173E-02  9.2301E-03
    2     5  5.0000E-01 -2.5000E-01  1.0000E-02  2.0000E-03  4.0000E+01 -1.0000E+01  1.0000E-02  2.0000E-03  2.0000E-03
"""
    assert NEC2Engine._parse_feed_voltages(text) == [
        complex(1.0, 0.0),
        complex(0.5, -0.25),
    ]


def test_the_seam_reads_the_stamped_feed_values():
    """`_NEC2_SEAMS.feed_values` reads what `solve_snapshot` stamped. Unlike
    PyNEC and NEC-5 this engine has no resolved-feed list of its own —
    `export_nec` builds and discards the PyNECEngine that resolves them — so
    the printout's VOLTAGE columns are the source, and they are what the binary
    was actually driven with."""
    eng = type("E", (), {"_excited_feed_values": [1 + 0j, 0.5 - 0.25j]})()
    assert _NEC2_SEAMS.feed_values(eng) == [1 + 0j, 0.5 - 0.25j]
    # Absent rather than zero-length is also an empty list, not a crash: the
    # body pads to len(zs) afterwards.
    assert _NEC2_SEAMS.feed_values(type("E", (), {})()) == []


def test_the_seam_runs_one_subprocess_not_two():
    calls = []

    class E:
        def solve_snapshot(self):
            calls.append("snapshot")
            return ([50 + 0j], ["currents"], {"input_w": 1.0})

        def impedance(self):  # pragma: no cover - must not be reached
            raise AssertionError("a second process")

    zs, currents = _NEC2_SEAMS.run(E())
    assert calls == ["snapshot"] and zs == [50 + 0j] and currents == ["currents"]


# --------------------------------------------------------------------------
# the roster
# --------------------------------------------------------------------------


def test_the_roster_entry_appears_only_when_the_binary_is_there():
    absent = {b["name"] for b in backend_roster(have_pynec=True, have_nec2=False)}
    present = {b["name"] for b in backend_roster(have_pynec=True, have_nec2=True)}
    assert "nec2" not in absent
    assert "nec2" in present


def test_the_roster_entry_says_it_does_not_serve_buried_and_why():
    """Not a limitation note for its own sake. nec2++ handed a buried wire
    solves it AS IF IN AIR and prints a number, so the UI must grey the tab
    rather than let a user read that number as an answer."""
    entry = next(
        b
        for b in backend_roster(have_pynec=True, have_nec2=True)
        if b["name"] == "nec2"
    )
    assert entry["buried"] is False
    assert "as if in air" in entry["buried_refusal"].lower()
    assert entry["buried_issue"] == "antennaknobs#1354"
    # It shares PyNEC's panel: same physics, same knobs, no second UI.
    assert entry["panel"] == "pynec"


def test_the_server_names_the_three_external_backends_by_a_map_not_a_ternary():
    """The two-way `"pynec" if backend is pynec_backend else "nec5"` named the
    resolved solver in two places; with a third engine it would have stamped
    every nec2 answer "nec5"."""
    import antennaknobs.web.server as server

    assert set(server._EXTERNAL_BACKENDS) == {"pynec", "nec5", "nec2"}
    assert set(server._BACKEND_NAME.values()) == {"pynec", "nec5", "nec2"}


# --------------------------------------------------------------------------
# end to end, through momwire's portal as the NEC-2 stand-in
# --------------------------------------------------------------------------


@pytest.fixture()
def portal_exe(tmp_path, monkeypatch):
    """The same stand-in `test_nec2_engine_1354.py` uses: momwire's portal,
    which writes a column-exact NEC-2 printout because SimNEC reads it as
    nec2c."""
    pytest.importorskip("momwire.portal")
    from test_nec2_engine_1354 import _PORTAL_STANDIN, _stub

    exe = _stub(tmp_path, _PORTAL_STANDIN, "nec2")
    monkeypatch.setenv("NEC2_EXE", exe)
    import antennaknobs.engines.nec2 as m

    m._FORM_CACHE.clear()
    m._PROBE_CACHE.clear()
    return exe


def test_a_real_solve_reports_a_parsed_budget_not_a_fallback(portal_exe):
    """`beams.owa_yagi_6el` declares an aluminium conductivity, so its printout
    carries a real conductor loss — the end-to-end proof that the efficiency is
    read rather than defaulted, because a fallback would read exactly 1.0."""
    B = importlib.import_module("antennaknobs.designs.beams.owa_yagi_6el").Builder
    eng = NEC2Engine(B(), ground="free")
    _zs, _currents, budget = eng.solve_snapshot()
    assert 0.90 < budget["efficiency_pct"] / 100.0 < 1.0, budget
    assert budget["wire_loss_w"] > 0.0, budget
    assert eng._excited_efficiency == budget["efficiency_pct"] / 100.0
    assert eng._excited_p_in == budget["input_w"] > 0.0
    assert [label for label, _w in eng._excited_power_budget][:2] == [
        "Radiated",
        "Wire loss",
    ]


def test_the_web_solve_ships_the_budget_fields(portal_exe):
    from antennaknobs.web.examples import example_for

    out = example_for("beams.owa_yagi_6el").nec2_solve(
        {"geometry": "beams.owa_yagi_6el"}
    )
    assert 0.90 < out["radiation_efficiency"] < 1.0, out["radiation_efficiency"]
    assert out["input_power_w"] > 0.0
    assert [r["label"] for r in out["power_budget"]][:2] == ["Radiated", "Wire loss"]
    assert out["z_in_re"] and out["ground_model_applied"]


def test_a_multi_feed_design_ships_one_feed_row_per_port(portal_exe):
    from antennaknobs.web.examples import example_for

    out = example_for("arrays.invveearray").nec2_solve(
        {"geometry": "arrays.invveearray"}
    )
    assert out["multi_feed"] is True
    assert len(out["feeds"]) == 4, out["feeds"]
    assert all("v_re" in f and "z_re" in f for f in out["feeds"])


def test_the_binarys_own_complaint_is_reported_not_the_missing_block(portal_exe):
    """A deck the engine rejects used to surface as "no POWER BUDGET" — true,
    and useless: it names the block that is missing rather than the reason.

    `dipoles.pota_invvee` carries an `LD 2` (a distributed jacket inductance)
    which momwire's portal declines, so the stand-in is the one refusing here.
    Real nec2c supports LD 2; what this pins is the REPORTING, which is the
    part that was wrong whoever refuses.
    """
    B = importlib.import_module("antennaknobs.designs.dipoles.pota_invvee").Builder
    eng = NEC2Engine(B(), ground="free")
    with pytest.raises(NEC2Error) as e:
        eng.solve_snapshot()
    assert "LD type 2" in str(e.value), str(e.value)
    assert "POWER BUDGET" not in str(e.value), str(e.value)


def test_the_pattern_endpoint_fills_the_grid_and_closes_the_seam(portal_exe):
    """46 thetas x 73 phis in dBi, the same contract every lane serves.

    The 360-degree column is the 0-degree one: NEC-2's RP computes NPH points
    from PHIS in steps of DPH, so 72 steps of 5 degrees reach 355 and 360 is
    never sampled. Reading the grid at `phi % 360` closes it without asking the
    engine for a column it already has -- and without this the endpoint raised
    `KeyError (0.0, 360.0)` on every request.
    """
    from antennaknobs.web.examples import example_for

    out = example_for("dipoles.invvee").nec2_pattern(
        {"geometry": "dipoles.invvee", "measurement_freq_mhz": 28.57}
    )
    assert out["available"] is True
    assert len(out["gain_dbi"]) == 46 and len(out["gain_dbi"][0]) == 73
    assert out["theta_deg"][0] == 0.0 and out["theta_deg"][-1] == 90.0
    assert out["phi_deg"][0] == 0.0 and out["phi_deg"][-1] == 360.0
    assert out["gain_dbi"][0][0] == out["gain_dbi"][0][-1]
    assert max(max(row) for row in out["gain_dbi"]) < 20.0

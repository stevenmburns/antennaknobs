"""A file's own sweep reaches the app's sweep, grid and all (AK#1682).

Before AK#1682 a file design's range set only the measurement dial's span
(``ui_params["meas_freq_range"]``); the sweep ran the app's ×0.8–×1.25 log
window whatever the file said. The range now travels with its grid as
``ui_params["sweep_range"]`` and reaches /examples as ``sweep_range``, which
the frontend ranks above ``sweep_policy`` (see ``lib/sweep.ts``).
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from antennaknobs.file_designs import builder_from_file
from antennaknobs.nec_import import parse_nec
from antennaknobs.simnec_import import _gen_sweep, parse_ssn

FIX = Path(__file__).parent / "fixtures" / "simnec_ac6la_1679"
LC1 = FIX / "snBydipole1-LC1.ssn"

# Dan's Generator sweep block, as SimNEC writes it; SPACING / EXPR are swapped
# per case. ``from``/``to`` are the stale 1-30 MHz the expr mode ignores.
GEN = """<element><type>GENERATOR</type>
<p><n>MHz</n><v>14.2</v>
  <sweepParam>
    <p><n>from</n><v>1</v></p>
    <p><n>to</n><v>30</v></p>
    <p><n>points</n><v>100</v></p>
    <p><n>expr</n><v>EXPR</v></p>
    <p><n>log</n><v>SPACING</v></p>
    <p><n>doSweep</n><v>y</v></p>
  </sweepParam>
</p>
</element>"""


def _gen(spacing: str, expr: str = "14 : 14.35 : 0.025"):
    return ET.fromstring(GEN.replace("SPACING", spacing).replace("EXPR", expr))


# --- the SimNEC Generator's start : stop : step -------------------------------


def test_the_expr_sweep_gives_start_stop_and_step():
    sweep, points, grid, note = _gen_sweep(_gen("expr"))
    assert sweep == pytest.approx((14.0, 14.35))
    assert grid == ("lin", pytest.approx(0.025))
    assert len(points) == 15
    assert note is None


def test_a_logstep_expr_is_a_log_grid_in_total_points():
    sweep, points, grid, _ = _gen_sweep(_gen("expr", "1.1 : 2.2 : logStep .1"))
    assert sweep == pytest.approx((1.1, 2.2))
    # lo, hi, and every 10**(k*.1) strictly between them: 5 values total.
    assert grid == ("log", 5)
    assert len(points) == 5


@pytest.mark.parametrize(
    ("spacing", "grid"),
    [
        ("lin", ("lin", pytest.approx(29 / 99))),
        ("log", ("log", 100)),  # the GEN fixture's own <points>, exactly
    ],
)
def test_lin_and_log_modes_carry_their_spacing(spacing, grid):
    sweep, _, got, _ = _gen_sweep(_gen(spacing))
    assert sweep == pytest.approx((1.0, 30.0))
    assert got == grid


def test_an_expr_of_several_items_has_a_range_but_no_one_grid():
    sweep, _, grid, _ = _gen_sweep(_gen("expr", "7:7.3:.05 {14:14.35:.1} 21.2"))
    assert sweep == pytest.approx((7.0, 21.2))
    assert grid is None


def test_dans_file_reaches_ui_params_as_a_linear_range():
    """The fixture itself: ``14 : 14.35 : 0.025`` under ``log = expr``."""
    assert parse_ssn(LC1.read_text(), name=LC1.name, network=True).sweep_grid == (
        "lin",
        pytest.approx(0.025),
    )
    ui = builder_from_file(str(LC1)).default_params["ui_params"]
    assert ui["sweep_range"] == {
        "lo": pytest.approx(14.0),
        "hi": pytest.approx(14.35),
        "spacing": "lin",
        "step": pytest.approx(0.025),
        "source": "file",
    }
    # The dial's own key is unchanged: it and the sweep read the same numbers.
    assert ui["meas_freq_range"] == pytest.approx((14.0, 14.35))


# --- the NEC FR card ----------------------------------------------------------

DECK = "GW 1 21 0 -5 10 0 5 10 .001\nGE 0\nEX 0 1 11 0 1 0\n{fr}\nEN\n"


def test_a_linear_fr_card_is_a_lin_grid():
    deck = parse_nec(DECK.format(fr="FR 0 15 0 0 14.0 0.025"))
    assert deck.freq_mhz == pytest.approx((14.0, 14.35))
    assert deck.freq_grid == ("lin", pytest.approx(0.025))


def test_a_multiplicative_fr_card_is_a_log_grid():
    deck = parse_nec(DECK.format(fr="FR 1 11 0 0 10.0 1.0717735"))
    # The card's own NFRQ (11) is the exact point count -- no ppd round trip.
    assert deck.freq_grid == ("log", 11)


def test_a_single_frequency_fr_card_has_no_range_or_grid(tmp_path):
    deck = parse_nec(DECK.format(fr="FR 0 1 0 0 14.2 0"))
    assert deck.freq_grid is None
    p = tmp_path / "one.nec"
    p.write_text(DECK.format(fr="FR 0 1 0 0 14.2 0"))
    ui = builder_from_file(str(p)).default_params["ui_params"]
    assert "sweep_range" not in ui


# --- the payload the frontend reads -------------------------------------------


def test_examples_serves_the_files_range_and_grid(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    import antennaknobs.web.server as server

    (tmp_path / "lin.nec").write_text(DECK.format(fr="FR 0 15 0 0 14.0 0.025"))
    (tmp_path / "LC1.ssn").write_text(LC1.read_text())
    (tmp_path / "one.nec").write_text(DECK.format(fr="FR 0 1 0 0 14.2 0"))
    monkeypatch.setenv("ANTENNAKNOBS_USER_DIR", str(tmp_path))
    with TestClient(server.app) as c:
        examples = {e["name"]: e for e in c.get("/examples").json()["examples"]}
    want = {
        "lo": pytest.approx(14.0),
        "hi": pytest.approx(14.35),
        "spacing": "lin",
        "step": pytest.approx(0.025),
        "source": "file",
    }
    assert examples["user.lin"]["sweep_range"] == want
    assert examples["user.LC1"]["sweep_range"] == want
    assert examples["user.one"]["sweep_range"] is None
    # A catalog design declares none, and says so.
    assert examples["dipoles.invvee"]["sweep_range"] is None


# --- a Python design's ui_params["sweep_range"] ------------------------------


def _ui(sweep_range):
    from antennaknobs.web.adapter import _ui_sweep_range

    return _ui_sweep_range({"ui_params": {"sweep_range": sweep_range}})


def test_a_design_range_is_normalised_with_source_design():
    assert _ui({"lo": 7.0, "hi": 7.3, "step": 0.01}) == {
        "lo": 7.0,
        "hi": 7.3,
        "spacing": "lin",
        "step": 0.01,
        "source": "design",
    }
    assert _ui({"lo": 3, "hi": 30, "spacing": "log", "points": 61})["points"] == 61


def test_a_served_points_per_decade_converts_to_a_point_count():
    """AK#1682 follow-up: a band-locked 14.0-14.35 MHz range is 0.011
    decades, so 17 points used to be served/shown as ~1,500 per decade.
    `points_per_decade` is still accepted from `ui_params` (backward
    compatibility) but always converts to a plain point count on arrival."""
    # A whole decade (3-30 MHz) at 40/decade is 41 points -- kept as
    # "points_per_decade" pre-#1682-followup, now converted even though the
    # spacing matches.
    got = _ui({"lo": 3, "hi": 30, "spacing": "log", "points_per_decade": 40})
    assert got == {
        "lo": 3.0,
        "hi": 30.0,
        "spacing": "log",
        "points": 41,
        "source": "design",
    }
    # 14.0-14.35 MHz (0.0108 decades) at 20/decade rounds to 2 points, the
    # floor -- not the ~1,500-per-decade-looking absurdity 17 points used to
    # print as.
    assert (
        _ui({"lo": 14.0, "hi": 14.35, "spacing": "log", "points_per_decade": 20})[
            "points"
        ]
        == 2
    )


def test_a_density_that_does_not_fit_the_spacing_becomes_a_point_count():
    # 0.1 MHz over 7.0-7.3 is 4 points; 10/decade over one decade is 11.
    assert _ui({"lo": 7.0, "hi": 7.3, "spacing": "log", "step": 0.1})["points"] == 4
    assert _ui({"lo": 3, "hi": 30, "points_per_decade": 10})["points"] == 11


@pytest.mark.parametrize(
    "bad",
    [
        None,
        (7.0, 7.3),
        {"lo": 7.3, "hi": 7.0},
        {"lo": 0, "hi": 7.0},
        {"lo": 7.0},
        {"lo": 7.0, "hi": 7.3, "spacing": "cubic"},
    ],
)
def test_a_malformed_range_is_dropped_not_guessed(bad):
    assert _ui(bad) is None


# --- the hosted cap the frontend clamps to ------------------------------------


def test_the_frontend_clamps_to_the_servers_sweep_cap():
    """``lib/sweep.ts`` clamps a too-fine grid to ``MAX_SWEEP_POINTS`` so the
    hosted instance never refuses it. The two numbers are one contract: the
    frontend's constant is the server's default (an operator's env override
    is the one thing the frontend cannot know)."""
    import os
    import re

    from antennaknobs.web import cost

    if "ANTENNAKNOBS_MAX_SWEEP_POINTS" in os.environ:
        pytest.skip("the server's cap is overridden in this environment")
    ts = (
        Path(__file__).parents[1] / "src/antennaknobs/web/frontend/src/lib/sweep.ts"
    ).read_text()
    m = re.search(r"export const MAX_SWEEP_POINTS = (\d+);", ts)
    assert m, "lib/sweep.ts no longer declares MAX_SWEEP_POINTS"
    assert int(m.group(1)) == cost.MAX_SWEEP_POINTS

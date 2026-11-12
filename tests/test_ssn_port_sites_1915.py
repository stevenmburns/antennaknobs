"""A SimNEC NECSource position knob on a wire fed at its end (momwire#1915).

The shape: one horizontal wire with its segment count jammed, fed by a
NECSource at 100 % of it (its far end, a knot source, so the wire keeps the
#824 cut spelling, `NecDeck._vertex_wires`), and a capacitor NECSource whose
place along the same wire is a slider. On that spelling the importer cuts the
load's segment out as a one-segment piece of its own, so the load sits at
that segment's centre whatever the percentage says, and a position knob reads
a zero slope ("a load that snaps to segments"). SimNEC itself does not snap
there (`simnec_import._Script._apply_loads`: "between sites the percentage is
the place").

With ``exact_load_places`` (the optimizer's port-sites path,
`port_sites.place_loads_exactly`) the load rides its piece at the exact
percentage, the mesh stays put as it moves, and the moved-port cache serves
the trials. Off, the import is what it always was.

Every geometry and value here is invented.
"""

from __future__ import annotations

import contextlib
import io
import sys

import numpy as np
import pytest
from test_simnec_import import _ssn
from test_ssn_dan_1109 import _with_sliders

from antennaknobs import port_sites
from antennaknobs.engines.momwire import MomwireEngine
from antennaknobs.file_designs import builder_from_text
from antennaknobs.network import PortOnWire

needs_port_sites = pytest.mark.skipif(
    not port_sites.available(), reason=port_sites.NO_PORT_SITES
)

N = 162
LEN = 17.3
FREQS = [7.05, 7.12, 7.2]
PCTS = [21.37, 37.77, 52.11, 68.43]
RTOL = 1e-9

SCRIPT = "\n".join(
    [
        "//invented flat top",
        "P1 w2 gnd;",
        "H_len;",
        "Cap_F;",
        "Cap_Pct;",
        "NECUnits meters;",
        "NEC2",
        f"GW 1 {N} 0 -H_len 10 0 0 10 0.00035",
        "GW 2 9 0 0 10 0 0 8.6 0.00035",
        "FR 0 1 0 0 7.1 0",
        "NECEND",
        f"$GW_1.JamSegments({N});",
        "$src = NECSource({w2, gnd}, $GW_1, 100);",
        "$cap = NECSource(C(Cap_F), $GW_1, Cap_Pct);",
    ]
)
TEXT = _with_sliders(_ssn(SCRIPT), H_len=str(LEN), Cap_F="83p", Cap_Pct="37.77")


@pytest.fixture(scope="module")
def design():
    return builder_from_text("invented_flat_top.ssn", TEXT)


def _b(design, exact, **knobs):
    b = design({**design.default_params, **knobs})
    return port_sites.place_loads_exactly(b) if exact else b


def _z(b, freqs=FREQS):
    return np.asarray(
        MomwireEngine(b, **port_sites.engine_kwargs()).impedance_sweep(freqs)
    )


def test_the_knobs_are_the_sliders(design):
    p = design.default_params
    assert (p["par_H_len"], p["par_Cap_F"], p["par_Cap_Pct"]) == (LEN, 83.0, 37.77)


def test_off_the_load_is_cut_out_at_its_segment_and_does_not_move(design):
    """Main's spelling, kept: the load on a one-segment piece of its own, so
    37.77 % and 37.9 % (both in segment 62) are the same antenna."""
    a, b = _b(design, False, par_Cap_Pct=37.77), _b(design, False, par_Cap_Pct=37.9)
    assert a.build_network().ports["load1"] == PortOnWire("load1")
    np.testing.assert_array_equal(_z(a, FREQS[:1]), _z(b, FREQS[:1]))


def test_exact_places_move_the_load_and_keep_the_mesh(design):
    """The load at its percentage on one fixed piece: the slope is nonzero,
    the wires are the same at every position, and the arclength is the
    percentage of the wire."""
    a, b = _b(design, True, par_Cap_Pct=37.77), _b(design, True, par_Cap_Pct=37.9)
    assert a.build_wires() == b.build_wires()
    ea = MomwireEngine(a, **port_sites.engine_kwargs())
    (arc,) = [x for (_pl, x, _v) in ea._feeds]
    assert arc == pytest.approx(0.3777 * LEN, rel=1e-12)
    za, zb = _z(a, FREQS[:1]), _z(b, FREQS[:1])
    slope = (zb - za) / 0.13
    assert np.all(np.abs(slope) > 1e-3), slope


@needs_port_sites
def test_the_cache_matches_the_whole_wire_rebuild_on_the_deck(design, monkeypatch):
    real = port_sites.PortSitesSession._build
    calls = []
    monkeypatch.setattr(
        port_sites.PortSitesSession,
        "_build",
        lambda self, *a: calls.append(a[-1]) or real(self, *a),
    )
    s = port_sites.PortSitesSession()
    s.sweep(
        MomwireEngine(_b(design, True, par_Cap_Pct=30.0), **port_sites.engine_kwargs()),
        FREQS,
    )
    worst = 0.0
    for pct in PCTS:
        b = _b(design, True, par_Cap_Pct=pct)
        zs = s.sweep(MomwireEngine(b, **port_sites.engine_kwargs()), FREQS)
        n = len(calls)
        ref = _z(_b(design, True, par_Cap_Pct=pct))
        assert len(calls) == n  # the rebuild never builds a PortSites
        worst = max(worst, float(np.max(np.abs(zs - ref) / np.abs(ref))))
    assert worst <= RTOL, worst
    assert s.counts == {"fast": 3, "first": 1, "rebuild": 1, "built": len(FREQS)}


@needs_port_sites
def test_the_cli_optimize_moves_the_position_knob_and_serves_it_fast(tmp_path):
    """``optimize --bands ... --port-sites`` on the deck: the position knob
    is not reported stuck, and trials come from the cache."""
    import antennaknobs.cli  # noqa: F401 — the module; the package re-exports cli()

    cli = sys.modules["antennaknobs.cli"]
    deck = tmp_path / "invented_flat_top.ssn"
    deck.write_text(TEXT)
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        cli.cli(
            [
                "optimize",
                "--builder",
                f"@{deck}",
                "--engine",
                "momwire",
                "--ground",
                "free",
                "--bands",
                ",".join(str(f) for f in FREQS),
                "--params",
                "par_Cap_Pct",
                "par_Cap_F",
                "--bound",
                "par_Cap_Pct=20:60",
                "--bound",
                "par_Cap_F=50:120",
                "--max-evals",
                "16",
                "--port-sites",
            ]
        )
    text = out.getvalue()
    line = next(ln for ln in text.splitlines() if ln.startswith("port sites:"))
    fast = int(line.split()[2])
    assert fast > 0, line
    assert "par_Cap_Pct did not move" not in text, text

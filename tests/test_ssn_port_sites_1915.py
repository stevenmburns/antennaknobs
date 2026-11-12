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


# --- the same antenna in a station, as a full-station file is saved ----------
#
# Seven wires and 302 segments: the flat top, its lead, and five parasitic
# counterpoise wires, one carrying a fixed coil. Between the antenna and the
# GENERATOR a station chain SimNEC style: an S block (a choke), a coax run,
# a second S block (an unun) and a second coax run, the two .s2p files stored
# in the .ssn's FILEARCHIVE (gzip, then base64), as SimNEC saves them.


def _s2p(s11, s21, s22) -> str:
    """A synthetic 2-port Touchstone file, RI, 50 ohm."""
    rows = []
    for k, f in enumerate((6.9, 7.0, 7.1, 7.2, 7.3)):
        d = 0.01 * k
        a, b, c = s11 + d, s21 * (1 - d), s22 - d
        rows.append(
            f"{f} {a.real} {a.imag} {b.real} {b.imag} {b.real} {b.imag} "
            f"{c.real} {c.imag}"
        )
    return "\n".join(["! invented", "# MHz S RI R 50", *rows])


def _stored(name: str, text: str) -> tuple[str, str]:
    import base64
    import gzip

    b64 = base64.b64encode(gzip.compress(text.encode())).decode()
    return name, "\n".join(b64[i : i + 76] for i in range(0, len(b64), 76))


def _station_ssn(script: str) -> str:
    import xml.etree.ElementTree as ET

    root = ET.Element("SimNEC1p0")
    top = ET.SubElement(root, "SmithChartCircuit")
    fa = ET.SubElement(top, "FILEARCHIVE")
    for name, blob in (
        _stored(
            "C:\\SimNEC\\choke.s2p", _s2p(0.06 + 0.04j, 0.95 - 0.18j, -0.02 + 0.1j)
        ),
        _stored("C:\\SimNEC\\unun.s2p", _s2p(0.11 - 0.07j, 0.88 + 0.25j, 0.05 - 0.03j)),
    ):
        el = ET.SubElement(fa, "element")
        ET.SubElement(el, "name").text = name
        ET.SubElement(el, "compressed").text = blob
    circuit = ET.SubElement(top, "CIRCUIT")

    def element(typ, label, params):
        el = ET.SubElement(circuit, "element")
        ET.SubElement(el, "type").text = typ
        ET.SubElement(el, "sweeperLabel").text = label
        for n, v in params:
            p = ET.SubElement(el, "p")
            ET.SubElement(p, "n").text = n
            ET.SubElement(p, "v").text = v

    coax = [("Zo", "50"), ("VFnom", "0.66"), ("k1", "0.3"), ("k2", "0.004")]
    element("LOAD", "L", [("ohms", "1000000000")])
    element("NETWORK", "A", [("equ", script)])
    element(
        "SCATTERING",
        "S1",
        [("dir", "2 <> 1"), ("Zref", "50"), ("file", ".\\choke.s2p")],
    )
    element("SERIES_TLINE", "T1", [("ft", "35"), *coax])
    element(
        "SCATTERING", "S2", [("dir", "2 <> 1"), ("Zref", "50"), ("file", ".\\unun.s2p")]
    )
    element("SERIES_TLINE", "T2", [("ft", "60"), *coax])
    element("GENERATOR", "G", [("MHz", "7.1"), ("Zo", "50")])
    return ET.tostring(root, encoding="unicode")


STATION_SCRIPT = "\n".join(
    [
        "//invented flat top in a station",
        "P1 w2 gnd;",
        "H_len;",
        "Cap_F;",
        "Cap_Pct;",
        "NECUnits meters;",
        "NEC2",
        f"GW 1 {N} 0 -H_len 10 0 0 10 0.00035",
        "GW 2 9 0 0 10 0 0 8.6 0.00035",
        *(
            f"GW {3 + k} 25 -12 {1.5 * k + 1} 1 4 {1.5 * k + 1} 1 0.001"
            for k in range(5)
        ),
        "FR 0 1 0 0 7.1 0",
        "NECEND",
        f"$GW_1.JamSegments({N});",
        "$src = NECSource({w2, gnd}, $GW_1, 100);",
        "$cap = NECSource(C(Cap_F), $GW_1, Cap_Pct);",
        "$coil = NECSource(R(0.7) + L(2.2u), $GW_3, 50);",
    ]
)
STATION_TEXT = _with_sliders(
    _station_ssn(STATION_SCRIPT), H_len=str(LEN), Cap_F="83p", Cap_Pct="37.77"
)


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


@needs_port_sites
def test_the_deck_s_knob_gradients_match_rebuilds(design):
    """On the deck: dZ/dCap_Pct (through x = pct/100 * H_len) and dZ/dCap_F
    (the network) with no solve, against central differences of whole-wire
    rebuilds, <= 1e-5 relative; H_len, which moves the geometry, has none."""
    from antennaknobs.band_opt import builder_sweep_fn

    s = port_sites.PortSitesSession()
    sweep = builder_sweep_fn(
        design(dict(design.default_params)), MomwireEngine, 50.0, port_sites=s
    )
    p = {"par_H_len": LEN, "par_Cap_F": 83.0, "par_Cap_Pct": 41.3}
    sweep({**p, "par_Cap_Pct": 44.0}, FREQS)
    dzs = sweep(p, FREQS, grad_knobs=p)["dzs"]
    assert set(dzs) == {"par_Cap_Pct", "par_Cap_F"}
    for name, h in {"par_Cap_Pct": 1e-4, "par_Cap_F": 1e-4}.items():
        fd = (
            _z(_b(design, True, **{**p, name: p[name] + h}))
            - _z(_b(design, True, **{**p, name: p[name] - h}))
        ) / (2 * h)
        rel = float(np.max(np.abs(dzs[name] - fd) / np.abs(fd)))
        assert rel <= 1e-5, (name, rel)


@needs_port_sites
def test_a_cached_trial_builds_no_solver_and_parses_once(design, monkeypatch):
    """A trial served from the cache constructs no solver (the base digest is
    read off the engine's constructor kwargs, `MomwireEngine._construction`),
    re-parses the deck once for its new knob value, and builds its wires
    once. The wires stay: the moved load's arclength is what the parse of the
    new percentage says, so no trial can be keyed without it."""
    from momwire import BSplineSolver

    import antennaknobs.file_designs as fdm
    from antennaknobs.band_opt import builder_sweep_fn

    s = port_sites.PortSitesSession()
    sweep = builder_sweep_fn(
        design(dict(design.default_params)), MomwireEngine, 50.0, port_sites=s
    )
    p = {"par_H_len": LEN, "par_Cap_F": 83.0}
    for pct in (30.0, 31.0, 32.0):
        sweep({**p, "par_Cap_Pct": pct}, FREQS)
    assert s.counts["fast"] == 1 and s.ready()

    counts = {"solver": 0, "parse": 0, "wires": 0}
    real_init = BSplineSolver.__init__
    real_parse = fdm._ssn_reparse
    real_wires = design.build_wires

    def init(self, *a, **k):
        counts["solver"] += 1
        return real_init(self, *a, **k)

    def parse(*a, **k):
        counts["parse"] += 1
        return real_parse(*a, **k)

    def wires(self):
        counts["wires"] += 1
        return real_wires(self)

    monkeypatch.setattr(BSplineSolver, "__init__", init)
    monkeypatch.setattr(fdm, "_ssn_reparse", parse)
    monkeypatch.setattr(design, "build_wires", wires)
    zs = sweep({**p, "par_Cap_Pct": 47.3}, FREQS)["zs"]
    assert s.counts["fast"] == 2
    assert counts == {"solver": 0, "parse": 1, "wires": 1}, counts
    monkeypatch.setattr(BSplineSolver, "__init__", real_init)
    ref = _z(_b(design, True, **{**p, "par_Cap_Pct": 47.3}))
    assert float(np.max(np.abs(zs - ref) / np.abs(ref))) <= RTOL

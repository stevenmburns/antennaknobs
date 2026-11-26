"""Junction probes and A/B rails on the station rail (docs/design/
block-builder.md, phase S1).

The probes are gated against circuits whose junction impedance is known in
closed form, on the antenna's own solved impedance as the load: a lossless
line (the transmission-line equation), a quarter-wave transformer
(Z_in·Z_L = Z0²) and an L network designed by hand to match 50 Ω. The probe
at the antenna terminal is gated against the plain feed-point impedance the
workbench reads for the same design. Free space throughout: the circuit is
what is under test.
"""

import cmath
import importlib
import math

import pytest
from fastapi.testclient import TestClient

import antennaknobs.web.server  # noqa: F401 — adapter import order (registry)
from antennaknobs import station_rail as sr
from antennaknobs.engines.momwire import MomwireEngine
from antennaknobs.network_reduce import C_LIGHT
from antennaknobs.station_rail_solve import solve_chain
from antennaknobs.web.adapter import _apply_plane, _make_momwire_engine
from antennaknobs.web.server import app

from test_station_rail import REL, solved


def _builder(design):
    return importlib.import_module(f"antennaknobs.designs.{design}").Builder()


def _z(row):
    return complex(row["z_re"], row["z_im"])


def _line_in(zl, z0, length, vf, f_mhz):
    """The lossless line equation: Z looking into ``length`` of line on
    ``zl``."""
    t = math.tan(2 * math.pi * f_mhz * 1e6 * length / (vf * C_LIGHT))
    return z0 * (zl + 1j * z0 * t) / (z0 + 1j * zl * t)


# The analytic gates' tolerance. The rail and the closed form evaluate the
# same line equation by different routes (the reducer's ABCD stamp against
# tan above); measured agreement is ~3e-16 relative.
ANALYTIC = 1e-10


def test_probe_through_a_lossless_line_matches_the_line_equation():
    att, sa = solved("dipoles.invvee")
    f = sa.eng.builder.freq
    chain = {
        "rig": "rig",
        "items": [
            {"kind": "line", "z0": 75.0, "length_m": 3.0, "vf": 0.66},
            {"kind": "line", "z0": 300.0, "length_m": 1.7, "vf": 0.9},
        ],
    }
    rows = solve_chain(sa, chain, att)["probes"]
    assert [r["at"] for r in rows] == ["rig", "li", "feed", "antenna"]
    zl = _z(rows[-1])
    # No shunt at the feed: the feed probe IS the bare antenna.
    assert _z(rows[2]) == zl
    z_li = _line_in(zl, 300.0, 1.7, 0.9, f)
    z_rig = _line_in(z_li, 75.0, 3.0, 0.66, f)
    assert _z(rows[1]) == pytest.approx(z_li, rel=ANALYTIC)
    assert _z(rows[0]) == pytest.approx(z_rig, rel=ANALYTIC)
    # SWR at the stated reference, 50 Ω.
    g = abs((z_rig - 50) / (z_rig + 50))
    assert rows[0]["swr"] == pytest.approx((1 + g) / (1 - g), rel=ANALYTIC)


def test_quarter_wave_section_inverts_the_load():
    att, sa = solved("dipoles.invvee")
    f = sa.eng.builder.freq
    quarter = 0.66 * C_LIGHT / (f * 1e6) / 4
    chain = {
        "rig": "rig",
        "items": [{"kind": "line", "z0": 75.0, "length_m": quarter, "vf": 0.66}],
    }
    rows = solve_chain(sa, chain, att)["probes"]
    assert _z(rows[0]) * _z(rows[-1]) == pytest.approx(75.0**2, rel=ANALYTIC)


def test_a_hand_designed_l_network_presents_fifty_ohms():
    att, sa = solved("dipoles.invvee")
    f = sa.eng.builder.freq
    zl = solve_chain(sa, {"rig": "rig", "items": []}, att)["probes"][-1]
    zl = _z(zl)
    w = 2 * math.pi * f * 1e6
    # Shunt C across the load lifts the susceptance to b, chosen so that
    # Re(1/(G + jb)) = 50; then a series L cancels what reactance is left.
    y = 1 / zl
    g = y.real
    assert g < 1 / 50  # the load this design gives is one a low-pass L matches
    b = math.sqrt(g / 50 - g * g)
    c = (b - y.imag) / w
    x = b / (g * g + b * b)
    lh = x / w
    assert c > 0 and lh > 0
    chain = {
        "rig": "rig",
        "items": [
            {
                "kind": "l_tuner",
                "series_l_uH": lh * 1e6,
                "shunt_c_pF": c * 1e12,
                "shunt_at": "out",
            }
        ],
    }
    s = solve_chain(sa, chain, att)
    assert _z(s["probes"][0]) == pytest.approx(50.0, rel=ANALYTIC)
    assert s["swr"] == pytest.approx(1.0, abs=1e-9)
    # A lossless network burns nothing: the whole of the rig's power reaches
    # the antenna.
    assert s["antenna_share"] == pytest.approx(1.0, abs=1e-12)


def test_shunts_at_a_node_belong_to_that_nodes_probe():
    att, sa = solved("dipoles.invvee")
    f = sa.eng.builder.freq
    stub = {"kind": "open_stub", "freq_mhz": f, "length_wl": 0.1, "z0": 50.0}
    chain = {
        "rig": "rig",
        "items": [{"kind": "line", "z0": 50.0, "length_m": 2.0, "vf": 1.0}, stub],
    }
    rows = solve_chain(sa, chain, att)["probes"]
    zl = _z(rows[-1])
    # An open stub of 0.1 λ: Y = j tan(2π·0.1)/Z0, in parallel with the load.
    y_stub = 1j * math.tan(2 * math.pi * 0.1) / 50.0
    z_feed = 1 / (1 / zl + y_stub)
    assert [r["at"] for r in rows] == ["rig", "feed", "antenna"]
    assert _z(rows[1]) == pytest.approx(z_feed, rel=ANALYTIC)
    assert _z(rows[0]) == pytest.approx(
        _line_in(z_feed, 50.0, 2.0, 1.0, f), rel=ANALYTIC
    )


# --- the antenna terminal against the plain feed-point impedance ----------------------


def test_antenna_probe_equals_the_plain_feed_point_on_a_wire_design():
    """A design with no network: the probe reduces the antenna's Y, the plain
    solve runs the excited solve on the ex wire. Two routes through the same
    fill; they agree to the house tolerance (measured ~4e-16 relative)."""
    att, sa = solved("dipoles.invvee")
    z_probe = _z(solve_chain(sa, {"rig": "rig", "items": []}, att)["probes"][-1])
    z_plain = complex(
        _make_momwire_engine({}, _builder("dipoles.invvee")).impedance()[0]
    )
    assert z_probe == pytest.approx(z_plain, rel=REL)


def test_antenna_probe_equals_the_workbench_plane_at_the_feed():
    """A station design: the workbench's own measurement plane at the feed
    (`_apply_plane`), the antenna with its station unscrewed. The same network
    reduced over the same Y: bit for bit."""
    b = _builder("wire.doublet_ladder_tuner")
    _apply_plane(b, {"plane": "feed"})
    z_plane = complex(_make_momwire_engine({}, b).impedance()[0])
    att, sa = solved("wire.doublet_ladder_tuner")
    chain = sr.starting_chain(att, _builder("wire.doublet_ladder_tuner"))[0]
    z_probe = _z(solve_chain(sa, chain, att)["probes"][-1])
    assert z_probe == z_plane


def test_antenna_probe_is_bit_identical_where_the_design_feeds_its_port():
    """A design whose source already sits on its feed port, with traps the
    antenna carries: the probe's network IS the design's, so the number is the
    same bits."""
    z_plain = complex(
        _make_momwire_engine({}, _builder("multiband.trap_dipole")).impedance()[0]
    )
    att, sa = solved("multiband.trap_dipole")
    assert att.form == "cut"
    z_probe = _z(solve_chain(sa, {"rig": "rig", "items": []}, att)["probes"][-1])
    assert z_probe == z_plain


@pytest.mark.parametrize(
    "design",
    [
        # A loading coil in series at the source port: no station, the coil
        # is the antenna's.
        "dipoles.short_dipole_loaded",
        # Bonds shorting the idle stubs at their own ports.
        "verticals.tri_moxon",
    ],
)
def test_antenna_probe_is_the_designs_own_z_where_it_has_no_station(design):
    z_plain = complex(_make_momwire_engine({}, _builder(design)).impedance()[0])
    att, sa = solved(design)
    z_probe = _z(solve_chain(sa, {"rig": "rig", "items": []}, att)["probes"][-1])
    assert z_probe == z_plain


def test_a_shunt_across_the_feed_is_named_where_the_plane_keeps_it():
    """The sky loop's L match puts its shunt arm across the feed. The rail
    takes it off with the station; the workbench's plane at the feed keeps
    it. The two "feed" numbers differ, and the antenna says why."""
    from types import SimpleNamespace

    from antennaknobs.web.station_rail_api import _Antenna

    att = sr.attach("loops.skyloop_lmatch", _builder("loops.skyloop_lmatch"))
    assert att.at_feed == 1
    view = SimpleNamespace(att=att, freq_mhz=7.0, z_ref=50.0)
    assert "measurement plane at feed keeps it" in _Antenna.describe(view)["notice"]
    att = sr.attach(
        "dipoles.invvee_coax_station", _builder("dipoles.invvee_coax_station")
    )
    assert att.at_feed == 0
    assert "notice" not in _Antenna.describe(
        SimpleNamespace(att=att, freq_mhz=7.0, z_ref=50.0)
    )


# --- A/B rails: the antenna solved once --------------------------------------------------


@pytest.fixture
def count_solves(monkeypatch):
    calls = []
    real = MomwireEngine._compute_y_matrix

    def counted(self, wavelength):
        calls.append(wavelength)
        return real(self, wavelength)

    monkeypatch.setattr(MomwireEngine, "_compute_y_matrix", counted)
    return calls


def _rail_b():
    return {
        "rig": "rig",
        "items": [
            {"kind": "cable", "cable": "RG-8X", "length_m": 15.0},
            {"kind": "l_tuner", "tune_to": 50.0, "shunt_at": "auto", "ql": 200.0},
            {"kind": "balun", "n": 1.0, "lmag_uH": 10.0, "qlmag": 100.0},
        ],
    }


def test_two_rails_their_probes_and_a_gallery_share_one_antenna_solve(count_solves):
    client = TestClient(app)
    req = {"geometry": "wire.doublet_ladder_tuner"}
    r = client.post(
        "/station/render", json={"request": req, "rails": [None, _rail_b()]}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    a, b = body["rails"]
    # Both rails solved their own circuits (they differ), with every probe,
    # on ONE solve of the antenna: counted at the engine's Y, the only place
    # the antenna is solved.
    assert _z(a) != pytest.approx(_z(b), rel=1e-3)
    assert len(a["probes"]) == 4 and len(b["probes"]) == 5
    assert len(count_solves) == 1 and body["antenna_solves"] == 1
    # The antenna terminal is one antenna: the same number on both rails.
    assert a["probes"][-1] == b["probes"][-1]
    count_solves.clear()
    g = client.post(
        "/station/gallery", json={"request": req, "chain": a["chain"], "add": "auto_t"}
    ).json()
    assert len(g["cards"]) == 3
    assert len(count_solves) == 1 and g["antenna_solves"] == 1


def test_endpoints_refuse_with_the_reason():
    client = TestClient(app)
    r = client.post(
        "/station/render", json={"request": {"geometry": "arrays.bowtiearray"}}
    )
    assert r.status_code == 422 and "fed at 4 wires" in r.json()["detail"]
    r = client.post(
        "/station/render",
        json={
            "request": {"geometry": "dipoles.invvee"},
            "rails": [{"items": [{"kind": "cable", "cable": "nope", "length_m": 1}]}],
        },
    )
    assert r.status_code == 422 and "unknown cable" in r.json()["detail"]


def test_read_endpoint_reads_the_rails_own_file_and_refuses_another_designs():
    client = TestClient(app)
    req = {"geometry": "dipoles.invvee"}
    rail = client.post("/station/render", json={"request": req}).json()["rails"][0]
    got = client.post(
        "/station/read", json={"request": req, "text": rail["python"]}
    ).json()
    assert got["chain"] == rail["chain"]
    other = {"geometry": "wire.doublet_ladder_tuner"}
    got = client.post(
        "/station/read", json={"request": other, "text": rail["python"]}
    ).json()
    assert "dipoles.invvee" in got["refusal"]
    got = client.post("/station/read", json={"text": "import os\n"}).json()
    assert "refusal" in got


def test_read_endpoint_refuses_a_file_for_another_feed_of_the_same_design():
    client = TestClient(app)
    req = {"geometry": "dipoles.invvee_coax_station"}
    text = sr.to_python(
        {"rig": "rig", "items": [{"kind": "cable", "cable": "RG-8X", "length_m": 9.0}]},
        sr.attach(req["geometry"], _builder(req["geometry"])),
    )
    assert (
        "chain"
        in client.post("/station/read", json={"request": req, "text": text}).json()
    )
    other = text.replace('"feed"', '"feed_b"')
    assert sr.read_python(other)[1]["feed"] == "feed_b"  # in the house style
    got = client.post("/station/read", json={"request": req, "text": other}).json()
    assert "'feed_b'" in got["refusal"] and "'feed'" in got["refusal"]


def test_probe_rows_use_the_requests_reference():
    client = TestClient(app)
    req = {"geometry": "dipoles.invvee", "target_z0": 75.0}
    body = client.post("/station/render", json={"request": req}).json()
    rig = body["rails"][0]["probes"][0]
    z = _z(rig)
    g = abs((z - 75) / (z + 75))
    assert body["antenna"]["z_ref"] == 75.0
    assert rig["swr"] == pytest.approx((1 + g) / (1 - g), rel=1e-12)
    assert cmath.isfinite(z)

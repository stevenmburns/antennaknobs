"""Unit tests for web/server.py.

Covers the pure helpers (no FastAPI), the JSON-shape contracts the
frontend depends on (/healthz, /examples), and one end-to-end /solve
through the lightest geometry (dipole) so the request → response
pipeline is exercised without dragging in expensive sweeps.

The expensive endpoints (/sweep, /converge, /pattern, /ws) are
streaming/async and are deliberately *not* covered here — those are
integration territory and want their own targeted tests.
"""

from __future__ import annotations

import json
import threading
import time
from copy import deepcopy

import momwire
import numpy as np
import pytest
from fastapi.testclient import TestClient

from antennaknobs.web import server, user_designs
from antennaknobs.web.examples import REGISTRY


# ---------------------------------------------------------------------------
# Test client — shared across the whole module so FastAPI's startup runs once.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(server.app)


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def test_physical_cpu_count_is_positive():
    assert server._physical_cpu_count() >= 1


def test_thread_pools_sized_to_physical_cores():
    """Importing the server must actually resize the BLAS/OpenMP pools.

    Regression test for issue #377: env vars set in server.py never took
    effect because antennaknobs/__init__ imports numpy (and friends) before
    server.py's module body runs, so every pool had already snapshotted the
    env. The runtime threadpoolctl call is immune to import order — assert
    the pools really report the configured size, whatever machine this runs
    on (env overrides included, mirroring server.py's own logic).
    """
    import os

    from threadpoolctl import threadpool_info

    expected = {
        "blas": int(os.environ.get("OPENBLAS_NUM_THREADS", server._NPROC)),
        "openmp": int(os.environ.get("OMP_NUM_THREADS", server._NPROC)),
    }
    pools = threadpool_info()
    assert pools, "no BLAS/OpenMP pools found — did the solver stack change?"
    for pool in pools:
        want = expected.get(pool["user_api"])
        if want is not None:
            assert pool["num_threads"] == want, pool["filepath"]


def test_polyline_knots_dedup_shared_corners():
    poly = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [1.0, 1.0, 0.0]])
    knots = server._polyline_knots(poly, [2, 3])
    # 2 + 3 segments with shared mid-corner → 2 + 3 + 1 = 6 knots, not 7.
    assert knots.shape == (6, 3)
    # First knot of segment 2 is the last knot of segment 1, not duplicated.
    np.testing.assert_allclose(knots[2], poly[1])


def test_sample_arc_for_wire_interleaves_knots_and_midpoints():
    # Wire: three colinear knots at x = 0, 1, 3. h_seg = [1, 2].
    # arc_at_knot = [0, 1, 3]; mid_arc = [0.5, 2.0]
    # sample_arc = [0, 0.5, 1, 2.0, 3]
    knots = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [3.0, 0.0, 0.0]])
    arc = server._sample_arc_for_wire(knots)
    np.testing.assert_allclose(arc, [0.0, 0.5, 1.0, 2.0, 3.0])


def test_attach_derived_em_fields_computes_wavenumber():
    # k = 2π f / c at the frontend's reference c (299_792_458 m/s).
    f_mhz = 30.0
    out = {"measurement_freq_mhz": f_mhz, "ground": False}
    server._attach_derived_em_fields(out)
    expected_k = 2 * np.pi * f_mhz * 1e6 / server.C_LIGHT
    assert out["k_meas_m_inv"] == pytest.approx(expected_k, rel=1e-12)
    # σ=0 → imaginary permittivity component is exactly zero.
    assert out["ground_eps_im"] == 0.0


def test_attach_derived_em_fields_ground_sigma_negates_into_eps_im():
    # With σ > 0, ground_eps_im = -σ / (ω ε₀) < 0.
    out = {
        "measurement_freq_mhz": 28.47,
        "ground": True,
        "ground_sigma": 0.005,
    }
    server._attach_derived_em_fields(out)
    assert out["ground_eps_im"] < 0.0


# ---------------------------------------------------------------------------
# /healthz — the smoke test the dev launcher polls
# ---------------------------------------------------------------------------


def test_healthz_returns_ok(client: TestClient):
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


# ---------------------------------------------------------------------------
# /params_source — "Copy Python" export of the live knob values
# ---------------------------------------------------------------------------


def _eval_params_block(src: str):
    from types import MappingProxyType

    ns: dict = {"MappingProxyType": MappingProxyType}
    exec(src, ns)
    return ns["default_params"]


def test_params_source_reflects_live_knob_values(client: TestClient):
    r = client.post(
        "/params_source",
        json={
            "geometry": "broadband.g5rv",
            "variant": "default",
            "z0_match": 512.5,
            "match_len_frac": 0.41,
        },
    )
    assert r.status_code == 200
    payload = r.json()
    assert payload["available"] is True
    block = _eval_params_block(payload["source"])
    # The overlaid slider values must come back out, not the design defaults.
    assert block["z0_match"] == 512.5
    assert block["match_len_frac"] == 0.41
    # Knob-values-only by default — no ui_params noise.
    assert "ui_params" not in block


def test_params_source_include_ui_and_mappingproxy(client: TestClient):
    r = client.post(
        "/params_source",
        json={
            "geometry": "broadband.g5rv",
            "include_ui": True,
            "wrap": "mappingproxy",
        },
    )
    payload = r.json()
    assert payload["source"].startswith("default_params = MappingProxyType({")
    block = _eval_params_block(payload["source"])
    assert "ui_params" in block


def test_params_source_names_block_after_variant(client: TestClient):
    payload = client.post(
        "/params_source",
        json={"geometry": "specialty.hentenna", "variant": "z100"},
    ).json()
    assert payload["source"].startswith("z100_params = {")


# ---------------------------------------------------------------------------
# /pattern_metrics — scalar far-field metrics for the compare table
# ---------------------------------------------------------------------------


def test_pattern_metrics_returns_expected_keys(client: TestClient):
    r = client.post(
        "/pattern_metrics",
        json={
            "geometry": "beams.yagi",
            "variant": "default",
            "measurement_freq_mhz": 28.4,
            "design_freq_mhz": 28.4,
        },
    )
    assert r.status_code == 200
    payload = r.json()
    assert payload["available"] is True
    m = payload["metrics"]
    for key in (
        "peak_gain_dbi",
        "takeoff_deg",
        "azimuth_deg",
        "front_to_back_db",
        "az_beamwidth_deg",
        "el_beamwidth_deg",
    ):
        assert key in m and isinstance(m[key], (int, float))
    # A yagi is a forward-gain beam: positive peak gain and a real F/B.
    assert m["peak_gain_dbi"] > 0.0
    assert m["front_to_back_db"] > 0.0


def test_pattern_metrics_tracks_the_measurement_frequency(client: TestClient):
    payload = client.post(
        "/pattern_metrics",
        json={"geometry": "beams.yagi", "measurement_freq_mhz": 21.1},
    ).json()
    assert payload["metrics"]["measurement_freq_mhz"] == 21.1


# ---------------------------------------------------------------------------
# /examples — schema serialization, used by the frontend on mount
# ---------------------------------------------------------------------------


def test_examples_endpoint_returns_every_registered_example(client: TestClient):
    payload = client.get("/examples").json()
    assert "examples" in payload
    names = {e["name"] for e in payload["examples"]}
    # Every registered geometry shows up.
    assert names == set(server.EXAMPLES.keys())


def test_examples_are_sorted_by_label(client: TestClient):
    payload = client.get("/examples").json()
    labels = [e["label"] for e in payload["examples"]]
    assert labels == sorted(labels)


def test_capabilities_reports_pynec_availability(client: TestClient, monkeypatch):
    """The frontend gates the PyNEC backend option on this flag (#429): when
    pynec-accel is absent the UI must not offer PyNEC, so the /ws solve does
    not silently fall back to momwire. Mirrors pynec_backend.HAVE_PYNEC."""
    from antennaknobs.web import pynec_backend

    payload = client.get("/capabilities").json()
    assert payload["have_pynec"] == pynec_backend.HAVE_PYNEC

    monkeypatch.setattr(pynec_backend, "HAVE_PYNEC", False)
    assert client.get("/capabilities").json()["have_pynec"] is False
    monkeypatch.setattr(pynec_backend, "HAVE_PYNEC", True)
    assert client.get("/capabilities").json()["have_pynec"] is True


def test_each_example_has_the_keys_the_frontend_reads(client: TestClient):
    payload = client.get("/examples").json()
    required = {
        "name",
        "label",
        "multi_feed",
        "param_schema",
        "result_schema",
        "bands",
        "meas_freq_range_mhz",
        "default_view",
        "default_freq_mhz",
        "has_design_freq",
        "variants",
        "variant_values",
        "sweep_policy",
        "variant_ui",
        "notes",
    }
    for ex in payload["examples"]:
        missing = required - set(ex.keys())
        assert not missing, f"{ex['name']}: missing keys {missing}"


# ---------------------------------------------------------------------------
# /trust + /untrust — in-UI trust for user designs
# ---------------------------------------------------------------------------

_TRUST_DESIGN = """
from types import MappingProxyType
from antennaknobs import AntennaBuilder

class Builder(AntennaBuilder):
    default_params = MappingProxyType({"freq": 14.0, "half_length": 5.0})

    def build_wires(self):
        h = self.half_length
        n = self.nominal_nsegs
        return [
            ((0.0, -h, 0.0), (0.0, -0.01, 0.0), n, None),
            ((0.0, 0.01, 0.0), (0.0, h, 0.0), n, None),
            ((0.0, -0.01, 0.0), (0.0, 0.01, 0.0), 1, 1 + 0j),
        ]
"""


@pytest.fixture
def gated_userdir(client, tmp_path, monkeypatch):
    """A fresh user dir with the trust gate ACTIVE (blanket-trust off) and the
    instance treated as local (not hosted). Cleans up REGISTRY after."""
    monkeypatch.setenv("ANTENNAKNOBS_USER_DIR", str(tmp_path))
    monkeypatch.delenv("ANTENNAKNOBS_TRUST_USER_DESIGNS", raising=False)
    monkeypatch.delenv("ANTENNAKNOBS_TRUST_FILE", raising=False)
    monkeypatch.setattr(server, "_HOSTED", False)
    yield tmp_path
    for k in [k for k in REGISTRY if k.startswith("user.")]:
        del REGISTRY[k]


def test_untrusted_design_surfaces_with_advisory(client, gated_userdir):
    (gated_userdir / "webby.py").write_text(
        _TRUST_DESIGN.replace(
            "from antennaknobs import AntennaBuilder",
            "from antennaknobs import AntennaBuilder\nimport socket",
        )
    )
    errs = {e["name"]: e for e in client.get("/examples").json()["errors"]}
    assert errs["user.webby"]["trust_required"] is True
    assert any("socket" in a["message"] for a in errs["user.webby"]["advisory"])
    assert "user.webby" not in {
        e["name"] for e in client.get("/examples").json()["examples"]
    }


def test_trust_endpoint_registers_design(client, gated_userdir):
    (gated_userdir / "webby.py").write_text(_TRUST_DESIGN)
    r = client.post("/trust", json={"stem": "user.webby"})
    assert r.status_code == 200 and r.json()["mode"] == "pinned"
    assert "user.webby" in {
        e["name"] for e in client.get("/examples").json()["examples"]
    }


def test_trust_edits_mode_and_untrust(client, gated_userdir):
    from antennaknobs import design_trust

    (gated_userdir / "webby.py").write_text(_TRUST_DESIGN)
    client.post("/trust", json={"stem": "webby", "allow_edits": True})
    assert design_trust.trust_status(gated_userdir / "webby.py") == "always"
    r = client.post("/untrust", json={"stem": "webby"})
    assert r.status_code == 200 and r.json()["removed"] is True
    assert design_trust.trust_status(gated_userdir / "webby.py") == "none"


def test_trust_unknown_design_404(client, gated_userdir):
    assert client.post("/trust", json={"stem": "ghost"}).status_code == 404


def test_trust_refused_when_hosted(client, monkeypatch):
    monkeypatch.setattr(server, "_HOSTED", True)
    assert client.post("/trust", json={"stem": "whatever"}).status_code == 403
    assert client.post("/untrust", json={"stem": "whatever"}).status_code == 403


def test_examples_serialize_param_groups_with_kind_group(client: TestClient):
    # fandipole is the canonical group-bearing geometry — its `bands`
    # ParamGroupSpec must round-trip with kind="group" so the frontend's
    # generic schema renderer knows to draw a repeating section.
    payload = client.get("/examples").json()
    fan = next(e for e in payload["examples"] if e["name"] == "multiband.fandipole")
    groups = [p for p in fan["param_schema"] if p.get("kind") == "group"]
    assert groups, "fandipole bands group missing from serialized schema"
    g = groups[0]
    assert g["name"] == "bands"
    assert g["repeat_count"] == "n_bands"
    assert g["max_repeats"] == 5
    # Inner params are serialized as a list of ParamSpec dicts.
    assert {p["name"] for p in g["params"]} == {"freq", "length_factor"}


def test_enum_options_always_serialize_as_value_label_dicts(client: TestClient):
    """The frontend renders enum_options as SchemaEnumOption dicts; designs
    may declare them as bare strings (the CABLES keys), which the adapter
    must normalise — un-normalised strings render as empty <option>s (the
    22px-wide cable dropdown bug)."""
    payload = client.get("/examples").json()
    seen_enum = False
    for ex in payload["examples"]:
        for p in ex["param_schema"]:
            if p.get("kind") != "enum":
                continue
            seen_enum = True
            for o in p["enum_options"]:
                assert isinstance(o, dict) and o.get("value") and o.get("label"), (
                    f"{ex['name']}.{p['name']}: bad enum option {o!r}"
                )
            values = [o["value"] for o in p["enum_options"]]
            assert p["default"] in values, (
                f"{ex['name']}.{p['name']}: default {p['default']!r} not in {values}"
            )
    assert seen_enum, "no enum params found — did the cable dropdowns vanish?"


def test_examples_carry_default_view_in_valid_set(client: TestClient):
    payload = client.get("/examples").json()
    for ex in payload["examples"]:
        assert ex["default_view"] in {"xy", "yz", "xz"}


def test_examples_carry_sweep_policy_keys(client: TestClient):
    payload = client.get("/examples").json()
    for ex in payload["examples"]:
        sp = ex["sweep_policy"]
        assert set(sp) == {"anchor", "lo_factor", "hi_factor", "band_locked"}
        assert sp["anchor"] in {"design_freq", "meas_freq"}


def test_variant_ui_only_lists_variants_that_differ(client: TestClient):
    # variant_ui is a per-variant override map; a variant appears only when its
    # derived hints differ from the design-level value. An entry carries a
    # sweep_policy (shaped exactly like the top-level one), explicit per-param
    # presentation overrides under "params", or both — never neither.
    payload = client.get("/examples").json()
    for ex in payload["examples"]:
        vui = ex["variant_ui"]
        assert isinstance(vui, dict)
        for variant, hints in vui.items():
            assert variant in ex["variants"]
            assert variant != "default"
            assert set(hints) <= {"sweep_policy", "params"} and hints
            if "sweep_policy" in hints:
                sp = hints["sweep_policy"]
                assert set(sp) == {"anchor", "lo_factor", "hi_factor", "band_locked"}
                assert sp != ex["sweep_policy"]  # only differing variants listed
            if "params" in hints:
                assert hints["params"]  # non-empty map of param -> hint fields
                for pname, fields in hints["params"].items():
                    assert fields and set(fields) <= {
                        "min",
                        "max",
                        "step",
                        "precision",
                        "unit",
                        "label",
                        "hidden",
                    }, (ex["name"], variant, pname)


def test_skyloop_band_locked_variant_flips_only_band_locked(client: TestClient):
    # The Part 2 payoff: a variant carrying only ui_params.sweep_policy.
    # band_locked deep-merges over the default's sweep_policy, inheriting anchor
    # and the lo/hi factors and flipping just band_locked.
    payload = client.get("/examples").json()
    ex = next(e for e in payload["examples"] if e["name"] == "loops.triangular_skyloop")
    assert "band_locked" in ex["variants"]
    default_sp = ex["sweep_policy"]
    assert default_sp["band_locked"] is False
    locked_sp = ex["variant_ui"]["band_locked"]["sweep_policy"]
    assert locked_sp["band_locked"] is True
    # everything except band_locked is inherited from the design-level policy
    assert {k: locked_sp[k] for k in ("anchor", "lo_factor", "hi_factor")} == {
        k: default_sp[k] for k in ("anchor", "lo_factor", "hi_factor")
    }


# ---------------------------------------------------------------------------
# solve() dispatcher — exercise the momwire path end-to-end on the cheapest
# geometry (dipole). This is the only place the test module calls a real
# solver; everything else stays I/O-only.
# ---------------------------------------------------------------------------


def test_solve_dispatches_to_momwire_for_dipole():
    out = server.solve(
        {
            "geometry": "dipoles.invvee",
            "measurement_freq_mhz": 28.47,
            "design_freq_mhz": 28.47,
            "momwire_model": "bspline",
        }
    )
    assert out["solver"] == "momwire"
    assert out["geometry"] == "dipoles.invvee"
    # _attach_derived_em_fields ran.
    assert "k_meas_m_inv" in out
    assert out["k_meas_m_inv"] > 0
    # _attach_gain_norm ran (η₀k²/8π·P_in — O(1), never skipped).
    assert "directivity_norm" in out
    assert out["directivity_norm"] > 0
    assert out["input_power_w"] > 0
    # Real dipole has a real-part impedance roughly in the tens of ohms.
    assert out["z_in_re"] > 0


def test_solve_open_circuited_feed_is_json_safe():
    """A matching-network slider at a physical open (T-match series C1 = 0 pF
    open-circuits the source; the network core reports Z = ∞, issue #289)
    must stay on the wire protocol: the adapter clamps to the Z_OPEN_OHMS
    sentinel so json.dumps never emits Infinity/NaN literals that the
    browser's JSON.parse would reject, and the gain norm degrades to 0 (no
    excitation, no pattern) instead of dividing by zero."""
    import json

    from antennaknobs.web.adapter import Z_OPEN_OHMS

    out = server.solve(
        {
            "geometry": "verticals.inverted_l_tmatch",
            "measurement_freq_mhz": 24.9,
            "design_freq_mhz": 28.57,
            "series_c1_pF": 0.0,
        }
    )
    assert out["z_in_re"] == Z_OPEN_OHMS and out["z_in_im"] == 0.0
    json.dumps(out, allow_nan=False)  # raises on any Infinity/NaN leftovers
    assert out["directivity_norm"] == 0.0
    assert out["input_power_w"] == 0.0


def test_solve_always_carries_norm_and_caches():
    """Every solve carries directivity_norm (it's an O(1) input-power scalar
    now, so there is no superseded-skip) and every solve result is cached."""
    req = {
        "geometry": "dipoles.invvee",
        "measurement_freq_mhz": 28.47,
        "design_freq_mhz": 28.47,
        "momwire_model": "bspline",
    }
    server._SOLVE_CACHE.clear()
    out = server.solve(req)
    assert out["directivity_norm"] > 0
    assert len(server._SOLVE_CACHE) == 1
    again = server.solve(req)
    assert again["cache_hit"] is True
    assert again["directivity_norm"] == out["directivity_norm"]


def test_adaptive_norm_grid_scales_with_size_and_clamps():
    """The directivity-norm grid sizer grows n_theta with electrical extent,
    keeps n_phi = 2*n_theta, and clamps to a floor/ceiling. A ~6λ structure
    must land above the measured aliasing floor (~16 theta-points), since
    sampling just below it corrupts the scalar by ~1 dB."""
    k = 2 * np.pi  # lambda = 1 m, so the bbox diagonal in metres equals D_lambda
    origin = np.zeros(3)

    def grid(d_lambda):
        return server._adaptive_norm_grid(k, origin, np.array([d_lambda, 0.0, 0.0]))

    nt_small, nph_small = grid(0.5)
    nt_mid, nph_mid = grid(6.0)
    nt_big, nph_big = grid(200.0)

    assert nph_small == 2 * nt_small and nph_mid == 2 * nt_mid
    assert nt_small <= nt_mid <= nt_big  # monotonic in electrical size
    assert nt_small >= 12  # floor
    assert nt_big == 90  # 13 + 1.2*200 = 253, clamped to the ceiling
    assert nt_mid >= 18  # clears the ~16-point aliasing floor with margin


# Designs spanning the electrical-size range, incl. an 80m skyloop run up to
# 50 MHz (~6λ bbox) — the case where a too-coarse grid falls off the aliasing
# cliff (~1 dB). Ground on and off (the ground path is a separate integral).
# The grounded entries pin ground_model="pec": these are solver
# SELF-CONSISTENCY diagnostics (field-side pattern power vs circuit-side
# P_in, and closed-form vs grid of the same PEC-image functional). Over a
# finite ground the two sides legitimately differ by the absorbed power and
# the closed form doesn't model Fresnel — that path is covered by
# test_norm_check_finite_ground_uses_grid_method instead.
_NORM_ACCURACY_REQS = [
    {
        "geometry": "dipoles.invvee",
        "measurement_freq_mhz": 28.47,
        "design_freq_mhz": 28.47,
        "momwire_model": "bspline",
        "ground": False,
    },
    {
        "geometry": "dipoles.invvee",
        "measurement_freq_mhz": 28.47,
        "design_freq_mhz": 28.47,
        "momwire_model": "bspline",
        "ground": True,
        "ground_model": "pec",
    },
    # n_per_wire=100: the 13-wavelength skyloop needs it for the BSpline
    # d=2 basis to conserve power under the 0.05 dB gate (0.063 dB at 80,
    # 0.041 at 100; the retired triangular basis sat under the gate at 80).
    {
        "geometry": "loops.triangular_skyloop",
        "measurement_freq_mhz": 50.0,
        "design_freq_mhz": 3.8,
        "momwire_model": "bspline",
        "n_per_wire": 100,
        "ground": False,
    },
    {
        "geometry": "loops.triangular_skyloop",
        "measurement_freq_mhz": 50.0,
        "design_freq_mhz": 3.8,
        "momwire_model": "bspline",
        "n_per_wire": 100,
        "ground": True,
        "ground_model": "pec",
    },
]


@pytest.mark.parametrize("req", _NORM_ACCURACY_REQS)
def test_gain_norm_power_balance_within_005_dB(req):
    """The circuit-side gain norm (η₀k²/8π·P_in) must match the field-side
    pattern-integral norm to within 0.05 dB across the electrical-size range —
    the momwire solve conserves power to well under the ~0.1 dB gain readout.
    This is NEC's 'average gain' diagnostic run as a regression test."""
    server._SOLVE_CACHE.clear()
    out = server.solve(req)
    circuit = out["directivity_norm"]
    assert circuit > 0
    field = server._pattern_integral_norm(out)
    db = 10 * np.log10(circuit / field)
    assert abs(db) < 0.05, (
        f"{req['geometry']} @ {req['measurement_freq_mhz']} MHz "
        f"ground={req['ground']}: power balance off by {db:+.4f} dB"
    )


@pytest.mark.parametrize("req", _NORM_ACCURACY_REQS)
def test_pattern_integral_closed_form_matches_fine_grid(req):
    """The closed-form pair-sum norm (spherical-Bessel kernel, PEC images)
    equals the fine 120x240 GL quadrature of the same discrete functional to
    within 0.01 dB — free space is exact; over ground the residual is the
    eps=1e10-Fresnel-vs-PEC difference near grazing."""
    server._SOLVE_CACHE.clear()
    out = server.solve(req)
    closed = server._pattern_integral_norm(out)
    assert closed > 0
    ref = deepcopy(out)
    server._compute_directivity_norm(ref, n_theta=120, n_phi=240)
    db = 10 * np.log10(closed / ref["directivity_norm"])
    assert abs(db) < 0.01, (
        f"{req['geometry']} ground={req['ground']}: closed form off by {db:+.4f} dB"
    )


def test_norm_check_endpoint_reports_power_balance(client: TestClient):
    """/norm_check returns the live circuit-side norm plus the field-side
    pattern norm (closed form on PEC-ground responses); for a converged
    design the two agree to within 0.05 dB (the overlay sits on the live
    trace). Pinned to ground_model="pec": that is the closed-form path,
    and the only ground where field-vs-circuit balance is physical."""
    server._SOLVE_CACHE.clear()
    req = {
        "geometry": "dipoles.invvee",
        "measurement_freq_mhz": 28.47,
        "design_freq_mhz": 28.47,
        "momwire_model": "bspline",
        "ground": True,
        "ground_model": "pec",
    }
    resp = client.post("/norm_check", json=req).json()
    assert resp["available"] is True
    assert resp["directivity_norm"] > 0 and resp["pattern_norm"] > 0
    assert resp["method"] == "closed_form"
    db = 10 * np.log10(resp["directivity_norm"] / resp["pattern_norm"])
    assert abs(db) < 0.05


def test_norm_check_finite_ground_uses_grid_method(client: TestClient):
    """Since the web momwire path ships real finite-ground constants, a
    grounded solve with a finite model must route /norm_check to the
    fine-grid Fresnel quadrature (the closed-form image identity is exact
    only for a perfect reflector). No tight balance assertion: over a lossy
    ground the field-side integral omits the absorbed power by design."""
    server._SOLVE_CACHE.clear()
    req = {
        "geometry": "dipoles.invvee",
        "measurement_freq_mhz": 28.47,
        "design_freq_mhz": 28.47,
        "momwire_model": "bspline",
        "ground": True,
        "ground_model": "fast",
    }
    resp = client.post("/norm_check", json=req).json()
    assert resp["available"] is True
    assert resp["method"].startswith("grid_")
    assert resp["pattern_norm"] > 0
    # The derived third-ledger number (issue #339) ships alongside, and is
    # exactly the norm-check ratio with the structural efficiency folded
    # back out of the field-side norm.
    assert resp["radiated_fraction"] == pytest.approx(
        resp["radiation_efficiency"] * resp["directivity_norm"] / resp["pattern_norm"]
    )


@pytest.mark.parametrize(
    "geometry, req_extra, params_extra, lo, hi",
    [
        # KJ6ER's POTA PERformer on 15M: ground absorption dominates —
        # ~30% radiated while >90% efficient structurally (the ledger
        # split advanced/pota-performer.md narrates).
        ("verticals.pota_performer", {}, {}, 0.22, 0.40),
        # A 7 m invvee on 20 m: higher in wavelengths, ~70% radiated.
        (
            "dipoles.invvee",
            {"measurement_freq_mhz": 14.1, "design_freq_mhz": 14.1},
            {"design_freq": 14.1, "freq": 14.1},
            0.60,
            0.85,
        ),
    ],
)
def test_norm_check_radiated_fraction_matches_far_field_ledger(
    client: TestClient, geometry, req_extra, params_extra, lo, hi
):
    """/norm_check's derived `radiated_fraction` (issue #339) agrees with the
    independent `far_field.radiated_fraction` trapezoid integral — the same
    solve run through MomwireEngine directly, over the web's Sommerfeld
    average ground — within a point on the calibration pair from the
    three-ledgers docs. The endpoint derives the number from the norm ratio
    (no angular grid of its own), so this pins the whole identity chain:
    gain-per-input-watt averaged over the sphere IS efficiency·dn/pn."""
    import importlib

    from antennaknobs import radiated_fraction
    from antennaknobs.engines import MomwireEngine

    server._SOLVE_CACHE.clear()
    req = {
        "geometry": geometry,
        "measurement_freq_mhz": 21.35,
        "design_freq_mhz": 21.35,
        "momwire_model": "bspline",
        "ground": True,
        "ground_model": "sommerfeld",
        **req_extra,
    }
    resp = client.post("/norm_check", json=req).json()
    assert resp["available"] is True
    assert lo < resp["radiated_fraction"] < hi

    mod = importlib.import_module(f"antennaknobs.designs.{geometry}")
    params = dict(mod.Builder.default_params)
    params.update(params_extra)
    eng = MomwireEngine(
        mod.Builder(params=params), ground=("finite", 10.0, 0.002), ground_z=0.0
    )
    ff = eng.far_field(n_theta=90, n_phi=360, del_theta=1, del_phi=1)
    assert resp["radiated_fraction"] == pytest.approx(radiated_fraction(ff), abs=0.01)


def test_norm_check_radiated_fraction_pec_and_free_space(client: TestClient):
    """Where there is no ground absorption the third ledger collapses onto
    the structural one: a lossless invvee reads ~100% radiated over PEC
    (closed form — no integration clipping) and in free space, within the
    solver's self-consistency gap."""
    server._SOLVE_CACHE.clear()
    base = {
        "geometry": "dipoles.invvee",
        "measurement_freq_mhz": 28.47,
        "design_freq_mhz": 28.47,
        "momwire_model": "bspline",
    }
    for ground in (
        {"ground": True, "ground_model": "pec"},
        {"ground": False},
    ):
        resp = client.post("/norm_check", json={**base, **ground}).json()
        assert resp["available"] is True
        assert resp["method"] == "closed_form"
        assert resp["radiated_fraction"] == pytest.approx(1.0, abs=0.02)


def test_directivity_norm_gl_beats_uniform_at_coarse_grid():
    """At a coarse theta grid on an electrically-large design, Gauss-Legendre is
    strictly closer to the fine reference than the legacy uniform-midpoint rule
    — the accuracy gain that lets the adaptive grid stay small."""
    req = {
        "geometry": "loops.triangular_skyloop",
        "measurement_freq_mhz": 50.0,
        "design_freq_mhz": 3.8,
        "momwire_model": "bspline",
        "n_per_wire": 80,
        "ground": False,
    }
    server._SOLVE_CACHE.clear()
    out = server.solve(req)
    ref = deepcopy(out)
    server._compute_directivity_norm(ref, n_theta=120, n_phi=240)
    fine = ref["directivity_norm"]

    gl, uni = deepcopy(out), deepcopy(out)
    server._compute_directivity_norm(gl, n_theta=20, n_phi=40, _theta_rule="gl")
    server._compute_directivity_norm(uni, n_theta=20, n_phi=40, _theta_rule="uniform")
    gl_err = abs(10 * np.log10(gl["directivity_norm"] / fine))
    uni_err = abs(10 * np.log10(uni["directivity_norm"] / fine))
    assert gl_err < uni_err


def test_solve_reports_radiation_efficiency_for_terminated_antenna():
    """A terminated antenna (the rhombic's load resistor) burns most of its
    input power, so the server reports radiation_efficiency < 1 and the plot
    means GAIN. With the input-power norm the load loss lives inside P_in (no
    efficiency multiply), so the norm must still agree with the old
    field-side construction (4π/∮|M_perp|²dΩ)·efficiency — the plotted gain
    of the rhombic did not move in this rework."""
    term = server.solve({"geometry": "wire.rhombic", "momwire_model": "bspline"})
    assert 0.1 < term["radiation_efficiency"] < 0.6  # ~0.29: most power in the load

    lossless = server.solve({"geometry": "broadband.g5rv", "momwire_model": "bspline"})
    assert lossless["radiation_efficiency"] == 1.0

    # Circuit-side norm ≡ (pattern-integral norm × efficiency), the old
    # displayed quantity, up to the solver's power-balance gap.
    assert term["directivity_norm"] > 0
    field_side = server._pattern_integral_norm(term)  # already × efficiency
    db = 10 * np.log10(term["directivity_norm"] / field_side)
    assert abs(db) < 0.05


def test_pynec_path_also_reports_radiation_efficiency():
    """Switching engines must keep the far-field plot meaning GAIN: the PyNEC
    path reports a radiation_efficiency < 1 for the terminated rhombic too
    (close to momwire's, both well under 1), and 1.0 for a lossless design --
    so the JS far-field cut is gain on either engine, not directivity on one
    and gain on the other."""
    from antennaknobs.web import pynec_backend

    if not pynec_backend.HAVE_PYNEC:
        import pytest

        pytest.skip("PyNEC backend not available")

    term_momwire = server.solve({"geometry": "wire.rhombic", "solver": "momwire"})
    term_pynec = server.solve({"geometry": "wire.rhombic", "solver": "pynec"})
    assert term_pynec["radiation_efficiency"] < 0.6
    # the two engines agree on the efficiency to better than ~1.5 dB (basis
    # difference + NEC's copper-loss card), far inside the old ~5 dB
    # directivity-vs-gain gap.
    ratio = term_pynec["radiation_efficiency"] / term_momwire["radiation_efficiency"]
    assert 0.7 < ratio < 1.4

    lossless_pynec = server.solve({"geometry": "broadband.g5rv", "solver": "pynec"})
    assert lossless_pynec["radiation_efficiency"] == 1.0


def test_solve_falls_back_when_geometry_unknown():
    # An unknown geometry should silently fall back to the first registered
    # example rather than 500 — the frontend can briefly send a stale name
    # while it reloads /examples.
    out = server.solve(
        {
            "geometry": "this_geometry_does_not_exist",
            "measurement_freq_mhz": 28.47,
        }
    )
    assert out["solver"] == "momwire"
    assert "wires" in out


# ---------------------------------------------------------------------------
# _wire_record — packs one wire's knot/sample currents for the JSON response.
# Pure data wrangling, no solver involvement.
# ---------------------------------------------------------------------------


def test_wire_record_packs_knot_data_without_samples():
    knots = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [2.0, 0.0, 0.0]])
    currents = np.array([0.5 + 0j, 1.0 + 0.2j, 0.0 + 0j])
    out = server._wire_record(knots, currents, label="wire7")
    assert out["label"] == "wire7"
    assert out["knot_positions"] == knots.tolist()
    assert out["knot_currents_re"] == [0.5, 1.0, 0.0]
    assert out["knot_currents_im"] == [0.0, 0.2, 0.0]
    # No sample keys when sample_currents is omitted.
    assert "sample_positions" not in out


def test_wire_record_packs_sample_data_when_provided():
    knots = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [2.0, 0.0, 0.0]])
    currents = np.array([0.0 + 0j, 1.0 + 0j, 0.0 + 0j])
    # 2 segments → 2*2+1 = 5 sample currents required.
    samples = np.array([0.0, 0.5, 1.0, 0.5, 0.0], dtype=complex)
    out = server._wire_record(knots, currents, "w", sample_currents=samples)
    # Interleaved positions: knot, midpoint, knot, midpoint, knot.
    pos = np.asarray(out["sample_positions"])
    assert pos.shape == (5, 3)
    np.testing.assert_allclose(pos[0], knots[0])
    np.testing.assert_allclose(pos[2], knots[1])
    np.testing.assert_allclose(pos[4], knots[2])
    np.testing.assert_allclose(pos[1], 0.5 * (knots[0] + knots[1]))
    assert out["sample_currents_re"] == [0.0, 0.5, 1.0, 0.5, 0.0]


def test_wire_record_rejects_currents_length_mismatch():
    knots = np.zeros((3, 3))
    currents = np.zeros(4, dtype=complex)  # one too many
    with pytest.raises(ValueError, match="currents/knots length mismatch"):
        server._wire_record(knots, currents, "w")


def test_wire_record_rejects_sample_currents_length_mismatch():
    knots = np.zeros((3, 3))
    currents = np.zeros(3, dtype=complex)
    bad_samples = np.zeros(4, dtype=complex)  # need 2*2+1 = 5
    with pytest.raises(ValueError, match="sample_currents length"):
        server._wire_record(knots, currents, "w", sample_currents=bad_samples)


# ---------------------------------------------------------------------------
# _compute_directivity_norm — pure-numpy integration over a synthetic
# wire grid. Doesn't need a solver; we feed it a hand-built response dict.
# ---------------------------------------------------------------------------


def _hertzian_dipole_response(freq_mhz: float = 30.0):
    """A 0.1 m centred-z wire with unit current — small enough that the
    radiation integral degenerates to a Hertzian-dipole pattern, large
    enough to keep the numerics well-conditioned.
    """
    knots = np.array(
        [[0.0, 0.0, -0.05], [0.0, 0.0, 0.0], [0.0, 0.0, 0.05]], dtype=float
    )
    return {
        "measurement_freq_mhz": freq_mhz,
        "ground": False,
        "wires": [
            {
                "knot_positions": knots.tolist(),
                "knot_currents_re": [1.0, 1.0, 1.0],
                "knot_currents_im": [0.0, 0.0, 0.0],
            }
        ],
    }


def test_compute_directivity_norm_positive_no_ground():
    out = _hertzian_dipole_response()
    server._attach_derived_em_fields(out)
    server._compute_directivity_norm(out, n_theta=15, n_phi=30)
    assert "directivity_norm" in out
    # ∫|M_perp|² dΩ > 0 for a non-zero current, so the norm is finite +.
    assert out["directivity_norm"] > 0
    assert np.isfinite(out["directivity_norm"])


# ---------------------------------------------------------------------------
# Streaming endpoints + /pattern dispatcher — TestClient drives the routes
# against the lightest geometry (dipole) so each call stays sub-second.
# ---------------------------------------------------------------------------


def _ndjson_records(response_text: str) -> list[dict]:
    return [
        __import__("json").loads(line)
        for line in response_text.splitlines()
        if line.strip()
    ]


def test_sweep_endpoint_empty_freqs_returns_only_done(client: TestClient):
    r = client.post("/sweep", json={"geometry": "dipoles.invvee", "freqs_mhz": []})
    assert r.status_code == 200
    recs = _ndjson_records(r.text)
    assert recs == [{"done": True, "solver": "momwire"}]


def test_sweep_endpoint_streams_one_record_per_freq_then_done(client: TestClient):
    freqs = [28.0, 28.47, 29.0]
    r = client.post(
        "/sweep",
        json={
            "geometry": "dipoles.invvee",
            "freqs_mhz": freqs,
            "measurement_freq_mhz": 28.47,
            "momwire_model": "bspline",
        },
    )
    assert r.status_code == 200
    recs = _ndjson_records(r.text)
    assert len(recs) == len(freqs) + 1
    *points, terminator = recs
    assert terminator == {"done": True, "solver": "momwire"}
    for f, rec in zip(freqs, points):
        assert rec["freq_mhz"] == f
        assert rec["solver"] == "momwire"
        assert isinstance(rec["z_re"], float)
        assert isinstance(rec["z_im"], float)
        # Real dipole impedance never goes pathologically far from order
        # ~50 Ω over a ±10% sweep — guards against a future signed-units
        # regression that produced -j×j-style mixups.
        assert abs(rec["z_re"]) < 1e4
        assert abs(rec["z_im"]) < 1e4


def test_sweep_endpoint_returns_ndjson_content_type(client: TestClient):
    r = client.post("/sweep", json={"geometry": "dipoles.invvee", "freqs_mhz": []})
    assert r.headers["content-type"].startswith("application/x-ndjson")


def test_converge_endpoint_streams_one_record_per_n_then_done(client: TestClient):
    ns = [3, 5]
    r = client.post(
        "/converge",
        json={
            "geometry": "dipoles.invvee",
            "n_values": ns,
            "measurement_freq_mhz": 28.47,
            "momwire_model": "bspline",
        },
    )
    assert r.status_code == 200
    recs = _ndjson_records(r.text)
    assert len(recs) == len(ns) + 1
    *points, terminator = recs
    assert terminator == {"done": True, "solver": "momwire"}
    for n, rec in zip(ns, points):
        assert rec["n_per_wire"] == n
        assert rec["solver"] == "momwire"
        # Convergence trace should always carry real impedance fields —
        # the error-path branch yields an `error` key instead, which
        # would mean dipole crapped out at this N (it shouldn't).
        assert "z_re" in rec and "z_im" in rec


def test_converge_endpoint_empty_n_values_returns_only_done(client: TestClient):
    r = client.post("/converge", json={"geometry": "dipoles.invvee", "n_values": []})
    recs = _ndjson_records(r.text)
    assert recs == [{"done": True, "solver": "momwire"}]


def test_pattern_endpoint_momwire_returns_unavailable(client: TestClient):
    # /pattern is PyNEC-only; momwire solvers get the {"available": False}
    # short-circuit. Tests both the solver-flag path and the
    # HAVE_PYNEC=False fallback shape.
    r = client.post(
        "/pattern",
        json={
            "geometry": "dipoles.invvee",
            "solver": "momwire",
            "measurement_freq_mhz": 28.47,
        },
    )
    assert r.status_code == 200
    assert r.json() == {"available": False}


def test_geometry_endpoint_returns_wires_without_solving(client: TestClient):
    # The fast antenna-shape preview: wires + feed marker, zero currents, and
    # no impedance/far-field (those come from the live solve). Geometry is
    # solver-independent, so it answers even with solver=pynec.
    r = client.post(
        "/geometry",
        json={
            "geometry": "dipoles.invvee",
            "design_freq_mhz": 28.47,
            "measurement_freq_mhz": 28.47,
            "solver": "pynec",
        },
    )
    assert r.status_code == 200
    out = r.json()
    assert out["geometry"] == "dipoles.invvee"
    assert out["preview"] is True
    assert out["solver"] == "momwire"
    assert len(out["wires"]) >= 1
    # Geometry only — every current is zero, and the solve never ran.
    assert "z_in_re" not in out
    for w in out["wires"]:
        assert len(w["knot_positions"]) > 0
        assert all(c == 0 for c in w["knot_currents_re"])
        assert all(c == 0 for c in w["knot_currents_im"])
    assert "feed_position" in out


def test_examples_carry_default_backend(client: TestClient):
    # Every example exposes default_backend (str | null). Grid arrays recommend
    # the array-block accelerator; benchmark-sized meshes recommend the
    # sinusoidal solver (see _SINUSOIDAL_RECOMMEND_MIN_BASIS); other designs
    # keep the UI default (null) so their basis/results are unchanged.
    payload = client.get("/examples").json()
    by_name = {e["name"]: e for e in payload["examples"]}
    for e in payload["examples"]:
        assert "default_backend" in e
        assert e["default_backend"] in (None, "arrayblock", "sinusoidal")
    assert by_name["arrays.bowtiearray2x4"]["default_backend"] == "arrayblock"
    assert by_name["verticals.elt_whip"]["default_backend"] == "sinusoidal"
    # A plain single-element design keeps the default.
    assert by_name["specialty.bowtie"]["default_backend"] is None
    # Regression: a Yagi is NOT a grid array — its equal-length directors used
    # to collapse to one signature and trip the "any repeated shape" test. The
    # recommendation now requires repetition to dominate (>= half the elements),
    # so a Yagi (and a plain dipole) keep the dense default.
    assert by_name["beams.yagi"]["default_backend"] is None
    assert by_name["dipoles.invvee"]["default_backend"] is None


def test_examples_carry_notes(client: TestClient):
    # `notes` is the informational design note (issue #373): a deck-backed
    # design fills it from NecDeck.skipped_note() via the reserved
    # ui_params["notes"] key; no built-in design is deck-backed, so every
    # example in the catalog ships it null (the frontend renders nothing).
    payload = client.get("/examples").json()
    for e in payload["examples"]:
        assert "notes" in e
        assert e["notes"] is None

    # The adapter forwards the reserved key verbatim to the example.
    from types import MappingProxyType

    from antennaknobs import AntennaBuilder
    from antennaknobs.web.adapter import _make_example

    class Noted(AntennaBuilder):
        default_params = MappingProxyType(
            {
                "freq": 14.0,
                "ui_params": MappingProxyType(
                    {"notes": "Deck cards not applied: LD (loading)"}
                ),
            }
        )

        def build_wires(self):
            return [((0.0, -5.0, 10.0), (0.0, 5.0, 10.0), 15, 1.0)]

    ex = _make_example("noted", Noted, defer_hints=True)
    assert ex.notes == "Deck cards not applied: LD (loading)"


def test_out_of_band_freq_synthesizes_band():
    """Issue #390: a design whose native `freq` lands outside every band tab
    must ship a band covering it — otherwise the frontend's design-switch
    snap falls back to bands[0] (160 m for the default HF set), framing a
    406 MHz whip for a 95 m wavelength and dragging measFreq along."""
    from types import MappingProxyType

    from antennaknobs import AntennaBuilder
    from antennaknobs.web.adapter import DEFAULT_AMATEUR_BANDS, _make_example

    class Uhf(AntennaBuilder):
        default_params = MappingProxyType({"freq": 406.0})

        def build_wires(self):
            return [((0.0, 0.0, 1.0), (0.0, 0.0, 1.6), 15, 1.0)]

    # Fixed geometry (no design_freq): ONLY the synthetic band — the HF
    # tabs can't retune it, and keeping them would offer the trap back.
    (b,) = _make_example("uhf", Uhf, defer_hints=True).bands
    assert b.key == "406 MHz" and b.freq_mhz == 406.0
    assert b.min_mhz == pytest.approx(0.985 * 406.0)
    assert b.max_mhz == pytest.approx(1.015 * 406.0)

    class UhfWindow(Uhf):
        default_params = MappingProxyType(
            {
                "freq": 406.0,
                "ui_params": MappingProxyType({"meas_freq_range": (400.0, 412.0)}),
            }
        )

    # A deck-seeded measurement window that brackets the freq becomes the
    # band window (FR-card fidelity), instead of the generic ±1.5%.
    (b,) = _make_example("uhfw", UhfWindow, defer_hints=True).bands
    assert (b.min_mhz, b.max_mhz) == (400.0, 412.0)

    class UhfScaled(Uhf):
        default_params = MappingProxyType({"freq": 406.0, "design_freq": 406.0})

    # Retunable designs keep their list with the synthetic band appended,
    # so the HF tabs stay available for design_freq scaling.
    scaled = _make_example("uhfs", UhfScaled, defer_hints=True)
    assert scaled.bands[:-1] == DEFAULT_AMATEUR_BANDS
    assert scaled.bands[-1].freq_mhz == 406.0

    class Hf(Uhf):
        default_params = MappingProxyType({"freq": 14.1})

    # In-band designs are byte-identical: no synthetic band.
    assert _make_example("hf", Hf, defer_hints=True).bands == DEFAULT_AMATEUR_BANDS

    class Suppressed(Uhf):
        default_params = MappingProxyType(
            {"freq": 406.0, "ui_params": MappingProxyType({"bands": ()})}
        )

    # An explicit empty override still suppresses the band row entirely.
    assert _make_example("sup", Suppressed, defer_hints=True).bands == ()


def test_deferred_design_view_is_null_then_arrives_with_preview():
    # Regression: a deferred (user) design with no default_view override must
    # report default_view=None in the schema — NOT a hardcoded "xy" that makes
    # the camera snap to the wrong plane and then flip when the auto-detected
    # view arrives with the first geometry preview.
    from types import MappingProxyType

    from antennaknobs.web import adapter
    from antennaknobs.designs.dipoles.invvee import Builder as Inv

    ui = {
        k: v
        for k, v in dict(dict(Inv.default_params).get("ui_params") or {}).items()
        if k != "default_view"
    }
    dp = dict(Inv.default_params)
    dp["ui_params"] = MappingProxyType(ui)

    class NoView(Inv):
        default_params = MappingProxyType(dp)

    ex = adapter._make_example("user.noview", NoView, defer_hints=True)
    assert ex.default_view is None  # schema holds; camera stays put
    g = ex.momwire_geometry({})  # the builder runs here
    assert g["default_view"] in {"xy", "yz", "xz"}  # real view rides the preview


def test_geometry_endpoint_falls_back_when_geometry_unknown(client: TestClient):
    r = client.post("/geometry", json={"geometry": "does.not.exist"})
    assert r.status_code == 200
    out = r.json()
    # Falls back to the first registered example rather than erroring.
    assert "wires" in out and len(out["wires"]) >= 1


# ---------------------------------------------------------------------------
# _solve_z_only — pure helper inlined from converge's per-point loop.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# PyNEC paths — same endpoints, solver="pynec" branch. Each test runs one
# real NEC solve on dipole; sub-second on the CI box.
# ---------------------------------------------------------------------------


# Skip the whole PyNEC-path section when PyNEC didn't build (it's a hard
# dep on CI, but local devs without swig+gfortran shouldn't see a hard
# failure). pynec_backend.HAVE_PYNEC is the same flag the dispatcher uses.
pynec_required = pytest.mark.skipif(
    not __import__(
        "antennaknobs.web.pynec_backend", fromlist=["HAVE_PYNEC"]
    ).HAVE_PYNEC,
    reason="PyNEC not built in this environment",
)


@pynec_required
def test_solve_dispatches_to_pynec_when_requested():
    out = server.solve(
        {
            "geometry": "dipoles.invvee",
            "solver": "pynec",
            "measurement_freq_mhz": 28.47,
        }
    )
    assert out["geometry"] == "dipoles.invvee"
    assert "wires" in out
    # _attach_derived_em_fields + _compute_directivity_norm wrap both
    # solver branches; their outputs must show up regardless of which
    # backend ran.
    assert out["k_meas_m_inv"] > 0
    assert out["directivity_norm"] > 0
    # Real dipole at 14 MHz: real Z roughly order 73 Ω; very loose bound
    # so a future PyNEC version bump doesn't trip the test.
    assert 10 < out["z_in_re"] < 500


@pynec_required
def test_pynec_ground_on_solves_over_finite_ground():
    base = {
        "geometry": "dipoles.invvee",
        "solver": "pynec",
        "measurement_freq_mhz": 28.47,
    }
    free = server.solve(base)
    grounded = server.solve({**base, "ground": True, "ground_model": "sommerfeld"})
    default = server.solve({**base, "ground": True})
    # Sommerfeld is opt-in (expensive); a bare ground=True defaults to the
    # reflection-coefficient model.
    assert default["ground_model_applied"] == "refl-coef"
    # ground=True + sommerfeld routes PyNEC to the Sommerfeld finite ground
    # (εr=10, σ=0.002) rather than silently staying PEC/free, and the
    # response carries the real constants so the frontend's Fresnel cut
    # matches.
    assert grounded["ground"] is True
    assert grounded["ground_eps_r"] == 10.0
    assert grounded["ground_sigma"] == 0.002
    assert grounded["ground_eps_im"] < 0.0  # derived -σ/(ωε₀)
    # the solve actually felt the ground
    dz = abs(
        complex(grounded["z_in_re"], grounded["z_in_im"])
        - complex(free["z_in_re"], free["z_in_im"])
    )
    assert dz > 1.0
    # ground off keeps the PEC placeholder constants (unused by the frontend)
    assert free["ground_eps_r"] == pytest.approx(1.0e10)
    # pynec responses report what the solve used, like the momwire path
    assert grounded["ground_model_applied"] == "sommerfeld"
    assert free["ground_model_applied"] == "free"


@pynec_required
def test_pynec_ground_model_selects_pec_fast_or_sommerfeld():
    base = {
        "geometry": "dipoles.invvee",
        "solver": "pynec",
        "measurement_freq_mhz": 28.47,
        "ground": True,
    }
    somm = server.solve({**base, "ground_model": "sommerfeld"})
    fast = server.solve({**base, "ground_model": "fast"})
    fast_legacy = server.solve({**base, "ground_fast": True})
    pec = server.solve({**base, "ground_model": "pec"})
    # PEC keeps the placeholder constants (client-side Fresnel ρ→−1); finite
    # models ship the real ones.
    assert pec["ground_eps_r"] == pytest.approx(1.0e10)
    assert pec["ground_sigma"] == 0.0
    assert fast["ground_eps_r"] == 10.0
    # ground_model_applied names the model that ran (PyNEC honours the
    # request directly, so it mirrors ground_model here)
    assert somm["ground_model_applied"] == "sommerfeld"
    assert fast["ground_model_applied"] == "refl-coef"
    assert pec["ground_model_applied"] == "pec-image"
    # The legacy ground_fast boolean and ground_model="fast" are the same solve.
    assert fast_legacy["z_in_re"] == fast["z_in_re"]
    assert fast_legacy["z_in_im"] == fast["z_in_im"]
    # PEC differs measurably from Sommerfeld (~5 Ω on this dipole)...
    z_pec = complex(pec["z_in_re"], pec["z_in_im"])
    z_somm = complex(somm["z_in_re"], somm["z_in_im"])
    assert abs(z_pec - z_somm) > 2.0
    # ...and lands near momwire's PEC image solve (same physics, different
    # solver: ~6.1 Ω measured against the default BSpline d=2 mesh — the
    # retired triangular basis' even mesh happened to sit ~0.9 Ω away.
    # A sanity bound, not a convergence claim.
    momwire_pec = server.solve({**base, "solver": "momwire"})
    z_mom = complex(momwire_pec["z_in_re"], momwire_pec["z_in_im"])
    assert abs(z_pec - z_mom) < 8.0


@pynec_required
def test_sweep_endpoint_with_pynec_streams_per_point(client: TestClient):
    freqs = [28.0, 28.47, 29.0]
    r = client.post(
        "/sweep",
        json={
            "geometry": "dipoles.invvee",
            "solver": "pynec",
            "freqs_mhz": freqs,
            "measurement_freq_mhz": 28.47,
        },
    )
    assert r.status_code == 200
    recs = _ndjson_records(r.text)
    assert len(recs) == len(freqs) + 1
    *points, terminator = recs
    assert terminator == {"done": True, "solver": "pynec"}
    for f, rec in zip(freqs, points):
        assert rec["freq_mhz"] == f
        assert rec["solver"] == "pynec"
        assert isinstance(rec["z_re"], float) and isinstance(rec["z_im"], float)


@pynec_required
def test_pattern_endpoint_with_pynec_returns_full_grid(client: TestClient):
    # /pattern routes through pynec_backend.pattern → rp_card → gain
    # extraction. Asserts the grid shape the frontend reads (46 thetas
    # × 73 phis) is what comes back, and that all gains are finite
    # (NaN/Inf would imply a botched ex_card or fr_card sequence).
    r = client.post(
        "/pattern",
        json={
            "geometry": "dipoles.invvee",
            "solver": "pynec",
            "measurement_freq_mhz": 28.47,
        },
    )
    assert r.status_code == 200
    payload = r.json()
    assert payload["available"] is True
    assert payload["geometry"] == "dipoles.invvee"
    assert len(payload["theta_deg"]) == 46
    assert len(payload["phi_deg"]) == 73
    assert len(payload["gain_dbi"]) == 46
    assert len(payload["gain_dbi"][0]) == 73
    # NEC reports -999.99 dBi at radiation nulls as a sentinel — filter
    # those before bounds-checking. Anything outside (-200, 30) on the
    # non-null cells implies a malformed solve, not a real antenna.
    flat = [g for row in payload["gain_dbi"] for g in row]
    real_gains = [g for g in flat if g > -900]
    assert real_gains, "NEC returned no non-null gain cells"
    assert all(-200 < g < 30 for g in real_gains)
    # Peak gain for a half-wave dipole is ~2.15 dBi (in free space).
    # Loose ceiling guards against accidental dBW vs dBi mixups.
    assert max(real_gains) < 10


@pynec_required
def test_sweep_endpoint_pynec_empty_freqs_returns_only_done(client: TestClient):
    r = client.post(
        "/sweep",
        json={"geometry": "dipoles.invvee", "solver": "pynec", "freqs_mhz": []},
    )
    recs = _ndjson_records(r.text)
    assert recs == [{"done": True, "solver": "pynec"}]


# ---------------------------------------------------------------------------
# Multi-feed dispatch — adapter._auto_multi_feed sets multi_feed=True
# whenever a design's build_wires() declares >1 excitation. /solve and
# /sweep both light up the per-feed response shape for those designs.
# ---------------------------------------------------------------------------


def test_multi_feed_flag_lights_up_for_array_designs():
    # 16 designs in the registry have >1 feed wire; all should be flagged
    # after the auto-detect lands. Pin a few canonical names so a future
    # refactor that drops the auto-detect path gets caught.
    ex = server.EXAMPLES["arrays.bowtiearray1x2"]
    assert ex.multi_feed is True
    assert server.EXAMPLES["arrays.invveearray"].multi_feed is True
    assert server.EXAMPLES["dipoles.invvee"].multi_feed is False


def test_solve_for_multi_feed_geometry_includes_feeds_array():
    out = server.solve(
        {
            "geometry": "arrays.bowtiearray1x2",
            "measurement_freq_mhz": 28.5,
            "momwire_model": "bspline",
        }
    )
    assert "feeds" in out
    assert len(out["feeds"]) == 2  # bowtiearray1x2 has two driven elements
    for f in out["feeds"]:
        assert set(f) == {"z_re", "z_im", "v_re", "v_im"}
        assert isinstance(f["z_re"], float)
        assert isinstance(f["v_re"], float)
    # Primary z_in_re must match feeds[0].z_re — the primary impedance
    # field has always been a duplicate of the first feed.
    assert out["z_in_re"] == pytest.approx(out["feeds"][0]["z_re"])
    assert out["z_in_im"] == pytest.approx(out["feeds"][0]["z_im"])


def test_solve_for_single_feed_geometry_omits_feeds_array():
    out = server.solve(
        {
            "geometry": "dipoles.invvee",
            "measurement_freq_mhz": 28.47,
            "momwire_model": "bspline",
        }
    )
    assert "feeds" not in out


@pytest.mark.parametrize(
    "design_module,expected_z0",
    [
        ("dipoles.invvee", 50.0),
        ("dipoles.dipole_turnstile", 50.0),  # 2 feeds but not Array*
        ("arrays.bowtiearray1x2", 100.0),
        ("arrays.delta_looparray", 100.0),
        ("arrays.hentenna_array", 100.0),
        ("arrays.hourglass_array", 100.0),
        ("arrays.bowtiearray", 200.0),
        ("arrays.invveearray", 200.0),
        ("arrays.delta_looparray_2x2", 200.0),
        ("arrays.moxonarray", 200.0),
        ("arrays.yagiarray", 200.0),
        ("arrays.delta_looparray_1x4", 200.0),
        ("arrays.delta_looparray_1x4_grouped", 200.0),
        ("arrays.bowtiearray2x4", 400.0),
    ],
)
def test_auto_target_z0_scales_by_array_class(design_module, expected_z0):
    # Auto-detect: Array1x2 → 100, Array2x2 → 200, Array2x4 → 400,
    # Array1x4 → 200. Non-array designs (dipole, turnstiles) stay at
    # 50. Pure-function check on _auto_target_z0 — no solver needed.
    import importlib

    from antennaknobs.web.adapter import _auto_target_z0

    cls = importlib.import_module(f"antennaknobs.designs.{design_module}").Builder
    assert _auto_target_z0(cls) == expected_z0


def test_solve_response_carries_z0_ohms_for_array_design():
    # End-to-end: the auto-derived target_z0 actually surfaces on the
    # solve response (where the frontend's SWR readout picks it up).
    out = server.solve(
        {
            "geometry": "arrays.bowtiearray1x2",
            "measurement_freq_mhz": 28.5,
            "momwire_model": "bspline",
        }
    )
    assert out["z0_ohms"] == 100.0


def test_geometry_preview_carries_default_backend(client: TestClient):
    # The frontend seeds its solver from the preview's default_backend (and
    # then fires the first solve), so the recommendation must ride on the
    # /geometry response — array-block for a grid array, None otherwise.
    arr = client.post("/geometry", json={"geometry": "arrays.bowtiearray2x4"}).json()
    assert arr["default_backend"] == "arrayblock"
    dip = client.post("/geometry", json={"geometry": "dipoles.invvee"}).json()
    assert dip["default_backend"] is None


def test_phase_param_slider_range_spans_full_unit_circle():
    # phase_lr / phase_tb default to 0.0; without the adapter's
    # phase_*-name special case the auto-derive falls back to (-1, 1)
    # for default=0, which is a useless 2° span. Confirm the unit-circle
    # default kicks in instead.
    import importlib

    schema = importlib.import_module(
        "antennaknobs.designs.arrays.bowtiearray"
    ).Builder.default_params
    assert "phase_lr" in schema and "phase_tb" in schema

    by_name = {s.name: s for s in REGISTRY["arrays.bowtiearray"].param_schema}
    lr = by_name["phase_lr"]
    assert (lr.min, lr.max, lr.step) == (-180.0, 180.0, 1.0)
    assert lr.unit == "°"
    assert lr.precision == 0


def test_phase_lr_drives_per_feed_voltage_phasor():
    # bowtiearray1x2 already tests this through flat_wires_to_polylines;
    # this is the end-to-end check that /solve's feeds[i].v_re/v_im
    # actually reflect the phase_lr setting.
    out_zero = server.solve(
        {
            "geometry": "arrays.bowtiearray1x2",
            "measurement_freq_mhz": 28.5,
            "momwire_model": "bspline",
            "phase_lr": 0.0,
        }
    )
    out_quad = server.solve(
        {
            "geometry": "arrays.bowtiearray1x2",
            "measurement_freq_mhz": 28.5,
            "momwire_model": "bspline",
            "phase_lr": 90.0,
        }
    )
    # phase_lr=0: both feed voltages are real (V0 = V1 = 1+0j).
    f0_zero, f1_zero = out_zero["feeds"]
    assert f0_zero["v_re"] == pytest.approx(1.0)
    assert f0_zero["v_im"] == pytest.approx(0.0)
    assert f1_zero["v_re"] == pytest.approx(1.0)
    assert f1_zero["v_im"] == pytest.approx(0.0)
    # phase_lr=90: V0 = 1+0j, V1 = j (0 + 1j).
    f0_q, f1_q = out_quad["feeds"]
    assert f0_q["v_re"] == pytest.approx(1.0)
    assert f0_q["v_im"] == pytest.approx(0.0)
    assert f1_q["v_re"] == pytest.approx(0.0, abs=1e-10)
    assert f1_q["v_im"] == pytest.approx(1.0)


def test_sweep_endpoint_streams_feeds_z_for_multi_feed_geometry(client: TestClient):
    r = client.post(
        "/sweep",
        json={
            "geometry": "arrays.bowtiearray1x2",
            "freqs_mhz": [28.4, 28.5],
            "momwire_model": "bspline",
        },
    )
    assert r.status_code == 200
    recs = _ndjson_records(r.text)
    *points, terminator = recs
    assert terminator == {"done": True, "solver": "momwire"}
    for rec in points:
        assert "feeds_z_re" in rec
        assert "feeds_z_im" in rec
        assert len(rec["feeds_z_re"]) == 2
        assert len(rec["feeds_z_im"]) == 2
        # Primary z must mirror feed 0 — same invariant as /solve.
        assert rec["z_re"] == pytest.approx(rec["feeds_z_re"][0])


# ---------------------------------------------------------------------------
# /ws — websocket endpoint. TestClient.websocket_connect gives a synchronous
# context manager around the live route.
# ---------------------------------------------------------------------------


def test_ws_endpoint_round_trips_a_solve(client: TestClient):
    with client.websocket_connect("/ws") as ws:
        ws.send_text(
            __import__("json").dumps(
                {
                    "geometry": "dipoles.invvee",
                    "measurement_freq_mhz": 28.47,
                    "momwire_model": "bspline",
                }
            )
        )
        result = __import__("json").loads(ws.receive_text())
    assert result["solver"] == "momwire"
    assert result["geometry"] == "dipoles.invvee"
    assert "wires" in result
    assert result["z_in_re"] > 0


def test_ws_endpoint_handles_multiple_requests_on_one_socket(client: TestClient):
    # The endpoint's outer `while True` loop must keep serving once the
    # first solve returns; the React frontend reuses the same socket
    # for every slider drag.
    req = __import__("json").dumps(
        {
            "geometry": "dipoles.invvee",
            "measurement_freq_mhz": 28.47,
            "momwire_model": "bspline",
        }
    )
    with client.websocket_connect("/ws") as ws:
        ws.send_text(req)
        first = __import__("json").loads(ws.receive_text())
        ws.send_text(req)
        second = __import__("json").loads(ws.receive_text())
    assert first["geometry"] == "dipoles.invvee"
    assert second["geometry"] == "dipoles.invvee"
    # Same request → deterministic same z_in.
    assert first["z_in_re"] == pytest.approx(second["z_in_re"])
    assert first["z_in_im"] == pytest.approx(second["z_in_im"])


def test_ws_endpoint_returns_cleanly_on_client_disconnect(client: TestClient):
    # Opening + closing the socket without sending anything has to hit
    # the outer WebSocketDisconnect path (receive_text raises). The
    # endpoint must catch it cleanly — no exception leaking out of the
    # context manager.
    with client.websocket_connect("/ws"):
        pass  # context exit closes the socket


_BROKEN_USER_DESIGN = """
from types import MappingProxyType
from antennaknobs import AntennaBuilder

class Builder(AntennaBuilder):
    default_params = MappingProxyType({"freq": 14.0})

    def build_wires(self):
        return 1 / 0  # ZeroDivisionError when geometry is built
"""


@pytest.fixture
def broken_user_design():
    """Install a user design that loads fine but raises in build_wires, so it
    registers (geometry is deferred) yet fails on the first solve/geometry."""
    d = user_designs.default_user_dir()
    d.mkdir(parents=True, exist_ok=True)
    f = d / "wsboom.py"
    f.write_text(_BROKEN_USER_DESIGN)
    user_designs.refresh()
    yield "user.wsboom"
    f.unlink(missing_ok=True)
    user_designs.refresh()
    for k in [k for k in REGISTRY if k.startswith("user.")]:
        del REGISTRY[k]


def test_geometry_endpoint_surfaces_build_error(client, broken_user_design):
    # A deferred user design that raises in build_wires fails at selection, not
    # at load. /geometry must return the cause (200, not 500) so the frontend
    # can show it instead of a blank stage.
    r = client.post("/geometry", json={"geometry": broken_user_design})
    assert r.status_code == 200
    body = r.json()
    assert "ZeroDivisionError" in body["error"]
    assert "wsboom.py" in body["error"]


def test_ws_solve_error_keeps_socket_alive(client, broken_user_design):
    # A solve that raises must surface as an error frame, NOT tear down the
    # socket — otherwise every subsequent slider-driven solve is lost.
    with client.websocket_connect("/ws") as ws:
        ws.send_text(__import__("json").dumps({"geometry": broken_user_design}))
        bad = __import__("json").loads(ws.receive_text())
        assert "ZeroDivisionError" in bad["error"]
        # Same socket still serves a healthy design.
        ws.send_text(__import__("json").dumps({"geometry": "dipoles.invvee"}))
        good = __import__("json").loads(ws.receive_text())
    assert good["geometry"] == "dipoles.invvee"
    assert "wires" in good


def test_ws_endpoint_echoes_seq_on_success(client: TestClient):
    # The latest-wins protocol keys ordering, RTT accounting, and solving-state
    # off the echoed `_seq`; every successful response must carry the request's.
    with client.websocket_connect("/ws") as ws:
        ws.send_text(
            json.dumps(
                {
                    "geometry": "dipoles.invvee",
                    "measurement_freq_mhz": 28.47,
                    "momwire_model": "bspline",
                    "_seq": 7,
                }
            )
        )
        result = json.loads(ws.receive_text())
    assert result["_seq"] == 7
    assert result["geometry"] == "dipoles.invvee"


def test_ws_endpoint_echoes_seq_on_error(client, broken_user_design):
    # The error path must echo `_seq` too — a dropped echo here would leave the
    # client's `solving` state stuck true forever when the newest request fails.
    with client.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps({"geometry": broken_user_design, "_seq": 42}))
        bad = json.loads(ws.receive_text())
    assert "error" in bad
    assert bad["_seq"] == 42


def test_ws_endpoint_squashes_and_skips_superseded(client, monkeypatch):
    # Latest-wins: while the first solve is held, a burst of newer requests
    # collapses in the size-1 mailbox to only the freshest. The held solve is
    # then superseded, so its send is skipped and only the newest result ships.
    seqs_solved: list[int] = []
    entered = threading.Event()
    release = threading.Event()
    reader_saw_last = threading.Event()

    def blocking_solve(req: dict, cancel=None) -> dict:
        seq = req.get("_seq")
        seqs_solved.append(seq)
        if seq == 1:
            entered.set()
            # Hold until the reader has drained the whole burst into the mailbox,
            # so this solve returns to find itself superseded (deterministic).
            release.wait(5)
        return {"geometry": req.get("geometry"), "z_in_re": 1.0}

    real_loads = json.loads

    def recording_loads(s):
        d = real_loads(s)
        if isinstance(d, dict) and d.get("_seq") == 5:
            reader_saw_last.set()
        return d

    monkeypatch.setattr(server, "solve", blocking_solve)
    monkeypatch.setattr(server.json, "loads", recording_loads)

    with client.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps({"geometry": "dipoles.invvee", "_seq": 1}))
        assert entered.wait(5), "first solve never started"
        for s in (2, 3, 4, 5):
            ws.send_text(json.dumps({"geometry": "dipoles.invvee", "_seq": s}))
        # Wait until the reader has consumed seq 5 (mailbox == [seq 5]) before
        # releasing, so seq 2..4 are provably squashed, never solved.
        assert reader_saw_last.wait(5), "reader never drained the burst"
        release.set()
        first = json.loads(ws.receive_text())

    # Only seq 1 and seq 5 ever reach solve(); 2..4 die in the mailbox.
    assert seqs_solved == [1, 5]
    # seq 1's result is superseded → skipped; seq 5 is the only thing sent.
    assert first["_seq"] == 5


def test_ws_endpoint_handles_disconnect_during_solve(client, monkeypatch):
    # Client drops mid-solve: the reader sees WebSocketDisconnect, the held
    # solve later returns to a closed socket, and the handler exits cleanly with
    # the reader task cancelled — no stray exception out of the context manager.
    entered = threading.Event()
    release = threading.Event()

    def blocking_solve(req: dict, cancel=None) -> dict:
        entered.set()
        release.wait(5)
        return {"geometry": req.get("geometry")}

    monkeypatch.setattr(server, "solve", blocking_solve)

    with client.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps({"geometry": "dipoles.invvee", "_seq": 1}))
        assert entered.wait(5), "solve never started"
        # Release shortly after the context exit disconnects the socket, so the
        # handler can finish its in-flight solve and return without deadlocking
        # the close handshake.
        threading.Timer(0.2, release.set).start()
    release.set()  # belt-and-suspenders if the timer hasn't fired yet


def test_ws_preempts_inflight_solve_on_supersede(client, monkeypatch):
    # Phase 3: a newer request must PREEMPT the in-flight solve. The handler
    # publishes a cancel token and the reader trips it the moment seq 2 lands;
    # the in-flight solve observes it, raises SolveAborted, its doomed response
    # is never sent, and only the superseding result ships.
    entered = threading.Event()
    aborted_seqs: list[int] = []
    completed_seqs: list[int] = []

    def cancellable_solve(req: dict, cancel=None) -> dict:
        seq = req.get("_seq")
        if seq == 1:
            entered.set()
            # Block until the reader trips our token (when seq 2 arrives), then
            # abort cooperatively — exactly what a real solve's checkpoint does.
            for _ in range(500):
                if cancel is not None and cancel.cancelled:
                    aborted_seqs.append(seq)
                    raise momwire.SolveAborted()
                time.sleep(0.01)
        completed_seqs.append(seq)
        return {"geometry": req.get("geometry"), "z_in_re": 1.0}

    monkeypatch.setattr(server, "solve", cancellable_solve)

    with client.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps({"geometry": "dipoles.invvee", "_seq": 1}))
        assert entered.wait(5), "first solve never started"
        ws.send_text(json.dumps({"geometry": "dipoles.invvee", "_seq": 2}))
        resp = json.loads(ws.receive_text())

    assert aborted_seqs == [1], "the in-flight solve was not preempted"
    assert 1 not in completed_seqs, "an aborted solve must not complete"
    assert resp["_seq"] == 2, "only the superseding result should ship"


def test_solve_aborted_propagates_uncached(monkeypatch):
    # A SolveAborted from the miss path must propagate to the caller (so the /ws
    # handler can `continue`) and never be stored in the solve cache.
    server._SOLVE_CACHE.clear()
    req = {
        "geometry": "dipoles.invvee",
        "solver": "momwire",
        "momwire_model": "bspline",
        "_seq": 7,
    }
    token = momwire.CancelToken()
    token.cancel()
    with pytest.raises(momwire.SolveAborted):
        server.solve(req, cancel=token)
    assert len(server._SOLVE_CACHE) == 0, "an aborted solve must not be cached"


def test_solve_z_only_returns_primary_z_and_no_feeds_for_dipole():
    z, feeds_z = server._solve_z_only(
        {
            "geometry": "dipoles.invvee",
            "measurement_freq_mhz": 28.47,
            "momwire_model": "bspline",
        }
    )
    assert isinstance(z, complex)
    assert z.real > 0  # real-input dipole has positive real Z
    assert feeds_z is None  # single-feed


def test_compute_directivity_norm_ground_on_stays_finite_and_positive():
    # With ground=True the integration domain halves and a reflected
    # image contribution is added; the resulting norm has to stay finite
    # and positive. (The exact ground/no-ground ratio depends on source
    # geometry and isn't a clean closed form.)
    with_ground = _hertzian_dipole_response()
    with_ground["ground"] = True
    # PEC ground: real Fresnel code path takes complex eps_r + j*eps_im.
    with_ground["ground_eps_r"] = 1.0e10
    with_ground["ground_sigma"] = 0.0
    server._attach_derived_em_fields(with_ground)
    server._compute_directivity_norm(with_ground, n_theta=15, n_phi=30)
    assert with_ground["directivity_norm"] > 0
    assert np.isfinite(with_ground["directivity_norm"])


# ---------------------------------------------------------------------------
# Cache-key allowlist tests
#
# The /ws live-tick cache in server.solve() hashes the request to skip
# repeat solves. Two correctness hazards:
#
#  (a) A new field is added to the request that DOES affect the physics,
#      but it isn't reflected in the key — the cache silently returns a
#      stale answer.
#  (b) A new field is added that does NOT affect the physics (a UI-only
#      hint, a client timestamp) — the key changes on every tick and the
#      cache effectively never hits.
#
# These tests pin a representative request and explicitly enumerate which
# fields are "physical" (must influence the key) vs "ignored" (must not).
# When a new field shows up that isn't in either list, the test fails
# with a message telling the author exactly what to do.
# ---------------------------------------------------------------------------


# Representative live request — the shape the React client posts on the
# /ws socket for an interactive solve. Update this when the frontend
# request shape changes; that update is the cue to also revisit the
# physical/ignored split below.
_CANONICAL_REQ = {
    "geometry": "multiband.fandipole",
    "solver": "momwire",
    "momwire_model": "bspline",
    "model_options": {
        "degree": 2,
        "use_singular_enrichment": True,
        "enrichment_variant": "auto",
        "tikhonov_lambda": 1e-3,
    },
    "wire_radius": 0.0005,
    "ground": False,
    "n_per_wire": 21,
    "variant": None,
    "design_freq_mhz": 14.300,
    "measurement_freq_mhz": 14.300,
    "params": {},
    # A representative builder param the adapter pulls from the top level.
    "base": 7.0,
    "angle_deg": 0.5,
    "n_bands": 5,
}

# Top-level fields known to influence the solve numerics. Each MUST cause
# the canonical key to change when perturbed.
_PHYSICAL_FIELDS = frozenset(
    {
        "geometry",
        "solver",
        "momwire_model",
        "model_options",
        "wire_radius",
        "ground",
        "n_per_wire",
        "variant",
        "design_freq_mhz",
        "measurement_freq_mhz",
        "params",
        "base",
        "angle_deg",
        "n_bands",
    }
)

# Top-level fields known NOT to influence the solve numerics. Adding any
# of these to the request MUST NOT change the canonical key — otherwise
# every tick is a cache miss. Members must also be in server's
# _CACHE_KEY_BLOCKLIST.
_IGNORED_FIELDS = frozenset(
    {
        "_request_id",
        "_client_ts",
        "_seq",
    }
)


def test_cache_key_field_coverage_is_exhaustive():
    """The canonical request's top-level keys must be fully classified.

    If this fails, the canonical request has grown a field that isn't
    declared physical or ignored. Pick one:

      - If the field changes the physics, add it to _PHYSICAL_FIELDS
        (it's already in the key via the catch-all hash; this just makes
        intent explicit and gives the perturbation test something to
        verify).
      - If the field is UI-only (timestamps, render hints, client ids),
        add it to _IGNORED_FIELDS *and* to server._CACHE_KEY_BLOCKLIST,
        otherwise it will torch the cache hit rate.
    """
    seen = set(_CANONICAL_REQ.keys())
    classified = _PHYSICAL_FIELDS | _IGNORED_FIELDS
    unclassified = seen - classified
    stale = (
        classified - seen - _IGNORED_FIELDS
    )  # ignored fields don't have to be in canonical
    assert not unclassified, (
        f"unclassified request fields in canonical request: {sorted(unclassified)}. "
        f"Add each to _PHYSICAL_FIELDS or _IGNORED_FIELDS (and _CACHE_KEY_BLOCKLIST)."
    )
    assert not stale, (
        f"fields declared physical but missing from canonical request: {sorted(stale)}. "
        f"Either remove from _PHYSICAL_FIELDS or add to _CANONICAL_REQ."
    )


def test_cache_key_blocklist_matches_ignored_fields():
    """Ignored fields must also be in server._CACHE_KEY_BLOCKLIST.

    Otherwise the blocklist is a lie: a field declared ignored here would
    still be hashed into the key in production.
    """
    missing = _IGNORED_FIELDS - server._CACHE_KEY_BLOCKLIST
    assert not missing, (
        f"fields in _IGNORED_FIELDS but not in server._CACHE_KEY_BLOCKLIST: "
        f"{sorted(missing)}. Add them to server._CACHE_KEY_BLOCKLIST so the "
        f"canonical-key builder actually strips them."
    )


@pytest.mark.parametrize("field", sorted(_PHYSICAL_FIELDS))
def test_cache_key_changes_when_physical_field_perturbed(field):
    """Perturbing a physical field MUST change the canonical key.

    If this fails on field X, the canonicalizer is dropping X — either it
    was added to _CACHE_KEY_BLOCKLIST by mistake, or the hashing function
    isn't reaching it (e.g. lives inside a non-dict / non-list container
    that quantise() doesn't recurse into).
    """
    base_key = server._canonical_solve_key(_CANONICAL_REQ)
    perturbed = dict(_CANONICAL_REQ)
    v = perturbed[field]
    if isinstance(v, bool):
        perturbed[field] = not v
    elif isinstance(v, (int, float)):
        perturbed[field] = v + 1
    elif isinstance(v, str):
        perturbed[field] = v + "_x"
    elif isinstance(v, dict):
        perturbed[field] = {**v, "__probe__": 999}
    elif v is None:
        perturbed[field] = "non_none"
    else:
        perturbed[field] = ("__probe__", v)
    new_key = server._canonical_solve_key(perturbed)
    assert new_key != base_key, (
        f"perturbing physical field {field!r} did NOT change the cache key. "
        f"The canonicalizer is failing to capture this field; cache will return "
        f"stale results when {field!r} changes between calls."
    )


@pytest.mark.parametrize("field", sorted(_IGNORED_FIELDS))
def test_cache_key_unchanged_when_ignored_field_added(field):
    """Adding an ignored field MUST NOT change the canonical key.

    If this fails on field X, X is in _IGNORED_FIELDS but server's
    blocklist isn't stripping it — every request that carries X will
    miss the cache. Add X to server._CACHE_KEY_BLOCKLIST.
    """
    base_key = server._canonical_solve_key(_CANONICAL_REQ)
    with_field = dict(_CANONICAL_REQ)
    with_field[field] = "anything"
    assert server._canonical_solve_key(with_field) == base_key, (
        f"adding ignored field {field!r} changed the cache key — the blocklist "
        f"is not stripping it. Add {field!r} to server._CACHE_KEY_BLOCKLIST."
    )


def test_cache_key_quantises_floats_below_step():
    """Floats within _CACHE_FLOAT_QUANT must collapse to the same key.

    Slider positions are coarser than this quant; without quantisation,
    back-and-forth scrubs to nominally-identical values would miss.
    """
    base = dict(_CANONICAL_REQ)
    nudged = dict(_CANONICAL_REQ)
    nudged["design_freq_mhz"] = (
        base["design_freq_mhz"] + server._CACHE_FLOAT_QUANT * 0.1
    )
    assert server._canonical_solve_key(base) == server._canonical_solve_key(nudged)


def test_cache_key_recurses_into_model_options():
    """Sanity: per-solver kwargs inside model_options must contribute to
    the key. Otherwise switching bspline degrees or toggling singular
    enrichment via model_options.use_singular_enrichment would return
    a stale answer."""
    base_key = server._canonical_solve_key(_CANONICAL_REQ)
    for k, alt in [
        ("degree", 1),
        ("use_singular_enrichment", False),
        ("enrichment_variant", "off"),
        ("tikhonov_lambda", 1e-2),
    ]:
        mutant = dict(_CANONICAL_REQ)
        mutant["model_options"] = {**_CANONICAL_REQ["model_options"], k: alt}
        assert server._canonical_solve_key(mutant) != base_key, (
            f"model_options.{k} change did not alter the cache key"
        )


# ---------------------------------------------------------------------------
# Live-engine size guard (_check_solve_size). A solve's matrix dimension N ≈ the
# total wire-segment count; the dense solvers (and PyNEC) form an N×N matrix, so
# an oversized N must be rejected *before* any matrix fill. The guard is OFF by
# default (local installs are unlocked) and only enforced when ANTENNAKNOBS_HOSTED
# is set — which the tests below force via monkeypatch. The cap is engine-aware:
# the compressed engines (arrayblock/hmatrix) skip the dense matrix and get a
# higher cap.
# ---------------------------------------------------------------------------


@pytest.fixture
def hosted(monkeypatch):
    """Force the hosted size-guard on for a test (it's off by default)."""
    monkeypatch.setattr(server, "_HOSTED", True)


def _n_per_wire_for_basis(geom: str, target_basis: int) -> int:
    """An n_per_wire that yields roughly ``target_basis`` segments for ``geom``
    (basis scales ~linearly with n_per_wire), so the test is robust to the exact
    cap values."""
    k = REGISTRY[geom].count_basis({"geometry": geom, "n_per_wire": 100}) / 100.0
    return max(1, round(target_basis / k))


def test_count_basis_scales_with_segments():
    ex = REGISTRY["dipoles.invvee"]
    small = ex.count_basis({"geometry": "dipoles.invvee", "n_per_wire": 20})
    big = ex.count_basis({"geometry": "dipoles.invvee", "n_per_wire": 200})
    assert small is not None and big is not None
    assert big > small  # more segments per wire → larger MoM system


def test_size_guard_disabled_by_default_local_is_unlocked():
    # With ANTENNAKNOBS_HOSTED unset (the default), even an absurd N is allowed —
    # a local `pip install` instance is uncapped.
    server._check_solve_size(
        {
            "geometry": "dipoles.invvee",
            "n_per_wire": server._MAX_BASIS * 100,
            "momwire_model": "bspline",
        },
        use_pynec=False,
    )


def test_check_solve_size_passes_for_normal_request(hosted):
    # A modest segment count is well under every cap → no rejection.
    server._check_solve_size(
        {"geometry": "dipoles.invvee", "n_per_wire": 40, "momwire_model": "bspline"},
        use_pynec=False,
    )


def test_check_solve_size_rejects_oversized_dense_but_allows_compressed(hosted):
    geom = "dipoles.invvee"
    # Aim the segment count between the dense and compressed caps so the dense
    # engine rejects but the compressed one (higher cap) accepts.
    target = (server._MAX_BASIS + server._MAX_BASIS_COMPRESSED) // 2
    req = {
        "geometry": geom,
        "n_per_wire": _n_per_wire_for_basis(geom, target),
        "momwire_model": "bspline",
    }
    basis = REGISTRY[geom].count_basis(req)
    assert server._MAX_BASIS < basis <= server._MAX_BASIS_COMPRESSED, (
        "test premise: basis must land between the dense and compressed caps"
    )

    # Dense engine rejects with a clear, actionable message.
    with pytest.raises(server.SolveTooLargeError) as excinfo:
        server._check_solve_size(req, use_pynec=False)
    assert "segments / wire" in str(excinfo.value)

    # The same N on a compressed engine is accepted (no dense matrix).
    server._check_solve_size({**req, "momwire_model": "arrayblock"}, use_pynec=False)


def test_solve_rejects_oversized_request_before_filling_matrix(hosted):
    # The full solve() path raises the size error cheaply (geometry-only count,
    # no expensive matrix fill).
    with pytest.raises(server.SolveTooLargeError):
        server.solve(
            {
                "geometry": "dipoles.invvee",
                "n_per_wire": _n_per_wire_for_basis("dipoles.invvee", server._MAX_BASIS)
                * 2,
                "momwire_model": "bspline",
            }
        )


def test_check_solve_size_unknown_geometry_does_not_falsely_reject(hosted):
    # Unbuildable / unknown geometry → count unavailable → guard defers to the
    # normal solve path instead of raising a spurious size error.
    server._check_solve_size(
        {"geometry": "does.not.exist", "n_per_wire": 999999}, use_pynec=False
    )


# ---------------------------------------------------------------------------
# Size guard on every solve-forming endpoint (issue #345). /ws and /converge
# always had it; /sweep, /optimize, /pattern_metrics, and /pattern each form
# the same N×N matrix and must reject an over-cap request instead of
# attempting the allocation.
# ---------------------------------------------------------------------------


def _oversized_req(**extra) -> dict:
    n = _n_per_wire_for_basis("dipoles.invvee", server._MAX_BASIS) * 2
    return {
        "geometry": "dipoles.invvee",
        "n_per_wire": n,
        "momwire_model": "bspline",
        **extra,
    }


def test_sweep_rejects_oversized_request_when_hosted(hosted, client):
    resp = client.post("/sweep", json=_oversized_req(freqs_mhz=[14.1]))
    assert resp.status_code == 413
    assert "segments / wire" in resp.json()["detail"]


def test_optimize_rejects_oversized_request_when_hosted(hosted, client):
    req = _oversized_req(
        optimize={
            "free": [{"name": "length_factor", "min": 0.9, "max": 1.1}],
            "objective": "swr",
        }
    )
    resp = client.post("/optimize", json=req)
    assert resp.status_code == 200  # error payload, not an exception
    assert "segments / wire" in resp.json()["error"]


def test_pattern_metrics_rejects_oversized_request_when_hosted(hosted, client):
    resp = client.post("/pattern_metrics", json=_oversized_req())
    assert resp.status_code == 200
    assert "segments / wire" in resp.json()["error"]


@pytest.mark.skipif(not server.pynec_backend.HAVE_PYNEC, reason="PyNEC not installed")
def test_pattern_rejects_oversized_request_when_hosted(hosted, client):
    resp = client.post("/pattern", json=_oversized_req(solver="pynec"))
    body = resp.json()
    assert body["available"] is False
    assert "segments / wire" in body["error"]


# ---------------------------------------------------------------------------
# Hosted compute levers (issue #346): list lengths, optimizer eval budget, and
# solver kwargs are clamped/whitelisted when hosted so an under-cap request
# can't multiply whole solves without bound.
# ---------------------------------------------------------------------------


def test_sweep_rejects_over_length_freq_list_when_hosted(hosted, client):
    freqs = [14.0 + i * 1e-4 for i in range(server._MAX_SWEEP_POINTS + 1)]
    resp = client.post(
        "/sweep",
        json={"geometry": "dipoles.invvee", "n_per_wire": 5, "freqs_mhz": freqs},
    )
    assert resp.status_code == 413
    assert "limit" in resp.json()["detail"]


def test_converge_rejects_over_length_n_values_when_hosted(hosted, client):
    n_values = list(range(5, 5 + server._MAX_SWEEP_POINTS + 1))
    resp = client.post(
        "/converge",
        json={"geometry": "dipoles.invvee", "n_values": n_values},
    )
    assert resp.status_code == 413


def test_optimize_max_evals_clamped_when_hosted(hosted, client, monkeypatch):
    # A tiny ceiling keeps the test fast while proving the client value can't
    # override it: the optimizer's own evals stop at the clamp, plus the two
    # bookend solves (x0 before, best-point after) optimize() always runs.
    monkeypatch.setattr(server, "_MAX_OPT_EVALS", 3)
    req = {
        "geometry": "dipoles.invvee",
        "n_per_wire": 7,
        "momwire_model": "bspline",
        "optimize": {
            "free": [{"name": "length_factor", "min": 0.95, "max": 1.05}],
            "objective": "swr",
            "max_evals": 10**9,
        },
    }
    body = client.post("/optimize", json=req).json()
    assert "error" not in body
    assert body["n_evals"] <= 3 + 2


def test_optimize_non_numeric_max_evals_is_clean_error(client):
    req = {
        "geometry": "dipoles.invvee",
        "optimize": {
            "free": [{"name": "length_factor", "min": 0.95, "max": 1.05}],
            "max_evals": "lots",
        },
    }
    body = client.post("/optimize", json=req).json()
    assert "max_evals" in body["error"]


def test_sweep_non_dict_model_options_is_422(client):
    resp = client.post(
        "/sweep",
        json={
            "geometry": "dipoles.invvee",
            "freqs_mhz": [14.0],
            "model_options": "junk",
        },
    )
    assert resp.status_code == 422
    assert "model_options" in resp.json()["detail"]


def test_hosted_model_options_filtered_to_whitelist(monkeypatch):
    from antennaknobs.web import adapter

    monkeypatch.setattr(adapter, "_HOSTED", True)
    out = adapter.sanitize_model_options(
        {
            "model_options": {
                "degree": 1,
                "use_singular_enrichment": False,
                # Internal compute-amplification levers: dropped, not forwarded.
                "aca_leaf_size": 2,
                "solve_tol": 1e-15,
                "swept_mem_mb": 10**6,
            }
        }
    )
    assert out == {"degree": 1, "use_singular_enrichment": False}

    with pytest.raises(ValueError, match="degree"):
        adapter.sanitize_model_options({"model_options": {"degree": 7}})
    with pytest.raises(ValueError, match="tikhonov_lambda"):
        adapter.sanitize_model_options(
            {"model_options": {"tikhonov_lambda": float("inf")}}
        )


def test_local_model_options_forward_verbatim():
    from antennaknobs.web import adapter

    assert adapter.sanitize_model_options({"model_options": {"anything_goes": 1}}) == {
        "anything_goes": 1
    }
    with pytest.raises(ValueError):  # non-dict is a clean error even locally
        adapter.sanitize_model_options({"model_options": "junk"})


# ---------------------------------------------------------------------------
# Numeric input validation at the physics boundary (issue #347). stdlib json
# accepts NaN/Infinity literals and nothing floored the physics inputs, so a
# zero/non-finite freq or radius reached the solver as a ZeroDivisionError /
# NaN matrix. /geometry exercises the same _build_builder + engine path as the
# solves, without the cost of one.
# ---------------------------------------------------------------------------


def _post_raw(client, path: str, payload: dict):
    # stdlib json.dumps emits bare NaN/Infinity literals (allow_nan=True is
    # the default) — the exact wire form the attack uses; httpx's json= kwarg
    # refuses to serialize them.
    return client.post(
        path,
        content=json.dumps(payload),
        headers={"content-type": "application/json"},
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("design_freq_mhz", 0),
        ("design_freq_mhz", float("nan")),
        ("measurement_freq_mhz", float("inf")),
        ("wire_radius", 0),
        ("wire_radius", -0.001),
    ],
)
def test_geometry_rejects_bad_physics_scalar(client, field, value):
    resp = _post_raw(client, "/geometry", {"geometry": "dipoles.invvee", field: value})
    assert resp.status_code == 200  # error payload for the UI banner, not a 500
    body = resp.json()
    assert field in body["error"]
    assert "positive, finite" in body["error"]


def test_geometry_rejects_non_finite_knob_value(client):
    resp = _post_raw(
        client,
        "/geometry",
        {"geometry": "dipoles.invvee", "length_factor": float("nan")},
    )
    assert "length_factor" in resp.json()["error"]


def test_geometry_rejects_non_positive_n_per_wire(client):
    resp = client.post(
        "/geometry", json={"geometry": "dipoles.invvee", "n_per_wire": 0}
    )
    assert "n_per_wire" in resp.json()["error"]


def test_sweep_rejects_non_finite_freqs(client):
    resp = _post_raw(
        client,
        "/sweep",
        {"geometry": "dipoles.invvee", "freqs_mhz": [14.0, float("nan")]},
    )
    assert resp.status_code == 422
    resp = client.post(
        "/sweep", json={"geometry": "dipoles.invvee", "freqs_mhz": ["abc"]}
    )
    assert resp.status_code == 422


def test_converge_rejects_non_numeric_n_values(client):
    resp = client.post(
        "/converge", json={"geometry": "dipoles.invvee", "n_values": ["abc"]}
    )
    assert resp.status_code == 422


def test_positive_finite_helper():
    from antennaknobs.web.adapter import _positive_finite

    assert _positive_finite("x", 14.1) == 14.1
    assert _positive_finite("x", "14.1") == 14.1  # numeric strings are fine
    for bad in (0, -1, float("nan"), float("inf"), None, "abc", [1]):
        with pytest.raises(ValueError, match="x must be"):
            _positive_finite("x", bad)


# ---------------------------------------------------------------------------
# Hosted hardening (issue #348): API docs off when hosted, /converge errors
# through the shared formatter.
# ---------------------------------------------------------------------------


def test_docs_available_locally(client):
    # The default (unhosted) app keeps the interactive docs for development.
    assert server.app.docs_url == "/docs"
    assert client.get("/openapi.json").status_code == 200


def test_docs_disabled_when_hosted_at_import():
    # docs_url is baked in at FastAPI construction (import time), so the
    # hosted flag can't be monkeypatched after the fact — check in a fresh
    # interpreter with the env var set, exactly like the Fly container.
    import os
    import subprocess
    import sys

    code = (
        "from antennaknobs.web import server; "
        "assert server.app.docs_url is None; "
        "assert server.app.redoc_url is None; "
        "assert server.app.openapi_url is None"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        env={**os.environ, "ANTENNAKNOBS_HOSTED": "1"},
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr


def test_converge_error_goes_through_solve_error_formatter(hosted, client):
    # A per-N failure (here the size rejection) streams through
    # format_solve_error — "TypeName: message", never a raw str(e)/traceback.
    n = _n_per_wire_for_basis("dipoles.invvee", server._MAX_BASIS) * 2
    resp = client.post(
        "/converge", json={"geometry": "dipoles.invvee", "n_values": [n]}
    )
    first = json.loads(resp.text.strip().splitlines()[0])
    assert first["error"].startswith("SolveTooLargeError: ")


def test_momwire_bspline_ground_model_drives_sommerfeld_solve():
    """Web ground parity: with the plain B-spline solver the default
    "sommerfeld" ground model drives momwire's TRUE Sommerfeld solve
    (momwire >= 0.6.0), "fast" drives the reflection-coefficient one, the
    response ships the real εr/σ for the frontend Fresnel cut, and
    ground_model_applied reports what actually ran."""
    base = {
        "geometry": "dipoles.invvee",
        "solver": "momwire",
        "momwire_model": "bspline",
        "measurement_freq_mhz": 28.47,
        "ground": True,
    }
    somm = server.solve({**base, "ground_model": "sommerfeld"})
    fast = server.solve({**base, "ground_model": "fast"})
    default = server.solve(base)
    pec = server.solve({**base, "ground_model": "pec"})

    assert somm["ground_model_applied"] == "sommerfeld"
    assert fast["ground_model_applied"] == "refl-coef"
    # Sommerfeld costs seconds per solve, so it is opt-in: the default is
    # the reflection-coefficient model.
    assert default["ground_model_applied"] == "refl-coef"
    assert pec["ground_model_applied"] == "pec-image"
    assert somm["ground_eps_r"] == 10.0
    assert somm["ground_sigma"] == 0.002
    assert somm["ground_eps_im"] < 0.0  # derived -σ/(ωε₀)
    assert pec["ground_eps_r"] == pytest.approx(1.0e10)
    # "sommerfeld" and "fast" are now genuinely different solves of the
    # same physical ground: distinct values, but in agreement at this
    # comfortable height (they only diverge hard below ~0.1λ).
    z_somm = complex(somm["z_in_re"], somm["z_in_im"])
    z_fast = complex(fast["z_in_re"], fast["z_in_im"])
    assert z_somm != z_fast
    assert abs(z_somm - z_fast) < 5.0
    # The finite solves differ measurably from the PEC image solve — the
    # reactance correction the finite grounds exist to deliver.
    z_pec = complex(pec["z_in_re"], pec["z_in_im"])
    assert abs(z_fast - z_pec) > 2.0


def test_momwire_sinusoidal_ground_model_drives_refl_coef_solve():
    """Since momwire 0.5.0 the sinusoidal solver honours ground_eps too
    (field-based refl-coef, phase 6), so the web's finite ground models
    reach its impedance solve instead of folding to the PEC image."""
    base = {
        "geometry": "dipoles.invvee",
        "solver": "momwire",
        "momwire_model": "sinusoidal",
        "measurement_freq_mhz": 28.47,
        "ground": True,
    }
    fin = server.solve(base)  # default ground_model = fast (refl-coef)
    pec = server.solve({**base, "ground_model": "pec"})

    assert fin["ground_model_applied"] == "refl-coef"
    assert pec["ground_model_applied"] == "pec-image"
    assert fin["ground_eps_r"] == 10.0
    assert fin["ground_sigma"] == 0.002
    # The finite solve differs measurably from the PEC image solve — the
    # reactance correction the refl-coef ground exists to deliver.
    z_fin = complex(fin["z_in_re"], fin["z_in_im"])
    z_pec = complex(pec["z_in_re"], pec["z_in_im"])
    assert abs(z_fin - z_pec) > 2.0


@pytest.mark.parametrize("model", ["sinusoidal", "hmatrix", "arrayblock"])
def test_momwire_sommerfeld_applies_on_every_solver(model):
    """Since momwire 0.8.0 the "sommerfeld" ground model drives the TRUE
    Sommerfeld solve on every momwire backend (sinusoidal field-based,
    hmatrix/arrayblock on their fast paths), not just plain bspline —
    the wiring this release exists to deliver. The sommerfeld solve
    agrees with bspline-sommerfeld at the cross-solver floor and stays
    a genuinely different solve from refl-coef."""
    base = {
        "geometry": "dipoles.invvee",
        "solver": "momwire",
        "measurement_freq_mhz": 28.47,
        "ground": True,
    }
    somm = server.solve({**base, "momwire_model": model, "ground_model": "sommerfeld"})
    fast = server.solve({**base, "momwire_model": model, "ground_model": "fast"})
    ref = server.solve(
        {**base, "momwire_model": "bspline", "ground_model": "sommerfeld"}
    )
    assert somm["ground_model_applied"] == "sommerfeld"
    assert fast["ground_model_applied"] == "refl-coef"
    z_somm = complex(somm["z_in_re"], somm["z_in_im"])
    z_fast = complex(fast["z_in_re"], fast["z_in_im"])
    z_ref = complex(ref["z_in_re"], ref["z_in_im"])
    assert z_somm != z_fast
    assert abs(z_somm - z_ref) < 3.0  # cross-solver floor


def test_retired_model_name_falls_back_to_bspline():
    """The triangular solver is retired: a stale client still naming it
    (or any unknown model) gets the default BSpline solve instead of a
    500 — same contract as the adapter's _MOMWIRE_MODELS fallback."""
    base = {
        "geometry": "dipoles.invvee",
        "solver": "momwire",
        "measurement_freq_mhz": 28.47,
    }
    stale = server.solve({**base, "momwire_model": "triangular"})
    bspline = server.solve({**base, "momwire_model": "bspline"})
    assert stale["z_in_re"] == bspline["z_in_re"]
    assert stale["z_in_im"] == bspline["z_in_im"]


def test_swept_mem_budget_injected_for_bspline_family(monkeypatch):
    """The deployment sweep-memory budget (ANTENNAKNOBS_SWEPT_MEM_MB, read
    at adapter import into _SWEPT_MEM_MB) must be injected into the
    bspline-family solvers' kwargs — overriding any client-sent value —
    and must NOT be passed to sinusoidal (no batched sweep, no such
    kwarg). Asserted at the engine-kwargs level so the test doesn't
    require a momwire version that accepts the kwarg (momwire >= 0.9).
    """
    import importlib

    from antennaknobs.web import adapter

    design = importlib.import_module("antennaknobs.designs.dipoles.invvee")
    req_base = {"measurement_freq_mhz": 28.47}
    builder = adapter._build_builder(design.Builder, req_base)

    monkeypatch.setattr(adapter, "_SWEPT_MEM_MB", 64)
    for model in ("bspline", "hmatrix", "arrayblock"):
        eng = adapter._make_momwire_engine(
            {**req_base, "momwire_model": model}, builder
        )
        assert eng._solver_kwargs.get("swept_mem_mb") == 64, model
    # Client-sent value loses to the server policy; other options survive.
    eng = adapter._make_momwire_engine(
        {
            **req_base,
            "momwire_model": "bspline",
            "model_options": {"swept_mem_mb": 4096, "degree": 1},
        },
        builder,
    )
    assert eng._solver_kwargs["swept_mem_mb"] == 64
    assert eng._solver_kwargs["degree"] == 1
    # Sinusoidal is skipped (kwarg unsupported there).
    eng = adapter._make_momwire_engine(
        {**req_base, "momwire_model": "sinusoidal"}, builder
    )
    assert "swept_mem_mb" not in (eng._solver_kwargs or {})

    # Unset (local default): nothing injected, momwire default applies.
    monkeypatch.setattr(adapter, "_SWEPT_MEM_MB", None)
    eng = adapter._make_momwire_engine(
        {**req_base, "momwire_model": "bspline"}, builder
    )
    assert "swept_mem_mb" not in (eng._solver_kwargs or {})


def test_momwire_ground_off_reports_free_model():
    resp = server.solve(
        {
            "geometry": "dipoles.invvee",
            "solver": "momwire",
            "momwire_model": "bspline",
            "measurement_freq_mhz": 28.47,
        }
    )
    assert resp["ground_model_applied"] == "free"
    assert resp["ground_eps_r"] == pytest.approx(1.0e10)

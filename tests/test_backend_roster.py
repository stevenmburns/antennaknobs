"""The served solver roster (issue #628).

Before #628 the roster lived twice — ``_MOMWIRE_MODELS`` in web/adapter.py and
a hand-kept ``BACKEND_ORDER``/``BACKEND_LABEL``/``BackendOptsMap`` in
lib/backends.ts — and the failure mode of drift was *silent absence*: when
sinusoidal-galerkin landed server-side (PR #626) both repos' CI stayed green
while the UI had no tab for any design. The interim tripwire
(tests/test_backend_roster_contract.py, a regex over the TSX) is retired here:
the frontend now renders from GET /capabilities, so there is only one roster
and these tests guard *it* — registry/roster agreement by construction, served
knob ranges the hosted sanitiser will actually accept, and the served shape the
frontend reads.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

# Import the server package first: importing adapter directly at collection
# time trips the adapter <-> examples circular import (the order every other
# web test uses).
from antennaknobs.web import server as _server

import antennaknobs.web.adapter as adapter  # noqa: E402
from antennaknobs.web.adapter import (  # noqa: E402
    _BACKENDS,
    _HOSTED_MODEL_OPTIONS,
    _MOMWIRE_MODELS,
    backend_roster,
)


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(_server.app)


def _roster(have_pynec: bool = True) -> list[dict]:
    return backend_roster(have_pynec=have_pynec)


# ---------------------------------------------------------------------------
# Registry <-> roster agreement
# ---------------------------------------------------------------------------


def test_roster_names_match_the_momwire_registry():
    """Every constructible solver is offered and every offered momwire entry is
    constructible. Trivially true while both derive from `_BACKENDS` — which is
    the point of unifying them: the drift #626 shipped is now unrepresentable.
    """
    momwire_entries = {e["name"] for e in _roster() if e["kind"] == "momwire"}
    assert momwire_entries == set(_MOMWIRE_MODELS)


def test_momwire_entries_carry_a_solver_class_and_pynec_does_not():
    """`_MOMWIRE_MODELS.get(model, BSplineSolver)` silently substitutes
    B-spline for an unknown model, so a momwire entry with no class would
    serve the wrong solver's numbers under the right tab. PyNEC is the one
    entry with no momwire class — it rides `solver: "pynec"`."""
    for spec in _BACKENDS:
        assert (spec.solver is None) == (spec.kind == "pynec"), spec.name
    assert all(cls is not None for cls in _MOMWIRE_MODELS.values())


def test_pynec_entry_is_gated_on_have_pynec_at_request_time(client, monkeypatch):
    """The frontend derives PyNEC availability from roster membership, so the
    entry must appear/disappear with pynec_backend.HAVE_PYNEC — read per
    request, not snapshotted at import (#429)."""
    from antennaknobs.web import pynec_backend

    assert [e["name"] for e in _roster(have_pynec=True)][-1] == "pynec"
    assert "pynec" not in {e["name"] for e in _roster(have_pynec=False)}

    monkeypatch.setattr(pynec_backend, "HAVE_PYNEC", False)
    served = client.get("/capabilities").json()
    assert "pynec" not in {e["name"] for e in served["backends"]}
    assert served["have_pynec"] is False

    monkeypatch.setattr(pynec_backend, "HAVE_PYNEC", True)
    served = client.get("/capabilities").json()
    assert "pynec" in {e["name"] for e in served["backends"]}
    assert served["have_pynec"] is True


# ---------------------------------------------------------------------------
# Served knob ranges vs the hosted sanitiser
# ---------------------------------------------------------------------------


def test_served_option_ranges_pass_the_hosted_sanitiser():
    """A served knob the hosted instance would reject is a slider that 400s at
    its own extreme. Every options_schema entry's key must be whitelisted and
    its min/max/default must all validate against that key's checker
    (_HOSTED_MODEL_OPTIONS), i.e. the served range sits inside the sanitiser's.
    """
    for entry in _roster():
        for field in entry["options_schema"]:
            check = _HOSTED_MODEL_OPTIONS.get(field["key"])
            assert check is not None, (
                f"{entry['name']}.{field['key']} is not in _HOSTED_MODEL_OPTIONS "
                "— the hosted instance would drop it from model_options"
            )
            for bound in ("min", "max", "default"):
                check(field[bound])  # raises ValueError if out of range
            assert field["min"] <= field["default"] <= field["max"]
            assert field["step"] > 0


# ---------------------------------------------------------------------------
# Served shape
# ---------------------------------------------------------------------------


def test_backend_roster_served_shape(client):
    """The catalog the frontend renders its whole solver picker from: order,
    labels, ground support, panel hints and the generic knob schema. Pinned
    here the way the terrain preset catalog is (issue #560)."""
    roster = _roster()
    assert [e["name"] for e in roster] == [
        "sinusoidal",
        "sinusoidal-galerkin",
        "bspline",
        "hmatrix",
        "arrayblock",
        "pynec",
    ]
    by_name = {e["name"]: e for e in roster}
    assert [e["label"] for e in roster] == [
        "Sinusoidal",
        "Sin-Galerkin",
        "B-spline",
        "H-matrix (ACA)",
        "Array-block",
        "PyNEC",
    ]
    # Every current solver models a ground; the flag exists so a future one
    # that doesn't can say so without a frontend change.
    assert all(e["supports_ground"] for e in roster)
    assert {n: e["panel"] for n, e in by_name.items()} == {
        "sinusoidal": None,
        "sinusoidal-galerkin": "sin-galerkin",
        "bspline": "bspline",
        "hmatrix": "bspline",
        "arrayblock": "bspline",
        "pynec": "pynec",
    }
    # Generic numeric knobs: only the two sinusoidal bases carry one today —
    # every other backend's knobs are non-numeric (degree tabs, gated
    # checkboxes, an enum select) and live in its bespoke panel.
    assert {n: [f["key"] for f in e["options_schema"]] for n, e in by_name.items()} == {
        "sinusoidal": ["n_qp_const"],
        "sinusoidal-galerkin": ["n_qp_const"],
        "bspline": [],
        "hmatrix": [],
        "arrayblock": [],
        "pynec": [],
    }
    assert by_name["sinusoidal"]["options_schema"][0] == {
        "key": "n_qp_const",
        "label": "n_qp_const (GL pts)",
        "min": 2,
        "max": 32,
        "step": 1,
        "default": 8,
    }
    # Interactive mesh defaults: 21 (odd, interior knot at the feed) for the
    # array-block solver and PyNEC, 30 elsewhere.
    assert {n: e["default_n_per_wire"] for n, e in by_name.items()} == {
        "sinusoidal": 30,
        "sinusoidal-galerkin": 30,
        "bspline": 30,
        "hmatrix": 30,
        "arrayblock": 21,
        "pynec": 21,
    }
    # comboInappropriate policy, served as capabilities instead of the
    # frontend's old name lists.
    assert {n for n, e in by_name.items() if e["accelerator"]} == {
        "hmatrix",
        "arrayblock",
    }
    assert {n for n, e in by_name.items() if e["dense_family"]} == {
        "sinusoidal-galerkin",
        "bspline",
        "hmatrix",
        "arrayblock",
    }
    # The catalog rides /capabilities so the frontend learns the roster on
    # mount, exactly like terrain_presets.
    from antennaknobs.web import pynec_backend

    served = client.get("/capabilities").json()["backends"]
    assert served == _roster(have_pynec=pynec_backend.HAVE_PYNEC)


def test_recommendable_backends_are_roster_members():
    """`default_backend` on a design descriptor is normalised against the
    served roster by the frontend; a recommendation naming a backend the
    roster has never heard of is dropped, so the seed would silently do
    nothing. ("triangular" is the one retired name the frontend still maps.)"""
    names = {e["name"] for e in _roster()}
    for ex in _server.EXAMPLES.values():
        rec = ex.default_backend
        if rec is None:
            continue
        assert rec in names or rec == "triangular", (ex.name, rec)


def test_required_backends_are_roster_members():
    """Same for the per-design allowlist (`requires_backends`): a name outside
    the roster would disable every tab with no way to satisfy it."""
    names = {e["name"] for e in _roster()}
    for ex in _server.EXAMPLES.values():
        for req in ex.requires_backends or ():
            assert req in names, (ex.name, req)


def test_adapter_module_import_is_the_one_registry():
    """`_MOMWIRE_MODELS` stays available (derived) for the solve path's lookup
    and the existing web tests that import it."""
    assert adapter._MOMWIRE_MODELS is _MOMWIRE_MODELS
    assert _MOMWIRE_MODELS["bspline"].__name__ == "BSplineSolver"

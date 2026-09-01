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

import antennaknobs.web.adapter as adapter
from antennaknobs.web.adapter import (
    _BACKENDS,
    _HOSTED_MODEL_OPTIONS,
    _MOMWIRE_MODELS,
    backend_roster,
)


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(_server.app)


def _roster(have_pynec: bool = True, have_nec5: bool = False) -> list[dict]:
    return backend_roster(have_pynec=have_pynec, have_nec5=have_nec5)


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
        assert (spec.solver is None) == (spec.kind in ("pynec", "nec5")), spec.name
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
    roster = _roster(have_nec5=True)
    assert [e["name"] for e in roster] == [
        "sinusoidal",
        "sinusoidal-galerkin",
        "bspline",
        "hmatrix",
        "arrayblock",
        "razor-2p",
        "pynec",
        "nec5",
    ]
    by_name = {e["name"]: e for e in roster}
    assert [e["label"] for e in roster] == [
        "Sinusoidal",
        "Sin-Galerkin",
        "B-spline",
        "H-matrix (ACA)",
        "Array-block",
        "Razor (2-point)",
        "PyNEC",
        "NEC-5",
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
        "razor-2p": None,
        "pynec": "pynec",
        "nec5": "nec5",
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
        # razor-2p's only quadrature knob (n_qp_path) is inert under the
        # two-point rule, so it serves none rather than an inert one.
        "razor-2p": [],
        "pynec": [],
        "nec5": [],
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
    # array-block solver and PyNEC, 30 elsewhere. razor-2p asks for more
    # because it converges slower -- ~16x the mesh of bspline for the same
    # self-convergence on the ByDipole1 ladder -- and EVEN, because a
    # centre-fed deck wants a knot at the feed for that basis.
    assert {n: e["default_n_per_wire"] for n, e in by_name.items()} == {
        "sinusoidal": 30,
        "sinusoidal-galerkin": 30,
        "bspline": 30,
        "hmatrix": 30,
        "arrayblock": 21,
        "razor-2p": 40,
        "pynec": 21,
        # NEC-5 sources sit at segment ends: an EVEN count puts the feed
        # knot at the wire's exact middle (issue #825).
        "nec5": 20,
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
        "razor-2p",
    }
    # The catalog rides /capabilities so the frontend learns the roster on
    # mount, exactly like terrain_presets.
    from antennaknobs.web import pynec_backend

    from antennaknobs.web import nec5_backend

    served = client.get("/capabilities").json()["backends"]
    assert served == _roster(
        have_pynec=pynec_backend.HAVE_PYNEC, have_nec5=nec5_backend.have_nec5()
    )


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
    the roster would disable every tab with no way to satisfy it. Validated
    against the FULL roster (both gated engines present): `nec5` is a
    legitimate allowlist member that only materializes as a tab on boxes
    resolving $NEC5_EXE — a listed-but-absent backend is simply not a tab,
    which is different from a name the roster can never serve."""
    names = {e["name"] for e in _roster(have_pynec=True, have_nec5=True)}
    for ex in _server.EXAMPLES.values():
        for req in ex.requires_backends or ():
            assert req in names, (ex.name, req)


def test_adapter_module_import_is_the_one_registry():
    """`_MOMWIRE_MODELS` stays available (derived) for the solve path's lookup
    and the existing web tests that import it."""
    assert adapter._MOMWIRE_MODELS is _MOMWIRE_MODELS
    assert _MOMWIRE_MODELS["bspline"].__name__ == "BSplineSolver"


def test_nec5_entry_is_gated_on_the_binary_probe_at_request_time(client, monkeypatch):
    """NEC-5 is licensed, user-supplied software (issue #825): the entry
    appears exactly when the serving machine resolves $NEC5_EXE — a runtime
    probe per request, so the hosted simulator (which never defines it) can
    never offer NEC-5, while a local instance with the env var set always
    does."""
    import sys

    assert "nec5" in {e["name"] for e in _roster(have_nec5=True)}
    assert "nec5" not in {e["name"] for e in _roster(have_nec5=False)}

    monkeypatch.delenv("NEC5_EXE", raising=False)
    served = client.get("/capabilities").json()
    assert "nec5" not in {e["name"] for e in served["backends"]}

    monkeypatch.setenv("NEC5_EXE", sys.executable)
    served = client.get("/capabilities").json()
    assert "nec5" in {e["name"] for e in served["backends"]}


# ---------------------------------------------------------------------------
# Bound kwargs (razor-2p)
# ---------------------------------------------------------------------------


def test_razor_2p_binds_the_two_point_rule_and_the_wire_cannot_unbind_it():
    """`razor-2p` is a lane, not just a class, so the roster BINDS the kwarg.

    `RazorSolver` serves two quadrature rules off one class and momwire names
    them `razor` (Gauss-Legendre) and `razor-2p` (the two-point centroid
    trapezoid). Only the second is offered here, so the binding has to survive
    whatever a client sends: if `model_options` could flip it, the label on the
    tab would stop describing what ran.
    """
    from antennaknobs.web.adapter import _MOMWIRE_BOUND

    assert _MOMWIRE_BOUND["razor-2p"] == {"nec5_quadrature": True}
    # Bound kwargs are applied last, so a hostile or stale option loses.
    merged = dict({"nec5_quadrature": False})
    merged.update(_MOMWIRE_BOUND["razor-2p"])
    assert merged["nec5_quadrature"] is True


def test_razor_2p_exposes_no_inert_quadrature_knob():
    """`n_qp_path` is IGNORED under the two-point rule (momwire's own
    docstring), so serving it would render a control that does nothing."""
    roster = _roster()
    entry = next(e for e in roster if e["name"] == "razor-2p")
    keys = {f["key"] for f in entry["options_schema"]}
    assert "n_qp_path" not in keys, entry["options_schema"]

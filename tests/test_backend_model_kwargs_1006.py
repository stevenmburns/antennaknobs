"""`_BackendSpec.model_kwargs` — what a backend EXPOSES — is constructible.

"ACCEPTS" AND "EXPOSES" ARE DIFFERENT FACTS. What a constructor accepts is
measurable: construct it and see. What the product offers is a DECISION, and
before #1006 G2-6 it was encoded by the `panel` hint. `model_kwargs` is the
decision; this file gates it against the measurement in the ONE direction
that can hurt a user.

Deleting the `panel` hint deletes the only record of WHICH solver knobs apply
to WHICH backend, so that fact has to be written down somewhere. Written down
is not the same as true, and this file is the difference.

CONSTRUCT, NEVER INTROSPECT. `inspect.signature` cannot answer this question
here and answers it wrongly with great confidence:

    HMatrixSolver             reports NO keyword arguments at all
    SinusoidalGalerkinSolver  reports only `feed_model`

Both take the full set through `**kwargs`. A gate built on signatures would
have declared `hmatrix` optionless and been green. So every cell below is
built.

`exposed ⊆ accepted`, AND NOT THE REVERSE. Every exposed kwarg must construct,
so the product can never offer a knob the engine rejects. The converse —
requiring every accepted kwarg to be exposed — is deliberately NOT gated, and
an earlier version of this file DID gate it, which is what produced a real
bug: it forced `model_kwargs` to mean "accepts", the request builder was fed
from it, and stock requests began carrying `feed_model="point"` to
`SinusoidalSolver`, the one solver that REFUSES the point gap (momwire#212).
A gate asserting a product decision as if it were a fact about the class does
not protect the product; it deforms it.

The three knobs that are accepted and deliberately not exposed, each of which
would change a request payload if listed:

    BSplineSolver   feed_model     axis is ("segment-gap",) — never offered
    RazorSolver     degree         axis is ("tent",)
    RazorSolver     n_qp_source    never had a control

`inspect.signature` cannot measure the accepted half either: `HMatrixSolver`
reports NO keyword arguments and takes the full B-spline set through
`**kwargs`, and `SinusoidalGalerkinSolver` reports only `feed_model` while
plainly accepting `extended_kernel`. Construct it.
"""

from __future__ import annotations

import warnings

import numpy as np
import pytest

import antennaknobs.web.server  # noqa: F401 — resolves the adapter import cycle
from antennaknobs.web.adapter import _BACKENDS, _OPTION_SPECS

WL = 42.83

# One value per kwarg that is VALID for it — the point is whether the
# constructor takes the keyword, so every value here must pass the sanitiser
# too (asserted below, so a typo cannot silently turn an accept into a
# ValueError that this file would read as "accepted").
SAMPLE = {
    "degree": 2,
    "n_qp_const": 8,
    "n_qp_pair": 8,
    "n_qp_source": 16,
    "n_qp_sing": 32,
    "feed_smoothing_factor": 0.5,
    "feed_model": "segment",
    "use_singular_enrichment": False,
    "enrichment_variant": "raw",
    "tikhonov_lambda": 0.1,
    "auto_tap_ratio_threshold": 0.3,
    "enrichment_min_k": 3,
    "extended_kernel": False,
}

MOMWIRE = [b for b in _BACKENDS if b.kind == "momwire" and b.solver is not None]


def _deck():
    """A two-segment-per-half dipole — the cheapest deck every family builds."""
    return dict(
        wires=[np.array([(0.0, 0.0, 5.0), (0.0, 0.0, -5.0)])],
        n_per_edge_per_wire=[[9]],
        feeds=[(0, 5.0, 1 + 0j)],
        wavelength=WL,
        wire_radius=1e-3,
    )


def _build(spec, **extra):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return spec.solver(**_deck(), **dict(spec.bound or {}), **extra)


def test_the_sample_values_are_all_valid_so_an_accept_means_what_it_says():
    from antennaknobs.web.adapter import _HOSTED_MODEL_OPTIONS

    assert set(SAMPLE) == set(_OPTION_SPECS)
    for k, v in SAMPLE.items():
        _HOSTED_MODEL_OPTIONS[k](v)  # raises if the sample is not valid


@pytest.mark.parametrize("spec", MOMWIRE, ids=lambda s: s.name)
def test_the_bare_deck_builds_so_a_failure_below_means_the_kwarg(spec):
    """Without this, every 'rejected' verdict could be the deck's fault and
    the file would be measuring nothing."""
    assert _build(spec) is not None


@pytest.mark.parametrize("spec", MOMWIRE, ids=lambda s: s.name)
def test_every_listed_kwarg_is_actually_accepted(spec):
    assert spec.model_kwargs, f"{spec.name}: no kwargs listed at all"
    for k in spec.model_kwargs:
        assert k in _OPTION_SPECS, f"{spec.name}: {k} is not a known option"
        try:
            _build(spec, **{k: SAMPLE[k]})
        except TypeError as e:  # pragma: no cover - the failure we want named
            if k in str(e):
                pytest.fail(f"{spec.name} does NOT accept {k}: {e}")
            raise
        except Exception:  # noqa: BLE001 — anything that is NOT a TypeError
            # about this keyword means the constructor ACCEPTED the name and
            # then failed for an unrelated reason (a refusal on this deck,
            # say). Narrowing this would make the test depend on which
            # exception each solver happens to raise, which is not the
            # question being asked.
            pass


def test_the_deliberately_unexposed_kwargs_are_ACCEPTED_and_still_not_listed():
    """The three exclusions, pinned with the reason each exists.

    These are accepted by their classes — asserted by construction below — and
    exposing any of them changes a request payload, which is what the recorded
    payload fixture would catch. Pinned here so nobody "fixes" the list by
    adding what the constructor happens to take.
    """
    by_name = {b.name: b for b in MOMWIRE}
    cases = [
        ("bspline", "feed_model", "segment"),
        ("razor-2p", "degree", 2),
        ("razor-2p", "n_qp_source", 16),
    ]
    for name, kwarg, value in cases:
        spec = by_name[name]
        assert kwarg not in spec.model_kwargs, f"{name} now exposes {kwarg}"
        # ...and it really is accepted, so this is a DECISION and not a
        # limitation of the class.
        try:
            _build(spec, **{kwarg: value})
        except TypeError as e:  # pragma: no cover - names the failure
            if kwarg in str(e):
                pytest.fail(f"{name} does not accept {kwarg} — premise gone: {e}")
            raise
        except Exception:  # noqa: BLE001 — accepted the keyword, failed later
            pass


def test_the_families_share_a_list_exactly_where_they_share_a_surface():
    """bspline/hmatrix/arrayblock are one class and two accelerated
    subclasses, so three separate literals would be three things to drift.

    The sinusoidal pair does NOT share one any more, and that is the point:
    the Galerkin member exposes `feed_model` and the point-matched one must
    not, because it refuses the point gap (momwire#212). They were a single
    shared tuple until that bug, and splitting them is the fix.
    """
    by_name = {b.name: b.model_kwargs for b in MOMWIRE}
    assert by_name["bspline"] is by_name["hmatrix"] is by_name["arrayblock"]
    assert by_name["sinusoidal"] is not by_name["sinusoidal-galerkin"]
    assert set(by_name["sinusoidal-galerkin"]) - set(by_name["sinusoidal"]) == {
        "feed_model"
    }


def test_the_exposed_lists_reproduce_the_pre_refactor_request_payloads():
    """The lists are not free choices — they are what the bespoke panels sent.

    Recorded from the frontend before any of this moved (the eight-state
    fixture), so the renderer swap can be a refactor rather than a change.
    `extended_kernel` is exposed everywhere and rides only when armed, so it
    is excluded here the way the wire excludes it.
    """
    expected = {
        "sinusoidal": {"n_qp_const"},
        "sinusoidal-galerkin": {"feed_model", "n_qp_const"},
        "bspline": {
            "auto_tap_ratio_threshold",
            "degree",
            "enrichment_min_k",
            "enrichment_variant",
            "feed_smoothing_factor",
            "n_qp_pair",
            "n_qp_sing",
            "n_qp_source",
            "tikhonov_lambda",
            "use_singular_enrichment",
        },
        "razor-2p": set(),
    }
    expected["hmatrix"] = expected["arrayblock"] = expected["bspline"]
    for name, want in expected.items():
        spec = next(b for b in MOMWIRE if b.name == name)
        got = set(spec.model_kwargs) - {"extended_kernel"}
        assert got == want, f"{name}: exposes {sorted(got ^ want)} unexpectedly"


def test_n_qp_const_belongs_to_the_sinusoidal_family_and_not_the_bspline_one():
    """The one asymmetry, pinned because it looks like a mistake.

    Everything else the b-spline family takes is a superset of what the
    sinusoidal family takes; `n_qp_const` runs the other way. The two families
    quadrature differently, and this is precisely the fact the `panel` hint
    could not express — it named a panel, not a set of knobs.
    """
    by_name = {b.name: set(b.model_kwargs) for b in MOMWIRE}
    assert "n_qp_const" in by_name["sinusoidal"]
    assert "n_qp_const" not in by_name["bspline"]

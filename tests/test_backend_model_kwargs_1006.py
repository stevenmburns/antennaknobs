"""`_BackendSpec.model_kwargs` is measured, not believed (#1006 G2-6).

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

BOTH DIRECTIONS, which is the whole point. A listed kwarg must be ACCEPTED,
and an unlisted one must raise TypeError. A one-directional gate lets the list
rot the other way: listing everything everywhere would satisfy "listed implies
accepted" for every backend that has `**kwargs`, i.e. four of the six.

ACCEPTING IS NOT OFFERING. `razor-2p` accepts `degree` and must never show a
degree control, because its `basis` axis holds one value. That separation is
asserted here so nobody closes the gap by "fixing" the list.
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


@pytest.mark.parametrize("spec", MOMWIRE, ids=lambda s: s.name)
def test_every_UNLISTED_kwarg_is_actually_rejected(spec):
    """The direction that keeps the list honest.

    Four of the six solvers take `**kwargs`, so "listed implies accepted"
    would be satisfied by listing everything everywhere. This is what makes
    the list a measurement rather than a superset.
    """
    unlisted = sorted(set(_OPTION_SPECS) - set(spec.model_kwargs))
    assert unlisted, f"{spec.name}: lists every option — nothing to check"
    for k in unlisted:
        with pytest.raises(TypeError) as exc:
            _build(spec, **{k: SAMPLE[k]})
        assert k in str(exc.value), (
            f"{spec.name}: {k} raised TypeError but not about {k}: {exc.value}"
        )


def test_accepting_a_kwarg_is_not_the_same_as_offering_a_control():
    """`razor-2p` accepts `degree` and offers one value of `basis`.

    Conflating the two is the failure this separation exists to prevent: a
    generic renderer that drew a control for every accepted kwarg would put a
    degree tab on the two-point razor lane, whose basis is "tent" and has no
    degree to choose.
    """
    razor = next(b for b in MOMWIRE if b.name == "razor-2p")
    assert "degree" in razor.model_kwargs
    from momwire._capabilities import axes_for

    assert axes_for(razor.solver.capabilities)["basis"] == frozenset({"tent"})


def test_the_families_that_share_a_constructor_share_a_list():
    """bspline/hmatrix/arrayblock are one class and two accelerated
    subclasses, so three separate literals would be three things to drift."""
    by_name = {b.name: b.model_kwargs for b in MOMWIRE}
    assert by_name["bspline"] is by_name["hmatrix"] is by_name["arrayblock"]
    assert by_name["sinusoidal"] is by_name["sinusoidal-galerkin"]


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

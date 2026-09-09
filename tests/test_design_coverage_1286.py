"""Per-design backend coverage (#1286).

`design_backend_coverage` DERIVES which backends refuse a design from the
design's measured capability needs and each solver's own `capabilities`. The
derivation is fast (0.1 s for the whole catalog) precisely because it does not
construct anything, which is also why it needs a gate against something that
does.

The gate is `_make_solver`: constructing the solver raises the ENGINE'S OWN
refusal and fills no matrix, so it is authoritative about capability refusals
without being a solve. It costs ~13 s over the catalog, which is why it is the
test and not the implementation.

Everything here is a capability question. A numerical domain limit found
during the fill is deliberately out of scope — it is not a property of
(design, backend); `wire.terminated_longwire` refused at the 2026-09-08
ladder's ground setting and serves at the defaults.
"""

from __future__ import annotations

import warnings

import pytest

import antennaknobs.web.examples  # noqa: F401 — import for registration order
from antennaknobs.web import adapter
from antennaknobs.web.examples import REGISTRY

# The momwire-kind backends the probe can answer. PyNEC and NEC-5 are excluded
# because `_make_solver` is a momwire engine method and NEC-5 additionally
# needs a licensed binary this box may not have — an availability question,
# not a capability one.
_PROBEABLE = (
    "sinusoidal",
    "sinusoidal-galerkin",
    "bspline",
    "pulse",
    "hmatrix",
    "arrayblock",
    "razor-2p",
)


def _spec(name):
    return next(b for b in adapter._BACKENDS if b.name == name)


def _probe_refuses(cls, backend: str) -> str | None:
    """The engine's own refusal from constructing the solver, or None.

    Fills nothing: `_make_solver` builds the solver object, which is where
    momwire raises for an unmet capability.
    """
    builder = adapter._build_builder(cls, {})
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            eng = adapter._make_momwire_engine(
                {"momwire_model": backend}, builder, None
            )
            eng._make_solver(wavelength=eng._wavelength_for(eng.builder.freq))
        except NotImplementedError as exc:
            return str(exc)
    return None


def _design_cls(name):
    import importlib

    mod = importlib.import_module(f"{adapter.DESIGNS_PKG}.{name}")
    return mod.Builder


# --------------------------------------------------------------------------
# The gate: the derivation must agree with the probe, cell for cell.
# --------------------------------------------------------------------------


@pytest.mark.antenna_computation_check
def test_derivation_agrees_with_the_solver_construction_probe():
    """Every (design, backend) cell agrees with constructing the solver.

    Buried is the one need the probe cannot see — `_make_solver` succeeds and
    the fill refuses later — so it is added from the capability object, which
    is the same source the derivation uses. That makes buried NOT independently
    checked here; `test_buried_refusals_are_present` pins it against the named
    designs instead, so the two together cover both halves.
    """
    buried_designs = {
        name
        for name in REGISTRY
        if "buried" in adapter._design_capability_needs(_design_cls(name))
    }
    assert buried_designs, "no buried design found — the probe's blind spot is untested"

    disagreements = []
    checked = 0
    for name in sorted(REGISTRY):
        cls = _design_cls(name)
        derived = adapter.design_backend_coverage(name)["refusals"]
        for backend in _PROBEABLE:
            spec = _spec(backend)
            probed = _probe_refuses(cls, backend)
            expected_refused = probed is not None or (
                name in buried_designs and adapter._backend_buried_refusal(spec)
            )
            got_refused = backend in derived
            checked += 1
            if bool(expected_refused) != got_refused:
                disagreements.append(
                    f"{name} x {backend}: probe={'refused' if expected_refused else 'served'} "
                    f"derived={'refused' if got_refused else 'served'}"
                )
    # An empty disagreement list means nothing unless cells were actually
    # compared — a broken loop also disagrees with nobody.
    assert checked == len(REGISTRY) * len(_PROBEABLE), (
        f"compared {checked} cells, expected {len(REGISTRY) * len(_PROBEABLE)}"
    )
    assert not disagreements, "\n".join(disagreements)


# --------------------------------------------------------------------------
# Presence: the refusals we know about must actually be reported.
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("design", "backend", "capability"),
    [
        ("dipoles.invvee_apex", "sinusoidal", "node_gaps"),
        ("dipoles.invvee_apex", "pulse", "node_gaps"),
        ("wire.sterba_bl", "sinusoidal", "junction_ports"),
        ("wire.sterba_bl", "razor-2p", "junction_ports"),
        ("wire.sterba_bl", "pulse", "junction_ports"),
        ("verticals.elt_whip", "pulse", "per_wire_radius"),
        ("specialty.buried_dipole", "hmatrix", "buried"),
        ("specialty.buried_dipole", "arrayblock", "buried"),
    ],
)
def test_known_refusals_are_present(design, backend, capability):
    got = adapter.design_backend_coverage(design)["refusals"]
    assert backend in got, f"{backend} should refuse {design} ({capability})"
    assert got[backend]["capability"] == capability


def test_buried_refusals_are_present():
    """The half the construction probe cannot see, pinned by name."""
    for design in (
        "specialty.buried_dipole",
        "verticals.buried_radial_vertical",
        "verticals.elevated_buried_counterpoise",
    ):
        cov = adapter.design_backend_coverage(design)
        assert "buried" in cov["needs"], design
        # bspline is the ONLY solver with a buried fill; if that changes this
        # assertion should fail rather than quietly widen.
        assert "bspline" not in cov["refusals"], design
        for backend in ("hmatrix", "arrayblock", "sinusoidal", "razor-2p", "pulse"):
            assert cov["refusals"][backend]["capability"] == "buried", (
                f"{backend} on {design}"
            )


# --------------------------------------------------------------------------
# Absence: a served design must report NOTHING, or the marks mean nothing.
# --------------------------------------------------------------------------


def test_a_plain_design_refuses_nowhere():
    cov = adapter.design_backend_coverage("dipoles.invvee")
    assert cov["needs"] == []
    assert cov["refusals"] == {}


def test_bspline_serves_every_design_in_the_catalog():
    """bspline has every capability field set; nothing may refuse on it."""
    refused = [
        name
        for name in REGISTRY
        if "bspline" in adapter.design_backend_coverage(name)["refusals"]
    ]
    assert refused == []


def test_needs_are_measured_not_universal():
    """Guards the opposite failure: a derivation that marks everything.

    If `_design_capability_needs` returned a constant, every design would
    carry the same needs and the marks would be noise.
    """
    needs = {name: adapter.design_backend_coverage(name)["needs"] for name in REGISTRY}
    plain = [n for n, v in needs.items() if v == []]
    marked = [n for n, v in needs.items() if v]
    assert plain, "no design needs nothing — the derivation marks everything"
    assert marked, "no design needs anything — the derivation measures nothing"


# --------------------------------------------------------------------------
# Provenance: the sentence must be momwire's, verbatim.
# --------------------------------------------------------------------------


def test_every_refusal_carries_a_sentence():
    """#1264: a refusal without prose is the bug, not the refusal."""
    missing = []
    for name in REGISTRY:
        for backend, row in adapter.design_backend_coverage(name)["refusals"].items():
            if not row.get("reason"):
                missing.append(f"{name} x {backend} [{row['capability']}]")
    assert not missing, "\n".join(missing)


def test_the_sentence_is_the_solvers_own_words():
    """Equal to `capabilities.refusal(field)`, not a paraphrase of it.

    This is the property #1286 asked for and the one a frontend constant
    cannot have: `RESTRICTED_BACKEND_REASON` was wrong for a vertex-port
    design precisely because it was written separately from the rule.
    """
    checked = 0
    for name in REGISTRY:
        for backend, row in adapter.design_backend_coverage(name)["refusals"].items():
            caps = getattr(
                getattr(_spec(backend), "solver", None), "capabilities", None
            )
            if caps is None:  # wrapper backends carry no capability object
                continue
            assert row["reason"] == caps.refusal(row["capability"]), (
                f"{name} x {backend}: sentence differs from momwire's"
            )
            checked += 1
    assert checked > 0, "no momwire-kind refusal was compared"


def test_coverage_is_not_a_promise_that_a_solve_succeeds():
    """The documented limit, pinned so it cannot be quietly widened.

    `wire.terminated_longwire` is the 2026-09-08 ladder's one refusal on every
    engine, on a below/below domain limit — and it has NO capability refusal
    here, because that limit depends on the ground the user picks rather than
    on the design. If this ever starts reporting one, the docstring promising
    callers that absence is not a guarantee needs revisiting too.
    """
    cov = adapter.design_backend_coverage("wire.terminated_longwire")
    assert cov["refusals"] == {}

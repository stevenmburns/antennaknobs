"""The geometry PREVIEW must not carry a solver's refusal.

FOUND IN THE BROWSER, and the trace is worth keeping because the symptom
pointed nowhere near the cause: switching to a buried design with an
accelerated backend selected showed the raw engine error in the failure
banner and NO gate — while the frontend's withhold logic was correct and
never ran.

Three pieces:

  1. momwire#814 moved the buried refusal to ENGINE CONSTRUCTION
     (engines/momwire.py: MomwireEngine.__init__ raises).
  2. `momwire_geometry` builds the engine with the REQUEST's
     `momwire_model`, so a refused solver+design combination raises in the
     PREVIEW — despite `geometry_endpoint`'s docstring promising the preview
     is solver-independent.
  3. The client's preview-error path never releases its gate, so the solve
     effect (which would have withheld and shown momwire's sentence) never
     runs. The banner is the preview's error, verbatim.

THE ASSERTION IS ON THE OUTPUT, not the producer: /geometry must return wires
for any served model on any design. What the preview does internally to
achieve that is its business; what it must never do is fail because of a
choice that belongs to the solve.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import antennaknobs.web.server as srv
from antennaknobs.web.adapter import _BACKENDS

MOMWIRE_MODELS = [b.name for b in _BACKENDS if b.kind == "momwire"]
BURIED = "verticals.buried_radial_vertical"
SOMMERFELD = {"enabled": True, "model": "sommerfeld", "eps_r": 13.0, "sigma": 0.005}


@pytest.fixture(scope="module")
def client():
    return TestClient(srv.app)


def _preview(client, design, model, **extra):
    return client.post(
        "/geometry",
        json={
            "geometry": design,
            "variant": "default",
            "solver": "momwire",
            "n_per_wire": 20,
            "momwire_model": model,
            **extra,
        },
    ).json()


@pytest.mark.parametrize("model", MOMWIRE_MODELS)
def test_a_buried_design_previews_on_every_model(client, model):
    """The failing case, and the one a user hits by switching design.

    `arrayblock` and `hmatrix` cannot SOLVE this deck — that is real, and the
    client gates it with momwire's own sentence. But they must still DRAW it:
    the preview is how the user sees the antenna they just selected, and a
    solver they have not run yet must not be able to blank it.
    """
    got = _preview(client, BURIED, model, ground=SOMMERFELD)
    assert not got.get("error"), f"{model}: {got.get('error')}"
    assert got.get("wires"), f"{model}: no wires"


def test_the_ground_is_what_makes_it_bite(client):
    """Recorded because it cost time: without ground the refusal does not
    fire, so a repro that omits it silently passes. The buried refusal is
    about geometry BELOW AN INTERFACE, and with no interface declared there
    is nothing to be below."""
    without = _preview(client, BURIED, "arrayblock")
    assert not without.get("error"), "premise moved: it now fails without ground too"


@pytest.mark.parametrize("model", MOMWIRE_MODELS)
def test_every_design_previews_on_every_model(client, model):
    """The general form. A preview that can fail for a solver reason is a
    preview that can blank the canvas for a choice the user has not made yet.
    """
    for design in ("dipoles.invvee", "arrays.bowtiearray1x2", "verticals.elt_whip"):
        got = _preview(client, design, model)
        assert not got.get("error"), f"{model} on {design}: {got.get('error')}"
        assert got.get("wires"), f"{model} on {design}: no wires"


def test_the_request_s_own_model_is_still_used_when_it_CAN_build(client):
    """The fallback must be a fallback, not a replacement.

    `geometry_distribution()` IS model-dependent: on this deck `razor-2p`
    puts the feed at knot 1 where every other model puts it at knot 0,
    because the two-point lane snaps the feed to a different grid. Always
    previewing with the default model would draw the feed marker in the wrong
    place on every razor preview — trading a rare blank canvas for a
    permanent quiet lie, which is the worse of the two.
    """
    razor = _preview(client, "arrays.bowtiearray1x2", "razor-2p")
    other = _preview(client, "arrays.bowtiearray1x2", "bspline")
    assert razor["feed_knot_index"] == 1
    assert other["feed_knot_index"] == 0


def test_a_design_that_genuinely_cannot_BUILD_still_reports_its_error(
    client, monkeypatch
):
    """The fallback must not swallow real errors.

    A deck whose builder raises has nothing to draw, and that error belongs
    in the banner — it is about the DESIGN, which the user did choose. Only a
    SOLVER's refusal may be routed around, and the original error is what
    surfaces when the fallback fails too.
    """
    import antennaknobs.web.adapter as ad

    def boom(*a, **k):
        raise RuntimeError("deliberate build failure")

    monkeypatch.setattr(ad, "_make_momwire_engine", boom)
    got = _preview(client, BURIED, "arrayblock", ground=SOMMERFELD)
    assert got.get("error"), "a genuine failure must still reach the client"
    assert "deliberate build failure" in got["error"]


def test_the_fallback_survives_options_the_default_model_would_reject(client):
    """The fallback keeps `model_options` while swapping the model — so it
    hands one solver's options to another. That is SAFE, and the reason is
    worth pinning rather than trusting.

    `BSplineSolver` genuinely rejects `n_qp_const` (TypeError: unexpected
    keyword argument) — it belongs to the sinusoidal family. `sinusoidal`
    cannot preview a buried deck, so it takes the fallback, and the fallback
    hands B-spline exactly that option. It still draws.

    WHY: the engine applies `solver_kwargs` at SOLVE time, not at
    construction — `geometry_distribution()` never instantiates the solver
    with them. The refusal that DOES fire in the constructor
    (`_buried_refusal`) depends on the solver CLASS, not its kwargs. So no
    model option can reach a constructor on this path, and the fallback
    cannot be broken by one.

    Asserted with the option that would actually bite, so this stays a
    measurement rather than a hope: if the engine ever moves kwargs into
    construction, this fails.
    """
    got = _preview(
        client,
        BURIED,
        "sinusoidal",
        ground=SOMMERFELD,
        model_options={"n_qp_const": 8},
    )
    assert not got.get("error"), got.get("error")
    assert got.get("wires")


def test_that_option_really_is_one_the_default_model_rejects():
    """Otherwise the test above proves nothing — it would be asserting that a
    harmless option is harmless."""
    import warnings

    import numpy as np
    import pytest as _pytest
    from momwire import BSplineSolver

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        with _pytest.raises(TypeError, match="n_qp_const"):
            BSplineSolver(
                wires=[np.array([(0.0, 0.0, 5.0), (0.0, 0.0, -5.0)])],
                n_per_edge_per_wire=[[9]],
                feeds=[(0, 5.0, 1 + 0j)],
                wavelength=42.83,
                wire_radius=1e-3,
                n_qp_const=8,
            )

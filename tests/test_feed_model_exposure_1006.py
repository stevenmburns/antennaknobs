"""The B-spline family exposes its feed model, and the wire change moves nothing.

momwire#891 corrected rows that declared only the segment gap while their
constructors defaulted to the POINT gap — so `BSplineSolver` and its two
accelerated subclasses had a feed model nobody could ask them about, and
antennaknobs' composition line stated the wrong one. The axis is honestly
multi-valued now, so the control is offered and `feed_model` joins the
request.

THE PAYLOAD CHANGES ON PURPOSE AND THE PHYSICS DOES NOT. "point" was already
the solver's default, so the stock request now says explicitly what it was
getting implicitly. That is the whole claim, and it is asserted numerically
below rather than argued: a solve with the key absent and a solve with
`feed_model="point"` must agree BIT FOR BIT, and both must differ from the
segment gap — otherwise the assertion would pass on a solver that ignored the
keyword entirely.
"""

from __future__ import annotations

import warnings

import numpy as np
import pytest

import antennaknobs.web.server  # noqa: F401 — resolves the adapter import cycle
from antennaknobs.web.adapter import backend_roster

FAMILY = ("bspline", "hmatrix", "arrayblock")
WL = 42.83


def _rows():
    return {r["name"]: r for r in backend_roster(have_pynec=True, have_nec5=True)}


def _z(result):
    if isinstance(result, tuple):
        result = result[0]
    return complex(np.asarray(result, dtype=complex).ravel()[0])


def _solve(**over):
    from momwire import BSplineSolver

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return _z(
            BSplineSolver(
                wires=[np.array([(0.0, 0.0, 5.0), (0.0, 0.0, -5.0)])],
                n_per_edge_per_wire=[[15]],
                feeds=[(0, 5.0, 1 + 0j)],
                wavelength=WL,
                wire_radius=1e-3,
                degree=2,
                **over,
            ).compute_impedance()
        )


def test_sending_the_default_explicitly_changes_no_number():
    """The anchor. Bit-for-bit, not approximately."""
    implicit = _solve()
    explicit = _solve(feed_model="point")
    assert implicit == explicit, (implicit, explicit)


def test_the_anchor_is_not_vacuous():
    """...and the keyword is not simply ignored.

    Without this, a solver that dropped `feed_model` on the floor would
    satisfy the test above, and the "moves nothing" claim would be true for
    the wrong reason.
    """
    assert _solve() != _solve(feed_model="segment")


@pytest.mark.parametrize("name", FAMILY)
def test_the_family_exposes_the_feed_model(name):
    row = _rows()[name]
    assert "feed_model" in row["model_kwargs"]
    assert row["axes"]["feed_model"] == ["point-gap", "segment-gap"]


def test_the_point_matched_solver_still_does_not_expose_it():
    """The negative half, and the reason it matters: `SinusoidalSolver`
    REFUSES the point gap (momwire#212), so exposing the choice there would
    offer a value that raises. Exposure is not "wherever the kwarg exists"."""
    row = _rows()["sinusoidal"]
    assert "feed_model" not in row["model_kwargs"]
    assert row["axes"]["feed_model"] == ["segment-gap"]


def test_razor_still_does_not_expose_it():
    """Its feed is a node port; there is no gap to choose."""
    row = _rows()["razor-2p"]
    assert "feed_model" not in row["model_kwargs"]
    assert row["axes"]["feed_model"] == ["node-port"]


def test_the_served_default_is_the_solver_default():
    """The spec's default is what a stock request will now carry, so it has to
    be the value the solver was already using — otherwise this change WOULD
    move numbers, silently, on every stock solve."""
    from antennaknobs.web.adapter import _OPTION_SPECS

    assert _OPTION_SPECS["feed_model"].default == "point"

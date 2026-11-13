"""The fill reuse switch on the solver pane (AK#2165, momwire#1809).

Offered by capability, the way the exact ring kernel and the sector route
are: the server probes the installed momwire's constructor and lists
`pair_reuse` in a backend's `model_kwargs` only where its solver takes it.
The B-spline tab at any degree does, and the point-matched sinusoidal tab
since momwire 0.91.0 (momwire#1911); razor, pulse, H-matrix and the array
tab do not. The pane renders the served bool spec as a generic
checkbox. On a momwire that predates it (0.86.0, the pin until 0.87.0)
nothing is offered and nothing is sent, which is what the solving checks
here skip on.
"""

from __future__ import annotations

import pytest

from antennaknobs.engines.momwire import _takes_pair_reuse
from antennaknobs.web import server  # noqa: F401  (registers the backends)
from antennaknobs.web import adapter

from test_pair_reuse_hint_2165 import fed_yagi

served = pytest.mark.skipif(
    not _takes_pair_reuse(adapter._BACKENDS_BY_NAME["bspline"].solver),
    reason="this momwire's BSplineSolver takes no pair_reuse (momwire#1810)",
)


def test_the_spec_is_a_plain_checkbox_off_by_default():
    spec = adapter.model_option_specs()["pair_reuse"]
    assert spec["kind"] == "bool" and spec["default"] is False


def test_offered_only_where_the_solver_takes_it():
    for b in adapter._BACKENDS:
        assert adapter._offers_pair_reuse(b) == (
            b.kind == "momwire" and _takes_pair_reuse(b.solver)
        ), b.name
    # The point-matched sinusoidal class takes it too since momwire 0.91.0
    # (momwire#1911), so it is not in this list.
    for name in ("razor-2p", "hmatrix", "arrayblock"):
        b = adapter._BACKENDS_BY_NAME.get(name)
        if b is not None:
            assert not adapter._offers_pair_reuse(b), name


@served
def test_bspline_offers_it():
    rows = {r["name"]: r for r in adapter.backend_roster(have_pynec=False)}
    assert "pair_reuse" in rows["bspline"]["model_kwargs"]


@served
@pytest.mark.parametrize("asked", [True, False])
def test_the_adapter_passes_the_choice_to_the_engine(asked, monkeypatch):
    monkeypatch.setenv("ANTENNAKNOBS_PAIR_REUSE", "1")  # an explicit off wins
    eng = adapter._make_momwire_engine(
        {"momwire_model": "bspline", "model_options": {"pair_reuse": asked}},
        fed_yagi(4),
    )
    assert eng._pair_reuse is asked
    assert "pair_reuse" not in eng._solver_kwargs


def test_another_tab_drops_it():
    """A hand-made local request to a tab that does not offer it changes
    nothing: the value is dropped, never forwarded to a constructor."""
    b = adapter._BACKENDS_BY_NAME.get("razor-2p")
    if b is None:
        pytest.skip("no razor-2p backend")
    eng = adapter._make_momwire_engine(
        {"momwire_model": "razor-2p", "model_options": {"pair_reuse": True}},
        fed_yagi(2),
    )
    assert eng._pair_reuse is False
    assert "pair_reuse" not in eng._solver_kwargs

"""momwire's pass-through features on the solver pane (momwire#1847, #1849).

`transmitted_anchors` (the B-spline and sinusoidal tabs) and
`point_cplx_staged` (the sinusoidal tab) are each one solver keyword, wired
like `pair_reuse` (AK#2165): offered by a live probe of the installed
momwire's constructor, and in addition only where momwire certifies the
feature on this platform (its reach; the hosted app is level 1). Off by
default; the server's ANTENNAKNOBS_<NAME> seeds an unset request and an
explicit off wins. On a momwire that predates a feature (the submodule
pointer and the PyPI pin until the release that carries it) nothing is
offered and nothing is sent, which is what the solving checks skip on.
"""

from __future__ import annotations

import pytest

from antennaknobs.engines import momwire as mw_engine
from antennaknobs.engines.momwire import FEATURE_SWITCHES, feature_served
from antennaknobs.web import server  # noqa: F401  (registers the backends)
from antennaknobs.web import adapter

from test_pair_reuse_hint_2165 import fed_yagi

# Where each feature is wired, when the installed momwire takes it.
TABS = {
    "transmitted_anchors": ("bspline", "sinusoidal"),
    "point_cplx_staged": ("sinusoidal",),
}


def _solver(tab):
    return adapter._BACKENDS_BY_NAME[tab].solver


def _served(name, tab):
    return pytest.mark.skipif(
        not feature_served(_solver(tab), name),
        reason=f"this momwire's {tab} solver does not serve {name} here",
    )


CASES = [(n, t) for n, tabs in TABS.items() for t in tabs]


@pytest.mark.parametrize("name", FEATURE_SWITCHES)
def test_each_spec_is_a_plain_checkbox_off_by_default(name):
    spec = adapter.model_option_specs()[name]
    assert spec["kind"] == "bool" and spec["default"] is False
    assert FEATURE_SWITCHES[name] == "ANTENNAKNOBS_" + name.upper()


@pytest.mark.parametrize("name", FEATURE_SWITCHES)
def test_offered_only_where_served(name):
    for b in adapter._BACKENDS:
        assert adapter._offers_feature(b, name) == (
            b.kind == "momwire" and feature_served(b.solver, name)
        ), b.name
    for tab in ("razor-2p", "pulse", "hmatrix", "arrayblock"):
        b = adapter._BACKENDS_BY_NAME.get(tab)
        if b is not None:
            assert not adapter._offers_feature(b, name), tab


def test_not_offered_outside_the_reach(monkeypatch):
    """The constructor probe alone is not enough: a platform below the
    feature's reach (sse2, Windows, macOS) is offered nothing."""
    from momwire import _features

    monkeypatch.setattr(_features, "certified", lambda name, *a, **k: False)
    for b in adapter._BACKENDS:
        for name in FEATURE_SWITCHES:
            assert not adapter._offers_feature(b, name), (b.name, name)


@pytest.mark.parametrize("name,tab", CASES)
def test_the_tab_lists_it_where_served(name, tab):
    rows = {r["name"]: r for r in adapter.backend_roster(have_pynec=False)}
    assert (name in rows[tab]["model_kwargs"]) == feature_served(_solver(tab), name)


@pytest.mark.parametrize("name,tab", CASES)
@pytest.mark.parametrize("asked", [True, False])
def test_the_adapter_passes_the_choice_to_the_engine(name, tab, asked, monkeypatch):
    if not feature_served(_solver(tab), name):
        pytest.skip(f"this momwire's {tab} solver does not serve {name} here")
    monkeypatch.setenv(FEATURE_SWITCHES[name], "1")  # an explicit off wins
    eng = adapter._make_momwire_engine(
        {"momwire_model": tab, "model_options": {name: asked}}, fed_yagi(2)
    )
    assert (name in eng._feature_kwargs) is asked
    assert name not in eng._solver_kwargs


@pytest.mark.parametrize("name,tab", CASES)
def test_the_server_env_seeds_an_unset_request(name, tab, monkeypatch):
    if not feature_served(_solver(tab), name):
        pytest.skip(f"this momwire's {tab} solver does not serve {name} here")
    eng = adapter._make_momwire_engine({"momwire_model": tab}, fed_yagi(2))
    assert name not in eng._feature_kwargs
    monkeypatch.setenv(FEATURE_SWITCHES[name], "1")
    eng = adapter._make_momwire_engine({"momwire_model": tab}, fed_yagi(2))
    assert eng._feature_kwargs.get(name) is True


@pytest.mark.parametrize("name,tab", CASES)
def test_an_on_feature_reaches_the_constructor_and_off_passes_nothing(
    name, tab, monkeypatch
):
    if not feature_served(_solver(tab), name):
        pytest.skip(f"this momwire's {tab} solver does not serve {name} here")
    seen = []
    real = mw_engine.MomwireEngine._construct_solver

    def spy(self, *a, **k):
        solver = real(self, *a, **k)
        seen.append(getattr(solver, "_" + name))
        return solver

    monkeypatch.setattr(mw_engine.MomwireEngine, "_construct_solver", spy)
    for asked in (False, True):
        eng = adapter._make_momwire_engine(
            {"momwire_model": tab, "model_options": {name: asked}}, fed_yagi(2)
        )
        eng.impedance()
    assert seen and seen[0] is False and seen[-1] is True


def test_another_tab_drops_it():
    """A hand-made local request to a tab that does not offer a feature
    changes nothing: the value is dropped, never forwarded."""
    for name in FEATURE_SWITCHES:
        eng = adapter._make_momwire_engine(
            {"momwire_model": "razor-2p", "model_options": {name: True}},
            fed_yagi(2),
        )
        assert name not in eng._feature_kwargs
        assert name not in eng._solver_kwargs

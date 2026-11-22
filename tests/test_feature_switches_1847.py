"""momwire's pass-through features on the solver pane (momwire#1847, #1849,
#1860).

`transmitted_anchors` (the B-spline and sinusoidal tabs) and
`point_cplx_staged` (the sinusoidal tab) are each one solver keyword, wired
like `pair_reuse` (AK#2165): offered by a live probe of the installed
momwire's constructor, and in addition only where momwire certifies the
feature on this platform (its reach; the hosted app is level 1). Off by
default unless momwire runs it by default (momwire#1951's
``Feature.default``, `feature_default`); the server's ANTENNAKNOBS_<NAME>
seeds an unset request and an explicit off wins. A served feature always
reaches the constructor as an explicit True or False (AK#2317): absence
would mean momwire's default, which is no longer always off. On a momwire that predates a feature (the submodule
pointer and the PyPI pin until the release that carries it) nothing is
offered and nothing is sent, which is what the solving checks skip on.
"""

from __future__ import annotations

import pytest

from antennaknobs.engines import momwire as mw_engine
from antennaknobs.engines.momwire import (
    FEATURE_SWITCHES,
    feature_default,
    feature_served,
)
from antennaknobs.web import server  # noqa: F401  (registers the backends)
from antennaknobs.web import adapter

from test_pair_reuse_hint_2165 import fed_yagi

# Where each feature is wired, when the installed momwire takes it.
TABS = {
    "transmitted_anchors": ("bs2", "sinusoidal"),
    "point_cplx_staged": ("sinusoidal",),
    "nec2_far_approx": ("sinusoidal",),
    "factored_columns": ("bs2", "razor2p"),
    "height_sheet_recal": ("bs2", "razor2p"),
    "crossing_table": ("bs2", "razor2p"),
    "crossing_above_rule": ("bs2",),
    "kcl_nullspace": ("bs2",),
    "nec2_end_cap": ("sinusoidal",),
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
def test_each_spec_is_a_plain_checkbox_at_momwires_default(name, monkeypatch):
    monkeypatch.delenv(FEATURE_SWITCHES[name], raising=False)
    spec = adapter.model_option_specs()[name]
    assert spec["kind"] == "bool" and spec["default"] is feature_default(name)
    assert FEATURE_SWITCHES[name] == "ANTENNAKNOBS_" + name.upper()


@pytest.mark.parametrize("name", [*FEATURE_SWITCHES, "pair_reuse"])
def test_a_seeded_server_serves_the_checkbox_ticked(name, monkeypatch):
    # The app sends every option it shows, so a seed reaches its solves only
    # through the served default; with it the box shows ticked and an
    # explicit untick still wins.
    env = adapter._SEED_ENVS[name]
    unseeded = name in FEATURE_SWITCHES and feature_default(name)
    monkeypatch.delenv(env, raising=False)
    assert adapter.model_option_specs()[name]["default"] is unseeded
    monkeypatch.setenv(env, "1")
    # An approximate feature (drift over the line) is never seeded on.
    assert adapter.model_option_specs()[name]["default"] is (
        mw_engine.feature_seedable(name) or unseeded
    )
    # A seed at "0" serves the box unticked, a default-on feature included.
    monkeypatch.setenv(env, "0")
    assert adapter.model_option_specs()[name]["default"] is False


@pytest.mark.parametrize("name", FEATURE_SWITCHES)
def test_offered_only_where_served(name):
    for b in adapter._BACKENDS:
        assert adapter._offers_feature(b, name) == (
            b.kind == "momwire" and feature_served(b.solver, name)
        ), b.name
    for tab in ("razor2p", "pulse", "hmatrix", "arrayblock"):
        if tab in TABS[name]:
            continue
        b = adapter._BACKENDS_BY_NAME.get(tab)
        if b is not None:
            assert not adapter._offers_feature(b, name), tab


def test_not_offered_outside_the_reach(monkeypatch):
    """The constructor probe alone is not enough: a platform below the
    feature's reach (sse2, Windows, macOS) is offered nothing."""
    _features = pytest.importorskip(
        "momwire._features", reason="this momwire has no feature registry"
    )
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
    # Explicit either way: an off is passed as False, never left out.
    assert eng._feature_kwargs[name] is asked
    assert name not in eng._solver_kwargs


@pytest.mark.parametrize("name,tab", CASES)
def test_the_server_env_seeds_an_unset_request(name, tab, monkeypatch):
    if not feature_served(_solver(tab), name):
        pytest.skip(f"this momwire's {tab} solver does not serve {name} here")
    monkeypatch.delenv(FEATURE_SWITCHES[name], raising=False)
    eng = adapter._make_momwire_engine({"momwire_model": tab}, fed_yagi(2))
    # Unseeded and unasked: momwire's own default, passed explicitly.
    assert eng._feature_kwargs[name] is feature_default(name)
    monkeypatch.setenv(FEATURE_SWITCHES[name], "1")
    eng = adapter._make_momwire_engine({"momwire_model": tab}, fed_yagi(2))
    if mw_engine.feature_seedable(name):
        assert eng._feature_kwargs[name] is True
    else:
        # Over the drift line: on only when a request asks (AK#2233).
        assert eng._feature_kwargs[name] is feature_default(name)
    monkeypatch.setenv(FEATURE_SWITCHES[name], "0")
    eng = adapter._make_momwire_engine({"momwire_model": tab}, fed_yagi(2))
    if mw_engine.feature_seedable(name):
        # A seed at "0" turns a default-on feature off for the server.
        assert eng._feature_kwargs[name] is False


@pytest.mark.parametrize("name,tab", CASES)
def test_the_solver_runs_what_the_request_says(name, tab, monkeypatch):
    """What momwire's constructor resolved (its own ``_<name>``, from
    `_features.enabled`), not what this repo meant to pass: an unticked box
    solves with the feature off even where momwire runs it by default
    (AK#2317), a ticked one with it on, and a request that says nothing
    with momwire's default."""
    if not feature_served(_solver(tab), name):
        pytest.skip(f"this momwire's {tab} solver does not serve {name} here")
    monkeypatch.delenv(FEATURE_SWITCHES[name], raising=False)
    seen = []
    real = mw_engine.MomwireEngine._construct_solver

    def spy(self, *a, **k):
        solver = real(self, *a, **k)
        seen.append(getattr(solver, "_" + name))
        return solver

    monkeypatch.setattr(mw_engine.MomwireEngine, "_construct_solver", spy)
    ran = {}
    for asked in (False, True, None):
        options = {} if asked is None else {name: asked}
        eng = adapter._make_momwire_engine(
            {"momwire_model": tab, "model_options": options}, fed_yagi(2)
        )
        del seen[:]
        eng.impedance()
        assert seen and len(set(seen)) == 1, (asked, seen)
        ran[asked] = seen[0]
    assert ran == {False: False, True: True, None: feature_default(name)}


def test_another_tab_drops_it():
    """A hand-made local request to a tab that does not offer a feature
    changes nothing: the value is dropped, never forwarded."""
    for name in FEATURE_SWITCHES:
        eng = adapter._make_momwire_engine(
            {"momwire_model": "pulse", "model_options": {name: True}},
            fed_yagi(2),
        )
        assert name not in eng._feature_kwargs
        assert name not in eng._solver_kwargs

"""The pair-reuse checkbox is offered only where momwire certifies the part
the switch turns on there (Steve, 11-17: "Only where certified").

momwire#1982 made ``pair_reuse`` one switch every solver takes, with parts
(``part_of="pair_reuse"`` in momwire's registry): bspline's ``offset_reuse``
and razor-2p's ``razor_pair_reuse``. A native part asked for only through the
switch outside its reach is silently off (momwire's ``withheld``), so a
checkbox there would be one that does nothing. A solver with no part (the
sinusoidal one) runs ``pair_reuse`` itself and is held to its reach. The
probe is live: the parts
come from the installed registry and a solver carries a part when its
constructor takes the part's keyword, never a version compare or a hand-kept
backend list.
"""

from __future__ import annotations

import types

import pytest

from antennaknobs.engines import momwire as engine
from antennaknobs.engines.momwire import _takes_kwarg, _takes_pair_reuse
from antennaknobs.web import server  # noqa: F401  (registers the backends)
from antennaknobs.web import adapter

from test_pair_reuse_hint_2165 import fed_yagi, spy


def _registry():
    from antennaknobs.mw import feature_registry

    return feature_registry() or {}


def _parts():
    return [
        f for f in _registry().values() if getattr(f, "part_of", None) == "pair_reuse"
    ]


has_parts = pytest.mark.skipif(
    not _parts(),
    reason="this momwire's registry has no pair_reuse parts (momwire#1982)",
)


def _razor():
    b = adapter._BACKENDS_BY_NAME.get("razor-2p")
    if b is None:
        pytest.skip("no razor-2p backend")
    return b


class _Solver:
    def __init__(self, pair_reuse=None, razor_pair_reuse=None):
        pass


class _Plain:
    def __init__(self, pair_reuse=None):
        pass


def _spec(solver):
    return types.SimpleNamespace(kind="momwire", solver=solver, name="probe")


@has_parts
def test_the_parts_are_read_from_the_registry_by_keyword():
    names = {f.name for f in _parts()}
    assert {"offset_reuse", "razor_pair_reuse"} <= names
    assert engine.pair_reuse_parts(_razor().solver) == ("razor_pair_reuse",)
    bspline = adapter._BACKENDS_BY_NAME["bspline"].solver
    assert "offset_reuse" in engine.pair_reuse_parts(bspline)


@has_parts
def test_razor_is_offered_where_razor_pair_reuse_is_certified():
    from antennaknobs.mw import feature_certified

    b = _razor()
    assert _takes_pair_reuse(b.solver)
    assert adapter._offers_pair_reuse(b) is feature_certified("razor_pair_reuse")
    rows = {r["name"]: r for r in adapter.backend_roster(have_pynec=False)}
    assert ("pair_reuse" in rows["razor-2p"]["model_kwargs"]) is feature_certified(
        "razor_pair_reuse"
    )


@has_parts
@pytest.mark.parametrize("certified", [True, False])
def test_an_uncertified_part_withholds_the_offer(certified, monkeypatch):
    seen = []

    def fake(name):
        seen.append(name)
        return certified

    monkeypatch.setattr("antennaknobs.mw.feature_certified", fake)
    assert adapter._offers_pair_reuse(_spec(_Solver)) is certified
    assert "razor_pair_reuse" in seen and "pair_reuse" not in seen
    # A solver that carries no part (the sinusoidal shape) is held to the
    # `pair_reuse` feature itself.
    seen.clear()
    assert adapter._offers_pair_reuse(_spec(_Plain)) is certified
    assert seen == ["pair_reuse"]


def _sinusoidal():
    b = adapter._BACKENDS_BY_NAME.get("sinusoidal")
    if b is None or not _takes_pair_reuse(b.solver):
        pytest.skip("this momwire's SinusoidalSolver takes no pair_reuse")
    return b


@has_parts
def test_sinusoidal_has_no_part_and_is_offered_where_pair_reuse_is_certified():
    from antennaknobs.mw import feature_certified

    b = _sinusoidal()
    assert engine.pair_reuse_parts(b.solver) == ()
    assert feature_certified("pair_reuse")  # the hosted level, as here
    assert adapter._offers_pair_reuse(b) is True
    rows = {r["name"]: r for r in adapter.backend_roster(have_pynec=False)}
    assert "pair_reuse" in rows["sinusoidal"]["model_kwargs"]


@has_parts
def test_sinusoidal_is_withheld_where_pair_reuse_is_uncertified(monkeypatch):
    b = _sinusoidal()
    monkeypatch.setattr(
        "antennaknobs.mw.feature_certified", lambda name: name != "pair_reuse"
    )
    assert adapter._offers_pair_reuse(b) is False
    rows = {r["name"]: r for r in adapter.backend_roster(have_pynec=False)}
    assert "pair_reuse" not in rows["sinusoidal"]["model_kwargs"]
    # and a request for it on that tab is dropped, never forwarded
    monkeypatch.delenv("ANTENNAKNOBS_PAIR_REUSE", raising=False)
    eng = adapter._make_momwire_engine(
        {"momwire_model": "sinusoidal", "model_options": {"pair_reuse": True}},
        fed_yagi(2),
    )
    assert eng._pair_reuse is False


def test_a_solver_without_the_switch_is_never_offered():
    class _None:
        def __init__(self):
            pass

    assert adapter._offers_pair_reuse(_spec(_None)) is False
    assert (
        adapter._offers_pair_reuse(types.SimpleNamespace(kind="pynec", solver=_Plain))
        is False
    )


def test_a_registry_without_parts_keeps_the_constructor_probe(monkeypatch):
    monkeypatch.setattr("antennaknobs.mw.feature_registry", lambda: {})
    assert engine.pair_reuse_parts(_Solver) == ()
    assert adapter._offers_pair_reuse(_spec(_Solver)) is True


@has_parts
@pytest.mark.parametrize("asked", [True, False])
def test_razor_takes_the_choice_where_offered(asked, monkeypatch):
    b = _razor()
    if not adapter._offers_pair_reuse(b):
        pytest.skip("razor_pair_reuse is not certified here")
    monkeypatch.setenv("ANTENNAKNOBS_PAIR_REUSE", "1")  # an explicit off wins
    eng = adapter._make_momwire_engine(
        {"momwire_model": "razor-2p", "model_options": {"pair_reuse": asked}},
        fed_yagi(2),
    )
    assert eng._pair_reuse is asked
    # razor-2p finds its own classes: handed True, never the bspline hint.
    assert eng._pair_reuse_hintless is asked
    assert "pair_reuse" not in eng._solver_kwargs


@has_parts
@pytest.mark.parametrize("seed, expect", [("1", True), ("", False)])
def test_the_umbrella_seed_covers_razor(seed, expect, monkeypatch):
    """ANTENNAKNOBS_PAIR_REUSE seeds an unset razor-2p request (Steve, 11-17),
    and razor-2p's constructor resolves the part on."""
    b = _razor()
    if not adapter._offers_pair_reuse(b):
        pytest.skip("razor_pair_reuse is not certified here")
    monkeypatch.setenv("ANTENNAKNOBS_PAIR_REUSE", seed)
    monkeypatch.delenv("MOMWIRE_X_PAIR_REUSE", raising=False)
    monkeypatch.delenv("MOMWIRE_X_RAZOR_PAIR_REUSE", raising=False)
    eng = adapter._make_momwire_engine(
        {"momwire_model": "razor-2p", "model_options": {}}, fed_yagi(2)
    )
    assert eng._pair_reuse is expect
    made = []
    seen = spy(monkeypatch, eng, made)
    eng.impedance()
    assert seen and made
    for kw in seen:
        if expect:
            assert kw.get("pair_reuse") is True
        else:
            assert "pair_reuse" not in kw
    # What razor-2p's constructor resolved, not only what it was handed:
    # the part is on exactly when the seed is.
    assert all(bool(s._pair_reuse) is expect for s in made)


def test_takes_kwarg_reads_the_constructor():
    assert _takes_kwarg(_Solver, "razor_pair_reuse")
    assert not _takes_kwarg(_Plain, "razor_pair_reuse")

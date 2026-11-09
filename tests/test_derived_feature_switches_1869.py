"""momwire's feature registry describes its own switches (momwire#1869).

A momwire whose ``FEATURES`` entries carry ``offer``, ``label``,
``summary`` and ``drift`` (the largest relative change in input impedance
its author measured with the feature on) is read here, not re-typed:
`FEATURE_SWITCHES`, the checkboxes and the hosted allowlist all follow from
it, so a new momwire feature reaches the app with no change to this repo. A
registry without those fields keeps the hand-kept table.

The installed momwire on CI predates the fields, so the derived path is
driven here by a fake registry. One check reads the installed registry
itself and states which path it took.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from antennaknobs.engines import momwire as mw_engine
from antennaknobs.engines.momwire import (
    _FALLBACK_SWITCHES,
    LAST_DIGITS_DRIFT,
    FeatureInfo,
    _derive_features,
    _switches_for,
)
from antennaknobs.web import server  # noqa: F401  (registers the backends)
from antennaknobs.web import adapter


@dataclass(frozen=True)
class _Old:
    """A 0.88-shaped registry entry: no description, no offer."""

    name: str
    kwarg: str | None


@dataclass(frozen=True)
class _New:
    name: str
    kwarg: str | None
    offer: bool
    label: str = ""
    summary: str = ""
    drift: float | None = None


def _reg(*entries):
    return {e.name: e for e in entries}


FAKE = _reg(
    _New("pair_reuse", "pair_reuse", offer=False, drift=0.0),
    _New("fast_a", "fast_a", True, "shared columns", "Fills a column once.", 8e-12),
    _New("edge", "edge", True, "edge case", "At the line.", LAST_DIGITS_DRIFT),
    _New("coarse_b", "coarse_b", True, "crossing table", "Reads a table.", 2e-3),
    _New("internal", None, offer=False),
)


def test_an_old_registry_keeps_the_hand_kept_table():
    old = _reg(_Old("transmitted_anchors", "transmitted_anchors"))
    assert _derive_features(old) is None
    assert _derive_features({}) is None
    assert _switches_for(None) == _FALLBACK_SWITCHES


def test_a_descriptive_registry_offers_what_it_says():
    info = _derive_features(FAKE)
    assert list(info) == ["fast_a", "edge", "coarse_b"]
    assert info["fast_a"] == FeatureInfo(
        "fast_a", "shared columns", "Fills a column once.", 8e-12
    )
    assert _switches_for(info) == {
        "fast_a": "ANTENNAKNOBS_FAST_A",
        "edge": "ANTENNAKNOBS_EDGE",
        "coarse_b": "ANTENNAKNOBS_COARSE_B",
    }


@pytest.mark.parametrize(
    "bad",
    [
        _New("x", "x", True, "", "s", 0.0),  # no label
        _New("x", "x", True, "l", " ", 0.0),  # no summary
        _New("x", None, True, "l", "s", 0.0),  # no kwarg
        _New("x", "x", True, "l", "s", None),  # no drift
        _New("x", "x", True, "l", "s", float("nan")),
        _New("x", "x", True, "l", "s", -1e-9),
    ],
)
def test_an_incomplete_offer_falls_back_whole(bad):
    # Nothing half-derived: one bad entry and the hand-kept table stands.
    assert _derive_features({**FAKE, "x": bad}) is None


@pytest.fixture
def described(monkeypatch):
    info = _derive_features(FAKE)
    monkeypatch.setattr(adapter, "FEATURE_INFO", info)
    return info


def test_the_drift_line_sets_label_hover_and_allowlist(described):
    specs = adapter._feature_specs()
    assert specs["fast_a"].label == "shared columns (faster)"
    assert specs["fast_a"].description.endswith("only in the last digits.")
    # At the line counts as under it.
    assert specs["edge"].label == "edge case (faster)"
    assert specs["coarse_b"].label == "crossing table (faster, approximate)"
    assert "2e-03 relative" in specs["coarse_b"].description
    assert all(s.default is False and s.kind == "bool" for s in specs.values())
    hosted = adapter._hosted_options(specs)
    assert set(hosted) == {"fast_a", "edge"}


def test_hosted_never_offers_an_approximate_feature(described, monkeypatch):
    class _Spec:
        kind = "momwire"
        solver = object()

    monkeypatch.setattr(adapter, "feature_served", lambda _s, _n: True)
    monkeypatch.setattr(adapter, "_HOSTED", False)
    assert adapter._offers_feature(_Spec, "coarse_b")
    monkeypatch.setattr(adapter, "_HOSTED", True)
    assert not adapter._offers_feature(_Spec, "coarse_b")
    assert adapter._offers_feature(_Spec, "fast_a")


def test_the_installed_registry_takes_one_path_whole():
    from momwire import _features

    derived = _derive_features(_features.FEATURES)
    assert mw_engine.FEATURE_INFO == derived
    if derived is None:
        assert mw_engine.FEATURE_SWITCHES == _FALLBACK_SWITCHES
    else:
        assert set(mw_engine.FEATURE_SWITCHES) == set(derived)
        assert set(derived) <= set(adapter.model_option_specs())

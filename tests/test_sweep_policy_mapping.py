"""A design's `sweep_policy` is honoured whatever Mapping spells it.

Dominator and Challenger freeze their ui_params, so their `sweep_policy` is a
MappingProxyType; `_derive_sweep_policy` accepted only a `dict` and served both
the default policy, dropping their band lock silently from the day they were
modelled (2026-07-12). With the measurement dial's travel now the sweep range
(AK#1682), the lock decides what the dial reaches as well as what is swept.
"""

from __future__ import annotations

from types import MappingProxyType

import pytest

from antennaknobs.web.examples import REGISTRY
from antennaknobs.web.adapter import DEFAULT_SWEEP_POLICY, _derive_sweep_policy


def test_a_frozen_policy_derives_like_the_same_dict():
    spec = {"anchor": "meas_freq", "band_locked": True, "hi_factor": 1.5}
    frozen = _derive_sweep_policy({"sweep_policy": MappingProxyType(spec)})
    assert frozen == _derive_sweep_policy({"sweep_policy": dict(spec)})
    assert frozen != DEFAULT_SWEEP_POLICY


@pytest.mark.parametrize("key", ["verticals.dominator", "verticals.challenger"])
def test_the_frozen_designs_are_band_locked_on_the_measurement_band(key):
    policy = REGISTRY[key].sweep_policy
    assert policy.band_locked is True
    assert policy.anchor == "meas_freq"


@pytest.mark.parametrize(
    "bad",
    [
        {"anchor": "meas_freq", "band_lock": True},  # misspelt key
        "band_locked",  # not a mapping or a triple
        ("meas_freq", 0.8),  # a short triple
    ],
)
def test_a_policy_it_cannot_read_is_refused_not_defaulted(bad):
    with pytest.raises(ValueError, match="sweep_policy"):
        _derive_sweep_policy({"sweep_policy": bad})


def test_no_policy_is_the_default():
    assert _derive_sweep_policy({}) is DEFAULT_SWEEP_POLICY

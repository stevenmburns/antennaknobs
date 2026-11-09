"""A station-chain knob turn reuses the antenna's Z across requests.

The server builds an engine per request, so the engine's own held Z
(`_share_z_fill`, AK#1723) never outlives one knob turn. A station knob
(`stn_*`, a ``.ssn`` chain value) moves the network the reducer applies,
never the antenna, so the next request's Z key is the same and the
process-wide `_Z_CACHE` serves it without a fill.

Oracle: the same request on an empty cache, i.e. a fresh fill. A hit must
match it exactly. Controls: a frequency change refills; a zero cap never
reuses. Fills are counted with a spy on `_compute_Z_operator`, as in
test_one_z_fill_1723. Every fixture is synthetic.
"""

from __future__ import annotations

import pytest
from momwire import BSplineSolver
from test_simnec_import import _SCRIPT_M, _el, _ssn

from antennaknobs.cli import make_engine_factory
from antennaknobs.engines.momwire import clear_z_cache
from antennaknobs.file_designs import builder_from_text

_ENGINE = make_engine_factory("momwire:bspline", None)

_TEXT = _ssn(
    _SCRIPT_M,
    extra_elements=_el(
        "SERIES_TLINE",
        {"Zo": 450, "VFnom": 0.91, "ft": "100", "k0": 0, "k1": 0.02, "k2": 0.0001},
        label="T1",
    )
    + _el("SHUNT_CAP", {"F": "500p", "Q": 0}, label="C1"),
)


@pytest.fixture
def fills(monkeypatch):
    calls: list[int] = []
    real = BSplineSolver._compute_Z_operator

    def spy(self, *a, **k):
        calls.append(1)
        return real(self, *a, **k)

    monkeypatch.setattr(BSplineSolver, "_compute_Z_operator", spy)
    return calls


def _z(**params):
    cls = builder_from_text("station.ssn", _TEXT)
    b = cls({**cls.default_params, **params})
    return complex(_ENGINE(b).impedance()[0])


def test_a_station_knob_turn_fills_nothing_and_matches_a_fresh_fill(fills):
    _z()
    assert len(fills) == 1
    turned = _z(stn_T1_ft=60.0, stn_C1_F=250.0)
    assert len(fills) == 1, "the antenna did not move, so its Z is reused"
    clear_z_cache()
    fresh = _z(stn_T1_ft=60.0, stn_C1_F=250.0)
    assert len(fills) == 2
    assert turned == fresh
    assert abs(turned - _z()) > 1.0, "the knob moved the answer"


def test_a_frequency_change_refills(fills):
    _z()
    _z(freq=7.2)
    assert len(fills) == 2


def test_a_zero_cap_never_reuses(fills, monkeypatch):
    monkeypatch.setenv("ANTENNAKNOBS_Z_CACHE_MB", "0")
    _z()
    _z(stn_T1_ft=60.0)
    assert len(fills) == 2

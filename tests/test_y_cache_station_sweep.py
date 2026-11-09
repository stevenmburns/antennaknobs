"""A station-chain knob turn's frequency sweep reuses the antenna's swept Y.

The network path sweeps the antenna's port admittance once
(`compute_y_matrix_swept`) and applies the station network to it at each
frequency. A station knob moves only that network, so the next turn's sweep
over the same frequencies finds the same Y in `_Y_CACHE` and solves nothing.

Oracle: the same sweep on an empty cache. A hit must match it exactly.
The cache is per frequency, because /sweep sizes its chunks by time and a
faster repeat chunks differently: a sweep that is part of an earlier one
solves nothing, and one that overlaps it solves only its new frequencies.
Controls: other frequencies solve again; a zero cap never reuses.
Synthetic fixtures.
"""

from __future__ import annotations

import numpy as np
import pytest
from momwire import BSplineSolver
from test_ssn_station_knobs import _text

from antennaknobs.cli import make_engine_factory
from antennaknobs.engines import momwire as mw_engine
from antennaknobs.engines.momwire import clear_z_cache
from antennaknobs.file_designs import builder_from_text

_ENGINE = make_engine_factory("momwire:bspline", None)
_FREQS = np.linspace(6.9, 7.3, 9)


@pytest.fixture
def sweeps(monkeypatch):
    calls: list[int] = []
    real = BSplineSolver.compute_y_matrix_swept

    def spy(self, k_array, *a, **k):
        calls.append(len(k_array))
        return real(self, k_array, *a, **k)

    monkeypatch.setattr(BSplineSolver, "compute_y_matrix_swept", spy)
    return calls


def _sweep(freqs=_FREQS, **params):
    cls = builder_from_text("station.ssn", _text())
    b = cls({**cls.default_params, **params})
    return np.asarray(_ENGINE(b).impedance_sweep(freqs))


def test_a_station_knob_turn_sweeps_nothing_and_matches_a_fresh_sweep(sweeps):
    first = _sweep()
    assert sweeps == [9]
    turned = _sweep(stn_T1_ft=60.0, stn_C1_F=250.0)
    assert sweeps == [9], "the antenna did not move, so its swept Y is reused"
    clear_z_cache()
    fresh = _sweep(stn_T1_ft=60.0, stn_C1_F=250.0)
    assert sweeps == [9, 9]
    np.testing.assert_array_equal(turned, fresh)
    assert np.max(np.abs(turned - first)) > 1.0, "the knobs moved the answer"


def test_a_chunk_of_an_earlier_sweep_solves_nothing_and_new_points_solve(sweeps):
    whole = _sweep()
    # /sweep's next chunking of the same frequencies: every point a hit.
    parts = [_sweep(freqs=_FREQS[:4]), _sweep(freqs=_FREQS[4:])]
    assert sweeps == [9]
    np.testing.assert_array_equal(np.vstack(parts), whole)
    # A sweep overlapping it solves only its new frequencies, once.
    more = np.concatenate([_FREQS[-3:], [7.35, 7.4]])
    got = _sweep(freqs=more)
    assert sweeps == [9, 2]
    clear_z_cache()
    np.testing.assert_allclose(got, _sweep(freqs=more), rtol=1e-12)
    _sweep(freqs=_FREQS + 0.01)
    assert sweeps[-1] == 9


def test_a_zero_cap_never_reuses(sweeps, monkeypatch):
    monkeypatch.setenv("ANTENNAKNOBS_Z_CACHE_MB", "0")
    _sweep()
    _sweep(stn_T1_ft=60.0)
    assert sweeps == [9, 9]


@pytest.mark.parametrize("ground", [None, ("finite", 13.0, 0.005)])
def test_a_swept_y_does_not_depend_on_the_wavelength_its_solver_was_built_at(ground):
    # The key the cache rests on (`_y_cache_base`): /sweep builds each chunk's
    # solver at that chunk's first frequency, and the swept Y must not care.
    # If this ever fails, the Y cache would hand one chunking's Y to another.
    cls = builder_from_text("station.ssn", _text())
    eng = make_engine_factory("momwire:bspline", ground)(cls(dict(cls.default_params)))
    k = 2 * np.pi * _FREQS / eng.builder.c_light_mhz_m
    ys = [
        np.asarray(
            eng._make_solver(wavelength=eng._wavelength_for(f0)).compute_y_matrix_swept(
                k
            )
        )
        for f0 in (6.9, 7.3, 14.0)
    ]
    np.testing.assert_array_equal(ys[0], ys[1])
    np.testing.assert_array_equal(ys[0], ys[2])


def _entries(kind):
    return [k for k in mw_engine._FILL_CACHE if k[0] == kind]


def test_y_entries_are_capped_newest_kept(monkeypatch):
    monkeypatch.setattr(mw_engine, "_Y_CACHE_ENTRIES", 5)
    _sweep()
    ys = _entries("Y")
    assert len(ys) == 5
    ks = sorted(k for _tag, (_base, k) in ys)
    want = 2 * np.pi * _FREQS[-5:] / builder_from_text("s.ssn", _text()).c_light_mhz_m
    np.testing.assert_allclose(ks, want, rtol=1e-15)


def test_z_and_y_share_one_byte_budget(monkeypatch):
    # A budget that holds a few Y entries and no Z: the Z the live point
    # filled is evicted (or never kept), and the total stays inside it.
    cls = builder_from_text("station.ssn", _text())
    eng = _ENGINE(cls(dict(cls.default_params)))
    eng.impedance()
    (zkey,) = _entries("Z")
    z_bytes = mw_engine._FILL_CACHE[zkey].nbytes
    clear_z_cache()
    budget = z_bytes // 2
    monkeypatch.setenv("ANTENNAKNOBS_Z_CACHE_MB", repr(budget / 2**20))
    _ENGINE(cls(dict(cls.default_params))).impedance()
    _sweep()
    assert _entries("Z") == [], "a Z larger than the whole budget is never kept"
    assert 0 < len(_entries("Y")) <= len(_FREQS)
    total = sum(v.nbytes for v in mw_engine._FILL_CACHE.values())
    assert total <= mw_engine._z_cache_cap() <= budget
    assert mw_engine._FILL_STATE["bytes"] == total

"""``pair_reuse`` on the Sinusoidal tab (AK#2279, momwire#1911).

momwire 0.91.0's SinusoidalSolver takes ``pair_reuse`` and finds its own
congruent (observer, source) classes, reading any truthy value as "on". The
engine used to pass the keyword only with a non-empty B-spline edge-pair hint,
so a sinusoidal solve of a design with no congruent edge pairs got nothing
when the switch was ticked. It now passes ``True`` to a solver that needs no
hint, and the B-spline hint path is unchanged. Off by default throughout.
"""

from __future__ import annotations

import importlib

import numpy as np
import pytest

from antennaknobs import Wire
from antennaknobs.cli import make_engine_factory
from antennaknobs.engines.momwire import _pair_reuse_needs_hint, _takes_pair_reuse

from test_pair_reuse_hint_2165 import design, fed_yagi, spy

momwire = pytest.importorskip("momwire")
needs_sin_reuse = pytest.mark.skipif(
    not _takes_pair_reuse(momwire.SinusoidalSolver),
    reason="this momwire's SinusoidalSolver takes no pair_reuse (momwire#1914)",
)


def engine(builder, spec, **kw):
    return make_engine_factory(spec, "free")(builder, **kw)


def lone_dipole():
    """One wire: no pair of edges is congruent, so the bspline hint is empty."""
    return design([Wire((0.0, 0.0, 10.0), (0.0, 0.0, 15.0), n_seg=21, ex=1 + 0j)])


@pytest.fixture(autouse=True)
def _no_seed(monkeypatch):
    monkeypatch.delenv("ANTENNAKNOBS_PAIR_REUSE", raising=False)


@needs_sin_reuse
def test_the_probe_splits_the_two_families():
    assert _pair_reuse_needs_hint(momwire.BSplineSolver)
    assert not _pair_reuse_needs_hint(momwire.SinusoidalSolver)


@needs_sin_reuse
def test_on_passes_true_even_with_no_congruent_edge_pairs(monkeypatch):
    e = engine(lone_dipole(), "momwire:sinusoidal", pair_reuse=True)
    assert e._pair_reuse_hint() is None  # the hint is empty here
    seen = spy(monkeypatch, e)
    e.impedance()
    assert seen and all(kw.get("pair_reuse") is True for kw in seen)


@needs_sin_reuse
@pytest.mark.parametrize("asked", [None, False])
def test_off_passes_no_pair_reuse_kwarg(monkeypatch, asked):
    kw = {} if asked is None else {"pair_reuse": asked}
    e = engine(fed_yagi(4), "momwire:sinusoidal", **kw)
    seen = spy(monkeypatch, e)
    e.impedance()
    assert seen and all("pair_reuse" not in k for k in seen)


@pytest.mark.parametrize("builder", [lone_dipole, lambda: fed_yagi(4)])
def test_bspline_is_unchanged(monkeypatch, builder):
    if not _takes_pair_reuse(momwire.BSplineSolver):
        pytest.skip("no bspline pair_reuse")
    # on: the hint when there is one, nothing when there is none (never True)
    e = engine(builder(), "momwire:bspline", pair_reuse=True)
    want = e._pair_reuse_hint()
    seen = spy(monkeypatch, e)
    e.impedance()
    assert seen
    for k in seen:
        if want:
            assert k["pair_reuse"] is want
        else:
            assert "pair_reuse" not in k
    # off: nothing
    e = engine(builder(), "momwire:bspline")
    seen = spy(monkeypatch, e)
    e.impedance()
    assert seen and all("pair_reuse" not in k for k in seen)


@needs_sin_reuse
def test_z_agrees_with_the_switch_off_and_the_reuse_path_ran(monkeypatch):
    # Since momwire 0.94.0 (momwire#1969) the sinusoidal reuse declines a deck
    # under SMALL_DECK_SEGS_FREE segments as too small to repay the plan; this
    # Yagi is far under it, so the floor is lowered to make the path run.
    small = importlib.import_module("momwire._sin_pair_reuse")
    if hasattr(small, "SMALL_DECK_SEGS_FREE"):
        monkeypatch.setattr(small, "SMALL_DECK_SEGS_FREE", 0)
    off = engine(fed_yagi(4), "momwire:sinusoidal")
    z0 = np.asarray(off.impedance(), dtype=complex)

    on = engine(fed_yagi(4), "momwire:sinusoidal", pair_reuse=True)
    made = []
    spy(monkeypatch, on, made)
    z1 = np.asarray(on.impedance(), dtype=complex)
    assert made
    # Not a green that measured nothing: momwire's own census says the reuse
    # fill ran (it records each block's pairs/classes) and did not decline.
    ran = [s for s in made if s.pair_reuse_census]
    assert ran, "no solver recorded a pair-reuse census: the path never ran"
    assert all(s.pair_reuse_declined is None for s in ran)
    n_pairs = sum(n for s in ran for (n, _c, _near) in s.pair_reuse_census.values())
    n_classes = sum(c for s in ran for (_n, c, _near) in s.pair_reuse_census.values())
    assert n_classes < n_pairs, (n_pairs, n_classes)  # something was shared
    # and the switch-off solver recorded none
    assert np.max(np.abs(z1 - z0) / np.abs(z0)) <= 1e-9

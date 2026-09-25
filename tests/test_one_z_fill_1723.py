"""AK#1723: one workbench solve fills the B-spline Z matrix once.

A request drives `impedance`, `current_distribution` and `input_power`
separately; on the network path each of those built its own port solver (for
Y) or excited solver (for the currents), and each filled the same Z. The
engine now routes every solver of one configuration through a single held Z,
keyed on the constructor kwargs less the port voltages (`_z_fill_key`).

Pinned here, counting fills with a spy on `_compute_Z_operator` rather than by
timing:

- one server-shaped solve fills once, on the network path (an imported deck)
  and with a ground;
- the shared fill is bit-identical to the unshared one, which fills four
  times;
- a different frequency on the SAME engine refills and matches a fresh
  engine at that frequency exactly;
- a knob change refills even when the two engines are handed the same held
  slot, and matches a fresh engine exactly;
- a solver whose k a sweep rebinds refills, and a sweep after a solve is the
  fresh engine's sweep;
- the checks above FAIL against a key that ignores the configuration (the
  negative control of the negative controls).
"""

from __future__ import annotations

import importlib
from pathlib import Path

import numpy as np
import pytest
from momwire import BSplineSolver

import antennaknobs.engines.momwire as mw_engine
from antennaknobs.file_designs import builder_from_file

FIXTURES = Path(__file__).parent / "fixtures" / "sy_knobs_1705"

# The sy_knobs_1705 dipole: an imported deck is a network design, which is
# the path that used to fill four times.
DIPOLE = """CM a dipole with one derived symbol
CE
SY len=10.4 'Dipole length
SY h=10 'Height
SY half=len/2
GW 1 21 -half 0 h half 0 h 1e-3
GE 0
EX 0 1 11 0 1 0
FR 0 1 0 0 14.1 0
EN
"""

# GndScreen (the issue's deck) with short, coarse radials, over the default
# (reflection-coefficient) ground so it stays test-sized: the sharing is
# ground-agnostic, and the ground's kwargs are in the key like any other. The
# issue's own Sommerfeld request is measured outside the suite (25 s -> 9 s).
GND_KNOBS = {"sy_radl": 3.0, "sy_len": 12.0, "sy_hgh": 6.0}
GND_REQ = {
    "freq": 1.8,
    "solver": "momwire",
    "ground": True,
    "eps_r": 14.0,
    "sigma": 0.005,
}


def _adapter():
    importlib.import_module("antennaknobs.web.examples")
    from antennaknobs.web import adapter

    return adapter


@pytest.fixture
def fills(monkeypatch):
    """Count `_compute_Z_operator` calls. Patched on the class, so the
    engine's shared wrapper (which captures the class attribute when a solver
    is constructed) reaches the spy exactly as it reaches the real fill."""
    calls: list[int] = []
    real = BSplineSolver._compute_Z_operator

    def spy(self, *a, **k):
        calls.append(1)
        return real(self, *a, **k)

    monkeypatch.setattr(BSplineSolver, "_compute_Z_operator", spy)
    return calls


@pytest.fixture
def dipole_cls(tmp_path):
    path = tmp_path / "dipole.nec"
    path.write_text(DIPOLE)
    return builder_from_file(str(path))


def _server_solve(cls, req, name):
    """`server._solve_uncached`'s momwire branch for a design not in the
    registry."""
    from antennaknobs.web import server

    ex = _adapter()._make_example(name, cls, defer_hints=True)
    out = ex.momwire_solve(dict(req, geometry=name))
    out["solver"] = "momwire"
    server._attach_derived_em_fields(out)
    server._attach_gain_norm(out)
    server._attach_in_medium_fraction(out)
    return out


def _engine(cls, params, freq, req=None):
    b = cls(dict(cls.default_params, **params))
    b.freq = freq
    return _adapter()._make_momwire_engine(dict(req or {"freq": freq}), b)


def _numeric_equal(a, b, path="out"):
    """Exact equality over a solve's output, timing excluded."""
    if isinstance(a, dict):
        assert set(a) == set(b), path
        for k in a:
            if not k.endswith("_ms"):
                _numeric_equal(a[k], b[k], f"{path}.{k}")
    elif isinstance(a, (list, tuple)):
        assert len(a) == len(b), path
        for i, (u, v) in enumerate(zip(a, b, strict=True)):
            _numeric_equal(u, v, f"{path}[{i}]")
    elif isinstance(a, np.ndarray):
        assert a.dtype == b.dtype and a.tobytes() == b.tobytes(), path
    elif isinstance(a, float):
        assert np.array(a).tobytes() == np.array(b).tobytes(), path
    elif isinstance(a, complex):
        assert np.array(a).tobytes() == np.array(b).tobytes(), path
    else:
        assert a == b, path


def _solve_state(eng):
    """Everything a request reads off the engine, as exact bytes."""
    z = np.asarray(eng.impedance(), dtype=np.complex128)
    cur = [c.knot_currents for c in eng.current_distribution()]
    p = np.float64(eng.input_power())
    return [z.tobytes(), *(c.tobytes() for c in cur), p.tobytes()]


@pytest.mark.parametrize("which", ["dipole", "gndscreen"])
def test_one_server_solve_fills_z_once_and_matches_unshared(
    which, fills, dipole_cls, monkeypatch
):
    if which == "dipole":
        cls, req = dipole_cls, {"freq": 14.1, "solver": "momwire"}
        params: dict = {}
    else:
        cls = builder_from_file(str(FIXTURES / "GndScreen.nec"))
        req, params = GND_REQ, GND_KNOBS
    solve_cls = type(cls.__name__, (cls,), {})
    solve_cls.default_params = dict(cls.default_params, **params)

    shared = _server_solve(solve_cls, req, f"user.{which}")
    assert len(fills) == 1

    fills.clear()
    monkeypatch.setattr(mw_engine, "_z_fill_shareable", lambda _s: False)
    unshared = _server_solve(solve_cls, req, f"user.{which}")
    # The unshared count is the defect this fixes: impedance's Y, the excited
    # solve's Y and its own Z, and input_power's Y again.
    assert len(fills) == 4
    _numeric_equal(shared, unshared)


def _assert_other_frequency_refills(cls, fills):
    eng = _engine(cls, {}, 14.1)
    _solve_state(eng)
    n0 = len(fills)
    eng.builder.freq = 21.2
    moved = _solve_state(eng)
    assert len(fills) == n0 + 1, "a new frequency must refill"
    assert moved == _solve_state(_engine(cls, {}, 21.2))


# The height knob over a ground: it moves every wire and leaves the segment
# counts and the feed's arclength where they were, so nothing but the wire
# coordinates in the key tells the two engines apart. (A length knob would
# also move the feed, and pass against a key that forgot the wires.)
OVER_GROUND = {"freq": 14.1, "ground": True, "eps_r": 13.0, "sigma": 0.005}


def _assert_knob_change_refills(cls, fills):
    eng_a = _engine(cls, {"sy_h": 10.0}, 14.1, OVER_GROUND)
    _solve_state(eng_a)
    eng_b = _engine(cls, {"sy_h": 7.0}, 14.1, OVER_GROUND)
    # Hand B the slot A filled: only the key stands between B and A's Z.
    eng_b._z_fill_held = eng_a._z_fill_held
    n0 = len(fills)
    moved = _solve_state(eng_b)
    assert len(fills) == n0 + 1, "a knob change must refill"
    assert moved == _solve_state(_engine(cls, {"sy_h": 7.0}, 14.1, OVER_GROUND))


def test_a_different_frequency_on_the_same_engine_refills(fills, dipole_cls):
    _assert_other_frequency_refills(dipole_cls, fills)


def test_a_knob_change_refills_even_through_a_shared_slot(fills, dipole_cls):
    _assert_knob_change_refills(dipole_cls, fills)


@pytest.mark.parametrize(
    "check", [_assert_other_frequency_refills, _assert_knob_change_refills]
)
def test_the_controls_fail_against_a_key_that_ignores_the_configuration(
    check, fills, dipole_cls, monkeypatch
):
    monkeypatch.setattr(mw_engine, "_z_fill_key", lambda _cls, _kw: b"stale")
    monkeypatch.setattr(mw_engine, "_z_fill_live", lambda _sim: ())
    with pytest.raises(AssertionError):
        check(dipole_cls, fills)


def test_a_solver_whose_k_is_rebound_refills(fills, dipole_cls):
    """momwire's sweeps move k on the instance (`_set_k`) and fill again; the
    construction key alone would serve the first k's Z to every k."""
    eng = _engine(dipole_cls, {}, 14.1)
    wl = eng._wavelength_for(14.1)
    sim = eng._make_solver(wavelength=wl, share_z=True)
    sim.compute_y_matrix()
    ref = eng._make_solver(wavelength=wl)
    k2 = sim.k * 1.5
    sim._set_k(k2)
    ref._set_k(k2)
    n0 = len(fills)
    y = sim.compute_y_matrix()
    assert len(fills) == n0 + 1
    assert y.tobytes() == ref.compute_y_matrix().tobytes()


def test_a_sweep_after_a_solve_matches_a_fresh_engine(fills, dipole_cls):
    freqs = [13.9, 14.1, 14.35]
    eng = _engine(dipole_cls, {}, 14.1)
    _solve_state(eng)
    swept = np.asarray(eng.impedance_sweep(freqs))
    fresh = np.asarray(_engine(dipole_cls, {}, 14.1).impedance_sweep(freqs))
    assert swept.tobytes() == fresh.tobytes()


def test_the_key_ignores_port_voltages_and_nothing_else():
    base = {
        "wires": [np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]])],
        "feeds": [(0, 0.5, 1 + 0j)],
        "wavelength": 20.0,
        "junction_ports": [(3, 0j)],
        "node_gaps": [(0, "p0", 0j)],
        "cancel": object(),
    }
    key = mw_engine._z_fill_key(BSplineSolver, base)
    same = dict(
        base,
        feeds=[(0, 0.5, 2 - 1j)],
        junction_ports=[(3, 1j)],
        node_gaps=[(0, "p0", 5 + 0j)],
        cancel=None,
    )
    assert mw_engine._z_fill_key(BSplineSolver, same) == key
    for moved in (
        {"wavelength": np.nextafter(20.0, 21.0)},
        {"feeds": [(0, 0.25, 1 + 0j)]},
        {"junction_ports": [(4, 0j)]},
        {"node_gaps": [(0, "p1", 0j)]},
        {"wires": [np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 1e-9]])]},
        {"ground_eps": 14.0 - 1j},
    ):
        assert mw_engine._z_fill_key(BSplineSolver, dict(base, **moved)) != key
    assert mw_engine._z_fill_key(type("Other", (), {}), base) != key

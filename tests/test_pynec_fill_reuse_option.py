"""PyNEC's fill reuse on the PyNEC pane (pynec-accel 1.7.7, `set_fill_reuse`).

Wired the way momwire's `pair_reuse` is (AK#2165): the server probes the
installed PyNEC's `nec_context` live for `set_fill_reuse` and lists
`fill_reuse` in the PyNEC row's `model_kwargs` only where it is there; the
pane renders the served bool spec as a generic checkbox. Off by default; the
server's ANTENNAKNOBS_PYNEC_FILL_REUSE seeds an unset request, and an explicit
off wins. The engine tells EVERY context it makes the resolved choice, 1 or
0, so PyNEC's own PYNEC_FILL_REUSE cannot turn reuse on behind a request.

CI installs pynec-accel 1.7.6, which predates the method: the checks that
need the real reuse skip there (`served`). The spy checks wrap whatever
PyNEC is installed and run everywhere PyNEC does.
"""

from __future__ import annotations

import types

import numpy as np
import pytest

from antennaknobs.engines import pynec as pynec_mod
from antennaknobs.engines.pynec import FILL_REUSE_ENV, PyNECEngine, takes_fill_reuse
from antennaknobs.web import server  # noqa: F401  (registers the backends)
from antennaknobs.web import adapter
from antennaknobs.web.examples import REGISTRY

from test_pair_reuse_hint_2165 import fed_yagi

needs_pynec = pytest.mark.skipif(pynec_mod.nec is None, reason="PyNEC not installed")
served = pytest.mark.skipif(
    not takes_fill_reuse(),
    reason="this PyNEC's nec_context has no set_fill_reuse (pynec-accel < 1.7.7)",
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv(FILL_REUSE_ENV, raising=False)
    monkeypatch.delenv("PYNEC_FILL_REUSE", raising=False)


def _rows():
    return {
        r["name"]: r for r in adapter.backend_roster(have_pynec=True, have_nec2=True)
    }


def _hb9cv():
    """A small design on the multiport-Y route, whose readings each build a
    fresh context (`_make_real_context`) rather than using the baked one."""
    return REGISTRY.get("beams.hb9cv").builder_cls()


# --------------------------------------------------------------------------
# the probe and the served option
# --------------------------------------------------------------------------


def test_the_spec_is_a_plain_checkbox_off_by_default():
    spec = adapter.model_option_specs()["fill_reuse"]
    assert spec["kind"] == "bool" and spec["default"] is False


def test_the_probe_reads_the_installed_class(monkeypatch):
    class With:
        def set_fill_reuse(self, mode):
            pass

    class Without:
        pass

    monkeypatch.setattr(pynec_mod, "nec", types.SimpleNamespace(nec_context=With))
    assert takes_fill_reuse() is True
    monkeypatch.setattr(pynec_mod, "nec", types.SimpleNamespace(nec_context=Without))
    assert takes_fill_reuse() is False
    monkeypatch.setattr(pynec_mod, "nec", None)
    assert takes_fill_reuse() is False


@pytest.mark.parametrize("has", [True, False])
def test_offered_exactly_where_the_probe_finds_the_method(has, monkeypatch):
    monkeypatch.setattr(adapter, "takes_fill_reuse", lambda: has)
    rows = _rows()
    assert ("fill_reuse" in rows["pynec"]["model_kwargs"]) is has
    # Every other row, the NEC-2 tab that shares PyNEC's panel included, never.
    for name, row in rows.items():
        if name != "pynec":
            assert "fill_reuse" not in row["model_kwargs"], name


def test_the_live_roster_follows_the_installed_pynec():
    assert ("fill_reuse" in _rows()["pynec"]["model_kwargs"]) is takes_fill_reuse()


def test_it_is_on_the_hosted_allowlist_as_a_bool():
    check = adapter._HOSTED_MODEL_OPTIONS["fill_reuse"]
    assert check(True) is True and check(False) is False


# --------------------------------------------------------------------------
# the adapter: request, seed, and a PyNEC without it
# --------------------------------------------------------------------------


@needs_pynec
@pytest.mark.parametrize(
    ("env", "asked", "expect"),
    [
        (None, None, False),  # stock: off
        ("1", None, True),  # an unset request takes the seed
        ("on", None, True),
        ("1", False, False),  # an explicit off wins over the seed
        (None, True, True),
        ("0", True, True),
    ],
)
def test_the_adapter_resolves_request_and_seed(env, asked, expect, monkeypatch):
    monkeypatch.setattr(adapter, "takes_fill_reuse", lambda: True)
    if env is not None:
        monkeypatch.setenv(FILL_REUSE_ENV, env)
    req = {"solver": "pynec"}
    if asked is not None:
        req["model_options"] = {"fill_reuse": asked}
    eng = adapter._make_pynec_engine(req, fed_yagi(2))
    assert eng._fill_reuse is expect


def test_the_seed_moves_the_served_default(monkeypatch):
    monkeypatch.setenv(FILL_REUSE_ENV, "1")
    assert adapter.model_option_specs()["fill_reuse"]["default"] is True


@needs_pynec
def test_a_pynec_without_it_drops_the_request(monkeypatch):
    """No option, and a hand-made request for it changes nothing."""
    monkeypatch.setattr(adapter, "takes_fill_reuse", lambda: False)
    assert "fill_reuse" not in _rows()["pynec"]["model_kwargs"]
    eng = adapter._make_pynec_engine(
        {"solver": "pynec", "model_options": {"fill_reuse": True}}, fed_yagi(2)
    )
    assert eng._fill_reuse is False


# --------------------------------------------------------------------------
# the engine: every context it makes is told
# --------------------------------------------------------------------------


class _Spy:
    """A real nec_context that records `set_fill_reuse` calls, forwarding
    them only where the installed PyNEC has the method."""

    def __init__(self, inner):
        self._inner = inner
        self.modes = []

    def set_fill_reuse(self, mode):
        self.modes.append(mode)
        real = getattr(self._inner, "set_fill_reuse", None)
        if real is not None:
            real(mode)

    def __getattr__(self, name):
        return getattr(self._inner, name)


class _Lacking:
    """A real nec_context as an older PyNEC has it: no `set_fill_reuse`."""

    def __init__(self, inner):
        self._inner = inner

    def __getattr__(self, name):
        if name in ("set_fill_reuse", "get_fill_reuse_classes"):
            raise AttributeError(name)
        return getattr(self._inner, name)


def _spy_contexts(monkeypatch, cls=_Spy):
    made = []
    real = pynec_mod._new_context

    def new():
        c = cls(real())
        made.append(c)
        return c

    monkeypatch.setattr(pynec_mod, "_new_context", new)
    return made


def _exercise(eng):
    """Impedance, a sweep, currents and a pattern: every reading that can
    build a context of its own."""
    eng.impedance()
    eng.impedance_sweep([13.9, 14.1])
    eng.current_distribution()
    eng.far_field(n_theta=10, n_phi=12, del_theta=9, del_phi=30)


@needs_pynec
@pytest.mark.parametrize("asked", [True, False])
@pytest.mark.parametrize(
    "make", [lambda: fed_yagi(3), _hb9cv], ids=["baked", "multiport"]
)
def test_every_context_is_told_the_choice(asked, make, monkeypatch):
    # A stray PyNEC env must not matter: the engine never sends -1.
    monkeypatch.setenv("PYNEC_FILL_REUSE", "1")
    made = _spy_contexts(monkeypatch)
    eng = PyNECEngine(make(), ground="free", fill_reuse=asked)
    _exercise(eng)
    assert made, "no context was built, so this checks nothing"
    want = 1 if asked else 0
    assert all(c.modes == [want] for c in made), [c.modes for c in made]


@needs_pynec
def test_the_multiport_route_builds_several_contexts(monkeypatch):
    """So the parametrised check above covers `_make_real_context`, not only
    the baked one."""
    made = _spy_contexts(monkeypatch)
    _exercise(PyNECEngine(_hb9cv(), ground="free", fill_reuse=True))
    assert len(made) > 1


@needs_pynec
def test_a_context_without_the_method_is_left_alone(monkeypatch):
    _spy_contexts(monkeypatch, cls=_Lacking)
    z = PyNECEngine(fed_yagi(2), ground="free", fill_reuse=True).impedance()
    assert np.isfinite(np.asarray(z)).all()


def test_the_deck_only_context_is_left_alone(monkeypatch):
    """Without PyNEC the engine still resolves a deck for Download .nec."""
    monkeypatch.setattr(pynec_mod, "nec", None)
    eng = PyNECEngine(fed_yagi(2), ground="free", fill_reuse=True)
    assert isinstance(eng.c, pynec_mod._DeckOnlyContext)


# --------------------------------------------------------------------------
# the real reuse (pynec-accel >= 1.7.7)
# --------------------------------------------------------------------------


# Five elements, not fewer: measured with 1.7.7, PyNEC reports no classes
# (reuse declined, -1) on `fed_yagi` of 2-4 elements and 9803 on five.
def _z(builder, ground="free", **kw):
    eng = PyNECEngine(builder, ground=ground, **kw)
    z = np.asarray(eng.impedance(), dtype=complex)
    return z, eng.c.get_fill_reuse_classes()


@served
@pytest.mark.parametrize("ground", ["free", "pec", ("finite", 13.0, 0.005)])
def test_reuse_matches_off_to_1e_9(ground):
    b = fed_yagi(5)
    z_off, classes_off = _z(b, ground, fill_reuse=False)
    z_on, classes_on = _z(b, ground, fill_reuse=True)
    assert classes_off == -1
    assert classes_on > 0, "reuse did not run, so the agreement measures nothing"
    rel = np.max(np.abs(z_on - z_off) / np.abs(z_off))
    assert rel <= 1e-9, rel


@served
def test_off_is_bit_identical_to_not_asking(monkeypatch):
    """Off sends 0, which is PyNEC's own default: the same bytes as a context
    never told anything (the engine before this option)."""
    b = fed_yagi(5)
    z_off, _ = _z(b, fill_reuse=False)
    monkeypatch.setattr(PyNECEngine, "_apply_fill_reuse", lambda self, c: None)
    z_untold, classes = _z(b, fill_reuse=False)
    assert classes == -1
    assert np.array_equal(z_off, z_untold)


@served
def test_a_stray_pynec_env_cannot_turn_it_on(monkeypatch):
    monkeypatch.setenv("PYNEC_FILL_REUSE", "1")
    _, classes = _z(fed_yagi(5), fill_reuse=False)
    assert classes == -1
    # ...and the same env really does turn it on for a context told -1, so
    # the line above is a measurement, not an env PyNEC ignores.
    monkeypatch.setattr(
        PyNECEngine, "_apply_fill_reuse", lambda self, c: c.set_fill_reuse(-1)
    )
    _, classes = _z(fed_yagi(5), fill_reuse=False)
    assert classes > 0

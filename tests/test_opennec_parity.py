"""OpenNEC against PyNEC over the catalog: the same NEC-2 on two bindings.

Both engines are `PyNECEngine`'s model — the same cards from the same code,
OpenNEC's solved through pyopennec's porty port-admittance interface — so on
one deck they differ only by the NEC-2 implementation underneath (OpenNEC, a
C rewrite of nec2c, against nec2++). pyopennec's own suite puts
that at ~1e-3 on Z; these bars are the brief's:

    impedance    |dZ| / |Z|                       <= 2e-3 (each port, each sweep point)
    currents     max |dI| / max |I|               <= 2e-3
    pattern      |dG| within 30 dB of the peak    <= 0.1 dB

The set covers free space, PEC, Sommerfeld and reflection-coefficient
grounds, LD loads (lumped and resistive termination), a TL network on the
multiport-Y route, a native NT card, two-port lumped coupling, multi-port
excitation, a three-point frequency sweep and a far-field pattern on every
case.

Two cases carry a documented, measured exception rather than being dropped
(measured 2026-11-13 against nec2c 1.3.1 as the tie-breaker):

* ``dipoles.short_dipole_loaded``: an 818-ohm loading coil on the feed cancels
  the short dipole's capacitive reactance to |Z| = 18.6 ohm, so a 2.6e-5
  difference in the antenna's own reactance reads as 2.9e-3 of |Z|. nec2c
  sits between the two engines (OpenNEC 1.2e-3 from it, PyNEC 1.7e-3). The
  feed current is the structure's largest and is V/Z, so the currents read
  the same 2.9e-3. Its Z and current bars are 5e-3.
* ``verticals.four_square``: a phased array with a deep back null. Its port Z
  agrees with nec2c to 4e-5 on OpenNEC and to 1.5e-3 on PyNEC, and that
  nec2++ offset moves the -27.6 dB null by 0.105 dB. Its pattern bar is
  applied within 25 dB of the peak (measured worst there: 0.047 dB).

Skips cleanly when either binding is missing. The guard against comparing
PyNEC with itself is in `_solve` (PyNEC must have made every context, and
OpenNEC none of them but at least one porty solve) and in
`_assert_two_engines_ran` (a parity that is bit-identical did not run two
engines); `test_routing_opennec_to_pynec_fails_the_parity` proves both trip.
"""

from __future__ import annotations

import warnings

import numpy as np
import pytest

from antennaknobs.engines import opennec as opennec_mod
from antennaknobs.engines import pynec as pynec_mod
from antennaknobs.engines.opennec import OpenNECEngine
from antennaknobs.engines.pynec import PyNECEngine

pytestmark = pytest.mark.skipif(
    pynec_mod.nec is None or opennec_mod.porty is None,
    reason="needs both PyNEC (pynec-accel) and pyopennec (porty)",
)

SOMMERFELD = ("finite", 13.0, 0.005)
REFL_COEF = ("finite-fast", 13.0, 0.005)

Z_BAR = 2e-3
I_BAR = 2e-3
G_BAR_DB = 0.1
G_WINDOW_DB = 30.0

# (id, design, ground, engine kwargs, z bar, pattern window dB)
CASES = [
    ("invvee-free", "dipoles.invvee", "free", {}, Z_BAR, G_WINDOW_DB),
    ("invvee-pec", "dipoles.invvee", "pec", {}, Z_BAR, G_WINDOW_DB),
    ("invvee-sommerfeld", "dipoles.invvee", SOMMERFELD, {}, Z_BAR, G_WINDOW_DB),
    ("vertical-reflcoef", "verticals.vertical", REFL_COEF, {}, Z_BAR, G_WINDOW_DB),
    ("yagi-free", "beams.yagi", "free", {}, Z_BAR, G_WINDOW_DB),
    ("trap-dipole-LD", "multiband.trap_dipole", "free", {}, Z_BAR, G_WINDOW_DB),
    ("loaded-short-LD", "dipoles.short_dipole_loaded", "free", {}, 5e-3, G_WINDOW_DB),
    ("rhombic-LD-sommerfeld", "wire.rhombic", SOMMERFELD, {}, Z_BAR, G_WINDOW_DB),
    ("g5rv-TL", "broadband.g5rv", "free", {}, Z_BAR, G_WINDOW_DB),
    ("hb9cv-network", "beams.hb9cv", "free", {}, Z_BAR, G_WINDOW_DB),
    (
        "coupled-pair-reducer",
        "arrays.lumped_coupled_pair",
        "free",
        {},
        Z_BAR,
        G_WINDOW_DB,
    ),
    (
        "coupled-pair-NT",
        "arrays.lumped_coupled_pair",
        "free",
        {"native_nt": True},
        Z_BAR,
        G_WINDOW_DB,
    ),
    ("bowtie-1x2-multiport", "arrays.bowtiearray1x2", "free", {}, Z_BAR, G_WINDOW_DB),
    ("four-square-multiport-pec", "verticals.four_square", "pec", {}, Z_BAR, 25.0),
]

BINDING = {PyNECEngine: "PyNEC", OpenNECEngine: "porty"}


def _builder(design):
    from antennaknobs.web import server  # noqa: F401 — registers the catalog
    from antennaknobs.web.examples import REGISTRY

    return REGISTRY.get(design).builder_cls()


def _spy_on_contexts(monkeypatch, made):
    """Record the module of every PyNEC context any engine creates."""
    real = pynec_mod._new_context

    def spy():
        c = real()
        made.append(type(c).__module__.split(".")[0])
        return c

    monkeypatch.setattr(pynec_mod, "_new_context", spy)


def _binding(eng, made):
    """What an engine solved through: porty when it logged porty solves and
    made no PyNEC context, else the module behind its contexts."""
    if getattr(eng, "solve_log", None) and not made:
        return "porty"
    return type(getattr(eng, "c", None)).__module__.split(".")[0]


def _solve(engine_cls, design, ground, kwargs, monkeypatch, want=None):
    """Z, currents and pattern from one engine (one instance, as the web lane
    reads them), and a 3-point sweep from a second. Every solve must go
    through the engine's own binding."""
    made: list[str] = []
    _spy_on_contexts(monkeypatch, made)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        eng = engine_cls(_builder(design), ground=ground, **kwargs)
        z = np.asarray(eng.impedance(), complex).ravel()
        cur = eng.current_distribution()
        ff = eng.far_field(n_theta=18, n_phi=36, del_theta=5, del_phi=10)
        b2 = _builder(design)
        f0 = b2.freq
        sweeper = engine_cls(b2, ground=ground, **kwargs)
        sweep = sweeper.impedance_sweep(np.linspace(0.97 * f0, 1.03 * f0, 3))
    want = want or BINDING[engine_cls]
    # The sweep too on porty, where nothing else would show which ran.
    for e in (eng, sweeper) if want == "porty" else (eng,):
        got = _binding(e, made)
        assert got == want, f"{engine_cls.__name__} solved through {got}, not {want}"
    if want == "PyNEC":
        # Every context the readings made, through the module factory.
        assert made and set(made) == {want}, (
            f"{engine_cls.__name__} solved through {sorted(set(made))}, not {want}"
        )
    monkeypatch.undo()
    currents = np.concatenate([np.asarray(w.knot_currents) for w in cur])
    return {
        "z": z,
        "sweep": np.asarray(sweep, complex),
        "currents": currents,
        "gain": np.asarray(ff.rings, float),
    }


def _errors(p, o, window_db):
    dz = float(np.max(np.abs(o["z"] - p["z"]) / np.abs(p["z"])))
    dz_sweep = float(np.max(np.abs(o["sweep"] - p["sweep"]) / np.abs(p["sweep"])))
    di = float(np.max(np.abs(o["currents"] - p["currents"])))
    di /= float(np.max(np.abs(p["currents"])))
    lit = p["gain"] >= p["gain"].max() - window_db
    dg = float(np.max(np.abs(o["gain"] - p["gain"])[lit]))
    return {"z": max(dz, dz_sweep), "currents": di, "gain_db": dg}


def _assert_two_engines_ran(p, o):
    """Bit-identical answers mean one engine ran twice: two NEC-2
    implementations never agree to the last bit on a real deck."""
    assert not np.array_equal(p["z"], o["z"]), "identical Z: one binding ran twice"


@pytest.mark.parametrize(
    "design, ground, kwargs, z_bar, window_db",
    [c[1:] for c in CASES],
    ids=[c[0] for c in CASES],
)
def test_opennec_agrees_with_pynec(
    design, ground, kwargs, z_bar, window_db, monkeypatch
):
    p = _solve(PyNECEngine, design, ground, kwargs, monkeypatch)
    o = _solve(OpenNECEngine, design, ground, kwargs, monkeypatch)
    _assert_two_engines_ran(p, o)
    err = _errors(p, o, window_db)
    assert p["z"].shape == o["z"].shape
    assert err["z"] <= z_bar, err
    assert err["currents"] <= max(I_BAR, z_bar), err
    assert err["gain_db"] <= G_BAR_DB, err


def test_the_set_covers_what_it_claims():
    names = {c[1] for c in CASES}
    grounds = {c[2] if isinstance(c[2], str) else c[2][0] for c in CASES}
    assert len(CASES) >= 8
    assert grounds == {"free", "pec", "finite", "finite-fast"}
    assert {"multiband.trap_dipole", "wire.rhombic"} <= names  # LD
    assert {"broadband.g5rv", "arrays.lumped_coupled_pair"} <= names  # TL / NT
    assert any(c[3].get("native_nt") for c in CASES)
    multiport = [
        c for c in CASES if c[1] in ("arrays.bowtiearray1x2", "verticals.four_square")
    ]
    assert multiport


def test_multiport_cases_really_drive_several_ports(monkeypatch):
    p = _solve(PyNECEngine, "verticals.four_square", "pec", {}, monkeypatch)
    assert p["z"].size == 4


# --------------------------------------------------------------------------
# adversarial: the parity must not pass with PyNEC on both sides
# --------------------------------------------------------------------------


class _PyNECAsOpenNEC(PyNECEngine):
    """The silent mistake the guards exist for: PyNEC answering for OpenNEC."""

    engine_label = "OpenNEC"


def test_routing_opennec_to_pynec_fails_the_parity(monkeypatch):
    """Answer for OpenNEC with PyNEC and the parity body must fail, both on
    the binding check and, with that check out of the way, on the
    bit-identity check."""
    design, ground = "dipoles.invvee", "free"
    p = _solve(PyNECEngine, design, ground, {}, monkeypatch)

    with pytest.raises(AssertionError, match="solved through"):
        _solve(_PyNECAsOpenNEC, design, ground, {}, monkeypatch, want="porty")

    # Without the binding check the numbers alone still give it away.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        eng = _PyNECAsOpenNEC(_builder(design), ground=ground)
        fake = {"z": np.asarray(eng.impedance(), complex).ravel()}
    with pytest.raises(AssertionError, match="one binding ran twice"):
        _assert_two_engines_ran(p, fake)

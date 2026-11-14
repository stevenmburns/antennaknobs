"""The opennec engine: PyNECEngine's model on pyopennec's porty interface.

`OpenNECEngine` keeps PyNECEngine's cards and readings and solves them through
`pyopennec.porty` (one port-admittance solve per frequency) instead of a
PyNEC-shaped binding. What is worth testing here:

- the solves are porty's and never touch the pybind module
  (``pyopennec._core`` / ``nec_context``), which is due to leave pyopennec: a
  subprocess with it blocked runs every route, the web lane included;
- one porty solve per frequency per build, however many readings and ports;
- with pyopennec absent, the engine is off the CLI roster with a sentence
  naming the package, a solve raises ImportError naming it, and the cards are
  still recorded (the deck writer never needed the binding, AK#1387);
- what porty cannot express refuses by name;
- a buried deck refuses as on the NEC-2 lane, and the roster says so.

The import-blocked cases run in a subprocess, as
test_export_without_pynec_1387.py does for PyNEC: the venv here usually has
the package, so an in-process test would prove nothing.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
import warnings

import numpy as np
import pytest

from antennaknobs.engines import opennec as opennec_mod
from antennaknobs.engines import pynec as pynec_mod
from antennaknobs.engines.opennec import OpenNECEngine
from antennaknobs.engines.pynec import PyNECEngine

needs_opennec = pytest.mark.skipif(
    opennec_mod.porty is None, reason="pyopennec (porty) not installed"
)


def _invvee():
    from antennaknobs.designs.dipoles.invvee import Builder

    return Builder()


def _catalog(name):
    from antennaknobs.web import server  # noqa: F401 — registers the catalog
    from antennaknobs.web.examples import REGISTRY

    return REGISTRY.get(name).builder_cls()


# --------------------------------------------------------------------------
# what the engine really solves through
# --------------------------------------------------------------------------


@needs_opennec
def test_the_solves_are_portys(monkeypatch):
    """Every solve is a `porty.Structure.solve` call, counted at the class
    itself so `solve_log` cannot report solves that did not run."""
    calls = []
    real = opennec_mod.porty.Structure.solve

    def spy(self, freqs, *args, **kwargs):
        calls.append(tuple(float(f) for f in freqs))
        return real(self, freqs, *args, **kwargs)

    monkeypatch.setattr(opennec_mod.porty.Structure, "solve", spy)
    eng = OpenNECEngine(_invvee(), ground="free")
    assert OpenNECEngine.nec_module() is opennec_mod.porty
    assert isinstance(eng.c, opennec_mod._CardDeck)
    eng.impedance()
    assert calls and calls == eng.solve_log


def test_the_pynec_engine_is_unchanged_by_the_seam():
    """PyNECEngine still answers PyNEC (or None), and still makes contexts
    through `pynec._new_context`, which existing tests monkeypatch."""
    assert PyNECEngine.nec_module() is pynec_mod.nec
    assert OpenNECEngine.engine_label == "OpenNEC"
    assert PyNECEngine.engine_label == "PyNEC"


@needs_opennec
def test_a_solve_returns_a_dipole_impedance():
    z = complex(OpenNECEngine(_invvee(), ground="free").impedance()[0])
    assert 30 < z.real < 120, z


# The pybind layer blocked, as it will be once pyopennec drops it. Today
# pyopennec/__init__.py imports ``_core`` unconditionally, so the package is
# stood in for by a bare one over the same directories: what imports from it
# is then exactly the porty module and its C extension.
NO_PYBIND = """
import importlib.util, sys, types
spec = importlib.util.find_spec("pyopennec")
pkg = types.ModuleType("pyopennec")
pkg.__path__ = list(spec.submodule_search_locations)
pkg.__spec__ = spec
sys.modules["pyopennec"] = pkg
sys.modules["pyopennec._core"] = None
"""


@needs_opennec
def test_every_route_solves_with_the_pybind_module_blocked():
    """Card route (plain, LD loads, native NT, multi-feed) and multiport route
    (line, virtual port, distributed port, tuner two-port), over each ground,
    through impedance, currents, pattern and a sweep — and the web lane."""
    code = NO_PYBIND + textwrap.dedent("""
        import warnings
        warnings.simplefilter("ignore")
        from antennaknobs.engines.opennec import OpenNECEngine, porty
        from antennaknobs.web import opennec_backend, server
        from antennaknobs.web.examples import REGISTRY
        assert porty is not None and opennec_backend.HAVE_OPENNEC
        cases = [
            ("dipoles.invvee", "free", {}),
            ("multiband.trap_dipole", ("finite", 13.0, 0.005), {}),
            ("arrays.lumped_coupled_pair", "free", {"native_nt": True}),
            ("verticals.four_square", "pec", {}),
            ("broadband.g5rv", ("finite-fast", 13.0, 0.005), {}),
            ("verticals.challenger", ("finite", 13.0, 0.005), {}),
            ("wire.zepp", "free", {}),
            ("loops.skyloop_lmatch", "free", {}),
        ]
        for name, ground, kw in cases:
            b = REGISTRY.get(name).builder_cls()
            eng = OpenNECEngine(b, ground=ground, **kw)
            z = eng.impedance()
            eng.current_distribution()
            ff = eng.far_field(n_theta=18, n_phi=36, del_theta=5, del_phi=10)
            sw = eng.impedance_sweep([0.98 * b.freq, 1.02 * b.freq])
            assert abs(complex(z[0])) > 0 and ff.max_gain > -50 and len(sw) == 2
            assert eng.solve_log
        server._HOSTED = False
        req = {"geometry": "dipoles.invvee", "measurement_freq_mhz": 28.47}
        out = server.solve({**req, "solver": "opennec"})
        assert out["solver"] == "opennec", out["solver"]
        assert len(opennec_backend.pattern(req)["gain_dbi"]) == 46
        assert sys.modules["pyopennec._core"] is None
        assert not hasattr(sys.modules["pyopennec"], "nec_context")
        print("ok", len(cases))
    """)
    r = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=300
    )
    assert r.returncode == 0, r.stderr[-3000:]
    assert r.stdout.startswith("ok 8"), r.stdout


# --------------------------------------------------------------------------
# one porty solve per frequency
# --------------------------------------------------------------------------


@needs_opennec
def test_one_solve_per_frequency_on_a_three_port_network():
    """tri_moxon: three real ports behind lines and a virtual driver. The
    pybind engine made 3 + 7 + 4 NEC runs for these three readings (one per
    port per Y, Y twice in current_distribution); porty makes one solve."""
    eng = OpenNECEngine(_catalog("verticals.tri_moxon"), ground="free")
    assert eng._use_reducer and len(eng._real_port_names) == 3
    eng.impedance()
    eng.current_distribution()
    eng.far_field(n_theta=18, n_phi=36, del_theta=5, del_phi=10)
    assert eng.solve_log == [(opennec_mod._freq_key(eng.builder.freq),)]

    b = _catalog("verticals.tri_moxon")
    sweeper = OpenNECEngine(b, ground="free")
    freqs = np.linspace(0.95, 1.05, 7) * b.freq
    zs = sweeper.impedance_sweep(freqs)
    assert zs.shape[0] == 7
    assert sweeper.solve_log == [tuple(opennec_mod._freq_key(f) for f in freqs)]
    # A reading at a swept frequency (the middle one) reuses that solve.
    sweeper.impedance()
    sweeper.current_distribution()
    assert len(sweeper.solve_log) == 1


@needs_opennec
def test_a_distributed_port_is_its_segments_contracted():
    """wire.sterba_tl's distributed ports drive every segment of their wires
    at V/S: Y_port = W^T Y_seg W, one porty port per segment."""
    eng = OpenNECEngine(_catalog("wire.sterba_tl"), ground="free")
    eng.impedance()
    n_seg = sum(len(eng._port_drive_points[n]) for n in eng._real_port_names)
    assert eng._W.shape == (n_seg, len(eng._real_port_names)) and n_seg > 1
    np.testing.assert_allclose(eng._W.sum(axis=0), 1.0)


# --------------------------------------------------------------------------
# refusals
# --------------------------------------------------------------------------


@needs_opennec
def test_the_mininec_ground_serves_z_and_refuses_the_pattern():
    """The MININEC-type ground's currents are the perfect ground's (served);
    its pattern reads the soil through a cliff-mode RP, which porty's far
    field does not have."""
    eng = OpenNECEngine(_invvee(), ground=("mininec", 13.0, 0.005))
    pec = OpenNECEngine(_invvee(), ground="pec")
    assert complex(eng.impedance()[0]) == complex(pec.impedance()[0])
    with pytest.raises(NotImplementedError, match="MININEC-type ground"):
        eng.far_field(n_theta=18, n_phi=36, del_theta=5, del_phi=10)


def test_a_legacy_tl_card_refuses_by_name():
    from fixtures.delta_looparray_with_tls import Builder

    with pytest.raises(NotImplementedError, match="build_tls"):
        OpenNECEngine(Builder(), ground="free")


def test_fill_reuse_is_accepted_and_means_nothing(monkeypatch):
    """The web lane and CLI may still pass it; porty has no fill choice, and
    the roster does not offer it."""
    monkeypatch.setenv(pynec_mod.FILL_REUSE_ENV, "1")
    eng = OpenNECEngine(_invvee(), ground="free", fill_reuse=True)
    assert not hasattr(eng.c, "set_fill_reuse")
    import antennaknobs.web.server  # noqa: F401
    from antennaknobs.web import adapter

    assert adapter._offers_fill_reuse(adapter._BACKENDS_BY_NAME["opennec"]) is False


@needs_opennec
def test_no_nec2pp_sommerfeld_warning():
    """#448 is nec2++'s defect; a low horizontal run over Sommerfeld ground
    that would warn on an old PyNEC is silent here."""
    from antennaknobs.engines.pynec import _somm_low_wire_risk

    eng = OpenNECEngine(_catalog("wire.longwire"), ground=("finite", 13.0, 0.005))
    assert _somm_low_wire_risk(eng.tups, 80.0)
    with warnings.catch_warnings():
        warnings.simplefilter("error", RuntimeWarning)
        eng._warn_if_somm_low_wires(80.0)


# --------------------------------------------------------------------------
# buried decks refuse (the roster's sentence quotes the old measurement)
# --------------------------------------------------------------------------


def test_a_buried_deck_refuses_as_on_the_nec2_lane():
    """NEC-2 has no below-ground medium. The pybind route solved the catalog's
    buried dipole as if in air (5 cm above vs below: 1.11x, momwire ~10x);
    the engine now refuses it by name, before any solve."""
    from antennaknobs.designs.specialty.buried_dipole import Builder

    b = Builder()
    b.depth = 0.05
    with pytest.raises(NotImplementedError, match="below z=0"):
        OpenNECEngine(b, ground=("finite", 10.0, 0.002))
    b.depth = -0.05
    OpenNECEngine(b, ground=("finite", 10.0, 0.002))  # above: served


def test_the_roster_marks_opennec_buried_false_with_its_own_sentence():
    import antennaknobs.web.server  # noqa: F401
    from antennaknobs.web import adapter

    spec = adapter._BACKENDS_BY_NAME["opennec"]
    assert adapter._backend_serves_buried(spec) is False
    sentence = adapter._backend_buried_refusal(spec)
    assert sentence.startswith("OpenNEC cannot model")
    assert "11%" in sentence
    assert adapter._backend_buried_issue(spec) == "antennaknobs#1167"


@needs_opennec
def test_junction_and_vertex_ports_refuse_by_name():
    for name, word in (
        ("wire.sterba_bl", "PortAtEnd"),
        ("dipoles.invvee_apex", "PortAtVertex"),
    ):
        with pytest.raises(ValueError, match=word):
            OpenNECEngine(_catalog(name), ground="free")


# --------------------------------------------------------------------------
# pyopennec absent
# --------------------------------------------------------------------------

BLOCK = "import sys; sys.modules['pyopennec'] = None\n"


def _run(code: str) -> str:
    r = subprocess.run(
        [sys.executable, "-c", BLOCK + textwrap.dedent(code)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert r.returncode == 0, r.stderr[-2000:]
    return r.stdout


def test_without_pyopennec_the_cli_names_the_missing_package():
    out = _run("""
        import argparse
        import importlib
        cli = importlib.import_module("antennaknobs.cli")
        assert "opennec" not in cli.ENGINE_CLASSES, sorted(cli.ENGINE_CLASSES)
        try:
            cli.parse_engine_spec("opennec")
        except argparse.ArgumentTypeError as e:
            msg = str(e)
        else:
            raise SystemExit("parse_engine_spec accepted opennec")
        assert "pyopennec" in msg and "not installed" in msg, msg
        print("ok", msg)
    """)
    assert out.startswith("ok")


def test_without_pyopennec_a_solve_raises_naming_the_package():
    out = _run("""
        import importlib
        from antennaknobs.engines.opennec import OpenNECEngine, _CardDeck
        B = importlib.import_module("antennaknobs.designs.dipoles.invvee").Builder
        eng = OpenNECEngine(B())
        assert isinstance(eng.c, _CardDeck) and eng.c.wires and eng.c.ex
        try:
            eng.impedance()
        except ImportError as e:
            assert "pyopennec" in str(e), e
            print("ok")
        else:
            raise SystemExit("impedance() did not raise")
    """)
    assert out.startswith("ok")


def test_without_pyopennec_the_web_roster_omits_it():
    out = _run("""
        from antennaknobs.web import opennec_backend, server
        assert opennec_backend.HAVE_OPENNEC is False
        assert server._have_opennec() is False
        assert server._external_backend({"solver": "opennec"}) is None
        print("ok")
    """)
    assert out.startswith("ok")


def test_the_cli_offers_it_exactly_when_the_binding_imports():
    import importlib

    cli = importlib.import_module("antennaknobs.cli")
    assert ("opennec" in cli.ENGINE_CLASSES) is (opennec_mod.porty is not None)

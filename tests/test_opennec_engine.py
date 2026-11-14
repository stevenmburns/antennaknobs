"""The opennec engine: PyNECEngine on the pyopennec binding.

`OpenNECEngine` changes one thing about `PyNECEngine` — where its contexts
come from — so most of what is worth testing is that the one thing really
changed, and that the optional-package contract is PyNEC's:

- the contexts are pyopennec's, not PyNEC's (the parity suite in
  `test_opennec_parity.py` would otherwise be comparing PyNEC with itself);
- with pyopennec absent, the engine is off the CLI roster with a sentence
  naming the package, a solve raises ImportError naming it, and the deck
  writer still works (the deck-only stand-in, as for PyNEC, AK#1387);
- PyNEC-only features are gated on live probes of the binding: no
  ``set_fill_reuse`` on pyopennec, so nothing is offered or sent;
- the buried refusal the roster serves for OpenNEC is a measurement.

The import-blocked cases run in a subprocess with ``sys.modules["pyopennec"]
= None``, as test_export_without_pynec_1387.py does for PyNEC: the venv here
usually has the package, so an in-process test would prove nothing.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
import warnings

import pytest

from antennaknobs.engines import opennec as opennec_mod
from antennaknobs.engines import pynec as pynec_mod
from antennaknobs.engines.opennec import OpenNECEngine
from antennaknobs.engines.pynec import PyNECEngine

needs_opennec = pytest.mark.skipif(
    opennec_mod.pyopennec is None, reason="pyopennec not installed"
)


def _invvee():
    from antennaknobs.designs.dipoles.invvee import Builder

    return Builder()


# --------------------------------------------------------------------------
# which binding the engine really drives
# --------------------------------------------------------------------------


@needs_opennec
def test_the_context_is_pyopennecs():
    eng = OpenNECEngine(_invvee(), ground="free")
    assert OpenNECEngine.nec_module() is opennec_mod.pyopennec
    assert isinstance(eng.c, opennec_mod.pyopennec.nec_context)
    assert type(eng.c).__module__.split(".")[0] == "pyopennec"


@needs_opennec
def test_every_context_comes_from_the_binding(monkeypatch):
    """The multiport-Y route builds a context per port solve; each must be
    pyopennec's, not only the baked one."""
    from antennaknobs.web import server  # noqa: F401 — registers the catalog
    from antennaknobs.web.examples import REGISTRY

    made = []
    real = opennec_mod._new_context

    def spy():
        c = real()
        made.append(type(c).__module__)
        return c

    monkeypatch.setattr(opennec_mod, "_new_context", spy)
    eng = OpenNECEngine(REGISTRY.get("beams.hb9cv").builder_cls(), ground="free")
    assert eng._use_reducer
    eng.impedance()
    eng.current_distribution()
    assert len(made) > 1
    assert all(m.split(".")[0] == "pyopennec" for m in made), made


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


# --------------------------------------------------------------------------
# PyNEC-only features follow the binding's live probe
# --------------------------------------------------------------------------


def test_fill_reuse_is_a_live_probe_of_the_binding(monkeypatch):
    import types

    class With:
        def set_fill_reuse(self, _mode):
            pass

    monkeypatch.setattr(
        opennec_mod, "pyopennec", types.SimpleNamespace(nec_context=With)
    )
    assert opennec_mod.takes_fill_reuse() is True
    monkeypatch.setattr(
        opennec_mod, "pyopennec", types.SimpleNamespace(nec_context=object)
    )
    assert opennec_mod.takes_fill_reuse() is False
    monkeypatch.setattr(opennec_mod, "pyopennec", None)
    assert opennec_mod.takes_fill_reuse() is False


@needs_opennec
def test_pyopennec_has_no_fill_reuse_so_none_is_sent(monkeypatch):
    """Asked for it (or seeded by the env) the engine still solves: the setter
    is only called where the context has one, and pyopennec's does not."""
    monkeypatch.setenv(pynec_mod.FILL_REUSE_ENV, "1")
    assert opennec_mod.takes_fill_reuse() is False
    eng = OpenNECEngine(_invvee(), ground="free", fill_reuse=True)
    assert not hasattr(eng.c, "set_fill_reuse")
    assert abs(complex(eng.impedance()[0])) > 0


@needs_opennec
def test_no_nec2pp_sommerfeld_warning():
    """#448 is nec2++'s defect; a low horizontal run over Sommerfeld ground
    that would warn on an old PyNEC is silent here."""
    from antennaknobs.web import server  # noqa: F401
    from antennaknobs.web.examples import REGISTRY

    eng = OpenNECEngine(
        REGISTRY.get("wire.beverage").builder_cls(), ground=("finite", 13.0, 0.005)
    )
    with warnings.catch_warnings():
        warnings.simplefilter("error", RuntimeWarning)
        eng._warn_if_somm_low_wires(20.0)


# --------------------------------------------------------------------------
# the buried row is a measurement (the roster's sentence quotes it)
# --------------------------------------------------------------------------


@needs_opennec
def test_opennec_solves_a_buried_deck_without_noticing_the_interface():
    """5 cm above vs 5 cm below on the catalog's buried dipole: measured 1.11x
    (PyNEC 1.12x, momwire ~10x). OpenNEC refuses nothing and barely moves —
    which is why the roster marks it False with a sentence."""
    from antennaknobs.designs.specialty.buried_dipole import Builder

    def z(depth):
        b = Builder()
        b.depth = depth
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return abs(
                complex(OpenNECEngine(b, ground=("finite", 10.0, 0.002)).impedance()[0])
            )

    above, below = z(-0.05), z(0.05)
    swing = max(above, below) / min(above, below)
    assert 1.0 < swing < 1.5, swing


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
    from antennaknobs.web import server  # noqa: F401
    from antennaknobs.web.examples import REGISTRY

    for name, word in (
        ("wire.sterba_bl", "PortAtEnd"),
        ("dipoles.invvee_apex", "PortAtVertex"),
    ):
        with pytest.raises(ValueError, match=word):
            OpenNECEngine(REGISTRY.get(name).builder_cls(), ground="free")


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
        from antennaknobs.engines.opennec import OpenNECEngine
        from antennaknobs.engines.pynec import _DeckOnlyContext
        B = importlib.import_module("antennaknobs.designs.dipoles.invvee").Builder
        eng = OpenNECEngine(B())
        assert isinstance(eng.c, _DeckOnlyContext)
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
    assert ("opennec" in cli.ENGINE_CLASSES) is (opennec_mod.pyopennec is not None)

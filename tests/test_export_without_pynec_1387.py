"""Download .nec must not need PyNEC (#1387).

AC6LA's "Download .nec" returned a 500 on the QRZ Windows thread: `nec_export`
constructs `PyNECEngine`, whose module imported PyNEC at the top and whose
constructor opened a PyNEC context. PyNEC is optional by design (GPL, out of
every extra and out of the frozen bundle), so writing a text deck was only
available where the engine was installed. The engine now builds against a
deck-only context when PyNEC is absent; solving still needs PyNEC and says so.

Each test runs in a subprocess with `sys.modules["PyNEC"] = None`, which makes
`import PyNEC` raise ImportError whether or not pynec-accel is installed in the
venv — the venv here usually has it, so an in-process test would prove nothing.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap

import pytest

BLOCK = "import sys; sys.modules['PyNEC'] = None\n"


def _run(code: str) -> str:
    r = subprocess.run(
        [sys.executable, "-c", BLOCK + textwrap.dedent(code)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert r.returncode == 0, r.stderr[-2000:]
    return r.stdout


def test_export_nec_writes_a_deck_with_pynec_blocked():
    out = _run("""
        import importlib
        from antennaknobs.nec_export import export_nec
        B = importlib.import_module("antennaknobs.designs.dipoles.invvee").Builder
        deck = export_nec(B())
        lines = deck.splitlines()
        assert any(l.startswith("GW") for l in lines), deck
        assert any(l.startswith("EX") for l in lines), deck
        assert lines[-1].strip() == "EN", deck
        print("ok", len(lines))
    """)
    assert out.startswith("ok")


def test_export_nec_with_loads_and_ground_with_pynec_blocked():
    """A Load-only network (the path that emits NT/LD cards through the
    context) and a Sommerfeld ground: every card the constructor emits goes
    through the deck-only context, none may raise."""
    out = _run("""
        import importlib
        from antennaknobs.nec_export import export_nec
        B = importlib.import_module("antennaknobs.designs.dipoles.short_dipole_loaded").Builder
        deck = export_nec(B(), ground=("finite", 13.0, 0.005))
        assert "GN" in deck and "LD" in deck, deck
        print("ok")
    """)
    assert out.startswith("ok")


def test_solve_without_pynec_raises_naming_the_package():
    out = _run("""
        import importlib
        from antennaknobs.engines.pynec import PyNECEngine
        B = importlib.import_module("antennaknobs.designs.dipoles.invvee").Builder
        eng = PyNECEngine(B())
        try:
            eng.impedance()
        except ImportError as e:
            assert "pynec-accel" in str(e), e
            print("ok")
        else:
            raise SystemExit("impedance() did not raise")
    """)
    assert out.startswith("ok")


def test_web_layer_still_reports_pynec_absent():
    out = _run("""
        from antennaknobs.web import pynec_backend
        assert pynec_backend.HAVE_PYNEC is False
        print("ok")
    """)
    assert out.startswith("ok")


@pytest.mark.skipif(
    subprocess.run(
        [sys.executable, "-c", "import PyNEC"], capture_output=True
    ).returncode
    != 0,
    reason="pynec-accel not installed: the with-PyNEC twin cannot run here",
)
def test_deck_is_identical_with_and_without_pynec():
    """The deck-only context must not change the deck: same bytes as the
    real-context path writes when PyNEC is present."""
    code = """
        import importlib
        from antennaknobs.nec_export import export_nec
        B = importlib.import_module("antennaknobs.designs.dipoles.invvee").Builder
        print(export_nec(B(), ground=("finite", 13.0, 0.005)), end="")
    """
    with_pynec = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(code)], capture_output=True, text=True
    )
    assert with_pynec.returncode == 0, with_pynec.stderr[-1000:]
    assert _run(code) == with_pynec.stdout

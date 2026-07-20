"""Multi-source EX 6 reference via Y-matrix superposition (issue #463).

nec2c has no port current source, and the single-R_BIG emulation (issue #442)
can't force N simultaneous port currents — on a phased active-feed deck the
per-feed readout comes out R_BIG-invariant, so the subtraction manufactures a
huge negative resistance (3vertical.nec: feed 0 reads −18,972 + 258j, engines
disagree at ΔΓ 0.43). ``superposition_reference`` recovers the physics with
native voltage drives: N solves → port admittance matrix → invert to Z →
compose the driving-point impedances V = Z·I for the deck's current vector.

The strongest check is the physics oracle: a multiport driven by known port
currents has a driving-point impedance the *engine* also computes (momwire uses
a real MNA current source, no resistor), so the superposition reference and the
engine must agree.
"""

from __future__ import annotations

import importlib.util
import shutil
from pathlib import Path

import pytest

_BNC = Path(__file__).resolve().parent.parent / "scripts" / "bench_nec_corpus.py"
_spec = importlib.util.spec_from_file_location("bench_nec_corpus", _BNC)
bnc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bnc)

needs_nec2c = pytest.mark.skipif(
    shutil.which("nec2c") is None, reason="nec2c not on PATH"
)

# A two-element phased array, both elements driven by EX 6 current sources 90°
# apart — the minimal multi-source deck that breaks the single-R_BIG emulation.
_PHASED2 = (
    "CE\n"
    "GW 1 15 -30 0 0 -30 0 20 0.05\n"
    "GW 2 15 30 0 0 30 0 20 0.05\n"
    "GE 1\nGN 1\n"
    "EX 6 1 1 0 1 0\n"
    "EX 6 2 1 0 0 1\n"
    "FR 0 1 0 0 7 0\nEN\n"
)


# --------------------------------------------------- pure (no nec2c) contract


def test_reference_deck_drop_strips_ex6_emulation():
    """``ex6="drop"`` removes the EX 6 cards and emits neither the EX 0 voltage
    twin nor the LD 4 R_BIG series resistor — the superposition path supplies
    its own excitation."""
    prepared = bnc.reference_deck(_PHASED2, "phased2", ex6="drop")
    mnems = [ln.split()[0] for ln in prepared.splitlines() if ln.split()]
    assert "EX" not in mnems  # no excitation left behind
    assert not any(ln.startswith("LD 4") for ln in prepared.splitlines())
    assert "GW" in mnems and "XQ" in mnems  # geometry + an execute request remain


def test_superposition_none_for_single_source():
    """One EX 6 feed is not this path's job (the R_BIG emulation handles it) —
    returns None before any nec2c solve."""
    one = (
        "CE\nGW 1 15 -30 0 0 -30 0 20 0.05\nGE 1\nGN 1\n"
        "EX 6 1 1 0 1 0\nFR 0 1 0 0 7 0\nEN\n"
    )
    assert bnc.superposition_reference(one, "one", 60.0, None) is None


def test_superposition_errors_on_zero_drive_current():
    """A feed with zero drive current has no V/I to report — caught before the
    solve, not divided-by-zero later."""
    zero = _PHASED2.replace("EX 6 2 1 0 0 1", "EX 6 2 1 0 0 0")
    res = bnc.superposition_reference(zero, "zero", 60.0, None)
    assert res is not None and res.get("error")
    assert "zero drive current" in res["error"]


# --------------------------------------------- physics oracle (needs nec2c)


@needs_nec2c
def test_superposition_matches_engine_on_phased_pair():
    """The reference the superposition builds must match what the engine solves
    for the same current excitation (the engine drives a real MNA current
    source). Agreement to a few percent pins the whole Y→Z→compose chain."""
    from antennaknobs import AntennaBuilder, WireSpec
    from antennaknobs.engines import MomwireEngine
    from antennaknobs.nec_import import parse_nec
    from momwire import SinusoidalSolver

    sup = bnc.superposition_reference(_PHASED2, "phased2", 60.0, None)
    assert sup is not None and sup.get("error") is None
    assert sup["superposition"] is True and sup["freq"] == pytest.approx(7.0)
    z_ref = [complex(re, im) for re, im in sup["z"]]

    deck = parse_nec(_PHASED2, name="phased2", network=True)

    class B(AntennaBuilder):
        default_params = {"freq": 7.0}

        def build_wires(self):
            return deck.wire_tuples()

        def build_network(self):
            return deck.network()

        def build_wire_material(self):
            return WireSpec(radius=deck.dominant_radius())

    z_eng = MomwireEngine(B(), solver=SinusoidalSolver, ground="pec").impedance()

    assert len(z_ref) == len(z_eng) == 2
    for zr, ze in zip(z_ref, z_eng):
        assert abs(zr - ze) / abs(ze) < 0.03, f"ref {zr:.1f} vs engine {ze:.1f}"


@needs_nec2c
def test_superposition_reference_is_physical():
    """Sanity floor: the composed driving-point impedances are finite with
    positive resistance — the exact failure the R_BIG bug produced was a huge
    *negative* resistance (−18,972 Ω), so a positive real part is the first
    thing that must hold."""
    sup = bnc.superposition_reference(_PHASED2, "phased2", 60.0, None)
    assert sup is not None and not sup.get("error")
    for re, im in sup["z"]:
        assert re > 0.0, f"non-physical negative resistance: {re}+{im}j"

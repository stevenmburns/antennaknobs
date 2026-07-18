"""LD 6 LC-trap loads (4nec2 dialect, issue #444).

The 4nec2 manual defines type 6 as an LC-trap whose F1 is the coil's
UNLOADED Q (0 → default 100), internally converted to a parallel RLC
with the loss resistance evaluated at the initial FR card's frequency:
R_p = Q·ωL. The contract here: our importer performs exactly that
conversion, so an LD 6 deck and the equivalent hand-written LD 1 deck
are indistinguishable all the way through an engine solve.
"""

import math

import pytest

from antennaknobs import AntennaBuilder, WireSpec
from antennaknobs.engines import MomwireEngine
from antennaknobs.nec_import import parse_nec
from momwire import SinusoidalSolver

FREQ = 21.05
OMEGA = 2.0 * math.pi * FREQ * 1e6
L_H = 2.86e-6
C_F = 20e-12

TRAP_DECK = (
    "GW 1 21 0 -10 15 0 10 15 0.008\nGE\n"
    "EX 0 1 11 0 1 0\n"
    "LD 6 1 5 5 {q} {l} {c}\n"
    "FR 0 1 0 0 21.05\nEN\n"
)


def _ld1_deck(r_p):
    return (
        "GW 1 21 0 -10 15 0 10 15 0.008\nGE\n"
        "EX 0 1 11 0 1 0\n"
        f"LD 1 1 5 5 {r_p!r} {L_H!r} {C_F!r}\n"
        "FR 0 1 0 0 21.05\nEN\n"
    )


def _builder(deck):
    class B(AntennaBuilder):
        default_params = {"freq": FREQ}

        def build_wires(self):
            return deck.wire_tuples()

        def build_network(self):
            return deck.network()

        def build_wire_material(self):
            return WireSpec(radius=deck.dominant_radius())

    return B()


def _z(deck):
    eng = MomwireEngine(_builder(deck), solver=SinusoidalSolver, ground=None)
    return eng.impedance()[0]


def test_ld6_translates_to_parallel_rlc():
    deck = parse_nec(TRAP_DECK.format(q=100, l=L_H, c=C_F), name="t", network=True)
    (load,) = deck.loads
    assert load.parallel is True
    assert load.l == pytest.approx(L_H)
    assert load.c == pytest.approx(C_F)
    assert load.r == pytest.approx(100.0 * OMEGA * L_H, rel=1e-12)
    assert not deck.ignored_detail  # fully expressed — no n-flag residue


def test_ld6_q_zero_defaults_to_100():
    deck = parse_nec(TRAP_DECK.format(q=0, l=L_H, c=C_F), name="t", network=True)
    assert deck.loads[0].r == pytest.approx(100.0 * OMEGA * L_H, rel=1e-12)


def test_ld6_without_inductance_is_skipped_not_fatal():
    deck = parse_nec(TRAP_DECK.format(q=100, l=0, c=C_F), name="t", network=True)
    assert not deck.loads
    assert any("LC-trap" in reason for _c, reason in deck.ignored_detail)


def test_ld6_solves_identically_to_hand_ld1():
    """Engine oracle: the LD 6 deck and the LD 1 deck with the same
    converted R_p must produce the same driving-point impedance."""
    r_p = 100.0 * OMEGA * L_H
    z6 = _z(parse_nec(TRAP_DECK.format(q=100, l=L_H, c=C_F), name="a", network=True))
    z1 = _z(parse_nec(_ld1_deck(r_p), name="b", network=True))
    assert z6 == pytest.approx(z1, rel=1e-12)


def test_trap_actually_bites_at_resonance():
    """Physics sanity: the 2.86 µH / 20 pF trap resonates at ~21.05 MHz, so
    at that frequency the trap inserts a large series impedance and the
    driving-point Z must differ hugely from the unloaded dipole's."""
    z_trap = _z(
        parse_nec(TRAP_DECK.format(q=100, l=L_H, c=C_F), name="t", network=True)
    )
    z_bare = _z(
        parse_nec(
            "GW 1 21 0 -10 15 0 10 15 0.008\nGE\nEX 0 1 11 0 1 0\n"
            "FR 0 1 0 0 21.05\nEN\n",
            name="b",
            network=True,
        )
    )
    assert abs(z_trap - z_bare) > 100.0


def test_reference_deck_emits_ld1_twin():
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    from bench_nec_corpus import reference_deck

    prepared = reference_deck(TRAP_DECK.format(q=100, l=L_H, c=C_F), "t")
    ld_lines = [ln for ln in prepared.splitlines() if ln.startswith("LD")]
    (ld,) = ld_lines
    toks = ld.split()
    assert toks[1] == "1"  # rewritten to parallel RLC
    assert float(toks[5]) == pytest.approx(100.0 * OMEGA * L_H, rel=1e-12)
    assert float(toks[6]) == pytest.approx(L_H)
    assert float(toks[7]) == pytest.approx(C_F)
    assert "LD 6" not in prepared

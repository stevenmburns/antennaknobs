"""EX 6 current-source reference via 4nec2's NT-gyrator emulation (issue #475).

The 4nec2 cross-check on #463 revealed how the authoring tool itself runs an
``EX 6`` deck on a stock NEC-2 kernel: per source, a phantom 1-segment wire
parked far away, an ``NT`` gyrator (Y11=Y22=0, Y12=Y21=j) tying phantom to the
real feed segment, and an ``EX 0`` on the phantom whose voltage carries the
requested current — the gyrator forces exactly that current into the real
segment regardless of load. It composes natively with the deck's own TL/NT
cards in one solve (no R_BIG subtraction, no N-solve superposition recovery)
and works for mixed EX 0 + EX 6 decks the superposition path must refuse.

Two readout gotchas the tests pin:

  * ANTENNA INPUT PARAMETERS reports the *phantom* port — nonsense values.
  * At a feed segment shared with a TL, the STRUCTURE EXCITATION DATA row's
    IMPEDANCE column is V/I_wire, which EXCLUDES the current the co-located
    network carries away — wrong exactly where the R_BIG emulation was also
    wrong. The correct readout is Z = V_row / I_requested (the gyrator forces
    the port current exactly, so the divisor is known without any parsing).

The strongest checks are the physics oracles: the engine drives a real MNA
current source, so gyrator reference and engine must agree; and the gyrator
must reproduce the independently-derived Y-matrix superposition reference.
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


def _parse(text, name):
    from antennaknobs.nec_import import parse_nec

    return parse_nec(text, name=name, network=True)


def _engine_z(text, name, freq):
    from antennaknobs import AntennaBuilder, WireSpec
    from antennaknobs.engines import MomwireEngine
    from momwire import SinusoidalSolver

    deck = _parse(text, name)

    class B(AntennaBuilder):
        default_params = {"freq": freq}

        def build_wires(self):
            return deck.wire_tuples()

        def build_network(self):
            return deck.network()

        def build_wire_material(self):
            return WireSpec(radius=deck.dominant_radius())

    return MomwireEngine(B(), solver=SinusoidalSolver, ground="pec").impedance()


# A two-element phased array, both elements driven by EX 6 current sources 90°
# apart (same deck the superposition tests use).
_PHASED2 = (
    "CE\n"
    "GW 1 15 -30 0 0 -30 0 20 0.05\n"
    "GW 2 15 30 0 0 30 0 20 0.05\n"
    "GE 1\nGN 1\n"
    "EX 6 1 1 0 1 0\n"
    "EX 6 2 1 0 0 1\n"
    "FR 0 1 0 0 7 0\nEN\n"
)

# A single EX 6 whose driven segment (wire 1, seg 1) also anchors a TL — the
# class where both the R_BIG readout (#464) and the naive structure-table
# IMPEDANCE column are composition artifacts.
_TL_SHARED1 = (
    "CE\n"
    "GW 1 15 -30 0 0 -30 0 20 0.05\n"
    "GW 2 15 30 0 0 30 0 20 0.05\n"
    "GE 1\nGN 1\n"
    "TL 1 1 2 1 50 5.0\n"
    "EX 6 1 1 0 1 0\n"
    "FR 0 1 0 0 7 0\nEN\n"
)

# Mixed excitation: element 1 voltage-driven (EX 0), element 2 current-driven
# (EX 6) — the deck shape the superposition path must refuse (it needs every
# feed to be a current source) but the gyrator composes in one solve.
_MIXED = (
    "CE\n"
    "GW 1 15 -30 0 0 -30 0 20 0.05\n"
    "GW 2 15 30 0 0 30 0 20 0.05\n"
    "GE 1\nGN 1\n"
    "EX 0 1 1 0 1 0\n"
    "EX 6 2 1 0 0 1\n"
    "FR 0 1 0 0 7 0\nEN\n"
)


# --------------------------------------------------- pure (no nec2c) contract


def test_gyrator_none_for_no_ex6_sources():
    """A deck with no EX 6 current source is not this path's job."""
    none = (
        "CE\nGW 1 15 -30 0 0 -30 0 20 0.05\nGE 1\nGN 1\n"
        "EX 0 1 1 0 1 0\nFR 0 1 0 0 7 0\nEN\n"
    )
    deck = _parse(none, "none")
    assert bnc.gyrator_reference(none, "none", deck, 60.0, None) is None


def test_gyrator_errors_on_zero_drive_current():
    """A feed with zero drive current has no V/I to report — caught before
    the solve, not divided-by-zero later."""
    zero = _PHASED2.replace("EX 6 2 1 0 0 1", "EX 6 2 1 0 0 0")
    deck = _parse(zero, "zero")
    res = bnc.gyrator_reference(zero, "zero", deck, 60.0, None)
    assert res is not None and res.get("error")
    assert "zero drive current" in res["error"]


def test_gyrator_nts_contiguous_with_deck_network(monkeypatch):
    """NEC-2 destroys previous network data when a network card is read after
    any non-network card, so the gyrator NTs must be spliced directly adjacent
    to the deck's own TL/NT block (this silently dropped DipTL's TL before the
    splice rule). Intercept the prepared deck text and check card adjacency,
    plus the other construction invariants: one phantom GW per source, EX 0
    cards last before the execute request, EX value = j * I_req."""
    captured = {}

    def fake_tables(deck_text, timeout, mem_bytes=None):
        captured["text"] = deck_text
        return {"error": "captured"}

    monkeypatch.setattr(bnc, "_nec2c_network_tables", fake_tables)
    deck = _parse(_TL_SHARED1, "tlshared1")
    res = bnc.gyrator_reference(_TL_SHARED1, "tlshared1", deck, 60.0, None)
    assert res["error"] == "gyrator: captured"

    lines = [ln.split() for ln in captured["text"].splitlines() if ln.split()]
    mnems = [t[0] for t in lines]
    # network block is contiguous: the deck's TL immediately followed by our NT
    tl_i = mnems.index("TL")
    assert mnems[tl_i + 1] == "NT"
    between = mnems[tl_i : mnems.index("XQ")]
    # nothing re-enters the network block after it closes
    assert between.count("TL") + between.count("NT") == 2
    # one phantom wire (tag 3 = maxtag+1), one EX, EX last before XQ
    gw_tags = [int(float(t[1])) for t in lines if t[0] == "GW"]
    assert gw_tags == [1, 2, 3]
    ex = [t for t in lines if t[0] == "EX"]
    assert len(ex) == 1 and int(float(ex[0][2])) == 3
    assert mnems[mnems.index("XQ") - 1] == "EX"
    # EX value = j * I_req = j * (1+0j) -> (0, 1)
    assert float(ex[0][5]) == 0.0 and float(ex[0][6]) == 1.0
    # NT port 2 uses tag-0 + absolute segment (wire 1 seg 1 -> abs 1)
    nt = next(t for t in lines if t[0] == "NT")
    assert nt[3] == "0" and int(float(nt[4])) == 1
    # gyrator admittance Y11=Y22=0, Y12=j
    assert [float(x) for x in nt[5:11]] == [0.0, 0.0, 0.0, 1.0, 0.0, 0.0]


# --------------------------------------------- physics oracles (needs nec2c)


@needs_nec2c
def test_gyrator_matches_engine_on_phased_pair():
    """The gyrator reference must match what the engine solves for the same
    current excitation (the engine drives a real MNA current source)."""
    deck = _parse(_PHASED2, "phased2")
    gyr = bnc.gyrator_reference(_PHASED2, "phased2", deck, 60.0, None)
    assert gyr is not None and gyr.get("error") is None
    assert gyr["gyrator"] is True and gyr["freq"] == pytest.approx(7.0)
    z_ref = [complex(re, im) for re, im in gyr["z"]]
    z_eng = _engine_z(_PHASED2, "phased2", 7.0)
    assert len(z_ref) == len(z_eng) == 2
    for zr, ze in zip(z_ref, z_eng):
        assert abs(zr - ze) / abs(ze) < 0.03, f"ref {zr:.1f} vs engine {ze:.1f}"


@needs_nec2c
def test_gyrator_matches_superposition():
    """Cross-check the two independent EX 6 reference routes against each
    other: N voltage solves + Y-matrix recovery vs one gyrator solve. In 4nec2
    they agreed <0.2%; hold the same bar here, on both the phased pair and the
    TL-shared single source."""
    for text, name in ((_PHASED2, "phased2"), (_TL_SHARED1, "tlshared1")):
        deck = _parse(text, name)
        gyr = bnc.gyrator_reference(text, name, deck, 60.0, None)
        sup = bnc.superposition_reference(text, name, 60.0, None)
        assert gyr.get("error") is None and sup.get("error") is None
        for zg, zs in zip(gyr["z"], sup["z"]):
            zg, zs = complex(*zg), complex(*zs)
            assert abs(zg - zs) / abs(zs) < 0.002, f"{name}: {zg:.3f} vs {zs:.3f}"


@needs_nec2c
def test_gyrator_single_source_sharing_tl():
    """Issue #464's corner: the driven segment also anchors a TL, so most of
    the forced current bypasses into the line and every V/I_wire readout is a
    composition artifact. The V_row/I_req readout must recover the true
    driving-point Z the engine also computes — and must NOT coincide with the
    R_BIG artifact (guards a silent revert to the #456 raw readout)."""
    deck = _parse(_TL_SHARED1, "tlshared1")
    gyr = bnc.gyrator_reference(_TL_SHARED1, "tlshared1", deck, 60.0, None)
    assert gyr is not None and gyr.get("error") is None
    assert len(gyr["z"]) == 1
    z_ref = complex(*gyr["z"][0])
    z_eng = _engine_z(_TL_SHARED1, "tlshared1", 7.0)[0]
    assert abs(z_ref - z_eng) / abs(z_eng) < 0.02, f"ref {z_ref:.2f} vs eng {z_eng:.2f}"

    prepared = bnc.reference_deck(_TL_SHARED1, "tlshared1")  # ex6="rbig"
    raw = bnc.run_nec2c(
        Path("unused-when-deck_text-given.nec"), 60.0, deck_text=prepared
    )
    z_raw = complex(*raw["z"][0])
    assert abs(z_ref - z_raw) / abs(z_ref) > 0.05, (
        f"gyrator {z_ref:.2f} suspiciously close to R_BIG artifact {z_raw:.2f}"
    )


@needs_nec2c
def test_gyrator_mixed_voltage_and_current_feeds():
    """A mixed EX 0 + EX 6 deck — outside the superposition path's contract
    (bench_deck only routes all-current decks there) — solves in one pass:
    the EX 0 feed reads its ANTENNA INPUT PARAMETERS row (network current
    included), the EX 6 feed reads V_row/I_req from the structure-excitation
    table, both in EX-card order."""
    deck = _parse(_MIXED, "mixed")
    gyr = bnc.gyrator_reference(_MIXED, "mixed", deck, 60.0, None)
    assert gyr is not None and gyr.get("error") is None
    z_ref = [complex(re, im) for re, im in gyr["z"]]
    z_eng = _engine_z(_MIXED, "mixed", 7.0)
    assert len(z_ref) == len(z_eng) == 2
    for zr, ze in zip(z_ref, z_eng):
        assert abs(zr - ze) / abs(ze) < 0.03, f"ref {zr:.1f} vs engine {ze:.1f}"

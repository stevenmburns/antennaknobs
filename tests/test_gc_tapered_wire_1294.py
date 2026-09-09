"""#1294: GW-with-zero-radius + GC translates into a stepped-radius run.

NEC announces a tapered wire by giving the GW a zero radius and putting the
taper on a GC continuation. Both progressions are GEOMETRIC, and both numbers
below were DERIVED FROM nec2c's own segmentation table rather than assumed —
nec2c reads GC natively, so it is the oracle here:

  YI20_40B.NEC  GW 1 16 ... 0 / GC 0 0 1. .006 .011
      16 equal segments of 0.1632 m, radii .0060 .0062 .0065 ... .0110,
      i.e. ratio (11/6)^(1/15) = 1.041237.

  3-1a-nec2.nec  GW 1 9 ... 0 / GC 0 0 .8163265 .001 .001
      lengths 0.0508 0.0415 0.0338 ... 0.0100, i.e. L[i+1] = L[i]*RDEL
      scaled to the wire's own span. Constant radius.
"""

import math
import os
from pathlib import Path

import pytest

from antennaknobs.nec_import import parse_nec

CORPUS = Path(os.path.expanduser("~/antennas/nec-wild"))
YAGI = CORPUS / "opensource/nec2c/YI20_40B.NEC"
TAPERED_LENGTH = (
    CORPUS / "community/cebik-w4rnl/tutorial-models/Tutorial-2/ch-3/3-1a-nec2.nec"
)

needs_corpus = pytest.mark.skipif(
    not YAGI.exists(), reason="wild corpus not on this box"
)


def _deck(path):
    return parse_nec(path.read_text(errors="replace"), name=path.name)


def _tag(deck, tag):
    return [w for w in deck.wires if w.tag == tag]


@needs_corpus
def test_g1294_1_the_radius_taper_reproduces_nec2c_step_for_step():
    """Every acceptance paired with the value it produces."""
    run = _tag(_deck(YAGI), 1)
    assert len(run) == 16, "the 16-segment GW should expand to 16 wires"
    assert all(w.n_seg == 1 for w in run)

    # nec2c's printed radii for this run, to its four decimals.
    expected = [
        0.0060,
        0.0062,
        0.0065,
        0.0068,
        0.0071,
        0.0073,
        0.0076,
        0.0080,
        0.0083,
        0.0086,
        0.0090,
        0.0094,
        0.0097,
        0.0101,
        0.0106,
        0.0110,
    ]
    got = [round(w.radius, 4) for w in run]
    assert got == expected, got

    lengths = [math.dist(w.p1, w.p2) for w in run]
    assert all(abs(length - 0.1632) < 5e-5 for length in lengths), lengths


@needs_corpus
def test_g1294_2_the_length_taper_reproduces_nec2c_step_for_step():
    """RDEL != 1 is honoured by re-meshing, not refused."""
    run = _tag(_deck(TAPERED_LENGTH), 1)
    assert len(run) == 9

    expected = [0.0508, 0.0415, 0.0338, 0.0276, 0.0226, 0.0184, 0.0150, 0.0123, 0.0100]
    got = [round(math.dist(w.p1, w.p2), 4) for w in run]
    assert got == expected, got

    # RAD1 == RAD2 here, so the radius must NOT move.
    assert {round(w.radius, 6) for w in run} == {0.001}

    # Ratios from the UNROUNDED lengths: `got` is rounded to nec2c's four
    # printed decimals, and dividing those gives a 2.5e-3 quantisation wobble
    # that says nothing about the progression.
    exact = [math.dist(w.p1, w.p2) for w in run]
    ratios = [exact[i + 1] / exact[i] for i in range(len(exact) - 1)]
    assert all(abs(r - 0.8163265) < 1e-9 for r in ratios), ratios


@needs_corpus
def test_g1294_3_the_run_spans_the_original_endpoints():
    """The expansion re-meshes the wire; it must not move its ends."""
    for path, tag in ((YAGI, 1), (TAPERED_LENGTH, 1)):
        text = path.read_text(errors="replace")
        gw = next(
            line
            for line in text.splitlines()
            if line.strip().upper().startswith("GW")
            and int(float(line.split()[1])) == tag
        )
        f = [float(x) for x in gw.split()[1:]]
        p1, p2 = tuple(f[2:5]), tuple(f[5:8])
        run = _tag(parse_nec(text, name=path.name), tag)
        assert math.dist(run[0].p1, p1) < 1e-9, path.name
        assert math.dist(run[-1].p2, p2) < 1e-9, path.name


@needs_corpus
def test_g1294_4_a_plain_GW_is_untouched():
    """The absence assertion: a wire with a real radius keeps its shape.

    Without this the translation could 'work' by expanding everything.
    """
    deck = _deck(YAGI)
    plain = _tag(deck, 2)  # GW 2 3 ... .011 -- a real radius, no GC
    assert len(plain) == 1, "a non-taper GW must stay one wire"
    assert plain[0].n_seg == 3
    assert plain[0].radius == pytest.approx(0.011)


def test_g1294_5_a_zero_radius_with_no_GC_is_refused_by_name():
    deck = "CM t\nCE\nGW 1 4 0 0 0 0 0 1 0\nGE 0\nFR 0 1 0 0 14 0\nEN\n"
    with pytest.raises(ValueError, match="no GC continuation followed it"):
        parse_nec(deck, name="t.nec")


def test_g1294_6_a_GC_without_a_pending_taper_is_refused_by_name():
    deck = "CM t\nCE\nGW 1 4 0 0 0 0 0 1 .001\nGC 0 0 1 .001 .002\nGE 0\nEN\n"
    with pytest.raises(ValueError, match="must follow a GW with zero radius"):
        parse_nec(deck, name="t.nec")


def test_g1294_7_a_nonplain_GC_form_is_refused_by_name():
    """The NEC-4 spellings are a separate issue; refuse them saying so."""
    deck = "CM t\nCE\nGW 1 4 0 0 0 0 0 1 0\nGC 2 0 0 .001 .001 .004 .1\nGE 0\nEN\n"
    with pytest.raises(ValueError, match="only the plain continuation form"):
        parse_nec(deck, name="t.nec")


# --- the solve gate -------------------------------------------------------
# nec2c reads GC natively, so these are a real oracle rather than a re-record
# of our own answer. Captured with nec2c 1.3.1 (md5 050927160cecf7ee86db907-
# dafac7bbe) on the decks as they sit in the corpus.
NEC2C_Z = {
    "YI20_40B.NEC": complex(25.4010, -9.9794),
    "3-1a-nec2.nec": complex(70.9230, -3.1248),
}


def _gamma(z, z0=50.0):
    return (z - z0) / (z + z0)


@needs_corpus
@pytest.mark.slow
@pytest.mark.parametrize("path", [YAGI, TAPERED_LENGTH], ids=lambda p: p.name)
def test_g1294_8_the_tapered_decks_solve_and_agree_with_nec2c(path):
    """Import AND solve, against nec2c's own impedance for the same deck."""
    pynec = pytest.importorskip("antennaknobs.engines.pynec")
    import sys
    from types import MappingProxyType

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    from bench_nec_corpus import load_deck, parse_ground

    from antennaknobs import AntennaBuilder, WireSpec

    text = path.read_text(errors="replace")
    deck, net, _ = load_deck(text, path.name)
    ground, _supported, _note = parse_ground(text)
    tups = deck.wire_tuples(specs=True)

    class DeckBuilder(AntennaBuilder):
        default_params = MappingProxyType({"freq": float(deck.freq_mhz[0])})

        def build_wires(self):
            return tups

        def build_network(self):
            return net

        def build_wire_material(self):
            return WireSpec(radius=deck.dominant_radius())

    z = pynec.PyNECEngine(DeckBuilder(), ground=ground).impedance()[0]
    ref = NEC2C_Z[path.name]
    dg = abs(_gamma(z) - _gamma(ref))
    assert dg < 0.01, f"{path.name}: Z={z}, nec2c={ref}, dGamma={dg:.5f}"

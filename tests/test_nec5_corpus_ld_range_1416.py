"""antennaknobs#1416: a whole-wire segment range must stay whole-wire.

NEC-5 addresses knots where NEC-2 addresses segment centres, so `translate`
remeshes a wire to put a referenced centre on a knot and remaps the references
that name it. That part is deliberate. The hole was in how a RANGE was remapped:
each edge went through the centre-mapping formula, so `GW 1 25` + `LD 5 1 1 25`
became `GW 1 50` + `LD 5 1 **2** 50` — a range that covered every segment of the
wire before the remesh covering all but the first afterwards.

It is not a rounding quibble. A whole-wire `LD 5` is per-wire conductivity, which
momwire's nec2 dialect carries; a partial range is one it refuses by name. The
AK#896 census lost **175 of 3,076 decks** to this, its single largest refusal,
and they were lost to our own translator rather than to either engine.

The mapping now used, and the reason it is the right one: old segment k of an
N-mesh occupies [(k-1)/N, k/N] of the wire, which on an N'-mesh begins inside
segment (k-1)*N'//N + 1 and ends inside ceil(k*N'/N). Those two edges give the
smallest new range COVERING the old one — the conservative direction for a load,
since under-covering silently unloads wire the author loaded. Whole-wire falls
out of it for every N and N': a=1 maps to 1, b=N maps to N'.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "nec5_corpus" / "nec5_corpus.py"


@pytest.fixture(scope="module")
def tool():
    spec = importlib.util.spec_from_file_location("nec5_corpus_ld_probe", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _deck(gw: str, ld: str, ex_seg: int = 13) -> str:
    """One wire, one load, one source. The source is what forces the remesh:
    without a reference to put on a knot the wire is left alone and the range
    never moves, which would make every assertion below vacuous."""
    return f"CM ld range\nCE\n{gw}\nGE 0\n{ld}\nEX 0 1 {ex_seg} 0 1 0\nGN -1\nXQ\nEN\n"


def _translate(tool, tmp_path, text: str, name="ld.nec") -> dict:
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return tool.translate_file(p, name, "double", False)


def _cards(rec, mn: str) -> list[str]:
    deck = rec["outputs"][0][1]
    return [ln for ln in deck.splitlines() if ln.split() and ln.split()[0] == mn]


# --- the four decks the census failure was verified on, reduced to the cards
# --- that matter. Each is (name, GW, LD, expected LD after translation).
REAL = [
    # 4nec2-models/VHFsimple/halfsq2m.nec — the deck in the issue
    (
        "halfsq2m",
        "GW 1 25 -20 0 360 -20 0 381.55 4.041334E-02",
        "LD 5 1 1 25 5.8001E7",
        "LD 5 1 1 50 5.8001E7",
    ),
    # cebik .../Tutorial-1/10-4-1.nec and 11-4.nec share this shape
    (
        "10-4-1",
        "GW 1 25 0 0 0 0 0 5 0.001",
        "LD 5 1 1 25 2.4938E7",
        "LD 5 1 1 50 2.4938E7",
    ),
    # cebik .../Tutorial-2/... a shorter wire, same whole-wire range
    (
        "13-4-1",
        "GW 1 11 0 0 0 0 0 5 0.001",
        "LD 5 1 1 11 5.8001E7",
        "LD 5 1 1 22 5.8001E7",
    ),
    # a load naming the whole wire on an already-even mesh: no remesh, no move
    (
        "even-mesh",
        "GW 1 12 0 0 0 0 0 5 0.001",
        "LD 5 1 1 12 5.8001E7",
        "LD 5 1 1 12 5.8001E7",
    ),
]


@pytest.mark.parametrize("name,gw,ld,want", REAL, ids=[r[0] for r in REAL])
def test_a_whole_wire_range_stays_whole_wire(tool, tmp_path, name, gw, ld, want):
    n = int(gw.split()[2])
    rec = _translate(tool, tmp_path, _deck(gw, ld, ex_seg=(n + 1) // 2), f"{name}.nec")
    assert rec["status"] == "translated", rec.get("reason")
    got = _cards(rec, "LD")
    assert got == [want], f"{name}: {got}"


def test_the_wire_really_was_remeshed(tool, tmp_path):
    """Guards the test above from passing for the wrong reason.

    If the remesh stopped happening, every whole-wire range would trivially
    stay whole-wire and these assertions would pass while saying nothing.
    """
    rec = _translate(
        tool,
        tmp_path,
        _deck("GW 1 25 0 0 0 0 0 5 0.001", "LD 5 1 1 25 5.8001E7", ex_seg=13),
    )
    assert _cards(rec, "GW")[0].split()[2] == "50", _cards(rec, "GW")


def test_a_partial_range_maps_proportionally(tool, tmp_path):
    """Segments 5..10 of 25 cover [4/25, 10/25]; on a 50-mesh that is 9..20."""
    rec = _translate(
        tool,
        tmp_path,
        _deck("GW 1 25 0 0 0 0 0 5 0.001", "LD 5 1 5 10 5.8001E7", ex_seg=13),
    )
    assert _cards(rec, "LD") == ["LD 5 1 9 20 5.8001E7"]


def test_a_single_segment_range_widens_to_the_segments_it_became(tool, tmp_path):
    """Old segment 1 of 25 becomes new segments 1 and 2 of 50. Naming only one
    of them would unload half the length the author loaded."""
    rec = _translate(
        tool,
        tmp_path,
        _deck("GW 1 25 0 0 0 0 0 5 0.001", "LD 5 1 1 1 5.8001E7", ex_seg=13),
    )
    assert _cards(rec, "LD") == ["LD 5 1 1 2 5.8001E7"]


def test_zero_zero_is_left_alone(tool, tmp_path):
    """`LD ... 0 0` is NEC's "the whole tag" spelling. It names no segment
    numbers, so there is nothing to remap and rewriting it as an explicit range
    would only be a chance to get it wrong."""
    rec = _translate(
        tool,
        tmp_path,
        _deck("GW 1 25 0 0 0 0 0 5 0.001", "LD 5 1 0 0 5.8001E7", ex_seg=13),
    )
    assert _cards(rec, "LD") == ["LD 5 1 0 0 5.8001E7"]


@pytest.mark.parametrize("typ", [2, 3, 5])
def test_every_range_carrying_LD_type_is_fixed_not_just_five(tool, tmp_path, typ):
    """LD 2, 3 and 5 all keep a segment range through translation (0, 1 and 4
    expand into one knot load per segment instead). The bug was reported on
    LD 5 because that is what the corpus decks used; it was never LD 5's."""
    rec = _translate(
        tool,
        tmp_path,
        _deck("GW 1 25 0 0 0 0 0 5 0.001", f"LD {typ} 1 1 25 1.0 2.0 3.0", ex_seg=13),
    )
    assert _cards(rec, "LD") == [f"LD {typ} 1 1 50 1.0 2.0 3.0"]


def test_PT_ranges_ride_the_same_mapping(tool, tmp_path):
    """PT is the other card the tool remaps by tag+range, through the same
    function — so it is fixed by the same change and pinned by the same test."""
    deck = (
        "CM pt range\nCE\nGW 1 25 0 0 0 0 0 5 0.001\nGE 0\n"
        "PT 0 1 1 25\nEX 0 1 13 0 1 0\nGN -1\nXQ\nEN\n"
    )
    rec = _translate(tool, tmp_path, deck, "pt.nec")
    assert rec["status"] == "translated", rec.get("reason")
    assert _cards(rec, "PT") == ["PT 0 1 1 50"]

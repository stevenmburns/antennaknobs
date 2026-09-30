"""`scripts/nec4_corpus/nec4_corpus.py`: the NEC-4.2 regression corpus.

Every rule the translator applies, on small inline decks -- no network, no
NEC-4.2 binary (`check` runs against a stand-in executable that writes a
printout). The rules themselves were measured on a licensed NEC-4.2 binary as
black-box probes; these tests hold the translator to them.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "nec4_corpus" / "nec4_corpus.py"


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def tool():
    return _load(SCRIPT, "nec4_corpus_under_test")


def _translate(tool, text, name="t.nec"):
    comments, cards = tool.n5.normalize(textwrap.dedent(text), name)
    return tool.translate_deck(comments, cards, name)


def _cards(deck):
    return [ln for ln in deck.splitlines() if not ln.startswith(("CM", "CE"))]


# --------------------------------------------------------------------------
# dialect cleaning is the NEC-5 tool's; the knot moves are not applied
# --------------------------------------------------------------------------
def test_dialect_is_cleaned_and_the_mesh_and_feed_stay_as_authored(tool):
    deck, notes, gtypes, twin = _translate(
        tool,
        """\
        CM 4nec2 style
        CE
        SY len=10, h=5
        GW1,11,0,-len/2,h,0,len/2,h,#14\t' a comment
        GE 0
        EX\t0\t1\t6\t10\t1\t0
        FR 0 1 0 0 14.2D0 0
        EN
        """,
    )
    cards = _cards(deck)
    # SY evaluated, commas / tab / fused mnemonic / AWG / D exponent resolved.
    assert cards[0].startswith("GW 1 11 0 -5 5 0 5 5 0.00081386")
    # NEC-4.2 feeds segment centres: the odd count stays odd, the source stays
    # on segment 6, and EX's fourth field (a NEC-2 print flag) is left alone.
    assert "EX 0 1 6 10 1 0" in cards
    assert "FR 0 1 0 0 14.2 0" in cards
    assert cards[-2:] == ["XQ 0", "EN"]
    assert any("XQ 0 added" in n for n in notes)
    assert gtypes == set() and not twin
    assert not any("knot" in n for n in notes)


def test_an_untagged_wire_keeps_tag_zero(tool):
    deck, *_ = _translate(
        tool,
        "GW 0 5 0 0 0 0 0 1 0.001\nGE 0\nEX 0 0 3 0 1 0\nXQ\nEN\n",
    )
    assert "GW 0 5 0 0 0 0 0 1 0.001" in _cards(deck)


# --------------------------------------------------------------------------
# ground
# --------------------------------------------------------------------------
SOMM = """\
GW 1 11 0 -5 10 0 5 10 0.001
GE 1
{gn}
EX 0 1 6 0 1 0
FR 0 1 0 0 14.2 0
XQ
EN
"""


def test_gn2_ends_nofile_and_gets_a_gn3_twin(tool):
    deck, notes, gtypes, twin = _translate(tool, SOMM.format(gn="GN 2 0 0 0 13 0.005"))
    assert "GN 2 0 0 0 13 0.005 NOFILE" in _cards(deck)
    assert gtypes == {2} and twin
    twin_deck = tool.gn3_twin(deck)
    a, b = deck.splitlines(), twin_deck.splitlines()
    diff = [(x, y) for x, y in zip(a, b[: len(a)], strict=False) if x != y]
    assert "GN 3 0 0 0 13 0.005 NOFILE" in b
    assert set(b) - set(a) == {
        "GN 3 0 0 0 13 0.005 NOFILE",
        "CM nec4_corpus: GN 3 twin -- identical to the .gn2 deck but for GN 3",
    }
    assert len(b) == len(a) + 1 and diff


def test_a_gn2_table_file_name_becomes_nofile_and_is_recorded(tool):
    deck, notes, *_ = _translate(
        tool, SOMM.format(gn="GN 2 0 0 0 13 0.005 0 0 SOMEX.NEC")
    )
    assert "GN 2 0 0 0 13 0.005 0 0 NOFILE" in _cards(deck)
    assert any("'SOMEX.NEC' replaced by NOFILE" in n for n in notes)


@pytest.mark.parametrize(
    ("gn", "label"),
    [("GN 1", "pec"), ("GN 0 0 0 0 13 0.005", "rc"), ("GN -1", "free")],
)
def test_other_grounds_pass_unchanged_and_get_no_twin(tool, gn, label):
    deck, _, gtypes, twin = _translate(tool, SOMM.format(gn=gn))
    assert gn in _cards(deck) and not twin
    assert tool._ground_label(gtypes) == label


def test_4nec2_gn3_is_its_mininec_ground_and_is_skipped(tool):
    with pytest.raises(tool.Refused, match="MININEC-type ground"):
        _translate(tool, SOMM.format(gn="GN 3 0 0 0 13 0.005"))


def test_a_radial_screen_on_gn2_is_skipped(tool):
    with pytest.raises(tool.Refused, match="120-radial ground screen"):
        _translate(tool, SOMM.format(gn="GN 2 120 0 0 13 0.005 10 0.001"))


BURIED = """\
GW 1 10 0 0 {top} 0 0 10 0.01
GW 2 5 0 0 -0.5 0 0 {top} 0.01
GW 3 10 0 0 -0.5 5 0 -0.5 0.01
GE {ge}
{gn}
EX 0 1 1 0 1 0
FR 0 1 0 0 7.1 0
XQ
EN
"""


@pytest.mark.parametrize("ge", ["0", "1"])
def test_buried_wires_over_gn2_are_spelled_ge_minus_1(tool, ge):
    deck, notes, *_ = _translate(
        tool, BURIED.format(top="0", ge=ge, gn="GN 2 0 0 0 13 0.005")
    )
    assert "GE -1" in _cards(deck)
    assert any(f"GE {ge} -> GE -1" in n for n in notes)


def test_ge_minus_1_is_left_alone(tool):
    deck, notes, *_ = _translate(
        tool, BURIED.format(top="0", ge="-1", gn="GN 2 0 0 0 13 0.005")
    )
    assert "GE -1" in _cards(deck) and not any("GE -1:" in n for n in notes)


def test_ge1_rewrite_that_would_cut_a_plane_end_loose_is_skipped(tool):
    # The rise stops at z=0 and the vertical starts there: GE 1 connected the
    # vertical's base to its image; GE -1 would leave it open.
    text = BURIED.replace(
        "GW 2 5 0 0 -0.5 0 0 {top} 0.01\n", "GW 2 5 0 0 -0.5 1 0 0 0.01\n"
    )
    with pytest.raises(tool.Refused, match="open-circuited"):
        _translate(tool, text.format(top="0", ge="1", gn="GN 2 0 0 0 13 0.005"))


def test_buried_wires_over_a_non_sommerfeld_ground_are_skipped(tool):
    with pytest.raises(tool.Refused, match="MUST USE SOMMERFELD"):
        _translate(tool, BURIED.format(top="0", ge="-1", gn="GN 0 0 0 0 13 0.005"))


def test_a_segment_straddling_the_interface_is_skipped(tool):
    # 5 segments from -0.5 to 0.25: no segment end at z=0.
    with pytest.raises(tool.Refused, match="straddling z=0"):
        _translate(tool, BURIED.format(top="0.25", ge="-1", gn="GN 2 0 0 0 13 0.005"))


def test_a_wire_lowered_by_gm_counts_as_buried(tool):
    text = """\
    GW 1 10 0 0 0 0 0 10 0.01
    GW 2 10 0 0 0.5 5 0 0.5 0.01
    GM 0 0 0 0 0 0 0 -1 2
    GE 1
    GN 2 0 0 0 13 0.005
    EX 0 1 1 0 1 0
    XQ
    EN
    """
    # The GM moves tag 2 (and only tag 2) to z=-0.5: buried, so GE 1 must go,
    # and the vertical's base on the plane would be cut loose by GE -1.
    with pytest.raises(tool.Refused, match="open-circuited"):
        _translate(tool, text)
    # Without the GM nothing is buried and GE 1 stays.
    deck, notes, *_ = _translate(tool, text.replace("    GM 0 0 0 0 0 0 0 -1 2\n", ""))
    assert "GE 1" in _cards(deck)


def test_ground_geometry_follows_gm_gr_and_gs(tool):
    cards = tool.n5.normalize(
        "GW 1 4 1 0 0.5 2 0 0.5 0.01\nGM 0 0 0 0 0 0 0 -1 1\nGR 0 4\nGS 0 0 2\nGE 1\nEN\n",
        "g",
    )[1]
    wires = tool.conductors(cards)
    assert len(wires) == 4
    assert all(p[2] == pytest.approx(-1.0) for _, pts in wires for p in pts)
    g = tool.ground_geometry(cards)
    assert g["buried"] and not g["straddle"]


# --------------------------------------------------------------------------
# 4nec2 EX 6, LD 6, LD 7
# --------------------------------------------------------------------------
DIPOLE = """\
GW 1 11 0 -5 10 0 5 10 0.001
GW 2 3 0 -5 12 0 5 12 0.001
GE 0
{cards}
FR 0 1 0 0 14.2 0
XQ
EN
"""


def test_4nec2_ex6_becomes_native_ex6(tool):
    deck, notes, *_ = _translate(
        tool,
        DIPOLE.format(
            cards="EX 6 1 6 00 -.86 .508 0\nEX 6 2 2 10 1 0\nTL 1 6 2 2 50 3"
        ),
    )
    cards = _cards(deck)
    # I4 and the trailing F3 normalised away (measured to make no difference);
    # a TL port on the same segment is NOT ambiguous (measured identical to
    # the gyrator 4nec2 builds).
    assert "EX 6 1 6 0 -.86 .508" in cards
    assert "EX 6 2 2 0 1 0" in cards
    assert any("native EX 6" in n for n in notes)


def test_ex6_sharing_a_segment_with_another_source_is_skipped(tool):
    with pytest.raises(tool.Refused, match="another source sits on the same segment"):
        _translate(tool, DIPOLE.format(cards="EX 0 1 6 0 1 0\nEX 6 1 6 0 1 0"))


def test_ex6_on_copies_of_one_wire_are_different_segments(tool):
    # GM copies tag 1 to tag 3: tag 3 segment 6 is not tag 1 segment 6.
    deck, *_ = _translate(
        tool,
        DIPOLE.replace("GE 0", "GM 2 1 0 0 0 1 0 0 1\nGE 0").format(
            cards="EX 6 1 6 0 1 0\nEX 6 3 6 0 1 0"
        ),
    )
    assert "EX 6 3 6 0 1 0" in _cards(deck)


def test_ex6_with_zero_current_is_skipped(tool):
    with pytest.raises(tool.Refused, match="current is zero"):
        _translate(tool, DIPOLE.format(cards="EX 6 1 1 1 0"))


def test_ld7_insulation_becomes_an_is_sheath(tool):
    deck, notes, *_ = _translate(
        tool, DIPOLE.format(cards="LD 7 0 0 0 4.5 .0016\nEX 0 1 6 0 1 0")
    )
    assert "IS 0 0 0 0 4.5 0 .0016" in _cards(deck)
    assert not any(ln.startswith("LD 7") for ln in _cards(deck))
    assert any("IS" in n and "LD 7" in n for n in notes)


def test_ld7_vacuum_jacket_is_dropped_as_no_load(tool):
    deck, notes, *_ = _translate(
        tool, DIPOLE.format(cards="LD 7 0 0 0 1 .0016\nEX 0 1 6 0 1 0")
    )
    assert not any(ln.startswith(("LD", "IS")) for ln in _cards(deck))


def test_ld6_trap_becomes_parallel_rlc_at_the_first_fr(tool):
    deck, notes, *_ = _translate(
        tool, DIPOLE.format(cards="LD 6 1 3 3 0 1e-6 1e-10\nEX 0 1 6 0 1 0")
    )
    ld = [ln for ln in _cards(deck) if ln.startswith("LD")]
    assert len(ld) == 1 and ld[0].startswith("LD 1 1 3 3 ")
    r = float(ld[0].split()[5])
    # Q 0 means 100; R = Q * 2 pi f L at 14.2 MHz.
    assert r == pytest.approx(100 * 2 * 3.141592653589793 * 14.2e6 * 1e-6, rel=1e-9)


def test_ld6_without_fr_is_skipped(tool):
    with pytest.raises(tool.Refused, match="no FR card"):
        _translate(
            tool,
            "GW 1 11 0 -5 10 0 5 10 0.001\nGE 0\nLD 6 1 3 3 100 1e-6 1e-10\n"
            "EX 0 1 6 0 1 0\nXQ\nEN\n",
        )


# --------------------------------------------------------------------------
# cards NEC-4.2 cannot take, and cards it takes as written
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("card", "match"),
    [("GF x.ngf", "Green's function"), ("MP 0 0 0 0 1 1", "MP")],
)
def test_cards_nec42_stops_on_are_skipped(tool, card, match):
    with pytest.raises(tool.Refused, match=match):
        _translate(tool, DIPOLE.format(cards=f"{card}\nEX 0 1 6 0 1 0"))


def test_ek_is_kept_and_noted(tool):
    deck, notes, *_ = _translate(tool, DIPOLE.format(cards="EK\nEX 0 1 6 0 1 0"))
    assert "EK" in _cards(deck)
    assert any("NO EFFECT IN NEC-4" in n for n in notes)


def test_flat_gh_loop_is_written_as_gw_pieces(tool):
    deck, notes, *_ = _translate(
        tool,
        "GH 1 8 1e-300 1e-300 1 1 0.99 0.99 0.005\nGE 0\nEX 0 1 1 0 1 0\nXQ\nEN\n",
    )
    assert sum(ln.startswith("GW 1 1 ") for ln in _cards(deck)) == 8
    assert any("NEC-4.2 stops on it" in n for n in notes)


def test_an_invalid_deck_is_still_invalid(tool):
    with pytest.raises(tool.InvalidNEC, match="above GE"):
        _translate(tool, "GW 1 5 0 0 0 0 0 1 0.001\nGN 1\nGE 1\nEX 0 1 3 0 1 0\nEN\n")


# --------------------------------------------------------------------------
# translate -> manifest -> check -> twins, end to end
# --------------------------------------------------------------------------
@pytest.fixture()
def corpus(tool, tmp_path):
    raw = tmp_path / "raw" / "coll"
    raw.mkdir(parents=True)
    (raw / "somm.nec").write_text("CM a\nCE\n" + SOMM.format(gn="GN 2 0 0 0 13 0.005"))
    (raw / "free.NEC").write_text("CM b\nCE\n" + DIPOLE.format(cards="EX 0 1 6 0 1 0"))
    (raw / "mininec.nec").write_text(SOMM.format(gn="GN 3 0 0 0 13 0.005"))
    root = tmp_path / "corpus"
    assert (
        tool.main(
            ["translate", "--src", str(tmp_path / "raw"), "--out", str(root / "public")]
        )
        == 0
    )
    cat = root / "catalog"
    cat.mkdir()
    (cat / "d.default.somm13.gn2.nec").write_text(
        SOMM.format(gn="GN 2 0 0 0 13 0.005 NOFILE")
    )
    (cat / "d.default.somm13.gn3.nec").write_text(
        SOMM.format(gn="GN 3 0 0 0 13 0.005 NOFILE")
    )
    (cat / "manifest.json").write_text(
        json.dumps(
            {
                "written": [
                    {
                        "design": "f.d",
                        "rung": "default",
                        "ground": "somm13",
                        "file": f"d.default.somm13.gn{v}.nec",
                        "gn": f"gn{v}",
                        "twin": f"d.default.somm13.gn{5 - v}.nec",
                    }
                    for v in (2, 3)
                ],
                "skipped": [
                    {
                        "design": "f.e",
                        "rung": "default",
                        "ground": "free",
                        "why": "nope",
                    }
                ],
            }
        )
    )
    assert tool.main(["manifest", "--root", str(root)]) == 0
    return root


def test_translate_writes_twins_and_the_manifest_covers_everything(corpus):
    pub = corpus / "public" / "coll"
    assert sorted(p.name for p in pub.iterdir()) == [
        "free.nec",
        "somm.gn2.nec",
        "somm.gn3.nec",
    ]
    rows = [
        json.loads(ln) for ln in (corpus / "manifest.jsonl").read_text().splitlines()
    ]
    assert "_meta" in rows[0]
    rows = rows[1:]
    by_path = {r["path"]: r for r in rows if r["path"]}
    assert by_path["public/coll/somm.gn2.nec"]["ground"] == "gn2"
    assert by_path["public/coll/somm.gn2.nec"]["twin"] == "public/coll/somm.gn3.nec"
    assert by_path["public/coll/somm.gn3.nec"]["ground"] == "gn3"
    assert by_path["public/coll/free.nec"]["ground"] == "free"
    assert by_path["catalog/d.default.somm13.gn3.nec"]["twin"] == (
        "catalog/d.default.somm13.gn2.nec"
    )
    skipped = {r["file"]: r for r in rows if r["status"] != "written"}
    assert "MININEC" in skipped["coll/mininec.nec"]["reason"]
    assert skipped["f.e (default, free)"]["reason"] == "nope"


FAKE_PRINTOUT = """\
                                          - - - ANTENNA INPUT PARAMETERS - - -

   TAG   SEG.    VOLTAGE (VOLTS)         CURRENT (AMPS)         IMPEDANCE (OHMS)        ADMITTANCE (MHOS)      POWER
   NO.   NO.    REAL        IMAG.       REAL        IMAG.       REAL        IMAG.       REAL        IMAG.     (WATTS)
     1 *   6 1.00000E+00 0.00000E+00 1.16664E-02 6.15107E-03 {zr}-3.53631E+01 1.16664E-02 6.15107E-03 5.83320E-03

"""


@pytest.fixture()
def fake_exe(tmp_path):
    """A stand-in NEC-4.2: `exe deck out`, writing an impedance that differs
    between GN 2 and GN 3, an input error for 'ERRDECK', a crash for 'CRASH'."""
    if os.name != "posix":
        pytest.skip("the stand-in executable is a POSIX script")
    exe = tmp_path / "fake_nec42"
    exe.write_text(
        f"#!{sys.executable}\n"
        + textwrap.dedent(
            f"""\
            import sys
            deck = open(sys.argv[1]).read()
            if 'CRASH' in deck:
                sys.exit(3)
            out = open(sys.argv[2], 'w')
            if 'ERRDECK' in deck:
                out.write('  DATAGN: SEGMENT DATA ERROR\\n')
                sys.exit(0)
            zr = '6.80000E+01' if 'GN 3' in deck else '6.70000E+01'
            out.write({FAKE_PRINTOUT!r}.format(zr=zr))
            """
        )
    )
    exe.chmod(0o755)
    return exe


def test_check_parses_classifies_and_keeps_only_failures(
    tool, corpus, fake_exe, tmp_path
):
    (corpus / "public" / "coll" / "bad.nec").write_text("CM ERRDECK\nCE\nEN\n")
    (corpus / "public" / "coll" / "crash.nec").write_text("CM CRASH\nCE\nEN\n")
    keep = tmp_path / "failed"
    report = tmp_path / "check.jsonl"
    rc = tool.main(
        [
            "check",
            "--exe",
            str(fake_exe),
            "--src",
            str(corpus),
            "--jobs",
            "2",
            "--report",
            str(report),
            "--keep-dir",
            str(keep),
            "--max-mem-mb",
            "2000",
        ]
    )
    assert rc == 0
    rows = {
        r["file"]: r
        for r in map(json.loads, report.read_text().splitlines())
        if "_meta" not in r
    }
    assert rows["public/coll/somm.gn2.nec"]["status"] == "ok"
    assert rows["public/coll/somm.gn2.nec"]["z"] == [[1, 6, 67.0, -35.3631]]
    assert rows["public/coll/somm.gn3.nec"]["z"][0][2] == 68.0
    # The CM line echoing "ERRDECK" is not what makes it an error: the
    # printout's DATAGN line is.
    assert rows["public/coll/bad.nec"]["status"] == "error"
    assert "DATA ERROR" in rows["public/coll/bad.nec"]["error"]
    assert rows["public/coll/crash.nec"]["status"] == "crash"
    kept = sorted(p.relative_to(keep).as_posix() for p in keep.rglob("*.out"))
    assert kept == ["public/coll/bad.out", "public/coll/crash.out"]

    out = tmp_path / "twins.jsonl"
    assert tool.main(["twins", str(report), "--out", str(out)]) == 0
    pairs = [json.loads(ln) for ln in out.read_text().splitlines()]
    assert {p["deck"] for p in pairs} == {
        "public/coll/somm",
        "catalog/d.default.somm13",
    }
    z2, z3 = complex(67.0, -35.3631), complex(68.0, -35.3631)
    assert pairs[0]["rel"] == pytest.approx(abs(z3 - z2) / abs(z2))


def test_aip_rows_reads_fused_fields_and_the_ex5_star(tool):
    rows = tool.aip_rows(FAKE_PRINTOUT.format(zr="6.70712E+01"))
    assert rows == [(1, 6, 67.0712, -35.3631)]

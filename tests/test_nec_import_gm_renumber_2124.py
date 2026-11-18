""".nec import: ``GM`` with NRPT 0 renumbers the moved wires (AK#2124).

``GM ITGI 0 ...`` moves the wires from ITS on IN PLACE, and NEC's MOVE still
adds the tag increment ITGI to every moved wire's nonzero tag. A later card
then addresses the moved wire by its NEW tag. The importer moved the wires
but kept their tags, so ``EX`` on the new tag was refused ("no wire has tag
6") under every dialect.

The rule is measured, not read: momwire's NEC-5 reader carries it from the
licensed binary (probes q1/q6, momwire#1669), and nec2c accepts the new tag
and refuses the old one (the skip-guarded gate below).

The issue's deck, ``q6.nec``, is momwire's fixture, reached through the
INSTALLED momwire as the ``*_1299`` modules reach theirs: a PyPI wheel ships
no ``tests/`` tree, so that gate skips under a wheel and runs on CI, where
momwire is installed editable from the submodule. The synthetic deck below
is the same shape and runs everywhere.
"""

from __future__ import annotations

import pathlib
import shutil
import subprocess
import tempfile
import warnings

import momwire
import pytest

import antennaknobs.web.server  # noqa: F401 — resolves the adapter import cycle
from antennaknobs.engines.momwire import MomwireEngine
from antennaknobs.file_designs import builder_from_text
from antennaknobs.nec_import import parse_nec

DIALECTS = ["nec2", "nec4", "nec5"]

# A wire tagged 2, moved 1 m along Y with a tag increment of 3: it answers as
# tag 5 afterwards, and no longer as tag 2.
GM_DECK = (
    "CM GM in place with a tag increment\nCE\n"
    "GW 2 11 0 0.4 -5 0 0.7 5 1e-3\n"
    "GM 3 0 0 0 0 0 1 0 0\n"
    "GE 0\nEX 0 5 4 0 1 0\nFR 0 1 0 0 14 0\nXQ\nEN\n"
)
# The same antenna written directly where the GM put it, under its new tag.
FLAT_DECK = (
    "CM the moved wire, written out\nCE\n"
    "GW 5 11 0 1.4 -5 0 1.7 5 1e-3\n"
    "GE 0\nEX 0 5 4 0 1 0\nFR 0 1 0 0 14 0\nXQ\nEN\n"
)
OLD_TAG_DECK = GM_DECK.replace("EX 0 5 4", "EX 0 2 4")


def _ak_z(text, dialect):
    cls = builder_from_text("t.nec", text, dialect=dialect)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return complex(
            MomwireEngine(
                cls(),
                ground=cls.file_ground,
                extended_kernel_default=cls.file_extended_kernel_default,
            ).impedance()[0]
        )


def _momwire_nec5_z(text):
    from momwire.deck._nec5 import parse_nec5
    from momwire.eznec import serve

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return complex(serve(parse_nec5(text)).sources[0].impedance)


@pytest.mark.parametrize("dialect", DIALECTS)
def test_the_moved_wire_answers_to_its_new_tag(dialect):
    deck = parse_nec(GM_DECK, network=True, dialect=dialect)
    (wire,) = deck.wire_tuples(specs=True)
    assert wire.p0 == pytest.approx((0.0, 1.4, -5.0))
    assert wire.p1 == pytest.approx((0.0, 1.7, 5.0))
    assert len(deck.network().ports) == 1


@pytest.mark.parametrize("dialect", DIALECTS)
def test_the_old_tag_is_gone(dialect):
    with pytest.raises(ValueError, match="no wire has tag 2"):
        parse_nec(OLD_TAG_DECK, network=True, dialect=dialect)


@pytest.mark.parametrize("dialect", DIALECTS)
def test_the_gm_deck_solves_as_the_written_out_one(dialect):
    assert _ak_z(GM_DECK, dialect) == pytest.approx(
        _ak_z(FLAT_DECK, dialect), rel=1e-12
    )


def test_a_tag_zero_wire_keeps_tag_zero():
    """NEC adds ITGI to NONZERO tags only; a tag-0 wire stays 0, so a card
    addressing the structure by absolute segment still reaches it."""
    text = (
        "CM\nCE\nGW 0 11 0 0.4 -5 0 0.7 5 1e-3\nGM 3 0 0 0 0 0 1 0 0\n"
        "GE 0\nEX 0 0 6 0 1 0\nFR 0 1 0 0 14 0\nEN\n"
    )
    deck = parse_nec(text, network=True, dialect="nec2")
    assert len(deck.network().ports) == 1
    with pytest.raises(ValueError, match="no wire has tag 3"):
        parse_nec(text.replace("EX 0 0 6", "EX 0 3 6"), network=True)


def test_feed_z_against_momwires_nec5_reader():
    """momwire's NEC-5 reader renumbers (momwire#1669). AK and momwire differ
    on this deck by the amount they differ on the written-out deck, to
    rounding: the GM adds nothing between them. (That standing gap, ~6.5e-3
    on this 11-segment dipole, is the two front ends' feed models and is
    there without any GM.)"""
    ak_gm, ak_flat = _ak_z(GM_DECK, "nec5"), _ak_z(FLAT_DECK, "nec5")
    mw_gm, mw_flat = _momwire_nec5_z(GM_DECK), _momwire_nec5_z(FLAT_DECK)
    assert mw_gm == pytest.approx(mw_flat, rel=1e-12)
    assert ak_gm / mw_gm == pytest.approx(ak_flat / mw_flat, rel=1e-12)
    assert abs(ak_gm - mw_gm) / abs(mw_gm) < 1e-2


@pytest.mark.skipif(shutil.which("nec2c") is None, reason="nec2c not installed")
def test_nec2c_renumbers_in_place_too():
    """The NEC-2 rule, on nec2c itself: the new tag runs, the old one stops
    the engine."""

    def run(text):
        with tempfile.TemporaryDirectory() as td:
            p = pathlib.Path(td)
            (p / "a.nec").write_text(text)
            r = subprocess.run(
                ["nec2c", "-i", "a.nec", "-o", "a.out"],
                cwd=td,
                capture_output=True,
                text=True,
                timeout=60,
            )
            out = (p / "a.out").read_text(errors="replace")
        return r.returncode, out

    code, out = run(GM_DECK)
    assert code == 0 and "ANTENNA INPUT PARAMETERS" in out
    code, out = run(OLD_TAG_DECK)
    assert code != 0 and "NO SEGMENT HAS AN ITAG OF 2" in out


# --- the issue's deck, through the installed momwire ---------------------------

Q6 = (
    pathlib.Path(momwire.__file__).resolve().parents[2]
    / "tests"
    / "fixtures"
    / "nec5_4nec2_cards_1669"
    / "q6.nec"
)
Q6_SKIP_REASON = (
    f"momwire's q6 fixture is not on disk at {Q6} — it is read from the "
    "momwire submodule (editable install), so a wheel-only momwire cannot run it"
)


@pytest.mark.skipif(not Q6.is_file(), reason=Q6_SKIP_REASON)
def test_q6_imports_under_every_dialect_and_matches_momwire():
    text = Q6.read_text(errors="replace")
    for dialect in DIALECTS:
        parse_nec(text, network=True, dialect=dialect)
    # q6 is `GW 1 ..` then `GM 5 0 .. 1 ..`: tag 6, 1 m along Y.
    lines = text.splitlines()
    (gw,) = [ln for ln in lines if ln.split()[:1] == ["GW"]]
    (gm,) = [ln for ln in lines if ln.split()[:1] == ["GM"]]
    f = gw.split()
    assert gm.split()[1:3] == ["5", "0"] and float(gm.split()[7]) == 1.0
    f[1] = str(int(f[1]) + 5)
    f[4], f[7] = str(float(f[4]) + 1.0), str(float(f[7]) + 1.0)
    flat = "\n".join(" ".join(f) if ln is gw else ln for ln in lines if ln is not gm)
    ak_gm, ak_flat = _ak_z(text, "nec5"), _ak_z(flat, "nec5")
    mw_gm, mw_flat = _momwire_nec5_z(text), _momwire_nec5_z(flat)
    assert ak_gm == pytest.approx(ak_flat, rel=1e-12)
    assert ak_gm / mw_gm == pytest.approx(ak_flat / mw_flat, rel=1e-12)
    assert abs(ak_gm - mw_gm) / abs(mw_gm) < 1e-2

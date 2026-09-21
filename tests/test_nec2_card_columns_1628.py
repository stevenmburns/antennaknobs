"""Every card antennaknobs writes for NEC-2 fits in 80 columns (AK#1628).

AC6LA's `nec2dxs11k.exe` (Arie Voors' 4nec2 build) rejected every deck we
wrote, even `dipoles.invvee`, with GEOMETRY DATA CARD ERROR, while `nec2c` ran
the same decks cleanly. Settled on the real binary: it reads each card as an
80-COLUMN record and parses free-format numbers inside it, dropping the rest
without a word. Our GW cards were 105 columns (`.6E` numbers, double spaces),
so the reader saw Z2 = 5 and a radius of 0.

| deck | longest line | nec2dxs11k |
|---|---:|---|
| as written before, `.6E` | 105 | GEOMETRY DATA CARD ERROR |
| compact free format, E-notation kept on GN/EX/FR | 46 | runs, 4.85323E+01 - 8.10377E+00 |
| the same, radius pushed to column 82 | 87 | GEOMETRY DATA CARD ERROR, radius read as 0 |

So the fix is not a card format; it is length. Numbers are written as short as
7 significant figures allow, which is what `.6E` carried, and a GW card that
would still pass column 80 drops its leading zeros (`-.05`), then figures.
"""

from __future__ import annotations

import importlib

import pytest

import antennaknobs.web.examples  # noqa: F401  registration order
from antennaknobs import AntennaBuilder, resolve_variant_params
from antennaknobs.designs.dipoles.invvee import Builder as InvVee
from antennaknobs.network import Wire
from antennaknobs.nec_export import CARD_COLUMNS, _gw, _num, export_nec
from antennaknobs.web.adapter import list_designs


def _as_an_80_column_reader_reads(line):
    """The fields a NEC-2 Fortran build sees on this card: free format, inside
    the first 80 columns."""
    return line[:CARD_COLUMNS].split()


@pytest.mark.parametrize(
    ("x", "kw", "text"),
    [
        (5.682399, {}, "5.682399"),
        (0.0005, {}, "0.0005"),
        (7.0, {}, "7"),
        (-0.0, {}, "0"),
        (5.8e7, {}, "5.8e+07"),
        (-0.05, {"bare": True}, "-.05"),
        (0.0005, {"bare": True}, ".0005"),
        (12.5, {"bare": True}, "12.5"),
    ],
)
def test_numbers_are_compact_at_seven_figures(x, kw, text):
    assert _num(x, **kw) == text


def test_the_reported_deck_fits_and_reads_whole():
    """Dan's reproducer, the stock inverted vee over finite ground: every card
    is inside 80 columns, so the reader sees every field."""
    deck = export_nec(
        InvVee(resolve_variant_params(InvVee, "dipole")),
        ground=("finite", 13.0, 0.005),
        include_rp=False,
    )
    cards = [ln for ln in deck.splitlines() if not ln.startswith("CM")]
    assert max(len(ln) for ln in cards) <= CARD_COLUMNS
    for ln in cards:
        assert _as_an_80_column_reader_reads(ln) == ln.split(), ln
    gw = [ln for ln in cards if ln.startswith("GW ")]
    assert all(len(ln.split()) == 10 for ln in gw), gw


def test_every_catalog_deck_fits():
    """The whole catalog, since a design's coordinates set its card lengths.
    Three catalog GW cards reach 81 columns at 7 figures (the helices and the
    fan dipole) and fit once their leading zeros go."""
    exported = 0
    for name in list_designs():
        cls = importlib.import_module(f"antennaknobs.designs.{name}").Builder
        try:
            deck = export_nec(cls())
        except (NotImplementedError, ValueError) as exc:
            # The writer's own refusals (networks it cannot spell, vertex
            # ports) stay; the column tripwire must never be one of them.
            assert "column" not in str(exc), (name, exc)
            continue
        exported += 1
        for ln in deck.splitlines():
            if not ln.startswith("CM"):
                assert len(ln) <= CARD_COLUMNS, (name, ln)
    # Not vacuous: most of the catalog exports.
    assert exported >= 60, exported


def test_a_long_gw_card_drops_its_leading_zeros_before_any_figure():
    p0, p1 = (-0.01092129, -0.01092129, -0.01092129), (-0.01092129, 0.01092129, -0.01)
    card = _gw(1, 21, p0, p1, 0.0001234567)
    assert len(card) <= CARD_COLUMNS
    assert "-.01092129" in card  # all seven figures kept
    back = [float(x) for x in card.split()[3:]]
    assert back == pytest.approx([*p0, *p1, 0.0001234567], rel=1e-7)


def test_a_gw_card_that_cannot_fit_refuses():
    tiny = -1.234567e-05
    with pytest.raises(ValueError, match="80-column"):
        _gw(99999, 99999, (tiny,) * 3, (tiny,) * 3, 1.234567e-06)


class _Tiny(AntennaBuilder):
    default_params = {"freq": 28.5}

    def build_wires(self):
        return [Wire((0, 0, -2.5), (0, 0, 2.5), n_seg=9, ex=1 + 0j)]


def test_the_tripwire_refuses_a_long_card(monkeypatch):
    """The last line of defence, independent of how any card was built."""
    import antennaknobs.nec_export as ne

    monkeypatch.setattr(ne, "_gw", lambda *a: "GW " + "1 " * 40)
    with pytest.raises(ValueError, match="column 80"):
        export_nec(_Tiny(), ground=None)

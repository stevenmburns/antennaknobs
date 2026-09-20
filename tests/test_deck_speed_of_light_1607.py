"""An imported deck is solved at NEC's speed of light, not the SI one
(AK#1607).

Two shipping routes into the same solver disagreed on the metre-megahertz
product: `momwire.eznec.serve` (the signed Windows drop-in) turns a deck's
frequency into a wavelength with NEC's own 299.8, antennaknobs (workbench and
CLI) used the SI 299.792458. That is 2.5e-5 of relative frequency, and it was
the ENTIRE residual between the two routes on a network-free deck: pinning
lambda takes the corpus's network-free median from 4.4e-4 to 1.2e-15, with 40
of 49 decks at or below 1e-12 rather than none.

Which constant is right here is not a matter of taste. A deck is a document in
a dialect, and the dialect's metre-megahertz product is part of it; solving it
at the SI c models a slightly different antenna than the one its author wrote
down and than every other tool they will compare against. The scope is
therefore DECKS: `AntennaBuilder.c_light_mhz_m` is SI, and only the import
seam (`file_designs`) overrides it, so an antennaknobs design — whose
dimensions are ours, with no dialect involved — is untouched.

`test_the_constant_is_what_the_engine_printed` is the load-bearing one. The
constant is a MEASUREMENT off the engine's own output, and the printouts that
measure it are committed, so it stays one: a later "correction" of 299.8 to
the physical speed of light fails here with the printed cell it contradicts.
"""

import pathlib

import momwire
import numpy as np
import pytest

from antennaknobs.builder import C_LIGHT_MHZ_M, AntennaBuilder
from antennaknobs.engines import MomwireEngine
from antennaknobs.file_designs import builder_from_file
from antennaknobs.nec_import import NEC_C_LIGHT_MHZ_M, parse_nec

# momwire's EZNEC corpus, reached through the INSTALLED momwire (the submodule
# at the recorded pointer), never copied here — ten momwire modules read the
# same tree and a copy drifts (AK#1299).
EZNEC = pathlib.Path(momwire.__file__).resolve().parents[2] / "tests/fixtures/eznec"
DECKS, PRINTOUTS = EZNEC / "decks", EZNEC / "printouts"

# Network-free decks: no TL, no NT. The TL/NT population keeps a residual two
# orders larger that lambda does not move at all — that is AK#1608, and is
# deliberately not gated here.
NETWORK_FREE = [
    "0010_dipole-in-free-space",
    "0013_vhf-ground-plane",
    "0015_vertical-over-real-ground",
    "0019_vertical-over-real-ground",
    "0020_vertical-over-real-ground",
    "0021_vertical-over-real-ground",
]


def _text(path):
    return path.read_text(errors="replace")


def _cell(printout, label):
    """The float in a `LABEL= 1.2345E+01 UNITS` cell of a NEC printout."""
    for line in _text(printout).splitlines():
        if label in line:
            return float(line.split(label)[1].split()[0])
    raise AssertionError(f"{printout.name}: no {label!r} cell")


def _deck_freq(stem):
    """The deck's OWN frequency, off its FR card.

    Not the printout's `FREQUENCY=` cell: that is printed to five digits, so
    0010's 299.7925 MHz reads back as 299.79, and the discriminating digit of
    this measurement is the sixth."""
    lo, hi = parse_nec(_text(DECKS / f"{stem}.nec"), name=stem, network=True).freq_mhz
    assert lo == hi, f"{stem}: a swept deck has no single frequency"
    return lo


def test_the_constant_is_what_the_engine_printed():
    """Measured off two committed printouts that discriminate, not assumed.

    Decisive at the engine's own print precision, in both directions: the
    printed cell is what 299.8 gives and is NOT what the SI c gives."""
    # Leg 1 — the printed WAVELENGTH cell. 0019 runs at 7 MHz.
    out = PRINTOUTS / "0019_vertical-over-real-ground.out"
    freq = _deck_freq("0019_vertical-over-real-ground")
    printed = f"{_cell(out, 'WAVELENGTH='):.4E}"
    assert printed == f"{NEC_C_LIGHT_MHZ_M / freq:.4E}" == "4.2829E+01"
    assert f"{C_LIGHT_MHZ_M / freq:.4E}" == "4.2827E+01" != printed

    # Leg 2 — the current table's segment length, "normalized by wavelength".
    # 0010 runs at 299.7925 MHz, where the two constants differ in the fifth
    # digit of the ratio rather than the fifth of the wavelength.
    out = PRINTOUTS / "0010_dipole-in-free-space.out"
    deck = parse_nec(
        _text(DECKS / "0010_dipole-in-free-space.nec"), name="0010", network=True
    )
    wire = deck.wires[0]
    seg_m = float(np.linalg.norm(np.subtract(wire.p2, wire.p1))) / wire.n_seg
    freq = _deck_freq("0010_dipole-in-free-space")

    row = next(ln for ln in _text(out).splitlines() if ln.strip().startswith("1    1"))
    printed = f"{float(row.split()[5]):.5E}"
    assert printed == f"{seg_m / (NEC_C_LIGHT_MHZ_M / freq):.5E}" == "4.54534E-02"
    assert f"{seg_m / (C_LIGHT_MHZ_M / freq):.5E}" == "4.54546E-02" != printed


def test_a_deck_carries_the_dialects_constant_and_a_design_keeps_si():
    """The scope line: only the import seam moves off SI."""
    assert AntennaBuilder.c_light_mhz_m == C_LIGHT_MHZ_M == 299.792458
    assert (
        builder_from_file(
            str(DECKS / "0019_vertical-over-real-ground.nec")
        ).c_light_mhz_m
        == NEC_C_LIGHT_MHZ_M
        == 299.8
    )

    from antennaknobs.designs.verticals.buried_radial_vertical import Builder

    assert Builder.c_light_mhz_m == C_LIGHT_MHZ_M


def test_the_si_path_is_bit_identical_to_the_constant_it_replaced():
    """The trap this fix could have walked into, pinned.

    `_wavelength_for` used to be `299_792_458.0 / (f * 1e6)`. Spelled the
    tidier `299.792458 / f` it differs by an ulp at 4 of these 13 frequencies
    — a silent perturbation of every catalog number, arriving as unexplained
    1e-16 noise in gates that have nothing to do with decks. The engine keeps
    the old arithmetic shape so the SI path cannot move at all."""
    eng = MomwireEngine.__new__(MomwireEngine)
    eng.builder = AntennaBuilder.__new__(AntennaBuilder)
    for f in (
        7.0,
        14.0,
        14.15,
        21.2,
        28.4,
        50.1,
        144.2,
        299.7925,
        3.75,
        1.83,
        0.5,
        440.0,
        1296.0,
    ):
        assert eng._wavelength_for(f) == 299_792_458.0 / (f * 1e6)


@pytest.mark.parametrize("stem", NETWORK_FREE)
def test_the_two_routes_agree_on_a_network_free_deck(stem):
    """THE claim: with the constant shared, there is nothing else between the
    two routes on these decks at all.

    The bar is 1e-12 — eight orders under the 4.4e-4 the disagreement used to
    be, and three above the 1.2e-15 that remains, which is the solve's own
    conditioning rather than a difference of model."""
    from momwire.deck._nec5 import parse_nec5
    from momwire.eznec import serve

    path = DECKS / f"{stem}.nec"
    mw = np.asarray(
        [complex(s.impedance) for s in serve(parse_nec5(_text(path))).sources]
    )
    cls = builder_from_file(str(path))
    ak = np.asarray(MomwireEngine(cls(), ground=cls.file_ground).impedance())
    rel = float(np.max(np.abs(ak - mw) / np.abs(mw)))
    assert rel < 1e-12, f"AK {ak} vs serve {mw}, rel {rel:.3e}"

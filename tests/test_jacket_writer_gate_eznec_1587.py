"""The jacketed-wire NEC writers against EZNEC's own insulated-wire deck
(issue #1587).

AK's writers spell a jacket as the pair a' + L' (issue #1523,
`engines._nec_wire`): the equivalent radius on the GW card, the jacket's
inductance on LD 2, and LD 5's conductivity rescaled by (a/a')^2. Capture 0206
is the first deck EZNEC wrote for the same wire: Dipole1 with insulation only
(eps_r 2.5, 1.0 mm thick, tan delta 0.01, on a 0.5 mm conductor), so
a = 0.5 mm and b = 1.5 mm.

WHAT IS GATED, AND AGAINST WHAT

  * a' — both writers against the capture's GW radius.
  * L' — both writers against the capture's LD 2 inductance. They do NOT agree
    to the deck's five figures, and the difference is stated rather than
    widened away: see ``test_inductance_is_eznecs_once_the_loss_tangent...``.
  * R' — EZNEC writes one (1.655357 ohm/m). Our writers carry none, which is
    antennaknobs#1997, so the gate here is that the closed form reproduces
    EZNEC's number and that our field is zero, not that the two agree.
  * the LD 5 conductivity — capture 0219 is the EZNEC deck that carries one,
    and it is NOT on main (it is in open PR #1802). So the only EZNEC-written
    bytes this module reads are 0206's. The conductivity gate is against the
    closed form, with EZNEC's card value entered as the literal issue #1587
    quotes; when 0219 lands it should be read from the capture instead.

TOLERANCES ARE DERIVED, NOT CHOSEN. A card field printed to k figures says its
value lies within half a unit of the last figure printed, so two fields agree
when they differ by no more than the sum of their two half-units. Equality is
wrong here for the reason #1587 records: EZNEC scales from the exact a', and
the GW card carries four figures of it.
"""

from __future__ import annotations

import math
import re
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType

import pytest
from momwire import equivalent_radius, insulation_inductance

from antennaknobs import AntennaBuilder
from antennaknobs.nec5_export import export_nec5
from antennaknobs.nec_export import export_nec
from antennaknobs.wire_catalog import WireSpec

CAPTURE_0206 = (
    Path(__file__).resolve().parents[1]
    / "scratch"
    / "eznec-capture"
    / "0206_20260918-091525"
    / "post"
    / "Docs__EZN5.NEC"
)

A, B, EPS_R, TAN_DELTA = 5.0e-4, 1.5e-3, 2.5, 0.01
FREQ_MHZ = 299.7925

# The three closed-form numbers issue #1587 states, as it states them.
A_EQ_1587 = "9.66591e-4"
L_INS_1587 = "1.318423e-7"
SIGMA_1587 = "1.53781e7"
# EZNEC's copper, and the LD 5 field of capture 0219, both as quoted in issue
# #1587. Neither is read from a file: 0219 is not on main.
EZNEC_COPPER = "5.7471E+7"
LD5_0219_AS_QUOTED = "1.5378E+7"


def _half_unit(field: str) -> float:
    """Half a unit in the last figure ``field`` prints."""
    return float(Decimal(1).scaleb(Decimal(field).as_tuple().exponent) / 2)


def _agree(x: str, y: str) -> bool:
    return abs(float(x) - float(y)) <= _half_unit(x) + _half_unit(y)


def _card(deck: str, mnemonic: str) -> list[str]:
    """The fields of the one ``mnemonic`` card in ``deck``. EZNEC separates
    fields with commas and our writers with spaces."""
    cards = [
        re.split(r"[,\s]+", ln.strip())
        for ln in deck.splitlines()
        if re.match(rf"{mnemonic}\b", ln)
    ]
    assert len(cards) == 1, f"expected one {mnemonic} card, found {len(cards)}"
    return cards[0]


def _capture() -> str:
    # Bytes, then decoded: the capture is a byte oracle stored with CRLF.
    return CAPTURE_0206.read_bytes().decode("ascii")


class _Dipole1(AntennaBuilder):
    """Capture 0206's wire: 0.5 m along y, 11 segments, the same jacket."""

    default_params = MappingProxyType({"freq": FREQ_MHZ})
    conductivity: float | None = None

    def build_wires(self):
        return [((0.0, -0.25, 0.0), (0.0, 0.25, 0.0), 11, 1 + 0j)]

    def build_wire_material(self):
        return WireSpec(
            radius=A,
            conductivity=self.conductivity,
            insulation_radius=B,
            insulation_eps_r=EPS_R,
        )


def _nec5_deck(builder) -> str:
    return export_nec5(
        builder, ground=None, design="dipole1", rung="0206", ground_name="free"
    )


def _nec2_deck(builder) -> str:
    return export_nec(builder, ground=None, include_rp=False)


WRITERS = pytest.mark.parametrize(
    "write", [_nec5_deck, _nec2_deck], ids=["nec5_export", "nec2_writer"]
)


class _Dipole1Copper(_Dipole1):
    """The same wire with Wire Loss = Copper, at EZNEC's own conductivity."""

    conductivity = float(EZNEC_COPPER)


def _closed_form_z_per_metre() -> complex:
    """Z' = j*omega*(mu0/2pi)*ln(b/a)*(1 - 1/eps*), eps* = eps_r*(1 - j*tan d):
    the form issue #1587 found EZNEC's two LD 2 numbers reproduce from."""
    mu0_2pi = 2.0 * float(insulation_inductance(1.0, math.e, 2.0))
    omega = 2.0 * math.pi * FREQ_MHZ * 1e6
    eps = EPS_R * (1.0 - 1j * TAN_DELTA)
    return 1j * omega * mu0_2pi * math.log(B / A) * (1.0 - 1.0 / eps)


def _loss_tangent_factor() -> float:
    """L'(tan delta) / L'(0): the real part of 1/eps* is 1/(eps_r*(1 + t^2)),
    so a lossy jacket's inductance is larger than the lossless one's, at second
    order in the loss tangent. 1.0000667 for this jacket."""
    return (1.0 - 1.0 / (EPS_R * (1.0 + TAN_DELTA**2))) / (1.0 - 1.0 / EPS_R)


def test_capture_0206_is_the_deck_issue_1587_describes():
    """The premise, read from the bytes: the equivalent radius on GW, one
    whole-wire LD 2 carrying R' and L', and no LD 5 (Wire Loss was Zero). The
    conductor's own 0.5 mm appears in no field, so a reader of this deck is
    told the equivalent radius is the wire: a round-trip fact to record."""
    deck = _capture()
    assert _card(deck, "GW")[-1] == "9.666E-4"
    assert _card(deck, "LD") == [
        "LD",
        "2",
        "1",
        "0",
        "0",
        "1.655357",
        "1.3184E-7",
        "0.",
    ]
    numbers = [
        float(f)
        for ln in deck.splitlines()
        if not ln.startswith(("CM", "CE", "EN"))
        for f in re.split(r"[,\s]+", ln.strip())[1:]
    ]
    assert A not in numbers


def test_the_closed_forms_reproduce_eznecs_three_numbers():
    """a', L' and R' from closed form against the deck, each to the figures
    the deck prints, and against the values #1587 states."""
    deck = _capture()
    a_eq = float(equivalent_radius(A, B, EPS_R))
    z = _closed_form_z_per_metre()
    l_ins = z.imag / (2.0 * math.pi * FREQ_MHZ * 1e6)

    assert _agree(repr(a_eq), A_EQ_1587)
    assert _agree(repr(a_eq), _card(deck, "GW")[-1])
    assert _agree(repr(l_ins), L_INS_1587)
    assert _agree(repr(l_ins), _card(deck, "LD")[6])
    assert _agree(repr(z.real), _card(deck, "LD")[5])


@WRITERS
def test_equivalent_radius_is_eznecs(write):
    ours = _card(write(_Dipole1()), "GW")[-1]
    assert _agree(ours, _card(_capture(), "GW")[-1])
    assert _agree(ours, A_EQ_1587)


@WRITERS
def test_inductance_is_eznecs_once_the_loss_tangent_is_accounted_for(write):
    """Where our L' differs from EZNEC's, and why.

    Our writers print 1.318335e-7 and the deck 1.3184E-7: one unit apart in
    the deck's fifth figure, so "the same to five figures" does not hold. The
    whole difference is the jacket's loss tangent. EZNEC's L' is the imaginary
    part of the complex-permittivity form, which is the lossless L' times
    ``_loss_tangent_factor()``; ours is the lossless L', because the wire spec
    carries no loss tangent (antennaknobs#1997). Scaled by that factor ours
    lands on the deck.

    The unscaled comparison is asserted to MISS, so this gate cannot pass by
    a tolerance wide enough to hide the term it names."""
    ld = _card(write(_Dipole1()), "LD")
    assert ld[:5] == ["LD", "2", "0", "0", "0"]
    ours, eznec = ld[6], _card(_capture(), "LD")[6]
    tol = _half_unit(ours) + _half_unit(eznec)
    assert abs(float(ours) * _loss_tangent_factor() - float(eznec)) <= tol
    assert abs(float(ours) - float(eznec)) > tol
    assert _agree(ours, repr(float(insulation_inductance(A, B, EPS_R))))


@WRITERS
def test_our_ld2_carries_no_resistance(write):
    """EZNEC writes R' = 1.655357 ohm/m for this jacket's tan delta of 0.01.
    Our writers carry no R': the LD 2 resistance field is zero, and a lossy
    jacket's dissipation is not in the deck. That is antennaknobs#1997, and
    this pins the present state so the day it changes is a deliberate edit."""
    assert float(_card(write(_Dipole1()), "LD")[5]) == 0.0
    assert float(_card(_capture(), "LD")[5]) > 1.0


@WRITERS
def test_a_lossless_jacket_writes_no_ld5(write):
    """As capture 0206: insulation alone adds LD 2 and nothing else."""
    assert not re.search(r"^LD 5\b", write(_Dipole1()), re.M)


@WRITERS
def test_ld5_conductivity_is_scaled_from_the_full_precision_radius(write):
    """sigma*(a/a')^2 with EZNEC's copper, 1.53781e7.

    Against the closed form to our own printed figures, and against EZNEC's
    card to its five. EZNEC's copper is itself known to five figures, so its
    half-unit is carried through the scaling into the second tolerance.

    The last assertion is #1587's trap, stated as a fact: the same scaling
    from the FOUR-figure radius a deck carries gives 1.537783e7, which is not
    our card. A consumer recomputing from a deck cannot reproduce it."""
    sigma = float(EZNEC_COPPER)
    deck = write(_Dipole1Copper())
    lds = [ln.split() for ln in deck.splitlines() if ln.startswith("LD 5")]
    assert len(lds) == 1
    ours = lds[0][5]
    a_eq = float(equivalent_radius(A, B, EPS_R))
    scale = (A / a_eq) ** 2

    assert abs(float(ours) - sigma * scale) <= _half_unit(ours)
    assert _agree(ours, SIGMA_1587)
    tol = (
        _half_unit(ours)
        + _half_unit(LD5_0219_AS_QUOTED)
        + _half_unit(EZNEC_COPPER) * scale
    )
    assert abs(float(ours) - float(LD5_0219_AS_QUOTED)) <= tol

    from_deck_radius = sigma * (A / float(_card(_capture(), "GW")[-1])) ** 2
    assert abs(from_deck_radius - float(ours)) > _half_unit(ours)

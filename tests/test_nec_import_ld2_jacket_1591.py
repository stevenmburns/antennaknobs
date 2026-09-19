"""LD 2 jacket-pair inversion (issue #1591).

AK's own writers spell a jacket as the a'+L' pair (issue #1523,
`engines._nec_wire.nec_wire_material`): the GW card carries the fattened
equivalent radius a', and LD 2 carries the jacket's series inductance L'.
The importer used to drop LD 2 outright (`ignored_detail` reported "type 2
distributed per-metre loading is not translated"), so a round-tripped
jacketed wire kept the fattened radius with none of the inductance that pays
for it — on the EZNEC capture this issue is named for, omega*L' is about
248 ohms/m on a half-metre wire, not a rounding error.

`engines._nec_wire.jacket_from_equivalent_radius` inverts the pair exactly:
ln(a'/a) = L' / (mu0/2pi) recovers the conductor radius `a` with no
root-finding. (b, eps_r) is NOT recoverable the same way -- only the product
k*ln(b/a) is pinned by a' and L', so every (b, eps_r) on that curve is
electrically identical. What lands in `NecDeck.wire_insulation` is one
canonical member of that family (`CANONICAL_INSULATION_EPS_R`), not a
measurement of the physical jacket -- these tests hold the ELECTRICAL
invariants (radius, a', L') exact and never assert a specific (b, eps_r).
"""

from __future__ import annotations

import math

from momwire import equivalent_radius, insulation_inductance

from antennaknobs.engines._nec_wire import (
    CANONICAL_INSULATION_EPS_R,
    jacket_from_equivalent_radius,
    nec_wire_material,
)
from antennaknobs.nec_import import parse_nec
from antennaknobs.wire_catalog import WireSpec

FREQ_MHZ = 299.7925


def _num(x: float) -> str:
    """Full double precision -- NEC's usual 6-7 significant digit card
    fields cannot round-trip to the 9+ significant figures these tests hold
    the inversion to; the precision has to come from the test fixture, not
    from `nec_export`'s formatter."""
    return f"{x:.17E}"


def _capture_0219_shape(a_eq: float, l_ins: float, *, ld_order=("5", "2")) -> str:
    """The EZNEC capture 0219 this issue is named for, verbatim in card
    shape: one 11-segment wire, an EX 4 (NEC-5 current source, issue #1243)
    needing the NEC-5 dialect, and the two addressing forms this issue's
    brief calls out as untested anywhere else in the corpus --
    ``LD 5,0,1,11`` is tag 0 with an ABSOLUTE segment span, ``LD 2,1,0,0``
    is tag 1 with the whole-wire sentinel, and LD 5 is written first.
    ``r_per_len`` (1.655357, EZNEC's own F1) is carried through unchanged to
    confirm it does not block the jacket reading -- AK's jacket model has no
    resistive term, so it is dropped, and NAMED in ``ignored_detail`` rather
    than dropped in silence (issue #1591 review).
    """
    cards = {
        "5": "LD 5,0,1,11,1.5378E+7,1.",
        "2": f"LD 2,1,0,0,1.655357,{_num(l_ins)},0.",
    }
    ld_lines = "\n".join(cards[k] for k in ld_order)
    return (
        "CM ! Written by EZNEC/Pro+ v. 7.0 in NEC-5 format.\nCE\n"
        f"GW 1,11,0.,-.25,0.,0.,.25,0.,{_num(a_eq)}\n"
        "GE 0,-1\n"
        f"{ld_lines}\n"
        f"FR 0,1,0,0,{FREQ_MHZ}\n"
        "GN -1\n"
        "EX 4,1,6,0,1.414214,0.\n"
        "XQ\nEN\n"
    )


def test_0219_recovers_the_conductor_radius_to_9_significant_figures():
    a, b, eps_r = 5.0e-4, 9.0e-4, 3.5
    a_eq = float(equivalent_radius(a, b, eps_r))
    l_ins = float(insulation_inductance(a, b, eps_r))

    deck = parse_nec(_capture_0219_shape(a_eq, l_ins), name="0219", network=True)

    assert deck.wire_insulation and deck.wire_insulation[0][0] == 0
    wire, radius = deck.wire_conductor_radius[0]
    assert wire == 0
    assert math.isclose(radius, a, rel_tol=1e-9)  # >= 9 significant figures
    # LD 5's conductivity survives alongside, unchanged (requirement 3).
    assert deck.wire_conductivity == ((0, 1.5378e7),)
    # The LD 2 is fully consumed -- no residue in ignored_detail.
    assert not any("type 2" in why for _m, why in deck.ignored_detail)


def test_0219_ld5_absolute_span_and_ld2_whole_wire_sentinel_agree_either_order():
    """The mixed-addressing shape is the point of the 0219 deck: LD 5 names
    an ABSOLUTE segment span (tag 0), LD 2 names a whole-wire SENTINEL (tag
    1, 0 0). A single-wire deck cannot by itself distinguish "absolute
    segment numbering" from "numbering local to the wire's own tag" (they
    coincide when there is exactly one wire) -- the two-wire deck below
    closes that gap. This test pins that deck order does not matter, since
    the two cards touch disjoint fields (conductivity vs. jacket) on the
    same wire."""
    a, b, eps_r = 5.0e-4, 9.0e-4, 3.5
    a_eq = float(equivalent_radius(a, b, eps_r))
    l_ins = float(insulation_inductance(a, b, eps_r))

    forward = parse_nec(
        _capture_0219_shape(a_eq, l_ins, ld_order=("5", "2")), network=True
    )
    swapped = parse_nec(
        _capture_0219_shape(a_eq, l_ins, ld_order=("2", "5")), network=True
    )

    assert forward.wire_conductivity == swapped.wire_conductivity == ((0, 1.5378e7),)
    assert forward.wire_insulation == swapped.wire_insulation
    assert forward.wire_conductor_radius == swapped.wire_conductor_radius
    untranslated = [
        why
        for d in (forward, swapped)
        for _m, why in d.ignored_detail
        if "not translated" in why
    ]
    assert not untranslated, untranslated


def _two_wire_mixed_addressing_deck(
    a_eq: float, l_ins: float, *, ld_order=("5", "2")
) -> str:
    """A wire that must NOT be touched (tag 1, global segments 1-5) plus the
    jacketed wire (tag 2, global segments 6-16). ``LD 5,0,6,16`` is an
    ABSOLUTE global-segment span that happens to cover exactly the second
    wire; ``LD 2,2,0,0`` addresses the same wire by NEC tag. A bug that
    confused the two addressing forms -- e.g. read the absolute span as
    local to tag 0, or the sentinel as a global range -- would attribute
    conductivity/insulation to the WRONG wire index (0 instead of 1), or to
    both, or to neither; this pins wire index 1 exclusively."""
    cards = {
        "5": "LD 5,0,6,16,1.5378E+7,1.",
        "2": f"LD 2,2,0,0,1.655357,{_num(l_ins)},0.",
    }
    ld_lines = "\n".join(cards[k] for k in ld_order)
    return (
        "CM t\nCE\n"
        "GW 1,5,0.,-1.,10.,0.,-.5,10.,0.0005\n"
        f"GW 2,11,0.,0.,10.,0.,.5,10.,{_num(a_eq)}\n"
        "GE 0\n"
        f"{ld_lines}\n"
        "EX 0,1,3,0,1.,0.\n"
        "FR 0,1,0,0,3.68\n"
        "GN -1\nXQ\nEN\n"
    )


def test_mixed_addressing_lands_on_the_correct_wire_only():
    a, b, eps_r = 5.0e-4, 9.0e-4, 3.5
    a_eq = float(equivalent_radius(a, b, eps_r))
    l_ins = float(insulation_inductance(a, b, eps_r))

    forward = parse_nec(
        _two_wire_mixed_addressing_deck(a_eq, l_ins, ld_order=("5", "2")), network=True
    )
    swapped = parse_nec(
        _two_wire_mixed_addressing_deck(a_eq, l_ins, ld_order=("2", "5")), network=True
    )

    for deck in (forward, swapped):
        assert deck.wire_conductivity == ((1, 1.5378e7),)
        assert [wi for wi, _ in deck.wire_insulation] == [1]
        assert [wi for wi, _ in deck.wire_conductor_radius] == [1]
        assert math.isclose(deck.wire_conductor_radius[0][1], a, rel_tol=1e-9)
        assert not [
            why for _m, why in deck.ignored_detail if "not translated" in why
        ], deck.ignored_detail
    assert forward.wire_conductivity == swapped.wire_conductivity
    assert forward.wire_insulation == swapped.wire_insulation
    assert forward.wire_conductor_radius == swapped.wire_conductor_radius


def _minimal_deck(radius, conductivity, inductance, freq=3.68) -> str:
    sigma_line = (
        f"LD 5 0 0 0 {_num(conductivity)} 0. 0.\n" if conductivity is not None else ""
    )
    return (
        "CM t\nCE\n"
        f"GW 1 11 0. -.25 0. 0. .25 0. {_num(radius)}\n"
        "GE 0\n"
        f"{sigma_line}"
        f"LD 2 1 0 0 0. {_num(inductance)} 0.\n"
        "EX 0 1 6 0 1. 0.\n"
        f"FR 0 1 0 0 {freq}\n"
        "GN -1\nXQ\nEN\n"
    )


def test_round_trip_through_nec_wire_material_is_exact_over_several_triples():
    """Requirement 2: forward through `nec_wire_material` (the writer AK's
    own engines use), import the result, then check the RE-DERIVED a' and L'
    -- recomputed forward from what the importer recovered -- equal the
    ORIGINALS, at rel_tol 1e-12. Several (a, b, eps_r) triples, not one, and
    the recovered conductor radius is checked directly too (stronger than
    the issue asks, and free given the identity is exact)."""
    triples = [
        (5.0e-4, 9.0e-4, 3.5),
        (1.0e-3, 1.5e-3, 2.5),
        (2.0e-4, 1.0e-3, 10.0),
        (8.0e-4, 8.5e-4 * 1.01, 1.2),
        (5.0e-4, 5.0e-4 * 1.5, 100.0),
    ]
    for a, b, eps_r in triples:
        spec = WireSpec(
            radius=a, conductivity=5.8e7, insulation_radius=b, insulation_eps_r=eps_r
        )
        mat = nec_wire_material(a, 5.8e7, spec)
        deck = parse_nec(
            _minimal_deck(mat.radius, mat.conductivity, mat.inductance), network=True
        )

        assert deck.wire_conductor_radius and deck.wire_insulation
        _wi, radius = deck.wire_conductor_radius[0]
        _wi2, (ins_radius, ins_eps_r) = deck.wire_insulation[0]
        assert math.isclose(radius, a, rel_tol=1e-12)
        assert ins_eps_r == CANONICAL_INSULATION_EPS_R

        a_eq_again = float(equivalent_radius(radius, ins_radius, ins_eps_r))
        l_ins_again = float(insulation_inductance(radius, ins_radius, ins_eps_r))
        assert math.isclose(a_eq_again, mat.radius, rel_tol=1e-12)
        assert math.isclose(l_ins_again, mat.inductance, rel_tol=1e-12)
        assert not [
            why for _m, why in deck.ignored_detail if "not translated" in why
        ], deck.ignored_detail


def _dipole7(*cards) -> str:
    return (
        "GW 1 7 0 -3.5 10 0 3.5 10 0.001\nGE\nEX 0 1 4 0 1 0\n"
        + "".join(c + "\n" for c in cards)
        + "EN\n"
    )


def test_ld3_stays_reported_as_not_translated():
    """Requirement 5: LD 3 (parallel distributed loading) is out of scope --
    this fix widens LD 2 reading only, and must not silently widen LD 3 too."""
    deck = parse_nec(_dipole7("LD 3 0 0 0 1.0 1e-7 1e-12"), network=True)
    assert deck.wire_insulation == () and deck.wire_conductor_radius == ()
    assert any(m == "LD" and "type 3" in why for m, why in deck.ignored_detail)


def test_ld2_with_nonzero_c_prime_is_reported_not_misread_as_a_jacket():
    """Requirement 6's discriminator: a nonzero C' is genuine distributed
    capacitance the a'+L' pair never writes, so it stays reported rather
    than silently becoming a jacket."""
    deck = parse_nec(_dipole7("LD 2 0 0 0 0. 1e-7 1e-12"), network=True)
    assert deck.wire_insulation == () and deck.wire_conductor_radius == ()
    assert any(m == "LD" and "type 2" in why for m, why in deck.ignored_detail)


def test_ld2_without_positive_inductance_is_reported_not_misread():
    """A jacket only ever ADDS inductance (L' = (mu0/2pi)*k*ln(b/a) with
    k, ln(b/a) > 0), so L' <= 0 is never this pair -- zero, and a negative
    value some other distributed load might carry."""
    for l_field in ("0.", "-1E-7"):
        deck = parse_nec(_dipole7(f"LD 2 0 0 0 0. {l_field} 0."), network=True)
        assert deck.wire_insulation == () and deck.wire_conductor_radius == ()
        assert any(m == "LD" and "type 2" in why for m, why in deck.ignored_detail)


def test_ld2_partial_wire_range_is_reported_not_misread():
    """Per-wire specs cover whole wires only (the LD 7/#447 precedent) --
    a positive-L', zero-C' LD 2 that only covers PART of a wire still
    cannot become a per-wire jacket spec."""
    deck = parse_nec(_dipole7("LD 2 1 2 2 1.0 1e-6 0"), network=True)
    assert deck.wire_insulation == () and deck.wire_conductor_radius == ()
    assert any(
        m == "LD" and "type 2" in why and "partial-wire" in why
        for m, why in deck.ignored_detail
    )


def test_jacket_from_equivalent_radius_rejects_a_malformed_gw_radius():
    """Direct unit coverage of the defensive branch nec_import.py cannot
    reach on its own (it only calls this with inductance > 0, which already
    guarantees radius < a_eq for any a_eq > 0) -- a_eq <= 0 is the one input
    that still needs the function's own guard."""
    assert jacket_from_equivalent_radius(0.0, 1e-8) is None
    assert jacket_from_equivalent_radius(-1e-4, 1e-8) is None
    assert jacket_from_equivalent_radius(9e-4, 0.0) is None
    assert jacket_from_equivalent_radius(9e-4, -1e-8) is None


def test_a_lossy_dielectric_r_prime_is_reported_while_the_jacket_is_applied():
    """EZNEC writes the jacket pair with a nonzero R' when the dielectric has
    a loss tangent -- capture 0219 carries 1.655357 ohm/m from Loss Tan 0.01,
    which is why `_capture_0219_shape` carries it by default.

    AK's jacket is lossless (momwire#131), so that number has nowhere to go.
    Dropping it is the right call; dropping it SILENTLY is not, because this
    module's contract is that what it cannot express is named in
    `ignored_detail`. The jacket must still be applied either way: R'
    disqualifies nothing, or capture 0219 itself would stop translating.
    """
    d = parse_nec(_capture_0219_shape(9.665910e-4, 1.318335e-7), network=True)
    assert d.wire_insulation, "the jacket was refused because of R'"
    assert d.wire_conductor_radius, "the conductor radius was not recovered"
    why = " ".join(r for m, r in d.ignored_detail if m == "LD")
    assert "R'" in why and "dropped" in why, d.ignored_detail


def test_a_lossless_dielectric_reports_nothing():
    """The complement, so the report above cannot become unconditional noise:
    with R' = 0 the card is fully expressed and nothing is named."""
    deck = _capture_0219_shape(9.665910e-4, 1.318335e-7).replace(
        "LD 2,1,0,0,1.655357,", "LD 2,1,0,0,0.,"
    )
    d = parse_nec(deck, network=True)
    assert d.wire_insulation
    assert not [r for m, r in d.ignored_detail if m == "LD"], d.ignored_detail

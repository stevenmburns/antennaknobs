"""IS insulated-sheath cards (NEC-4 dialect, issue #873).

The card as SimNEC's NECSource writes it — ``IS 0 tag first last  eps_r
sigma b`` — translates to the same per-wire ``WireSpec`` jacket as
4nec2's LD 7 (issue #447): whole-wire ranges only, lossless dielectric
only (momwire's King quasi-static L' model), skip-with-detail for the
unexpressible remainder. The portal turns those skips into named
refusals; here the import-level contract is pinned.
"""

from antennaknobs.nec_import import parse_nec

DECK = (
    "GW 1 21 0 -19 10 0 0 10 0.0005\n"
    "GW 2 21 0 0 10 0 19 10 0.0005\n"
    "GE\n"
    "EX 0 1 21 0 1 0\n"
    "IS 0 {tag} {sf} {st} {eps} {sigma} {b}\n"
    "FR 0 1 0 0 3.68\nEN\n"
)


def _deck(tag=1, sf=0, st=0, eps=4.5, sigma=0.0, b=1e-3):
    return parse_nec(
        DECK.format(tag=tag, sf=sf, st=st, eps=eps, sigma=sigma, b=b),
        name="t",
        network=True,
    )


def _is_detail(deck):
    return [reason for mnemonic, reason in deck.ignored_detail if mnemonic == "IS"]


def test_is_whole_wire_maps_to_wirespec_jacket():
    deck = _deck(tag=1, sf=0, st=0)
    assert deck.wire_insulation == ((0, (1e-3, 4.5)),)
    assert not _is_detail(deck)
    spec = deck.wire_tuples(specs=True)[0].spec
    assert spec.insulation_radius == 1e-3 and spec.insulation_eps_r == 4.5


def test_is_explicit_full_range_is_the_same_spelling():
    deck = _deck(tag=1, sf=1, st=21)
    assert deck.wire_insulation == ((0, (1e-3, 4.5)),)


def test_is_matches_the_ld7_translation():
    ld7 = parse_nec(
        DECK.replace("IS 0 {tag} {sf} {st} {eps} {sigma} {b}", "LD 7 1 0 0 4.5 1e-3"),
        name="t",
        network=True,
    )
    assert _deck(tag=1).wire_insulation == ld7.wire_insulation


def test_is_partial_range_skips_with_detail():
    deck = _deck(tag=1, sf=3, st=9)
    assert deck.wire_insulation == ()
    assert any("partial-wire" in r for r in _is_detail(deck))


def test_is_conductive_sheath_skips_with_detail():
    deck = _deck(sigma=0.01)
    assert deck.wire_insulation == ()
    assert any("conductive sheath" in r for r in _is_detail(deck))


def test_is_jacket_inside_conductor_skips_with_detail():
    deck = _deck(b=0.0002)  # conductor radius is 0.0005
    assert deck.wire_insulation == ()
    assert any("conductor radius" in r for r in _is_detail(deck))


def test_is_vacuum_jacket_is_a_noop():
    deck = _deck(eps=1.0)
    assert deck.wire_insulation == ()
    assert not _is_detail(deck)


def test_ld_minus_one_does_not_clear_is():
    text = DECK.replace("FR 0 1 0 0 3.68\n", "LD -1\nFR 0 1 0 0 3.68\n").format(
        tag=1, sf=0, st=0, eps=4.5, sigma=0.0, b=1e-3
    )
    deck = parse_nec(text, name="t", network=True)
    assert deck.wire_insulation == ((0, (1e-3, 4.5)),)

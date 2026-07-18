"""LD 7 insulated-wire loads (4nec2 dialect, issue #447).

4nec2's type 7 is wire insulation: F1 the jacket's relative
permittivity, F2 its outer radius in metres. The contract here: the
importer translates whole-wire LD 7 ranges into per-wire WireSpec
insulation (the lossy-wire arc's dielectric-jacket model), so an LD 7
deck and hand-built insulated specs are indistinguishable through an
engine solve — and the bench reference rewrites LD 7 to the LD 2
distributed-L' emulation PR #326 validated against that model.
"""

import pytest

from antennaknobs import AntennaBuilder, WireSpec
from antennaknobs.engines import MomwireEngine
from antennaknobs.nec_import import parse_nec
from momwire import SinusoidalSolver, insulation_inductance

FREQ = 3.68
EPS_R = 4.5
B_M = 1e-3  # jacket outer radius; conductor is 0.5 mm

COATED_DECK = (
    "GW 1 21 0 -19 10 0 0 10 0.0005\n"
    "GW 2 21 0 0 10 0 19 10 0.0005\n"
    "GE\n"
    "EX 0 1 21 0 1 0\n"
    "LD 7 {tag} {sf} {st} {eps} {b}\n"
    "FR 0 1 0 0 3.68\nEN\n"
)


def _deck(tag=0, sf=0, st=0, eps=EPS_R, b=B_M):
    return parse_nec(
        COATED_DECK.format(tag=tag, sf=sf, st=st, eps=eps, b=b),
        name="t",
        network=True,
    )


def _builder(deck):
    class B(AntennaBuilder):
        default_params = {"freq": FREQ}

        def build_wires(self):
            return deck.wire_tuples(specs=True)

        def build_network(self):
            return deck.network()

    return B()


def _z(deck):
    eng = MomwireEngine(_builder(deck), solver=SinusoidalSolver, ground=None)
    return eng.impedance()[0]


def test_ld7_whole_structure_covers_every_wire():
    deck = _deck(tag=0)
    assert deck.wire_insulation == ((0, (B_M, EPS_R)), (1, (B_M, EPS_R)))
    for w in deck.wire_tuples(specs=True):
        assert w.spec.insulation_radius == pytest.approx(B_M)
        assert w.spec.insulation_eps_r == pytest.approx(EPS_R)
    assert not deck.ignored_detail  # fully expressed — no n-flag residue


def test_ld7_whole_wire_range_covers_that_wire_only():
    deck = _deck(tag=2, sf=1, st=21)
    assert deck.wire_insulation == ((1, (B_M, EPS_R)),)
    specs = [w.spec for w in deck.wire_tuples(specs=True)]
    bare = [s for s in specs if s.insulation_radius is None]
    coated = [s for s in specs if s.insulation_radius is not None]
    assert bare and coated
    assert not deck.ignored_detail


def test_ld7_partial_wire_range_is_skipped_labeled():
    deck = _deck(tag=1, sf=3, st=9)
    assert deck.wire_insulation == ()
    assert any("partial-wire" in reason for _c, reason in deck.ignored_detail)


def test_ld7_jacket_inside_conductor_is_skipped_labeled():
    deck = _deck(b=0.0004)  # jacket radius below the 0.5 mm conductor
    assert deck.wire_insulation == ()
    assert any("conductor radius" in reason for _c, reason in deck.ignored_detail)


def test_ld7_vacuum_or_absent_jacket_is_a_silent_noop():
    for kwargs in ({"eps": 1.0}, {"b": 0}):
        deck = _deck(**kwargs)
        assert deck.wire_insulation == ()
        assert not deck.ignored_detail


def test_ld7_solves_identically_to_hand_built_spec():
    """Engine oracle: the LD 7 deck and the same geometry with hand-built
    insulated WireSpecs must produce the same driving-point impedance."""
    z_ld7 = _z(_deck(tag=0))

    bare = parse_nec(
        COATED_DECK.format(tag=0, sf=0, st=0, eps=1, b=0), name="b", network=True
    )
    spec = WireSpec(radius=0.0005, insulation_radius=B_M, insulation_eps_r=EPS_R)
    hand = [w._replace(spec=spec) for w in bare.wire_tuples(specs=True)]

    class B(AntennaBuilder):
        default_params = {"freq": FREQ}

        def build_wires(self):
            return hand

        def build_network(self):
            return bare.network()

    z_hand = MomwireEngine(B(), solver=SinusoidalSolver, ground=None).impedance()[0]
    assert z_ld7 == pytest.approx(z_hand, rel=1e-12)


def test_insulation_actually_bites():
    """Physics sanity: a PVC jacket makes the wire electrically longer, so
    the coated antenna's reactance must differ visibly from the bare one's."""
    z_coated = _z(_deck(tag=0))
    z_bare = _z(_deck(eps=1, b=0))
    assert abs(z_coated.imag - z_bare.imag) > 5.0


def test_reference_deck_emits_ld2_emulation():
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    from bench_nec_corpus import reference_deck

    prepared = reference_deck(
        COATED_DECK.format(tag=0, sf=0, st=0, eps=EPS_R, b=B_M), "t"
    )
    assert "LD 7" not in prepared
    ld_lines = [ln for ln in prepared.splitlines() if ln.startswith("LD")]
    assert len(ld_lines) == 2  # whole-structure card expands per tag
    l_exp = insulation_inductance(0.0005, B_M, EPS_R)
    for tag, ld in zip((1, 2), ld_lines):
        toks = ld.split()
        assert toks[1] == "2" and toks[2] == str(tag)
        assert float(toks[5]) == 0.0
        assert float(toks[6]) == pytest.approx(l_exp)


def test_reference_deck_drops_non_clearing_jacket():
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    from bench_nec_corpus import reference_deck

    prepared = reference_deck(
        COATED_DECK.format(tag=0, sf=0, st=0, eps=EPS_R, b=0.0004), "t"
    )
    # Jacket inside the conductor: the importer leaves the wire bare, so
    # the reference must too — no LD 7 (nec2c aborts) and no LD 2.
    assert "LD 7" not in prepared and "LD 2" not in prepared

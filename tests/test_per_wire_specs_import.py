"""Phase-4 tests for issue #388: NEC decks import with true per-wire radii
(`wire_tuples(specs=True)`), ranged LD 5 translates to per-wire
conductivity, and the web length/weight readout sums per wire."""

from pathlib import Path
from types import MappingProxyType

import pytest

from antennaknobs import AntennaBuilder, Wire, WireSpec
from antennaknobs.nec_import import parse_nec

import antennaknobs.web.examples  # noqa: F401 — primes the adapter (import order)
from antennaknobs.web.adapter import _wire_material_results

TWO_RADIUS = (
    "GW 1 5 0 0 0  1 0 0  0.001\nGW 2 5 1 0 0  2 0 0  0.004\nGE\nEX 0 1 3 0 1 0\nEN\n"
)


def test_default_wire_tuples_stay_plain():
    tups = parse_nec(TWO_RADIUS).wire_tuples()
    assert all(type(t) is tuple and len(t) == 4 for t in tups)


def test_specs_true_carries_each_wires_own_radius():
    tups = parse_nec(TWO_RADIUS).wire_tuples(specs=True)
    assert all(isinstance(t, Wire) for t in tups)
    assert [t.spec.radius for t in tups] == [0.001, 0.004]
    # PEC deck: no LD 5 anywhere -> conductivity stays None
    assert all(t.spec.conductivity is None for t in tups)


def test_split_pieces_inherit_the_parent_wires_spec():
    # Feed off-middle forces a split of wire 1 into three pieces; all
    # three carry wire 1's spec, wire 2 keeps its own.
    deck = parse_nec(
        "GW 1 10 0 0 0  10 0 0  0.002\n"
        "GW 2 4 10 0 0  14 0 0  0.005\n"
        "GE\n"
        "EX 0 1 3 0 1 0\n"
        "EN\n"
    )
    tups = deck.wire_tuples(specs=True)
    radii = [t.spec.radius for t in tups]
    assert radii == [0.002, 0.002, 0.002, 0.005]
    assert [t.n_seg for t in tups] == [2, 1, 7, 4]


def test_ranged_ld5_becomes_per_wire_conductivity():
    deck = parse_nec(
        "GW 1 5 0 0 0  1 0 0  0.001\n"
        "GW 2 5 1 0 0  2 0 0  0.002\n"
        "GE\n"
        "LD 5 0 0 0 5.8e7\n"  # whole structure
        "LD 5 2 0 0 3.5e7\n"  # all of tag 2 — expressible per wire
        "EX 0 1 3 0 1 0\n"
        "EN\n",
        network=True,
    )
    assert deck.conductivity == pytest.approx(5.8e7)
    assert deck.wire_conductivity == ((1, pytest.approx(3.5e7)),)
    # No LD entry may remain unexplained: the ranged card translated.
    assert not any(m == "LD" for m, _ in deck.ignored_detail)
    sigmas = [t.spec.conductivity for t in deck.wire_tuples(specs=True)]
    assert sigmas == [pytest.approx(5.8e7), pytest.approx(3.5e7)]


def test_partial_wire_ld5_still_skipped_with_reason():
    deck = parse_nec(
        "GW 1 5 0 0 0  1 0 0  0.001\n"
        "GE\n"
        "LD 5 1 2 3 1e7\n"  # segments 2-3 of 5 only
        "EX 0 1 3 0 1 0\n"
        "EN\n",
        network=True,
    )
    assert deck.wire_conductivity == ()
    assert any(
        m == "LD" and "partial-wire" in reason for m, reason in deck.ignored_detail
    )


def test_whip_benchmark_imports_with_true_radii():
    """The motivating deck: 0.010\" grid + 0.035\" whip (GS-scaled to
    metres). specs=True must carry both radii — no dominant_radius()."""
    text = (
        Path(__file__).parent / "data" / "whip_antenna_8ft_groundplane.nec"
    ).read_text()
    deck = parse_nec(text, name="whip", network=True)
    tups = deck.wire_tuples(specs=True)
    radii = {round(t.spec.radius, 9) for t in tups}
    assert radii == {round(0.010 * 0.0254, 9), round(0.035 * 0.0254, 9)}
    thick_len = sum(1 for t in tups if t.spec.radius == pytest.approx(0.035 * 0.0254))
    assert thick_len >= 1  # the whip's upper section survives the splits


def test_wire_material_readout_sums_per_wire():
    heavy = WireSpec(radius=1e-3, weight_g_per_m=5.0)
    light = WireSpec(radius=1e-3, weight_g_per_m=1.0)

    class _B(AntennaBuilder):
        default_params = MappingProxyType({"freq": 14.1})

        def build_wires(self):
            return [
                Wire((0, 0, 0.0), (0, 0, 1.0), 3, 1 + 0j, None, heavy),  # 1 m
                ((0, 0, 1.0), (0, 0, 3.0), 3, None),  # 2 m, falls to default
            ]

        def build_wire_material(self):
            return light

    out = _wire_material_results(_B())
    assert out["wire_length_m"] == pytest.approx(3.0)
    assert out["wire_weight_g"] == pytest.approx(1 * 5.0 + 2 * 1.0)

    class _NoDefault(_B):
        def build_wire_material(self):
            return None

    out2 = _wire_material_results(_NoDefault())
    # per-wire specs alone are enough to surface the readout; spec-less
    # wires count toward length but contribute no weight
    assert out2["wire_length_m"] == pytest.approx(3.0)
    assert out2["wire_weight_g"] == pytest.approx(5.0)

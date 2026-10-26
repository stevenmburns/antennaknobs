"""Multiband EFHW on a tapped autotransformer (issue #2062): a 40 m half
wave whose harmonics a capacitor in the wire pulls onto 20, 15 and 10 m,
matched by one tapped winding (coupled inductors), with the coax shield as
antenna wire and a common-mode choke.

Every figure below is over average ground in Sommerfeld (εr 13, σ 0.005),
the workbench's default ground.
"""

import math

import pytest

from antennaknobs.designs.wire.efhw_autotransformer import (
    BANDS,
    TAPS,
    Builder,
    section_uH,
)
from antennaknobs.engines import MomwireEngine
from antennaknobs.network import Autotransformer, Network, Transformer
from antennaknobs.station import autotransformer_ratio

GROUND = dict(ground=("finite", 13.0, 0.005), ground_z=0.0)

# Three points across each band the stock tune is for; 10 m's lowest
# 600 kHz, where its SSB and CW live.
BAND_POINTS = {
    "40 m": (7.0, 7.15, 7.3),
    "20 m": (14.0, 14.175, 14.35),
    "15 m": (21.0, 21.225, 21.45),
    "10 m": (28.0, 28.3, 28.6),
}


def _with_params(**overrides):
    return Builder(params={**Builder.default_params, **overrides})


def _z(builder):
    (z,) = MomwireEngine(builder, **GROUND).impedance()
    return complex(z)


def _swr(z, z0=50.0):
    g = abs((z - z0) / (z + z0))
    return (1 + g) / (1 - g)


def _budget(eng):
    eng.current_distribution()
    p_in = eng._excited_p_in
    return {label: w / p_in for label, w in eng._excited_power_budget}


class _IdealBox(Builder):
    """The same wires with the winding replaced by an ideal n:1 transformer."""

    def build_network(self):
        net = super().build_network()
        n = autotransformer_ratio(*section_uH(self.taps, self.al_nH))
        # Network flattens the "box" instance into its Autotransformer branch.
        branches = [b for b in net.branches if not isinstance(b, Autotransformer)]
        branches.append(Transformer(a="pri", b="ant", n=1.0 / n))
        return Network(ports=net.ports, branches=branches, sources=net.sources)


def test_discoverable():
    from antennaknobs.cli import list_builtin_designs

    assert "wire.efhw_autotransformer" in set(list_builtin_designs())


def test_taps_are_the_named_ratios():
    """FT240-43 (A_L 1075 nH/N²): 2:14 is 4.3 / 155 µH, and every tap
    choice's ideal ratio is its turns ratio."""
    lower, upper = section_uH("2:14", 1075.0)
    assert lower == pytest.approx(4.3)
    assert upper == pytest.approx(154.8)
    for taps, (pri, total) in TAPS.items():
        assert autotransformer_ratio(*section_uH(taps, 1075.0)) == pytest.approx(
            total / pri
        )


@pytest.mark.parametrize("band", list(BAND_POINTS))
def test_stock_tune_matches_each_band(band):
    """The stock tune holds every band under 2:1."""
    for f in BAND_POINTS[band]:
        assert _swr(_z(_with_params(freq=f))) < 2.0, (band, f)


def test_the_load_cap_is_what_aligns_the_harmonics():
    """Without the cap in the wire, the harmonics fall off the bands."""
    worst = max(
        _swr(_z(_with_params(freq=f, load_c_pF=0.0)))
        for pts in BAND_POINTS.values()
        for f in pts
    )
    assert worst > 2.5


@pytest.mark.parametrize("taps", ["2:14", "2:16"])
def test_ideal_limit_is_an_ideal_transformer_on_the_same_wire(taps):
    """k → 1 with huge inductances and no loss: the tap sees Z_ant / n², the
    ideal transformer of the same ratio on the same wires."""
    shared = dict(taps=taps, k=1.0, al_nH=1e7, ql=0.0, freq=14.175)
    auto = _with_params(**shared)
    ideal = _IdealBox(params={**Builder.default_params, **shared})
    assert _z(auto) == pytest.approx(_z(ideal), rel=1e-4)


def test_leakage_is_load_bearing_on_10m():
    """At a realistic coupling the winding's leakage moves the 10 m match."""
    z98 = _z(_with_params(freq=28.3))
    z1 = _z(_with_params(freq=28.3, k=1.0))
    assert abs(z98 - z1) > 5.0


def test_power_budget_balances_and_names_every_row():
    """Radiated plus every loss row is the input power; the winding's two
    sections and the choke burn real power, the ideal capacitors none."""
    eng = MomwireEngine(_with_params(freq=14.175), **GROUND)
    fr = _budget(eng)
    assert eng._excited_efficiency + sum(fr.values()) == pytest.approx(1.0, abs=1e-6)
    winding = (
        fr["box: Autotransformer pri→ant (lower)"]
        + fr["box: Autotransformer pri→ant (upper)"]
    )
    assert winding > 0.005
    assert abs(fr["Shunt pri"]) < 1e-9
    assert abs(fr["Load load"]) < 1e-9
    assert fr["Load choke"] > 0.0
    labels = Builder.default_params["ui_params"]["budget_labels"]
    assert set(fr) - {"wire loss (I²R)"} <= set(labels)


def test_the_counterpoise_is_the_return_not_the_coax():
    """With the 4 m counterpoise the shield carries little: no choke and an
    ideal one stay near the stock match. Shrink the counterpoise with the coax
    choked off and the end-fed has no return: the match falls apart (stock
    1.60, no choke 1.60, ideal choke 1.80, 0.5 m counterpoise and ideal choke
    4.05, worst of the band points)."""

    def worst(**o):
        return max(
            _swr(_z(_with_params(freq=f, **o)))
            for pts in BAND_POINTS.values()
            for f in pts
        )

    stock = worst()
    assert abs(worst(choke="none") - stock) < 0.1
    assert worst(choke="ideal") < 2.0
    assert worst(choke="ideal", cp_len_m=0.5) > 3.0


def test_the_tap_plane_includes_the_comp_cap():
    """At the tap the comp cap is in parallel with the box, so its
    admittance adds exactly; the rig plane adds the coax on top."""
    f = 28.3
    bare = _z(_with_params(freq=f, measure_at="tap", comp_c_pF=0.0))
    with_cap = _z(_with_params(freq=f, measure_at="tap"))
    y_cap = 2j * math.pi * f * 1e6 * Builder.default_params["comp_c_pF"] * 1e-12
    assert with_cap == pytest.approx(1 / (1 / bare + y_cap), rel=1e-9)
    assert abs(_z(_with_params(freq=f)) - with_cap) > 1.0


def test_the_ant_plane_is_the_bare_wire():
    """Across the feed gap, the box and its comp cap are not in the circuit:
    the high impedance the box has to match."""
    f = 14.175
    z = _z(_with_params(freq=f, measure_at="ant"))
    assert z == _z(_with_params(freq=f, measure_at="ant", taps="2:16", comp_c_pF=0.0))
    assert abs(z) > 1000.0


def test_geometry_is_validated():
    with pytest.raises(ValueError, match="measure_at"):
        _with_params(measure_at="feed").build_network()
    with pytest.raises(ValueError, match="choke_at_m"):
        _with_params(choke_at_m=9.5).build_wires()
    with pytest.raises(ValueError, match="does not reach the ground"):
        _with_params(line_len_m=5.0).build_wires()
    with pytest.raises(ValueError, match="counterpoise"):
        _with_params(cp_len_m=10.0, cp_slope_deg=85.0).build_wires()


def test_analyses_sweep_3_to_30_and_each_band_within_the_hosted_cap():
    from antennaknobs import analyses as an
    from antennaknobs.web.cost import MAX_SWEEP_POINTS

    specs = {a.name: a for a in Builder().build_analyses()}
    assert list(specs) == ["SWR 3-30 MHz"] + [f"SWR {b[0]}" for b in BANDS]
    wide = specs["SWR 3-30 MHz"].sweep
    assert (wide.knob, wide.lo, wide.hi) == (an.FREQUENCY, 3.0, 30.0)
    for a in specs.values():
        assert a.sweep.points <= MAX_SWEEP_POINTS
        assert not an.problems(a, Builder())

"""EFHW sloper on a tapped autotransformer (issue #2062): the sibling of
``wire.efhw_sloper`` whose box is one tapped winding (coupled inductors)
and whose coax shield is antenna wire with a common-mode choke.

Stock tune targets average ground in Sommerfeld (εr 13, σ 0.005), the
workbench's default ground; every figure below names it.
"""

import pytest

from antennaknobs.designs.wire import efhw_sloper
from antennaknobs.designs.wire.efhw_autotransformer import TAPS, Builder, section_uH
from antennaknobs.engines import MomwireEngine
from antennaknobs.station import autotransformer_ratio

GROUND = dict(ground=("finite", 13.0, 0.005), ground_z=0.0)


def _with_params(**overrides):
    return Builder(params={**Builder.default_params, **overrides})


def _swr(z, z0=50.0):
    g = abs((z - z0) / (z + z0))
    return (1 + g) / (1 - g)


def _budget(eng):
    eng.current_distribution()
    p_in = eng._excited_p_in
    return {label: w / p_in for label, w in eng._excited_power_budget}


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


def test_stock_tune_matches_fifty_ohms():
    """measured 1.238 at 14.1 MHz with the stock 150 pF comp cap and the
    choke 1 m down the shield."""
    (z,) = MomwireEngine(Builder(), **GROUND).impedance()
    assert _swr(complex(z)) < 1.3


@pytest.mark.parametrize("taps,ratio", [("2:14", "49:1"), ("2:16", "64:1")])
def test_ideal_limit_is_the_sloper_unun(taps, ratio):
    """k → 1 with huge inductances, no loss, no comp cap, no line and no
    shield: the tap sees Z_ant / n², the sloper's ideal unun on the same
    wire."""
    shared = dict(comp_c_pF=0.0, line_len_m=1e-9, length_factor=0.8815)
    auto = _with_params(taps=taps, k=1.0, al_nH=1e7, ql=0.0, choke="ideal", **shared)
    ideal = efhw_sloper.Builder(
        params={
            **efhw_sloper.Builder.default_params,
            "unun_ratio": ratio,
            "lmag_uH": 1e9,
            "qlmag": 0.0,
            **shared,
        }
    )
    (za,) = MomwireEngine(auto, **GROUND).impedance()
    (zi,) = MomwireEngine(ideal, **GROUND).impedance()
    assert complex(za) == pytest.approx(complex(zi), rel=1e-4)


def test_leakage_is_load_bearing():
    """At a realistic coupling the winding's leakage moves the match a long
    way from the ideal ratio — the reason this is a sibling, not an option."""
    (z98,) = MomwireEngine(Builder(), **GROUND).impedance()
    (z1,) = MomwireEngine(_with_params(k=1.0), **GROUND).impedance()
    assert abs(complex(z98) - complex(z1)) > 5.0


def test_power_budget_balances_and_names_the_winding():
    """Radiated plus every loss row is the input power; the winding's two
    sections and the choke burn real power, the ideal comp cap none."""
    eng = MomwireEngine(Builder(), **GROUND)
    fr = _budget(eng)
    assert eng._excited_efficiency + sum(fr.values()) == pytest.approx(1.0, abs=1e-6)
    winding = (
        fr["box: Autotransformer pri→ant (lower)"]
        + fr["box: Autotransformer pri→ant (upper)"]
    )
    assert 0.02 < winding < 0.08  # measured 0.049
    assert abs(fr["Shunt pri"]) < 1e-9
    assert 0.01 < fr["Load choke"] < 0.10  # measured 0.068
    assert 0.70 < eng._excited_efficiency < 0.90  # measured 0.772
    labels = Builder.default_params["ui_params"]["budget_labels"]
    assert set(fr) - {"wire loss (I²R)"} <= set(labels)


def test_choke_placement_and_the_bare_shield():
    """A bare shield is a second counterpoise and spoils the match; a choke
    at the feed point burns more than one partway down the shield."""
    (z_bare,) = MomwireEngine(_with_params(choke="none"), **GROUND).impedance()
    assert _swr(complex(z_bare)) > 1.5
    at_feed = _budget(MomwireEngine(_with_params(choke_at_m=0.0), **GROUND))
    down = _budget(MomwireEngine(Builder(), **GROUND))
    assert at_feed["Load choke"] > 2 * down["Load choke"]


def test_choke_must_sit_on_the_drop():
    with pytest.raises(ValueError, match="choke_at_m"):
        _with_params(choke_at_m=3.0).build_wires()
    with pytest.raises(ValueError, match="does not reach the ground"):
        _with_params(line_len_m=1.0).build_wires()

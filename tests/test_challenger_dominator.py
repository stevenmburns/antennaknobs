"""KJ6ER's Challenger (OCF halfwave + 4:1) and Dominator (EFHW vertical +
49:1): duplicate the published claims, and pin the transformer insertion
losses in the power budget (plans rev 2025-02, 4NEC2 at 21.350 MHz).

Published reference points (15M, "Computer Model" lengths):
  Challenger: peak −0.32 dBi @ 20°, el BW 33°, unun loss −0.34 dB (LDG)
              / −0.24 dB (Palomar, "plus"); structural 94.3%
  Dominator:  peak +0.60 dBi @ 18°, el BW 27°, xfmr loss −0.96 dB
              (TennTennas 49:1) / −0.40 dB (MyAntennas 56:1, "plus");
              structural 99.5%
  Takeoff ordering (the trio's marquee claim): Dominator 18° <
              Challenger 21° < PERformer 24°.
We measure: Challenger +0.14 dBi @ 21° BW 34°, Dominator +0.34 dBi @ 17°
BW 26°, ordering 17° < 21° < 23°.
"""

import numpy as np
import pytest

from antennaknobs import radiated_fraction, resolve_variant_params
from antennaknobs.designs.verticals.challenger import Builder as Challenger
from antennaknobs.designs.verticals.dominator import Builder as Dominator, XFMR_TURNS
from antennaknobs.engines import MomwireEngine
from antennaknobs.far_field import pattern_metrics

# Pattern/efficiency claims solve over full Sommerfeld average ground;
# the transformer-loss calibration used the workbench finite-fast ground.
SOMMERFELD = dict(ground=("finite", 13.0, 0.005), ground_z=0.0)
WORKBENCH = dict(ground=("finite-fast", 10.0, 0.002), ground_z=0.0)


def _build(Builder, variant=None, **overrides):
    params = (
        resolve_variant_params(Builder, variant)
        if variant
        else dict(Builder.default_params)
    )
    params.update(overrides)
    return Builder(params=params)


def _pattern(builder):
    eng = MomwireEngine(builder, **SOMMERFELD)
    ff = eng.far_field(n_theta=90, n_phi=360, del_theta=1, del_phi=1)
    return ff, pattern_metrics(ff)


def _mag_loss_db(builder):
    eng = MomwireEngine(builder, **WORKBENCH)
    eng.current_distribution()
    budget = dict(eng._excited_power_budget)
    frac = max(0.0, budget["unun: Transformer rig→ant (mag)"]) / eng._excited_p_in
    return -10.0 * np.log10(1.0 - frac)


def test_discoverable():
    from antennaknobs.cli import list_builtin_designs

    designs = set(list_builtin_designs())
    assert "verticals.challenger" in designs
    assert "verticals.dominator" in designs


def test_challenger_pattern_claims():
    _, m = _pattern(_build(Challenger))
    assert 18 <= m["takeoff_deg"] <= 24  # claim 20°
    assert 28 <= m["el_beamwidth_deg"] <= 40  # claim 33°
    assert -0.7 < m["peak_gain_dbi"] < 0.8  # claim −0.32, measured +0.14
    assert m["front_to_back_db"] < 1.0  # omnidirectional


def test_dominator_pattern_claims():
    _, m = _pattern(_build(Dominator))
    assert 14 <= m["takeoff_deg"] <= 21  # claim 18°
    assert 21 <= m["el_beamwidth_deg"] <= 32  # claim 27°
    assert -0.4 < m["peak_gain_dbi"] < 1.2  # claim +0.60, measured +0.34


def test_takeoff_ordering_across_the_trio():
    """The p.14 'primary reach' table's marquee physics: the EFHW halfwave
    sits lowest, the OCF halfwave next, the quarterwave highest."""
    from antennaknobs.designs.verticals.pota_performer import Builder as Performer

    _, m_dom = _pattern(_build(Dominator))
    _, m_cha = _pattern(_build(Challenger))
    _, m_per = _pattern(_build(Performer, "omni"))
    assert m_dom["takeoff_deg"] < m_cha["takeoff_deg"] <= m_per["takeoff_deg"]


def test_transformer_losses_land_the_measured_values():
    """lmag/qlmag are calibrated so the budget's (mag) row reproduces the
    measured insertion losses at the 15M reference frequency."""
    assert _mag_loss_db(_build(Challenger)) == pytest.approx(0.34, abs=0.08)
    assert _mag_loss_db(_build(Challenger, "plus")) == pytest.approx(0.24, abs=0.06)
    assert _mag_loss_db(_build(Dominator)) == pytest.approx(0.96, abs=0.15)
    assert _mag_loss_db(_build(Dominator, "plus")) == pytest.approx(0.40, abs=0.10)


def test_idealized_transformer_ratio_sanity():
    """With the magnetizing branch idealized, switching the Dominator's
    49:1 to 56:1 rescales the rig impedance by the turns² quotient."""

    def rig_z(ratio):
        b = _build(Dominator, xfmr_ratio=ratio, lmag_uH=1e6, qlmag=0.0)
        return complex(MomwireEngine(b, **WORKBENCH).impedance()[0])

    q = rig_z("49:1") / rig_z("56:1")
    expected = XFMR_TURNS["56:1"] ** 2 / XFMR_TURNS["49:1"] ** 2
    assert complex(q) == pytest.approx(expected, rel=1e-5)


def test_radiated_fraction_same_ground_tax():
    """Neither halfwave escapes the dirt: ~25% of input power radiates
    (including their transformer's share), same regime as the PERformer.
    The trio's real differentiator is takeoff angle, not efficiency."""
    ff_c, _ = _pattern(_build(Challenger))
    ff_d, _ = _pattern(_build(Dominator))
    assert 0.17 < radiated_fraction(ff_c) < 0.35  # measured 0.247
    assert 0.17 < radiated_fraction(ff_d) < 0.35  # measured 0.246


def test_band_variants_build():
    for Builder, bands in (
        (Challenger, ("band20", "band17", "band12", "band10", "band6")),
        (Dominator, ("band17", "band12", "band10")),
    ):
        for name in bands:
            b = _build(Builder, name)
            wires = b.build_wires()
            top = max(max(p0[2], p1[2]) for p0, p1, *_ in wires)
            bottom = min(min(p0[2], p1[2]) for p0, p1, *_ in wires)
            assert top == pytest.approx(b.h_feed + b.whip_len_m)
            # A counterpoise too short to reach the target end height
            # (6M's 26") hangs straight down instead — the droop clamp.
            expected_bottom = max(b.cp_end_h, b.h_feed - b.cp_len_m)
            assert bottom == pytest.approx(expected_bottom, abs=0.02)

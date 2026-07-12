"""KJ6ER's POTA PERformer: duplicate the published claims (PDF rev
2025-02, 4NEC2 at 21.350 MHz) and pin the three-ledger efficiency story.

Cross-model reference points (15M, two radials, average ground):
  KJ6ER 4NEC2:  directional peak +0.31 dBi @ 24°, F/B 3.37, el BW 46°;
                omni peak −0.67 dBi @ 24°; "structural efficiency" 90.8%
  VA3KOT EZNEC: two radials +1.19 dBi @ 25°, F/B 3.34, el BW 47°;
                single radial +1.34 dBi, F/B 4.6
  momwire:      +1.06 dBi @ 24°, F/B 2.91, radiated/input 29%
  PyNEC:        +1.02 dBi @ 23°, radiated/input 34%
"""

import pytest

from antennaknobs import radiated_fraction, resolve_variant_params
from antennaknobs.designs.verticals.pota_performer import Builder
from antennaknobs.engines import MomwireEngine
from antennaknobs.far_field import pattern_metrics

# Full Sommerfeld average ground: the claim tables are gain/efficiency
# claims about real earth, not workbench-tune numbers.
GROUND = dict(ground=("finite", 13.0, 0.005), ground_z=0.0)


def _variant(name=None, **overrides):
    params = (
        resolve_variant_params(Builder, name) if name else dict(Builder.default_params)
    )
    params.update(overrides)
    return Builder(params=params)


def _solve(builder):
    eng = MomwireEngine(builder, **GROUND)
    ff = eng.far_field(n_theta=90, n_phi=360, del_theta=1, del_phi=1)
    return eng, ff, pattern_metrics(ff)


def test_discoverable():
    from antennaknobs.cli import list_builtin_designs

    assert "verticals.pota_performer" in set(list_builtin_designs())


def test_directional_claims_duplicate():
    """The 90°-span pattern shape matches all three published models:
    takeoff ~24°, F/B ~3 dB, lobe on +x, peak gain in the VA3KOT/momwire/
    PyNEC cluster (+1.0–1.3 dBi) — about 0.8 dB above KJ6ER's own plot."""
    _, ff, m = _solve(_variant())
    assert 20 <= m["takeoff_deg"] <= 28  # claims say 23–25
    assert m["azimuth_deg"] == pytest.approx(0.0, abs=15)
    assert 2.0 < m["front_to_back_db"] < 4.5  # 2.91 here; 3.34–3.37 published
    assert 0.5 < m["peak_gain_dbi"] < 1.7  # measured 1.06


def test_omni_span_loses_the_directionality():
    """180° span: the directionality claim inverts — F/B collapses and
    the peak drops by roughly KJ6ER's published ~1 dB delta."""
    _, _, m_dir = _solve(_variant())
    _, _, m_omni = _solve(_variant("omni"))
    assert m_omni["front_to_back_db"] < 0.5
    delta = m_dir["peak_gain_dbi"] - m_omni["peak_gain_dbi"]
    assert 0.4 < delta < 1.6  # KJ6ER +0.98 dB, we measure ~0.76


def test_single_radial_matches_va3kot_trend():
    """VA3KOT's EZNEC single-radial config: more front-to-back than the
    orthogonal pair (4.6 vs 3.34 — we measure 4.01 vs 2.91), wider
    elevation beamwidth, narrower azimuth coverage. Peak gain is the one
    metric where the models split on ORDER (his +0.15 dB, ours −0.27 dB)
    — sub-half-dB and sensitive to exact radial geometry, so we pin the
    two gains to within a dB of each other rather than an ordering."""
    _, _, m2 = _solve(_variant())
    _, _, m1 = _solve(_variant("single_radial"))
    assert m1["front_to_back_db"] > m2["front_to_back_db"]
    assert m1["el_beamwidth_deg"] > m2["el_beamwidth_deg"]
    assert m1["az_beamwidth_deg"] < m2["az_beamwidth_deg"]
    assert abs(m1["peak_gain_dbi"] - m2["peak_gain_dbi"]) < 1.0


def test_the_efficiency_ledgers():
    """The headline: ~90% structural efficiency and ~30% radiated are
    simultaneously true. Conductor loss (stainless everywhere) is a few
    percent — the rest of the missing power is ground absorption, which
    never appears in a structural-efficiency figure."""
    eng, ff, m = _solve(_variant())
    frac = radiated_fraction(ff)
    assert 0.22 < frac < 0.40  # measured 0.29 (PyNEC 0.34, KJ6ER's own ~0.24)

    # Same solve with lossless wire: the conductor's share is tiny, so
    # structural efficiency (lossy/lossless radiated ratio) is >90% —
    # KJ6ER's claim, confirmed in his own ledger.
    class PECBuilder(Builder):
        def build_wire_material(self):
            from antennaknobs.network import WireSpec

            return WireSpec(radius=0.005, conductivity=None)

    _, ff_pec, _ = _solve(PECBuilder(params=dict(Builder.default_params)))
    structural = frac / radiated_fraction(ff_pec)
    assert 0.90 < structural <= 1.0  # measured ~0.98


def test_radiated_fraction_normalization():
    """Over PEC ground with lossless wire the integral must return ~all
    the power (grid clipping at the horizon costs a few percent — the
    vertical's PEC-ground pattern peaks exactly there)."""

    class PECBuilder(Builder):
        def build_wire_material(self):
            from antennaknobs.network import WireSpec

            return WireSpec(radius=0.005, conductivity=None)

    eng = MomwireEngine(
        PECBuilder(params=dict(Builder.default_params)), ground="pec", ground_z=0.0
    )
    ff = eng.far_field(n_theta=90, n_phi=360, del_theta=1, del_phi=1)
    assert 0.90 < radiated_fraction(ff) < 1.05  # measured 0.962


def test_band_variants_build():
    """Each per-band overlay from the plans' table builds valid geometry:
    whip above the feed, radial ends at the stake height."""
    for name in ("band20", "band17", "band12", "band10", "band6"):
        b = _variant(name)
        wires = b.build_wires()
        top = max(max(p0[2], p1[2]) for p0, p1, *_ in wires)
        bottom = min(min(p0[2], p1[2]) for p0, p1, *_ in wires)
        assert top == pytest.approx(b.h_feed + b.whip_len_m)
        assert bottom == pytest.approx(b.radial_end_h, abs=0.02)

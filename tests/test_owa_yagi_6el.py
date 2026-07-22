"""6-element 2 m OWA yagi (issue #497): the Cebik `144-6elOWAYagi` port.

Anchors from solving the source deck directly through momwire (bs2, free
space): SWR(50) 1.21 / 1.21 / 1.10 at 144/146/148 MHz, gain 10.1–10.2
dBi, F/B 21–36 dB. The native wavelength-fraction builder reproduced
those within a few percent at port time; these tests pin that window.
"""

import pytest

from antennaknobs import pattern_metrics, resolve_variant_params
from antennaknobs.designs.beams.owa_yagi_6el import Builder
from antennaknobs.engines.momwire import MomwireEngine


def _swr(builder, freq):
    builder.freq = freq
    z = MomwireEngine(builder).impedance()[0]
    g = abs((z - 50.0) / (z + 50.0))
    return (1 + g) / (1 - g)


def test_discoverable():
    from antennaknobs.cli import list_builtin_designs

    assert "beams.owa_yagi_6el" in set(list_builtin_designs())


def test_band_flat_swr_on_2m():
    """The OWA promise: direct 50-ohm feed stays flat across ALL of
    144-148 (deck anchors 1.21/1.21/1.10)."""
    for f in (144.0, 146.0, 148.0):
        assert _swr(Builder(), f) < 1.35, f


def test_gain_pattern_and_forward_direction():
    eng = MomwireEngine(Builder())
    ff = eng.far_field(n_theta=90, n_phi=360, del_theta=1, del_phi=1)
    m = pattern_metrics(ff)
    assert 9.7 < m["peak_gain_dbi"] < 10.7  # deck: 10.20 at 146
    assert m["front_to_back_db"] > 15  # deck: 35.7 at 146
    assert m["azimuth_deg"] == pytest.approx(0.0, abs=10)  # fires +x


def test_d1_is_the_matching_network():
    """Detune the coupled resonator 8 % and the whole-band match
    collapses (measured 2.4-4.1 across the band) while stock stays
    under 1.35 — the OWA mechanism, same demonstration as the 4-el."""
    params = dict(Builder.default_params)
    params["d1_length_factor"] = 0.92
    assert _swr(Builder(params=params), 146.0) > 2.0


def test_70cm_scaled_variant_holds_the_match():
    b = Builder(params=resolve_variant_params(Builder, "band70cm"))
    assert _swr(b, 435.0) < 1.35

"""hexbeam_5band Builder: per-band z-stagger, single-feed default, and the
build_network() daisy-chain feed (replaces the old PyNEC-only build_tls path)."""

from __future__ import annotations

import math

import pytest

from antennaknobs.network import TL
from antennaknobs.designs.multiband.hexbeam_5band import Builder


def _feed_wires(tups):
    """The named band-feed wires (feed0..feedN-1), in emission order."""
    return [t for t in tups if len(t) > 4 and t[4] and str(t[4]).startswith("feed")]


def test_default_is_single_feed_five_bands():
    b = Builder()
    tups = b.build_wires()
    feeds = _feed_wires(tups)
    assert b.n_bands == 5
    assert b.daisy_chain is True  # single common feed by default
    assert len(feeds) == 5
    # Single-feed: no band is driven inline; build_network() drives band 0.
    assert all(t[3] is None for t in feeds)
    net = b.build_network()
    assert net is not None
    assert [s.port for s in net.sources] == ["feed0"]


def test_single_feed_network_jumpers_chain_the_bands():
    b = Builder()
    b.z_spacing = 1.2
    net = b.build_network()
    tls = [br for br in net.branches if isinstance(br, TL)]
    assert len(tls) == 4  # N-1 jumpers for 5 bands
    for tl in tls:
        assert tl.z0 == 50.0
        assert tl.length == pytest.approx(1.2)
    # Each jumper couples successive band feeds up the stack.
    assert [(tl.a, tl.b) for tl in tls] == [
        ("feed0", "feed1"),
        ("feed1", "feed2"),
        ("feed2", "feed3"),
        ("feed3", "feed4"),
    ]


def test_independent_feed_mode_drives_every_band_inline():
    b = Builder()
    b.daisy_chain = False
    assert b.build_network() is None  # no network -> inline-ex multi-feed path
    feeds = _feed_wires(b.build_wires())
    assert len(feeds) == 5
    assert all(t[3] is not None for t in feeds)  # every band driven with ex


def test_n_bands_slicing_drops_higher_bands():
    b = Builder()
    b.n_bands = 3
    tups = b.build_wires()
    assert len(_feed_wires(tups)) == 3
    # single feed still drives only band 0, with n_bands-1 = 2 jumpers
    net = b.build_network()
    assert len([br for br in net.branches if isinstance(br, TL)]) == 2
    # Same per-band tuple count → exactly n_bands × per_band_tuples.
    b5 = Builder()
    assert len(tups) == len(b5.build_wires()) * 3 // 5


def test_n_bands_out_of_range_raises():
    b = Builder()
    b.n_bands = 0
    with pytest.raises(ValueError):
        b.build_wires()
    b.n_bands = 6
    with pytest.raises(ValueError):
        b.build_wires()


def test_z_stagger_band0_on_top():
    """Band 0 (longest wavelength) sits at the highest z; band N-1 at base."""
    b = Builder()
    b.n_bands = 3
    b.z_spacing = 1.5
    b.base = 10.0
    feeds = _feed_wires(b.build_wires())
    zs = [t[0][2] for t in feeds]  # z of the T knot (feed wire start)
    assert zs[0] > zs[1] > zs[2]
    assert math.isclose(zs[0] - zs[1], 1.5)
    assert math.isclose(zs[1] - zs[2], 1.5)
    assert math.isclose(zs[-1], 10.0)


def test_per_band_freq_scales_geometry():
    """Halving the band freq should roughly double its radius (linear in λ)."""
    b = Builder()
    b.n_bands = 2
    bands = (
        {
            "freq": 28.0,
            "halfdriver_factor": 1.0,
            "tipspacer_factor": 0.13,
            "t0_factor": 0.13,
        },
        {
            "freq": 14.0,
            "halfdriver_factor": 1.0,
            "tipspacer_factor": 0.13,
            "t0_factor": 0.13,
        },
    )
    b.bands = bands
    tups = b.build_wires()
    per_band = len(tups) // 2
    s0, s1 = tups[0], tups[per_band]
    dist0 = math.dist(s0[0], s0[1])
    dist1 = math.dist(s1[0], s1[1])
    assert dist1 / dist0 == pytest.approx(2.0, rel=0.05)


def test_registered_single_feed_by_default():
    """The auto-discovered example is single-feed by default (one common feed
    modelled with build_network(), so multi_feed is False)."""
    from antennaknobs.web.examples import REGISTRY

    ex = REGISTRY.get("multiband.hexbeam_5band")
    assert ex is not None
    assert ex.multi_feed is False


def test_opt_physical_variant_keeps_one_coax_mode():
    """opt_physical (issue #921) is tuned against the one-coax drive
    point, so the overlay must leave daisy_chain=True intact and only
    move the per-band shape factors."""
    from antennaknobs.builder import resolve_variant_params

    b = Builder(params=resolve_variant_params(Builder, "opt_physical"))
    assert b.daisy_chain is True
    assert int(b.n_bands) == 5
    assert len(b.bands) == 5
    for band, coupled in zip(b.bands, Builder.opt_coupled_params["bands"]):
        assert band["freq"] == coupled["freq"]
        # Same knob family as the other tunes; factors stay in UI bounds.
        assert 0.9 < band["halfdriver_factor"] < 1.2
        assert 0.05 < band["t0_factor"] < 0.30
    assert [s.port for s in b.build_network().sources] == ["feed0"]


def test_nominal_nsegs_scales_radiator_edges():
    """Standard convergence-flow contract: bumping nominal_nsegs scales
    the radiator edges (auto_mesh density: N per design_freq
    quarter-wave) and leaves the feed gap at 1."""
    counts = {}
    for n in (41, 123):
        b = Builder()
        b.nominal_nsegs = n
        tups = b.build_wires()
        counts[n] = max(t[2] for t in tups)
        assert all(t[2] == 1 for t in _feed_wires(tups))  # feed gaps stay 1
    assert 2.8 < counts[123] / counts[41] < 3.2

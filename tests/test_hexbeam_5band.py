"""hexbeam_5band Builder: per-band z-stagger, multi-feed shape, daisy-
chain TL list. Ports the multi-band convention from momwire's
hexbeam_5band example into antennaknobs's Builder pattern."""

from __future__ import annotations

import math

import pytest

from antennaknobs.designs.multiband.hexbeam_5band import Builder


def _feeds(tups):
    return [(i + 1, t) for i, t in enumerate(tups) if t[3] is not None]


def test_default_is_five_bands_multi_feed():
    b = Builder()
    tups = b.build_wires()
    feeds = _feeds(tups)
    assert b.n_bands == 5
    assert b.daisy_chain is False
    assert len(feeds) == 5
    assert b.build_tls() == []


def test_n_bands_slicing_drops_higher_bands():
    b = Builder()
    b.n_bands = 3
    tups = b.build_wires()
    feeds = _feeds(tups)
    assert len(feeds) == 3
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
    tups = b.build_wires()
    # The feed tuple is the last edge added per band; its endpoints
    # share the same z as the rest of that band.
    feeds = _feeds(tups)
    zs = [feed[1][0][2] for feed in feeds]  # z of T knot
    # Bands emitted in order 0,1,2 → z descends.
    assert zs[0] > zs[1] > zs[2]
    assert math.isclose(zs[0] - zs[1], 1.5)
    assert math.isclose(zs[1] - zs[2], 1.5)
    assert math.isclose(zs[-1], 10.0)


def test_daisy_chain_strips_excitation_from_lower_bands():
    b = Builder()
    b.daisy_chain = True
    tups = b.build_wires()
    feeds = _feeds(tups)
    # Only band 0 (the first feed) keeps a non-None excitation.
    assert len(feeds) == 1


def test_daisy_chain_emits_tl_jumpers():
    b = Builder()
    b.daisy_chain = True
    b.z_spacing = 1.2
    tls = b.build_tls()
    assert len(tls) == 4  # N-1 jumpers for 5 bands
    # Shape PyNECEngine consumes: (idx1, seg1, idx2, seg2, Z, length).
    for jumper in tls:
        assert len(jumper) == 6
        assert jumper[4] == 50.0
        assert jumper[5] == pytest.approx(1.2)
    # Each jumper connects successive feed wires; with the build_wires
    # convention each band emits the same number of tuples so feed
    # indices increment uniformly.
    feed_idxs = [j[0] for j in tls] + [tls[-1][2]]
    diffs = [b - a for a, b in zip(feed_idxs[:-1], feed_idxs[1:])]
    assert len(set(diffs)) == 1  # uniform stride between feeds


def test_daisy_chain_disabled_returns_empty_tls():
    b = Builder()
    assert b.daisy_chain is False
    assert b.build_tls() == []


def test_per_band_freq_scales_geometry():
    """Halving the band freq should roughly double its radius (linear in λ)."""
    b = Builder()
    b.n_bands = 2
    # Use the per-band freq override path: override the second band to
    # double the first's wavelength.
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
    # Take the second-edge-of-each-band (S→A on the driver path); its
    # length should scale with wavelength.
    # Band 0's S→A edge is at tuple index 0; band 1's at index 10
    # (single-band emits 10 tuples).
    per_band = len(tups) // 2
    s0 = tups[0]
    s1 = tups[per_band]
    dist0 = math.dist(s0[0], s0[1])
    dist1 = math.dist(s1[0], s1[1])
    # Band 1 has half the freq → λ doubles → radius doubles.
    assert dist1 / dist0 == pytest.approx(2.0, rel=0.05)


def test_registered_in_web_examples():
    """Adapter auto-discovers the new design and reports multi_feed."""
    from antennaknobs.web.examples import REGISTRY

    ex = REGISTRY.get("multiband.hexbeam_5band")
    assert ex is not None
    assert ex.multi_feed is True


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
        feeds = _feeds(tups)
        assert all(f[1][2] == 1 for f in feeds)  # feed gaps stay 1
    # tripling N triples the densest edge's count (within rounding)
    assert 2.8 < counts[123] / counts[41] < 3.2

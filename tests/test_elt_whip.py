"""Tests for the ELT whip NEC-benchmark design (verticals.elt_whip).

The design's value is *fidelity to the source deck* — a parametric rebuild
of the W8IO ``whip_antenna_8ft_groundplane.nec`` benchmark, including its LD
matching network (90 nH / 3 pF in the two grounded posts) via
``build_network``. The structural pins below are cheap (build only) and run
per-PR; the full-size PyNEC solves are quarantined to the main-only catalog
lane like every per-design solve.
"""

from __future__ import annotations

import math

import pytest

from antennaknobs import as_wire, merge_params
from antennaknobs.designs.verticals.elt_whip import Builder


def _wire(w):
    """Normalize a build_wires entry: (p0, p1, nseg, ex, name-or-None).
    Entries may be plain tuples or Wire named tuples (the upper whip
    carries a per-wire spec since #388)."""
    t = as_wire(w)
    return (t.p0, t.p1, t.n_seg, t.ex, t.name)


def test_default_build_reproduces_deck_counts():
    """At the default knobs the generator must emit exactly the source
    deck's segmentation: 4,392 segments (the number the W8IO benchmark is
    known by). The wire count is pinned too — it changes only if the
    unit-cell emission or the outline profile logic changes."""
    wires = Builder().build_wires()
    assert len(wires) == 4067
    assert sum(w[2] for w in wires) == 4392


def test_default_build_is_well_formed():
    """Finite endpoints, positive lengths, and the network's named wires:
    one "feed" (whip bottom segment) and two posts. No legacy ex markers —
    the drive comes from build_network's Driven port."""
    wires = [_wire(w) for w in Builder().build_wires()]
    names = {name for *_rest, name in wires if name is not None}
    assert names == {"feed", "post0", "post1"}
    assert all(ex is None for _p0, _p1, _n, ex, _name in wires)
    feed = next(w for w in wires if w[4] == "feed")
    assert feed[0] == (0.0, 0.0, 1.0) and feed[2] == 1  # bottom, height=1
    for p0, p1, nseg, _ex, _name in wires:
        assert nseg >= 1
        assert all(math.isfinite(c) for c in (*p0, *p1))
        assert math.dist(p0, p1) > 1e-9


def test_network_matches_deck_ld_cards():
    """build_network carries the deck's LD elements: 90 nH in series with
    post0 (+x), 3 pF in series with post1 (−x); zero knobs omit elements."""
    net = Builder().build_network()
    by_port = {br.port: br for br in net.branches}
    assert by_port["post0"].l == pytest.approx(90e-9) and by_port["post0"].c is None
    assert by_port["post1"].c == pytest.approx(3e-12) and by_port["post1"].l is None
    assert [s.port for s in net.sources] == ["feed"]

    bare = Builder(
        merge_params(Builder.default_params, {"post_l_nh": 0.0, "post_c_pf": 0.0})
    ).build_network()
    assert bare.branches == []


def test_shrunken_knobs_build():
    """Off-default knobs (smaller plane, coarser mesh, fewer cage wires)
    still produce a sane mesh — the resampled outline profile and the
    post/spoke index selection must not crash or emit zero-length wires."""
    b = Builder(
        merge_params(
            Builder.default_params,
            {
                "plane_radius": 0.6,
                "grid_pitch": 0.1016,
                "num_cage_wires": 8,
                "num_posts": 2,
                "num_spokes": 4,
            },
        )
    )
    wires = [_wire(w) for w in b.build_wires()]
    assert len(wires) > 100
    for p0, p1, _nseg, _ex, _name in wires:
        assert math.dist(p0, p1) > 1e-9


def test_coarse_variant_thins_only_the_ground_plane():
    """The `coarse` variant coarsens the passive ground screen to just inside
    the λ/10 rule of thumb — 17 cells across the 48" plane (pitch ≈ λ/10.3 at
    406 MHz, the coarsest integer count under the limit) — and leaves the active
    feed/cage sleeve at full resolution: markedly fewer segments than the
    deck-verbatim default, an unchanged cage, and every wire well-formed."""
    coarse = Builder(merge_params(Builder.default_params, Builder.coarse_params))
    assert round(coarse.plane_radius / coarse.grid_pitch) == 17
    assert coarse.num_cage_wires == Builder.default_params["num_cage_wires"]

    full_segs = sum(_wire(w)[2] for w in Builder().build_wires())
    coarse_segs = sum(_wire(w)[2] for w in coarse.build_wires())
    assert coarse_segs == 2472  # 4392 (deck) thinned by the coarser screen
    assert coarse_segs < 0.7 * full_segs
    for p0, p1, _nseg, _ex, _name in map(_wire, coarse.build_wires()):
        assert math.dist(p0, p1) > 1e-9


@pytest.mark.antenna_computation_check
def test_free_space_impedance_matches_benchmark():
    """Full-size PyNEC solves at the deck's 406 MHz centre.

    With the posts' elements zeroed the feed must reproduce the raw
    benchmark impedance every engine agreed on in the 2026-07-14 run
    (Z ≈ 1.38 + 33.5j free space at one whole-antenna radius; 1.49 + 33.6j
    remeasured 2026-07-15 with the upper whip's true 0.889 mm per-wire
    radius, #388); with the deck's LD values the network transforms that
    to a ~50 Ω-class match (63.0 + 8.1j single-radius, 59.2 + 8.5j
    per-wire). A geometry or network-stamping regression moves either far
    outside its window."""
    pytest.importorskip("PyNEC")
    from antennaknobs.engines import PyNECEngine

    bare = Builder(
        merge_params(Builder.default_params, {"post_l_nh": 0.0, "post_c_pf": 0.0})
    )
    z0 = PyNECEngine(bare, ground=None).impedance()[0]
    assert 1.0 < z0.real < 1.8
    assert 30.0 < z0.imag < 37.0

    z = PyNECEngine(Builder(), ground=None).impedance()[0]
    assert 50.0 < z.real < 75.0
    assert abs(z.imag) < 20.0


def test_example_recommends_sinusoidal_and_declares_406_band():
    """The /examples payload must steer the UI: benchmark-sized mesh ⇒
    default_backend "sinusoidal" (the withhold-warning gate keys on it), and
    a custom 406 MHz band so the design-switch snap can't drag design_freq
    down to 160 m (406 sits outside every HF band)."""
    import antennaknobs.web.examples  # noqa: F401 — primes the adapter

    from antennaknobs.web.examples import REGISTRY

    ex = REGISTRY["verticals.elt_whip"]
    assert ex.default_backend == "sinusoidal"
    assert [(b.key, b.freq_mhz, b.min_mhz, b.max_mhz) for b in ex.bands] == [
        ("406", 406.0, 400.0, 412.0)
    ]
    assert ex.meas_freq_range_mhz == (400.0, 412.0)

"""The stub-matched vertical (issue #648) — the #598 stubs, end to end.

The stub factories are tested against analytic oracles elsewhere. This is the
other half: a real catalog design whose entire matching network is two lengths
of cable, checked the way a user would judge it — does the match land, does it
come apart off-band the way a stub match should, and does the same network
reduce identically on both engines.
"""

import numpy as np
import pytest

from antennaknobs.designs.verticals.stub_matched_vertical import Builder
from antennaknobs.engines import MomwireEngine

from conftest import needs_pynec

Z0 = 50.0


def swr(z, z0=Z0):
    g = abs((z - z0) / (z + z0))
    return (1.0 + g) / (1.0 - g)


def z_at(engine=MomwireEngine, **knobs):
    b = Builder(dict(Builder.default_params, **knobs))
    return complex(engine(b, ground=None).impedance()[0])


# ---------------------------------------------------------------------------
# the match itself
# ---------------------------------------------------------------------------
def test_the_default_knobs_are_a_match():
    """The design ships sitting on a solved match — the boring case that makes
    the interesting one (dragging off it) legible."""
    assert swr(z_at()) < 1.05


def test_bypass_shows_what_the_stub_is_buying():
    """The A/B that gives the match its meaning: the same antenna, same line
    length, no stub — a resonant 22 Ω vertical and its 2.3:1 mismatch."""
    z = z_at(match="bypass")
    assert z.real == pytest.approx(22.0, abs=2.0)
    assert abs(z.imag) < 3.0  # resonant: the mismatch is pure radiation R
    assert 2.0 < swr(z) < 2.6


def test_both_stub_solutions_match():
    """The load's SWR circle crosses the unit-conductance circle twice, so
    there are two answers; the docstring documents both and both must work."""
    long_walk = z_at()  # line 0.406 λ, stub 0.141 λ — the default
    short_walk = z_at(line_wl=0.0957, stub_wl=0.3604)
    assert swr(long_walk) < 1.05
    assert swr(short_walk) < 1.05


def test_either_knob_alone_destroys_the_match():
    """Both lengths are load-bearing: the section rotates, the stub cancels.

    This is what makes it a two-knob exercise rather than a slider with a
    correct value.
    """
    assert swr(z_at(line_wl=0.30)) > 2.0
    assert swr(z_at(stub_wl=0.30)) > 2.0


def test_the_section_rotates_at_constant_swr():
    """Sliding the tap moves Z around the constant-SWR circle of the load —
    the whole reason a line section is step one.
    """
    swrs = [swr(z_at(match="bypass", line_wl=d)) for d in (0.05, 0.15, 0.25, 0.35)]
    # Same circle: the spread is the line's own loss, not a change of match.
    assert max(swrs) - min(swrs) < 0.35
    assert all(2.0 < s < 2.6 for s in swrs)


# ---------------------------------------------------------------------------
# bandwidth — the honest part
# ---------------------------------------------------------------------------
def test_the_match_is_narrow_and_symmetric_about_the_design_freq():
    """A stub match is cut in metres, so it walks off with frequency faster
    than the antenna does. Showing that honestly is half the design's point."""
    b = Builder()
    f0 = b.design_freq
    freqs = np.array([f0 * 0.96, f0 * 0.99, f0, f0 * 1.01, f0 * 1.04])
    zs = MomwireEngine(b, ground=None).impedance_sweep(freqs)[:, 0]
    s = np.array([swr(z) for z in zs])

    assert s[2] < 1.05  # matched at the design frequency
    assert s[1] < 2.0 and s[3] < 2.0  # still usable ±1 %
    assert s[0] > 2.5 and s[4] > 2.5  # gone by ±4 %
    # ...and the antenna alone is nothing like as sharp over the same span.
    bare = MomwireEngine(
        Builder(dict(Builder.default_params, match="bypass")), ground=None
    ).impedance_sweep(freqs)[:, 0]
    assert max(swr(z) for z in bare) < max(s)


def test_the_stub_detunes_because_it_is_cut_in_metres():
    """Cutting the match for another frequency spoils it monotonically — the
    mechanism behind the bandwidth above, isolated: here the *antenna* is
    untouched (its geometry is absolute metres) and only the cut moves.
    """
    on = swr(z_at())  # cut at 28.57, measured at 28.57
    below = [swr(z_at(design_freq=f)) for f in (28.0, 27.0, 26.0)]
    above = swr(z_at(design_freq=30.0))
    assert on < below[0] < below[1] < below[2]
    assert above > on


# ---------------------------------------------------------------------------
# the loss the cable really has
# ---------------------------------------------------------------------------
def test_the_match_costs_real_watts_and_the_budget_says_so():
    """`cable=` means the match is made of real coax, so the power budget
    itemises what the section and the stub burn."""
    eng = MomwireEngine(Builder(), ground=None)
    eng.current_distribution()  # the excited solve is what fills the budget
    rows = dict(eng._excited_power_budget)
    assert rows, "a cable-cut match must itemise its loss"
    # Both halves of the match are made of real coax and both appear.
    assert any("rig" in k or "section" in k for k in rows)
    assert any("stub" in k for k in rows)
    assert sum(max(0.0, w) for w in rows.values()) > 0.0  # RG-213 is not lossless


def test_a_lossier_cable_burns_more():
    """RG-58 against RG-213 in the same match: the ordering has to come out of
    the solve, not from a table."""

    def dissipated(cable):
        eng = MomwireEngine(
            Builder(dict(Builder.default_params, cable=cable)), ground=None
        )
        eng.current_distribution()
        return sum(max(0.0, w) for _lab, w in eng._excited_power_budget)

    assert dissipated("RG-58") > dissipated("RG-213")


# ---------------------------------------------------------------------------
# cross-engine parity — what this design exists to prove
# ---------------------------------------------------------------------------
@needs_pynec
def test_both_engines_agree_on_the_reduced_network():
    """The stubs are reducer-level circuit math on a shunt topology, so PyNEC
    and momwire should agree to MoM-basis tolerance. This design is the
    end-to-end proof of that claim, which #598 could only assert."""
    from antennaknobs.engines.pynec import PyNECEngine  # noqa: PLC0415

    zm = z_at()
    zp = z_at(engine=PyNECEngine)
    # The two engines disagree slightly about the antenna's own feedpoint Z;
    # what must not differ is the network stamped on top of it, so compare at
    # the level the mesh difference allows.
    assert abs(zm - zp) / abs(zm) < 0.10
    assert swr(zp) < 1.35


@needs_pynec
def test_both_engines_agree_on_the_bare_antenna_too():
    """The control for the test above: if the bare feedpoints already differ by
    more than the matched ones, the parity claim would be about the antenna,
    not the network."""
    from antennaknobs.engines.pynec import PyNECEngine  # noqa: PLC0415

    zm = z_at(match="bypass")
    zp = z_at(match="bypass", engine=PyNECEngine)
    assert abs(zm - zp) / abs(zm) < 0.10


# ---------------------------------------------------------------------------
# it behaves like a catalog design
# ---------------------------------------------------------------------------
def test_it_sweeps_without_hitting_a_pole():
    """A shorted stub has no λ/4 singularity (its λ/4 is an open, which is
    harmless) — so unlike an open stub this design sweeps clean. Guards the
    #647 interaction."""
    b = Builder()
    zs = MomwireEngine(b, ground=None).impedance_sweep(
        np.linspace(b.freq * 0.8, b.freq * 1.25, 21)
    )[:, 0]
    assert np.all(np.isfinite(zs))


def test_the_knobs_are_declared_for_the_workbench():
    ui = Builder.default_params["ui_params"]
    assert set(ui["cable"]["enum_options"]) >= {"RG-58", "RG-213"}
    assert ui["match"]["enum_options"] == ("stub", "bypass")
    for knob in ("line_wl", "stub_wl"):
        assert ui[knob]["min"] > 0 and ui[knob]["max"] <= 0.5

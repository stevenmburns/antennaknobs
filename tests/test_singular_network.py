"""Singular networks reached mid-sweep (issue #647).

The stub factories guard their own singularity at *construction*, where
`freq_mhz` and `length_wl` make it decidable. A frequency sweep can walk the
same stub onto its pole anyway, at a frequency the construction guard never
saw — and there the failure is not in any one stamp (each is perfectly finite)
but in the assembled system. These tests cover the two halves of the fix:
detecting that with attribution, and losing one sweep sample instead of the
whole sweep.
"""

from types import MappingProxyType

import numpy as np
import pytest

from antennaknobs import AntennaBuilder
from antennaknobs.engines import MomwireEngine
from antennaknobs.network import (
    Driven,
    Instance,
    Network,
    PortOnWire,
    PortVirtual,
    Shunt,
    TwoPort,
    Wire,
)
from antennaknobs.network_reduce import (
    RCOND_SINGULAR,
    RCOND_SUSPECT,
    SingularNetworkError,
)
from antennaknobs.station import shunt_open_stub

# The stub is 0.20 λ at 28 MHz — a perfectly ordinary length there, and an odd
# quarter-wave at 35 MHz, which is where the sweep below walks it.
STUB_DESIGN_MHZ, STUB_WL = 28.0, 0.20
POLE_MHZ = STUB_DESIGN_MHZ * 0.25 / STUB_WL  # 35.0


class StubbedDipole(AntennaBuilder):
    """A dipole with a lossless open stub across the feed."""

    default_params = MappingProxyType(
        {"freq": 30.0, "base": 0.0, "length_factor": 1.0, "stub_k1": 0.0}
    )

    def build_wires(self):
        y = 0.25 * (300.0 / self.freq) * self.length_factor
        return [
            Wire((0, -y, 0), (0, -0.05, 0), 21, None),
            Wire((0, 0.05, 0), (0, y, 0), 21, None),
            Wire((0, -0.05, 0), (0, 0.05, 0), 3, 1 + 0j, "feed"),
        ]

    def build_network(self):
        stub = shunt_open_stub(
            freq_mhz=STUB_DESIGN_MHZ, length_wl=STUB_WL, z0=50.0, k1=self.stub_k1
        )
        return Network(
            ports={"feed": PortOnWire("feed")},
            branches=[Instance("stub", stub, port="feed")],
            sources=[Driven(port="feed")],
        )


def engine(**knobs):
    return MomwireEngine(StubbedDipole(dict(StubbedDipole.default_params, **knobs)),
                         ground=None)  # fmt: skip


# ---------------------------------------------------------------------------
# the λ/4 open stub: an answer, not a pole (issue #746)
#
# These four tests premised that the exact quarter-wave was unanswerable. It
# never was: Z_in = 0 shorts the port, and only an IDEAL generator — Z_s = 0 —
# cannot drive a short. The reducer's impedance path now stamps the source
# behind `Z_REF_DEFAULT`, so the same stub returns Z = 0 / Γ = −1 with the
# conditioning it has everywhere else. Rewritten to pin that, since a test
# asserting the old refusal would now be asserting a bug.
# ---------------------------------------------------------------------------
def _rcond_at(freq, *, z_ref, **knobs):
    """The equilibrated reciprocal condition of the assembled system."""
    from scipy.linalg.lapack import zgesvx

    e = engine(freq=freq, **knobs)
    wl = e._wavelength_for(freq)
    system = e._reducer.apply_branches(e._compute_y_matrix(wl), wl, z_ref=z_ref)
    return float(zgesvx(system.A, system.rhs.reshape(-1, 1))[8])


def test_a_single_point_on_the_pole_is_a_dead_short_and_says_so():
    """The quarter-wave open stub is the harmonic-notch trap: it puts 0 Ω
    across the feed. That is an answer."""
    z = engine(freq=POLE_MHZ).impedance()[0]
    assert abs(z) < 1e-9, z


def test_the_shorted_port_reads_as_total_reflection():
    """Γ = −1 to within a rounding error — the sign that says short, not open.

    (The issue text asked for Γ ≈ +1 here; that is the OPEN. A λ/4 open stub is
    a short across the port, and the measured value is −1 + 1.2e-16j.)"""
    e = engine(freq=POLE_MHZ)
    wl = e._wavelength_for(POLE_MHZ)
    g = e._reducer.driven_reflection(e._compute_y_matrix(wl), wl)[0]
    assert abs(g + 1.0) < 1e-6, g


def test_the_pole_is_no_worse_conditioned_than_any_other_frequency():
    """The strong form of the claim: not "survivable at the pole" but "there
    is no pole". Measured 2026-08-06 — the ideal-generator stamp collapses
    from 3.2e-2 at 30 MHz to 1.0e-17 at 35, while the Γ-referenced stamp holds
    0.0649 → 0.0656 across the same span."""
    rc_pole = _rcond_at(POLE_MHZ, z_ref=50.0)
    rc_off = _rcond_at(POLE_MHZ * 0.857, z_ref=50.0)  # 30 MHz
    assert rc_pole > 0.05
    assert abs(rc_pole - rc_off) / rc_off < 0.05
    # ...and the thing it replaced really was singular there.
    assert _rcond_at(POLE_MHZ, z_ref=0j) < RCOND_SINGULAR


def test_real_loss_still_gives_the_lossy_answer():
    """Loss used to be the escape hatch; it is now just loss. The stub's own
    copper makes Z_in real and small instead of exactly zero."""
    z = engine(freq=POLE_MHZ, stub_k1=0.2).impedance()[0]
    assert np.isfinite(z) and z.real > 0.0
    assert abs(z) < 1e6


def test_off_the_pole_solves_normally():
    z = engine(freq=POLE_MHZ * 0.9).impedance()[0]
    assert np.isfinite(z)


# ---------------------------------------------------------------------------
# a sweep across the λ/4 keeps every sample
# ---------------------------------------------------------------------------
def test_sweep_across_the_pole_loses_nothing():
    """Was: "poisons only that sample". The poisoning machinery stays for
    topologies that are genuinely singular (below); this stub is not one."""
    freqs = np.array([33.0, 34.0, POLE_MHZ, 36.0, 37.0])
    zs = engine().impedance_sweep(freqs)[:, 0]

    assert np.all(np.isfinite(zs))
    assert abs(zs[2]) < 1e-9  # the short, in the middle of the sweep
    # ...and the samples either side are the real answer, not garbage: an open
    # stub is capacitive below λ/4 and inductive above.
    assert zs[1].imag < 0 < zs[3].imag


class FloatingNode(StubbedDipole):
    """A dipole with a virtual node reachable only through opens.

    The remaining shape of genuine singularity, now that the lossless-line
    poles are gone: a 0 F series capacitor (the inert end of a
    matching-network slider) into a node whose only other branch is another
    open, so nothing in the system determines its voltage. No source impedance
    fixes this and no loss regularises it — the equation is simply missing.
    """

    def build_network(self):
        return Network(
            ports={"feed": PortOnWire("feed"), "dead": PortVirtual("dead")},
            branches=[TwoPort(a="feed", b="dead", c=0.0), Shunt(port="dead", c=0.0)],
            sources=[Driven(port="feed")],
        )


def floating_engine():
    return MomwireEngine(FloatingNode(dict(FloatingNode.default_params)), ground=None)


def test_a_genuinely_singular_topology_still_poisons_its_sample(caplog):
    """The machinery, exercised on something that really has no solution.
    NaN with no explanation would be its own kind of silent failure."""
    with caplog.at_level("WARNING"):
        zs = floating_engine().impedance_sweep(np.array([28.0, 30.0]))[:, 0]
    assert not np.isfinite(zs).any()
    assert "singular network" in caplog.text
    with pytest.raises(SingularNetworkError, match="assembled system"):
        floating_engine().impedance()


def test_a_half_wave_line_mid_sweep_fails_for_its_real_reason_now():
    """Rewritten for issue #746, which retired this test's original premise.

    A plain TL at k·λ/2 used to trip a stamp-time guard, from inside the
    stamp, so it aborted the whole sweep rather than one sample of it; #647's
    fix was to poison the sample. The chain-matrix stamp is finite at every
    length, so the line is no longer the complaint — and what the old guard
    was hiding at this exact frequency turns out to be a genuinely singular
    topology. `wire.doublet_balanced_tuner`'s common-mode return runs through
    that same line, open-terminated at the doublet's floating gap, and an
    open-terminated lossless line at k·λ/2 presents an OPEN. The floating
    tuner section is then referenced to nothing at all.

    Measured 2026-08-06: the sample dies at 16.0387 MHz — the line's own
    half-wave, 14.1 · ½ · 0.91 / 0.40 — for zcomm = 100, 250 and 400 Ω alike.
    Insensitivity to the value is what makes it topological rather than a
    near-pole; the surrounding samples solve normally.
    """
    from antennaknobs.designs.wire.doublet_balanced_tuner import Builder

    b = Builder()
    f_half = b.freq * 0.5 * b.line_vf / b.line_len_factor
    zs = MomwireEngine(b, ground=None).impedance_sweep(
        np.array([f_half * 0.99, f_half, f_half * 1.01])
    )[:, 0]
    assert np.isfinite(zs[[0, 2]]).all()
    assert not np.isfinite(zs[1])

    with pytest.raises(SingularNetworkError, match="assembled system"):
        MomwireEngine(
            Builder(dict(Builder.default_params, freq=f_half)), ground=None
        ).impedance()


# ---------------------------------------------------------------------------
# the thresholds — the part that could silently break healthy designs
# ---------------------------------------------------------------------------
def test_thresholds_are_ordered_and_far_below_healthy_designs():
    assert RCOND_SINGULAR < RCOND_SUSPECT
    # Measured worst case across every catalog design carrying a network is
    # 2.4e-7 (arrays.bowtie1x2_bl); the suspect threshold must sit well under
    # it or healthy designs would warn on every solve.
    assert RCOND_SUSPECT < 2.4e-7


@pytest.mark.parametrize(
    "design",
    [
        "dipoles.invvee_coax_station",
        "dipoles.folded_invvee_balun",
        "verticals.dominator",
        "wire.doublet_ladder_tuner",
        "wire.efhw_sloper",
        "arrays.bowtie1x2_bl",
    ],
)
def test_shipping_network_designs_still_solve(design, caplog):
    """The regression this guard could plausibly cause.

    An MNA matrix mixes admittance rows with unit-valued constitutive rows, so
    a healthy network spans twenty-plus orders of magnitude and an *unscaled*
    condition estimate calls it singular — `arrays.bowtie1x2_bl` reports 1e-16
    that way. Equilibration is what makes the threshold mean rank-deficient
    rather than badly-scaled, and this test is what keeps it honest.
    """
    from importlib import import_module

    Builder = import_module(f"antennaknobs.designs.{design}").Builder
    with caplog.at_level("WARNING"):
        z = MomwireEngine(Builder(), ground=None).impedance()[0]
    assert np.isfinite(z)
    assert "nearly singular" not in caplog.text


# ---------------------------------------------------------------------------
# the web contract: a singular sample must not produce un-parseable JSON
# ---------------------------------------------------------------------------
def test_web_sweep_stays_json_clean_through_a_singular_sample():
    import json

    # `web.examples` first: importing `web.adapter` cold trips the adapter ⇄
    # examples import cycle (the same reason pynec_backend imports the
    # sentinel lazily).
    import antennaknobs.web.examples  # noqa: F401
    from antennaknobs.web.adapter import Z_OPEN_OHMS

    # Retargeted (issue #746) onto `FloatingNode`: the λ/4 open stub this used
    # to sweep no longer produces a NaN to serialise.
    zs = floating_engine().impedance_sweep(np.array([28.0, 30.0]))
    # This is the clamp the /sweep adapter applies before serialising.
    clamped = np.where(np.isfinite(zs), zs, complex(Z_OPEN_OHMS, 0.0))
    body = json.dumps({"z_re": clamped[:, 0].real.tolist()})
    assert "NaN" not in body and "Infinity" not in body
    assert json.loads(body)["z_re"][1] == Z_OPEN_OHMS

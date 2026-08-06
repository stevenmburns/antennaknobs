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
from antennaknobs.network import Driven, Instance, Network, PortOnWire, Wire
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
# detection + attribution
# ---------------------------------------------------------------------------
def test_a_single_point_on_the_pole_raises_with_the_element_named():
    """The whole value of the guard is the sentence it prints."""
    with pytest.raises(SingularNetworkError) as exc:
        engine(freq=POLE_MHZ).impedance()
    msg = str(exc.value)
    assert "stub" in msg  # the instance path, so you know WHICH element
    assert "λ/4" in msg and f"{POLE_MHZ:.4f}" in msg
    assert "k1/k2" in msg or "cable=" in msg  # ...and what to do about it


def test_the_message_says_the_stamps_were_individually_fine():
    """This is the distinguishing feature of the reducer-level case: no single
    branch is singular, so the user should not go looking for one."""
    with pytest.raises(SingularNetworkError) as exc:
        engine(freq=POLE_MHZ).impedance()
    assert "assembled system" in str(exc.value)


def test_real_loss_dissolves_the_singularity():
    """The remedy the message recommends has to actually work."""
    z = engine(freq=POLE_MHZ, stub_k1=0.2).impedance()[0]
    assert np.isfinite(z)
    assert abs(z) < 1e6


def test_off_the_pole_solves_normally():
    z = engine(freq=POLE_MHZ * 0.9).impedance()[0]
    assert np.isfinite(z)


# ---------------------------------------------------------------------------
# a sweep loses one sample, not the sweep
# ---------------------------------------------------------------------------
def test_sweep_across_the_pole_poisons_only_that_sample():
    """The acceptance criterion: a lossless open stub swept across its λ/4."""
    freqs = np.array([33.0, 34.0, POLE_MHZ, 36.0, 37.0])
    zs = engine().impedance_sweep(freqs)[:, 0]

    assert not np.isfinite(zs[2])  # the pole
    assert np.all(np.isfinite(np.delete(zs, 2)))  # everything either side
    # ...and the surviving samples are the real answer, not garbage: an open
    # stub is capacitive below λ/4 and inductive above.
    assert zs[1].imag < 0 < zs[3].imag


def test_the_poisoned_sample_is_logged_with_its_reason(caplog):
    """NaN with no explanation would be its own kind of silent failure."""
    with caplog.at_level("WARNING"):
        engine().impedance_sweep(np.array([34.0, POLE_MHZ, 36.0]))
    text = caplog.text
    assert "singular network" in text and f"{POLE_MHZ:g}" in text
    assert "stub" in text


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

    zs = engine().impedance_sweep(np.array([34.0, POLE_MHZ, 36.0]))
    # This is the clamp the /sweep adapter applies before serialising.
    clamped = np.where(np.isfinite(zs), zs, complex(Z_OPEN_OHMS, 0.0))
    body = json.dumps({"z_re": clamped[:, 0].real.tolist()})
    assert "NaN" not in body and "Infinity" not in body
    assert json.loads(body)["z_re"][1] == Z_OPEN_OHMS

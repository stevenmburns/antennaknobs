"""Physics validation for `BalancedLine` (issue #576) — the measured half.

`tests/test_balanced_line.py` (issue #575) proves the 4×4 differential stamp
is mathematically exact. These tests validate the *physics the stamp claims
to model*, against full-wave MoM solves:

1. A close-spaced two-wire pair, built as physical MoM wires, IS the ideal
   TEM line the element stamps: its measured characteristic impedance matches
   the analytic ``(η0/π)·acosh(D/2a)`` and its electrical length is the
   physical length plus a small constant end-effect (vf = 1 for bare wire).
   Measured on the momwire solver via the classic open/short method:
   ``Z0 = sqrt(Zoc·Zsc)``, ``tanh(γl) = sqrt(Zsc/Zoc)``.

2. That fidelity is a *tightly-coupled-regime* property: the deviation from
   ideal-TEM grows monotonically with conductor spacing as the pair
   decouples into two radiating wires (the `tl_riser_test.py` over-
   generalization from issue #575's background, made into an assertion).

3. `wire.sterba`'s offset-pair verticals — the structure BalancedLine was
   built to model — really do carry differential current: the common-mode
   residual |I1+I2| is a small fraction of the differential |I1−I2| on every
   interior riser pair. This is the premise that the pair does not radiate
   (and it bounds how faithful any differential-only element can be). Note
   it is a property of the *closed multi-cell curtain*: a single extracted
   cell is common-mode dominated (CM/DM ≈ 2.3, measured while developing
   these tests), which is why the oracle must be the full structure.

4. The end-to-end BalancedLine-riser curtain (one Sterba bay, risers as
   4-terminal elements on `PortAtEnd` junction ports) reproduces the all-wire
   `wire.sterba`'s broadside gain — but ONLY with the element's ``zcomm``
   common-mode path enabled. This is the #576 end-to-end finding: the pair's
   conductor continuity is a load-bearing boundary condition in the
   multi-loop curtain even though its CM current is small (test 3), and at
   the risers' resonant λ/2 length the CM transport is a repeater —
   insensitive to the ``zcomm`` value, which the test also asserts.
   (History: #576 first found the attachment blocker, solved by #579's end
   ports; then the differential-only residual, solved by ``zcomm``.)

5. The same end-to-end claim at the *catalog* configuration, n_cells=3,
   where it is far sharper than at one bay: omitting the CM path costs 5 dB
   and swings the beam 35° off broadside (vs −0.9 dB and still broadside at
   n=1). Pins both published gain figures over average ground (+15.2 dBi
   all-wire, +15.4 dBi BL-riser), and establishes that ``zcomm`` is a
   *topological switch* rather than a tuning knob: a 128× sweep of its value
   (25 Ω → 3200 Ω) moves the gain by 0.05 dB, while removing it costs 5 dB.

6. Element SUBSTITUTION as a two-port — #576's original acceptance criterion,
   stated directly. One antenna built twice, once with a physical open-wire
   feeder and once with that feeder replaced by the element (``zdiff`` from
   the analytic geometry, not fitted): the complex driving-point impedance
   agrees to 2.4–4.3 % across feeder lengths spanning 83 − j118 to
   1158 + j1616 Ω. Covers the NON-λ/2 regime section 5's repeater argument
   does not, which is where ``wire.doublet_balanced_tuner`` operates.

7. The counter-case that keeps 5 and 6 from being over-generalized: in an
   OPEN feed tree (``arrays.bowtie1x2_bl``'s corporate feed) there is no
   common-mode return, so a CM path is a real extra shunt admittance and its
   VALUE matters — ``zcomm = 100 Ω`` drags the driving-point R from 50 Ω to
   5 Ω. CM-open is the physical model there, and large ``zcomm`` converges
   back to it monotonically. So the rule is topological, not universal: set
   ``zcomm`` when the pair closes a conduction loop the differential stamp
   would break; leave it open when the pair simply ends.

8. Why ``PortAtEnd`` exists at all — the negative result. The obvious
   engine-portable substitute (hang a short stub off the conductor end and
   centre-tap it with an ordinary gap port, then shrink it) does NOT converge
   to a junction-node port: it converges to an OPEN, R collapsing to ~0.01 Ω.
   The stub beyond the gap is a dead end, so the port can only drive
   displacement current into a capacitance that vanishes with the stub. The
   contrast with momwire's own ``_bridged_z`` oracle — where the same limit
   converges to 1.5 % — is where the SECOND terminal lands: a live conductor
   converges, a dead stub opens. A gap always needs metal on both sides,
   which is exactly what a conductor end does not have.

9. The construction actually shipped (`wire.doublet_balanced_tuner`): one
   wire, an ideal delta gap at its centre exposed as a `PortOnWireFloating`,
   no bridge and no second length scale. Its idealization error against a
   physical feeder is 3.2 / 2.1 / 1.3 % — a few percent being the expected gap
   between an ideal delta-gap feed and a real two-wire attachment. Agreement
   with physical wires BOUNDS that error; it is not the definition of
   correctness, since the model is an idealization and the physical build is a
   different model. The model's own criterion is convergence under refinement,
   which both engines satisfy.
"""

import importlib
import math
from types import MappingProxyType

import numpy as np
import pytest

from antennaknobs import AntennaBuilder
from antennaknobs.network import (
    BalancedLine,
    Driven,
    FloatingBalun,
    Network,
    PortAtEnd,
    PortOnWire,
    PortOnWireFloating,
    PortVirtual,
    Wire,
)
from antennaknobs.engines.momwire import MomwireEngine

C_LIGHT = 299.792458  # m·MHz
FREQ = 28.47
WL = C_LIGHT / FREQ
ETA0_OVER_PI = 376.730313668 / math.pi
WIRE_RADIUS = 0.0005  # engine default idealization (PEC, 0.5 mm)


def analytic_zdiff(spacing):
    """Ideal TEM two-wire differential impedance for the default wire."""
    return ETA0_OVER_PI * math.acosh(spacing / (2.0 * WIRE_RADIUS))


class _PairBuilder(AntennaBuilder):
    """Vertical two-wire pair, driven at the bottom through a small bridge
    (the source loop closure a differential drive physically needs), far end
    open or shorted. The characterization testbed from the #576 oracle."""

    default_params = MappingProxyType(
        {
            "design_freq": FREQ,
            "freq": FREQ,
            "spacing": 0.042,
            "line_len_wl": 0.3,
            "termination": "open",  # "open" | "short"
        }
    )

    def build_wires(self):
        s = self.spacing
        L = self.line_len_wl * WL
        xa, xb = 0.3 * s, 0.7 * s
        n_pair = min(max(self.segs_for(L, 0.25 * WL), round(L / s)), 151)
        tups = [
            Wire((0.0, 0.0, 0.0), (xa, 0.0, 0.0)),
            Wire((xa, 0.0, 0.0), (xb, 0.0, 0.0), name="feed"),
            Wire((xb, 0.0, 0.0), (s, 0.0, 0.0)),
            Wire((0.0, 0.0, 0.0), (0.0, 0.0, L), n_seg=n_pair),
            Wire((s, 0.0, 0.0), (s, 0.0, L), n_seg=n_pair),
        ]
        if self.termination == "short":
            tups.append(Wire((0.0, 0.0, L), (s, 0.0, L)))
        return tups

    def build_network(self):
        return Network(
            ports={"feed": PortOnWire("feed", distributed=True)},
            branches=[],
            sources=[Driven(port="feed", voltage=1 + 0j)],
        )


def _zin(spacing, line_len_wl, termination):
    b = _PairBuilder(
        dict(
            _PairBuilder.default_params,
            spacing=spacing,
            line_len_wl=line_len_wl,
            termination=termination,
        )
    )
    return complex(MomwireEngine(b, ground=None).impedance()[0])


def _characterize(spacing, line_len_wl):
    """(Z0, beta·l in rad) of the physical pair from open/short Zin."""
    zoc = _zin(spacing, line_len_wl, "open")
    zsc = _zin(spacing, line_len_wl, "short")
    z0 = complex(np.sqrt(zoc * zsc))
    gl = complex(np.arctanh(np.sqrt(zsc / zoc)))
    beta_l = gl.imag
    # arctanh returns the principal branch; unwrap onto the branch nearest
    # the physical length
    target = 2.0 * math.pi * line_len_wl
    beta_l += round((target - beta_l) / math.pi) * math.pi
    return z0, beta_l


@pytest.mark.antenna_computation_check
def test_physical_pair_is_the_ideal_tem_line_balancedline_stamps():
    """Tightly-coupled regime (s = 0.004 λ, the Sterba offset-pair scale):
    the MoM pair's Z0 matches the analytic zdiff within 3 %, is essentially
    lossless, and its electrical length is the physical length plus a small
    constant end-effect — i.e. vf = 1.000 with a per-testbed ~1° fixture
    offset, not a velocity-factor error that would accumulate with length."""
    s = 0.004 * WL
    excesses = []
    for llw in (0.2, 0.3):
        z0, beta_l = _characterize(s, llw)
        assert abs(z0.real - analytic_zdiff(s)) / analytic_zdiff(s) < 0.03
        # bare PEC pair: no measurable loss component in Z0
        assert abs(z0.imag) < 0.02 * abs(z0.real)
        excesses.append(math.degrees(beta_l) - 360.0 * llw)
    # both lengths see the SAME small end-effect excess: constant offset
    # (attachment fixture), zero slope (vf = 1 on the line proper)
    assert 0.3 < excesses[0] < 2.0
    assert abs(excesses[1] - excesses[0]) < 0.15


@pytest.mark.antenna_computation_check
def test_pair_fidelity_degrades_monotonically_as_it_decouples():
    """The ideal-line correspondence is a property of tight coupling. As the
    spacing grows toward the decoupled regime the measured Z0 falls away
    from the analytic TEM value monotonically — the quantified form of the
    `tl_riser_test.py` lesson (a wide pair is NOT a transmission line, and a
    test that only samples it proves nothing about the coupled regime)."""
    devs = []
    for s_wl in (0.004, 0.016, 0.06):
        s = s_wl * WL
        z0, _ = _characterize(s, 0.3)
        devs.append(abs(z0.real - analytic_zdiff(s)) / analytic_zdiff(s))
    assert devs[0] < 0.03  # tightly coupled: the element's home regime
    assert devs[0] < devs[1] < devs[2]  # decoupling: monotone degradation
    assert devs[2] > 0.10  # by 0.06 λ the TEM model is visibly wrong


@pytest.mark.antenna_computation_check
def test_sterba_offset_pair_risers_carry_differential_current():
    """wire.sterba's interior offset-pair verticals operate as a balanced
    line: on every interior boundary the common-mode residual |I1+I2| stays
    below 20 % of the differential |I1−I2| (measured 0.05–0.15). This is the
    premise behind both the risers' non-radiation in the catalog design and
    the BalancedLine element's differential-only contract."""
    from antennaknobs.designs.wire.sterba import Builder

    b = Builder()
    eng = MomwireEngine(b, ground=None)
    dist = eng.current_distribution()

    wl = C_LIGHT / b.design_freq
    h = 0.5 * wl * b.length_factor
    q = 0.5 * h
    n = int(b.n_cells)
    s = b.spacing
    yb = [0.0, q] + [q + k * h for k in range(1, n + 1)] + [2 * q + n * h]
    bot, top = b.base, b.base + h

    def riser_current(x, y):
        """Current samples (normalized to +z flow) on the vertical at (x, y)."""
        for wc in dist:
            pos = np.asarray(wc.knot_positions)
            cur = np.asarray(wc.knot_currents)
            on = (
                (np.abs(pos[:, 0] - x) < 1e-6)
                & (np.abs(pos[:, 1] - y) < 1e-6)
                & (pos[:, 2] > bot + 0.05 * h)
                & (pos[:, 2] < top - 0.05 * h)
            )
            if on.sum() >= 3:
                z, i = pos[on, 2], cur[on]
                if z[-1] < z[0]:  # polyline walked downward: flip convention
                    i = -i
                order = np.argsort(z)
                return z[order], i[order]
        raise AssertionError(f"riser at (x={x}, y={y}) not found")

    zs = np.linspace(bot + 0.1 * h, top - 0.1 * h, 25)

    def resample(z, i):
        return np.interp(zs, z, i.real) + 1j * np.interp(zs, z, i.imag)

    ratios = []
    for k in range(1, n + 2):  # the interior boundaries carry the pairs
        i1 = resample(*riser_current(0.0, yb[k]))
        i2 = resample(*riser_current(s, yb[k]))
        cm = np.max(np.abs(i1 + i2))
        dm = np.max(np.abs(i1 - i2))
        ratios.append(cm / dm)
    assert all(r < 0.2 for r in ratios), ratios


# ---------------------------------------------------------------------------
# 4. End-to-end: a one-bay BL-riser curtain reproduces wire.sterba — with zcomm
# ---------------------------------------------------------------------------


def _catalog_curtain(n_cells, **overrides):
    """The promoted catalog design (wire.sterba_bl): wire.sterba's exact
    radiator layout with every interior riser pair replaced by a BalancedLine
    across four `PortAtEnd` junction ports, wired by physical conductor
    pairing (port A = the two top-rail ends, conductor 1 = the A-conductor
    riser). This test IS the design's physics regression."""
    from antennaknobs.designs.wire.sterba_bl import Builder

    return Builder(dict(Builder.default_params, n_cells=n_cells, **overrides))


def _peak(eng):
    ff = eng.far_field(n_theta=45, n_phi=72, del_theta=2, del_phi=5)
    rings = np.asarray(ff.rings)
    _, j = np.unravel_index(np.argmax(rings), rings.shape)
    return float(ff.max_gain), float(np.asarray(ff.phis)[j])


@pytest.mark.antenna_computation_check
def test_bl_riser_curtain_reproduces_wire_sterba_with_zcomm():
    """The #576 end-to-end acceptance at one bay, free space: the BL-riser
    curtain must land within 0.5 dB of the all-wire wire.sterba and fire
    BROADSIDE. Differential-only (zcomm=None) fails the gain bound (−0.9 dB
    at one bay, from the ±90°-per-boundary span-phase fanout that at n≥3
    grows to −5 dB with the beam steered to az 35°); the CM path restores
    it. At the risers' λ/2 length the CM line is a repeater, so the result
    must be insensitive to the zcomm value — the reason no zdiff/zcomm
    tuning is needed or possible."""
    ster = importlib.import_module("antennaknobs.designs.wire.sterba").Builder
    bp = ster(dict(ster.default_params, n_cells=1))
    gain_phys, az_phys = _peak(MomwireEngine(bp, ground=None))
    assert min(az_phys % 180.0, 180.0 - az_phys % 180.0) <= 10.0  # broadside

    b100 = _catalog_curtain(1, zcomm=100.0)
    gain_100, az_100 = _peak(MomwireEngine(b100, ground=None))
    assert min(az_100 % 180.0, 180.0 - az_100 % 180.0) <= 10.0
    assert abs(gain_100 - gain_phys) < 0.5

    b400 = _catalog_curtain(1, zcomm=400.0)
    gain_400, _az = _peak(MomwireEngine(b400, ground=None))
    assert abs(gain_400 - gain_100) < 0.1  # λ/2 repeater: zcomm-insensitive


# ---------------------------------------------------------------------------
# 5. The catalog configuration: n_cells=3, where the CM path is load-bearing
# ---------------------------------------------------------------------------
#
# Section 4 validates one bay, which is the *weakest* form of the claim: at
# n=1 the differential-only curtain is only −0.9 dB and still broadside, so
# the CM path looks like a refinement. The catalog default is n_cells=3, and
# there the same omission costs −5 dB AND swings the beam 35° off broadside.
# These tests pin the shipped configuration and the documented gain figures.


def _peak_over(builder, ground):
    return _peak(MomwireEngine(builder, ground=ground))


AVG_GROUND = ("finite-fast", 13.0, 0.005)


@pytest.mark.antenna_computation_check
def test_bl_riser_curtain_matches_wire_sterba_at_catalog_n_cells():
    """Free space, n_cells=3 (the catalog default): the BL-riser curtain
    tracks the all-wire wire.sterba to within 0.5 dB and fires broadside.

    This is the load-bearing end-to-end case. Unlike the one-bay test, the
    differential-only build fails here *unmistakably* — the per-boundary
    span-phase fanout accumulates over three bays into a beam that is both
    ~5 dB down and pointed 35° off broadside. Measured 2026-07-28:

        wire.sterba (all wire)   10.47 dBi  az 180
        sterba_bl  (zcomm on)    10.61 dBi  az 180   (+0.14)
        sterba_bl  (zcomm off)    5.52 dBi  az  35   (-4.95)
    """
    ster = importlib.import_module("antennaknobs.designs.wire.sterba").Builder
    bp = ster(dict(ster.default_params, n_cells=3))
    gain_phys, az_phys = _peak_over(bp, None)
    assert min(az_phys % 180.0, 180.0 - az_phys % 180.0) <= 10.0

    gain_bl, az_bl = _peak_over(_catalog_curtain(3), None)
    assert min(az_bl % 180.0, 180.0 - az_bl % 180.0) <= 10.0
    assert abs(gain_bl - gain_phys) < 0.5

    # differential-only: the failure is large and directional, not marginal
    gain_dm, az_dm = _peak_over(_catalog_curtain(3, zcomm=0.0), None)
    assert gain_phys - gain_dm > 3.0
    assert min(az_dm % 180.0, 180.0 - az_dm % 180.0) > 20.0


@pytest.mark.antenna_computation_check
def test_catalog_curtain_gain_over_average_ground():
    """Over average ground (eps_r 13, sigma 0.005) at n_cells=3 — the
    configuration the documentation quotes. Pins both published figures:
    wire.sterba at +15.2 dBi (issue #576's acceptance target) and
    wire.sterba_bl at +15.4 dBi, both broadside. Measured 2026-07-28:
    15.22 and 15.39 dBi."""
    ster = importlib.import_module("antennaknobs.designs.wire.sterba").Builder
    gain_phys, az_phys = _peak_over(
        ster(dict(ster.default_params, n_cells=3)), AVG_GROUND
    )
    gain_bl, az_bl = _peak_over(_catalog_curtain(3), AVG_GROUND)

    assert abs(gain_phys - 15.2) < 0.3, gain_phys
    assert abs(gain_bl - 15.4) < 0.3, gain_bl
    assert abs(gain_bl - gain_phys) < 0.5
    for az in (az_phys, az_bl):
        assert min(az % 180.0, 180.0 - az % 180.0) <= 10.0


@pytest.mark.antenna_computation_check
def test_zcomm_is_a_topological_switch_not_a_tuning_knob():
    """The CM path's *presence* is load-bearing; its *value* is not.

    At the risers' λ/2 length the common-mode line is a repeater, so the
    curtain is insensitive to zcomm across a 128× range — 25 Ω to 3200 Ω
    spans 0.05 dB (measured 2026-07-28: 10.62 / 10.61 / 10.61 / 10.61 /
    10.61 / 10.62 / 10.63 / 10.66 dBi, all broadside). Removing it entirely
    costs 5 dB (previous test).

    This is why `zcomm` needs no calibration and cannot be fitted: it is a
    switch for conductor continuity, not a characteristic impedance the user
    is expected to get right. A future geometry-derived zcomm (#596) must
    reproduce this insensitivity, not a particular number."""
    gains = []
    for zc in (25.0, 100.0, 400.0, 1600.0, 3200.0):
        g, az = _peak_over(_catalog_curtain(3, zcomm=zc), None)
        assert min(az % 180.0, 180.0 - az % 180.0) <= 10.0
        gains.append(g)
    assert max(gains) - min(gains) < 0.25, gains


# ---------------------------------------------------------------------------
# 6. Element substitution: a real feeder replaced by the element, as a 2-port
# ---------------------------------------------------------------------------
#
# Sections 1-2 characterize the pair as a line (Z0, electrical length) and
# sections 4-5 check an end-to-end pattern. This is the direct statement of
# #576's original criterion in between: build one antenna twice — once with
# the feeder as PHYSICAL MoM wires, once with that same feeder replaced by a
# `BalancedLine` element — and compare the complex driving-point impedance.
#
# It generalizes past the Sterba: the feeder here is a plain open-wire drop
# at lengths that are NOT λ/2, which is the regime `wire.doublet_balanced_
# tuner` lives in and the one section 5's repeater argument does not cover.

_ARM_FACTOR = 0.25
_SUBST_BASE = {
    "design_freq": FREQ,
    "freq": FREQ,
    "spacing": 0.004 * WL,
    "arm_factor": _ARM_FACTOR,
    "feed_len_wl": 0.30,
}


class _PhysFedDoublet(AntennaBuilder):
    """Doublet + open-wire drop, all as physical wires, driven at a bridge
    gap across the bottom of the pair (a genuinely floating differential
    drive: the source loop closes through real metal)."""

    default_params = MappingProxyType(_SUBST_BASE)

    def build_wires(self):
        s, arm, L = self.spacing, self.arm_factor * WL, self.feed_len_wl * WL
        n = min(max(self.segs_for(L, 0.25 * WL), round(L / s)), 151)
        xa, xb = -0.2 * s, 0.2 * s
        return [
            Wire((0.0, -s / 2, L), (-arm, -s / 2, L)),
            Wire((0.0, +s / 2, L), (+arm, +s / 2, L)),
            Wire((0.0, -s / 2, L), (0.0, -s / 2, 0.0), n_seg=n),
            Wire((0.0, +s / 2, L), (0.0, +s / 2, 0.0), n_seg=n),
            Wire((0.0, -s / 2, 0.0), (0.0, xa, 0.0)),
            Wire((0.0, xa, 0.0), (0.0, xb, 0.0), name="feed"),
            Wire((0.0, xb, 0.0), (0.0, +s / 2, 0.0)),
        ]

    def build_network(self):
        return Network(
            ports={"feed": PortOnWire("feed", distributed=True)},
            branches=[],
            sources=[Driven(port="feed")],
        )


class _ElementFedDoublet(AntennaBuilder):
    """The SAME doublet, feeder deleted from the geometry and replaced by a
    `BalancedLine` on `PortAtEnd` ports. Driven through an ideal 1:1
    `FloatingBalun`, the circuit equivalent of the physical build's floating
    bridge-gap drive."""

    default_params = MappingProxyType(dict(_SUBST_BASE, zcomm=600.0))

    def build_wires(self):
        s, arm, L = self.spacing, self.arm_factor * WL, self.feed_len_wl * WL
        return [
            Wire((0.0, -s / 2, L), (-arm, -s / 2, L), name="armL"),
            Wire((0.0, +s / 2, L), (+arm, +s / 2, L), name="armR"),
        ]

    def build_network(self):
        s, L = self.spacing, self.feed_len_wl * WL
        return Network(
            ports={
                "ta": PortAtEnd("armL", end="p0"),
                "tb": PortAtEnd("armR", end="p0"),
                "rig": PortVirtual("rig"),
                "bL": PortVirtual("bL"),
                "bR": PortVirtual("bR"),
            },
            branches=[
                FloatingBalun(primary="rig", a="bL", b="bR", n=1.0),
                BalancedLine(
                    a1="bL",
                    a2="bR",
                    b1="ta",
                    b2="tb",
                    zdiff=analytic_zdiff(s),
                    length=L,
                    vf=1.0,
                    zcomm=self.zcomm or None,
                ),
            ],
            sources=[Driven(port="rig")],
        )


def _subst_zin(cls, **over):
    b = cls(dict(cls.default_params, **over))
    return complex(MomwireEngine(b, ground=None).impedance()[0])


@pytest.mark.antenna_computation_check
def test_element_reproduces_a_physical_feeder_as_a_two_port():
    """Replacing a physical open-wire feeder with the element reproduces the
    complex driving-point impedance to within 6 %, at feeder lengths chosen
    to span wildly different impedance regimes — the element is not being
    checked at one convenient operating point. `zdiff` is the ANALYTIC
    value from the geometry, not a fitted one. Measured 2026-07-28:

        len     physical            element           deviation
        0.20 λ  1158.2 +1615.8j     1079.0 +1583.4j     4.3 %
        0.30 λ   445.2 -1075.6j      467.2 -1100.5j     2.9 %
        0.45 λ    82.6  -118.4j       83.1  -121.9j     2.4 %

    The residual is the physical pair's own radiation and end effects, which
    a differential-only element cannot represent by construction — i.e. this
    bounds the element's achievable fidelity, it is not a bug to drive out.
    """
    for flw, tol in ((0.20, 0.06), (0.30, 0.06), (0.45, 0.06)):
        zp = _subst_zin(_PhysFedDoublet, feed_len_wl=flw)
        ze = _subst_zin(_ElementFedDoublet, feed_len_wl=flw)
        assert abs(ze - zp) / abs(zp) < tol, (flw, zp, ze)


@pytest.mark.antenna_computation_check
def test_zcomm_value_is_immaterial_behind_a_floating_balun():
    """Third independent confirmation that `zcomm` carries no information
    (after section 5's λ/2-repeater sweep): behind a floating balun secondary
    there is no common-mode circuit path at all, so the CM line carries no
    current whatever its impedance — a 16× sweep is bit-identical.

    `zcomm` is required here only for MNA determinacy: `Network` rejects a
    CM-open BalancedLine feeding a floating-balun secondary as structurally
    singular. That is the whole reason `wire.doublet_balanced_tuner` sets a
    `line_zcomm` at all, and why its particular value needs no defending."""
    zs = [
        _subst_zin(_ElementFedDoublet, zcomm=zc)
        for zc in (150.0, 300.0, 600.0, 1200.0, 2400.0)
    ]
    assert max(abs(z - zs[0]) for z in zs) < 1e-6, zs


# ---------------------------------------------------------------------------
# 7. The other topology: an OPEN feed tree, where zcomm is a modelling error
# ---------------------------------------------------------------------------
#
# Sections 5 and 6 both found zcomm's value immaterial — but both live in
# topologies that make it so (a closed λ/2 loop; a floating-balun secondary
# with no CM path at all). `arrays.bowtie1x2_bl` is the counter-case and the
# reason the element ships zcomm as an explicit opt-in rather than a default:
# its corporate feed is an open tree, and the physical model is CM-OPEN.
#
# In the design's floating-gap authoring (#608) the statement sharpens from
# "the value matters" to "any value is wrong": the element-side gap passes
# zero CM current STRUCTURALLY, so the λ/4 CM line dead-ends into an open,
# and the quarter-wave open→short transform pins the CM level at the
# grounded tap to zero — shorting the driven node for ANY finite zcomm (the
# constraint is Z-independent; only the current scale changes). The PortAtEnd
# authoring recovered the open answer as zcomm→∞; the floating authoring is
# discontinuous there, which is why the design pins the CM level with 100 MΩ
# shunts instead of zcomm (see its docstring).


@pytest.mark.antenna_computation_check
def test_zcomm_is_a_modelling_error_in_an_open_feed_tree():
    """`arrays.bowtie1x2_bl` (zcomm off by default): adding a common-mode
    path to a feed whose element side is a structural CM open is not a
    refinement at ANY value — the λ/4 line transforms the open into a CM
    short at the grounded tap, collapsing the driving-point impedance.
    Measured 2026-07-30 (floating-gap authoring): zcomm off → 49.8−0.4j
    (the physical model, SWR 1.01); zcomm 100/600/1500 → |Ztap| < 1 Ω.
    Guards the docs' claim that the choice is topological AND that the CM
    level pin must be the high-R shunt, never zcomm."""
    from antennaknobs.designs.arrays.bowtie1x2_bl import Builder

    def zin(zc):
        b = Builder(dict(Builder.default_params, zcomm=zc))
        return complex(MomwireEngine(b, ground=None).impedance()[0])

    z_open = zin(0.0)  # the design default: CM path absent
    assert abs(z_open.real - 50.0) < 5.0 and abs(z_open.imag) < 5.0

    # ANY finite zcomm is a gross, visible error — the λ/4 open→short
    # transform is independent of the line impedance.
    for zc in (100.0, 600.0, 1500.0):
        z = zin(zc)
        assert abs(z - z_open) / abs(z_open) > 0.5, (zc, z)
        assert abs(z) < 1.0, (zc, z)  # the tap-short mechanism specifically


@pytest.mark.antenna_computation_check
def test_bowtie_corporate_feed_runs_on_both_engines():
    """The #608 bowtie-half payoff: the floating-gap corporate feed is
    engine-portable. PyNEC accepts the design (impossible with the previous
    PortAtEnd authoring — NEC-2 has no junction-node card) and agrees with
    momwire on the matched tap. Measured 2026-07-30 at the retuned point
    (45.0°, 0.5525, 100 Ω): momwire 50.00−0.21j, PyNEC 49.86−1.19j, gains
    5.70/5.70 dBi broadside."""
    from antennaknobs.designs.arrays.bowtie1x2_bl import Builder
    from antennaknobs.engines.pynec import PyNECEngine

    zm = complex(MomwireEngine(Builder(), ground=None).impedance()[0])
    zp = complex(PyNECEngine(Builder(), ground=None).impedance()[0])
    for z in (zm, zp):
        assert abs(z - 50.0) < 3.0, z  # both engines see the ~1:1 match
    assert abs(zm - zp) < 3.0, (zm, zp)  # and agree with each other


# ---------------------------------------------------------------------------
# 8. Why PortAtEnd exists: the shrinking-nub construction does NOT converge
# ---------------------------------------------------------------------------
#
# The natural objection to a momwire-only junction-node port is: "attach a
# tiny wire at the conductor end, centre-tap it, and shrink it — in the limit
# that IS an end port, and it works on every engine." It is a good objection,
# and it is wrong, for a reason worth recording rather than rediscovering.


class _NubFedDoublet(_ElementFedDoublet):
    """`_ElementFedDoublet` with each `PortAtEnd` replaced by a short stub at
    the arm end, centre-tapped by an ordinary `PortOnWire` gap."""

    default_params = MappingProxyType(dict(_SUBST_BASE, zcomm=600.0, nub=0.1))

    def build_wires(self):
        s, arm, L = self.spacing, self.arm_factor * WL, self.feed_len_wl * WL
        nub = self.nub
        return [
            # arms unnamed: the ports now live on the stubs, not the arm ends
            Wire((0.0, -s / 2, L), (-arm, -s / 2, L)),
            Wire((0.0, +s / 2, L), (+arm, +s / 2, L)),
            Wire((0.0, -s / 2, L), (nub, -s / 2, L), name="nubL", n_seg=3),
            Wire((0.0, +s / 2, L), (nub, +s / 2, L), name="nubR", n_seg=3),
        ]

    def build_network(self):
        s, L = self.spacing, self.feed_len_wl * WL
        return Network(
            ports={
                "nubL": PortOnWire("nubL"),
                "nubR": PortOnWire("nubR"),
                "rig": PortVirtual("rig"),
                "bL": PortVirtual("bL"),
                "bR": PortVirtual("bR"),
            },
            branches=[
                FloatingBalun(primary="rig", a="bL", b="bR", n=1.0),
                BalancedLine(
                    a1="bL",
                    a2="bR",
                    b1="nubL",
                    b2="nubR",
                    zdiff=analytic_zdiff(s),
                    length=L,
                    vf=1.0,
                    zcomm=self.zcomm,
                ),
            ],
            sources=[Driven(port="rig")],
        )


@pytest.mark.antenna_computation_check
def test_shrinking_nub_does_not_converge_to_an_end_port():
    """A centre-tapped stub at a conductor end converges to an OPEN, not to
    a junction-node port — so `PortAtEnd` cannot be replaced by it.

    The stub beyond the gap is a dead end: current must vanish at its tip, so
    the only current the port can drive is displacement current charging the
    stub, whose capacitance shrinks with its length. The port series
    impedance runs to -j*infinity. Measured 2026-07-29 (reference
    PortAtEnd: 467.2 - 1100.5j):

        nub = 1.00 m   13.32 + 470.7j
        nub = 0.30 m    0.56 + 175.7j
        nub = 0.10 m    0.06 + 193.5j
        nub = 0.03 m    0.01 + 180.2j
        nub = 0.01 m    0.01 + 173.8j

    R collapses toward zero: no power reaches the antenna at all. Contrast
    momwire's own `_bridged_z` oracle, where the same shrinking limit DOES
    converge (<1.5%) — there both terminals land on conductors that carry
    current away. The discriminator is where the second terminal lands: a
    live conductor (converges) or a dead stub (opens). A gap construction
    always needs metal on both sides, which is precisely what a conductor
    END does not have."""
    z_ref = _subst_zin(_ElementFedDoublet)
    assert z_ref.real > 100.0  # the end port genuinely couples

    r_vals = []
    for nub in (1.0, 0.3, 0.1, 0.03, 0.01):
        z = _subst_zin(_NubFedDoublet, nub=nub)
        r_vals.append(z.real)
        # never approaches the end-port answer, at any stub size
        assert abs(z - z_ref) / abs(z_ref) > 0.5, (nub, z, z_ref)
    # ...and the coupling collapses as the stub shrinks: the port opens
    assert r_vals[0] > 1.0
    assert r_vals[-1] < 0.1


# ---------------------------------------------------------------------------
# 9. The shipped centre-port construction, on the same oracle
# ---------------------------------------------------------------------------
#
# `wire.doublet_balanced_tuner` feeds a single wire through a
# `PortOnWireFloating` at its centre: an ideal TL plus an ideal delta gap, with
# no bridge and no second length scale. Section 6 bounded `PortAtEnd`'s
# idealization error against a physical feeder; this does the same for the
# construction actually shipped.
#
# NOTE on what this does and does not prove. Agreement with a physical-wire
# feeder BOUNDS the idealization error — it is not the definition of
# correctness, because the model is an idealization by construction and the
# physical build is a different model. The model's own criterion is
# convergence under refinement, which both engines satisfy (bare wire,
# N = 21 -> 641: momwire 344.3 -> 383.4 + j1010.0, PyNEC 328.3 -> 382.1 +
# j1008.6, steps halving per doubling, 0.4% apart at the end).


class _CentrePortDoublet(_ElementFedDoublet):
    """One wire, floating port at its centre — the shipped construction."""

    def build_wires(self):
        arm, L = self.arm_factor * WL, self.feed_len_wl * WL
        return self.auto_mesh([Wire((-arm, 0.0, L), (arm, 0.0, L), name="feed")])

    def build_network(self):
        s, L = self.spacing, self.feed_len_wl * WL
        return Network(
            ports={
                "feed": PortOnWireFloating("feed"),
                "rig": PortVirtual("rig"),
                "bL": PortVirtual("bL"),
                "bR": PortVirtual("bR"),
            },
            branches=[
                FloatingBalun(primary="rig", a="bL", b="bR", n=1.0),
                BalancedLine(
                    a1="bL",
                    a2="bR",
                    b1="feed.p",
                    b2="feed.n",
                    zdiff=analytic_zdiff(s),
                    length=L,
                    vf=1.0,
                    zcomm=self.zcomm,
                ),
            ],
            sources=[Driven(port="rig")],
        )


@pytest.mark.antenna_computation_check
def test_centre_port_construction_tracks_a_physical_feeder():
    """Idealization error of the shipped construction, measured 2026-07-29:

        feeder   physical           centre port         dev    (PortAtEnd)
        0.20 λ   1158.2 +1615.8j    1097.5 +1595.0j    3.2 %      4.3 %
        0.30 λ    445.2 -1075.6j     460.5 -1094.0j    2.1 %      2.9 %
        0.45 λ     82.6  -118.4j      82.8  -120.3j    1.3 %      2.4 %

    A few percent is the expected gap between an ideal delta-gap feed and a
    real two-wire attachment, and it is the bound worth pinning. It also beats
    the `PortAtEnd` authoring at every length — but that is a secondary
    observation, not the reason to prefer it; portability and the absence of a
    second length scale are."""
    for flw in (0.20, 0.30, 0.45):
        zp = _subst_zin(_PhysFedDoublet, feed_len_wl=flw)
        dev = abs(_subst_zin(_CentrePortDoublet, feed_len_wl=flw) - zp) / abs(zp)
        assert dev < 0.05, (flw, dev)


# ---------------------------------------------------------------------------
# 8. The junction-port network on a second formulation (momwire#182 M5b)
# ---------------------------------------------------------------------------
#
# Everything above rides `PortAtEnd` -> momwire junction ports, which until
# momwire#182 only `BSplineSolver` implemented. A single implementation of a
# port model is a single point of failure for the whole `sterba_bl` result:
# the design's physics rests on 16 one-terminal node ports whose only oracle
# is the all-wire `wire.sterba`, and a shared bug in the port algebra would
# reproduce itself in every test in this file.
#
# `SinusoidalGalerkinSolver` is now an independent second implementation --
# different basis (NEC's three-term vs quadratic B-spline), different testing
# quadrature, and a completely different port derivation (the node's lumped
# charge removed from a FIELD-based reaction integral, vs a Lagrange
# multiplier on a KCL row in a MIXED-POTENTIAL formulation). Agreement
# between them is therefore evidence about the port MODEL, not about one
# implementation's self-consistency.
#
# FREE SPACE ONLY, stated openly: momwire#182 M5b scoped junction ports over
# any ground out (the node-charge IMAGE is not removed yet, so part of the M5
# blocker would survive), and the solver refuses rather than approximating.
# Section 5's average-ground test therefore has no sinusoidal-Galerkin column;
# `test_catalog_curtain_on_sin_galerkin_refuses_a_ground` pins the refusal so
# the omission cannot be mistaken for an oversight.


def _sin_galerkin_curtain(n_cells, **overrides):
    from momwire import SinusoidalGalerkinSolver

    return MomwireEngine(
        _catalog_curtain(n_cells, **overrides),
        solver=SinusoidalGalerkinSolver,
        ground=None,
    )


@pytest.mark.antenna_computation_check
def test_catalog_curtain_matches_on_the_sinusoidal_galerkin_basis():
    """wire.sterba_bl's 16-port junction-port network, solved twice on two
    formulations that share no basis, no testing and no port algebra.

    Both the driving-point impedance and the radiated pattern must agree --
    Z is the port network's own readout, gain is what the resulting current
    distribution does, and a port-model error that cancelled in one would
    still show in the other.

    Measured 2026-07-30, free space, catalog default n_cells=3:

        bspline d=2           Z = 673.293 + 385.592j   10.606 dBi  az 180
        sinusoidal-Galerkin   Z = 672.055 + 387.371j   10.605 dBi  az 180

    i.e. 0.28 % in |Z| and 0.001 dB in peak gain. The bounds below are set an
    order of magnitude looser than the measurement (2 % / 0.15 dB) because
    this is a cross-FORMULATION check, not a pin: the two schemes' ordinary
    discretization error does not have to agree to three digits, and only a
    port-model discrepancy would be large enough to trip these.
    """
    # One engine per formulation, reused for both readouts (the far field
    # rides the same cached solve, so this costs one solve each).
    e_ref = MomwireEngine(_catalog_curtain(3), ground=None)  # BSplineSolver
    e_sg = _sin_galerkin_curtain(3)
    z_ref, z_sg = e_ref.impedance()[0], e_sg.impedance()[0]
    assert abs(z_sg - z_ref) / abs(z_ref) < 0.02, (z_ref, z_sg)

    gain_ref, az_ref = _peak(e_ref)
    gain_sg, az_sg = _peak(e_sg)
    assert abs(gain_sg - gain_ref) < 0.15, (gain_ref, gain_sg)
    for az in (az_ref, az_sg):
        assert min(az % 180.0, 180.0 - az % 180.0) <= 10.0


@pytest.mark.antenna_computation_check
def test_sin_galerkin_curtain_still_needs_the_common_mode_path():
    """The section-5 finding, re-derived on the independent formulation.

    `zcomm` is the file's most load-bearing claim -- the CM path is what
    makes a 4-terminal element stand in for a pair of conductors that closes
    a conduction loop -- and it is a claim about the PORT boundary condition,
    exactly what a second port implementation is able to falsify. Removing
    the CM path must cost several dB and swing the beam off broadside here
    too. Measured 2026-07-30: 10.605 dBi az 180 with, 5.518 dBi az 35
    without -- against the B-spline solver's own 10.606 / 5.519 on the same
    pair of builds.
    """
    gain_on, az_on = _peak(_sin_galerkin_curtain(3))
    gain_off, az_off = _peak(_sin_galerkin_curtain(3, zcomm=0.0))
    assert min(az_on % 180.0, 180.0 - az_on % 180.0) <= 10.0
    assert gain_on - gain_off > 3.0, (gain_on, gain_off)
    assert min(az_off % 180.0, 180.0 - az_off % 180.0) > 20.0


def test_catalog_curtain_on_sin_galerkin_refuses_a_ground():
    """Junction ports over a ground are REFUSED on the sinusoidal-Galerkin
    solver, not approximated (momwire#182 M5b scoped them out: the node
    charge's ground IMAGE is still in the kernel). Pinned so that section 5's
    missing sinusoidal-Galerkin column reads as a scope boundary rather than
    an untested path -- and so a future momwire that lifts the restriction
    fails here loudly instead of silently changing what this file covers."""
    with pytest.raises(NotImplementedError, match="junction_ports over a ground"):
        MomwireEngine(
            _catalog_curtain(1),
            solver=__import__("momwire").SinusoidalGalerkinSolver,
            ground=AVG_GROUND,
        ).impedance()

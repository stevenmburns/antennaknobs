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

The end-to-end BalancedLine-riser Sterba is NOT here: issue #576's
validation found the blocker is attachment semantics (a `PortOnWire` gap
cannot faithfully attach a floating element at a conductor END), not the
element or its premise — see the issue thread for the evidence trail.
"""

import math
from types import MappingProxyType

import numpy as np
import pytest

from antennaknobs import AntennaBuilder
from antennaknobs.network import Driven, Network, PortOnWire, Wire
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

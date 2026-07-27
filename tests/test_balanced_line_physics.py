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


# ---------------------------------------------------------------------------
# 4. End-to-end: a one-bay BL-riser curtain reproduces wire.sterba — with zcomm
# ---------------------------------------------------------------------------


class _MiniSterbaTL(AntennaBuilder):
    """One Sterba bay (n_cells = 1) with wire.sterba's exact radiator layout —
    two interleaved conductors, sections λ/4 + λ/2 + λ/4, physical
    single-conductor end closures — and each interior riser pair replaced by
    a BalancedLine across four `PortAtEnd` junction ports, wired by physical
    conductor pairing (port A = the two top-rail ends, conductor 1 = the
    A-conductor riser). The scratchpad `sterba_bl.py` riser="end" builder,
    specialised to one bay."""

    default_params = MappingProxyType(
        {
            "design_freq": FREQ,
            "freq": FREQ,
            "base": 7.0,
            "spacing": 0.04,
            "zcomm": 200.0,
            "k1": 0.02,  # real open-wire loss regularises the λ/2 stamp
            "end_corr": 0.030,  # measured pair end-effect elongation (m)
        }
    )

    def _layout(self):
        h = 0.5 * WL
        q = 0.5 * h
        yb = [0.0, q, q + h, 2 * q + h]
        return h, yb

    def _lvl(self, i, cond):
        h, _ = self._layout()
        a_top = i % 2 == 0
        top, bot = self.base + h, self.base
        if cond == "A":
            return top if a_top else bot
        return bot if a_top else top

    def build_wires(self):
        h, yb = self._layout()
        s, pe = self.spacing, 0.2
        tups = []
        for cond, x in (("A", 0.0), ("B", s)):
            for i in range(3):
                z = self._lvl(i, cond)
                y0, y1 = yb[i], yb[i + 1]
                la = f"{cond}{i}a" if i > 0 else None
                lb = f"{cond}{i}b" if i < 2 else None
                if cond == "A" and i == 1:  # feed span (bottom-rail conductor)
                    yc = 0.5 * (y0 + y1)
                    tups.append(Wire((x, y0, z), (x, yc - 0.5 * pe, z), name=la))
                    tups.append(
                        Wire(
                            (x, yc - 0.5 * pe, z), (x, yc + 0.5 * pe, z), name="feed"
                        )  # fmt: skip
                    )
                    tups.append(Wire((x, yc + 0.5 * pe, z), (x, y1, z), name=lb))
                else:
                    ym = 0.5 * (y0 + y1)
                    tups.append(Wire((x, y0, z), (x, ym, z), name=la))
                    tups.append(Wire((x, ym, z), (x, y1, z), name=lb))
        tups.append(Wire((0.0, 0.0, self._lvl(0, "A")), (s, 0.0, self._lvl(0, "B"))))
        yl = yb[-1]
        tups.append(Wire((0.0, yl, self._lvl(2, "A")), (s, yl, self._lvl(2, "B"))))
        return tups

    def build_network(self):
        from antennaknobs.network import BalancedLine, PortAtEnd

        h, _ = self._layout()
        zd = analytic_zdiff(self.spacing)
        ports = {"feed": PortOnWire("feed", distributed=True)}
        branches = []
        top = self.base + h
        for k in (1, 2):
            i = k - 1
            pa, pa2 = f"eA{k}", f"eA{k}n"
            pb, pb2 = f"eB{k}", f"eB{k}n"
            ports[pa] = PortAtEnd(f"A{i}b", end="p1")
            ports[pa2] = PortAtEnd(f"A{k}a", end="p0")
            ports[pb] = PortAtEnd(f"B{i}b", end="p1")
            ports[pb2] = PortAtEnd(f"B{k}a", end="p0")
            a_top = self._lvl(i, "A") == top
            a1, b1 = (pa, pa2) if a_top else (pa2, pa)
            a2, b2 = (pb2, pb) if a_top else (pb, pb2)
            branches.append(
                BalancedLine(
                    a1=a1,
                    a2=a2,
                    b1=b1,
                    b2=b2,
                    zdiff=zd,
                    length=h + self.end_corr,
                    k1=self.k1,
                    zcomm=self.zcomm,
                )  # fmt: skip
            )
        return Network(
            ports=ports,
            branches=branches,
            sources=[Driven(port="feed", voltage=1 + 0j)],
        )


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
    import importlib

    ster = importlib.import_module("antennaknobs.designs.wire.sterba").Builder
    bp = ster(dict(ster.default_params, n_cells=1))
    gain_phys, az_phys = _peak(MomwireEngine(bp, ground=None))
    assert min(az_phys % 180.0, 180.0 - az_phys % 180.0) <= 10.0  # broadside

    b100 = _MiniSterbaTL(dict(_MiniSterbaTL.default_params, zcomm=100.0))
    gain_100, az_100 = _peak(MomwireEngine(b100, ground=None))
    assert min(az_100 % 180.0, 180.0 - az_100 % 180.0) <= 10.0
    assert abs(gain_100 - gain_phys) < 0.5

    b400 = _MiniSterbaTL(dict(_MiniSterbaTL.default_params, zcomm=400.0))
    gain_400, _az = _peak(MomwireEngine(b400, ground=None))
    assert abs(gain_400 - gain_100) < 0.1  # λ/2 repeater: zcomm-insensitive

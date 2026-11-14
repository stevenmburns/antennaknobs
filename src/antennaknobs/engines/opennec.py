"""OpenNEC through pyopennec's port-admittance interface, `pyopennec.porty`.

pyopennec (https://github.com/stevenmburns/pyopennec) wraps OpenNEC, a C
rewrite of NEC-2 / nec2c. Its `porty` module solves a structure (straight
wires, LD 0-5 loads, a ground, the kernel) ONCE per frequency for the
short-circuit admittance ``Y`` at a set of segment ports, ``I = Y @ V``, and
the segment currents each port drives; fields for any port voltages are then
superposition, with no re-solve. Every circuit is this engine's, on ``Y``.
The PyNEC-shaped pybind module (``pyopennec.nec_context``) is never touched.

The model is `PyNECEngine`'s: the same wires in their authored p0->p1
direction (so the port sign convention of issue #580 holds), the same LD
cards for wire material and for a Load-only network, the same ground, kernel
and refusals. The engine records those cards (`_CardDeck`) instead of handing
them to a binding, and builds one `porty.Structure` from them:

* the multiport-Y route (a line, a virtual port, a two-port, a distributed
  port, ...): a porty port on EVERY segment a real network port drives, and
  ``Y_port = W^T Y_seg W`` with ``W[a, j]`` the weight port j drives segment a
  with — 1 on a delta gap, the length split on a distributed port. That is
  the contraction `PyNECEngine._compute_y_matrix` makes with one NEC run per
  port: it drives segment b of port j at ``w_b`` volts and reads port i as
  ``sum_a w_a I_a``. The shared `NetworkReducer` then stamps the network.
* the card route (plain feeds, a Load-only network, ``native_nt``): a porty
  port on each EX segment and each NT end; the loads stay LD cards. An NT
  card is its short-circuit admittance stamped onto ``Y`` at its two ports,
  where NEC adds the network current to the segment's (nec2c network.c): at
  a source ``I_source = I_seg + I_net``, at an undriven NT port
  ``I_seg + I_net = 0``. With no NT card that is just ``I = Y @ V``.

One `porty.Structure.solve` call per set of frequencies, cached on the engine
by frequency: `impedance`, `current_distribution` and `far_field` on one
build share one solve, and an N-point `impedance_sweep` is one solve over its
N frequencies (``solve_log`` records each call's frequencies). The pybind
engine made one NEC run per port per reading on the multiport route.

Gains are porty's NEC power gain, normalised by the power the port voltages
deliver to the structure, then shifted per SOURCE watt (AK#1637) wherever a
network sits between the sources and the ports.

What porty cannot express refuses by name: a legacy `build_tls()` line (NEC's
TL card; the network spec serves lines), and the pattern over the
MININEC-type ground, whose soil enters only a cliff-mode RP (porty's far
field reads the solve's own ground). Its impedance and currents, which are
the perfect ground's by definition, are served. A wire below or in the
ground plane refuses as on the NEC-2 lane (`refuse_nec2_geometry`). OpenNEC makes no
intersection check, so ``check_intersections`` changes nothing, and
nec2++'s Sommerfeld defect (#448) is not OpenNEC's.

pyopennec is MIT, like antennaknobs, but it is not on PyPI yet, so it stays an
OPTIONAL import: absent, the engine still records its cards (the deck writer
never needed it) and a solve raises an ImportError naming the package.
"""

from __future__ import annotations

import numpy as np

try:
    from pyopennec import porty
except ImportError:  # optional; built from source (see OPENNEC_MISSING)
    porty = None

from ..engine import FarField
from ..network import Load, load_impedance
from ..network_reduce import C_LIGHT, poison_singular_sample
from .nec2 import refuse_nec2_geometry
from .pynec import PyNECEngine

OPENNEC_MISSING = (
    "pyopennec is not installed: the opennec engine cannot solve without it. "
    "It is not on PyPI yet; build it from source with `pip install "
    "git+https://github.com/stevenmburns/pyopennec` (MIT; needs a C compiler, "
    "CMake and, optionally, OpenBLAS), or solve with momwire."
)

# NEC's RP marks a direction it has no value for (below the horizon over a
# ground) with this; a gain shift leaves it alone.
_NULL_GAIN_DB = -999.99


def _freq_key(freq_mhz):
    """The cache key for a frequency. Twelve significant figures: a reading
    reaches a frequency through ``C / (C / f)``, which can move the last bit."""
    return float(f"{float(freq_mhz):.12g}")


class _CardDeck:
    """Stands in for a NEC context: records the cards `PyNECEngine` emits
    (geometry, LD, GN/GD, EX, NT, EK) for `porty.Structure`, and refuses by
    name, at construction, any card porty has no spelling for."""

    def __init__(self, label):
        self._label = label
        self.wires = []
        self.loads = []
        self.ex = []
        self.nt = []
        self.gn = None
        self.gd = None
        self.gpflag = 0
        self.ek = False

    def _refuse(self, what):
        raise NotImplementedError(
            f"{self._label} solves through pyopennec's porty interface, which "
            f"has no {what}"
        )

    def get_geometry(self):
        return self

    def set_intersection_check(self, _on):
        """OpenNEC makes no intersection check to turn off."""

    def wire(self, tag, nseg, x1, y1, z1, x2, y2, z2, radius, rdel, rrad):
        if rdel != 1.0 or rrad != 1.0:
            self._refuse("tapered GW card (segment-length or radius ratio)")
        self.wires.append((int(tag), int(nseg), (x1, y1, z1), (x2, y2, z2), radius))

    def geometry_complete(self, gpflag):
        self.gpflag = int(gpflag)

    def set_extended_thin_wire_kernel(self, on):
        self.ek = bool(on)

    def ld_card(self, ldtyp, tag, seg_from, seg_to, f1, f2, f3):
        self.loads.append(
            (int(ldtyp), int(tag), int(seg_from), int(seg_to), f1, f2, f3)
        )

    def gn_card(self, iperf, nradl, eps_r, sigma, *_rest):
        if nradl:
            self._refuse("radial ground screen (GN NRADL)")
        self.gn = (int(iperf), float(eps_r), float(sigma))

    def gd_card(self, eps_r, sigma, cliff_dist, cliff_height):
        self.gd = (float(eps_r), float(sigma), float(cliff_dist), float(cliff_height))

    def ex_card(self, extype, tag, seg, _i4, v_re, v_im, *_rest):
        if extype != 0:
            self._refuse(f"EX {extype} (only applied-field voltage sources)")
        self.ex.append((int(tag), int(seg), complex(v_re, v_im)))

    def nt_card(self, tag_a, seg_a, tag_b, seg_b, y11r, y11i, y12r, y12i, y22r, y22i):
        self.nt.append(
            (
                (int(tag_a), int(seg_a)),
                (int(tag_b), int(seg_b)),
                complex(y11r, y11i),
                complex(y12r, y12i),
                complex(y22r, y22i),
            )
        )

    def tl_card(self, *_args):
        self._refuse(
            "TL card: a legacy build_tls() line is not served; spell the line "
            "in build_network(), where the shared reducer stamps it"
        )

    def porty_ground(self):
        """The GN card as porty's ground spec (GN 1 perfect, GN 2 Sommerfeld,
        GN 0 reflection coefficient); None for free space."""
        if self.gn is None:
            return None
        iperf, eps_r, sigma = self.gn
        if iperf == 1:
            return "perfect"
        if iperf == 2:
            return ("sommerfeld", eps_r, sigma)
        if iperf == 0:
            return ("reflection", eps_r, sigma)
        return self._refuse(f"GN {iperf}")


class _SegmentCurrents:
    """porty's segment currents behind the two getters `PyNECEngine`'s loss
    and port readers take from a NEC structure-currents object."""

    def __init__(self, tags, currents):
        self._tags, self._cur = tags, currents

    def get_current_segment_tag(self):
        return self._tags

    def get_current(self):
        return self._cur


class OpenNECEngine(PyNECEngine):
    """OpenNEC (NEC-2) through pyopennec's porty, with PyNECEngine's model.

    On the same deck it agrees with PyNEC to ~1e-3 on Z: both are NEC-2's
    formulation, and nec2++ itself differs from nec2c by ~2e-4.
    tests/test_opennec_parity.py holds the two engines together over the
    catalog, and tests/test_opennec_porty_parity.py holds this engine to the
    pybind-route OpenNECEngine it replaced.
    """

    engine_label = "OpenNEC"
    warns_somm_low_wires = False

    def __init__(self, builder, **kwargs):
        # Set before PyNECEngine's constructor, which may already ask for Y
        # (a self-tuning tuner is tuned from the engine's own admittance).
        self._porty_structure = None
        self._solutions = {}
        # One entry per porty solve() call: the frequencies (MHz) it solved.
        self.solve_log: list[tuple[float, ...]] = []
        # ``fill_reuse`` is pynec-accel's; porty has no fill choice.
        kwargs.pop("fill_reuse", None)
        super().__init__(builder, **kwargs)
        # NEC-2's ground has no below-ground medium (the NEC-2 lane's rule,
        # antennaknobs#1389). porty sets the ground-plane flag (GE 1) with
        # every ground, so OpenNEC would refuse the deck anyway, but in its
        # own words; under the pybind route's GE 0 it solved one as if in air.
        refuse_nec2_geometry(self.tups, self.ground)

    @staticmethod
    def nec_module():
        """The porty module this engine solves through, or None when
        pyopennec is not installed. Read at call time."""
        return porty

    def _make_context(self):
        return _CardDeck(f"the {self.engine_label} engine")

    # ----- the structure and its solves -----

    def _port_layout(self):
        """``(deck, segments, W)``: the recorded cards, the porty ports as
        (tag, seg), and the weights mapping the engine's own ports onto them.

        Multiport route: a row per segment any real network port drives, a
        column per real port (Y's order, `_real_port_names`). Card route: the
        EX segments in `excitation_pairs` order, then each NT end not
        already a source; W is the identity there."""
        if self._use_reducer:
            deck, loc = self._make_real_context()
            segs, rows, cols = [], {}, []
            for name in self._real_port_names:
                tag = loc[self._port_wire_of[name]][0]
                col = []
                for seg, w in self._port_drive_points[name]:
                    if (tag, seg) not in rows:
                        rows[(tag, seg)] = len(segs)
                        segs.append((tag, seg))
                    col.append((rows[(tag, seg)], w))
                cols.append(col)
            W = np.zeros((len(segs), len(cols)))
            for j, col in enumerate(cols):
                for a, w in col:
                    W[a, j] += w
            return deck, segs, W
        deck = self.c
        segs = []
        for tag, seg, _v in deck.ex:
            if (tag, seg) in segs:
                raise ValueError(
                    f"two sources on tag {tag} segment {seg}: NEC's EX cards "
                    "would superpose there, which this engine does not model"
                )
            segs.append((tag, seg))
        for a, b, *_y in deck.nt:
            for end in (a, b):
                if end not in segs:
                    segs.append(end)
        return deck, segs, np.eye(len(segs))

    def _structure(self):
        if porty is None:
            raise ImportError(OPENNEC_MISSING)
        if self._porty_structure is None:
            deck, segs, W = self._port_layout()
            if not segs:
                raise ValueError(
                    f"{self.engine_label}: the design drives no segment, so "
                    "there is nothing to solve"
                )
            self._deck, self._port_segs, self._W = deck, segs, W
            self._port_index = {s: i for i, s in enumerate(segs)}
            self._porty_structure = porty.Structure(
                deck.wires,
                ports=segs,
                ground=deck.porty_ground(),
                loads=deck.loads,
                extended_kernel=deck.ek,
            )
        return self._porty_structure

    def _prefetch(self, freqs_mhz):
        """Solve every frequency in `freqs_mhz` not solved yet, in ONE porty
        solve() call."""
        st = self._structure()
        todo = []
        for f in freqs_mhz:
            k = _freq_key(f)
            if k not in self._solutions and k not in todo:
                todo.append(k)
        if not todo:
            return
        sol = st.solve(todo)
        self.solve_log.append(tuple(todo))
        for i, k in enumerate(todo):
            self._solutions[k] = (sol, i)

    def _solution(self, freq_mhz):
        """``(Solution, frequency index)`` at `freq_mhz`."""
        self._prefetch([freq_mhz])
        return self._solutions[_freq_key(freq_mhz)]

    def _compute_y_matrix(self, wavelength):
        """The short-circuit Y at the real network ports (`_real_port_names`
        order), ``W^T Y_seg W`` from the cached solve."""
        sol, i = self._solution(C_LIGHT / wavelength / 1e6)
        return self._W.T @ sol.y[i] @ self._W

    # ----- the card route: EX sources, LD loads, NT stamps -----

    def _nt_stamp(self):
        """The NT cards' short-circuit admittances on the porty ports. An NT
        card's values are fixed (the native-nt oracle stamps them at the
        design frequency), so this is frequency independent."""
        n = len(self._port_segs)
        Y = np.zeros((n, n), dtype=np.complex128)
        for a, b, y11, y12, y22 in self._deck.nt:
            ia, ib = self._port_index[a], self._port_index[b]
            Y[ia, ia] += y11
            Y[ia, ib] += y12
            Y[ib, ia] += y12
            Y[ib, ib] += y22
        return Y

    def _card_state(self, freq_mhz):
        """``(sol, i, V, I_source)`` on the card route: every porty port's
        voltage and each source's current, NT network included."""
        sol, i = self._solution(freq_mhz)
        n_src = len(self._deck.ex)
        v_src = np.array([v for _t, _s, v in self._deck.ex], dtype=np.complex128)
        Y = sol.y[i]
        if self._deck.nt:
            Y = Y + self._nt_stamp()
        V = np.zeros(len(self._port_segs), dtype=np.complex128)
        V[:n_src] = v_src
        if len(V) > n_src:
            # The undriven NT ports: I_seg + I_net = 0.
            V[n_src:] = np.linalg.solve(Y[n_src:, n_src:], -Y[n_src:, :n_src] @ v_src)
        return sol, i, V, (Y @ V)[:n_src]

    @staticmethod
    def _source_power(V, I_src):
        v = V[: len(I_src)]
        return float(0.5 * np.real(np.sum(v * np.conj(I_src))))

    # ----- the network-resolved drive on either route -----

    def _excited(self, freq_mhz):
        """``(sol, i, v_ports, p_source)``: the porty-port voltages a reading
        superposes, and the power the SOURCES deliver where a network stands
        between them and the structure — None where the structure's input
        power is the sources' (the card route without NT)."""
        if self._use_reducer:
            sol, i = self._solution(freq_mhz)
            wl = C_LIGHT / (float(freq_mhz) * 1e6)
            Y = self._compute_y_matrix(wl)
            V = self._reducer.resolve_voltages(self._reducer.apply_branches(Y, wl))
            n = len(self._real_port_names)
            p_source = float(self._reducer.excited_state(Y, wl)[2])
            return sol, i, self._W @ np.asarray(V[:n], complex), p_source
        sol, i, V, I_src = self._card_state(freq_mhz)
        p_source = self._source_power(V, I_src) if self._deck.nt else None
        return sol, i, V, p_source

    # ----- readings -----

    def _card_impedances(self, freq_mhz, sum_currents):
        _sol, _i, V, I_src = self._card_state(freq_mhz)
        zs = [complex(v / c) for v, c in zip(V[: len(I_src)], I_src, strict=True)]
        if sum_currents:
            zs = [1 / sum(1 / z for z in zs)]
        return zs

    def impedance(self, sum_currents=False):
        self._refuse_export_only()
        f = self.builder.freq
        if self._use_reducer:
            wl = C_LIGHT / (f * 1e6)
            return self._reducer.driven_impedance(self._compute_y_matrix(wl), wl)
        return self._card_impedances(f, sum_currents)

    def impedance_sweep(self, freqs, sum_currents=False):
        """One porty solve over every frequency, then each one's reduction.
        The frequencies need not be evenly spaced (there is no FR card)."""
        self._refuse_export_only()
        freqs = np.asarray(freqs, dtype=float)
        if freqs.ndim != 1 or freqs.size == 0:
            raise ValueError("freqs must be a 1-D non-empty array")
        self._prefetch(freqs)
        if self._use_reducer:
            zs = np.empty((freqs.size, self._reducer.n_driven), dtype=np.complex128)
            for k, f in enumerate(freqs):
                wl = C_LIGHT / (float(f) * 1e6)
                # One singular sample must not cost the sweep (issue #647).
                z = poison_singular_sample(
                    self._reducer.driven_impedance,
                    self._compute_y_matrix(wl),
                    wl,
                    where=f" at {f:.6g} MHz",
                )
                zs[k] = np.nan if z is None else z
            return zs
        return np.array([self._card_impedances(f, sum_currents) for f in freqs])

    def _radiation_efficiency(self, sc, wavelength):
        """`PyNECEngine._radiation_efficiency` with the card route's source
        power from this engine's own solve instead of NEC's ANTENNA INPUT
        PARAMETERS. The multiport route is PyNEC's unchanged."""
        if self._use_reducer:
            return super()._radiation_efficiency(sc, wavelength)
        _sol, _i, V, I_src = self._card_state(C_LIGHT / wavelength / 1e6)
        p_in = self._source_power(V, I_src)
        omega = 2.0 * np.pi * C_LIGHT / wavelength
        loads = (
            [b for b in self._network.branches if isinstance(b, Load)]
            if self._network is not None
            else []
        )
        budget, p_diss = [], 0.0
        for br in loads:
            tag, seg = self._network_port_loc[br.port]
            cur = self._port_current(sc, tag, seg)
            w = 0.5 * load_impedance(br, omega).real * abs(cur) ** 2
            budget.append((f"Load {br.port}", w))
            p_diss += w
        p_wire = self._wire_loss_from_currents(sc, wavelength)
        if p_wire > 0.0:
            budget.append(("wire loss (I²R)", p_wire))
            p_diss += p_wire
        if not budget or p_in <= 0.0:
            return 1.0, p_in, []
        return max(0.0, min(1.0, 1.0 - p_diss / p_in)), p_in, budget

    def current_distribution(self):
        self._refuse_export_only()
        f = self.builder.freq
        sol, i, v, _p = self._excited(f)
        sc = _SegmentCurrents(sol.segments.tags, sol.currents(i, v))
        (
            self._excited_efficiency,
            self._excited_p_in,
            self._excited_power_budget,
        ) = self._radiation_efficiency(sc, C_LIGHT / (f * 1e6))
        return self._knot_currents(list(sc.get_current_segment_tag()), sc.get_current())

    def gain_grid_dbi(self, thetas_deg, phis_deg, freq_mhz=None):
        """``(gain, valid)``: NEC's total power gain (dBi) per SOURCE watt on
        the grid ``thetas_deg x phis_deg`` (zenith angle, azimuth) from the
        cached solve, at the builder's frequency unless `freq_mhz` says.
        ``valid`` is False below the horizon over a ground, where the gain
        reads -999.99 as NEC's RP does."""
        self._refuse_export_only()
        f = self.builder.freq if freq_mhz is None else float(freq_mhz)
        sol, i, v, p_source = self._excited(f)
        if self._deck.gd is not None:
            raise NotImplementedError(
                f"{self.engine_label} cannot read a pattern over the MININEC-type "
                "ground: its soil enters NEC-2 only through a cliff-mode RP (the "
                "GD card), and pyopennec's porty far field reads the solve's own "
                "perfect ground. Impedance and currents are served; for the "
                "pattern use the PyNEC, NEC-2 or momwire engine."
            )
        th, ph = np.meshgrid(
            np.asarray(thetas_deg, float), np.asarray(phis_deg, float), indexing="ij"
        )
        ff = porty.far_field(sol, i, v, th, ph)
        g = np.asarray(ff.gain_total, float)
        if p_source is not None:
            # Per SOURCE watt (AK#1637): porty normalises by the structure's.
            if p_source <= 0.0 or ff.power_in <= 0.0:
                raise ValueError(
                    f"cannot normalise the pattern per source watt: structure "
                    f"input {ff.power_in} W, source power {p_source} W"
                )
            shift_db = 10.0 * np.log10(ff.power_in / p_source)
            g = np.where(g <= _NULL_GAIN_DB, g, g + shift_db)
        return g, np.asarray(ff.valid, bool)

    def far_field(self, *, n_theta=90, n_phi=360, del_theta=1, del_phi=1):
        assert 90 % n_theta == 0 and 90 == del_theta * n_theta
        assert 360 % n_phi == 0 and 360 == del_phi * n_phi
        thetas = np.linspace(0, 90 - del_theta, n_theta)
        phis = np.linspace(0, 360, n_phi + 1)
        g, valid = self.gain_grid_dbi(thetas, phis)
        # The pybind binding's get_gain_max/min: over the points RP computed.
        lit = g[valid]
        return FarField(
            rings=g.tolist(),
            max_gain=float(lit.max()) if lit.size else _NULL_GAIN_DB,
            min_gain=float(lit.min()) if lit.size else _NULL_GAIN_DB,
            thetas=thetas,
            phis=phis,
        )

    def _excited_for_pattern(self, *_args, **_kwargs):
        """The pybind route's pattern seams. Nothing here solves a context, so
        a caller still reaching for one is told where the pattern is."""
        raise NotImplementedError(
            f"{self.engine_label} has no NEC context to excite; read the pattern "
            "with far_field() or gain_grid_dbi()"
        )

    _excited_real_context = _excited_for_pattern

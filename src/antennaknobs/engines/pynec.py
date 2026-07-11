import numpy as np
import PyNEC as nec

from ..engine import FarField, SimulationEngine, WireCurrents
from ..network import (
    Driven,
    Load,
    PortAtEdge,
    PortVirtual,
    TL,
    load_impedance,
)
from ..network_reduce import C_LIGHT, NetworkReducer

WIRE_RADIUS = 0.0005
COPPER_CONDUCTIVITY = 5.8e7

# Conductivity (S/m) of the wire-loss ld_card, or None for PERFECT conductors.
# Default None = PEC, matching momwire's lossless-wire model. This is what makes
# PyNEC a clean cross-engine reference: with copper loss off, PyNEC and momwire's
# sinusoidal basis (the same NEC2 basis family) agree on impedance to ~0.1 Ω
# and on gain/efficiency to ~0.1 dB. Set to COPPER_CONDUCTIVITY to model real
# copper loss instead (a few tenths of a dB on a resonant antenna; more on a
# high-current structure), at the cost of that clean agreement.
WIRE_CONDUCTIVITY = None


DEFAULT_GROUND = ("finite", 10.0, 0.002)  # (kind, dielectric, conductivity)


class PyNECEngine(SimulationEngine):
    supports_far_field = True
    # NEC's source placement uses (n_seg+1)//2, which lands on the centre
    # segment for odd n_seg. Even counts get bumped up so the feed sits
    # at a true wire midpoint instead of off-centre.
    segment_parity = "odd"

    def __init__(self, builder, *, ground=DEFAULT_GROUND):
        """
        ground:
          None or "free"                 — no gn_card (free space)
          "pec"                          — perfectly conducting ground
          ("finite", eps_r, sigma)       — Sommerfeld-Norton finite ground
                                           (default, matches the historical
                                           hard-coded eps_r=10, sigma=0.002)
          ("finite-fast", eps_r, sigma)  — finite ground via NEC's reflection-
                                           coefficient approximation. Much
                                           cheaper than Sommerfeld and within
                                           ~0.1 dB / a few Ω of it for wires
                                           ≳0.2λ above ground, but impedance
                                           drifts by 10+ Ω below ~0.1λ.
        """
        super().__init__(builder)
        self.tups = self._coerce_wire_tuples(builder.build_wires())
        self._network = builder.build_network()
        # build_tls() is only consulted when there's no Network spec; with a
        # Network, the engine drives ex_card/tl_card calls off the spec instead.
        self.tls = [] if self._network is not None else builder.build_tls()
        self.ground = ground
        self.excitation_pairs = None
        # Fraction of input power radiated; set by current_distribution() when
        # the design carries resistive loads (e.g. a terminated rhombic). The
        # web far-field normaliser reads it to plot GAIN, matching momwire and
        # NEC's own get_gain so engine-switching keeps the pattern meaning
        # the same thing. 1.0 = no resistive loss.
        self._excited_efficiency = 1.0
        # Source input power 1/2·Re(Σ V·I*) in watts from the same solve; the
        # web gain normaliser is η₀k²/(8π·P_in). None until a solve runs.
        self._excited_p_in = None
        # Loads alone are handled natively (ld_card) and accurately by NEC, so
        # only divert to the multiport-Y + NetworkReducer path for what NEC
        # *can't* do natively: transmission lines (TL) and virtual
        # drivers. Those skip the baked NEC context entirely — impedance uses
        # per-port solves and far-field/current build an excitation-resolved
        # context on demand. Load-only and plain designs keep the native path.
        self._use_reducer = self._network is not None and self._network_uses_reducer()
        if self._use_reducer:
            self._init_network()
        else:
            self._build_geometry()

    def __del__(self):
        # Release the nec_context handle if construction got that far.
        c = getattr(self, "c", None)
        if c is not None:
            del self.c

    def _build_geometry(self):
        self.c = nec.nec_context()
        geo = self.c.get_geometry()

        # Walk build_wires(): emit `geo.wire` cards, collect ex_card pairs from
        # any tuple with a non-None `ev`, and remember (tag, mid_seg) for every
        # named edge so the network path can resolve PortAtEdge later.
        self.excitation_pairs = []
        self._feed_name_to_loc = {}
        for idx, t in enumerate(self.tups, start=1):
            p0, p1, n_seg, ev = t[0], t[1], t[2], t[3]
            name = t[4] if len(t) >= 5 else None
            geo.wire(
                idx, n_seg, p0[0], p0[1], p0[2], p1[0], p1[1], p1[2], 0.0005, 1.0, 1.0
            )
            mid_seg = (n_seg + 1) // 2
            if name is not None:
                self._feed_name_to_loc[name] = (idx, mid_seg, p0, p1, n_seg)
            # In the network path the spec drives ex_card emission; ignore ev's
            # (they're typically placeholders to keep a segment marked at the
            # feed edge for the geometry translator).
            if ev is not None and self._network is None:
                self.excitation_pairs.append((idx, mid_seg, ev))

        self._network_port_loc = {}

        self.c.geometry_complete(0)

        if self._network is not None:
            # Only Load-only networks reach here; TL/virtual-driver
            # networks take the NetworkReducer path and never build this
            # context.
            self._resolve_network_ports()
            self._emit_network_cards()
        else:
            for idx1, seg1, idx2, seg2, impedance, length in self.tls:
                self.c.tl_card(idx1, seg1, idx2, seg2, impedance, length, 0, 0, 0, 0)

        if WIRE_CONDUCTIVITY is not None:
            self.c.ld_card(5, 0, 0, 0, WIRE_CONDUCTIVITY, 0.0, 0.0)
        self._apply_ground_card()

        for tag, sub_index, voltage in self.excitation_pairs:
            self.c.ex_card(0, tag, sub_index, 0, voltage.real, voltage.imag, 0, 0, 0, 0)

    def _resolve_network_ports(self):
        """Resolve every PortAtEdge to its (tag, sub_seg) for native ld_card /
        ex_card emission. Only reached for Load-only networks; TL and
        virtual-driver networks take the NetworkReducer path instead."""
        for name, port in self._network.ports.items():
            if isinstance(port, PortAtEdge):
                if name not in self._feed_name_to_loc:
                    raise ValueError(
                        f"network port {name!r} is a PortAtEdge but no edge in "
                        f"build_wires() carries that name; named edges: "
                        f"{sorted(self._feed_name_to_loc)}"
                    )
                tag, mid_seg, _p0, _p1, _ns = self._feed_name_to_loc[name]
                self._network_port_loc[name] = (tag, mid_seg)

    def _emit_network_cards(self):
        """Emit a Load-only network as native NEC2 ld_cards + ex_cards. Called
        after geometry_complete(). (TL/virtual-driver networks never
        reach here — they go through the multiport-Y NetworkReducer path.)

        Load branches become ld_cards (type 0 = series RLC, type 1 = parallel
        RLC) on a single segment; a zero R/L/C means that element is absent,
        matching the Load dataclass's optional fields.
        """
        net = self._network
        for br in net.branches:
            if not isinstance(br, Load):
                raise NotImplementedError(
                    f"{type(br).__name__} reached PyNEC's native network path; "
                    "only Load is handled natively (TL/virtual-driver "
                    "networks use the NetworkReducer path)"
                )
            port = net.ports[br.port]
            if not isinstance(port, PortAtEdge):
                raise ValueError(
                    f"Load on virtual port {br.port!r}: a Load is a series "
                    "impedance on an antenna segment, which only PortAtEdge has"
                )
            tag, seg = self._network_port_loc[br.port]
            r = float(br.r) if br.r is not None else 0.0
            l = float(br.l) if br.l is not None else 0.0
            c = float(br.c) if br.c is not None else 0.0
            if r == 0.0 and l == 0.0 and c == 0.0:
                continue
            ldtyp = 1 if br.parallel else 0
            self.c.ld_card(ldtyp, tag, seg, seg, r, l, c)
        for src in net.sources:
            if not isinstance(src, Driven):
                raise NotImplementedError(f"unknown source type: {src!r}")
            tag, seg = self._network_port_loc[src.port]
            v = complex(src.voltage)
            self.excitation_pairs.append((tag, seg, v))

    def _apply_ground_card(self, c=None):
        c = c if c is not None else self.c
        g = self.ground
        if g is None or g == "free":
            return  # no gn_card -> free space
        if g == "pec":
            c.gn_card(1, 0, 0, 0, 0, 0, 0, 0)
            return
        if isinstance(g, tuple) and len(g) == 3 and g[0] in ("finite", "finite-fast"):
            _, eps_r, sigma = g
            # gn_card's first parameter (IPERF): 2 = Sommerfeld-Norton,
            # 0 = reflection-coefficient approximation.
            c.gn_card(2 if g[0] == "finite" else 0, 0, eps_r, sigma, 0, 0, 0, 0)
            return
        raise ValueError(f"unrecognised ground spec: {g!r}")

    # ----- network-spec path: multiport Y + shared NetworkReducer -----
    #
    # NEC2's tl_card can't represent a virtual driver behind a line (it needs
    # both endpoints on real segments, and a synthesised dummy stub injects a
    # huge parasitic reactance that the line fails to transform away). So for
    # `build_network()` designs we don't emit tl_cards at all: we extract the
    # antenna's multiport short-circuit Y at the real ports and hand it to the
    # engine-agnostic NetworkReducer (the EZNEC approach — transmission lines
    # as a circuit post-process on the field solution). Shared with momwire.

    def _network_uses_reducer(self):
        """True iff the network needs the Y-matrix reduction path — i.e. it
        has a transmission line (TL) or a virtual driver. Load-only networks
        are handled natively by NEC's ld_card."""
        net = self._network
        if any(isinstance(b, TL) for b in net.branches):
            return True
        return any(isinstance(p, PortVirtual) for p in net.ports.values())

    def _init_network(self):
        """Build the port-index map (real PortAtEdge ports first, virtual
        ports after) and the NetworkReducer. Validates that every PortAtEdge
        names an edge in build_wires()."""
        net = self._network
        named = {t[4] for t in self.tups if len(t) >= 5 and t[4] is not None}
        self._real_port_names = [
            n for n, p in net.ports.items() if isinstance(p, PortAtEdge)
        ]
        for name in self._real_port_names:
            if name not in named:
                raise ValueError(
                    f"network port {name!r} is a PortAtEdge but no edge in "
                    f"build_wires() carries that name; named edges: {sorted(named)}"
                )
        port_to_idx = {n: i for i, n in enumerate(self._real_port_names)}
        next_idx = len(self._real_port_names)
        for name, port in net.ports.items():
            if isinstance(port, PortVirtual):
                port_to_idx[name] = next_idx
                next_idx += 1
        self._reducer = NetworkReducer(net, port_to_idx, next_idx)

    def _make_real_context(self):
        """A fresh nec_context with only the real build_wires() geometry, wire
        conductivity, and ground — no virtual stubs, no tl_cards. Returns
        (context, {edge_name: (tag, mid_seg)})."""
        c = nec.nec_context()
        geo = c.get_geometry()
        loc = {}
        for idx, t in enumerate(self.tups, start=1):
            p0, p1, n_seg = t[0], t[1], t[2]
            name = t[4] if len(t) >= 5 else None
            geo.wire(
                idx,
                n_seg,
                p0[0],
                p0[1],
                p0[2],
                p1[0],
                p1[1],
                p1[2],
                WIRE_RADIUS,
                1.0,
                1.0,
            )
            if name is not None:
                loc[name] = (idx, (n_seg + 1) // 2)
        c.geometry_complete(0)
        if WIRE_CONDUCTIVITY is not None:
            c.ld_card(5, 0, 0, 0, WIRE_CONDUCTIVITY, 0.0, 0.0)
        self._apply_ground_card(c)
        return c, loc

    @staticmethod
    def _port_current(sc, tag, seg):
        """Complex current in sub-segment `seg` (1-based) of wire `tag`."""
        matches = [k for k, t in enumerate(sc.get_current_segment_tag()) if t == tag]
        return sc.get_current()[matches[seg - 1]]

    def _radiation_efficiency(self, sc, wavelength):
        """Return ``(efficiency, p_in)``: the fraction of source input power
        radiated rather than burned in explicit resistive Load branches
        (1.0 when there are none), and the source input power
        1/2·Re(Σ V·I*) itself in watts (the gain normaliser 4π·U/P_in).

        This mirrors MomwireEngine so the web UI normalises the far-field
        cut identically on either engine. The efficiency matches NEC's own
        get_gain overlay to a tenth of a dB. (With WIRE_CONDUCTIVITY left at
        None there is no global copper-loss ld_card — wires are PEC on both
        engines — so over ground the remaining rp-vs-cut gap is purely NEC's
        Sommerfeld ground versus the PEC-image approximation, measured within
        ~0.5 dB.)

        `sc` is the already-solved structure-currents object; `wavelength`
        sets the load reactances. Reactive loads (a loading coil) burn
        nothing and leave efficiency at 1.0.
        """
        # TL/virtual-driver networks reduce through the shared
        # reducer; reuse its port-level efficiency and input power.
        if self._network is not None and self._use_reducer:
            Y = self._compute_y_matrix(wavelength)
            _v, efficiency, p_in = self._reducer.excited_state(Y, wavelength)
            return efficiency, p_in
        # Native path: read the solved feed (and load) currents.
        p_in = 0.0
        for tag, seg, v in self.excitation_pairs or []:
            cur = self._port_current(sc, tag, seg)
            p_in += 0.5 * (complex(v) * np.conj(cur)).real
        loads = (
            [b for b in self._network.branches if isinstance(b, Load)]
            if self._network is not None
            else []
        )
        if not loads or p_in <= 0.0:
            return 1.0, p_in
        omega = 2.0 * np.pi * C_LIGHT / wavelength
        p_diss = 0.0
        for br in loads:
            tag, seg = self._network_port_loc[br.port]
            cur = self._port_current(sc, tag, seg)
            p_diss += 0.5 * load_impedance(br, omega).real * abs(cur) ** 2
        return max(0.0, min(1.0, 1.0 - p_diss / p_in)), p_in

    def _compute_y_matrix(self, wavelength):
        """Multiport short-circuit Y at the real ports, via one NEC solve per
        port: drive that port's gap at 1 V (the other named ports stay
        continuous = shorted) and read the resulting current at every port —
        column j of Y. The geometry's interaction matrix is refactored once
        per solve; small antennas make the N solves cheap."""
        freq = C_LIGHT / wavelength / 1e6
        names = self._real_port_names
        n = len(names)
        Y = np.zeros((n, n), dtype=np.complex128)
        for j, drv in enumerate(names):
            c, loc = self._make_real_context()
            tag, seg = loc[drv]
            c.ex_card(0, tag, seg, 0, 1.0, 0.0, 0, 0, 0, 0)
            c.fr_card(0, 1, freq, 0)
            c.xq_card(0)
            sc = c.get_structure_currents(0)
            for i, name in enumerate(names):
                Y[i, j] = self._port_current(sc, *loc[name])
            del c
        return Y

    def _excited_real_context(self, wavelength):
        """Fresh real-geometry context driven at the network-resolved real-
        port voltages (each real port a delta-gap at its resolved V), so
        far-field / current readouts reflect the network. fr_card is left to
        the caller."""
        Y = self._compute_y_matrix(wavelength)
        V = self._reducer.resolve_voltages(self._reducer.apply_branches(Y, wavelength))
        c, loc = self._make_real_context()
        for i, name in enumerate(self._real_port_names):
            tag, seg = loc[name]
            v = complex(V[i])
            c.ex_card(0, tag, seg, 0, v.real, v.imag, 0, 0, 0, 0)
        return c

    def _set_freq_and_execute(self):
        self.c.fr_card(0, 1, self.builder.freq, 0)
        self.c.xq_card(0)

    def _impedances_at(self, freq_index, sum_currents=False):
        sc = self.c.get_structure_currents(freq_index)

        indices = []
        for tag, tag_index, voltage in self.excitation_pairs:
            matches = [
                (i, t) for (i, t) in enumerate(sc.get_current_segment_tag()) if t == tag
            ]
            index = matches[tag_index - 1][0]
            indices.append((index, voltage))

        currents = sc.get_current()
        zs = [voltage / currents[idx] for idx, voltage in indices]

        if sum_currents:
            zs = [1 / sum(1 / z for z in zs)]

        return zs

    def impedance(self, sum_currents=False):
        if self._use_reducer:
            wl = C_LIGHT / (self.builder.freq * 1e6)
            return self._reducer.driven_impedance(self._compute_y_matrix(wl), wl)
        self._set_freq_and_execute()
        return self._impedances_at(0, sum_currents=sum_currents)

    def impedance_sweep(self, freqs, sum_currents=False):
        freqs = np.asarray(freqs, dtype=float)
        if freqs.ndim != 1 or freqs.size == 0:
            raise ValueError("freqs must be a 1-D non-empty array")
        if self._use_reducer:
            zs = np.empty((freqs.size, self._reducer.n_driven), dtype=np.complex128)
            for k, f in enumerate(freqs):
                wl = C_LIGHT / (float(f) * 1e6)
                zs[k] = self._reducer.driven_impedance(self._compute_y_matrix(wl), wl)
            return zs
        if freqs.size == 1:
            del_freq = 0.0
        else:
            steps = np.diff(freqs)
            del_freq = float(steps[0])
            if not np.allclose(steps, del_freq):
                raise ValueError(
                    "PyNECEngine.impedance_sweep requires evenly spaced freqs"
                )
        self.c.fr_card(0, freqs.size, float(freqs[0]), del_freq)
        self.c.xq_card(0)
        return np.array(
            [
                self._impedances_at(i, sum_currents=sum_currents)
                for i in range(freqs.size)
            ]
        )

    def current_distribution(self):
        """Per-tuple knot positions + complex currents. Each build_wires()
        tuple becomes one wire entry with n_seg+1 knot positions; interior
        knots are the average of the two adjacent NEC segment-centre
        currents. Boundary knots are zeroed at genuine free ends (open-wire
        BC) but carry the adjacent segment-centre current at junctions, where
        the current is physically continuous through the shared endpoint.
        Mirrors antennaknobs.web.pynec_backend._segment_centers_to_knot_currents."""
        if self._use_reducer:
            self.c = self._excited_real_context(C_LIGHT / (self.builder.freq * 1e6))
        self._set_freq_and_execute()
        sc = self.c.get_structure_currents(0)
        self._excited_efficiency, self._excited_p_in = self._radiation_efficiency(
            sc, C_LIGHT / (self.builder.freq * 1e6)
        )
        all_tags = list(sc.get_current_segment_tag())
        all_cur = sc.get_current()

        # A wire end shared with another tuple is a junction (current
        # continuous through it); an unshared end is a free end (I -> 0).
        # Without this, a 1-segment feed stub — both ends junctions — would
        # render zero current along its whole length even though it sits at a
        # current maximum, opening a visible gap at the feed.
        def _key(p):
            return tuple(np.round(np.asarray(p, dtype=float), 6))

        endpoint_count: dict = {}
        for t in self.tups:
            for p in (t[0], t[1]):
                endpoint_count[_key(p)] = endpoint_count.get(_key(p), 0) + 1

        out = []
        for tag_idx, t in enumerate(self.tups, start=1):
            p0, p1, n_seg = t[0], t[1], t[2]
            seg_idxs = [i for i, t in enumerate(all_tags) if t == tag_idx]
            cur_per_seg = np.array([all_cur[i] for i in seg_idxs], dtype=np.complex128)
            knots = np.linspace(p0, p1, n_seg + 1)
            knot_cur = np.zeros(n_seg + 1, dtype=np.complex128)
            if n_seg >= 2:
                knot_cur[1:-1] = 0.5 * (cur_per_seg[:-1] + cur_per_seg[1:])
            if cur_per_seg.shape[0] >= 1:
                if endpoint_count.get(_key(p0), 0) >= 2:
                    knot_cur[0] = cur_per_seg[0]
                if endpoint_count.get(_key(p1), 0) >= 2:
                    knot_cur[-1] = cur_per_seg[-1]
            out.append(
                WireCurrents(
                    knot_positions=knots,
                    knot_currents=knot_cur,
                )
            )
        return out

    def far_field(self, *, n_theta=90, n_phi=360, del_theta=1, del_phi=1):
        if self._use_reducer:
            self.c = self._excited_real_context(C_LIGHT / (self.builder.freq * 1e6))
        self._set_freq_and_execute()
        return self._collect_pattern(
            n_theta=n_theta, n_phi=n_phi, del_theta=del_theta, del_phi=del_phi
        )

    def _collect_pattern(self, *, n_theta, n_phi, del_theta, del_phi):
        assert 90 % n_theta == 0 and 90 == del_theta * n_theta
        assert 360 % n_phi == 0 and 360 == del_phi * n_phi

        self.c.rp_card(
            0, n_theta, n_phi + 1, 0, 5, 0, 0, 0, 0, del_theta, del_phi, 0, 0
        )

        thetas = np.linspace(0, 90 - del_theta, n_theta)
        phis = np.linspace(0, 360, n_phi + 1)

        rings = [
            [
                self.c.get_gain(0, theta_index, phi_index)
                for phi_index, _ in enumerate(phis)
            ]
            for theta_index, _ in enumerate(thetas)
        ]

        return FarField(
            rings=rings,
            max_gain=self.c.get_gain_max(0),
            min_gain=self.c.get_gain_min(0),
            thetas=thetas,
            phis=phis,
        )

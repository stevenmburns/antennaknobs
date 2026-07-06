"""momwire-backed SimulationEngine. Impedance via TriangularSolver;
far-field/directivity ported from momwire/web/server.py:_compute_directivity_norm.
"""

from __future__ import annotations

import numpy as np
from momwire import TriangularSolver

from ..engine import FarField, SimulationEngine, WireCurrents
from ..geometry import flat_wires_to_polylines
from ..network import PortAtEdge, PortVirtual
from ..network_reduce import NetworkReducer, tl_admittance_2x2


def _parity_for_solver(solver, solver_kwargs):
    """The basis types have fixed parity expectations:
      - TriangularSolver (tent / linear B-spline) → even (feed straddles 2 segs)
      - BSplineSolver degree=1 → same as triangular → even
      - BSplineSolver degree=2 → quadratic → odd
      - SinusoidalSolver → odd
    Anything else falls through as "any" (no coercion)."""
    name = getattr(solver, "__name__", "")
    if name == "TriangularSolver":
        return "even"
    if name == "SinusoidalSolver":
        return "odd"
    if name in ("BSplineSolver", "HMatrixSolver", "ArrayBlockSolver"):
        # HMatrixSolver and ArrayBlockSolver are BSplineSolver subclasses (same
        # basis), so they share the degree-driven parity. Getting this right
        # matters for cross-solver comparison: a mismatched parity would build
        # a *different* mesh and silently invalidate any A/B against the dense
        # bspline path.
        degree = (solver_kwargs or {}).get("degree", 2)
        return "even" if int(degree) == 1 else "odd"
    return "any"


C_LIGHT = 299_792_458.0
ETA0 = 376.730313668  # free-space impedance, ohms
EPS0 = 8.854_187_817e-12


def _polyline_knots(polyline, npe_list):
    """Concatenated per-edge knot positions (shared corners deduped).
    Mirrors momwire/web/server.py:_polyline_knots."""
    parts = []
    for i, n_e in enumerate(npe_list):
        seg = np.linspace(polyline[i], polyline[i + 1], n_e + 1)
        parts.append(seg if i == 0 else seg[1:])
    return np.vstack(parts)


def _normalise_ground(ground):
    if ground is None or ground == "free":
        return None
    if ground == "pec":
        return ("pec",)
    if (
        isinstance(ground, tuple)
        and len(ground) == 3
        and ground[0]
        in (
            "finite",
            "finite-fast",
        )
    ):
        # "finite-fast" is a PyNECEngine distinction (Sommerfeld-Norton vs the
        # reflection-coefficient approximation); momwire's best finite model
        # is the reflection-coefficient one (BSplineSolver ground_eps), so
        # both fold to a single spec and, for solvers that support it, both
        # get the refl-coef solve (Sommerfeld in momwire is out of scope —
        # see momwire docs/refl-coef-ground-plan.md).
        return ("finite",) + tuple(ground[1:])
    raise ValueError(f"unrecognised ground spec: {ground!r}")


# Solvers whose impedance solve honours the reflection-coefficient finite
# ground. BSplineSolver implements it; HMatrixSolver / ArrayBlockSolver
# subclass it and fall back to the dense path when ground_eps is set
# (momwire >= 0.4.0). TriangularSolver / SinusoidalSolver only model the
# PEC image, so finite grounds keep folding to PEC for them.
_GROUND_EPS_SOLVERS = ("BSplineSolver", "HMatrixSolver", "ArrayBlockSolver")


def _solver_supports_ground_eps(solver):
    return getattr(solver, "__name__", None) in _GROUND_EPS_SOLVERS


class MomwireEngine(SimulationEngine):
    supports_far_field = True

    def __init__(
        self,
        builder,
        *,
        solver=TriangularSolver,
        wire_radius=0.0005,
        solver_kwargs=None,
        ground=None,
        ground_z=0.0,
        cancel=None,
    ):
        """
        solver:
          A momwire solver class — TriangularSolver (default), SinusoidalSolver,
          or BSplineSolver. Different bases trade speed vs impedance fidelity;
          on the hentenna sinusoidal is typically closer to PyNEC at modest
          segmentation than triangular.
        solver_kwargs:
          Dict of solver-specific kwargs passed straight to the constructor
          (e.g. `{"n_qp_reg": 8, "n_qp_off": 8}` for TriangularSolver, or
          `{"n_qp_const": 16}` for SinusoidalSolver). None = solver defaults.
        ground:
          None or "free"           — no ground (default)
          "pec"                    — PEC plane at z=ground_z (image method)
          ("finite", eps_r, sigma) — far-field uses PEC image + Fresnel
                                     coefficients on the reflected component.
                                     The impedance solve uses momwire's
                                     reflection-coefficient finite ground
                                     (NEC gn 0 style, BSplineSolver
                                     ground_eps) when the solver supports it
                                     (bspline family); TriangularSolver /
                                     SinusoidalSolver still fold to the PEC
                                     image. ("finite-fast", eps_r, sigma) is
                                     accepted as an alias; Sommerfeld gn 2 is
                                     approximated by the same model (they
                                     agree to ~2 ohm above ~0.1λ heights).
        """
        super().__init__(builder)

        # Cooperative-cancellation token (momwire.CancelToken or None). Forwarded
        # into every solver construction so a mid-solve cancel aborts the C++
        # fill / Python checkpoints, and polled between this engine's own phases.
        self._cancel = cancel
        self._solver = solver
        self._solver_kwargs = dict(solver_kwargs) if solver_kwargs else {}
        # Per-instance parity: triangular wants even, sinusoidal odd,
        # bspline depends on degree. Set before _coerce_wire_tuples runs.
        self.segment_parity = _parity_for_solver(self._solver, self._solver_kwargs)

        # build_wires() must run before build_tls() — some designs populate
        # self.tls inside build_wires() (delta_looparray_with_tls).
        tups = self._coerce_wire_tuples(builder.build_wires())
        self._network = builder.build_network()
        self._tls = [] if self._network is not None else list(builder.build_tls())

        # Resolve TL endpoint tags into augmented tups: any tag whose ev was
        # nullified gets a passive feed (V=0) so momwire assembles the full
        # multi-port Y matrix. Driven ports keep their original voltages.
        augmented_tags = set()
        if self._tls:
            tups = list(tups)
            for tag1, _seg1, tag2, _seg2, _z0, _length in self._tls:
                for tag in (tag1, tag2):
                    t = tups[tag - 1]
                    p0, p1, n_seg, ev = t[0], t[1], t[2], t[3]
                    if ev is None:
                        tups[tag - 1] = (p0, p1, n_seg, 0 + 0j)
                        augmented_tags.add(tag)

        translated = flat_wires_to_polylines(tups)
        self._polylines = translated["polylines"]
        self._edge_segments = translated["edge_segments"]
        self._feeds = translated["feeds"]
        self._feed_names = translated["feed_names"]
        self._junctions = translated["junctions"]
        self._wire_radius = wire_radius
        self._ground = _normalise_ground(ground)
        self._ground_z = ground_z if self._ground is not None else None
        # Finite ground constants forwarded to the impedance solve when the
        # solver supports the reflection-coefficient model; None otherwise
        # (PEC image, today's behavior for triangular/sinusoidal).
        self._ground_eps = None
        if (
            self._ground is not None
            and self._ground[0] == "finite"
            and _solver_supports_ground_eps(self._solver)
        ):
            self._ground_eps = (float(self._ground[1]), float(self._ground[2]))

        # Map TL tags to feed indices for the legacy build_tls() path.
        self._tag_to_feed = {}
        feed_i = 0
        for tag, t in enumerate(tups, start=1):
            ev = t[3]
            if ev is not None:
                self._tag_to_feed[tag] = feed_i
                feed_i += 1
        # 0-based feed indices that are TL passive ports (V=0, floating).
        self._tl_passive_feed_idx = {self._tag_to_feed[t] for t in augmented_tags}

        if self._network is not None:
            self._init_network()

    def _init_network(self):
        """Build the port-index map (real feeds first, virtual ports after)
        and the engine-agnostic NetworkReducer that stamps the branches and
        reduces to driven-port impedance. Validates that every PortAtEdge
        resolves to a translated feed name."""
        net = self._network
        feed_name_to_idx = {n: i for i, n in enumerate(self._feed_names) if n}

        port_to_idx = {}
        for name, port in net.ports.items():
            if isinstance(port, PortAtEdge):
                if name not in feed_name_to_idx:
                    raise ValueError(
                        f"network port {name!r} is a PortAtEdge but no edge in "
                        f"build_wires() carries that name; named edges: "
                        f"{sorted(feed_name_to_idx)}"
                    )
                port_to_idx[name] = feed_name_to_idx[name]

        # Virtual ports are indexed after the real feeds.
        next_idx = len(self._feeds)
        for name, port in net.ports.items():
            if isinstance(port, PortVirtual):
                port_to_idx[name] = next_idx
                next_idx += 1

        self._reducer = NetworkReducer(net, port_to_idx, next_idx)

    def _ground_solver_kwargs(self):
        """Extra ground kwargs for solver construction. Only spliced in when
        set — TriangularSolver / SinusoidalSolver don't accept ground_eps."""
        if self._ground_eps is None:
            return {}
        return {"ground_eps": self._ground_eps}

    def _make_solver(self, *, wavelength):
        return self._solver(
            wires=self._polylines,
            n_per_edge_per_wire=self._edge_segments,
            feeds=self._feeds,
            wavelength=wavelength,
            wire_radius=self._wire_radius,
            ground_z=self._ground_z,
            junctions=self._junctions or None,
            cancel=self._cancel,
            **self._ground_solver_kwargs(),
            **self._solver_kwargs,
        )

    @staticmethod
    def _wavelength_for(freq_mhz):
        return C_LIGHT / (freq_mhz * 1e6)

    def _apply_tls(self, Y, wavelength):
        """Y + per-TL stamps at the corresponding feed-index pairs (legacy
        build_tls() path; the network-spec path goes through NetworkReducer)."""
        Y = Y.copy()
        for tag1, _s1, tag2, _s2, z0, length in self._tls:
            a = self._tag_to_feed[tag1]
            b = self._tag_to_feed[tag2]
            y_tl = tl_admittance_2x2(z0, length, wavelength)
            Y[np.ix_([a, b], [a, b])] += y_tl
        return Y

    def _resolve_feed_voltages(self, Y_total):
        """Return the full per-feed voltage vector V with passive ports'
        voltages set so I_ext=0 there. The driven ports keep their applied V."""
        n = Y_total.shape[0]
        driven = [i for i in range(n) if i not in self._tl_passive_feed_idx]
        passive = sorted(self._tl_passive_feed_idx)
        v_driven = np.array([self._feeds[i][2] for i in driven], dtype=np.complex128)
        V = np.empty(n, dtype=np.complex128)
        V[driven] = v_driven
        if passive:
            Y_pp = Y_total[np.ix_(passive, passive)]
            Y_pd = Y_total[np.ix_(passive, driven)]
            V[passive] = np.linalg.solve(Y_pp, -Y_pd @ v_driven)
        return V, driven

    def _impedance_from_y(self, Y_total):
        """Driving-point Z at each driven port, with passive (TL-only) ports
        floating (I_ext=0). Matches PyNECEngine's per-driven-port semantics
        when all drivers are excited simultaneously."""
        V, driven = self._resolve_feed_voltages(Y_total)
        I = Y_total @ V
        return [complex(V[i] / I[i]) for i in driven]

    def _compute_y_matrix(self, wavelength):
        """Multi-port short-circuit Y at the configured feeds. Builds one
        solver with the full feed list and calls momwire's compute_y_matrix,
        which since the junction-aware-y-matrix PR handles closed-loop /
        tee-junction antennas correctly (one LU + N back-subs per Y)."""
        return np.asarray(
            self._make_solver(wavelength=wavelength).compute_y_matrix(),
            dtype=np.complex128,
        )

    def _solved_excited(self, wavelength):
        """Build the excitation-resolved solver and run compute_impedance
        once per (wavelength, feed-voltage) tuple, caching on the engine
        instance. Lets impedance(), current_distribution(), and far_field()
        share one MoM solve when the live UI tick calls them in sequence.

        Cache lives for this engine instance only; the server constructs a
        fresh MomwireEngine each tick, so nothing leaks across requests.
        """
        sim = self._make_excited_solver(wavelength=wavelength)
        v_key = tuple((complex(v).real, complex(v).imag) for *_, v in sim.feeds)
        key = (float(wavelength), v_key)
        cached = getattr(self, "_solved_cache", None)
        if cached is not None and cached[0] == key:
            return cached[1]
        z, coeffs = sim.compute_impedance()
        self._solved_cache = (key, (sim, coeffs, z))
        return sim, coeffs, z

    def _raise_if_cancelled(self):
        """Poll the cancel token at an engine-phase boundary (no-op without one).

        Complements the solver-internal checkpoints: catches a cancel that lands
        between this engine's phases (e.g. after impedance() before far_field())
        without waiting for the next solver-internal seam.
        """
        if self._cancel is not None:
            self._cancel.raise_if_cancelled()

    def impedance(self):
        self._raise_if_cancelled()
        wavelength = self._wavelength_for(self.builder.freq)
        if self._network is not None:
            Y = self._compute_y_matrix(wavelength)
            return self._reducer.driven_impedance(Y, wavelength)
        if self._tls:
            Y = self._compute_y_matrix(wavelength)
            Y_total = self._apply_tls(Y, wavelength)
            return self._impedance_from_y(Y_total)
        _sim, _coeffs, z = self._solved_excited(wavelength)
        # Single-feed path returns a scalar; multi-feed returns an array.
        # Match PyNECEngine's list-of-Z return shape.
        z_arr = np.atleast_1d(z)
        return [complex(zi) for zi in z_arr]

    def impedance_sweep(self, freqs):
        freqs = np.asarray(freqs, dtype=float)
        if freqs.ndim != 1 or freqs.size == 0:
            raise ValueError("freqs must be a 1-D non-empty array")
        s = self._make_solver(wavelength=self._wavelength_for(freqs[0]))
        k_array = 2.0 * np.pi * freqs * 1e6 / C_LIGHT
        if self._network is not None:
            Y_swept = np.asarray(
                s.compute_y_matrix_swept(k_array), dtype=np.complex128
            )  # (n_k, n_real, n_real)
            zs = np.empty((freqs.size, self._reducer.n_driven), dtype=np.complex128)
            for ki, freq in enumerate(freqs):
                Y_total = self._reducer.apply_branches(
                    Y_swept[ki], self._wavelength_for(freq)
                )
                zs[ki] = self._reducer.impedance_from_y(Y_total)
            return zs
        if self._tls:
            # Batched Y at every frequency, then per-k TL stamping (βL is
            # frequency-dependent) and driven-port reduction. The Y assembly
            # is amortised across frequencies via the upstream swept solve;
            # the per-k post-processing is O(n_p³) and dwarfed by the solve.
            Y_swept = np.asarray(
                s.compute_y_matrix_swept(k_array), dtype=np.complex128
            )  # (n_k, n_p, n_p)
            n_driven = sum(
                1 for i in range(Y_swept.shape[1]) if i not in self._tl_passive_feed_idx
            )
            zs = np.empty((freqs.size, n_driven), dtype=np.complex128)
            for ki, freq in enumerate(freqs):
                Y_total = self._apply_tls(Y_swept[ki], self._wavelength_for(freq))
                zs[ki] = self._impedance_from_y(Y_total)
            return zs
        zs = s.compute_impedance_swept(k_array)
        # Single-feed: (n_k,); multi-feed: (n_k, n_feeds). Normalise to
        # (n_k, n_feeds) to match PyNECEngine.
        zs = np.asarray(zs)
        if zs.ndim == 1:
            zs = zs.reshape(-1, 1)
        return zs

    def _make_excited_solver(self, *, wavelength):
        """Build a solver whose feed voltages match the actual excitation:
        for plain designs, just the build_wires() voltages; for TL or
        Network designs, the per-port voltages after the network reduction
        so basis coefficients reflect the branch-induced port voltages.
        Without this, network-spec designs (where every named feed carries
        a placeholder V=0) would solve with no excitation — every basis
        coefficient is zero and `compute_impedance`'s V/I returns NaN."""
        if self._network is not None:
            # excited_state imposes the physical series-load BC (not the V=0
            # pin the impedance path uses), so resistive loads shape the
            # current; it also returns the radiation efficiency and the
            # source input power the far field uses to normalise gain.
            Y = self._compute_y_matrix(wavelength)
            V_full, self._excited_efficiency, self._excited_p_in = (
                self._reducer.excited_state(Y, wavelength)
            )
            feeds_resolved = [
                (w, arc, complex(V_full[i]))
                for i, (w, arc, _v) in enumerate(self._feeds)
            ]
        elif self._tls:
            self._excited_efficiency = 1.0
            Y = self._compute_y_matrix(wavelength)
            Y_total = self._apply_tls(Y, wavelength)
            V, driven = self._resolve_feed_voltages(Y_total)
            # Source input power at the driven ports of the TL-stamped port
            # model; the TLs are lossless so this equals the power entering
            # the wires.
            I_ports = Y_total @ V
            self._excited_p_in = 0.5 * float(
                sum((V[i] * np.conj(I_ports[i])).real for i in driven)
            )
            feeds_resolved = [
                (w, arc, complex(V[i])) for i, (w, arc, _v) in enumerate(self._feeds)
            ]
        else:
            self._excited_efficiency = 1.0
            # Plain path: no port model here; input_power() derives P_in from
            # the excited solve's driving-point impedance(s) on demand.
            self._excited_p_in = None
            return self._make_solver(wavelength=wavelength)
        return self._solver(
            wires=self._polylines,
            n_per_edge_per_wire=self._edge_segments,
            feeds=feeds_resolved,
            wavelength=wavelength,
            wire_radius=self._wire_radius,
            ground_z=self._ground_z,
            junctions=self._junctions or None,
            cancel=self._cancel,
            **self._ground_solver_kwargs(),
            **self._solver_kwargs,
        )

    def input_power(self):
        """Input power 1/2·Re(Σ V_f·I_f*) in watts over the SOURCE feeds of
        the excited solve — the gain normaliser (gain = 4π·U/P_in). Power
        burned in resistive loads and any ground absorption stay inside
        P_in (that is what makes 4π·U/P_in GAIN rather than directivity).

        Network / TL designs record it while resolving the excitation in
        `_make_excited_solver` (a load port is excited too, but it is not a
        source, so its absorbed power must not be summed — the port model
        separates the two). The plain path derives it from the excited
        driving-point impedance(s): I_f = V_f/Z_f, so each feed contributes
        ½·|V_f|²·Re(Z_f)/|Z_f|².
        """
        wavelength = self._wavelength_for(self.builder.freq)
        sim, _coeffs, z = self._solved_excited(wavelength)
        p_in = getattr(self, "_excited_p_in", None)
        if p_in is not None:
            return float(p_in)
        z_arr = np.atleast_1d(np.asarray(z, dtype=np.complex128))
        volts = np.array([complex(v) for *_, v in sim.feeds], dtype=np.complex128)
        with np.errstate(divide="ignore", invalid="ignore"):
            terms = 0.5 * np.abs(volts) ** 2 * z_arr.real / np.abs(z_arr) ** 2
        return float(np.sum(terms[np.isfinite(terms)]))

    def current_distribution(self):
        self._raise_if_cancelled()
        sim, coeffs, _z = self._solved_excited(self._wavelength_for(self.builder.freq))
        knot_currents = sim.currents_at_knots(coeffs)
        out = []
        for w_idx, polyline in enumerate(self._polylines):
            knots = _polyline_knots(polyline, self._edge_segments[w_idx])
            out.append(
                WireCurrents(
                    knot_positions=np.ascontiguousarray(knots),
                    knot_currents=np.ascontiguousarray(knot_currents[w_idx]),
                )
            )
        return out

    def geometry_distribution(self):
        """Per-wire knot positions with zero currents — a cheap geometry-only
        snapshot that skips the (possibly slow) MoM solve.

        Same shape as `current_distribution()` so the web layer can pack it
        with the same helper, but it only reads `_polylines` / `_edge_segments`
        (both built in `__init__`), so it returns in milliseconds even for
        large arrays. The UI uses it to draw a newly-selected antenna's shape
        immediately, then fills in the heatmap/waveforms when the real solve
        lands."""
        out = []
        for w_idx, polyline in enumerate(self._polylines):
            knots = _polyline_knots(polyline, self._edge_segments[w_idx])
            out.append(
                WireCurrents(
                    knot_positions=np.ascontiguousarray(knots),
                    knot_currents=np.zeros(knots.shape[0], dtype=np.complex128),
                )
            )
        return out

    def _segment_dipoles(self, sim, coeffs):
        """Returns (mid, dr, i_mid) — concatenated per-segment midpoints,
        edge vectors, and midpoint currents from the MoM solution."""
        knot_currents = sim.currents_at_knots(coeffs)
        mids, drs, i_mids = [], [], []
        for w_idx, polyline in enumerate(self._polylines):
            knots = _polyline_knots(polyline, self._edge_segments[w_idx])
            cur = knot_currents[w_idx]
            drs.append(knots[1:] - knots[:-1])
            mids.append(0.5 * (knots[1:] + knots[:-1]))
            i_mids.append(0.5 * (cur[1:] + cur[:-1]))
        return (
            np.concatenate(mids, axis=0),
            np.concatenate(drs, axis=0),
            np.concatenate(i_mids, axis=0),
        )

    def _evaluate_M_perp(self, mid, dr, i_mid, k, theta, phi, freq_hz):
        """|M_perp(θ,φ)|² on the (theta, phi) grids (radians).

        With ground enabled, adds the geometric-image contribution with PEC
        polarity, then layers Fresnel coefficients on the reflected wave so
        ρ_h=−1, ρ_v=+1 recovers the PEC limit exactly. Returns a real
        (n_theta, n_phi) array."""
        sin_t, cos_t = np.sin(theta), np.cos(theta)
        cos_p, sin_p = np.cos(phi), np.sin(phi)

        rx = sin_t[:, None] * cos_p[None, :]
        ry = sin_t[:, None] * sin_p[None, :]
        rz = np.broadcast_to(cos_t[:, None], rx.shape)
        rhat = np.stack([rx, ry, rz], axis=-1)

        phase = k * np.einsum("ijc,nc->ijn", rhat, mid)
        expp = np.exp(1j * phase)
        weighted = i_mid[:, None] * dr
        M = np.einsum("ijn,nc->ijc", expp, weighted)
        m_dot_r = np.sum(M * rhat, axis=-1)
        M_perp = M - m_dot_r[..., None] * rhat

        if self._ground is None:
            return np.sum(M_perp.real**2 + M_perp.imag**2, axis=-1)

        # Geometric image — horizontal current flipped, vertical preserved,
        # mirrored across z = ground_z.
        z0 = self._ground_z
        mid_img = mid.copy()
        mid_img[:, 2] = 2 * z0 - mid[:, 2]
        dr_img = dr * np.array([-1.0, -1.0, 1.0])
        weighted_img = i_mid[:, None] * dr_img
        phase_img = k * np.einsum("ijc,nc->ijn", rhat, mid_img)
        expp_img = np.exp(1j * phase_img)
        M_img = np.einsum("ijn,nc->ijc", expp_img, weighted_img)
        m_img_dot_r = np.sum(M_img * rhat, axis=-1)
        M_img_perp = M_img - m_img_dot_r[..., None] * rhat

        if self._ground[0] == "pec":
            M_perp = M_perp + M_img_perp
            return np.sum(M_perp.real**2 + M_perp.imag**2, axis=-1)

        # ("finite", eps_r, sigma): polarisation basis at each ray and
        # Fresnel reflection on the image wave.
        _, eps_r, sigma = self._ground
        s = np.sqrt(rx * rx + ry * ry)
        s_safe = np.where(s > 1e-12, s, 1.0)
        h_hat = np.stack([-ry / s_safe, rx / s_safe, np.zeros_like(rx)], axis=-1)
        v_hat = np.stack([-rx * rz / s_safe, -ry * rz / s_safe, s], axis=-1)
        M_img_h = np.sum(M_img_perp * h_hat, axis=-1)
        M_img_v = np.sum(M_img_perp * v_hat, axis=-1)

        omega = 2 * np.pi * freq_hz
        eps_c = eps_r - 1j * sigma / (omega * EPS0)
        cos_ti = rz
        sin2_ti = s * s
        Q = np.sqrt(eps_c - sin2_ti)
        rho_h = (cos_ti - Q) / (cos_ti + Q)
        rho_v = (eps_c * cos_ti - Q) / (eps_c * cos_ti + Q)

        # PEC reflection corresponds to ρ_h=−1, ρ_v=+1. The image we built
        # already has the PEC sign convention baked in, so we need the
        # Fresnel-vs-PEC ratio per polarisation:
        #     reflected_h = (−ρ_h) · M_img_h        # PEC was +1·M_img_h
        #     reflected_v = (+ρ_v) · M_img_v        # PEC was +1·M_img_v
        M_refl = (rho_v * M_img_v)[..., None] * v_hat - (rho_h * M_img_h)[
            ..., None
        ] * h_hat
        M_perp = M_perp + M_refl
        return np.sum(M_perp.real**2 + M_perp.imag**2, axis=-1)

    def far_field(self, *, n_theta=90, n_phi=360, del_theta=1, del_phi=1):
        self._raise_if_cancelled()
        assert 90 % n_theta == 0 and 90 == del_theta * n_theta
        assert 360 % n_phi == 0 and 360 == del_phi * n_phi

        wavelength = self._wavelength_for(self.builder.freq)
        k = 2.0 * np.pi / wavelength
        freq_hz = self.builder.freq * 1e6

        sim, coeffs, _z = self._solved_excited(wavelength)
        mid, dr, i_mid = self._segment_dipoles(sim, coeffs)

        # Gain normaliser from the source input power (same convention as the
        # web solve path): gain = 4π·U/P_in = η₀k²/(8π·P_in)·|M_perp|². Load
        # loss lives inside P_in, so terminated antennas come out as GAIN with
        # no efficiency multiply.
        p_in = self.input_power()
        if p_in > 0:
            directivity_norm = ETA0 * k * k / (8.0 * np.pi * p_in)
        else:
            # Defensive fallback (a pathological R_in ≤ 0): normalise by the
            # integrated pattern instead. Cell-centred grid over the sphere,
            # upper hemisphere only with ground (the image contribution is
            # already folded into |M_perp|² there).
            n_th_int, n_ph_int = 90, 180
            if self._ground is not None:
                theta_int = (np.arange(n_th_int) + 0.5) * (np.pi / 2 / n_th_int)
                dtheta = np.pi / 2 / n_th_int
            else:
                theta_int = (np.arange(n_th_int) + 0.5) * (np.pi / n_th_int)
                dtheta = np.pi / n_th_int
            phi_int = np.arange(n_ph_int) * (2 * np.pi / n_ph_int)
            dphi = 2 * np.pi / n_ph_int
            mag2_int = self._evaluate_M_perp(
                mid, dr, i_mid, k, theta_int, phi_int, freq_hz
            )
            p_rad = float(np.sum(mag2_int * np.sin(theta_int)[:, None]) * dtheta * dphi)
            if p_rad <= 0:
                raise RuntimeError("computed zero radiated power")
            efficiency = getattr(self, "_excited_efficiency", 1.0)
            directivity_norm = 4 * np.pi / p_rad * efficiency

        # Evaluate on the user grid (NEC convention: θ from 0 to 90−Δθ).
        theta_deg = np.linspace(0, 90 - del_theta, n_theta)
        phi_deg = np.linspace(0, 360, n_phi + 1)
        theta_user = np.deg2rad(theta_deg)
        phi_user = np.deg2rad(phi_deg)

        mag2_user = self._evaluate_M_perp(
            mid, dr, i_mid, k, theta_user, phi_user, freq_hz
        )
        D = directivity_norm * mag2_user
        # Floor before log so points where M_perp is exactly zero (poles,
        # nulls below quantisation) don't produce −inf.
        dBi = 10.0 * np.log10(np.maximum(D, 1e-30))

        rings = dBi.tolist()
        return FarField(
            rings=rings,
            max_gain=float(np.max(dBi)),
            min_gain=float(np.min(dBi)),
            thetas=theta_deg,
            phis=phi_deg,
        )

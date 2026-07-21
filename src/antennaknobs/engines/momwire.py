"""momwire-backed SimulationEngine. Impedance via a momwire solver class
(BSplineSolver by default); far-field/directivity ported from
momwire/web/server.py:_compute_directivity_norm.
"""

from __future__ import annotations

import logging

import numpy as np
from momwire import BSplineSolver

from ..engine import FarField, SimulationEngine, WireCurrents
from ..geometry import flat_wires_to_polylines
from ..network import PortOnWire, PortVirtual, as_wire
from ..network_reduce import NetworkReducer, tl_admittance_2x2

_logger = logging.getLogger(__name__)


def _parity_for_solver(solver, solver_kwargs):
    """The basis types have fixed parity expectations:
      - BSplineSolver degree=1 → tent basis, even (feed straddles 2 segs)
      - BSplineSolver degree=2 → quadratic → odd
      - SinusoidalSolver → odd
    Anything else falls through as "any" (no coercion)."""
    name = getattr(solver, "__name__", "")
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
        # The variant is preserved: "finite" means the true Sommerfeld/
        # Norton ground (NEC gn 2 — momwire BSplineSolver implements it
        # since 0.6.0), "finite-fast" the reflection-coefficient
        # approximation (NEC gn 0). Solvers without the requested model
        # fall back to their best available one — see the ground-model
        # mapping in __init__.
        return (ground[0],) + tuple(ground[1:])
    raise ValueError(f"unrecognised ground spec: {ground!r}")


# Solvers whose impedance solve honours the reflection-coefficient finite
# ground. BSplineSolver implements it; HMatrixSolver / ArrayBlockSolver
# subclass it (dense fallback in momwire 0.4.0, fast-path blocks in 0.4.1);
# SinusoidalSolver grew its own field-based ground_eps in momwire 0.5.0
# (phase 6 — matches NEC gn 0 at the solver's own discretization floor,
# ~0.1 ohm on the validation matrix). Every shipping momwire solver is on
# the list; the guard stays for exotic/user-supplied solver classes.
_GROUND_EPS_SOLVERS = (
    "BSplineSolver",
    "HMatrixSolver",
    "ArrayBlockSolver",
    "SinusoidalSolver",
)


def _solver_supports_ground_eps(solver):
    return getattr(solver, "__name__", None) in _GROUND_EPS_SOLVERS


# Distributed wire loading (issue #316 / momwire#131): every momwire
# solver models it since momwire 0.11.0 — the BSpline family as a Galerkin
# overlap, SinusoidalSolver as NEC's impedance boundary condition at the
# match points (momwire#134). The gate remains as the seam for any future
# solver that lacks the feature (warn-and-drop, not crash).
_WIRE_LOADING_SOLVERS = (
    "BSplineSolver",
    "HMatrixSolver",
    "ArrayBlockSolver",
    "SinusoidalSolver",
)


def _solver_supports_wire_loading(solver):
    return getattr(solver, "__name__", None) in _WIRE_LOADING_SOLVERS


class MomwireEngine(SimulationEngine):
    supports_far_field = True

    def __init__(
        self,
        builder,
        *,
        solver=BSplineSolver,
        wire_radius=0.0005,
        solver_kwargs=None,
        ground=None,
        ground_z=0.0,
        cancel=None,
    ):
        """
        solver:
          A momwire solver class — BSplineSolver (default), SinusoidalSolver,
          or the fast BSpline subclasses (HMatrixSolver, ArrayBlockSolver).
          Different bases trade speed vs impedance fidelity; on the hentenna
          sinusoidal is typically closer to PyNEC at modest segmentation.
        solver_kwargs:
          Dict of solver-specific kwargs passed straight to the constructor
          (e.g. `{"degree": 1}` for BSplineSolver, or `{"n_qp_const": 16}`
          for SinusoidalSolver). None = solver defaults.
        ground:
          None or "free"           — no ground (default)
          "pec"                    — PEC plane at z=ground_z (image method)
          ("finite", eps_r, sigma) — far-field uses PEC image + Fresnel
                                     coefficients on the reflected component.
                                     The impedance solve uses momwire's TRUE
                                     Sommerfeld ground (NEC gn 2 style,
                                     ground_model="sommerfeld") on every
                                     momwire solver (momwire >= 0.8.0:
                                     BSpline dense, Sinusoidal field-based,
                                     HMatrix/ArrayBlock fast paths) — the
                                     accurate-at-any-height model.
          ("finite-fast", eps_r, sigma) — the reflection-coefficient model
                                     (NEC gn 0 style, ground_eps) on every
                                     solver that supports it. Matches
                                     "finite" to ~2 ohm above ~0.1λ heights
                                     but diverges hard below (~22 ohm at
                                     0.05λ, >100 ohm at 0.02λ).
        """
        super().__init__(builder)

        # Cooperative-cancellation token (momwire.CancelToken or None). Forwarded
        # into every solver construction so a mid-solve cancel aborts the C++
        # fill / Python checkpoints, and polled between this engine's own phases.
        self._cancel = cancel
        self._solver = solver
        self._solver_kwargs = dict(solver_kwargs) if solver_kwargs else {}
        # Per-instance parity: sinusoidal wants odd, bspline depends on
        # degree. Set before _coerce_wire_tuples runs.
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
                    if t[3] is None:
                        # Preserve any name/spec fields while nullifying the
                        # feed (as_wire keeps them; only ex changes).
                        tups[tag - 1] = as_wire(t)._replace(ex=0 + 0j)
                        augmented_tags.add(tag)

        translated = flat_wires_to_polylines(tups)
        self._polylines = translated["polylines"]
        self._edge_segments = translated["edge_segments"]
        self._polyline_specs = translated["polyline_specs"]
        self._feeds = translated["feeds"]
        self._feed_names = translated["feed_names"]
        self._feed_edges = translated["feed_edges"]
        self._junctions = translated["junctions"]
        # Distributed-port expansion (issue #477): None until _init_network
        # finds a PortOnWire(distributed=True); every other path treats the
        # feed list 1:1.
        self._feed_W = None
        self._exp_feed_pos = None
        # Wire material (issues #316/#388): a design-declared WireSpec
        # supplies the default conductor radius plus the distributed-loading
        # kwargs; per-wire specs on individual Wire entries override it wire
        # by wire. Precedence for the default radius: an explicit non-default
        # `wire_radius` (the web model-options control) wins over
        # build_wire_material(); the stock 0.0005 acts as "auto" so a spec
        # design's skin-effect loss is computed at its real radius. An
        # explicit per-wire spec beats both — the web override only moves
        # the default.
        self._wire_spec = builder.build_wire_material()
        if wire_radius != 0.0005 and wire_radius is not None:
            default_radius = wire_radius
        elif self._wire_spec is not None:
            default_radius = self._wire_spec.radius
        else:
            default_radius = 0.0005
        specs = self._polyline_specs
        if any(s is not None for s in specs):
            # Per-wire radii (momwire#147, momwire >= 0.13.0 — all four
            # solver bases): one entry per polyline, passed straight
            # through as momwire's wire_radius array. A uniform list is
            # collapsed to the scalar (momwire does the same internally;
            # keeping the engine's readouts scalar preserves the
            # pre-#147 API surface for uniform designs).
            radii = [s.radius if s is not None else default_radius for s in specs]
            if len(set(radii)) == 1:
                self._wire_radius = radii[0]
            else:
                self._wire_radius = radii
        else:
            self._wire_radius = default_radius
        # Distributed loading rides only the solvers that model it; warn
        # once (not raise) so a matched-basis sinusoidal comparison of a
        # lossy design still solves — as the ideal wire, stated plainly.
        self._loading_kwargs = {}
        spec = self._wire_spec
        if any(s is not None for s in specs):
            # Per-wire loading (issue #388): one entry per polyline, NaN
            # switching the effect off for that wire (momwire's
            # normalize_per_wire convention). A wire without its own spec
            # inherits the design default. Skin loss is evaluated at each
            # wire's own radius since momwire#147 (the solver receives
            # the same per-wire radius array as the kernels).
            eff = [s if s is not None else spec for s in specs]
            nan = float("nan")
            cond = np.array(
                [
                    e.conductivity
                    if e is not None and e.conductivity is not None
                    else nan
                    for e in eff
                ]
            )
            ins_r = np.array(
                [
                    e.insulation_radius
                    if e is not None and e.insulation_radius is not None
                    else nan
                    for e in eff
                ]
            )
            ins_eps = np.array(
                [
                    e.insulation_eps_r
                    if e is not None and e.insulation_radius is not None
                    else nan
                    for e in eff
                ]
            )
            wants_loading = bool(np.isfinite(cond).any() or np.isfinite(ins_r).any())
            if wants_loading and _solver_supports_wire_loading(self._solver):
                if np.isfinite(cond).any():
                    self._loading_kwargs["wire_conductivity"] = cond
                if np.isfinite(ins_r).any():
                    self._loading_kwargs["insulation_radius"] = ins_r
                    self._loading_kwargs["insulation_eps_r"] = ins_eps
            elif wants_loading:
                _logger.warning(
                    "%s doesn't model distributed wire loading; solving the "
                    "design's %s wire as ideal (PEC, bare)",
                    getattr(self._solver, "__name__", self._solver),
                    type(builder).__name__,
                )
        elif spec is not None and (
            spec.conductivity is not None or spec.insulation_radius is not None
        ):
            if _solver_supports_wire_loading(self._solver):
                if spec.conductivity is not None:
                    self._loading_kwargs["wire_conductivity"] = spec.conductivity
                if spec.insulation_radius is not None:
                    self._loading_kwargs["insulation_radius"] = spec.insulation_radius
                    self._loading_kwargs["insulation_eps_r"] = spec.insulation_eps_r
            else:
                _logger.warning(
                    "%s doesn't model distributed wire loading; solving the "
                    "design's %s wire as ideal (PEC, bare)",
                    getattr(self._solver, "__name__", self._solver),
                    type(builder).__name__,
                )
        self._ground = _normalise_ground(ground)
        self._ground_z = ground_z if self._ground is not None else None
        # Finite ground constants forwarded to the impedance solve when the
        # solver supports the reflection-coefficient model; None otherwise
        # (PEC image).
        self._ground_eps = None
        self._ground_model = None
        if (
            self._ground is not None
            and self._ground[0] in ("finite", "finite-fast")
            and _solver_supports_ground_eps(self._solver)
        ):
            self._ground_eps = (float(self._ground[1]), float(self._ground[2]))
            # "finite" means true Sommerfeld on EVERY momwire solver since
            # momwire 0.8.0 (sinusoidal grew the model; HMatrix/ArrayBlock
            # solve it on their fast paths — C2-scaled image blocks + one
            # global low-rank remainder — so the old dense-solve cliff that
            # kept them on refl-coef is gone). "finite-fast" is refl-coef
            # everywhere.
            self._ground_model = (
                "sommerfeld" if self._ground[0] == "finite" else "refl-coef"
            )

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
        reduces to driven-port impedance. Validates that every PortOnWire
        resolves to a translated feed name."""
        net = self._network
        feed_name_to_idx = {n: i for i, n in enumerate(self._feed_names) if n}

        port_to_idx = {}
        for name, port in net.ports.items():
            if isinstance(port, PortOnWire):
                if name not in feed_name_to_idx:
                    raise ValueError(
                        f"network port {name!r} is a PortOnWire but no wire in "
                        f"build_wires() carries that name; named wires: "
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

        # Finite-gap (distributed) ports — issue #477. A distributed port
        # is realised as one delta-gap sub-feed per SEGMENT of its named
        # wire, voltages split by length (constant E over the wire's fixed
        # physical extent), and the antenna Y contracted back to port
        # granularity by congruence: Y_port = Wᵀ·Y_sub·W, with W's column
        # for a port holding the length weights h_i/L (uniform segments →
        # 1/S). The weighted current readout Σ wᵢ·Iᵢ is the bilinear dual
        # of the voltage split, so port power Σ V*·I is preserved and the
        # reducer sees an ordinary port row. Everything downstream —
        # reducer, sweeps, excited state — keeps feed-granularity code
        # untouched; only the solver feed list and the Y contraction know.
        dist_idx = {
            i
            for i, n in enumerate(self._feed_names)
            if n
            and isinstance(net.ports.get(n), PortOnWire)
            and net.ports[n].distributed
        }
        if dist_idx:
            self._build_feed_expansion(dist_idx)

    def _build_feed_expansion(self, dist_idx):
        """Expanded solver-feed positions + the (n_sub × n_feeds) weight
        matrix W for distributed ports. Non-distributed feeds keep a single
        sub-feed with weight 1 (W's column is a unit vector), so the
        contraction is exact for every port kind."""
        pos, cols = [], []
        for k, ((pl, arc, _v), (epl, eidx)) in enumerate(
            zip(self._feeds, self._feed_edges)
        ):
            if k in dist_idx:
                poly = self._polylines[epl]
                lens = np.linalg.norm(np.diff(poly, axis=0), axis=1)
                arc0 = float(lens[:eidx].sum())
                length = float(lens[eidx])
                n_sub = int(self._edge_segments[epl][eidx])
                for i in range(n_sub):
                    pos.append((epl, arc0 + (i + 0.5) * length / n_sub))
                    cols.append((k, 1.0 / n_sub))
            else:
                pos.append((pl, arc))
                cols.append((k, 1.0))
        W = np.zeros((len(pos), len(self._feeds)))
        for row, (k, w) in enumerate(cols):
            W[row, k] = w
        self._exp_feed_pos = pos
        self._feed_W = W

    def _solver_feeds(self, voltages=None):
        """The feed list handed to momwire solvers: per-feed (wire, arc, V),
        expanded to sub-feeds with length-split voltages when distributed
        ports exist. ``voltages`` (per ORIGINAL feed, in feed order)
        defaults to the translated feed voltages."""
        if voltages is None:
            voltages = [v for *_, v in self._feeds]
        if self._feed_W is None:
            return [(w, a, complex(v)) for (w, a, _v), v in zip(self._feeds, voltages)]
        v_exp = self._feed_W @ np.asarray(voltages, dtype=np.complex128)
        return [(w, a, complex(v)) for (w, a), v in zip(self._exp_feed_pos, v_exp)]

    def _contract_y(self, Y):
        """Contract a solver Y (sub-feed granularity) to port granularity;
        identity when no distributed ports exist. Works on one matrix or a
        swept (n_k, n, n) stack."""
        if self._feed_W is None:
            return Y
        W = self._feed_W
        if Y.ndim == 3:
            return np.einsum("ia,kij,jb->kab", W, Y, W)
        return W.T @ Y @ W

    def _ground_solver_kwargs(self):
        """Extra ground kwargs for solver construction. Only spliced in when
        set (free-space / PEC solves pass no ground_eps)."""
        if self._ground_eps is None:
            return {}
        kw = {"ground_eps": self._ground_eps}
        # Every ground_eps solver accepts ground_model since momwire 0.8.0
        # (refl-coef is the default, so it is only spliced in for
        # sommerfeld to keep refl-coef solves bit-identical to older pins).
        if self._ground_model == "sommerfeld":
            kw["ground_model"] = "sommerfeld"
        return kw

    def _make_solver(self, *, wavelength):
        return self._solver(
            wires=self._polylines,
            n_per_edge_per_wire=self._edge_segments,
            feeds=self._solver_feeds(),
            wavelength=wavelength,
            wire_radius=self._wire_radius,
            ground_z=self._ground_z,
            junctions=self._junctions or None,
            cancel=self._cancel,
            **self._loading_kwargs,
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
        tee-junction antennas correctly (one LU + N back-subs per Y).
        Distributed ports solve at sub-feed granularity and contract back
        to one row/column per port (issue #477)."""
        return self._contract_y(
            np.asarray(
                self._make_solver(wavelength=wavelength).compute_y_matrix(),
                dtype=np.complex128,
            )
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
            sim, coeffs, z = cached[1]
        else:
            z, coeffs = sim.compute_impedance()
            self._solved_cache = (key, (sim, coeffs, z))
        # _make_excited_solver reset the power bookkeeping either way, so
        # the wire-loss amendment below is applied exactly once per call.
        self._amend_wire_loss(sim, coeffs, z)
        return sim, coeffs, z

    def _amend_wire_loss(self, sim, coeffs, z):
        """Fold ohmic wire loss (momwire#131 distributed loading) into the
        power bookkeeping (issue #317): a "wire loss (I²R)" budget row and
        the matching efficiency drop. The loss already lives inside P_in
        (the loading raised the driving-point R), so gain = 4π·U/P_in needs
        no change — this keeps the *reported* efficiency and budget rows
        truthful about where those watts went. Insulation is reactive and
        contributes nothing; lossless designs are untouched."""
        self._excited_p_wire = 0.0
        if not self._loading_kwargs:
            return
        p_wire, _per_wire = sim.wire_loss_power(coeffs)
        if p_wire <= 0.0:
            return
        self._excited_p_wire = float(p_wire)
        self._excited_power_budget = list(self._excited_power_budget) + [
            ("wire loss (I²R)", float(p_wire))
        ]
        p_in = self._excited_p_in
        if p_in is None:  # plain path records no port-model power
            p_in = self._p_in_from_excited(sim, z)
        if p_in > 0.0:
            self._excited_efficiency = max(
                0.0, min(1.0, self._excited_efficiency - p_wire / p_in)
            )

    @staticmethod
    def _p_in_from_excited(sim, z):
        """Source input power ½·Σ|V_f|²·Re(Z_f)/|Z_f|² from an excited
        solve's driving-point impedances (the plain-path formula shared by
        `input_power` and the wire-loss amendment)."""
        z_arr = np.atleast_1d(np.asarray(z, dtype=np.complex128))
        volts = np.array([complex(v) for *_, v in sim.feeds], dtype=np.complex128)
        with np.errstate(divide="ignore", invalid="ignore"):
            terms = 0.5 * np.abs(volts) ** 2 * z_arr.real / np.abs(z_arr) ** 2
        return float(np.sum(terms[np.isfinite(terms)]))

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
            Y_swept = self._contract_y(
                np.asarray(s.compute_y_matrix_swept(k_array), dtype=np.complex128)
            )  # (n_k, n_real, n_real) at port granularity
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
            # excited_state solves the same MNA system as the impedance
            # path, so resistive loads shape the current through their
            # physical series BC; it also returns the radiation efficiency
            # and the source input power the far field uses to normalise
            # gain.
            Y = self._compute_y_matrix(wavelength)
            (
                V_full,
                self._excited_efficiency,
                self._excited_p_in,
                self._excited_power_budget,
            ) = self._reducer.excited_state(Y, wavelength)
            feeds_resolved = self._solver_feeds(
                [complex(V_full[i]) for i in range(len(self._feeds))]
            )
        elif self._tls:
            self._excited_efficiency = 1.0
            self._excited_power_budget = []
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
            self._excited_power_budget = []
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
            **self._loading_kwargs,
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
        return self._p_in_from_excited(sim, z)

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
        # Vertical (TM, in-plane) and horizontal (TE, out-of-plane)
        # polarisation unit vectors for the reflected ray, written straight
        # from the azimuth/zenith angles rather than from the horizontal
        # projection s = sin(theta). Dividing by s degenerates at the zenith
        # (s -> 0, the plane of incidence is undefined): the old s->1.0 guard
        # collapsed BOTH vectors to zero there, dropping the reflected wave and
        # reading ~3 dB low. The phi-limit h_hat=(-sin phi, cos phi, 0),
        # v_hat=(-cos phi, -sin phi, 0) is exact, unit, orthonormal to rhat,
        # and recovers the PEC limit (rho_h=-1, rho_v=+1) at theta=0.
        s = np.sqrt(rx * rx + ry * ry)  # = sin(theta); feeds sin2_ti below
        cos_p_g = np.broadcast_to(cos_p[None, :], rx.shape)
        sin_p_g = np.broadcast_to(sin_p[None, :], rx.shape)
        cos_t_g = np.broadcast_to(cos_t[:, None], rx.shape)
        sin_t_g = np.broadcast_to(sin_t[:, None], rx.shape)
        h_hat = np.stack([-sin_p_g, cos_p_g, np.zeros_like(rx)], axis=-1)
        v_hat = np.stack([-cos_p_g * cos_t_g, -sin_p_g * cos_t_g, sin_t_g], axis=-1)
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

"""Engine-agnostic reduction of a port-based `Network` spec to driven-port
impedances, on top of a raw multiport antenna admittance matrix.

Both MomwireEngine and PyNECEngine assemble the antenna's short-circuit Y at
the real (`PortAtEdge`) ports, then hand it here with a port-name -> matrix-
index map. This module stamps the network branches and sources into one
Modified Nodal Analysis (MNA) system — the SPICE formulation, issue #285 —
and solves it once for everything: driven-port impedances, physical port
voltages for the excited far-field/current solve, and the source-power /
load-dissipation bookkeeping. The only engine-specific work is producing the
raw Y and the index map; the linear algebra here is identical regardless of
which MoM solver produced Y.

This is the EZNEC-style approach: model transmission lines and lumped
elements as a circuit post-process on top of the field solution, rather than
via NEC2's native `tl_card` / `nt_card` / `ld_card`.

The node space is the port space: one node per port (real feeds first,
virtual ports after), every node's voltage referenced to the common return
(the datum). The datum has no matrix row — every port's second terminal is
bonded to it, which is the same convention the antenna's short-circuit
multiport Y already assumes. Elements that a bare admittance matrix cannot
represent — ideal voltage sources, ideal shorts, 0 Ω / 0 H series elements —
become Group-2 unknowns: the branch current joins the solution vector with a
constitutive row, so no element value is ever inverted.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .network import (
    TL,
    Driven,
    Load,
    PortAtEdge,
    Shunt,
    TwoPort,
    _parallel_rlc_admittance,
    _series_rlc_impedance,
    load_impedance,
    load_series_admittance,
)

C_LIGHT = 299_792_458.0


FEET_PER_M = 1.0 / 0.3048
NEPER_PER_DB = 1.0 / (20.0 / np.log(10.0))  # 1/8.6859: dB → nepers


def tl_admittance_2x2(z0, length, wavelength, transposed=False, vf=1.0, k1=0.0, k2=0.0):
    """Ideal-TL nodal admittance between its two terminals — lossless or
    lossy (issue #297).

    For complex propagation γl = (α + jβ)·length with β = 2π/(vf·λ):
        Y_TL = 1/(Z0 sinh γl) · [[cosh γl, -1], [-1, cosh γl]]
    which reduces exactly to the classic lossless form
        Y_TL = 1/(j Z0 sin θ) · [[cos θ, -1], [-1, cos θ]]
    at α = 0 (sinh jθ = j·sin θ). α comes from the cable-table matched-loss
    model k1·√f_MHz + k2·f_MHz in dB per 100 ft (see `network.TL`).

    Singular only for an exactly-lossless half-wavelength multiple
    (sinh γl = 0 requires α = 0); raise rather than return garbage so
    callers can pick a different length. Any nonzero loss regularizes it.

    `transposed=True` models a crossed ("half-twist") line: port B's
    polarity is inverted, which flips the sign of the off-diagonal
    (transfer) terms only. This is the nodal-model equivalent of NEC2's
    negative-Z0 tl_card crossing, used by transposed-feeder arrays (LPDA,
    ZL-Special). Note it is NOT the same as a negative z0, which would
    (wrongly) negate the diagonal self terms too.
    """
    beta = 2.0 * np.pi / (vf * wavelength)
    f_mhz = C_LIGHT / wavelength / 1e6
    loss_db_per_100ft = k1 * np.sqrt(f_mhz) + k2 * f_mhz
    alpha = loss_db_per_100ft * NEPER_PER_DB * FEET_PER_M / 100.0  # nepers/m
    gl = (alpha + 1j * beta) * length
    sh, ch = np.sinh(gl), np.cosh(gl)
    if abs(sh) < 1e-12:
        raise ValueError(
            f"lossless TL length {length} is ~k·vf·λ/2 at "
            f"f={f_mhz:.4f} MHz (sinh γl ≈ 0); admittance is singular"
        )
    scale = 1.0 / (z0 * sh)
    off = 1.0 if transposed else -1.0
    return scale * np.array([[ch, off], [off, ch]], dtype=np.complex128)


# ---------------------------------------------------------------------------
# MNA (Modified Nodal Analysis) core — issue #285.
# ---------------------------------------------------------------------------


@dataclass
class _Group2Element:
    """One Group-2 (auxiliary-current) element of the MNA system.

    The element carries a branch current ``j`` flowing a → b *through* the
    element (``None`` = the datum, which has no matrix row). KCL: ``+j``
    leaves node a and enters node b. The constitutive row is

        c_v · (v_b − v_a) + c_j · j = e

    Two scalings describe the same physical series branch — an EMF ``emf``
    (oriented to raise the potential from a to b) in series with impedance
    ``z`` = 1/``y``:

      impedance form:  (v_b − v_a) + z·j = emf      (c_v=1, c_j=z, e=emf)
          exact for every finite z, including the ideal short z = 0;
      admittance form: y·(v_b − v_a) + j = y·emf    (c_v=y, c_j=1, e=y·emf)
          exact for every finite y, including the ideal open y = 0.

    Each branch picks whichever form keeps its coefficients finite, so no
    element value is ever inverted — the reason ideal shorts and trap-
    resonance opens need no special-case guards here.
    """

    a: int | None
    b: int | None
    c_v: complex
    c_j: complex
    e: complex


def _series_group2(a, b, r, l, c, omega, emf=0j, ql=None, qc=None):
    """Group-2 stamp of a series R + jωL + 1/(jωC) (+ optional EMF) between
    nodes a and b. A 0 F capacitor is an open in the series path (infinite
    reactance) → admittance form with y = 0 (the branch carries no current).
    Every other value combination has finite z — including the ideal short
    z = 0 (0 Ω, 0 H, all-omitted, or exact series-LC resonance), which the
    old admittance-only stamps had to raise on. `ql`/`qc` add the finite-Q
    component losses (issue #298, see `network._series_rlc_impedance`)."""
    if c is not None and c == 0:
        return _Group2Element(a, b, c_v=0j, c_j=1.0 + 0j, e=0j)
    z = _series_rlc_impedance(r, l, c, omega, ql, qc)
    return _Group2Element(a, b, c_v=1.0 + 0j, c_j=z, e=emf)


class MNASystem:
    """Assembled MNA system ``[[G, B], [Cᵀ, D]] · [v; j] = [i_ext; e]``.

    ``v`` — node voltages vs. the datum (one per port, real feeds first);
    ``j`` — Group-2 branch currents. ``i_ext`` is zero at every node (all
    external injections enter through Group-2 source branches).

    ``terminations`` maps a port node index → ``(column, emf)`` for the
    per-port source/load termination branch (see
    ``NetworkReducer.apply_branches``); its current ``j[column]`` is the
    current the termination delivers INTO the node, so a driven port's
    impedance is ``emf / j[column]`` read straight off the solution.
    """

    def __init__(self, G, elements, terminations, probes=None):
        n = G.shape[0]
        m = len(elements)
        A = np.zeros((n + m, n + m), dtype=np.complex128)
        A[:n, :n] = G
        rhs = np.zeros(n + m, dtype=np.complex128)
        for x, el in enumerate(elements):
            col = n + x
            if el.a is not None:
                A[el.a, col] += 1.0  # j leaves node a
                A[col, el.a] -= el.c_v
            if el.b is not None:
                A[el.b, col] -= 1.0  # j enters node b
                A[col, el.b] += el.c_v
            A[col, col] = el.c_j
            rhs[col] = el.e
        self.n_nodes = n
        self.A = A
        self.rhs = rhs
        self.terminations = terminations
        self.elements = elements
        # (label, kind, payload) probes for the power budget (issue #299):
        # kind "group1" → payload (node_idx_list, stamped Y block);
        # kind "group2" → payload element index; kind "termination" →
        # payload node index (dissipation = the Load part of the branch).
        self.probes = probes or []
        self._solution = None

    def branch_power(self, label_kind_payload):
        """Time-average power in watts dissipated in one probed branch of
        the SOLVED system (issue #299). Group-1 stamps: ½·Re(v†·Y_br·v)
        over the branch's own stamped block (≈ 0 for a lossless TL, > 0
        for a lossy one). Group-2 elements: ½·Re((v_a − v_b)·j*), the drop
        across the element times its explicit branch current — exact in
        both impedance and admittance form, including shorts and opens.
        Terminations: ½·Re((E − v_k)·j*), the drop across the Load part
        (the EMF term is the port's input power, not dissipation)."""
        v, j = self.solve()
        label, kind, payload = label_kind_payload
        if kind == "group1":
            nodes, y_block = payload
            vb = v[nodes]
            return 0.5 * float(np.real(np.conj(vb) @ (y_block @ vb)))
        if kind == "group2":
            el = self.elements[payload]
            va = 0j if el.a is None else v[el.a]
            vb = 0j if el.b is None else v[el.b]
            return 0.5 * float(np.real((va - vb) * np.conj(j[payload])))
        # termination: the Load part of the source/load branch at node k.
        col, e = self.terminations[payload]
        return 0.5 * float(np.real((e - v[payload]) * np.conj(j[col])))

    def solve(self):
        """Solve once (cached); returns ``(v, j)``."""
        if self._solution is None:
            x = np.linalg.solve(self.A, self.rhs)
            self._solution = (x[: self.n_nodes], x[self.n_nodes :])
        return self._solution


class NetworkReducer:
    """Stamps a `Network`'s branches and sources into an MNA system on top
    of the raw real-port antenna Y and reads out driven-port impedances,
    physical port voltages, and the power bookkeeping.

    Construct with the network spec, a ``port_to_idx`` mapping every port
    name (real and virtual) to its row/column in the node space, and
    ``n_total_ports`` (real feeds + virtual ports). Real ports must occupy
    indices ``0..n_real-1`` in the same order as the raw Y handed to
    :meth:`apply_branches`; virtual ports come after.
    """

    def __init__(self, network, port_to_idx, n_total_ports):
        self.network = network
        self.port_to_idx = port_to_idx
        self.n_total_ports = n_total_ports

        # 0-based driven port indices and their applied voltages.
        self.driven_port_idx = []
        self.driven_voltages = []
        for src in network.sources:
            if not isinstance(src, Driven):
                raise NotImplementedError(f"unknown source type: {src!r}")
            self.driven_port_idx.append(port_to_idx[src.port])
            self.driven_voltages.append(complex(src.voltage))

    @property
    def n_driven(self):
        return len(self.driven_port_idx)

    def apply_branches(self, Y_real, wavelength):
        """Stamp the antenna Y and every network branch into one MNA system.

        Group 1 (node-admittance block G):
          - the antenna's dense multiport short-circuit Y at the real-feed
            nodes vs. datum;
          - TL branches (their 2×2 has shunt legs, so it is a natural
            admittance stamp; the half-wave singularity still raises);
          - parallel-mode Shunt (the tank admittance is the natural finite
            quantity, → 0 at trap resonance).

        Group 2 (auxiliary branch currents):
          - TwoPort and series-mode Shunt — series elements, exact for the
            ideal short z = 0 and the 0 F open;
          - one TERMINATION branch per port that is driven and/or loaded:
            an EMF (0 if undriven) in series with the port's Load impedance
            (0 if unloaded) from the datum into the node. Its constitutive
            row v_k + Z_L·j = E is the Thevenin boundary condition, and its
            current j is the delivered port current — so the driven-point
            impedance E/j and the load dissipation (E − v_k)·j* both read
            off the solution. Driven-only ports (Z_L = 0) degenerate to the
            ideal voltage-source pin v_k = E; loaded-only ports (E = 0) to
            the series load termination v_k = −Z_L·j. A `Load` is thus a
            series impedance between the antenna gap and the common return,
            matching NEC2's ld_card physics.

        Ports that are neither driven, loaded, nor touched by a branch keep
        plain KCL with zero injection (the floating I_ext = 0 condition).
        """
        omega = 2.0 * np.pi * C_LIGHT / wavelength
        n = self.n_total_ports
        G = np.zeros((n, n), dtype=np.complex128)
        n_real = Y_real.shape[0]
        G[:n_real, :n_real] = Y_real

        elements = []
        loads_by_node = {}
        probes = []
        for br in self.network.branches:
            if isinstance(br, TL):
                a, b = self.port_to_idx[br.a], self.port_to_idx[br.b]
                y_tl = tl_admittance_2x2(
                    br.z0,
                    br.length,
                    wavelength,
                    transposed=br.transposed,
                    vf=br.vf,
                    k1=br.k1,
                    k2=br.k2,
                )
                G[np.ix_([a, b], [a, b])] += y_tl
                probes.append((f"TL {br.a}→{br.b}", "group1", ([a, b], y_tl)))
            elif isinstance(br, TwoPort):
                a, b = self.port_to_idx[br.a], self.port_to_idx[br.b]
                probes.append((f"TwoPort {br.a}→{br.b}", "group2", len(elements)))
                elements.append(
                    _series_group2(a, b, br.r, br.l, br.c, omega, ql=br.ql, qc=br.qc)
                )
            elif isinstance(br, Shunt):
                k = self.port_to_idx[br.port]
                if br.parallel:
                    y_sh = _parallel_rlc_admittance(
                        br.r, br.l, br.c, omega, br.ql, br.qc
                    )
                    G[k, k] += y_sh
                    probes.append(
                        (f"Shunt {br.port}", "group1", ([k], np.array([[y_sh]])))
                    )
                else:
                    probes.append((f"Shunt {br.port}", "group2", len(elements)))
                    elements.append(
                        _series_group2(
                            k, None, br.r, br.l, br.c, omega, ql=br.ql, qc=br.qc
                        )
                    )
            elif isinstance(br, Load):
                if not isinstance(self.network.ports[br.port], PortAtEdge):
                    raise ValueError(
                        f"Load on virtual port {br.port!r}: a Load is a series "
                        "impedance on an antenna segment, which only PortAtEdge has"
                    )
                loads_by_node.setdefault(self.port_to_idx[br.port], []).append(br)
            else:
                raise NotImplementedError(f"branch type {type(br).__name__}")

        # Per-port termination branches. A port may carry BOTH a source and
        # a series load (the centre-loaded driven short dipole); they chain
        # into one branch: datum —EMF—Z_L→ node.
        emf = dict(zip(self.driven_port_idx, self.driven_voltages))
        terminations = {}
        for k in sorted(set(emf) | set(loads_by_node)):
            e = emf.get(k, 0j)
            loads = loads_by_node.get(k, [])
            zs = [load_impedance(br, omega) for br in loads]
            if len(loads) == 1 and loads[0].parallel:
                # Parallel-LC trap: the tank admittance is the finite
                # quantity (→ 0 at resonance, the intended open circuit);
                # the impedance form would blow up there.
                y = load_series_admittance(loads[0], omega)
                el = _Group2Element(None, k, c_v=y, c_j=1.0 + 0j, e=y * e)
            elif all(np.isfinite(z) for z in zs):
                # Series composition of every load (plus the EMF). Includes
                # the no-load case z = 0: an ideal voltage-source pin.
                el = _Group2Element(None, k, c_v=1.0 + 0j, c_j=sum(zs, 0j), e=e)
            else:
                # A chain containing an at-resonance trap is an open.
                el = _Group2Element(None, k, c_v=0j, c_j=1.0 + 0j, e=0j)
            terminations[k] = (len(elements), e)
            elements.append(el)
            if loads:
                names = [br.port for br in loads]
                probes.append((f"Load {'+'.join(names)}", "termination", k))

        return MNASystem(G, elements, terminations, probes=probes)

    def resolve_voltages(self, system):
        """Return the (n_total,) physical port-voltage vector of the solved
        network: driven ports at their applied voltages, loaded ports at the
        gap voltage V_k = V_src − Z_L·I_k (the load shapes the current the
        way NEC2's ld_card does), every other port floating with I_ext = 0.
        These are the voltages the excited far-field/current solver forces
        at the real feeds."""
        v, _j = system.solve()
        return v.copy()

    def excited_state(self, Y_real, wavelength):
        """Physical port voltages + radiation efficiency + per-branch power
        budget for the CURRENT-DISTRIBUTION / far-field solve — the same
        MNA solve as the impedance path, read out for power bookkeeping.

        Returns ``(V_full, efficiency, p_in, budget)``:
          V_full      -- (n_total,) port voltages to force in the excited solver
          efficiency  -- P_radiated / P_input = 1 - P_dissipated / P_input, the
                         fraction of input power radiated rather than burned in
                         the network. A load-free / lossless network
                         returns 1.0.
          p_in        -- input power 1/2 Re(Σ V_src · I*) in watts, the gain
                         normaliser (gain = 4π·U/P_in); it already includes the
                         power burned in the network.
          budget      -- list of ``(label, watts)`` per network branch, in
                         branch order (issue #299): TL and parallel-Shunt
                         stamps via ½·Re(v†·Y_br·v), TwoPort/series-Shunt
                         via their explicit branch currents, Loads via the
                         termination drop. Lossless branches report ~0.
                         Power delivered to the antenna (radiated + any
                         wire/ground loss inside the MoM solve) is
                         p_in − Σ watts.

        The termination branches carry the physical port currents, so the
        source power reads directly off the solution vector:

            p_in   = ½ Σ Re(E_k · j_k*)          (E = 0 terms vanish)

        Reactive elements burn nothing and report ~0 in the budget.
        Efficiency counts EVERY dissipative network branch — resistive
        TwoPort/Shunt elements and lossy TLs included (issue #299; the
        pre-#299 accounting counted Load terminations only, so designs
        with resistive coupling/matching branches now report a lower,
        physically consistent efficiency).
        """
        system = self.apply_branches(Y_real, wavelength)
        v, j = system.solve()
        p_in = 0.0
        for k, (col, e) in system.terminations.items():
            p_in += 0.5 * float(np.real(e * np.conj(j[col])))
        budget = [
            (label, system.branch_power((label, kind, payload)))
            for label, kind, payload in system.probes
        ]
        p_diss = sum(w for _label, w in budget)
        # A lossless network's probes read pure float noise (|w| ~ 1e-17·p_in
        # from the reactive TL stamp); snap that to exactly 1.0 so lossless
        # designs keep reporting unity efficiency.
        if p_in > 0.0 and abs(p_diss) <= 1e-9 * p_in:
            p_diss = 0.0
        efficiency = 1.0 if p_in <= 0.0 else max(0.0, min(1.0, 1.0 - p_diss / p_in))
        return v.copy(), efficiency, p_in, budget

    def impedance_from_y(self, system):
        """Driven-point impedance per Driven source from an `apply_branches`
        result: Z = E / j_term, the termination EMF over its delivered
        current — read straight off the solution vector, no Y·V
        post-multiply."""
        _v, j = system.solve()
        out = []
        for k in self.driven_port_idx:
            col, e = system.terminations[k]
            if j[col] == 0:
                # Open-circuited source — no current path from the port
                # (e.g. a matching-network series capacitor slider at 0 F,
                # which is an open, not an absent element). The physical
                # driving-point impedance is ∞; report it as a clean real
                # infinity instead of dividing by zero (numpy would warn
                # and produce inf+nanj). Issue #289.
                out.append(complex(float("inf"), 0.0))
            else:
                out.append(complex(e / j[col]))
        return out

    def driven_impedance(self, Y_real, wavelength):
        """Convenience: stamp branches onto the raw real-port Y and reduce
        to the driven-port impedance(s) in one call."""
        return self.impedance_from_y(self.apply_branches(Y_real, wavelength))

"""Engine-agnostic reduction of a port-based `Network` spec to driven-port
impedances, on top of a raw multiport antenna admittance matrix.

Both MomwireEngine and PyNECEngine assemble the antenna's short-circuit Y at
the real (`PortAtEdge`) ports, then hand it here with a port-name -> matrix-
index map. This module stamps the network branches (`TL` / `Load`)
into the Y matrix and reduces it to the driven-port impedance(s). The only
engine-specific work is producing that raw Y and the index map; the linear
algebra here is identical regardless of which MoM solver produced Y.

This is the EZNEC-style approach: model transmission lines as a circuit
post-process on top of the field solution, rather than via NEC2's native
`tl_card`.
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


def tl_admittance_2x2(z0, length, wavelength, transposed=False):
    """Lossless ideal-TL nodal admittance between its two terminals.

    For electrical length θ = 2π·length/λ:
        Y_TL = 1/(j Z0 sin θ) · [[cos θ, -1], [-1, cos θ]]
    Singular at sin θ = 0 (TL is a half-wavelength multiple); raise
    rather than return garbage so callers can pick a different length.

    `transposed=True` models a crossed ("half-twist") line: port B's
    polarity is inverted, which flips the sign of the off-diagonal
    (transfer) terms only. This is the nodal-model equivalent of NEC2's
    negative-Z0 tl_card crossing, used by transposed-feeder arrays (LPDA,
    ZL-Special). Note it is NOT the same as a negative z0, which would
    (wrongly) negate the diagonal self terms too.
    """
    theta = 2.0 * np.pi * length / wavelength
    s, c = np.sin(theta), np.cos(theta)
    if abs(s) < 1e-12:
        raise ValueError(
            f"TL length {length} is ~kλ/2 at f={C_LIGHT / wavelength / 1e6:.4f} MHz "
            "(sin βl ≈ 0); admittance is singular"
        )
    scale = 1.0 / (1j * z0 * s)
    off = 1.0 if transposed else -1.0
    return scale * np.array([[c, off], [off, c]], dtype=np.complex128)


def twoport_admittance_2x2(r, l, c, omega):
    """Nodal admittance of a lumped series R+jωL+1/(jωC) bridging two ports.

    A series impedance Z = R + jωL + 1/(jωC) between terminals a and b has the
    2×2 short-circuit admittance
        Y = (1/Z) · [[1, -1], [-1, 1]]
    — current 1/Z flows a→b under a unit differential, and none into an
    external short at either node beyond that branch. This is the same shape as
    NEC2's `nt_card` takes directly (Y11=Y22=1/Z, Y12=Y21=−1/Z), which is why
    the native-`nt_card` oracle path and this stamp agree by construction.

    A series-LC short (Z → 0 at ω₀ = 1/√(LC)) makes Y singular; the two nodes
    are then hard-shorted together. Raise rather than emit inf so the caller
    can pick different element values — callers never depend on the short
    limit (unlike the parallel-LC trap, which the Load path handles).
    """
    if c == 0:
        # A 0 F capacitor is an open in the series path (infinite reactance):
        # the branch carries no current, so it contributes no coupling. Return
        # the zero stamp rather than forming 1/(jωC) and dividing by zero.
        return np.zeros((2, 2), dtype=np.complex128)
    z = _series_rlc_impedance(r, l, c, omega)
    if abs(z) < 1e-15:
        raise ValueError(
            "TwoPort series impedance ≈ 0 (short circuit): a 0 Ω / 0 H element, "
            "an all-omitted branch, or series-LC resonance shorts the two ports. "
            "A lossless short is not a finite admittance stamp — express it as a "
            "direct connection (drive the shared node) or use a small nonzero "
            "value. General ideal-short handling is tracked in issue #285 (MNA)."
        )
    y = 1.0 / z
    return y * np.array([[1.0, -1.0], [-1.0, 1.0]], dtype=np.complex128)


def shunt_admittance(r, l, c, omega, parallel=False):
    """Scalar admittance of a lumped R/L/C shunt from a port to the common
    reference, stamped onto the port diagonal (``Y[k,k] += y``).

    series (default): y = 1/(R + jωL + 1/(jωC)) — single C → jωC, single L →
        1/(jωL), series LC → shunt trap.
    parallel:         y = 1/R + 1/(jωL) + jωC — parallel-LC tank, → 0 at
        resonance (open shunt).

    A series-LC short (Z → 0) is a hard short of the port to common; raise
    rather than emit inf so the caller can pick different element values."""
    if parallel:
        return _parallel_rlc_admittance(r, l, c, omega)
    if c == 0:
        # A 0 F shunt capacitor is an open shunt (infinite reactance): no
        # element, y = 0. The natural "inert" limit of a matching-network
        # slider — return it rather than dividing by zero forming 1/(jωC).
        return 0.0 + 0.0j
    z = _series_rlc_impedance(r, l, c, omega)
    if abs(z) < 1e-15:
        raise ValueError(
            "Shunt series impedance ≈ 0 (short to common): a 0 Ω / 0 H element "
            "or series-LC resonance shorts the port to the reference. A lossless "
            "short is not a finite admittance stamp — remove the branch or use a "
            "small nonzero value. General handling is tracked in issue #285 (MNA)."
        )
    return 1.0 / z


# ---------------------------------------------------------------------------
# MNA (Modified Nodal Analysis) core — issue #285.
#
# The node space is the existing port space: one node per port (real feeds
# first, virtual ports after), every node's voltage referenced to the common
# return (the datum). The datum has no matrix row — every port's second
# terminal is bonded to it, which is the same convention the antenna's
# short-circuit multiport Y already assumes.
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


def _series_group2(a, b, r, l, c, omega, emf=0j):
    """Group-2 stamp of a series R + jωL + 1/(jωC) (+ optional EMF) between
    nodes a and b. A 0 F capacitor is an open in the series path (infinite
    reactance) → admittance form with y = 0 (the branch carries no current).
    Every other value combination has finite z — including the ideal short
    z = 0 (0 Ω, 0 H, all-omitted, or exact series-LC resonance), which is
    the degenerate case the old admittance-only stamps had to raise on."""
    if c is not None and c == 0:
        return _Group2Element(a, b, c_v=0j, c_j=1.0 + 0j, e=0j)
    z = _series_rlc_impedance(r, l, c, omega)
    return _Group2Element(a, b, c_v=1.0 + 0j, c_j=z, e=emf)


class MNASystem:
    """Assembled MNA system ``[[G, B], [Cᵀ, D]] · [v; j] = [i_ext; e]``.

    ``v`` — node voltages vs. the datum (one per port, real feeds first);
    ``j`` — Group-2 branch currents. ``i_ext`` is zero at every node (all
    external injections enter through Group-2 source branches).

    ``terminations`` maps a port node index → ``(column, emf)`` for the
    per-port source/load termination branch (see
    ``NetworkReducer._assemble_mna``); its current ``j[column]`` is the
    current the termination delivers INTO the node, so a driven port's
    impedance is ``emf / j[column]`` read straight off the solution.
    """

    def __init__(self, G, elements, terminations):
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
        self._solution = None

    def solve(self):
        """Solve once (cached); returns ``(v, j)``."""
        if self._solution is None:
            x = np.linalg.solve(self.A, self.rhs)
            self._solution = (x[: self.n_nodes], x[self.n_nodes :])
        return self._solution


class NetworkReducer:
    """Stamps a `Network`'s branches onto a raw real-port Y and reduces to
    the driven-port impedance(s).

    Construct with the network spec, a ``port_to_idx`` mapping every port
    name (real and virtual) to its row/column in the augmented Y matrix, and
    ``n_total_ports`` (real feeds + virtual ports). Real ports must occupy
    indices ``0..n_real-1`` in the same order as the raw Y handed to
    :meth:`apply_branches`; virtual ports come after.
    """

    def __init__(self, network, port_to_idx, n_total_ports, formulation="admittance"):
        # formulation: "admittance" (legacy: bare nodal Y + hand-rolled
        # boundary conditions) or "mna" (Modified Nodal Analysis, issue #285).
        # Both produce the same observable behavior on finite-element
        # networks; only MNA can stamp ideal shorts / 0 Ω / 0 H elements.
        # The flag exists for side-by-side bring-up and goes away once the
        # default flips to MNA.
        if formulation not in ("admittance", "mna"):
            raise ValueError(f"unknown formulation {formulation!r}")
        self.formulation = formulation
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

        # A Load on a port modifies the MoM Z-diagonal of that segment via
        # Sherman-Morrison (equivalent to NEC2's ld_card on segment k). The
        # right boundary condition at a loaded port is V_external = 0 (no
        # source attached to the segment's external terminal) — NOT
        # I_external = 0, which is the right BC for TL passive ports. With
        # I_ext = 0 forced, the Sherman-Morrison update's effect on the
        # driven-port impedance cancels out algebraically (you can derive
        # it: V_passive picks up a factor (1 − α·Y_kk) that divides out).
        # So track loaded ports separately and pin their V = 0 in the
        # reduction. They take precedence over the floating-passive default.
        self.loaded_port_idx = set()
        for br in network.branches:
            if isinstance(br, Load):
                self.loaded_port_idx.add(port_to_idx[br.port])

    @property
    def n_driven(self):
        return len(self.driven_port_idx)

    # ----- MNA formulation (issue #285) -----

    def _assemble_mna(self, Y_real, wavelength):
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
            row v_k + Z_L·j = E is exactly the Thevenin boundary condition
            the legacy `excited_state` hand-coded, and its current j is the
            delivered port current — so the driven-point impedance E/j and
            the load dissipation (E − v_k)·j* both read off the solution.
            Driven-only ports (Z_L = 0) degenerate to the ideal voltage
            source pin v_k = E; loaded-only ports (E = 0) to the series
            load termination v_k = −Z_L·j.

        Ports that are neither driven, loaded, nor touched by a branch keep
        plain KCL with zero injection — the legacy floating (I_ext = 0) BC.
        """
        omega = 2.0 * np.pi * C_LIGHT / wavelength
        n = self.n_total_ports
        G = np.zeros((n, n), dtype=np.complex128)
        n_real = Y_real.shape[0]
        G[:n_real, :n_real] = Y_real

        elements = []
        loads_by_node = {}
        for br in self.network.branches:
            if isinstance(br, TL):
                a, b = self.port_to_idx[br.a], self.port_to_idx[br.b]
                G[np.ix_([a, b], [a, b])] += tl_admittance_2x2(
                    br.z0, br.length, wavelength, transposed=br.transposed
                )
            elif isinstance(br, TwoPort):
                a, b = self.port_to_idx[br.a], self.port_to_idx[br.b]
                elements.append(_series_group2(a, b, br.r, br.l, br.c, omega))
            elif isinstance(br, Shunt):
                k = self.port_to_idx[br.port]
                if br.parallel:
                    G[k, k] += _parallel_rlc_admittance(br.r, br.l, br.c, omega)
                else:
                    elements.append(_series_group2(k, None, br.r, br.l, br.c, omega))
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

        return MNASystem(G, elements, terminations)

    def _mna_impedances(self, system):
        """Driven-point impedance per Driven source: Z = E / j_term, the
        termination EMF over its delivered current — read straight off the
        solution vector, no Y·V post-multiply."""
        _v, j = system.solve()
        out = []
        for k in self.driven_port_idx:
            col, e = system.terminations[k]
            out.append(complex(e / j[col]))
        return out

    def _mna_excited_state(self, system):
        """(V, efficiency, p_in) from one MNA solve — see `excited_state`
        for the meaning of the readouts. The termination branches carry the
        physical port currents, so source input power and load dissipation
        are direct sums over them:

            p_in   = ½ Σ Re(E_k · j_k*)          (E = 0 terms vanish)
            p_diss = ½ Σ Re((E_k − v_k) · j_k*)  (drop across the load part
                                                  is Z_L·j, so this is
                                                  ½·Re(Z_L)·|j|² without
                                                  ever forming a trap's ∞)
        """
        v, j = system.solve()
        p_in = 0.0
        p_diss = 0.0
        for k, (col, e) in system.terminations.items():
            p_in += 0.5 * float(np.real(e * np.conj(j[col])))
            p_diss += 0.5 * float(np.real((e - v[k]) * np.conj(j[col])))
        efficiency = 1.0 if p_in <= 0.0 else max(0.0, min(1.0, 1.0 - p_diss / p_in))
        return v.copy(), efficiency, p_in

    # ----- legacy admittance formulation -----

    def apply_loads(self, Y, omega):
        """Apply every Load branch as a Sherman-Morrison rank-1 update on
        the real-port Y — the network-level equivalent of NEC2's `ld_card`
        modifying the segment's MoM Z[k,k].

        The update has two algebraically-identical forms, dual under
        Z_L ↔ y_L = 1/Z_L:

            impedance:   Y − Z_L/(1 + Z_L·Y_kk) · outer(Y[:,k], Y[k,:])
            admittance:  Y − 1/(y_L + Y_kk)     · outer(Y[:,k], Y[k,:])

        Each Load mode has a resonance where one form divides by an
        intermediate infinity while the other stays finite, so we pick the
        form whose denominator is bounded at that mode's resonance:

          - Parallel-LC trap: Z_L→∞ at ω₀ (open circuit). Use the
            ADMITTANCE form — y_L is the tank admittance, →0 at ω₀, giving
            coefficient 1/Y_kk (the open-circuit Schur complement).
          - Series-LC: Z_L→0 at ω₀ (short circuit = unbroken wire). Use the
            IMPEDANCE form — coefficient →0, i.e. no stamp.

        This way neither path ever forms or tests for infinity.
        """
        Y = Y.copy()
        for br in self.network.branches:
            if not isinstance(br, Load):
                continue
            port = self.network.ports[br.port]
            if not isinstance(port, PortAtEdge):
                raise ValueError(
                    f"Load on virtual port {br.port!r}: a Load is a series "
                    "impedance on an antenna segment, which only PortAtEdge has"
                )
            k = self.port_to_idx[br.port]
            y_col = Y[:, k].copy()

            if br.parallel:
                # Admittance form: y_L is the parallel-LC tank admittance,
                # cleanly 0 at trap resonance (the open-circuit point).
                y_l = load_series_admittance(br, omega)
                denom = y_l + Y[k, k]
                if abs(denom) < 1e-15:
                    raise ValueError(
                        f"Load on port {br.port!r}: y_L + Y[k,k] ≈ 0 (singular)"
                    )
                Y -= np.outer(y_col, y_col) / denom
            else:
                # Impedance form: Z_L is 0 at series-LC resonance (a short
                # = unbroken wire), where the coefficient vanishes anyway.
                z_l = load_impedance(br, omega)
                if z_l == 0:
                    continue
                denom = 1.0 + z_l * Y[k, k]
                if abs(denom) < 1e-15:
                    raise ValueError(
                        f"Load on port {br.port!r}: 1 + Z_L·Y[k,k] ≈ 0 (singular)"
                    )
                Y -= (z_l / denom) * np.outer(y_col, y_col)
        return Y

    def _augment_with_lines(self, Y, wavelength):
        """Pad the real-port Y to all ports and stamp the TL branches.

        Loads are NOT stamped here: for the impedance reduction they are folded
        into the real-port Y by `apply_loads` (called first by `apply_branches`),
        and for the current solve they are imposed as explicit series-impedance
        boundary conditions by `excited_state`. Either way the line stamping is
        identical, so it lives here and both paths share it."""
        n_total = self.n_total_ports
        Y_full = np.zeros((n_total, n_total), dtype=np.complex128)
        n_real = Y.shape[0]
        Y_full[:n_real, :n_real] = Y
        for br in self.network.branches:
            if isinstance(br, TL):
                a, b = self.port_to_idx[br.a], self.port_to_idx[br.b]
                y_tl = tl_admittance_2x2(
                    br.z0, br.length, wavelength, transposed=br.transposed
                )
                Y_full[np.ix_([a, b], [a, b])] += y_tl
            elif isinstance(br, Load):
                continue  # not a line; see apply_loads / excited_state
            elif isinstance(br, TwoPort):
                # A lumped 2-port is an explicit admittance stamp exactly like
                # a TL — same [[·,·],[·,·]] into Y_full at the (a,b) pair — so
                # it inherits the TL passive-port BC (I_ext=0, handled in
                # resolve_voltages / excited_state). No Sherman-Morrison fold
                # (that is the Load path); the branch never redefines a port
                # variable, so no V=0 pin is needed.
                a, b = self.port_to_idx[br.a], self.port_to_idx[br.b]
                omega = 2.0 * np.pi * C_LIGHT / wavelength
                y_2p = twoport_admittance_2x2(br.r, br.l, br.c, omega)
                Y_full[np.ix_([a, b], [a, b])] += y_2p
            elif isinstance(br, Shunt):
                # A shunt to common is a 1-port admittance on the node diagonal
                # — the port's return terminal IS the reference, so no ground
                # node is needed. Undriven shunt ports keep the floating
                # (I_ext=0) BC; driven ones (the L-match input) stay pinned.
                k = self.port_to_idx[br.port]
                omega = 2.0 * np.pi * C_LIGHT / wavelength
                Y_full[k, k] += shunt_admittance(
                    br.r, br.l, br.c, omega, parallel=br.parallel
                )
            else:
                raise NotImplementedError(f"branch type {type(br).__name__}")
        return Y_full

    def apply_branches(self, Y, wavelength):
        """Pad Y to include virtual ports, then stamp every network branch.

        Y is the raw real-port admittance, shape (n_real, n_real); the
        return is a (n_total, n_total) augmented matrix with zeros in the
        virtual-port rows/cols (no antenna admittance) plus the branch
        contributions.

        Order matters: Load branches modify the antenna's real-port Y first
        (matching ld_card's effect inside the MoM), then TL branches stamp
        on the loaded Y. A TL connected to a loaded port sees the external
        side of the load.

        Under the MNA formulation the return is an `MNASystem` instead of a
        matrix; it composes with `impedance_from_y` / `resolve_voltages`
        exactly as the matrix does.
        """
        if self.formulation == "mna":
            return self._assemble_mna(Y, wavelength)
        omega = 2.0 * np.pi * C_LIGHT / wavelength
        Y = self.apply_loads(Y, omega)
        return self._augment_with_lines(Y, wavelength)

    def resolve_voltages(self, Y_total):
        """Return the (n_total,) voltage vector after solving the network:
        driven ports at their applied voltages, every other port floating
        with I_ext = 0.

        Loaded ports: the legacy admittance path pins V = 0 (the load is
        folded into Y by `apply_loads`, so the pin is correct for the
        impedance readout but shorts the load for anything else); the MNA
        path returns the PHYSICAL gap voltage V_k = V_src − Z_L·I_k — the
        same voltage `excited_state` reports, because both readouts come
        from the one MNA solve."""
        if self.formulation == "mna":
            v, _j = Y_total.solve()
            return v.copy()
        n = Y_total.shape[0]
        driven = list(self.driven_port_idx)
        floating = [
            i for i in range(n) if i not in driven and i not in self.loaded_port_idx
        ]
        v_driven = np.array(self.driven_voltages, dtype=np.complex128)
        V = np.zeros(n, dtype=np.complex128)
        V[driven] = v_driven
        # V[loaded] = 0 by zeros init.
        if floating:
            # I_ext = 0 at floating ports: Y_ff V_f = -Y_fd V_d - Y_fl V_l.
            # V_l = 0 so the last term drops.
            Y_ff = Y_total[np.ix_(floating, floating)]
            Y_fd = Y_total[np.ix_(floating, driven)]
            V[floating] = np.linalg.solve(Y_ff, -Y_fd @ v_driven)
        return V

    def excited_state(self, Y_real, wavelength):
        """Physical port voltages + radiation efficiency for the CURRENT-
        DISTRIBUTION / far-field solve.

        `resolve_voltages` pins loaded ports at V=0 and folds the load into the
        Y matrix via Sherman-Morrison (`apply_loads`): correct for the driving-
        point impedance, but WRONG for the radiated field. Forcing V=0 at a
        loaded port makes the load a SHORT, so a terminated antenna (rhombic,
        T2FD) never develops the traveling wave that makes it unidirectional.
        Here we instead impose the physical series-load boundary condition
        ``V_k = -Z_L,k * I_k`` at each loaded port, so the load shapes the
        current the same way NEC2's ld_card does.

        Returns ``(V_full, efficiency, p_in)``:
          V_full      -- (n_total,) port voltages to force in the excited solver
          efficiency  -- P_radiated / P_input = 1 - P_dissipated / P_input, the
                         fraction of input power radiated rather than burned in
                         resistive loads. A load-free / lossless network
                         returns 1.0.
          p_in        -- input power 1/2 Re(Σ V_src · I*) in watts, the gain
                         normaliser (gain = 4π·U/P_in); it already includes the
                         power burned in resistive loads.
        """
        if self.formulation == "mna":
            return self._mna_excited_state(self._assemble_mna(Y_real, wavelength))
        omega = 2.0 * np.pi * C_LIGHT / wavelength
        # Lines stamped, loads left OUT -- they are imposed as BCs below, not
        # folded into Y (that is the resolve_voltages/impedance path).
        Y = self._augment_with_lines(Y_real, wavelength)
        n = self.n_total_ports

        # Per-port source EMF and series-load impedance. A port may carry
        # BOTH (a driven segment with a series loading element, e.g. the
        # centre-loaded short dipole) -- the Thevenin BC below covers it.
        v_src = dict(zip(self.driven_port_idx, self.driven_voltages))
        z_load = {
            self.port_to_idx[br.port]: load_impedance(br, omega)
            for br in self.network.branches
            if isinstance(br, Load)
        }

        # A pure source (EMF, no series load) pins V_k = V_src,k and is known.
        # Every other port is an unknown with a single linear BC:
        #   load present:  V_k + Z_L,k * (Y V)_k = V_src,k   (Thevenin; V_src=0
        #                                                      if undriven)
        #   no load:                  (Y V)_k    = 0         (floating, I_ext=0)
        pinned = [k for k in v_src if k not in z_load]
        unknown = [k for k in range(n) if k not in pinned]
        V = np.zeros(n, dtype=np.complex128)
        for k in pinned:
            V[k] = v_src[k]
        if unknown:
            pos = {p: j for j, p in enumerate(unknown)}
            v_pin = np.array([V[k] for k in pinned], dtype=np.complex128)
            A = np.zeros((len(unknown), len(unknown)), dtype=np.complex128)
            rhs = np.zeros(len(unknown), dtype=np.complex128)
            for row, k in enumerate(unknown):
                # (Y V)_k = Y[k,unknown]·V_unknown + Y[k,pinned]·V_pin; the
                # pinned part is known and moves to the right-hand side.
                known = Y[k, pinned] @ v_pin if pinned else 0.0
                if k in z_load:
                    A[row, pos[k]] += 1.0
                    A[row, :] += z_load[k] * Y[k, unknown]
                    rhs[row] = v_src.get(k, 0.0 + 0.0j) - z_load[k] * known
                else:
                    A[row, :] += Y[k, unknown]
                    rhs[row] = -known
            V[unknown] = np.linalg.solve(A, rhs)

        # Efficiency = P_radiated / P_input from the resulting port currents.
        # Sources deliver P_in = 1/2 Re(V_src · I*); resistive loads burn
        # P_diss = 1/2 Re(Z_L) |I|². Reactive loads (a loading coil) burn
        # nothing, so they leave efficiency at 1.0.
        current = Y @ V
        p_in = 0.5 * float(np.real(sum(v_src[k] * np.conj(current[k]) for k in v_src)))
        p_diss = 0.5 * float(
            sum(np.real(z_load[k]) * abs(current[k]) ** 2 for k in z_load)
        )
        efficiency = 1.0 if p_in <= 0.0 else max(0.0, min(1.0, 1.0 - p_diss / p_in))
        return V, efficiency, p_in

    def impedance_from_y(self, Y_total):
        """Driven-port impedance from an `apply_branches` result.

        MNA: Z = E / j_term straight off the solution vector. Legacy: solve
        the network for V (loaded ports pinned at V=0, floating ports
        satisfying I_ext=0, driven ports at their applied V), then read
        I_driven = (Y_total @ V)_driven."""
        if self.formulation == "mna":
            return self._mna_impedances(Y_total)
        V = self.resolve_voltages(Y_total)
        I = Y_total @ V
        return [complex(V[i] / I[i]) for i in self.driven_port_idx]

    def driven_impedance(self, Y_real, wavelength):
        """Convenience: stamp branches onto the raw real-port Y and reduce
        to the driven-port impedance(s) in one call."""
        return self.impedance_from_y(self.apply_branches(Y_real, wavelength))

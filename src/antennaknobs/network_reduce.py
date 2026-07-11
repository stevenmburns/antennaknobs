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


class NetworkReducer:
    """Stamps a `Network`'s branches onto a raw real-port Y and reduces to
    the driven-port impedance(s).

    Construct with the network spec, a ``port_to_idx`` mapping every port
    name (real and virtual) to its row/column in the augmented Y matrix, and
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
        """
        omega = 2.0 * np.pi * C_LIGHT / wavelength
        Y = self.apply_loads(Y, omega)
        return self._augment_with_lines(Y, wavelength)

    def resolve_voltages(self, Y_total):
        """Return the (n_total,) voltage vector after solving the network:
        driven ports at their applied voltages, loaded ports pinned at V=0,
        every other port floating with I_ext = 0."""
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
        """Driven-port impedance: solve the network for V (loaded ports
        pinned at V=0, floating ports satisfying I_ext=0, driven ports at
        their applied V), then read I_driven = (Y_total @ V)_driven."""
        V = self.resolve_voltages(Y_total)
        I = Y_total @ V
        return [complex(V[i] / I[i]) for i in self.driven_port_idx]

    def driven_impedance(self, Y_real, wavelength):
        """Convenience: stamp branches onto the raw real-port Y and reduce
        to the driven-port impedance(s) in one call."""
        return self.impedance_from_y(self.apply_branches(Y_real, wavelength))

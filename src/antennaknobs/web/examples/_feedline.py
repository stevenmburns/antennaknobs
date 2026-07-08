"""Feedline-network utilities used by multi-band antennas in daisy-chain
drive mode.

The single function `daisy_chain_z_in` takes the antenna's open-circuit
N-port Z matrix and stitches it together with N-1 50Ω transmission-line
jumpers, returning the single driving-point impedance the rig sees at
the main-feed end. Port 0 is the main-feed connection; ports 1..N-1
are subsequent stops along the chain; port N-1 is the open end.

Usage from momwire: build Y_sc via `BSplineSolver.compute_y_matrix`,
invert to get Z_oc, pass to `daisy_chain_z_in`. PyNEC's TL card path
solves the same problem natively (no Python-side math) — this helper
is just for the momwire half.
"""

from __future__ import annotations

import numpy as np

_C_LIGHT = 299_792_458.0


def daisy_chain_z_in(
    z_oc: np.ndarray,
    jumper_lengths_m: list[float],
    freq_mhz: float,
    z0_ohms: float = 50.0,
) -> complex:
    """Driving-point impedance at port 0 with the chain feedline applied.

    z_oc: N×N open-circuit impedance matrix of the antenna (V = Z·I).
    jumper_lengths_m: length-(N-1) sequence of lossless 50Ω jumpers
        connecting port i to port i+1 along the chain.
    freq_mhz: operating frequency in MHz.
    z0_ohms: characteristic impedance of the jumpers (50 by default).

    Returns the complex Z_in seen at port 0 when current is injected
    there and port N-1 is left open.

    Math: each lossless TL segment of length L contributes nodal-
    admittance terms y11 = y22 = -j cot(βL)/Z0 and y12 = y21 =
    j csc(βL)/Z0 between the two endpoint nodes. Adding those to
    Y_ant = inv(Z_oc) gives the combined nodal Y matrix; Z_in =
    inv(Y_combined)[0, 0] when the input current is at node 0 and
    all other nodes have no external excitation (open end at N-1
    is implicit — its KCL row has zero external current).
    """
    n_ports = z_oc.shape[0]
    if z_oc.shape != (n_ports, n_ports):
        raise ValueError(f"z_oc must be square; got shape {z_oc.shape}")
    if len(jumper_lengths_m) != n_ports - 1:
        raise ValueError(
            f"need {n_ports - 1} jumper lengths for {n_ports} ports, "
            f"got {len(jumper_lengths_m)}"
        )
    if n_ports == 1:
        return complex(z_oc[0, 0])

    omega = 2.0 * np.pi * freq_mhz * 1e6
    beta = omega / _C_LIGHT

    y = np.linalg.inv(z_oc)

    for i, length in enumerate(jumper_lengths_m):
        bl = beta * length
        sin_bl = np.sin(bl)
        if abs(sin_bl) < 1e-12:
            # Quarter-wave-multiple — the line shorts/opens through;
            # numerically catastrophic and physically degenerate. Nudge
            # the length a hair to dodge the singularity. Real antennas
            # don't sit exactly here either; this only matters if the
            # user dials the slider onto it.
            bl += 1e-9
            sin_bl = np.sin(bl)
        cos_bl = np.cos(bl)
        y_self = -1j * cos_bl / (z0_ohms * sin_bl)
        y_mut = 1j / (z0_ohms * sin_bl)
        y[i, i] += y_self
        y[i + 1, i + 1] += y_self
        y[i, i + 1] += y_mut
        y[i + 1, i] += y_mut

    # I_ext = [Iin, 0, ..., 0]; Iin = 1 → V = inv(Y) · I_ext → V[0] = Z_in.
    z_combined = np.linalg.inv(y)
    return complex(z_combined[0, 0])

"""The multiport-Y route, shared by the card-deck engines (AK#1280, AK#1678).

A network no card expresses (a line, a transformer, a virtual driver, a
self-tuning tuner, ...) is solved outside the field solve: the engine measures
the antenna's short-circuit admittance Y at its real ports, one run per port,
and the shared `NetworkReducer` stamps the network on it. PyNEC has done this
since #575, NEC-5 since #1280, NEC-2 since #1678.

What differs between NEC-5 and NEC-2 is only how a port is ADDRESSED (NEC-5's
EX sits on a knot, NEC-2's on a segment centre), how a deck is written and how
a printout is read. Everything downstream of Y is the same arithmetic, and it
lives here so the two cannot drift: the port index map and the reducer, the
reduced impedance and sweep, the network-resolved drive with the power its
sources deliver, the budget with the engine's conductor loss folded in, the
per-source-watt gain factor, and the asymmetry backstop (AK#1689).

Every function takes the ENGINE and reads ``eng._compute_y_matrix`` and
``eng._reducer`` at call time, never a bound method captured earlier: the gates
replace an engine's ``_compute_y_matrix`` on the instance, and a captured one
would run the binary behind their back.
"""

from __future__ import annotations

from typing import NamedTuple

import numpy as np

from ..auto_match import design_freq_mhz, make_reducer
from ..network import PortVirtual
from ..network_reduce import C_LIGHT


def make_port_reducer(eng, network, real_names):
    """The engine's reducer over `network`, with its real ports first (in
    `real_names` order, which is Y's) and the virtual ports after them.

    A self-tuning tuner (AK#1646, #1661) is tuned from this engine's OWN port
    admittance, so the reducer's ``y_at`` calls back into the engine."""
    port_to_idx = {n: i for i, n in enumerate(real_names)}
    next_idx = len(real_names)
    for name, port in network.ports.items():
        if isinstance(port, PortVirtual):
            port_to_idx[name] = next_idx
            next_idx += 1
    return make_reducer(
        network,
        port_to_idx,
        next_idx,
        y_at=lambda wl: eng._compute_y_matrix(wl),
        design_freq_mhz=design_freq_mhz(eng.builder),
    )


def reduced_impedance(eng, freq_mhz):
    """The driven impedances at `freq_mhz`, one per network source."""
    wl = C_LIGHT / (float(freq_mhz) * 1e6)
    return np.atleast_1d(eng._reducer.driven_impedance(eng._compute_y_matrix(wl), wl))


def reduced_impedance_sweep(eng, freqs):
    """(n_freqs, n_driven) driven impedances, one reduction per frequency: the
    antenna Y and every branch the reducer stamps are frequency-dependent, so a
    single multi-frequency printout cannot serve this route."""
    freqs = np.asarray(freqs, dtype=float)
    if freqs.ndim != 1 or freqs.size == 0:
        raise ValueError("freqs must be a 1-D non-empty array")
    out = [np.atleast_1d(reduced_impedance(eng, f)) for f in freqs]
    return np.array(out).reshape(freqs.size, -1)


class ReducedState(NamedTuple):
    """One frequency's reduction. ``zs`` is None unless it was asked for."""

    Y: np.ndarray
    wavelength: float
    V: np.ndarray
    zs: list | None
    efficiency: float
    p_in: float
    budget: list


def reduced_state(eng, freq_mhz, *, impedances=False) -> ReducedState:
    """Y once, then everything a single-deck reading needs from it: the voltage
    the network resolves at every real port (which is what drives the one
    structure deck), the source power and the network's own losses — and, with
    ``impedances``, the driven impedances too."""
    wl = C_LIGHT / (float(freq_mhz) * 1e6)
    Y = eng._compute_y_matrix(wl)
    red = eng._reducer
    zs = list(np.atleast_1d(red.driven_impedance(Y, wl))) if impedances else None
    V = red.resolve_voltages(red.apply_branches(Y, wl))
    _v, efficiency, p_in, budget = red.excited_state(Y, wl)
    return ReducedState(Y, wl, V, zs, efficiency, p_in, budget)


def fold_wire_loss(efficiency, p_in, net_budget, p_wire):
    """``(efficiency, budget rows)`` with the engine's conductor loss folded in.

    The network's input power and losses come from the reducer, which the
    structure deck cannot see; the wire loss comes from the deck, which the
    reducer cannot see. LOSSES ONLY in the rows (issue #1354)."""
    if p_wire > 0.0 and p_in > 0.0:
        efficiency = max(0.0, min(1.0, efficiency - p_wire / p_in))
    return efficiency, list(net_budget) + [("Wire loss", p_wire)]


def source_gain_factor(p_struct, p_source, error_cls):
    """P_structure / P_source, the factor turning a NEC gain per STRUCTURE watt
    into gain per SOURCE watt (AK#1637); 1.0 when `p_source` is None (the
    native route, where the structure's input power already is the source's).

    A NEC normalises gain by the power into the structure, the sum over its EX
    cards. On this route the network sits between the sources and those cards,
    and a lossy one burns its share first."""
    if p_source is None:
        return 1.0
    if p_source <= 0.0 or p_struct <= 0.0:
        raise error_cls(
            f"cannot normalise the pattern per source watt: structure "
            f"input {p_struct} W, source power {p_source} W"
        )
    return p_struct / p_source


# The gross-error backstop on Y's asymmetry (AK#1689). NOT a bookkeeping
# check: each engine checks its port bookkeeping DIRECTLY, run by run (NEC-5
# matches every source row to its card by tag and segment; NEC-2 checks the
# driven port's rows, voltages and currents), which needs no tolerance. The
# asymmetry itself is the formulation's: neither NEC tests by Galerkin, so its
# discrete Y is not symmetric by a mesh- and design-dependent amount
# (`multiband.hexbeam_5band` reads 1.96e-2 on NEC-2, on nec2c and PyNEC alike).
# A bar tuned to that number per engine was fragile and, once loosened to
# admit it, no longer caught the misreads it was for. So the measured value is
# kept as information (`_y_reciprocity_rel`), and only an asymmetry no solver
# produces on a sane mesh is refused. One bar for every engine.
Y_ASYMMETRY_BACKSTOP = 0.5


def y_asymmetry(Y, names):
    """``(rel, (name_i, name_j))``: the worst |Y[i,j] - Y[j,i]| relative to
    sqrt(|Y[i,i]| |Y[j,j]|), the ports' own scale (AK#1629), and the pair it is
    at (None when there is no pair to compare)."""
    n = len(names)
    worst = (0.0, None)
    for i in range(n):
        for j in range(i + 1, n):
            scale = np.sqrt(abs(Y[i, i]) * abs(Y[j, j]))
            if scale <= 0:
                continue
            rel = float(abs(Y[i, j] - Y[j, i]) / scale)
            if rel > worst[0]:
                worst = (rel, (names[i], names[j]))
    return worst


def check_reciprocity(Y, names, error_cls, engine):
    """Y's asymmetry (`y_asymmetry`), returned as information; raises
    `error_cls` only past `Y_ASYMMETRY_BACKSTOP`, read at call time.

    Y[i, j] and Y[j, i] come from DIFFERENT runs, so a gross misread shows up
    here — but agreement is not evidence the entries are right (an error that
    is itself symmetric passes, AK#1629), and a modest asymmetry is the
    formulation, not a defect. The port bookkeeping has its own direct check
    in each engine."""
    rel, pair = y_asymmetry(Y, names)
    if rel > Y_ASYMMETRY_BACKSTOP:
        a, b = pair
        raise error_cls(
            f"the multiport Y is not reciprocal: ports {a!r} and {b!r} "
            f"disagree by {rel:.3e} of the ports' own admittance, over the "
            f"{Y_ASYMMETRY_BACKSTOP:g} gross-error backstop. No {engine} "
            "formulation is that asymmetric on a sane mesh, and each run's port "
            "bookkeeping already passed its direct check, so suspect the "
            "printout or the mesh rather than the network."
        )
    return rel

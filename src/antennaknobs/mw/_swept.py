"""The swept multi-port admittance, assembled on AK's side (AK#2219).

momwire core streams one `PortSolution` per wavenumber; the stacked Y is
AK's. Each frequency's block takes its shape from that solution, so there
is no separate port count to disagree with it: momwire#1861 was exactly a
second copy of "how many ports does this solver produce" drifting from
the first.
"""

from __future__ import annotations

import numpy as np


def swept_y(solver, k_array) -> np.ndarray:
    """``(n_k, n_ports, n_ports)``: the port admittance at every wavenumber
    of `k_array`, in order; `[i]` is what `compute_y_matrix()` answers at
    `k_array[i]`.

    Streams core's per-k solutions (`_port_solutions_swept`, the generator
    momwire's own `compute_y_matrix_swept` reads) and keeps only each
    `y`, so the solution columns never accumulate across the sweep. That
    generator is private today; publishing it is #2219 phase 2. A solver
    without it falls back to its own swept Y."""
    k_array = np.asarray(k_array, dtype=float)
    stream = getattr(solver, "_port_solutions_swept", None)
    if stream is None:
        return np.asarray(solver.compute_y_matrix_swept(k_array), dtype=np.complex128)
    ys = [np.array(sol.y, dtype=np.complex128) for sol in stream(k_array)]
    if not ys:
        return np.zeros((0, 0, 0), dtype=np.complex128)
    if any(y.shape != ys[0].shape for y in ys):
        raise ValueError(
            "momwire's swept port solutions changed port count within one "
            "sweep: " + ", ".join(str(y.shape) for y in ys)
        )
    return np.stack(ys)

"""Where a PortSites build's cost over a rebuild goes, at 1 band and at 4.

On the benchmark design (`bench_coil_slide.CoilL`), each band's build is timed
by part, by wrapping momwire's own pieces:

- ``fill``: ``BSplineSolver._compute_Z_operator``, the Z fill;
- ``lu``: ``bspline._lu_solve``, one LU factorisation plus every right-hand
  side's back-solve (the ports, the basis sites and the KCL constraint
  columns), split below into the factorisation alone and the back-solves;
- ``reduce``: what ``_solve_with_kcl_ports`` does past ``_lu_solve`` (the
  KCL Schur or null-space reduction over all columns);
- ``rest``: everything else in the build (geometry, basis, readout).

Beside it: the swept rebuild of all the bands (``impedance_sweep``) and one
single-band ``compute_y_matrix`` per band (fill + factor + the port columns),
so (c), each band filled and factored alone, reads as ``per-band Y`` minus
``rebuild``, and (a) + (b), the site columns, as ``build`` minus ``per-band Y``.

    python scratch/port-sites-1915/build_breakdown.py
"""

import statistics
import time
from collections import defaultdict

import momwire.bspline as bs
import numpy as np
import scipy.linalg as sla
from bench_coil_slide import BANDS, GROUND, CoilL

from antennaknobs import port_sites
from antennaknobs.engines.momwire import MomwireEngine
from antennaknobs.web.optimize_bands import parse_bands

T = defaultdict(float)
SHAPES = []


def timed(name, fn):
    def wrapper(*a, **k):
        t0 = time.perf_counter()
        try:
            return fn(*a, **k)
        finally:
            T[name] += time.perf_counter() - t0

    return wrapper


def eng(pct):
    return MomwireEngine(
        CoilL(dict(CoilL.default_params, coil_pct=pct)),
        ground=GROUND,
        **port_sites.engine_kwargs(),
    )


def base_solver(e, f):
    s = e._make_solver(wavelength=e._wavelength_for(f))
    cls, kw = s._ak_construct
    feeds = list(kw["feeds"])
    moving = e._feed_names.index("coil")
    wire = int(feeds.pop(moving)[0])
    return cls(**{**kw, "feeds": feeds, "wavelength": e._wavelength_for(f)}), wire


def main():
    freqs = [b.freq_mhz for b in parse_bands(BANDS)]
    real_fill = bs.BSplineSolver._compute_Z_operator
    real_lu = bs._lu_solve
    real_kcl = bs.BSplineSolver._solve_with_kcl_ports
    lu_inner = {"t": 0.0}

    def lu(Z, rhs, **k):
        SHAPES.append((Z.shape[0], rhs.shape[1] if rhs.ndim == 2 else 1))
        t0 = time.perf_counter()
        try:
            return real_lu(Z, rhs, **k)
        finally:
            lu_inner["t"] += time.perf_counter() - t0

    bs.BSplineSolver._compute_Z_operator = timed("fill", real_fill)
    bs._lu_solve = lu

    def kcl(self, *a, **k):
        before = lu_inner["t"]
        t0 = time.perf_counter()
        try:
            return real_kcl(self, *a, **k)
        finally:
            dt = time.perf_counter() - t0
            T["lu"] += lu_inner["t"] - before
            T["reduce"] += dt - (lu_inner["t"] - before)

    bs.BSplineSolver._solve_with_kcl_ports = kcl
    for nb in (1, len(freqs)):
        fs = freqs[:nb]
        reps = []
        for i in range(7):
            pct = 20.0 + 7.3 * i
            e = eng(pct)
            T.clear()
            SHAPES.clear()
            t0 = time.perf_counter()
            for f in fs:
                s, wire = base_solver(e, f)
                s.port_sites(wire)
            build = time.perf_counter() - t0
            parts = dict(T)
            shapes = list(SHAPES)
            T.clear()
            t0 = time.perf_counter()
            for f in fs:
                e._make_solver(wavelength=e._wavelength_for(f)).compute_y_matrix()
            per_band_y = time.perf_counter() - t0
            T.clear()
            t0 = time.perf_counter()
            eng(pct + 0.05).impedance_sweep(fs)
            rebuild = time.perf_counter() - t0
            # The factorisation alone, on a matrix of the build's size.
            n = shapes[0][0]
            Z = np.asarray(
                np.random.default_rng(i).standard_normal((n, n))
                + 1j * np.random.default_rng(i + 1).standard_normal((n, n)),
                order="F",
            )
            Z += n * np.eye(n)
            t0 = time.perf_counter()
            for _ in fs:
                sla.lu_factor(Z.copy(order="F"), check_finite=False)
            factor = time.perf_counter() - t0
            reps.append((build, per_band_y, rebuild, parts, factor, shapes))
        med = statistics.median

        def m(key):
            return 1e3 * med(r[3].get(key, 0.0) for r in reps)

        build = 1e3 * med(r[0] for r in reps)
        per_band_y = 1e3 * med(r[1] for r in reps)
        rebuild = 1e3 * med(r[2] for r in reps)
        factor = 1e3 * med(r[4] for r in reps)
        fill, lu_t, red = m("fill"), m("lu"), m("reduce")
        print(f"{nb} band(s), Z {reps[0][5][0][0]}^2, rhs columns {reps[0][5][0][1]}:")
        print(f"  rebuild (swept)         {rebuild:8.2f} ms")
        print(
            f"  per-band compute_y      {per_band_y:8.2f} ms   (c) = {per_band_y - rebuild:+.2f}"
        )
        print(
            f"  build                   {build:8.2f} ms   (a)+(b) = {build - per_band_y:+.2f}"
        )
        print(f"    fill                  {fill:8.2f} ms")
        print(f"    LU factor (alone)     {factor:8.2f} ms")
        print(f"    back-solves           {lu_t - factor:8.2f} ms   (a)")
        print(f"    KCL reduction         {red:8.2f} ms   (b)")
        print(f"    rest                  {build - fill - lu_t - red:8.2f} ms")


if __name__ == "__main__":
    main()

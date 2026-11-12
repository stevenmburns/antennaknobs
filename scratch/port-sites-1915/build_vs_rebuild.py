"""What one PortSites build costs against one rebuild, on the benchmark design.

A trial whose base is new is either rebuilt (``impedance_sweep``, the swept
fill across the bands) or answered by building its `PortSites` (one solver
per band with the other ports configured, ``port_sites(wire)``). Prints the
median of a few repeats of each, per band count, and the single-frequency
``compute_y_matrix`` the build path is made of, so the gap can be read.

    python scratch/port-sites-1915/build_vs_rebuild.py
"""

import statistics
import time

from bench_coil_slide import BANDS, GROUND, CoilL

from antennaknobs import port_sites
from antennaknobs.engines.momwire import MomwireEngine
from antennaknobs.web.optimize_bands import parse_bands


def med(fn, n=9):
    """Median ms of ``fn(pct)`` over ``n`` distinct positions, so no cache of
    an earlier repeat answers it."""
    ts = []
    for i in range(n):
        t0 = time.perf_counter()
        fn(20.0 + 7.3 * i)
        ts.append(time.perf_counter() - t0)
    return 1e3 * statistics.median(ts)


def main():
    freqs = [b.freq_mhz for b in parse_bands(BANDS)]
    for nb in (1, len(freqs)):
        fs = freqs[:nb]

        def eng(pct=31.7):
            return MomwireEngine(
                CoilL(dict(CoilL.default_params, coil_pct=pct)),
                ground=GROUND,
                **port_sites.engine_kwargs(),
            )

        def rebuild(pct):
            eng(pct).impedance_sweep(fs)

        def build(pct):
            e = eng(pct)
            s = e._make_solver(wavelength=e._wavelength_for(fs[0]))
            cls, kw = s._ak_construct
            feeds = list(kw["feeds"])
            moving = e._feed_names.index("coil")
            wire = int(feeds.pop(moving)[0])
            for f in fs:
                cls(
                    **{**kw, "feeds": feeds, "wavelength": e._wavelength_for(f)}
                ).port_sites(wire)

        def single_y(pct):
            e = eng(pct)
            for f in fs:
                e._make_solver(wavelength=e._wavelength_for(f)).compute_y_matrix()

        print(
            f"{nb} band(s): rebuild {med(rebuild):8.2f} ms  "
            f"build {med(build):8.2f} ms  per-band compute_y_matrix {med(single_y):8.2f} ms"
        )


if __name__ == "__main__":
    main()

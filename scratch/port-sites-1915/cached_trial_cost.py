"""What a cached port-sites trial costs on the invented end-fed SimNEC deck.

The deck is `tests/test_ssn_port_sites_1915.py`'s station deck (seven wires,
296 segments, a fixed coil, a station chain of two stored .s2p blocks and two
coax runs; ``--plain`` takes the bare 162-segment antenna instead). After two
trials that find the moving port, every trial moves the capacitor's
percentage alone, so the session serves it from the cache: this times those
trials through the CLI's own sweep_fn at five bands, and prints a cProfile
top-15 of them.

    python scratch/port-sites-1915/cached_trial_cost.py
"""

import cProfile
import pstats
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tests"))

from test_ssn_port_sites_1915 import STATION_TEXT, TEXT

from antennaknobs import port_sites
from antennaknobs.band_opt import builder_sweep_fn
from antennaknobs.engines.momwire import MomwireEngine
from antennaknobs.file_designs import builder_from_text

FREQS = [6.95, 7.02, 7.1, 7.18, 7.25]


def main():
    station = "--plain" not in sys.argv
    design = builder_from_text(
        "invented_station.ssn" if station else "invented_flat_top.ssn",
        STATION_TEXT if station else TEXT,
    )
    s = port_sites.PortSitesSession()
    sweep = builder_sweep_fn(
        design(dict(design.default_params)), MomwireEngine, 50.0, port_sites=s
    )
    base = {"par_H_len": 17.3, "par_Cap_F": 83.0}
    sweep({**base, "par_Cap_Pct": 30.0}, FREQS)
    sweep({**base, "par_Cap_Pct": 31.0}, FREQS)
    assert s.counts["first"] == 1, s.summary()
    pcts = [32.0 + 0.37 * i for i in range(40)]
    ts = []
    for p in pcts[:20]:
        t0 = time.perf_counter()
        sweep({**base, "par_Cap_Pct": p}, FREQS)
        ts.append(time.perf_counter() - t0)
    g0 = time.perf_counter()
    sweep(
        {**base, "par_Cap_Pct": 40.0}, FREQS, grad_knobs={**base, "par_Cap_Pct": 40.0}
    )
    grad = time.perf_counter() - g0
    assert s.counts["fast"] >= 20, s.summary()
    print(
        f"cached trial, 5 bands: median {1e3 * statistics.median(ts):.2f} ms "
        f"(min {1e3 * min(ts):.2f}); with gradients of 3 knobs {1e3 * grad:.2f} ms"
    )
    pr = cProfile.Profile()
    pr.enable()
    for p in pcts[20:]:
        sweep({**base, "par_Cap_Pct": p}, FREQS)
    pr.disable()
    pstats.Stats(pr).sort_stats("cumulative").print_stats(15)
    if "--tottime" in sys.argv:
        pstats.Stats(pr).sort_stats("tottime").print_stats(25)
    if "--callers" in sys.argv:
        st = pstats.Stats(pr).sort_stats("cumulative")
        st.print_callers("_junction_cuts")
        st.print_callees("parse_ssn")


if __name__ == "__main__":
    main()

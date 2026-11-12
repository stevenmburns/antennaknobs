"""Measure the opt-in moved-load fast path (momwire#1915) in a multi-band optimize.

Invented geometry: an inverted L over Sommerfeld ground (eps_r 13, 5 mS/m),
fed at the ground contact, a coil on the horizontal top wire whose position
is the one knob (a percentage of the top wire's length), solved on bs2 at four
band frequencies. Four runs from the same start, same budget:

- ``snapped``: the coil position rounded to the nearest segment centre of the
  top wire before the build, the way a deck's LD card on a segment index
  places a load (main's behaviour for such a knob);
- ``split``: main's default engine; a position off a segment centre splits
  the top wire there (AK#1519), so the mesh moves with the knob;
- ``whole``: the whole-wire engine the fast path builds, solved by rebuild;
- ``fast``: the same whole-wire model through `port_sites.PortSitesSession`.

Prints the wall time per trial and in total, the answer and its objective,
and the session's tally. Run on a quiet machine:

    python scratch/port-sites-1915/bench_coil_slide.py
"""

import math
import time
from types import MappingProxyType

import numpy as np

from antennaknobs import AntennaBuilder, port_sites
from antennaknobs.band_opt import builder_sweep_fn
from antennaknobs.engines.momwire import MomwireEngine
from antennaknobs.network import Driven, Load, Network, PortOnWire
from antennaknobs.network import Wire as W
from antennaknobs.web.optimize_bands import optimize_bands, parse_bands

H = 7.0
TOP = 6.0
N_VERT = 61
N_TOP = 81
COIL_H = 5.0e-6
GROUND = ("finite", 13.0, 0.005)
BANDS = "5.33,5.36,5.40,5.43"
START = 37.0


class CoilL(AntennaBuilder):
    default_params = MappingProxyType(
        {
            "freq": 5.38,
            "design_freq": 5.38,
            "coil_pct": START,
            "snap": False,
            "h": H,
            "coil_uh": COIL_H * 1e6,
        }
    )

    def build_wires(self):
        return [
            W((0.0, 0.0, 0.0), (0.0, 0.0, self.h), n_seg=N_VERT, name="vert"),
            W((0.0, 0.0, self.h), (TOP, 0.0, self.h), n_seg=N_TOP, name="top"),
        ]

    def build_network(self):
        at = float(self.coil_pct) / 100.0
        if self.snap:
            at = (min(N_TOP, max(1, round(at * N_TOP + 0.5))) - 0.5) / N_TOP
        return Network(
            ports={
                "feed": PortOnWire("feed", wire="vert", at=0.0),
                "coil": PortOnWire("coil", wire="top", at=at),
            },
            branches=[Load(port="coil", r=0.9, l=self.coil_uh * 1e-6)],
            sources=[Driven(port="feed")],
        )


def run(label, *, snap=False, whole=False, fast=False):
    b = CoilL(dict(CoilL.default_params, snap=snap))
    session = port_sites.PortSitesSession() if fast else None
    kw = port_sites.engine_kwargs() if (whole and not fast) else {}

    def factory(builder, **extra):
        return MomwireEngine(builder, ground=GROUND, **{**kw, **extra})

    t0 = time.perf_counter()
    res = optimize_bands(
        {"coil_pct": START},
        [{"name": "coil_pct", "min": 5.0, "max": 85.0}],
        parse_bands(BANDS),
        sweep_fn=builder_sweep_fn(b, factory, 50.0, port_sites=session),
        max_evals=40,
    )
    wall = time.perf_counter() - t0
    pct = res["params"]["coil_pct"]
    seg_pos = pct / 100.0 * N_TOP + 0.5
    print(
        f"{label:8s} trials {res['n_solves']:3d}  total {wall:7.2f} s  "
        f"per trial {1e3 * wall / res['n_solves']:8.2f} ms  "
        f"coil_pct {pct:.6f} (segment-centre index {seg_pos:.3f})  "
        f"J {res['objective_before']:.6f} -> {res['objective_after']:.6f}  "
        f"worst SWR {res['worst_swr_after']:.6f}  stuck {res.get('stuck')}"
    )
    if session is not None:
        print("         ", session.summary())
    return res


def run3(label, *, fast=False):
    """The flat three-knob run: a geometry knob (the vertical's height), the
    coil's position and a network value (its inductance), whole-wire model."""
    b = CoilL(dict(CoilL.default_params))
    session = port_sites.PortSitesSession() if fast else None
    kw = {} if fast else port_sites.engine_kwargs()

    def factory(builder, **extra):
        return MomwireEngine(builder, ground=GROUND, **{**kw, **extra})

    t0 = time.perf_counter()
    res = optimize_bands(
        {"h": H, "coil_pct": START, "coil_uh": COIL_H * 1e6},
        [
            {"name": "h", "min": 6.5, "max": 7.5},
            {"name": "coil_pct", "min": 5.0, "max": 85.0},
            {"name": "coil_uh", "min": 3.0, "max": 7.0},
        ],
        parse_bands(BANDS),
        sweep_fn=builder_sweep_fn(b, factory, 50.0, port_sites=session),
        max_evals=60,
    )
    wall = time.perf_counter() - t0
    p = res["params"]
    print(
        f"{label:8s} trials {res['n_solves']:3d}  total {wall:7.2f} s  "
        f"per trial {1e3 * wall / res['n_solves']:8.2f} ms  "
        f"h {p['h']:.5f} coil_pct {p['coil_pct']:.5f} coil_uh {p['coil_uh']:.5f}  "
        f"J {res['objective_before']:.6f} -> {res['objective_after']:.6f}"
    )
    if session is not None:
        print("         ", session.summary())
    return res


def j_at(pct):
    """The run's balanced J (w = 0.5) of SWR at ``pct``, whole-wire model."""
    freqs = [b.freq_mhz for b in parse_bands(BANDS)]
    b = CoilL(dict(CoilL.default_params, coil_pct=pct))
    zs = np.asarray(
        MomwireEngine(b, ground=GROUND, **port_sites.engine_kwargs()).impedance_sweep(
            freqs
        )
    )[:, 0]
    g = np.abs((zs - 50.0) / (zs + 50.0))
    swr = (1 + g) / (1 - g)
    return 0.5 * swr.max() + 0.5 * swr.mean()


def neighbours(pct):
    """J at the continuous answer and at the two segment centres around it."""
    k = pct / 100.0 * N_TOP + 0.5
    lo, hi = math.floor(k), math.ceil(k)
    for label, p in (
        ("answer", pct),
        (f"centre {lo}", 100.0 * (lo - 0.5) / N_TOP),
        (f"centre {hi}", 100.0 * (hi - 0.5) / N_TOP),
    ):
        print(f"  {label:10s} {p:9.5f}%  J {j_at(p):.6f}")


def oracle(pcts):
    """Fast-path Z vs a whole-wire rebuild, per band, at positions."""
    freqs = [b.freq_mhz for b in parse_bands(BANDS)]
    s = port_sites.PortSitesSession()

    def eng(p):
        return MomwireEngine(
            CoilL(dict(CoilL.default_params, coil_pct=p)),
            ground=GROUND,
            **port_sites.engine_kwargs(),
        )

    s.sweep(eng(pcts[0] + 1.0), freqs)
    worst = 0.0
    for p in pcts:
        t0 = time.perf_counter()
        zf = s.sweep(eng(p), freqs)
        tf = time.perf_counter() - t0
        t0 = time.perf_counter()
        zr = np.asarray(eng(p).impedance_sweep(freqs))
        tr = time.perf_counter() - t0
        worst = max(worst, float(np.max(np.abs(zf - zr) / np.abs(zr))))
        ztxt = ", ".join(f"{z:.4f}" for z in zf[:, 0])
        print(
            f"  {p:7.3f}%  fast {1e3 * tf:7.2f} ms  rebuild {1e3 * tr:7.2f} ms  Z {ztxt}"
        )
    print(f"  worst relative |dZ| fast vs rebuild: {worst:.3e}; {s.summary()}")


def split_gap(pcts):
    """How far main's split mesh is from the whole-wire model, per position."""
    freqs = [b.freq_mhz for b in parse_bands(BANDS)]
    for p in pcts:
        b = CoilL(dict(CoilL.default_params, coil_pct=p))
        zs = np.asarray(MomwireEngine(b, ground=GROUND).impedance_sweep(freqs))
        zw = np.asarray(
            MomwireEngine(
                b, ground=GROUND, **port_sites.engine_kwargs()
            ).impedance_sweep(freqs)
        )
        print(
            f"  {p:7.3f}%  split vs whole max rel |dZ| {np.max(np.abs(zs - zw) / np.abs(zw)):.3e}"
        )


if __name__ == "__main__":
    assert port_sites.available(), port_sites.NO_PORT_SITES
    print("oracle:")
    oracle([23.17, 41.88, 52.03, 66.61, 79.45])
    print("split mesh vs whole wire:")
    split_gap([23.17, 41.88, 52.03, 66.61, 79.45])
    print("optimize:")
    for label, kw in (
        ("snapped", {"snap": True}),
        ("split", {}),
        ("whole", {"whole": True}),
        ("fast", {"fast": True}),
    ):
        res = run(label, **kw)
        if label == "fast":
            neighbours(res["params"]["coil_pct"])
    print("optimize, three knobs (geometry, position, network):")
    run3("whole")
    run3("fast", fast=True)

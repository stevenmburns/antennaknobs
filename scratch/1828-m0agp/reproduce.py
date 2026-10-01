"""M0AGP's "DX gain" table, reproduced (AK#1828 unit 4).

QRZ thread 1005128 (first post): a 160 m inverted L against a full-size
vertical, two radials 5 ft up over Average ground (13, 0.005), modelled on
NEC-5 through AutoEZ. DX gain is the power average of the gain over 2-10
degrees of elevation, 0.1 degree apart, back in dB; each inverted L is
reported relative to the vertical.

This runs the catalog's own pieces: `verticals.inverted_l:topband` (the
vertical section and the top wire in feet, two radials 5 ft up), the study's
metric (`an.ElevationWindow("DX gain", 2, 10, step=0.1)`) read through
`antennaknobs.metrics` exactly as `analyze` reads it, and the engines through
the CLI's own factory over Sommerfeld finite ground. The study's
`an.Hold("resonance", adjust=("horiz_ft",))` is the framework's step 6 and
does not run yet, so the hold is done here by hand: at each vertical section
the top wire is cut so that X = 0 (Brent on the engine's own reactance), and
the vertical is cut for resonance with no top wire.

His azimuth is not stated, so each point is read on every mode: PEAK_AZ (the
pattern's peak azimuth), MEAN_AZ (the azimuth average), and fixed cuts at 0
(along a radial, broadside to the top wire), 90 (toward the top wire's far
end) and 270 (away from it). The geometry: riser along z, top wire along +y,
radials along +x and -x.

Usage: python reproduce.py ENGINE [OUT.json [FREQ_MHZ]]
(ENGINE: nec5 or momwire:bspline; FREQ_MHZ the measurement frequency, the
variant's own 1.83 when not given). NEC5_EXE must point at the NEC-5 binary
for nec5.
"""

from __future__ import annotations

import json
import sys
import time

from scipy.optimize import brentq

import antennaknobs.analyses as an
from antennaknobs import metrics as mx
from antennaknobs.cli import get_builder, make_engine_factory, parse_ground

DESIGN = "verticals.inverted_l:topband"
TABLE = {  # vertical section (ft): M0AGP's DX gain vs the vertical (dB)
    100: -0.26,
    90: -0.45,
    80: -0.72,
    70: -1.10,
    60: -1.66,
    50: -2.51,
    40: -3.84,
    30: -6.54,
    20: -9.64,
}
MODES = {
    "PEAK_AZ": an.PEAK_AZ,
    "MEAN_AZ": an.MEAN_AZ,
    "az0": 0.0,
    "az90": 90.0,
    "az270": 270.0,
}


FREQ: float | None = None


def builder(vert_ft: float, horiz_ft: float):
    b = get_builder(DESIGN)()
    b.vert_ft = float(vert_ft)
    b.horiz_ft = float(horiz_ft)
    if FREQ is not None:
        b.freq = FREQ
    return b


def reactance(factory, vert_ft, horiz_ft) -> float:
    return float(factory(builder(vert_ft, horiz_ft)).impedance()[0].imag)


def resonate_top(factory, vert_ft: float) -> float:
    """The top wire (ft) that makes the feed resonant at this vertical."""
    # The FIRST resonance (the quarter-wave one): scan up from a stub in 5 ft
    # steps to the first sign change of X, then Brent inside it. Further out
    # the wire passes its half-wave antiresonance, where X changes sign the
    # other way, so a wide bracket can hold no root or the wrong one.
    lo, f_lo = 1.0, reactance(factory, vert_ft, 1.0)
    while lo < 250.0:
        hi = lo + 5.0
        f_hi = reactance(factory, vert_ft, hi)
        if f_lo < 0 <= f_hi:
            return brentq(lambda h: reactance(factory, vert_ft, h), lo, hi, xtol=1e-3)
        lo, f_lo = hi, f_hi
    raise SystemExit(f"no resonance for vert {vert_ft} ft below 250 ft of top wire")


def resonate_vertical(factory) -> float:
    return brentq(lambda v: reactance(factory, v, 0.0), 100.0, 150.0, xtol=1e-3)


def read(factory, vert_ft, horiz_ft) -> dict:
    eng = factory(builder(vert_ft, horiz_ft))
    src = mx.source_for(eng)
    out = {"z": [eng.impedance()[0].real, eng.impedance()[0].imag]}
    table = src.table()
    out["peak_az"] = table["azimuth_deg"]
    out["takeoff"] = table["takeoff_deg"]
    out["peak_dbi"] = table["peak_gain_dbi"]
    for name, az in MODES.items():
        out[name] = mx.evaluate(
            an.ElevationWindow("DX gain", 2, 10, step=0.1, az=az), src
        )
    return out


def main() -> None:
    global FREQ
    engine = sys.argv[1]
    out_path = sys.argv[2] if len(sys.argv) > 2 else None
    FREQ = float(sys.argv[3]) if len(sys.argv) > 3 else None
    factory = make_engine_factory(engine, parse_ground("finite"))
    t0 = time.time()
    v_ft = resonate_vertical(factory)
    ref = read(factory, v_ft, 0.0)
    print(f"{engine}: vertical resonant at {v_ft:.2f} ft, Z {ref['z']}", flush=True)
    rows = []
    for vert in sorted(TABLE, reverse=True):
        h = resonate_top(factory, vert)
        got = read(factory, vert, h)
        rel = {m: got[m] - ref[m] for m in MODES}
        rows.append({"vert_ft": vert, "horiz_ft": h, **got, "rel": rel})
        print(
            f"{vert:>4} ft  top {h:7.2f} ft  M0AGP {TABLE[vert]:+6.2f}  "
            + "  ".join(f"{m} {rel[m]:+6.2f}" for m in MODES)
            + f"  (peak az {got['peak_az']:.1f}, take-off {got['takeoff']:.1f})",
            flush=True,
        )
    print(f"{time.time() - t0:.0f} s")
    if out_path:
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "engine": engine,
                    "freq_mhz": FREQ or get_builder(DESIGN)().freq,
                    "vertical_ft": v_ft,
                    "vertical": ref,
                    "rows": rows,
                },
                f,
                indent=1,
            )


if __name__ == "__main__":
    main()

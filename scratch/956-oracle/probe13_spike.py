"""#956 spike: why does the prototype's regime-2 kernel cost 50x the transmitted one?

`field_in_medium` measured 1376 ms/eval against `field_transmitted`'s 27.5 ms,
and that gap is the whole cost of the proposed next unit. This asks what
dominates, using the prototype's own quadrature-health tally rather than a
guess, and prices the two knobs that are free to turn.
"""

import sys
import time
import warnings
from pathlib import Path


warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "524-phase0" / "proto"))

import buried_proto as bp  # noqa: E402

HS = bp.HalfSpace(freq=7.1e6, eps_r=13.0, sigma=0.005)

# configurations the next unit would actually query: a buried observer near the
# node against buried sources from the rise and out along a radial.
CASES = [
    ("rise x rise, both shallow", (0.0005, 0.0, -0.003), -0.02, "VED"),
    ("rise x rise, node to hub", (0.0005, 0.0, -0.003), -0.15, "VED"),
    ("radial x rise", (0.5, 0.0, -0.15), -0.05, "HED"),
    ("radial x radial, far", (3.0, 0.0, -0.15), -0.15, "HED"),
    ("hub depth pair", (0.05, 0.0, -0.15), -0.15, "VED"),
]


def reset():
    for k in bp.STATS:
        bp.STATS[k] = 0 if isinstance(bp.STATS[k], int) else bp.STATS[k]
    bp.STATS["n"] = 0
    bp.STATS["accel"] = 0
    bp.STATS["nonconv"] = 0
    bp.STATS["max_tail_panels"] = 0
    bp.STATS["max_head_panels"] = 0
    bp.STATS["worst_selfconv"] = 0.0


def bench(fn, *a, **kw):
    reset()
    t0 = time.time()
    out = fn(*a, **kw)
    dt = (time.time() - t0) * 1000.0
    s = dict(bp.STATS)
    return dt, out, s


def main():
    print(
        f"{'case':>28} {'kernel':>12} {'err':>5} {'ms':>9} {'ints':>5} "
        f"{'headmax':>8} {'tailmax':>8} {'accel':>6} {'nonconv':>8}"
    )
    for name, obs, zp, kind in CASES:
        for err in (True, False):
            dt, _o, s = bench(bp.field_in_medium, HS, obs, zp, kind, err=err)
            print(
                f"{name:>28} {'in_medium':>12} {str(err):>5} {dt:9.1f} "
                f"{s['n']:5d} {s['max_head_panels']:8d} {s['max_tail_panels']:8d} "
                f"{s['accel']:6d} {s['nonconv']:8d}"
            )
            sys.stdout.flush()
    print()
    for err in (True, False):
        dt, _o, s = bench(
            bp.field_transmitted, HS, (1.0, 0.0, 1.0), -0.05, "VED", err=err
        )
        print(
            f"{'(reference) far transmitted':>28} {'transmitted':>12} "
            f"{str(err):>5} {dt:9.1f} {s['n']:5d} {s['max_head_panels']:8d} "
            f"{s['max_tail_panels']:8d} {s['accel']:6d} {s['nonconv']:8d}"
        )

    # the two knobs that are free: err=False halves the work (it skips the
    # COARSE companion integration), and the tail panel cap bounds the worst
    # case. Price a sampled-error policy over a realistic mix.
    print("\n--- a realistic mix, err=True vs err=False ---")
    for err in (True, False):
        reset()
        t0 = time.time()
        for name, obs, zp, kind in CASES:
            bp.field_in_medium(HS, obs, zp, kind, err=err)
        dt = (time.time() - t0) * 1000.0 / len(CASES)
        print(
            f"  err={str(err):>5}: {dt:8.1f} ms/eval mean   "
            f"tail panels max {bp.STATS['max_tail_panels']}, "
            f"nonconvergent {bp.STATS['nonconv']}/{bp.STATS['n']}"
        )


if __name__ == "__main__":
    main()

"""#956 Phase B: the oracle block's real cost, from the deck's own pair set.

The prototype's transmitted integral is adaptive, so its cost is a function of
the pair geometry, not a constant. One configuration measured 15 s against a
20-30 ms typical. Before launching a block assembly, enumerate the deck's
actual (rho, z, |z'|) triples at the fill's own quadrature nodes and time a
stratified sample of them — the tail is what sets the wall clock.
"""

import sys
import time
import warnings
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "524-phase0" / "proto"))

import buried_proto as bp  # noqa: E402

from probe3_cross_block import build, parts, solver_of  # noqa: E402

SOIL_A = (13.0, 0.005)
FREQ = 7.1e6


def main():
    q_factor = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    n_sample = int(sys.argv[2]) if len(sys.argv) > 2 else 24
    b = build()
    s = solver_of(b)
    geom, _supp, _polys, a_idx, b_idx = parts(s)
    obs_a, t_a, _W_a = s._buried_nodes(geom, a_idx, q_factor=q_factor)
    obs_b, t_b, _W_b = s._buried_nodes(geom, b_idx, q_factor=q_factor)
    n_pairs = len(obs_a) * len(obs_b)
    print(
        f"q_factor {q_factor}: obs nodes {len(obs_a)}, src nodes {len(obs_b)}, "
        f"pairs {n_pairs:,}"
    )

    d = obs_a[:, None, :] - obs_b[None, :, :]
    rho = np.hypot(d[..., 0], d[..., 1]).ravel()
    z = np.repeat(obs_a[:, 2], len(obs_b))
    zp = np.tile(obs_b[:, 2], len(obs_a))
    print(
        f"rho  [{rho.min():.2e}, {rho.max():.2e}]  "
        f"z [{z.min():.2e}, {z.max():.2e}]  |z'| [{abs(zp).min():.2e}, "
        f"{abs(zp).max():.2e}]"
    )

    # stratify on the quantity the 15 s case was extreme in: rho / |z'|
    key = rho / np.maximum(np.abs(zp), 1e-12)
    order = np.argsort(key)
    picks = order[np.linspace(0, len(order) - 1, n_sample).astype(int)]
    hs = bp.HalfSpace(freq=FREQ, eps_r=SOIL_A[0], sigma=SOIL_A[1])
    ts = []
    print(
        f"\n{'rho/|zp|':>12} {'rho':>10} {'z':>10} {'|zp|':>10} {'ms':>9} {'rel':>10}"
    )
    for p in picks:
        t0 = time.time()
        _e, rel, _q = bp.field_transmitted(hs, (rho[p], 0.0, z[p]), zp[p], "VED")
        dt = (time.time() - t0) * 1e3
        ts.append(dt)
        print(
            f"{key[p]:12.3e} {rho[p]:10.3e} {z[p]:10.3e} {abs(zp[p]):10.3e} "
            f"{dt:9.1f} {rel:10.2e}"
        )
        sys.stdout.flush()
    ts = np.array(ts)
    print(
        f"\nsample ms: median {np.median(ts):.1f}  mean {ts.mean():.1f}  "
        f"p90 {np.percentile(ts, 90):.1f}  max {ts.max():.1f}"
    )
    est = n_pairs * ts.mean() / 1000.0
    print(
        f"stratified-mean estimate for the FULL block: {est / 60:.1f} min "
        f"single-core, {est / 60 / 7:.1f} min on 7 workers"
    )


if __name__ == "__main__":
    main()

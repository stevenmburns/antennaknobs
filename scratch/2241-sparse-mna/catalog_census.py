"""AK#2241: every catalog design's network, forced through both MNA paths.

Builds each design's momwire engine (geometry and the reducer only; the
engine's `make_reducer` is intercepted so no tuner tunes and nothing solves),
then reduces the network over a synthetic passive antenna Y at a few
frequencies, once forced dense and once forced sparse, and reports the MNA
size, the worst relative disagreement in Z, Γ, port voltages, p_in and
budget watts, and the two rcond values.

Usage: python catalog_census.py   (prints one row per design with a network)
"""

import importlib
import pkgutil
import sys
import warnings

import numpy as np

import antennaknobs.designs as designs_pkg
import antennaknobs.engines.momwire as em
from antennaknobs.mw.networks import NetworkReducer, PortVirtual
from antennaknobs.mw.networks import _reduce

C = 299_792_458.0


def catalog_networks():
    captured = []

    def capture(net, port_to_idx, n_total, **kw):
        captured.append((net, dict(port_to_idx), n_total, kw.get("c_light_mhz_m")))
        return NetworkReducer(
            net, port_to_idx, n_total, c_light_mhz_m=kw.get("c_light_mhz_m")
        )

    em.make_reducer = capture
    for m in pkgutil.walk_packages(designs_pkg.__path__, designs_pkg.__name__ + "."):
        if m.ispkg:
            continue
        try:
            builder = importlib.import_module(m.name).Builder
        except Exception:  # noqa: BLE001 — an unimportable design is gated elsewhere
            continue
        name = m.name.split("antennaknobs.designs.")[-1]
        captured.clear()
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                b = builder()
                em.MomwireEngine(b)
        except Exception as e:  # noqa: BLE001 — a census row, not a gate
            print(f"{name}: engine refused ({type(e).__name__})", file=sys.stderr)
            continue
        if captured:
            yield name, b.freq, captured[-1]


def antenna_y(n, seed):
    if n == 0:
        return np.zeros((0, 0), dtype=np.complex128)
    rng = np.random.default_rng(seed)
    a = rng.normal(size=(n, n))
    r = a @ a.T + n * np.eye(n) * 20.0
    b = rng.normal(size=(n, n)) * 40.0
    return np.linalg.inv(r + 1j * (b + b.T) / 2.0)


def run(red, y, wl, path):
    old = _reduce.SPARSE_MIN_UNKNOWNS
    _reduce.SPARSE_MIN_UNKNOWNS = 0 if path == "sparse" else 10**12
    try:
        s = red.apply_branches(y, wl, z_ref=50.0)
        z = np.array(red.impedance_from_y(s))
        g = np.array(red.reflection_from_y(s))
        v, eff, p_in, budget = red.excited_state(y, wl)
        return dict(
            n=s.A.shape[0],
            rcond=s.rcond,
            z=z,
            g=g,
            v=v,
            p_in=p_in,
            eff=eff,
            w=np.array([w for _l, w in budget]),
        )
    finally:
        _reduce.SPARSE_MIN_UNKNOWNS = old


def rel(a, b, scale=None):
    a, b = np.atleast_1d(a), np.atleast_1d(b)
    if a.size == 0:
        return 0.0
    s = np.max(np.abs(b)) if scale is None else scale
    return float(np.max(np.abs(a - b)) / s) if s else float(np.max(np.abs(a - b)))


def main():
    worst = 0.0
    sizes = []
    for name, f_mhz, (net, idx, n_total, c_light) in catalog_networks():
        n_virtual = sum(1 for p in net.ports.values() if isinstance(p, PortVirtual))
        n_real = n_total - n_virtual
        red = NetworkReducer(net, idx, n_total, c_light_mhz_m=c_light)
        y = antenna_y(n_real, seed=n_total)
        for f in (0.9 * f_mhz, f_mhz, 1.1 * f_mhz):
            wl = C / (f * 1e6) if c_light is None else c_light / f
            out = {}
            for path in ("dense", "sparse"):
                try:
                    out[path] = run(red, y, wl, path)
                except Exception as e:  # noqa: BLE001 — compared below
                    out[path] = (type(e).__name__, str(e).splitlines()[0])
            d, s = out["dense"], out["sparse"]
            if isinstance(d, tuple) or isinstance(s, tuple):
                same = "SAME" if d == s else "DIFFERENT"
                print(f"{name:40s} {f:8.4f}  refused: {same} dense={d} sparse={s}")
                continue
            p_scale = max(abs(d["p_in"]), 1e-300)
            err = max(
                rel(s["z"], d["z"]),
                rel(s["g"], d["g"]),
                rel(s["v"], d["v"]),
                rel(s["p_in"], d["p_in"]),
                rel(s["w"], d["w"], scale=p_scale),
                abs(s["eff"] - d["eff"]),
            )
            worst = max(worst, err)
            sizes.append(d["n"])
            dec = abs(np.log10(s["rcond"]) - np.log10(d["rcond"]))
            print(
                f"{name:40s} {f:8.4f}  n+m {d['n']:4d}  err {err:.1e}"
                f"  rcond dense {d['rcond']:.2e} sparse {s['rcond']:.2e}"
                f"  |log10 ratio| {dec:.2f}"
            )
    print(f"worst {worst:.2e}; largest n+m {max(sizes)}; rows {len(sizes)}")


if __name__ == "__main__":
    main()

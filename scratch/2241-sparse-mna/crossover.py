"""AK#2241: dense vs sparse MNA per-frequency cost, on the RLCG ladder and on a
station-like network repeated in a chain, through antennaknobs' own reducer.

Synthetic throughout. The ladder is AK#2241's study (a 30 m RG-58-like line as
N symmetric T sections in front of a fixed 73 + j42 ohm antenna, 7.1 MHz);
the station chain is K copies of rig - coax - L tuner - balun - ladder line,
each copy's far end feeding the next copy's rig node, the last one an antenna
pair, so its unknown count grows with K the way a big hand-built network's
would and its stamp mix is the catalog's, not just TwoPort / Shunt.

Usage: python crossover.py ladder N [N ...] | station K [K ...] [--dense-max M]
Prints n+m, the per-frequency driven_impedance time on each path (best of a
few), and the two answers' relative difference.
"""

import sys
import time

import numpy as np

import antennaknobs.mw.networks as ak
from antennaknobs.mw.networks import _reduce

F_MHZ = 7.1
C = 299.792458
LENGTH = 30.0
L_PM, C_PM, R_PM, G_PM = 250e-9, 100e-12, 0.06, 2e-6
Z_ANT = 73.0 + 42.0j


def exact():
    w = 2 * np.pi * F_MHZ * 1e6
    z = R_PM + 1j * w * L_PM
    y = G_PM + 1j * w * C_PM
    zc = np.sqrt(z / y)
    t = np.tanh(np.sqrt(z * y) * LENGTH)
    return zc * (Z_ANT + zc * t) / (zc + Z_ANT * t)


def ladder(n):
    dz = LENGTH / n
    ports = {"feed": ak.PortOnWire("feed"), "rig": ak.PortVirtual("rig")}
    branches = []
    left = "rig"
    for k in range(n):
        mid = f"m{k}"
        right = "feed" if k == n - 1 else f"n{k + 1}"
        ports[mid] = ak.PortVirtual(mid)
        if right != "feed":
            ports[right] = ak.PortVirtual(right)
        branches.append(ak.TwoPort(left, mid, r=R_PM * dz / 2, l=L_PM * dz / 2))
        branches.append(ak.Shunt(mid, r=1.0 / (G_PM * dz), c=C_PM * dz, parallel=True))
        branches.append(ak.TwoPort(mid, right, r=R_PM * dz / 2, l=L_PM * dz / 2))
        left = right
    net = ak.Network(ports=ports, branches=branches, sources=[ak.Driven("rig")])
    idx = {p: i for i, p in enumerate(ports)}
    y = np.array([[1.0 / Z_ANT]], dtype=np.complex128)
    return net, idx, y


def station(k):
    ports = {"w1": ak.PortOnWire("w1"), "w2": ak.PortOnWire("w2")}
    branches = []
    rig = "rig0"
    ports[rig] = ak.PortVirtual(rig)
    for s in range(k):
        names = [f"{x}{s}" for x in ("t_in", "t_mid", "bal", "l1", "l2")]
        for nm in names:
            ports[nm] = ak.PortVirtual(nm)
        t_in, t_mid, bal, l1, l2 = names
        last = s == k - 1
        o1, o2 = ("w1", "w2") if last else (f"o1_{s}", f"o2_{s}")
        if not last:
            ports[o1] = ak.PortVirtual(o1)
            ports[o2] = ak.PortVirtual(o2)
        branches += [
            ak.TL(rig, t_in, z0=50.0, length=15.0, vf=0.82, k1=0.25, k2=0.0009),
            ak.TwoPort(t_in, t_mid, l=2.7e-6, ql=300.0),
            ak.Shunt(t_mid, c=410e-12, qc=1200.0),
            ak.TwoPort(t_mid, bal, r=0.05),
            ak.FloatingBalun(primary=bal, a=l1, b=l2, n=2.0),
            ak.BalancedLine(
                l1, l2, o1, o2, zdiff=450.0, length=18.0, vf=0.91, k1=0.05, zcomm=600.0
            ),
        ]
        if not last:
            # The next copy's rig is a balanced-to-unbalanced hop off this
            # copy's far pair; a resistive common-mode return keeps it pinned.
            nxt = f"rig{s + 1}"
            ports[nxt] = ak.PortVirtual(nxt)
            branches += [
                ak.FloatingBalun(primary=nxt, a=o1, b=o2, n=0.5),
                ak.Shunt(o2, r=1000.0),
            ]
            rig = nxt
    net = ak.Network(ports=ports, branches=branches, sources=[ak.Driven("rig0")])
    idx = {p: i for i, p in enumerate(ports)}
    z = np.array([[60.0 + 20j, 5.0 - 3j], [5.0 - 3j, 60.0 + 20j]])
    return net, idx, np.linalg.inv(z)


def timed(red, y, wl, path, reps):
    old = _reduce.SPARSE_MIN_UNKNOWNS
    _reduce.SPARSE_MIN_UNKNOWNS = 0 if path == "sparse" else 10**12
    try:
        best = float("inf")
        z = None
        for _ in range(reps):
            t0 = time.perf_counter()
            s = red.apply_branches(y, wl, z_ref=ak.Z_REF_DEFAULT)
            z = red.impedance_from_y(s)[0]
            best = min(best, time.perf_counter() - t0)
        return best, z, s
    finally:
        _reduce.SPARSE_MIN_UNKNOWNS = old


def main():
    kind = sys.argv[1]
    dense_max = 2000
    args = sys.argv[2:]
    if "--dense-max" in args:
        i = args.index("--dense-max")
        dense_max = int(args[i + 1])
        args = args[:i] + args[i + 2 :]
    wl = C / F_MHZ
    for a in args:
        size = int(a)
        net, idx, y = ladder(size) if kind == "ladder" else station(size)
        red = ak.NetworkReducer(net, idx, len(idx), c_light_mhz_m=C)
        reps = 5 if len(idx) < 3000 else 2
        ts, zs, ss = timed(red, y, wl, "sparse", reps)
        nm = ss.A.shape[0]
        row = f"{kind} {size:6d}  n+m {nm:6d}  sparse {ts * 1e3:9.2f} ms  rcond {ss.rcond:.2e}"
        if nm <= dense_max:
            td, zd, sd = timed(red, y, wl, "dense", reps)
            row += (
                f"  dense {td * 1e3:9.2f} ms  rcond {sd.rcond:.2e}"
                f"  |dz|/|z| {abs(zs - zd) / abs(zd):.1e}"
            )
        if kind == "ladder":
            ze = exact()
            row += f"  err vs line {abs(zs - ze) / abs(ze):.2e}"
        print(row, flush=True)


if __name__ == "__main__":
    main()

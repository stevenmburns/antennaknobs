"""Driving example E5 for the sweep framework (AK#1757, 2026-09-28): one
frequency sweep observed at every measurement plane of Dan's CLC rig
(QRZ #143, scratch/dan-140-144/tl-xfmr-clc/Bydipole-TL-Xfmr-CLC.ssn), the
workbench's plane choice (`plane.driven_at`, as `web/adapter.py` does it).
Run with the released package:

    .venv-pypi/bin/python scratch/sweep-examples/ex5_planes.py
"""

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from antennaknobs.cli import get_builder, make_engine_factory, resolve_ground
from antennaknobs.plane import driven_at, planes_of

DECK = "scratch/dan-140-144/tl-xfmr-clc/Bydipole-TL-Xfmr-CLC.ssn"
FREQS = np.linspace(13.9, 14.45, 23)
Z0 = 50.0
# The planes drawn: the rig, after the transformer, and the bare antenna.
SHOWN = ("rig", "T1", "feed")

B = get_builder("@" + DECK)
net0 = B().build_network()
planes = planes_of(net0)
natural = net0.sources[0].port
print("planes:", planes, "natural:", natural)
fac = make_engine_factory(
    "momwire:bspline",
    resolve_ground(None, B()),
    extended_kernel=False,
    deck_extended_kernel=False,
    nominal_nsegs=None,
)

curves = {}
for plane in planes:
    zs = []
    for f in FREQS:
        b = B()
        b.freq = float(f)
        if plane != natural:
            pruned = driven_at(b.build_network(), plane)
            object.__setattr__(b, "build_network", lambda p=pruned: p)
        zs.append(complex(fac(b).impedance()[0]))
    curves[plane] = np.array(zs)
    g = np.abs((curves[plane] - Z0) / (curves[plane] + Z0))
    k = int(np.argmin(g))
    print(
        f"{plane:>8}: min SWR {(1 + g[k]) / (1 - g[k]):.2f} at {FREQS[k]:.3f} MHz, Z there {curves[plane][k]:.2f}"
    )

fig, (a, b2) = plt.subplots(1, 2, figsize=(12.5, 4.8))
for c, plane in zip(("tab:blue", "tab:orange", "tab:green"), SHOWN, strict=True):
    z = curves[plane]
    g = np.abs((z - Z0) / (z + Z0))
    rho = g  # EZNEC's SWR scale is linear in rho
    a.plot(FREQS, rho, marker=".", color=c, label=plane)
    b2.plot(FREQS, z.real, color=c, label=f"{plane} R")
    b2.plot(FREQS, z.imag, color=c, ls="--", label=f"{plane} X")
for s in (1.5, 2, 3):
    r = (s - 1) / (s + 1)
    a.axhline(r, color="0.6", lw=0.7, ls=":")
    a.text(FREQS[0], r, f" {s:g}:1", va="bottom", fontsize=8, color="0.4")
a.set_ylim(0, 1)
a.set_ylabel("ρ on 50 Ω (EZNEC's SWR scale)")
a.set_xlabel("freq (MHz)")
a.set_title("SWR at three of the rig's eight planes")
a.legend(fontsize=8)
b2.set_xlabel("freq (MHz)")
b2.set_ylabel("Ω")
b2.set_title("R (solid) and X (dashed) per plane")
b2.legend(fontsize=7, ncol=2)
fig.suptitle(
    "Dan's Bydipole TL-Xfmr-CLC rig (QRZ #143), momwire:bspline, the file's own ground"
)
fig.tight_layout()
fig.savefig("scratch/sweep-examples/ex5_planes.png", dpi=110)

"""Driving example 2 for the sweep framework (AK#1757, 2026-09-28): tune the
default inverted vee's length_factor and apex angle to a Z0 over average
ground. Left: a family of R/X curves vs length_factor, one per angle, with
the R = 50/75 and X = 0 references. Right: the tuning map over (length_factor,
angle), the X = 0 contour against the R = 50 and R = 75 contours; where they
cross is a match. Run with the released package:

    .venv-pypi/bin/python scratch/sweep-examples/ex2_tuning.py
"""

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from antennaknobs.cli import get_builder, make_engine_factory, resolve_ground

LF = np.linspace(0.90, 1.06, 33)
ANG = np.linspace(0.0, 60.0, 25)
FAMILY = [0.0, 15.0, 30.0, 45.0, 60.0]

B = get_builder("dipoles.invvee")
ground = resolve_ground("finite:13,0.005", B())
fac = make_engine_factory(
    "momwire:bspline",
    ground,
    extended_kernel=False,
    deck_extended_kernel=False,
    nominal_nsegs=None,
)
Z = np.empty((ANG.size, LF.size), dtype=complex)
for i, a in enumerate(ANG):
    for j, lf in enumerate(LF):
        b = B()
        b.angle_deg = float(a)
        b.length_factor = float(lf)
        Z[i, j] = complex(fac(b).impedance()[0])
np.savez("scratch/sweep-examples/ex2_grid.npz", LF=LF, ANG=ANG, Z=Z)

fig, (fa, fm) = plt.subplots(1, 2, figsize=(13, 5.2))
ax2 = fa.twinx()
cols = plt.cm.viridis(np.linspace(0, 0.9, len(FAMILY)))
for c, a in zip(cols, FAMILY, strict=True):
    i = int(np.argmin(abs(ANG - a)))
    fa.plot(LF, Z[i].real, color=c, lw=1.6, label=f"angle {a:g}°")
    ax2.plot(LF, Z[i].imag, color=c, lw=1.2, ls="--")
for z0 in (50, 75):
    fa.axhline(z0, color="0.4", lw=0.8, ls=":")
    fa.text(LF[0], z0, f" R = {z0}", va="bottom", fontsize=8, color="0.3")
ax2.axhline(0, color="0.4", lw=0.8)
fa.set_xlabel("length_factor")
fa.set_ylabel("R (Ω), solid")
ax2.set_ylabel("X (Ω), dashed")
fa.set_ylim(20, 110)
ax2.set_ylim(-250, 250)
fa.legend(fontsize=8, loc="upper left")
fa.set_title("family: one R/X pair per apex angle")

L, A = np.meshgrid(LF, ANG)
cx = fm.contour(L, A, Z.imag, levels=[0], colors="tab:blue", linewidths=2)
cr = fm.contour(
    L, A, Z.real, levels=[50, 75], colors=["tab:red", "tab:orange"], linewidths=1.6
)
fm.clabel(cr, fmt={50: "R=50", 75: "R=75"}, fontsize=8)
fm.clabel(cx, fmt={0: "X=0"}, fontsize=8)
im = fm.contourf(
    L, A, np.abs((Z - 50) / (Z + 50)), levels=20, cmap="Greys_r", alpha=0.35
)
fig.colorbar(im, ax=fm, label="|Γ| on 50 Ω")
fm.set_xlabel("length_factor")
fm.set_ylabel("apex angle (°)")
fm.set_title("tuning map: X = 0 against R = 50 / 75")
fig.suptitle(
    "dipoles.invvee, 28.47 MHz, 7 m apex, average ground (13 / 0.005), momwire:bspline"
)
fig.tight_layout()
fig.savefig("scratch/sweep-examples/ex2_tuning.png", dpi=110)

# Where X = 0 crosses R = Z0 (linear interpolation along each angle row).
for z0 in (50, 75):
    hits = []
    for i, a in enumerate(ANG):
        x = Z[i].imag
        k = np.flatnonzero(np.sign(x[:-1]) != np.sign(x[1:]))
        for kk in k:
            t = x[kk] / (x[kk] - x[kk + 1])
            r = Z[i, kk].real + t * (Z[i, kk + 1].real - Z[i, kk].real)
            hits.append((a, LF[kk] + t * (LF[kk + 1] - LF[kk]), r))
    best = min(hits, key=lambda h: abs(h[2] - z0))
    print(
        f"Z0={z0}: resonant R closest at angle {best[0]:.1f}°, length_factor {best[1]:.4f}, R {best[2]:.1f} Ω"
    )

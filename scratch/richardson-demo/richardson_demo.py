"""Two-panel Richardson-extrapolation demo on the HenTenna (free space).

Data: `antennaknobs sweep --builder specialty.hentenna --param nominal_nsegs
--markers 10 20 40 80 160 320 640 --engine momwire:razor-2p | momwire`
(momwire main + #1253, Skylake, 2026-09-28). Writes the docs figure
site/src/assets/advanced/richardson-hentenna.png (the convergence guide);
run from the repo root. N is the ACHIEVED total segment
count; the doubling ladder is what makes the successive differences a clean
order test.
"""

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

n_razor = np.array([60, 116, 230, 460, 914, 1828, 3660])
x_razor = np.array([46.449, 44.793, 42.232, 40.607, 39.746, 39.296, 39.072])
n_bs = np.array([59, 115, 231, 459, 915, 1829, 3661])
x_bs = np.array([38.754, 38.827, 38.883, 38.906, 38.915, 38.915, 38.915])

h = 1.0 / n_razor
# First-order Richardson on the last two rungs: X_inf = X(h) + (X(h) - X(2h)) / (2^p - 1), p = 1.
x_inf = x_razor[-1] + (x_razor[-1] - x_razor[-2])
fit = np.polyfit(
    h[-3:], x_razor[-3:], 1
)  # straight line in h through the asymptotic rungs

fig, (a, b) = plt.subplots(1, 2, figsize=(11.5, 4.6))

# Left: value against h = 1/N, linear axes. The limit is the intercept at h = 0.
hh = np.linspace(0, h[2], 50)
a.plot(
    hh,
    np.polyval(fit, hh),
    color="tab:blue",
    lw=1,
    ls="--",
    label="straight line through the last 3 rungs",
)
a.plot(h, x_razor, "o", color="tab:blue", label="razor-2p (NEC-5's formulation)")
a.plot(1.0 / n_bs, x_bs, "s", color="tab:green", ms=5, label="B-spline")
a.plot(
    [0],
    [x_inf],
    "D",
    color="tab:red",
    ms=8,
    zorder=5,
    label=f"extrapolated X∞ = {x_inf:.3f} Ω",
)
a.axhline(x_bs[-1], color="tab:green", lw=0.8, ls=":")
a.set_xlim(-0.0004, h[1] * 1.05)
a.set_xlabel("h = 1 / N   (N = total segments)")
a.set_ylabel("feed reactance X (Ω)")
a.set_title("The limit is where the curve meets h = 0")
a.legend(fontsize=8, loc="upper left")
a.grid(alpha=0.3)
for ni, xi, hi in zip(n_razor[:5], x_razor[:5], h[:5], strict=True):
    a.annotate(
        f"N={ni}", (hi, xi), textcoords="offset points", xytext=(6, -3), fontsize=7
    )

# Right: successive differences on log-log. Slope -p is the order the extrapolation assumes.
d_r = np.abs(np.diff(x_razor))
d_b = np.abs(np.diff(x_bs))
b.loglog(n_razor[:-1], d_r, "o-", color="tab:blue", label="razor-2p  |X(N) − X(2N)|")
mask = d_b > 0
b.loglog(
    n_bs[:-1][mask],
    d_b[mask],
    "s-",
    color="tab:green",
    ms=5,
    label="B-spline  |X(N) − X(2N)|",
)
ref = d_r[-1] * (n_razor[-2] / n_razor[:-1])
b.loglog(n_razor[:-1], ref, color="0.5", ls="--", lw=1, label="slope −1 (first order)")
b.set_xlabel("N (total segments)")
b.set_ylabel("change per doubling (Ω)")
b.set_title("A straight line of slope −p means order p")
b.legend(fontsize=8, loc="lower left")
b.grid(alpha=0.3, which="both")

fig.suptitle(
    "Richardson extrapolation: HenTenna, free space, feed reactance", fontsize=12
)
fig.tight_layout()
fig.savefig("site/src/assets/advanced/richardson-hentenna.png", dpi=130)
print(
    f"X_inf (p=1, last two) = {x_inf:.3f}; B-spline = {x_bs[-1]:.3f}; fit intercept = {fit[1]:.3f}"
)
print("ratios of successive differences:", np.round(d_r[1:] / d_r[:-1], 3))

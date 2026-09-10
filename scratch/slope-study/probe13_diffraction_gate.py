"""Issue #1373 gate 3 on M0AGP's hill: the 40 m, 45° hill with the mast
mid-slope and at the crest, `Terrain(diffraction=True)` against the #534
specular path, on the plumb quarter-wave with surface radials of probe10.

Prints, per case and per side (downhill az 0 / uphill az 180): the largest
step between adjacent 1° elevations in dB (the continuity number), the gain
at 3 / 10 / 20 / 30 / 60° and — uphill — what the hatched band now reads.
Writes a two-panel comparison figure."""

import pathlib
import sys

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from antennaknobs.engines.momwire import MomwireEngine  # noqa: E402
from antennaknobs.terrain import Terrain  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import probe9_mike_hillside as probe9  # noqa: E402
from probe4_azimuth_on_slope import gain_lookup  # noqa: E402
from probe9_mike_hillside import mike_terrain  # noqa: E402
from probe10_mike_elevation_figure import PlumbVerticalSurfaceRadials  # noqa: E402

probe9.N_FACETS = 12


def cut(ff, az):
    g = gain_lookup(ff)
    els = np.arange(1.0, 90.0, 1.0)
    return els, np.array([g(e, az) for e in els])


def run(H, S, f, diffraction):
    t = mike_terrain(H, S, f)
    t = Terrain(sectors=t.sectors, diffraction=diffraction)
    e = MomwireEngine(PlumbVerticalSurfaceRadials(), ground=("terrain", t))
    return e.far_field()


def main():
    cases = [(40.0, 45.0, 0.5, "mid-slope"), (40.0, 45.0, 1.0, "crest")]
    fig, axes = plt.subplots(2, 2, figsize=(12, 8), sharex=True, sharey=True)
    for row, (H, S, f, name) in enumerate(cases):
        ffs = {False: run(H, S, f, False), True: run(H, S, f, True)}
        for col, (az, side) in enumerate(((0.0, "downhill"), (180.0, "uphill"))):
            ax = axes[row, col]
            for flag, label, ls in (
                (False, "#534 specular", "--"),
                (True, "#1373 shadow + UTD", "-"),
            ):
                els, g = cut(ffs[flag], az)
                step = np.nanmax(np.abs(np.diff(g)))
                pick = {e: g[int(e) - 1] for e in (3, 10, 20, 30, 60)}
                print(
                    f"{name:9s} {side:8s} {label:18s} max 1° step {step:5.2f} dB | "
                    + " ".join(f"{e}°:{v:6.1f}" for e, v in pick.items())
                )
                ax.plot(els, g, ls, label=label)
            ax.set_title(f"{name}, {side} (az {az:.0f}), {H:.0f} m hill at {S:.0f}°")
            ax.grid(alpha=0.3)
            ax.set_ylim(-30, 6)
            if side == "uphill":
                ax.axvspan(0, S, color="0.85", alpha=0.5)
    axes[0, 0].legend(fontsize=8)
    for ax in axes[1]:
        ax.set_xlabel("elevation above the horizontal, deg")
    for ax in axes[:, 0]:
        ax.set_ylabel("gain, dBi")
    out = HERE / "diffraction_gate_2026-09-10.png"
    fig.savefig(out, dpi=130, bbox_inches="tight")
    print("wrote", out)


if __name__ == "__main__":
    main()

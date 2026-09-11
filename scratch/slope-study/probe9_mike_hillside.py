"""M0AGP's sketch through the faceted-terrain far-field ground (issue #534):
a plateau uphill, a slope, a plain downhill, and a plumb quarter-wave vertical
with four buried radials standing ON the slope at height `h_a` above the
plain. The hill has total relief `H` and slope angle `S`; the antenna's
position on it is `f = h_a / H` (0 = at the toe, 1 = at the crest).

What the model does (and does not) do, from `antennaknobs/terrain.py`: the
impedance/current solve runs over a FLAT Sommerfeld ground with the crest
facet's medium (near-field ground interaction is crest-local — the local tilt
of the slope under the radials is NOT modelled here; the slope study's
tilted-wire solve is the tool for that). The far field is composed per
direction by finding the facet the specular point lands on, tilting the
incidence angle by the facet's slope, applying that facet's Fresnel
coefficients and the facet's height as extra reflected-path phase. It is
geometric optics: no diffraction at the crest or the toe, so uphill below the
slope angle it reports grazing-cancelled reflection where the real sky is
shadowed, and downhill it has no edge-diffracted field from the crest behind
the antenna. Facets should be many wavelengths long for it to be credible;
at 40 m a 20 m hill is half a wavelength, which is exactly the regime Mike
calls hard. So this is the FIRST picture, with its validity stated, not the
answer.

Reads: gain in dBi in the crest-plane frame (the mast is plumb; the frame is
horizontal) toward downhill (az 0) and uphill (az 180) at low elevations.
"""

import math
import pathlib
import sys

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from antennaknobs.designs.verticals.buried_radial_vertical import (  # noqa: E402
    Builder as BRV,
)
from antennaknobs.engines.momwire import MomwireEngine  # noqa: E402
from antennaknobs.far_field import pattern_metrics  # noqa: E402
from antennaknobs.terrain import Facet, Sector, Terrain  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from probe4_azimuth_on_slope import gain_lookup  # noqa: E402

FREQ = 7.1
SOIL = (13.0, 0.005)
LAMBDA = 299.792458 / FREQ
N_FACETS = 12


def mike_terrain(H, S_deg, f, medium=SOIL, downhill_az=0.0):
    """Plateau at +(H - h_a), slope S, plain at -h_a; the mast at (0, 0) on
    the slope with h_a = f * H. Each ramp is subdivided so `specular_cut`
    (which locates facets by midpoint height) tracks the tilted mirror."""
    eps, sig = medium
    h_a = f * H
    h_up = H - h_a
    tan_s = math.tan(math.radians(S_deg))

    def ramp(dz_total):
        if abs(dz_total) < 1e-9:
            return ()
        run = abs(dz_total) / tan_s
        return tuple(
            Facet(run * (i + 1) / N_FACETS, dz_total * (i + 1) / N_FACETS, eps, sig)
            for i in range(N_FACETS)
        )

    down = (*ramp(-h_a), Facet(None, -h_a, eps, sig))
    up = (*ramp(+h_up), Facet(None, +h_up, eps, sig))
    return Terrain(
        # diffraction=False names what this probe's published figure IS: the
        # specular-facet field, geometric optics only. The flag's default
        # flipped to True in the #1373 follow-up, and a record of a number is
        # only a record while it still produces that number.
        diffraction=False,
        sectors=(
            Sector(downhill_az - 90.0, downhill_az + 90.0, down),
            Sector(downhill_az + 90.0, downhill_az + 270.0, up),
        ),
    )


def run(ground, label):
    b = BRV()
    e = MomwireEngine(b, ground=ground)
    z = e.impedance()[0]
    ff = e.far_field()
    g = gain_lookup(ff)
    pm = pattern_metrics(ff)
    row = {
        "label": label,
        "Z": z,
        "peak": pm["peak_gain_dbi"],
        "down3": g(3.0, 0.0),
        "down5": g(5.0, 0.0),
        "down10": g(10.0, 0.0),
        "down20": g(20.0, 0.0),
        "up10": g(10.0, 180.0),
        "up20": g(20.0, 180.0),
        "up30": g(30.0, 180.0),
        "across10": g(10.0, 90.0),
        "ff": ff,
    }
    return row


def elevation_cut(ff, az_deg):
    g = gain_lookup(ff)
    els = np.arange(0.5, 90.0, 0.5)
    return els, np.array([g(el, az_deg) for el in els])


if __name__ == "__main__":
    print(
        f"λ = {LAMBDA:.2f} m at {FREQ} MHz; soil {SOIL}; BRV default (λ/4 plumb, 4 buried radials)"
    )
    hdr = f"{'case':34s} {'Z (Ω)':>16s} {'peak':>6s} | down 3/5/10/20° | up 10/20/30° | across 10°"
    rows = [run(("finite",) + SOIL, "flat ground (reference)")]
    for H in (20.0, 40.0):
        for f in (0.0, 0.25, 0.5, 0.75, 1.0):
            rows.append(
                run(
                    ("terrain", mike_terrain(H, 45.0, f)),
                    f"H={H:.0f} m, 45°, f={f:.2f}",
                )
            )
    for H in (20.0,):
        for f in (0.5, 1.0):
            rows.append(
                run(
                    ("terrain", mike_terrain(H, 20.0, f)),
                    f"H={H:.0f} m, 20°, f={f:.2f}",
                )
            )
    print(hdr)
    for r in rows:
        print(
            f"{r['label']:34s} {r['Z'].real:7.2f}{r['Z'].imag:+8.2f}j {r['peak']:6.2f} | "
            f"{r['down3']:5.1f}/{r['down5']:5.1f}/{r['down10']:5.1f}/{r['down20']:5.1f} | "
            f"{r['up10']:5.1f}/{r['up20']:5.1f}/{r['up30']:5.1f} | {r['across10']:5.1f}"
        )

    fig, axes = plt.subplots(1, 2, figsize=(12, 5), sharey=True)
    sel = [
        r for r in rows if r["label"].startswith("flat") or "H=20 m, 45°" in r["label"]
    ]
    for ax, az, title in (
        (axes[0], 0.0, "downhill (az 0)"),
        (axes[1], 180.0, "uphill (az 180)"),
    ):
        for r in sel:
            els, gains = elevation_cut(r["ff"], az)
            ax.plot(els, gains, label=r["label"])
        ax.set_xlim(0, 60)
        ax.set_ylim(-20, 6)
        ax.set_xlabel("elevation above the crest plane, deg")
        ax.set_title(f"{title} — 20 m hill at 45°, mast at f·H above the plain")
        ax.grid(True, alpha=0.3)
    axes[0].set_ylabel("gain, dBi")
    axes[1].legend(fontsize=8)
    fig.suptitle(
        "M0AGP's hillside through the specular-facet ground (no diffraction) — 7.1 MHz, soil 13/0.005"
    )
    out = HERE / "mike_hillside_facets_2026-09-10.png"
    fig.savefig(out, dpi=140, bbox_inches="tight")
    print("wrote", out)

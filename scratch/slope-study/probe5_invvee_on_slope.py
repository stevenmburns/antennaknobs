"""An inverted vee on a 45 deg slope, against the resonant vertical: how high
does the apex have to be before it is useful downhill? Mast normal to the
slope, so the deck is the level one and only the sky rotates (probe4's
machinery). Legs ACROSS the slope put the vee's broadside on the fall line;
one along-slope arm for comparison. True azimuth 0 = downhill."""

import pathlib
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from antennaknobs.designs.dipoles.invvee import Builder as InvVee  # noqa: E402
from antennaknobs.designs.verticals.buried_radial_vertical import Builder as BRV  # noqa: E402
from antennaknobs.engines.momwire import MomwireEngine  # noqa: E402
from antennaknobs.far_field import pattern_metrics  # noqa: E402
from probe4_azimuth_on_slope import azimuth_ring, gain_lookup, true_to_ground  # noqa: E402

SOIL = ("finite", 13.0, 0.005)
FREQ = 7.1
SLOPE = 45.0
HEIGHTS = (3.0, 5.0, 8.0, 12.0)
SERIES = ("#2a78d6", "#eb6834", "#1baf7a", "#eda100")
INK, INK2, GROUND = "#0b0b0b", "#52514e", "#c3c2b7"
FLOOR = -20.0
TOP = 10.0


def vee(base, along_slope=False, tip_clearance=1.0):
    # legs run along y by construction (broadside toward +-x = the fall line);
    # rotate the whole deck 90 deg about z for the along-slope arm. The droop
    # is set so the tips sit `tip_clearance` above the ground, capped at the
    # catalog's default 31.68 deg -- at 7.1 MHz a 10.3 m leg at full droop
    # would put the tips 5.4 m below a 3 m apex.
    import math

    leg = 0.25 * (299.792458 / FREQ) * InvVee.default_params["length_factor"]
    angle = min(
        InvVee.default_params["angle_deg"],
        math.degrees(math.asin(min(1.0, max(0.0, base - tip_clearance) / leg))),
    )
    attrs = {
        "design_freq": FREQ,
        "freq": FREQ,
        "base": float(base),
        "angle_deg": float(angle),
    }

    class B(InvVee):
        def build_wires(self):
            tups = super().build_wires()
            if not along_slope:
                return tups
            return [
                w._replace(
                    p0=(-w.p0[1], w.p0[0], w.p0[2]), p1=(-w.p1[1], w.p1[0], w.p1[2])
                )
                for w in tups
            ]

    for k, v in attrs.items():
        setattr(B, k, v)
    return B


def vertical():
    return type("V", (BRV,), {"length_factor": 0.9531})


def true_cut(ff, slope):
    """Elevation cut in the fall-line plane, true frame: angle from the
    downhill horizon (0) over the zenith (90) to the uphill horizon (180)."""
    g = gain_lookup(ff)
    ang = np.linspace(-slope, 180.0, 400)
    out = []
    for a in ang:
        az_true = 0.0 if a <= 90.0 else 180.0
        e_true = a if a <= 90.0 else 180.0 - a
        eg, ag = true_to_ground(az_true, e_true, slope)
        out.append(g(eg, ag))
    return ang, np.asarray(out)


def g_true(ff, az, el, slope):
    eg, ag = true_to_ground(az, el, slope)
    return gain_lookup(ff)(eg, ag)


def slope_figure(pick, slope=SLOPE):
    """Elevation cut in the fall-line plane + azimuth ring at 10 deg true, for
    a list of (name, color, z, ff)."""
    # --- figure: elevation cut (fall-line plane) + azimuth at 10 deg true
    fig, axes = plt.subplots(1, 2, subplot_kw={"projection": "polar"}, figsize=(12, 6))
    fig.patch.set_facecolor("#fcfcfb")
    ax = axes[0]
    ax.set_facecolor("#fcfcfb")
    ax.set_thetamin(-slope)
    ax.set_thetamax(180)
    ax.set_rlim(0, (TOP - FLOOR))
    ax.set_rticks([0, 10, 20, 30])
    ax.set_yticklabels([])
    for rv, lab in ((10.0, "−10"), (20.0, "0"), (30.0, "+10 dBi")):
        ax.text(
            np.deg2rad(88), rv - 0.6, lab, color=INK2, fontsize=7.5, ha="left", va="top"
        )
    ax.set_thetagrids(
        [0, 30, 60, 90, 120, 150, 180],
        labels=["0°", "30°", "60°", "90°", "60°", "30°", "0°"],
        color=INK2,
        fontsize=8,
    )
    ax.grid(color="#e6e5e1", linewidth=0.6)
    ax.spines["polar"].set_color("#e6e5e1")
    hill = np.deg2rad(np.linspace(180 - slope, 180, 40))
    ax.fill_between(hill, 0, (TOP - FLOOR), color=GROUND, alpha=0.35, linewidth=0)
    ax.plot(
        [np.deg2rad(-slope), np.deg2rad(180 - slope)],
        [(TOP - FLOOR), (TOP - FLOOR)],
        color=INK2,
        linewidth=1.4,
    )
    ax.plot(
        [0, np.pi],
        [(TOP - FLOOR), (TOP - FLOOR)],
        color=INK2,
        linewidth=0.8,
        linestyle=(0, (3, 3)),
    )
    for name, color, z, ff in pick:
        ang, g = true_cut(ff, slope)
        r = np.where(np.isnan(g), np.nan, np.clip(g, FLOOR, TOP) - FLOOR)
        ax.plot(np.deg2rad(ang), r, color=color, linewidth=2, label=name)
    ax.set_title(
        "Elevation, uphill–downhill plane (true angles)", color=INK, fontsize=10, pad=14
    )
    ax.text(np.deg2rad(150), 9, "behind\nthe hill", color=INK2, fontsize=8, ha="center")

    ax = axes[1]
    ax.set_facecolor("#fcfcfb")
    ax.set_theta_zero_location("E")
    ax.set_theta_direction(1)
    for name, color, z, ff in pick:
        az, g = azimuth_ring(ff, 10.0, slope)
        r = np.where(np.isnan(g), np.nan, np.clip(g, FLOOR, TOP) - FLOOR)
        ax.plot(np.deg2rad(az), r, color=color, linewidth=2, label=name)
    ax.set_rlim(0, (TOP - FLOOR))
    ax.set_rticks([0, 10, 20, 30])
    ax.set_yticklabels(["", "−10", "0", "+10 dBi"], color=INK2, fontsize=8)
    ax.set_rlabel_position(135)
    ax.set_thetagrids(
        range(0, 360, 30),
        labels=[
            "downhill" if d == 0 else ("uphill" if d == 180 else f"{d}°")
            for d in range(0, 360, 30)
        ],
        color=INK2,
        fontsize=8,
    )
    ax.grid(color="#e6e5e1", linewidth=0.6)
    ax.spines["polar"].set_color("#e6e5e1")
    ax.set_title("Azimuth at 10° true elevation", color=INK, fontsize=10, pad=14)
    fig.legend(
        *ax.get_legend_handles_labels(),
        loc="lower center",
        ncol=3,
        frameon=False,
        fontsize=8,
        bbox_to_anchor=(0.5, 0.01),
    )
    fig.suptitle(
        f"Mast normal to a {slope:g}° slope, 7.1 MHz, soil εr 13 / σ 0.005 — one level-ground solve each, sky rotated",
        color=INK,
        fontsize=10,
        y=0.98,
    )
    fig.tight_layout(rect=(0, 0.06, 1, 0.95))
    return fig


if __name__ == "__main__":
    cases = [("vertical, 4 buried radials", vertical(), "#0b0b0b")]
    cases += [
        (f"inverted vee, apex {h:g} m, legs across", vee(h), c)
        for h, c in zip(HEIGHTS, SERIES, strict=True)
    ]
    cases += [
        (
            "inverted vee, apex 8 m, legs along the slope",
            vee(8.0, along_slope=True),
            "#4a3aa7",
        )
    ]
    results = []
    print(
        f"{'antenna':46s} {'Z (ohm)':>18s} {'peak':>6s} | true 45 deg slope: downhill 3 / 10 / 20 deg | uphill 60 | across 10"
    )
    for name, cls, color in cases:
        e = MomwireEngine(cls(), ground=SOIL)
        z = e.impedance()[0]
        ff = e.far_field()
        pm = pattern_metrics(ff)
        d3, d10, d20 = (g_true(ff, 0.0, el, SLOPE) for el in (3, 10, 20))
        u60 = g_true(ff, 180.0, 60, SLOPE)
        x10 = g_true(ff, 90.0, 10, SLOPE)
        results.append((name, color, z, ff))
        print(
            f"{name:46s} {z.real:7.1f}{z.imag:+8.1f}j {pm['peak_gain_dbi']:6.2f} | {d3:6.2f} / {d10:6.2f} / {d20:6.2f}          | {u60:6.2f} | {x10:6.2f}"
        )

    pick = [results[0], results[2], results[4]]  # vertical, vee 5 m, vee 12 m
    fig = slope_figure(pick)
    out = HERE / "slope45_vee_vs_vertical.png"
    fig.savefig(out, dpi=160)
    print("wrote", out)

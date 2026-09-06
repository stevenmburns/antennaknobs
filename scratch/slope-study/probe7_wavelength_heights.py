"""Two more data points for the 45 deg slope (Steve, 2026-09-06): the plumb
vertical with its horizontal half-fan of radials resting on the ground at the
feed point (base 5 cm, the smallest stand-off a bare wire is served at), and
the inverted vee with its apex at 1/8, 1/4, 3/8 and 1/2 wavelength."""

import pathlib
import sys

import matplotlib

matplotlib.use("Agg")

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from antennaknobs.engines.momwire import MomwireEngine  # noqa: E402
from antennaknobs.far_field import pattern_metrics  # noqa: E402
from probe5_invvee_on_slope import (  # noqa: E402
    FREQ,
    SLOPE,
    SOIL,
    g_true,
    slope_figure,
    vee,
    vertical,
)  # noqa: E402
from probe6_elevated_radials_on_slope import PlumbVerticalHalfFan  # noqa: E402

LAMBDA = 299.792458 / FREQ
FRACS = (1 / 8, 1 / 4, 3 / 8, 1 / 2)
SERIES = ("#2a78d6", "#eb6834", "#1baf7a", "#eda100")

if __name__ == "__main__":
    cases = [
        ("vertical, 4 buried radials", vertical(), "#0b0b0b"),
        (
            "plumb vertical, radials on the ground (base 5 cm)",
            type("E005", (PlumbVerticalHalfFan,), {"base": 0.05}),
            "#4a3aa7",
        ),
        (
            "plumb vertical, radials at 0.5 m",
            type("E05", (PlumbVerticalHalfFan,), {"base": 0.5}),
            "#e87ba4",
        ),
    ]
    for f, c in zip(FRACS, SERIES, strict=True):
        h = f * LAMBDA
        cases.append((f"inverted vee, apex {f:.3g} λ = {h:.1f} m", vee(h), c))
    results = []
    print(f"λ = {LAMBDA:.2f} m at {FREQ} MHz; true 45 deg slope; dBi")
    print(
        f"{'antenna':46s} {'Z (ohm)':>18s} {'peak':>6s} | downhill 3 / 10 / 20 deg | uphill 60 | across 10"
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
            f"{name:46s} {z.real:7.1f}{z.imag:+8.1f}j {pm['peak_gain_dbi']:6.2f} | {d3:6.2f} / {d10:6.2f} / {d20:6.2f}     | {u60:6.2f} | {x10:6.2f}"
        )
    fig = slope_figure(
        [results[0], results[1], results[3], results[6]]
    )  # vertical, radials-on-ground, vee λ/8, vee λ/2
    out = HERE / "slope45_wavelength_heights.png"
    fig.savefig(out, dpi=160)
    print("wrote", out)

"""A PLUMB vertical (90 deg to the horizon) with elevated radials parallel to
the horizon, on a 45 deg slope -- the other forum suggestion. Modelled in the
ground's frame: the mast is tilted by the slope toward uphill, the radials are
a half-fan on the downhill side tilted UP by the slope (true-horizontal), no
ground contact anywhere, and the sky is rotated back with probe4's machinery.
Geometry convention (all probes): ground-frame +x = uphill, so a true-frame
direction at azimuth a (0 = downhill) and elevation e maps to
  x_g = -cos(e) cos(a) cos(s) + sin(e) sin(s),  y_g = cos(e) sin(a),
  z_g =  cos(e) cos(a) sin(s) + sin(e) cos(s)."""

import math
import pathlib
import sys
from types import MappingProxyType

import matplotlib

matplotlib.use("Agg")

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from antennaknobs import AntennaBuilder  # noqa: E402
from antennaknobs.engines.momwire import MomwireEngine  # noqa: E402
from antennaknobs.far_field import pattern_metrics  # noqa: E402
from antennaknobs.network import Wire  # noqa: E402
from probe5_invvee_on_slope import (  # noqa: E402
    FREQ,
    SLOPE,
    SOIL,
    g_true,
    slope_figure,
    vee,
    vertical,
)  # noqa: E402


def true_dir_to_ground(a_deg, e_deg, s_deg):
    a, e, s = map(math.radians, (a_deg, e_deg, s_deg))
    return (
        -math.cos(e) * math.cos(a) * math.cos(s) + math.sin(e) * math.sin(s),
        math.cos(e) * math.sin(a),
        math.cos(e) * math.cos(a) * math.sin(s) + math.sin(e) * math.cos(s),
    )


class PlumbVerticalHalfFan(AntennaBuilder):
    """Plumb quarter-wave vertical, fed at its base `base` metres above the
    sloping ground (measured normal to the slope), with `n_radials`
    quarter-wave radials horizontal in the TRUE frame fanned over the downhill
    half. Built in the ground frame for a slope of `slope_deg`."""

    default_params = MappingProxyType(
        {
            "design_freq": FREQ,
            "freq": FREQ,
            "base": 2.0,
            "length_factor": 0.95,
            "radial_factor": 1.0,
            "n_radials": 4,
            "slope_deg": SLOPE,
            "fan_deg": 180.0,
        }
    )

    def build_wires(self):
        eps = 0.05
        lam = self.design_wavelength
        h = 0.25 * lam * self.length_factor
        r = 0.25 * lam * self.radial_factor
        s = self.slope_deg
        base = (0.0, 0.0, float(self.base))
        up = true_dir_to_ground(0.0, 90.0, s)  # the true vertical, in the ground frame
        tups = [Wire(base, tuple(base[i] + eps * up[i] for i in range(3)), ex=1 + 0j)]
        top = tuple(base[i] + eps * up[i] + h * up[i] for i in range(3))
        tups.append(Wire(tuple(base[i] + eps * up[i] for i in range(3)), top))
        n = int(self.n_radials)
        for k in range(n):
            a = (
                -self.fan_deg / 2 + self.fan_deg * (k + 0.5) / n
            )  # true azimuth, 0 = downhill
            d = true_dir_to_ground(a, 0.0, s)  # true-horizontal, in the ground frame
            tups.append(Wire(base, tuple(base[i] + r * d[i] for i in range(3))))
        return tups


if __name__ == "__main__":
    cases = [
        ("vertical, 4 buried radials", vertical(), "#0b0b0b"),
        (
            "plumb vertical, 4 elevated radials, base 2 m",
            type("E2", (PlumbVerticalHalfFan,), {"base": 2.0}),
            "#2a78d6",
        ),
        (
            "plumb vertical, 4 elevated radials, base 4 m",
            type("E4", (PlumbVerticalHalfFan,), {"base": 4.0}),
            "#1baf7a",
        ),
        ("inverted vee, apex 5 m, legs across", vee(5.0), "#eb6834"),
    ]
    results = []
    print(
        f"{'antenna':46s} {'Z (ohm)':>18s} {'peak':>6s} | true 45 deg slope: downhill 3 / 10 / 20 deg | uphill 60 | across 10"
    )
    for name, cls, color in cases:
        b = cls()
        if isinstance(b, PlumbVerticalHalfFan):
            assert all(min(w.p0[2], w.p1[2]) > 0.0 for w in b.build_wires()), (
                "clear of the ground"
            )
        e = MomwireEngine(b, ground=SOIL)
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
    fig = slope_figure([results[0], results[1], results[3]])
    out = HERE / "slope45_elevated_radials.png"
    fig.savefig(out, dpi=160)
    print("wrote", out)

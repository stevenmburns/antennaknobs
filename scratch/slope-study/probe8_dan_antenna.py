"""The fourth antenna for the 45 deg slope: AC6LA's (QRZ, 2026-09-06). In his
deck the ground is level and the wire tilts 45 deg over four quarter-wave
radials one inch above the soil; rotating that pattern back so the wire is
plumb is the same construction as ours, so in the ground frame his antenna is
a PLUMB mast whose radials lie on the slope surface (one uphill, one downhill,
two across), fed at the hub. Compared here with the three antennas of the
second QRZ post: the vertical normal to the slope over buried radials, the
plumb vertical with horizontal radials resting on the ground, and the inverted
vee at a quarter-wave apex. Same solve-then-rotate read-out for all four."""

import pathlib
import sys
from types import MappingProxyType

import matplotlib

matplotlib.use("Agg")

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from antennaknobs import AntennaBuilder, Wire, WireSpec  # noqa: E402
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
)
from probe6_elevated_radials_on_slope import (  # noqa: E402
    PlumbVerticalHalfFan,
    true_dir_to_ground,
)

LAMBDA = 299.792458 / FREQ


class DanAntenna(AntennaBuilder):
    """AC6LA's deck in the ground frame: plumb quarter-wave mast (0.956 λ/4,
    his resonant length), base one inch above the slope, four λ/4 radials one
    inch above the slope surface along the fall line and across it, 1 mm
    radius wire."""

    default_params = MappingProxyType(
        {
            "design_freq": FREQ,
            "freq": FREQ,
            "base": 0.0254,
            "length_factor": 0.956,
            "radial_factor": 1.0,
            "slope_deg": SLOPE,
        }
    )

    def build_wire_material(self):
        return WireSpec(radius=0.001)

    def build_wires(self):
        eps = 0.05
        h = 0.25 * LAMBDA * self.length_factor
        r = 0.25 * LAMBDA * self.radial_factor
        s = self.slope_deg
        base = (0.0, 0.0, float(self.base))
        up = true_dir_to_ground(0.0, 90.0, s)  # plumb, in the ground frame
        foot = tuple(base[i] + eps * up[i] for i in range(3))
        tups = [Wire(base, foot, ex=1 + 0j)]
        tups.append(Wire(foot, tuple(foot[i] + h * up[i] for i in range(3))))
        # radials on the slope surface: ground-frame +-x (fall line) and +-y (across)
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            tups.append(Wire(base, (r * dx, r * dy, float(self.base))))
        return tups


class OPPlumbBuried(DanAntenna):
    """What N8SMG actually described: a plumb ground-mounted vertical whose
    four radials follow the sloped ground -- here buried 15 cm below the slope
    surface, the catalog's depth, with the hub below ground and one rise to
    the surface node the mast stands on (our buried-radial spelling with the
    mast leaning 45 deg from the ground normal). Same wire as Dan's."""

    default_params = MappingProxyType(
        {**DanAntenna.default_params, "depth": 0.15, "stub": 0.3}
    )

    def build_wires(self):
        eps = 0.05
        h = 0.25 * LAMBDA * self.length_factor
        r = 0.25 * LAMBDA * self.radial_factor
        s = self.slope_deg
        d = float(self.depth)
        hub = (0.0, 0.0, -d)
        node = (0.0, 0.0, 0.0)
        up = true_dir_to_ground(0.0, 90.0, s)
        # momwire's crossing fill serves only horizontal or vertical segments
        # at the interface (momwire#936), so the wire leaves the surface node
        # along the ground normal for `stub` metres before leaning to plumb:
        # a short kink at the base, stated rather than hidden.
        stub = float(self.stub)
        post = (0.0, 0.0, stub)
        tups = [Wire(hub, node)]  # the rise through the interface
        tups.append(Wire(node, (0.0, 0.0, eps), ex=1 + 0j))
        tups.append(Wire((0.0, 0.0, eps), post))
        tups.append(Wire(post, tuple(post[i] + (h - stub) * up[i] for i in range(3))))
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            tups.append(Wire(hub, (r * dx, r * dy, -d)))
        return tups


def nec5_far_field(csv_path):
    """momwire's FarField shape (dBi rings over theta 0..89 x phi 0..360) from
    the CSV beside this script, which holds the licensed NEC-5's full-hemisphere
    pattern for `op_plumb_buried.nec5.nec` (RP 0,91,361 at 1 deg; nulls
    floored at -40 dBi). momwire cannot fill a deck whose mast leans through
    the interface (the crossing fill has no tilt tables, momwire#936), so
    N8SMG's antenna as asked is solved by NEC-5 and read through the same
    rotation as the others."""
    from antennaknobs.engine import FarField

    rings = []
    for line in pathlib.Path(csv_path).read_text().splitlines():
        if line.startswith("#") or line.startswith("theta"):
            continue
        f = line.split(",")
        rings.append([float(x) for x in f[1:]])
    flat = [g for r in rings for g in r]
    return FarField(
        rings=rings,
        max_gain=max(flat),
        min_gain=min(flat),
        thetas=list(range(len(rings))),
        phis=list(range(len(rings[0]))),
    )


if __name__ == "__main__":
    cases = [
        ("vertical normal to the slope, 4 buried radials", vertical(), "#0b0b0b"),
        (
            "plumb vertical, horizontal radials on the ground",
            type("E005", (PlumbVerticalHalfFan,), {"base": 0.05}),
            "#4a3aa7",
        ),
        ("inverted vee, apex λ/4", vee(0.25 * LAMBDA), "#eb6834"),
        ("AC6LA: plumb wire, 4 radials 1 in above the slope", DanAntenna, "#1baf7a"),
    ]
    results = []
    print(f"λ = {LAMBDA:.2f} m at {FREQ} MHz; true {SLOPE:g} deg slope; dBi")
    print(
        f"{'antenna':50s} {'Z (ohm)':>18s} {'peak':>6s} | downhill 3 / 10 / 20 deg | uphill 60 | across 10"
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
            f"{name:50s} {z.real:7.1f}{z.imag:+8.1f}j {pm['peak_gain_dbi']:6.2f} | {d3:6.2f} / {d10:6.2f} / {d20:6.2f}     | {u60:6.2f} | {x10:6.2f}"
        )
    nec5_csv = HERE / "op_plumb_buried.nec5_pattern.csv"
    if nec5_csv.exists():
        ff = nec5_far_field(nec5_csv)
        z = complex(58.085, -3.661)  # from the same printout's input parameters
        name = "N8SMG as asked (NEC-5): plumb wire, 4 radials buried 15 cm in the slope"
        d3, d10, d20 = (g_true(ff, 0.0, el, SLOPE) for el in (3, 10, 20))
        u60 = g_true(ff, 180.0, 60, SLOPE)
        x10 = g_true(ff, 90.0, 10, SLOPE)
        print(
            f"{name:50s} {z.real:7.1f}{z.imag:+8.1f}j {ff.max_gain:6.2f} | {d3:6.2f} / {d10:6.2f} / {d20:6.2f}     | {u60:6.2f} | {x10:6.2f}"
        )
        results.append((name, "#eda100", z, ff))
    fig = slope_figure(results)
    fig.suptitle(
        "Five antennas on a 45° slope, 7.1 MHz, soil εr 13 / σ 0.005 — one level-ground solve each, sky rotated",
        color="#0b0b0b",
        fontsize=12,
    )
    out = HERE / "slope45_five_antennas.png"
    fig.savefig(out, dpi=160)
    print("wrote", out)

"""momwire#865 / #597: the z = 0 limit, approached from BOTH sides.

Same wire, mesh held FIXED, height swept through the interface. The question
is not "what is the answer at z = 0" -- momwire refuses that by name and the
trail argues it should keep refusing -- but how each engine BEHAVES as the
interface is approached, and whether the two agree on the way in.

Heights are chosen to straddle the proposed validity floor h/a >= 2: with
a = 0.5 mm that floor is h = 1.0 mm, which is also where the trail's insulated
No. 18 conductor sits.

Cross-engine, so this runs from the antennaknobs checkout (the NEC-5 wrapper
lives there). No momwire source is touched.
"""

from antennaknobs import AntennaBuilder
from antennaknobs.engines.momwire import MomwireEngine
from antennaknobs.engines.nec5 import NEC5Engine
from antennaknobs.wire_catalog import Wire

HALF, EPSG, RAD = 2.9557, 0.025, 5.0e-4
NS_ARM, NS_FEED = 25, 2
FREQ = 7.1
SOIL = ("finite", 13.0, 0.005)


class Dipole(AntennaBuilder):
    default_params = {"freq": FREQ, "design_freq": FREQ, "z": 1.0, "wire_radius": RAD}

    def build_wires(self):
        z = self.z
        return [
            Wire((-HALF, 0.0, z), (-EPSG, 0.0, z), NS_ARM),
            Wire((-EPSG, 0.0, z), (EPSG, 0.0, z), NS_FEED, ex=1 + 0j),
            Wire((EPSG, 0.0, z), (HALF, 0.0, z), NS_ARM),
        ]


def at(z):
    b = Dipole()
    b.z = z
    return b


def run(engine_cls, z, **kw):
    try:
        eng = engine_cls(at(z), ground=SOIL, **kw)
        return complex(eng.impedance()[0]), None
    except Exception as e:  # noqa: BLE001 - a refusal IS a result here
        return None, f"{type(e).__name__}: {str(e).splitlines()[0][:58]}"


HEIGHTS = [
    2.0,
    1.0,
    0.15,
    0.01,
    0.003,
    0.001,
    0.0005,
    0.0,
    -0.0005,
    -0.001,
    -0.003,
    -0.01,
    -0.15,
    -1.0,
    -2.0,
]

print(
    f"a = {RAD * 1000:.1f} mm, so the proposed floor h/a >= 2 is h = "
    f"{2 * RAD * 1000:.1f} mm\n"
)
print(f"{'h (m)':>10s} {'h/a':>8s} {'momwire':>26s} {'NEC-5':>26s}")
for z in HEIGHTS:
    zm, em = run(MomwireEngine, z)
    zn, en = run(NEC5Engine, z)
    hoa = f"{abs(z) / RAD:8.1f}" if z else "     0.0"
    sm = f"{zm.real:11.3f}{zm.imag:+11.3f}j" if zm else f"{em[:24]:>24s}"
    sn = f"{zn.real:11.3f}{zn.imag:+11.3f}j" if zn else f"{en[:24]:>24s}"
    print(f"{z:10.4f} {hoa} {sm:>26s} {sn:>26s}")

"""AK#1025 probe 2: the height ladder, mesh held FIXED.

Same wire (5.911 m, radius 5e-4, 25/2/25 segments) at a sequence of heights,
so burial is the only variable — auto_mesh would otherwise re-segment a buried
wire against the in-medium wavelength and confound the comparison.

Each rung through the NEC-5 wrapper and through momwire. The first rung where
they diverge names where the trouble starts.
"""

from antennaknobs import AntennaBuilder
from antennaknobs.engines.nec5 import NEC5Engine
from antennaknobs.wire_catalog import Wire

HALF = 2.9557
EPSG = 0.025
RAD = 5.0e-4
NS_ARM, NS_FEED = 25, 2
FREQ = 7.1
SOIL = ("finite", 13.0, 0.005)


class Dipole(AntennaBuilder):
    """The buried_dipole geometry at an arbitrary z, meshed verbatim."""

    default_params = {"freq": FREQ, "design_freq": FREQ, "z": -0.15, "wire_radius": RAD}

    def build_wires(self):
        z = self.z
        return [
            Wire((-HALF, 0.0, z), (-EPSG, 0.0, z), NS_ARM),
            Wire((-EPSG, 0.0, z), (EPSG, 0.0, z), NS_FEED, ex=1 + 0j),
            Wire((EPSG, 0.0, z), (HALF, 0.0, z), NS_ARM),
        ]


def _deck(z):
    b = Dipole()
    b.z = z
    return b


def nec5_z(z, ground):
    b = _deck(z)
    try:
        eng = NEC5Engine(b, ground=ground)
        return complex(eng.impedance()[0]), None
    except Exception as e:  # noqa: BLE001 - a refusal is a result here
        return None, f"{type(e).__name__}: {e}"


def momwire_z(z, ground):
    from antennaknobs.engines.momwire import MomwireEngine

    b = _deck(z)
    try:
        eng = MomwireEngine(b, ground=ground)
        return complex(eng.impedance()[0]), None
    except Exception as e:  # noqa: BLE001
        return None, f"{type(e).__name__}: {e}"


RUNGS = [
    ("free space", None, 0.0),
    ("above +2.00 m", SOIL, 2.0),
    ("above +1.00 m", SOIL, 1.0),
    ("above +0.15 m", SOIL, 0.15),
    ("buried -0.15 m", SOIL, -0.15),
    ("buried -1.00 m", SOIL, -1.0),
    ("buried -2.00 m", SOIL, -2.0),
]

print(f"{'rung':16s} {'NEC-5':>28s}   {'momwire':>28s}")
for name, g, z in RUNGS:
    zn, en = nec5_z(z, g)
    zm, em = momwire_z(z, g)
    sn = f"{zn.real:12.4f}{zn.imag:+12.4f}j" if zn is not None else f"{en[:26]:>26s}"
    sm = f"{zm.real:12.4f}{zm.imag:+12.4f}j" if zm is not None else f"{em[:26]:>26s}"
    print(f"{name:16s} {sn:>28s}   {sm:>28s}")
    if en:
        print(f"                 NEC-5 refusal: {en}")
    if em:
        print(f"                 momwire refusal: {em}")

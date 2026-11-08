"""AK#2209 gates 2/3/5 by hand, one stitched station per antenna.

Every comparison holds the FIELD SOLVER fixed on both sides, so what is left
is the circuit's spelling as cards plus the printout's rounding:

- licensed NEC-5 (black box): the deck through the binary, against the
  station network reduced on the binary's own antenna Y (NEC5Engine's
  multiport route, one run per real port);
- momwire's NEC-5 drop-in (`momwire-nec5-bspline`): the deck through the
  exe, against the network reduced on the exe's own antenna-only Z;
- AK's importer: the deck read back with `parse_nec(network=True)` and
  solved on momwire bspline, against the network on the same engine.

Run: PYTHONPATH=<worktree>/src:. python gates_by_engine.py > gates_by_engine.out
"""

import pathlib
import sys
import subprocess
import tempfile
from types import MappingProxyType, SimpleNamespace

import numpy as np

from antennaknobs.builder import AntennaBuilder
from antennaknobs.cli import make_engine_factory
from antennaknobs.engines.nec5 import NEC5Engine
from antennaknobs.nec5_export import export_nec5
from antennaknobs.nec5_station import station_deck
from antennaknobs.nec_import import parse_nec
from fixture import DIPOLE, F_MHZ, VEE, station

LICENSED = "/home/smburns/bin/nec5-licensed"
DROPIN = str(pathlib.Path(sys.executable).parent / "momwire-nec5-bspline")


# NEC-5 prints five significant figures per part: half a unit in the fifth
# figure of each part, as a fraction of |Z|.
def printout_rounding(z):
    def half_ulp(x):
        if x == 0:
            return 0.0
        e = np.floor(np.log10(abs(x)))
        return 0.5 * 10 ** (e - 4)

    return float(np.hypot(half_ulp(z.real), half_ulp(z.imag)) / abs(z))


def run_exe(exe, deck):
    with tempfile.TemporaryDirectory() as td:
        p = pathlib.Path(td)
        (p / "m.nec").write_text(deck)
        subprocess.run(
            [exe],
            input="m.nec\nm.out\n\n",
            cwd=td,
            capture_output=True,
            text=True,
            timeout=600,
        )
        rows = NEC5Engine._parse_input_parameters(
            (p / "m.out").read_text(errors="replace")
        )
    return rows[0][0][2]


def fake_engine(names, y):
    return SimpleNamespace(
        _reducer=SimpleNamespace(port_to_idx={n: i for i, n in enumerate(names)}),
        _compute_y_matrix=lambda _wl: np.atleast_2d(y),
    )


def antenna_only(antenna_text):
    deck = parse_nec(antenna_text, network=True)

    class A(AntennaBuilder):
        default_params = MappingProxyType({"freq": F_MHZ})
        c_light_mhz_m = 299.8

        def build_wires(self):
            return deck.wire_tuples(specs=True)

        def build_network(self):
            return deck.network()

    return A(), list(deck.network().ports)


def report(label, z_deck, z_comp, sd):
    rel = abs(z_deck - z_comp) / abs(z_comp)
    print(f"  {label}: deck {z_deck:.6f}  composite {z_comp:.6f}  rel {rel:.2e}")
    return rel


def main():
    for name, antenna in (
        ("dipole (centre knot)", DIPOLE),
        ("inverted V (vertex knot)", VEE),
    ):
        print(f"=== {name} at {F_MHZ} MHz")
        b = station(antenna=antenna)
        sd = station_deck(b)
        print(sd.text)
        print("  knots (measured on momwire bspline):")
        for k in sd.knots:
            print(f"    knot {k.segment}: {', '.join(k.nodes)}  effect {k.effect:.2e}")
        print(f"  derived phantom tolerance (sum of knot effects): {sd.tolerance:.2e}")
        print(
            f"  cards-as-circuit vs composite: {abs(sd.z_cards - sd.z_composite) / abs(sd.z_composite):.1e}"
        )

        # importer round trip, on momwire bspline both sides
        deck = parse_nec(sd.text, network=True)

        class Back(AntennaBuilder):
            default_params = MappingProxyType({"freq": F_MHZ})
            c_light_mhz_m = 299.8

            def build_wires(self):
                return deck.wire_tuples(specs=True)

            def build_network(self):
                return deck.network()

        z_back = complex(
            make_engine_factory("momwire:bspline", None)(Back()).impedance()[0]
        )
        rel = report("importer -> momwire bspline", z_back, sd.z_composite, sd)
        print(f"    within derived tolerance {sd.tolerance:.2e}: {rel <= sd.tolerance}")

        # licensed NEC-5
        eng = NEC5Engine(b, nec5_exe=LICENSED)
        sd5 = station_deck(b, engine=eng)
        cards = lambda t: [ln for ln in t.splitlines() if not ln.startswith("CM knot")]  # noqa: E731
        assert cards(sd5.text) == cards(sd.text)  # only the measured CM lines move
        z5 = run_exe(LICENSED, sd.text)
        tol5 = sd5.tolerance + printout_rounding(z5)
        rel = report("licensed NEC-5", z5, sd5.z_composite, sd5)
        for k in sd5.knots:
            print(
                f"    knot {k.segment}: {', '.join(k.nodes)}  effect {k.effect:.2e} (on NEC-5's Y)"
            )
        print(
            f"    tolerance = knots {sd5.tolerance:.2e} + printout {printout_rounding(z5):.2e}"
            f" = {tol5:.2e}: {rel <= tol5}"
        )

        # momwire NEC-5 drop-in
        ab, ports = antenna_only(antenna)
        feed = [p for p in ports][0]
        z_ant = run_exe(
            DROPIN, export_nec5(ab, design="antenna", rung="as-is", ground_name="free")
        )
        sdd = station_deck(b, engine=fake_engine([feed], 1.0 / z_ant))
        zd = run_exe(DROPIN, sd.text)
        told = sdd.tolerance + printout_rounding(zd) + printout_rounding(z_ant)
        rel = report("momwire-nec5-bspline drop-in", zd, sdd.z_composite, sdd)
        print(
            f"    (antenna-only Z on the drop-in {z_ant}, itself printed to 5 figures)"
        )
        print(
            f"    tolerance = knots {sdd.tolerance:.2e} + printout x2 = {told:.2e}: {rel <= told}"
        )


if __name__ == "__main__":
    main()

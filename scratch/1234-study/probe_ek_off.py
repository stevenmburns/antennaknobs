"""#1234: is the regression tail the EK default the bench started passing?

`extended_kernel=deck.extended_kernel` entered the momwire lanes of
`scripts/bench_nec_corpus.py` on 2026-08-12 (e62668627), AFTER the 07-18
baseline. So the two sweeps differ in the BENCH, not only in momwire: July
solved every deck reduced-kernel, 09-07 honours the deck's EK card.

Decks carrying an EK card are enriched 4.01x in the regression tail (44.4 %
against 11.1 % of the corpus). This re-solves those decks on today's stack
with EK forced OFF. If ΔΓ returns to its July value, the cause is named.

Reuses the bench's own DeckBuilder shape so the only difference from the
sweep is the kernel flag.
"""

import json
import math
import os
import sys
from pathlib import Path
from types import MappingProxyType

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from bench_nec_corpus import load_deck, parse_ground  # noqa: E402

from antennaknobs import AntennaBuilder, WireSpec  # noqa: E402
from antennaknobs.engines.momwire import MomwireEngine  # noqa: E402
from momwire import BSplineSolver, SinusoidalSolver  # noqa: E402

CORPUS = Path(os.path.expanduser("~/antennas/nec-wild"))
SOLVERS = {
    "sin": (SinusoidalSolver, {}),
    "bs1": (BSplineSolver, {"degree": 1}),
    "bs2": (BSplineSolver, {"degree": 2}),
}


def gamma(z, z0=50.0):
    return (z - z0) / (z + z0)


def solve(deck_rel, engine, ek, freq):
    path = CORPUS / deck_rel
    text = path.read_text(errors="replace")
    deck, net, _ = load_deck(text, path.name)
    ground, _supported, _note = parse_ground(text)
    tups = deck.wire_tuples(specs=True)

    class DeckBuilder(AntennaBuilder):
        default_params = MappingProxyType({"freq": float(freq)})

        def build_wires(self):
            return tups

        def build_network(self):
            return net

        def build_wire_material(self):
            return WireSpec(radius=deck.dominant_radius())

    solver, kw = SOLVERS[engine]
    eng = MomwireEngine(
        DeckBuilder(),
        solver=solver,
        solver_kwargs=kw,
        ground=ground,
        extended_kernel=ek,
    )
    return complex(eng.impedance()[0])


def main():
    todo = json.loads(Path(sys.argv[1]).read_text())
    out = []
    for rec in todo:
        d, e, ref = rec["deck"], rec["engine"], complex(*rec["ref"])
        row = {**rec}
        for tag, ek in (("ek_off", False), ("ek_on", True)):
            try:
                z = solve(d, e, ek, rec["freq"])
                row[tag] = abs(gamma(z) - gamma(ref)) if math.isfinite(z.real) else None
                row[tag + "_z"] = [z.real, z.imag]
            except Exception as exc:  # noqa: BLE001 -- probe reports, never fails
                row[tag] = None
                row[tag + "_err"] = f"{type(exc).__name__}: {exc}"[:120]
        out.append(row)
        print(json.dumps(row), flush=True)
    _ = np  # imported for parity with the bench's numeric env


if __name__ == "__main__":
    main()

"""AK#1025 probe 1: what cards does the wrapper write for a fully-buried
FED deck, and what does the binary print back?

No conclusions here — this is the raw material for the ladder. Nothing from
the licensed source tree is read; only the executable is invoked.
"""

import sys

from antennaknobs.designs.specialty.buried_dipole import Builder
from antennaknobs.engines.nec5 import NEC5Engine

GROUND = ("finite", 13.0, 0.005)

b = Builder()
print("=== design params ===")
for k, v in sorted(b.default_params.items()):
    print(f"   {k:22s} {v}")

print("\n=== authored wires ===")
for i, w in enumerate(b.build_wires()):
    print(
        f"   wire {i + 1}: p0={tuple(round(float(x), 4) for x in w.p0)} "
        f"p1={tuple(round(float(x), 4) for x in w.p1)} "
        f"ns={getattr(w, 'ns', '?')} name={getattr(w, 'name', '?')}"
    )

eng = NEC5Engine(b, ground=GROUND)
freq = float(b.default_params["freq"])
deck = eng.deck([freq])
print("\n=== DECK THE WRAPPER WRITES ===")
print(deck)

print("=== RAW PRINTOUT ===")
text = eng._run(deck)
sys.stdout.write(text)
print("=== END RAW PRINTOUT ===")

print("\n=== wrapper's parsed impedance ===")
try:
    print("   ", eng.impedance())
except Exception as e:  # noqa: BLE001 - a refusal IS a result in a probe
    print("   FAILED:", type(e).__name__, e)

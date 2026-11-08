"""What the LD 4 pins buy (AK#2209): the dipole station deck through the
licensed NEC-5 with and without its phantom-knot pins, against the composite
on NEC-5's own antenna Y. Run as gates_by_engine.py."""

from antennaknobs.engines.nec5 import NEC5Engine
from antennaknobs.nec5_station import station_deck
from fixture import station
from gates_by_engine import LICENSED, run_exe

b = station()
sd = station_deck(b, engine=NEC5Engine(b, nec5_exe=LICENSED))
unpinned = (
    "\n".join(ln for ln in sd.text.splitlines() if not ln.startswith("LD 4 2 ")) + "\n"
)
for label, text in (("pinned", sd.text), ("unpinned", unpinned)):
    z = run_exe(LICENSED, text)
    rel = abs(z - sd.z_composite) / abs(sd.z_composite)
    print(f"{label:9s} deck {z}  composite {sd.z_composite:.6f}  rel {rel:.2e}")

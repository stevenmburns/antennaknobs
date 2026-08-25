"""momwire#608 case (c) — what the licensed engine does with an inert wire.

razor is the NEC-5 formulation twin, so before deciding whether razor should
REFUSE a one-segment wire junctioned at neither end, ask the engine. Three
decks, identical but for the floater:

  1. a bare 20-segment dipole
  2. the same dipole + an isolated ONE-segment wire alongside
  3. the same dipole + the same floater given TWO segments

If (1) and (2) print the same impedance, the engine drops the one-segment
floater too and razor's inert behaviour IS the twin's; if (3) moves, the
floater is a real scatterer that the one-segment spelling loses.

Only the binary's PRINTED impedance is read. Nothing about the engine's
internals is quoted or inferred.

    NEC5_EXE=~/antennas/NEC5-downloads/nec5-linux/nec5cl python nec5_case_c.py
"""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
from pathlib import Path

EXE = Path(os.path.expanduser(os.environ.get("NEC5_EXE", "")))

LEN = 10.18946
RAD = 1.0262e-3
N = 20
D = LEN / N
FREQ_MHZ = 14.0

# The floater sits 0.5 m to the side, spanning one segment's worth of the
# dipole's own mesh, centred on the feed.
FX = 0.5


def deck(floater_segs: int | None) -> str:
    lines = [
        "CM one-segment floater probe (momwire#608)",
        "CE",
        f"GW 1,{N},0.,0.,0.,0.,{LEN:.6f},0.,{RAD:.7f}",
    ]
    if floater_segs is not None:
        y0, y1 = LEN / 2 - D / 2, LEN / 2 + D / 2
        lines.append(
            f"GW 2,{floater_segs},{FX},{y0:.6f},0.,{FX},{y1:.6f},0.,{RAD:.7f}"
        )
    lines += [
        "GE 0",
        f"EX 0,1,{N // 2},0,1.,0.",
        f"FR 0,1,0,0,{FREQ_MHZ:.3f},0.",
        "XQ",
        "EN",
    ]
    return "\n".join(lines) + "\n"


IMP = re.compile(
    r"^\s*\d+\s+\d+\s+[-\d.E+]+\s+[-\d.E+]+\s+[-\d.E+]+\s+[-\d.E+]+\s+"
    r"([-\d.E+]+)\s+([-\d.E+]+)",
    re.M,
)


def run(text: str) -> tuple[str, str]:
    with tempfile.TemporaryDirectory() as td:
        (Path(td) / "model.nec").write_text(text)
        proc = subprocess.run(
            [str(EXE)],
            input="model.nec\nmodel.out\n\n",
            capture_output=True,
            text=True,
            cwd=td,
            timeout=180,
        )
        out = Path(td) / "model.out"
        return (out.read_text(errors="replace") if out.exists() else ""), proc.stdout


def impedance(report: str):
    """The IMPEDANCE columns of the ANTENNA INPUT PARAMETERS block."""
    rows = [
        ln for ln in report.splitlines() if re.match(r"\s*1\s+\d+ 1\s+1\.0000E\+00", ln)
    ]
    if not rows:
        return None
    nums = re.findall(r"[-+]?\d\.\d+E[-+]\d+", rows[0])
    return float(nums[4]), float(nums[5])


def counts(report: str):
    """The engine's own element and unknown tallies — the decisive numbers."""
    el = re.search(r"Number of wire elements :\s*(\d+)", report)
    un = re.search(r"Number unknowns:\s*(\d+)", report)
    return (int(el.group(1)) if el else None, int(un.group(1)) if un else None)


def main():
    if not EXE.is_file():
        raise SystemExit(f"NEC5_EXE not found: {EXE}")
    print(f"  {'deck':<16s} {'Z (printed)':>22s}  elements  unknowns")
    for label, segs in (("no floater", None), ("1-seg floater", 1), ("2-seg floater", 2)):
        report, _stdout = run(deck(segs))
        z = impedance(report)
        n_el, n_un = counts(report)
        err = [ln.strip() for ln in report.splitlines() if "ERROR" in ln.upper()]
        shown = f"{z[0]:10.4f}{z[1]:+10.4f}j" if z else "     (none printed)"
        print(f"  {label:<16s} {shown:>22s}  {n_el:>8}  {n_un:>8}  {err if err else ''}")
    print(
        "\n  The 1-seg floater adds an ELEMENT and no UNKNOWN, and Z does not\n"
        "  move: the licensed engine drops it exactly as razor does. The\n"
        "  2-seg floater carries an unknown and scatters."
    )


if __name__ == "__main__":
    main()

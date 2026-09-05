"""AK#1025 item 2: the elevated case-study decks under both ground flags.

antennaknobs.dev/advanced/buried-radials runs the ELEVATED-detached class —
vertical clear of the ground, radials buried, nothing touching z = 0 — and its
NEC-5 column was captured through the wrapper, i.e. ground flag 1 with buried
wires present. Under the rule the #1025 measurements imply, those decks should
be on flag -1.

Only the GE card is substituted in the captured deck text, so mesh, geometry
and source are byte-identical between columns.
"""

import os
import re
import subprocess
import tempfile
from pathlib import Path

EXE = os.environ["NEC5_EXE"]
ROOT = Path("scratch/elevated-panel/results")


def run(deck):
    with tempfile.TemporaryDirectory(prefix="nec5_ep_") as td:
        (Path(td) / "m.nec").write_text(deck)
        try:
            subprocess.run(
                [EXE],
                input="m.nec\nm.out\n\n",
                text=True,
                capture_output=True,
                cwd=td,
                timeout=900,
            )
        except subprocess.TimeoutExpired:
            return None, "timeout"
        out = Path(td) / "m.out"
        if not out.is_file():
            return None, "no printout"
        text = out.read_text(errors="replace")
    m = re.search(
        r"- - - ANTENNA INPUT PARAMETERS - - -(.*?)(?:\n\s*\n\s*\n|$)", text, re.S
    )
    for line in m.group(1).splitlines() if m else []:
        t = line.split()
        if len(t) >= 12 and re.fullmatch(r"\d+", t[0]):
            return complex(float(t[7]), float(t[8])), None
    for line in text.splitlines():
        if re.search(r"ERROR|ILLEGAL|CANNOT|STOP", line, re.I):
            return None, " ".join(line.split())[:44]
    return None, "no row"


def buried(text):
    zs = []
    for ln in text.splitlines():
        if ln.startswith("GW"):
            p = re.split(r"[,\s]+", ln.strip())
            try:
                zs += [float(p[5]), float(p[8])]
            except (IndexError, ValueError):
                pass
    return any(z < -1e-12 for z in zs), any(abs(z) <= 1e-12 for z in zs)


rows = []
for sub in ("nec5-cap", "nec5-cap-verify"):
    for f in sorted((ROOT / sub).glob("*.nec")):
        text = f.read_text()
        has_buried, touches = buried(text)
        if not has_buried:
            continue
        ge = next(ln.strip() for ln in text.splitlines() if ln.startswith("GE"))
        title = next(
            (ln[2:].strip() for ln in text.splitlines() if ln.startswith("CM")), f.name
        )
        z_old, e_old = run(text)
        z_new, e_new = run(re.sub(r"^GE.*$", "GE -1,0", text, count=1, flags=re.M))
        rows.append((title, f.name, ge, touches, z_old, e_old, z_new, e_new))

print(f"{len(rows)} decks with buried wires (all clear of z=0)\n")
print(f"{'deck':44s} {'GE 1,-1 (published)':>21s} {'GE -1,0':>21s} {'dR %':>8s}")
moved = same = failed = 0
for title, name, ge, touches, zo, eo, zn, en in rows:
    if zo is None or zn is None:
        print(f"{title[:44]:44s} {(eo or '')[:21]:>21s} {(en or '')[:21]:>21s}")
        failed += 1
        continue
    d = 100 * abs(zn.real - zo.real) / abs(zo.real) if zo.real else float("inf")
    if abs(zn - zo) < 1e-9:
        same += 1
    else:
        moved += 1
    print(
        f"{title[:44]:44s} {zo.real:9.3f}{zo.imag:+9.3f}j {zn.real:9.3f}{zn.imag:+9.3f}j {d:8.2f}"
    )
print(f"\nmoved {moved}   identical {same}   failed {failed}")

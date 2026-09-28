"""Driving example E7 for the sweep framework (AK#1757, 2026-09-28): two
segmentation methods, i.e. two antennas, on one convergence chart. The
catalog inverted vee fed through its 0.1 m bridge wire (`dipoles.invvee`),
against the same vee fed at its apex knot (`dipoles.invvee_apex`, #898),
on the engines that can feed a knot. Free space, the same dense ladder.
Run with the released package:

    NEC5_EXE=~/bin/nec5-licensed .venv-pypi/bin/python scratch/sweep-examples/ex7_spellings.py
"""

import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from antennaknobs.cli import get_builder, make_engine_factory, resolve_ground
from antennaknobs.sweep import _achieved_n

LADDER = [
    8,
    10,
    12,
    14,
    17,
    20,
    24,
    28,
    34,
    40,
    48,
    57,
    68,
    80,
    96,
    113,
    136,
    160,
    192,
    226,
    272,
]
ENGINES = ("momwire:bspline", "momwire:razor-2p", "nec5")
SPELLINGS = {
    "bridge (dipoles.invvee)": "dipoles.invvee",
    "apex knot (dipoles.invvee_apex)": "dipoles.invvee_apex",
}
OUT = "scratch/sweep-examples/ex7_spellings"

rows = []
for label, design in SPELLINGS.items():
    B = get_builder(design)
    ground = resolve_ground("free", B())
    for spec in ENGINES:
        fac = make_engine_factory(
            spec,
            ground,
            extended_kernel=False,
            deck_extended_kernel=False,
            nominal_nsegs=None,
        )
        for n in LADDER:
            b = B()
            b.nominal_nsegs = n
            eng = fac(b)
            z = complex(eng.impedance()[0])
            fed = eng.fed_segments()
            rows.append(
                dict(
                    spelling=label,
                    engine=spec,
                    n=n,
                    N=_achieved_n(eng, b),
                    fed_m=fed[0]["length_m"] if fed else None,
                    re=z.real,
                    im=z.imag,
                )
            )
with open(OUT + ".jsonl", "w") as f:
    for r in rows:
        f.write(json.dumps(r) + "\n")

colors = dict(zip(ENGINES, ("tab:blue", "tab:orange", "tab:green"), strict=True))
styles = dict(zip(SPELLINGS, ("-", "--"), strict=True))
fig, (ar, ax) = plt.subplots(1, 2, figsize=(13, 5))
for label in SPELLINGS:
    for spec in ENGINES:
        r = [x for x in rows if x["spelling"] == label and x["engine"] == spec]
        N = [x["N"] for x in r]
        for a, key in ((ar, "re"), (ax, "im")):
            a.plot(
                N,
                [x[key] for x in r],
                styles[label],
                color=colors[spec],
                marker=".",
                ms=4,
                lw=1.2,
                label=f"{spec} · {label.split(' (')[0]}",
            )
for a, t in ((ar, "R (Ω)"), (ax, "X (Ω)")):
    a.set_xscale("log")
    a.set_xlabel("segments achieved (log)")
    a.set_ylabel(t)
    a.grid(alpha=0.3, which="both")
ar.legend(fontsize=7)
ar.set_title("R: solid = bridge wire, dashed = apex knot")
ax.set_title("X")
fig.suptitle(
    "E7: one inverted vee, two feed spellings, three engines (free space, 28.47 MHz)"
)
fig.tight_layout()
fig.savefig(OUT + ".png", dpi=110)

for label in SPELLINGS:
    for spec in ENGINES:
        r = [x for x in rows if x["spelling"] == label and x["engine"] == spec]
        print(
            f"{label.split(' (')[0]:>9} {spec:>17}: N {r[0]['N']}->{r[-1]['N']}  "
            f"Z {r[0]['re']:.3f}{r[0]['im']:+.3f}j -> {r[-1]['re']:.3f}{r[-1]['im']:+.3f}j"
        )

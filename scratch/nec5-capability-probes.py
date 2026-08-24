"""NEC-5 capability audit probe battery (momwire seam side + two licensed runs).

Every seam status printed here is citable evidence; the licensed runs cover
the two model-level ground capabilities (interface-crossing wire, buried
radial screen) that momwire#524 names.
"""

import subprocess
from pathlib import Path

from momwire.eznec._shell import render

NEC5CL = Path.home() / "antennas/NEC5-downloads/nec5-linux/nec5cl"
ROOM = Path(__file__).parent / "audit-room"

MONO = "GW 1,15,0.,0.,10.,0.,0.,0.,.001\n"
TAIL = "FR 0,1,0,0,7.\nGN 0,0,0,0,13.,.005\nEX 4,1,7,0,1.,0.\nPQ 0\nXQ 0\nEN\n"


def deck(extra_geo="", ge="1,-1", tail=TAIL):
    return "CM probe\nCE\n" + MONO + extra_geo + f"GE {ge}\n" + tail


PROBES = [
    ("GA (wire arc)", deck(extra_geo="GA 2,8,2.,0.,90.,.001\n")),
    (
        "GC (tapered wire)",
        "CM probe\nCE\nGW 1,15,0.,0.,10.,0.,0.,0.,.002\n"
        "GC 0,0,.9,.002,.001\nGE 1,-1\n" + TAIL,
    ),
    ("CW (catenary)", deck(extra_geo="CW 2,8,0.,0.,10.,5.,0.,10.,1.,.001\n")),
    ("GH (helix)", deck(extra_geo="GH 2,20,.1,1.,.5,.5,.5,.5,.001\n")),
    ("GM (transform)", deck(extra_geo="GM 0,0,0.,0.,45.,0.,0.,0.\n")),
    ("GR (cylindrical symmetry)", deck(extra_geo="GR 0,4\n")),
    ("GX (reflection symmetry)", deck(extra_geo="GX 2,110\n")),
    ("GS (scale)", deck(extra_geo="GS 0,0,.3048\n")),
    ("CY (cylinder surface)", deck(extra_geo="CY 2,8,4,1.,5.,0.\n")),
    ("SP (sphere surface)", deck(extra_geo="SP 2,8,4,1.\n")),
    ("QP (quad plate)", deck(extra_geo="QP 2,4,4,0.,0.,1.,1.,0.,1.,1.,0.,2.\n")),
    ("NL (node/element input)", deck(extra_geo="NL 2,1\n")),
    (
        "PA (parameter definition)",
        "CM probe\nCE\nPA L 10.\n" + MONO + "GE 1,-1\n" + TAIL,
    ),
    (
        "UM (upper medium)",
        deck(
            tail="FR 0,1,0,0,7.\nGN 0,0,0,0,13.,.005\n"
            "UM 4.,.001\nEX 4,1,7,0,1.,0.\nPQ 0\nXQ 0\nEN\n"
        ),
    ),
    (
        "NX (next structure)",
        deck().replace("EN\n", "NX\nCM probe2\nCE\n" + MONO + "GE 1,-1\n" + TAIL),
    ),
    (
        "LE (near E along line)",
        deck(
            tail="FR 0,1,0,0,7.\n"
            "GN 0,0,0,0,13.,.005\nEX 4,1,7,0,1.,0.\nLE 0,1.,0.,1.,0.,0.,.5,10\n"
            "XQ 0\nEN\n"
        ),
    ),
    (
        "EX 1 (incident wave)",
        deck(
            tail="FR 0,1,0,0,7.\n"
            "GN 0,0,0,0,13.,.005\nEX 1,1,1,0,0.,0.,0.\nRP 0,1,361,1000,90.,0.,0.,1.,0.\nEN\n"
        ),
    ),
    (
        "EX 5 (current-slope)",
        deck(
            tail="FR 0,1,0,0,7.\n"
            "GN 0,0,0,0,13.,.005\nEX 5,1,7,0,1.,0.\nPQ 0\nXQ 0\nEN\n"
        ),
    ),
    (
        "LD 2 (series RLC dist)",
        deck(
            tail="FR 0,1,0,0,7.\n"
            "GN 0,0,0,0,13.,.005\nEX 4,1,7,0,1.,0.\nLD 2,1,3,3,1.,1e-6,1e-12\n"
            "PQ 0\nXQ 0\nEN\n"
        ),
    ),
    (
        "GN with mu_r != 1",
        deck(
            tail="FR 0,1,0,0,7.\n"
            "GN 0,0,0,0,13.,.005,2.,0.\nEX 4,1,7,0,1.,0.\nPQ 0\nXQ 0\nEN\n"
        ),
    ),
    (
        "GN with table file name",
        deck(
            tail="FR 0,1,0,0,7.\n"
            "GN 0,0,0,0,13.,.005,1.,0.,TABLES.NEX\nEX 4,1,7,0,1.,0.\nPQ 0\nXQ 0\nEN\n"
        ),
    ),
    (
        "wire crossing the interface",
        "CM probe\nCE\nGW 1,4,0.,0.,-2.,0.,0.,0.\n".replace("\n", ",.001\n")
        + "GW 2,15,0.,0.,0.,0.,0.,10.,.001\nGE 1,-1\n"
        + TAIL.replace("EX 4,1,7", "EX 4,2,7"),
    ),
    (
        "buried 4-radial screen",
        "CM probe\nCE\n"
        + "GW 1,15,0.,0.,10.,0.,0.,0.,.001\n"
        + "".join(
            f"GW {t},10,0.,0.,0.,{x}.,{y}.,-0.15,.001\n"
            for t, (x, y) in enumerate([(5, 0), (0, 5), (-5, 0), (0, -5)], start=2)
        )
        + "GE 1,-1\n"
        + TAIL,
    ),
]


def seam_status(text):
    try:
        out = render(text)
    except Exception as e:
        return f"EXCEPTION {type(e).__name__}: {str(e)[:90]}"
    if " ***** NEC ERROR - " in out:
        return "refuse: " + out.split(" ***** NEC ERROR - ")[1].split("\n")[0][:130]
    return "SERVES"


def nec5cl_status(text, name):
    d = ROOM / name.split()[0].strip("(),")
    d.mkdir(parents=True, exist_ok=True)
    (d / "deck.nec").write_text(text)
    subprocess.run(
        [str(NEC5CL), "deck.nec", "out.txt"], cwd=d, capture_output=True, timeout=300
    )
    out = (d / "out.txt").read_text(encoding="latin-1", errors="replace")
    if "ANTENNA INPUT PARAMETERS" in out:
        for line in out.splitlines():
            p = line.split()
            if len(p) >= 9 and p[0].isdigit() and "E" in p[7]:
                return f"serves (Z = {p[7]} + j{p[8]})"
        return "serves"
    err = [l for l in out.splitlines() if "ERROR" in l.upper()]
    return "engine says: " + (err[0][:100] if err else "(no input-params block)")


for name, text in PROBES:
    print(f"{name:32s} seam: {seam_status(text)}", flush=True)
for name in ("wire crossing the interface", "buried 4-radial screen"):
    text = dict(PROBES)[name]
    print(f"{name:32s} nec5cl: {nec5cl_status(text, name)}", flush=True)

"""Dense X(knob0) curves at each start's knob1, for the one-knob figure."""

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from harness import Deck
from run_all import STARTS

HERE = Path(__file__).resolve().parent

kind, n = sys.argv[1], int(sys.argv[2])
d = Deck(kind)
lo, hi = d.box[0]
out = {"knobs": d.knobs, "box": d.box, "z0": d.z0, "curves": {}}
for sname, x0 in STARTS[kind].items():
    vs = np.linspace(lo, hi, n)
    X, R = [], []
    for v in vs:
        z = d.z((v, x0[1]))
        X.append(z.imag)
        R.append(z.real)
    d.flush()
    out["curves"][sname] = {"knob1": x0[1], "v": vs.tolist(), "X": X, "R": R}
    print(f"  {sname}: X {min(X):.1f} .. {max(X):.1f}", flush=True)
(HERE / f"curve_{kind}.json").write_text(json.dumps(out))
print("wrote", f"curve_{kind}.json")

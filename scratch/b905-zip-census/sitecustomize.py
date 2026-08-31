"""Observe every zip() call site without changing behaviour.

Records, per call site, whether the arguments had equal lengths. Returns the
real (non-strict) zip every time, so the run behaves exactly as it does today
— the point is to find out which sites would ever have raised under
strict=True, not to make them raise.
"""

import atexit
import builtins
import json
import os
import sys
from collections import defaultdict

_real_zip = builtins.zip
_ROOT = os.environ.get("ZIPCENSUS_ROOT", "")
_OUT = os.environ.get("ZIPCENSUS_OUT", "/tmp/zipcensus.json")

# site -> counters
_c = defaultdict(
    lambda: {"calls": 0, "equal": 0, "unequal": 0, "unsized": 0, "shapes": set()}
)


def _zip(*args, **kwargs):
    if args:
        try:
            f = sys._getframe(1)
            fn = f.f_code.co_filename
            if fn.startswith(_ROOT) and "/.venv/" not in fn:
                rec = _c[f"{fn[len(_ROOT) :].lstrip('/')}:{f.f_lineno}"]
                rec["calls"] += 1
                try:
                    lens = [len(a) for a in args]
                except TypeError:
                    rec["unsized"] += 1
                else:
                    if len(set(lens)) <= 1:
                        rec["equal"] += 1
                    else:
                        rec["unequal"] += 1
                        if len(rec["shapes"]) < 5:
                            rec["shapes"].add(tuple(lens))
        except Exception:  # noqa: BLE001 — instrumentation must never break the run
            pass
    return _real_zip(*args, **kwargs)


def _dump():
    out = {k: {**v, "shapes": sorted(v["shapes"])} for k, v in _c.items()}
    try:
        with open(_OUT, "w") as fh:
            json.dump(out, fh, indent=1, sort_keys=True)
    except Exception:  # noqa: BLE001 — best effort at interpreter shutdown
        pass


builtins.zip = _zip
atexit.register(_dump)

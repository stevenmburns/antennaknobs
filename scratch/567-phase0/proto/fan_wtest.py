"""The blind transfer test: apply the lone-radial-fitted boundary weight
w* to the FAN deck untouched. 2 new real equations, 0 new dof — if the
contact-endpoint rule is real physics, w* must land inside the envelope
here too. Also refits fan's own w* for comparison, and caches the fan
tables to disk for reuse."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from scipy.optimize import minimize

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "momwire" / "tests"))

from mp_cross import mp_cross_block, seeded  # noqa: E402
from probe3 import ANCHORS, BUILDS, solve_with_weight  # noqa: E402

W_STAR_CONTACT = 0.4197 + 0.1510j


def main():
    deck = "fan"
    anchor = ANCHORS[deck]
    s = seeded(BUILDS[deck]())
    cache = HERE.parent / "results" / "fan-tables.npz"
    tables = None
    if cache.exists():
        d = np.load(cache)
        tables = {k: d[k] for k in ("U", "V", "W", "dzW")}
    mp = mp_cross_block(s, rtol=1e-10, tables=tables)
    if not cache.exists():
        cache.parent.mkdir(exist_ok=True)
        np.savez(cache, **mp["tables"])

    z, _ = solve_with_weight(deck, mp, W_STAR_CONTACT)
    transfer_miss = abs(z - anchor)
    print(
        f"TRANSFER  w*(contact) = {W_STAR_CONTACT}  ->  Z = {z:.4f}  "
        f"miss = {transfer_miss:.3f} ohm  (anchor {anchor})"
    )

    def miss(wv):
        zz, _ = solve_with_weight(deck, mp, complex(wv[0], wv[1]))
        return abs(zz - anchor)

    r = minimize(
        miss,
        [W_STAR_CONTACT.real, W_STAR_CONTACT.imag],
        method="Nelder-Mead",
        options=dict(xatol=1e-3, fatol=1e-3, maxfev=60),
    )
    w_fan = complex(r.x[0], r.x[1])
    z_fan, _ = solve_with_weight(deck, mp, w_fan)
    print(
        f"REFIT     w*(fan) = {w_fan:.4f}  ->  Z = {z_fan:.4f}  miss = {r.fun:.3f} ohm"
    )

    (HERE.parent / "results" / "fan-wtest.json").write_text(
        json.dumps(
            dict(
                w_contact=str(W_STAR_CONTACT),
                transfer_z=f"{z:.4f}",
                transfer_miss=round(float(transfer_miss), 3),
                w_fan=str(w_fan),
                refit_z=f"{z_fan:.4f}",
                refit_miss=round(float(r.fun), 3),
            ),
            indent=1,
        )
    )


if __name__ == "__main__":
    main()

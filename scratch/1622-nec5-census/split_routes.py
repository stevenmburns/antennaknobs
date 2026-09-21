"""Which route owns each disagreement: both, AK only, or serve only?

`census.py` measures antennaknobs against the licensed engine. This adds
`momwire.eznec.serve` at the SAME matched basis, so every deck splits three
ways: a gap BOTH routes share is momwire's model, a gap only one carries is
that route's own defect.

The SAME basis includes the extended kernel, which serve has no argument for:
it takes EK from the deck's own card, and the NEC-5 dialect has none (the parser
refuses one). So `razor-2p`'s roster entry is widened here to carry
`extended_kernel=True`, and `check_arrival` confirms it reached `RazorSolver`.
"""

from __future__ import annotations

import json
import pathlib
import sys
import warnings

warnings.filterwarnings("ignore")

import numpy as np  # noqa: E402
from momwire.deck._nec5 import parse_nec5  # noqa: E402
from momwire.eznec import _serve, serve  # noqa: E402

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from census import ARRIVED, DECKS, nec5  # noqa: E402

_basis_entry = _serve.basis_entry


def _matched_basis_entry(basis):
    solver_class, kwargs = _basis_entry(basis)
    return solver_class, {**kwargs, "extended_kernel": True}


_serve.basis_entry = _matched_basis_entry


def check_arrival() -> None:
    """The matched basis must be what REACHED the solver, not what was asked."""
    ARRIVED.clear()
    text = (DECKS / "0010_dipole-in-free-space.nec").read_text(errors="replace")
    serve(parse_nec5(text), basis="razor-2p")
    if not ARRIVED or not all(
        a.get("nec5_quadrature") and a.get("extended_kernel") for a in ARRIVED
    ):
        raise SystemExit(f"ARRIVAL FAILED: serve's RazorSolver received {ARRIVED!r}")
    print("arrival OK (serve: nec5_quadrature + extended_kernel reached RazorSolver)")


# Above this, a route is "off"; below, it is at the corpus noise floor.
BAR = 1e-3


def main() -> None:
    check_arrival()
    here = pathlib.Path(__file__).resolve().parent
    cen = {
        r["deck"]: r
        for r in (
            json.loads(line)
            for line in (here / "census_r1.jsonl").read_text().splitlines()
        )
    }
    out = []
    for i, stem in enumerate(sorted(cen), 1):
        rec = {"deck": stem, "ak": cen[stem].get("rel_max")}
        try:
            text = (DECKS / f"{stem}.nec").read_text(errors="replace")
            ref = nec5(text)
            sv = np.asarray(
                [
                    complex(s.impedance)
                    for s in serve(parse_nec5(text), basis="razor-2p").sources
                ]
            )
            rec["serve"] = (
                float(np.max(np.abs(sv - ref) / np.abs(ref)))
                if sv.shape == ref.shape
                else None
            )
        except Exception as exc:  # noqa: BLE001 — a census records refusals as data
            rec["serve"] = None
            rec["error"] = f"{type(exc).__name__}: {exc}"[:200]
        a, s = rec["ak"], rec["serve"]
        if a is None or s is None:
            rec["owner"] = "unmeasured"
        elif a <= BAR and s <= BAR:
            rec["owner"] = "both fine"
        elif a > BAR and s > BAR:
            rec["owner"] = "SHARED (momwire model)"
        elif a > BAR:
            rec["owner"] = "AK-SIDE ONLY"
        else:
            rec["owner"] = "SERVE-SIDE ONLY"
        out.append(rec)
        print(f"[{i:>3}/{len(cen)}] {stem:<48} {rec['owner']}", flush=True)
    (here / "split_routes.jsonl").write_text(
        "\n".join(json.dumps(r) for r in out) + "\n"
    )


if __name__ == "__main__":
    main()

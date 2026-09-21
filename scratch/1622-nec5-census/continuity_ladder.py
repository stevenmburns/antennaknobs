"""Is the drive-point continuity gap only convergence? (AK#1622)

The two routes into momwire's degree-2 B-spline lane disagree on 0116/0117 and
0028 because they hand the solver different topologies at a drive point: serve
cuts the fed wire there, which clamps the basis, and antennaknobs keeps it whole
with a positioned feed. At matched razor-2p the routes agree to float noise, so
nothing else differs.

This refines all three decks together and runs four lanes on the SAME deck text
at every rung, the extended kernel ON in all of them (`--no-ek` for the reduced
kernel on the momwire lanes):

* `ak`     - antennaknobs' default route (`MomwireEngine`, degree-2 B-spline);
* `serve`  - `momwire.eznec.serve`, default `bspline` basis;
* `razor`  - antennaknobs' route at razor-2p + nec5_quadrature (NEC-5's own
             formulation, the lane that reproduces the licensed engine);
* `nec5`   - the licensed `nec5cl` itself.

If the gap is only convergence, `ak` and `serve` close on each other as the mesh
refines and all four head for one limit. Every rung records the segment count
each route actually solved and the kwargs that actually reached each solver,
and the run aborts if EK did not arrive.

    python continuity_ladder.py --r 1,2,4,8,16,32 --out continuity_ladder.jsonl
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time
import warnings

warnings.filterwarnings("ignore")

import numpy as np  # noqa: E402
from momwire import BSplineSolver  # noqa: E402
from momwire.deck._nec5 import parse_nec5  # noqa: E402
from momwire.eznec import _serve, serve  # noqa: E402
from momwire.razor import RazorSolver  # noqa: E402

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from census import DECKS, check_controls, nec5, refine  # noqa: E402

from antennaknobs.engines import MomwireEngine  # noqa: E402
from antennaknobs.file_designs import builder_from_file  # noqa: E402

STEMS = (
    "0116_40-meter-four-square-array",
    "0117_40-meter-four-square-array",
    "0028_17-10m-log-per-arrl-ant-book",
)

# serve takes EK only from the deck's own card, and this dialect has none, so
# its roster entries are widened to carry it (as `split_routes.py` does).
_basis_entry = _serve.basis_entry


def _with_ek(basis):
    solver_class, kwargs = _basis_entry(basis)
    return solver_class, {**kwargs, "extended_kernel": True}


_serve.basis_entry = _with_ek

# What each solver's constructor actually received, per lane.
LAST: dict[str, dict] = {}


def _record(cls, key):
    init = cls.__init__

    def recording(self, *args, **kwargs):
        LAST[key] = kwargs
        init(self, *args, **kwargs)

    cls.__init__ = recording


_record(BSplineSolver, "bspline")
_record(RazorSolver, "razor")


def _unknowns(kwargs) -> int:
    """Segments the solver was given: the sum over its wires' edge counts."""
    per = kwargs.get("n_per_edge_per_wire") or []
    return int(sum(sum(edges) for edges in per))


def _arrived(key, **want) -> dict:
    got = LAST.pop(key, None)
    if got is None:
        raise SystemExit(f"ARRIVAL FAILED: no {key} solver was constructed")
    for k, v in want.items():
        if bool(got.get(k)) != v:
            raise SystemExit(f"ARRIVAL FAILED: {key} got {k}={got.get(k)!r}")
    return got


def _z(values) -> list[list[float]]:
    return [[complex(z).real, complex(z).imag] for z in values]


def rung(stem: str, r: int, work: pathlib.Path, ek: bool = True) -> dict:
    text = refine((DECKS / f"{stem}.nec").read_text(errors="replace"), r)
    path = work / f"{stem}_r{r}.nec"
    path.write_text(text)
    rec: dict = {"deck": stem, "r": r, "ek": ek}
    cls = builder_from_file(str(path))

    t0 = time.perf_counter()
    ak = MomwireEngine(cls(), ground=cls.file_ground, extended_kernel=ek).impedance()
    kw = _arrived("bspline", extended_kernel=ek)
    rec["ak"], rec["ak_segments"] = _z(ak), _unknowns(kw)
    rec["ak_s"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    _serve.basis_entry = _with_ek if ek else _basis_entry
    sv = [s.impedance for s in serve(parse_nec5(text), basis="bspline").sources]
    kw = _arrived("bspline", extended_kernel=ek)
    rec["serve"], rec["serve_segments"] = _z(sv), _unknowns(kw)
    rec["serve_s"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    rz = MomwireEngine(
        cls(),
        ground=cls.file_ground,
        solver=RazorSolver,
        solver_kwargs={"nec5_quadrature": True},
        extended_kernel=ek,
    ).impedance()
    kw = _arrived("razor", extended_kernel=ek, nec5_quadrature=True)
    rec["razor"], rec["razor_segments"] = _z(rz), _unknowns(kw)
    rec["razor_s"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    rec["nec5"] = _z(nec5(text))
    rec["nec5_s"] = time.perf_counter() - t0
    return rec


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--r", default="1,2,4,8,16,32")
    ap.add_argument("--only", default=None, help="comma-separated stems")
    ap.add_argument("--out", default="continuity_ladder.jsonl")
    ap.add_argument(
        "--no-ek",
        action="store_true",
        help="reduced kernel on the momwire lanes (nec5cl has no switch)",
    )
    args = ap.parse_args()
    check_controls()
    stems = args.only.split(",") if args.only else STEMS
    here = pathlib.Path(__file__).resolve().parent
    work = here / "_decks"
    work.mkdir(exist_ok=True)
    out = pathlib.Path(args.out)
    with out.open("a") as fh:
        for r in (int(x) for x in args.r.split(",")):
            for stem in stems:
                rec = rung(stem, r, work, ek=not args.no_ek)
                fh.write(json.dumps(rec) + "\n")
                fh.flush()
                z = {
                    k: np.asarray([complex(*c) for c in rec[k]])
                    for k in ("ak", "serve", "razor", "nec5")
                }
                gap = float(np.max(np.abs(z["ak"] - z["serve"]) / np.abs(z["serve"])))
                print(
                    f"r={r:>3} {stem[:4]} segs ak/serve/razor "
                    f"{rec['ak_segments']}/{rec['serve_segments']}/{rec['razor_segments']}"
                    f"  ak-serve {gap:.3e}  ak {z['ak'][0]:.5f}  serve {z['serve'][0]:.5f}"
                    f"  razor {z['razor'][0]:.5f}  nec5 {z['nec5'][0]:.5f}"
                    f"  ({rec['ak_s'] + rec['serve_s'] + rec['razor_s'] + rec['nec5_s']:.1f} s)",
                    flush=True,
                )


if __name__ == "__main__":
    main()

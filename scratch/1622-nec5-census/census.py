"""Adjudicate the EZNEC corpus against the LICENSED NEC-5, at a MATCHED BASIS.

Why this exists. Every routine gate in this repo compares antennaknobs'
`builder_from_file` route against `momwire.eznec.serve` -- a CONSISTENCY bar. It
says "the same computation", never "the right computation", and by AK#1619 it
had saturated: 23 of 28 networked decks sit at float noise and the rest are
inside the bspline basis error, which is where AK#1622 stopped.

The instrument that HAS resolution is razor-2p + `nec5_quadrature` +
`extended_kernel` -- NEC-5's own formulation -- against `nec5cl` itself. It reads
0.00 % where it agrees. It had never been run across the corpus; roughly ten decks
had been done by hand.

The extended kernel is part of the MATCH. NEC-5 has no `EK` card and rejects one,
because its kernel is exact natively, so the matched momwire run has it ON. It is
not only about fat wires: 0067, at Delta/a = 40, moves 23x with it. The first
version of this census ran it off.

Method rules this obeys, each learned the expensive way:

* EVERY number in one comparison comes from ONE configuration. Both sides here
  read the SAME deck text. Nothing is translated between dialects, which is what
  AK#1515 says poisons the older `scratch/896-census` harness (it feeds momwire
  through the NEC-2 reader a deck written in the NEC-5 dialect, so a knot source
  lands half a segment out).
* NEC-5 needs an `XQ` card or it reads the cards and stops with no results, so a
  malformed probe reads as a refusal. Hence `CONTROLS`: if 0012 does not come
  back at 114.4700 + 21.0960j the harness is wrong and the run aborts.
* Impedance is fields 7-8 (0-based) of an ANTENNA INPUT PARAMETERS row -- three
  leading integer columns are tag, GLOBAL segment, node. The printed
  `FREQUENCY=` cell is only 5 digits; never read frequency from there.

Courtesy rule: never cite NEC-5 internals publicly, only "verified against our
licensed materials".
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import traceback
import warnings

warnings.filterwarnings("ignore")

import momwire  # noqa: E402
import numpy as np  # noqa: E402
from momwire.razor import RazorSolver  # noqa: E402

from antennaknobs.engines import MomwireEngine  # noqa: E402
from antennaknobs.engines.nec5 import run_deck  # noqa: E402
from antennaknobs.file_designs import builder_from_file  # noqa: E402

DECKS = (
    pathlib.Path(momwire.__file__).resolve().parents[2] / "tests/fixtures/eznec/decks"
)
EXE = str(pathlib.Path.home() / "antennas/NEC5-downloads/nec5-linux/nec5cl")
MATCHED = dict(
    solver=RazorSolver,
    solver_kwargs={"nec5_quadrature": True},
    extended_kernel=True,
)

# What `RazorSolver.__init__` actually received, for `check_arrival`: the engine
# documents that a solver without the requested model falls back to its best
# available one, so a request is not evidence.
ARRIVED: list[dict] = []
_razor_init = RazorSolver.__init__


def _recording_init(self, *args, **kwargs):
    ARRIVED.append(dict(kwargs))
    _razor_init(self, *args, **kwargs)


RazorSolver.__init__ = _recording_init

# Decks whose licensed answer is already written down elsewhere in the repo.
# If either fails, the harness is lying and every other row is worthless.
CONTROLS = {
    "0012_network-connection-test": complex(114.4700, 21.0960),
    "0016_network-connection-test": complex(114.4700, 21.0960),
}


def refine(text: str, r: int) -> str:
    """The deck text with every wire's segment count multiplied by `r`, and
    every card that names a place on a wire moved to the same place.

    In this dialect every such address is a KNOT, whatever the card. `EX`
    names end 2 of segment s, the same knot `TL` and `NT` name; its fourth
    field 0 reads as 2, measured on the licensed binary (on 0010, `EX 4,1,3,0`,
    `EX 4,1,3,2` and `EX 4,1,4,1` all print 139.55 + 39.37j, `EX 4,1,3,1`
    275.92 + 35.744j). A knot at s/n refines to s*r. The first version read `EX`
    as a segment CENTRE, round((s - 1/2) r + 1/2); on 0011's one-segment feed
    wire that put the p1 knot at an interior knot, a different one per r, which
    is what made 0011/0030 look non-monotonic.

    A NEGATIVE field is an END SELECTOR, not a segment, and is never scaled
    (the first version turned `TL 2,-1,4,1` into `TL 2,-3,4,3`).

    A PHANTOM wire -- the virtual-node idiom -- is left alone: its `LD` pins
    address fixed segments, and refining it floats the virtual nodes into a
    `SingularNetworkError`. A tag is phantom when it carries an open-circuit
    pin, an `LD` of 1e9 ohm or more, NOT merely an `LD`: the four-squares and
    cardioids carry real 18-ohm loads on their radiators, and the first version
    left those radiators unrefined. A real load at a positive segment is
    refused rather than guessed; the corpus has none (all 20 sit at -1)."""
    if r == 1:
        return text
    phantom = _phantom_tags(text)
    out = []
    for line in text.splitlines():
        f = [x.strip() for x in line.replace(",", " ").split()]
        if f and f[0] == "GW" and int(f[1]) not in phantom:
            f[2] = str(int(f[2]) * r)
            out.append("GW " + ",".join(f[1:]))
        elif f and f[0] in ("EX", "TL", "NT"):
            pairs = ((2, 3),) if f[0] == "EX" else ((1, 2), (3, 4))
            for tag_i, seg_i in pairs:
                tag, seg = int(f[tag_i]), int(f[seg_i])
                if tag not in phantom and seg > 0:
                    f[seg_i] = str(seg * r)
            out.append(f[0] + " " + ",".join(f[1:]))
        elif f and f[0] == "LD" and len(f) >= 4:
            tag, seg = int(f[2]), int(f[3])
            if tag not in phantom and seg > 0:
                raise ValueError(f"refine: a real load at segment {seg}: {line!r}")
            out.append(line.rstrip())
        else:
            out.append(line.rstrip())
    return "\n".join(out) + "\n"


def _phantom_tags(text: str) -> set[int]:
    """Tags carrying an `LD` open-circuit pin (1e9 ohm or more): the
    virtual-node idiom, and nothing else."""
    tags = set()
    for line in text.splitlines():
        f = [x.strip() for x in line.replace(",", " ").split()]
        # LD type, tag, segment, end, R, ...: the resistance is field 5.
        if f and f[0] == "LD" and len(f) >= 6:
            try:
                if float(f[5]) >= 1e9:
                    tags.add(int(f[2]))
            except ValueError:
                pass
    return tags


def nec5(text: str, timeout: float = 900) -> np.ndarray:
    """The licensed engine's driving-point impedances for `text`, in card order."""
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not any(ln[:2] == "XQ" for ln in lines):
        end = next((j for j, ln in enumerate(lines) if ln[:2] == "EN"), len(lines))
        lines.insert(end, "XQ")
    out = run_deck(EXE, "\n".join(lines) + "\n", timeout=timeout)
    rows: list[complex] = []
    grabbing = False
    for ln in out.splitlines():
        if "ANTENNA INPUT PARAMETERS" in ln:
            grabbing = True
            continue
        if not grabbing:
            continue
        f = ln.split()
        if len(f) >= 9 and f[0].lstrip("-").isdigit():
            rows.append(complex(float(f[7]), float(f[8])))
        elif rows and not ln.strip():
            grabbing = False
    return np.asarray(rows)


def ak(path: str) -> np.ndarray:
    cls = builder_from_file(path)
    eng = MomwireEngine(cls(), ground=cls.file_ground, **MATCHED)
    return np.asarray(eng.impedance())


def check_controls() -> None:
    for stem, want in CONTROLS.items():
        got = nec5((DECKS / f"{stem}.nec").read_text(errors="replace"))
        if got.size != 1 or abs(got[0] - want) / abs(want) > 1e-6:
            raise SystemExit(
                f"CONTROL FAILED: {stem} read {got!r}, expected {want!r}. "
                "The harness is wrong; every other row would be worthless."
            )
    print(f"controls OK ({', '.join(CONTROLS)})", flush=True)


def check_arrival() -> None:
    """The matched basis must be what REACHED the solver, not what was asked."""
    ARRIVED.clear()
    ak(str(DECKS / "0010_dipole-in-free-space.nec"))
    if not ARRIVED or not all(
        a.get("nec5_quadrature") and a.get("extended_kernel") for a in ARRIVED
    ):
        raise SystemExit(f"ARRIVAL FAILED: RazorSolver received {ARRIVED!r}")
    print("arrival OK (nec5_quadrature + extended_kernel reached RazorSolver)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--r", type=int, default=1, help="mesh refinement factor")
    ap.add_argument("--out", default="census.jsonl")
    ap.add_argument("--only", default=None, help="comma-separated stems")
    args = ap.parse_args()

    check_controls()
    check_arrival()
    stems = sorted(p.stem for p in DECKS.glob("*.nec"))
    if args.only:
        want = set(args.only.split(","))
        stems = [s for s in stems if s in want]

    work = pathlib.Path(args.out).resolve().parent / "_decks"
    work.mkdir(parents=True, exist_ok=True)
    rows = []
    for i, stem in enumerate(stems, 1):
        rec = {"deck": stem, "r": args.r}
        try:
            text = refine((DECKS / f"{stem}.nec").read_text(errors="replace"), args.r)
            path = work / f"{stem}_r{args.r}.nec"
            path.write_text(text)
            ref = nec5(text)
            got = ak(str(path))
            rec["n_nec5"], rec["n_ak"] = int(ref.size), int(got.size)
            if ref.size == 0:
                rec["status"] = "nec5-no-sources"
            elif ref.size != got.size:
                rec["status"] = "shape-mismatch"
            else:
                rel = np.abs(got - ref) / np.abs(ref)
                rec["status"] = "ok"
                rec["rel_max"] = float(np.max(rel))
                rec["ak"] = [[z.real, z.imag] for z in got]
                rec["nec5"] = [[z.real, z.imag] for z in ref]
        except Exception as exc:  # noqa: BLE001 — a census records refusals as data
            rec["status"] = "raised"
            rec["error"] = f"{type(exc).__name__}: {exc}"[:400]
            rec["trace"] = traceback.format_exc()[-600:]
        rows.append(rec)
        flag = rec.get("rel_max")
        print(
            f"[{i:>3}/{len(stems)}] {stem:<48} {rec['status']:<18}"
            + (f" {flag:.3e}" if flag is not None else ""),
            flush=True,
        )
    pathlib.Path(args.out).write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    ok = [r for r in rows if r["status"] == "ok"]
    print(f"\nwrote {args.out}: {len(rows)} decks, {len(ok)} adjudicated", flush=True)
    if ok:
        v = sorted(r["rel_max"] for r in ok)
        print(f"  median {v[len(v) // 2]:.3e}   worst {v[-1]:.3e}")
        for bar, label in ((1e-4, "<= 0.01 %"), (3e-2, "<= 3 % (agreement)")):
            print(f"  {sum(1 for x in v if x <= bar):>3} of {len(v)} {label}")


if __name__ == "__main__":
    sys.exit(main())

"""AK#1456 side finding: momwire's NEC-2 portal ignores NEC-5's EX end selector.

The #896 corpus census runs both engines on the TRANSLATED decks (NEC-5
dialect), where `translate` moves a centre feed onto a knot: `EX 0 tag k 2`,
the end of segment k. momwire's portal reads the EX card as NEC-2 does, as
(tag, seg), and drives the CENTRE of segment k. So on those decks momwire's
source sits half a segment from the knot NEC-5 drives.

Probe: a 10-segment half-wave dipole in free space, fed four ways through
`momwire.portal.run_deck`:
  * `EX 0 1 5 2` (the translated spelling) and `EX 0 1 5 0` read the same,
    so the fourth field is not read;
  * `EX 0 1 6 2` reads the same as segment 5, the mirror point, so the source
    is at a segment centre (0.45 / 0.55 of the wire), not at knot 5 (0.50);
  * 11 segments with `EX 0 1 6 0` is the true centre, for scale.

  PYTHONPATH=<momwire src> python scratch/1456-fed-segments/probe_end_selector.py
"""

from __future__ import annotations

import json
from pathlib import Path

from momwire.portal import run_deck


def deck(n, seg, sel):
    return "\n".join(
        [
            "CM end-selector probe",
            "CE",
            f"GW 1 {n} 0 -5 10 0 5 10 0.001",
            "GE 0",
            "FR 0 1 0 0 14.3 0",
            f"EX 0 1 {seg} {sel} 1 0",
            "XQ",
            "EN",
            "",
        ]
    )


def z(body):
    out, _err = run_deck(body)
    lines = out.splitlines()
    i = next(k for k, ln in enumerate(lines) if "ANTENNA INPUT PARAMETERS" in ln)
    for ln in lines[i + 1 : i + 8]:
        t = ln.split()
        if len(t) >= 11 and t[0].isdigit():
            return complex(float(t[6]), float(t[7]))
    raise RuntimeError("no input-parameters row")


def main():
    cases = [
        ("10 segs, EX 5 end 2 (translated)", 10, 5, 2),
        ("10 segs, EX 5 field 0", 10, 5, 0),
        ("10 segs, EX 6 end 2 (mirror)", 10, 6, 2),
        ("11 segs, EX 6 (true centre)", 11, 6, 0),
    ]
    rows = []
    for label, n, seg, sel in cases:
        zz = z(deck(n, seg, sel))
        rows.append(dict(label=label, n=n, seg=seg, field4=sel, z=[zz.real, zz.imag]))
        print(f"{label:34s} {zz.real:.4f} {zz.imag:+.4f}j")
    ztr, zc = complex(*rows[0]["z"]), complex(*rows[3]["z"])
    summary = dict(
        field4_ignored=rows[0]["z"] == rows[1]["z"],
        mirror_equal=rows[0]["z"] == rows[2]["z"],
        dR_vs_true_centre_pct=100 * (ztr.real - zc.real) / zc.real,
    )
    print(json.dumps(summary))
    out = Path(__file__).resolve().parent / "probe_end_selector.json"
    out.write_text(json.dumps(dict(rows=rows, summary=summary), indent=1))


if __name__ == "__main__":
    main()

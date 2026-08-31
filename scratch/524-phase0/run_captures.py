"""momwire#524 phase 0 — nec5cl oracle capture driver.

Runs every capture twice (stock / EZParam.txt EZ5 off), parses Z and NE
blocks, accumulates oracle/captures.json.  Stages are selectable so the
capture campaign can be built up incrementally:

    python3 run_captures.py anchors     # anchor decks x1, stock-only sanity
    python3 run_captures.py ladders     # anchor convergence ladders, A/B
    python3 run_captures.py ne          # buried-dipole NE matrix, A/B
    python3 run_captures.py control     # positive-control deck, A/B
    python3 run_captures.py json        # (re)write captures.json from disk
"""

import json
import math
import re
import subprocess
import sys
from pathlib import Path

NEC5CL = Path.home() / "antennas/NEC5-downloads/nec5-linux/nec5cl"
ROOT = Path(__file__).parent / "oracle"
EZOFF_LINE = "EZ5 0,0,0,-1.,-1.\n"


# ---------------------------------------------------------------- running


def run_once(cap_dir: Path, deck: str, ezoff: bool) -> str:
    cap_dir.mkdir(parents=True, exist_ok=True)
    (cap_dir / "deck.nec").write_text(deck)
    # CRITICAL: the engine caches Sommerfeld tables as *.NEX in the cwd and
    # silently reads them back on the next run, which would let the B run
    # reuse tables built under the A run's settings.  Scrub before EVERY run.
    for nex in cap_dir.glob("*.NEX"):
        nex.unlink()
    ez = cap_dir / "EZParam.txt"
    outname = "out_ezoff.txt" if ezoff else "out_stock.txt"
    if ezoff:
        ez.write_text(EZOFF_LINE)
    elif ez.exists():
        ez.unlink()
    out = cap_dir / "out.txt"
    if out.exists():
        out.unlink()
    subprocess.run(
        [str(NEC5CL), "deck.nec", "out.txt"],
        cwd=cap_dir,
        capture_output=True,
        timeout=300,
    )
    text = out.read_text(encoding="latin-1", errors="replace") if out.exists() else ""
    (cap_dir / outname).write_text(text, encoding="latin-1")
    if out.exists():
        out.unlink()
    if ezoff and ez.exists():
        # keep as a record of the B-run configuration
        pass
    return text


# ---------------------------------------------------------------- parsing


def parse_z(text: str):
    """Fed-segment row of ANTENNA INPUT PARAMETERS: 8th/9th fields = R, X."""
    if "ANTENNA INPUT PARAMETERS" not in text:
        return None
    block = text.split("ANTENNA INPUT PARAMETERS", 1)[1]
    for line in block.splitlines():
        p = line.split()
        if len(p) >= 9 and p[0].isdigit() and "E" in p[7]:
            try:
                return (float(p[7]), float(p[8]))
            except ValueError:
                continue
    return None


FLOATRE = re.compile(r"[-+]?\d*\.\d+(?:E[-+]?\d+)?|[-+]?\d+\.?(?:E[-+]?\d+)?")


def parse_ne_blocks(text: str):
    """Parse near-field tables: rows whose first 3 floats are coords followed
    by >=6 numeric field entries.  Returns list of blocks, each a list of
    {'xyz': [...], 'vals': [...]} rows, plus the header line seen."""
    blocks = []
    cur = None
    header = None
    for line in text.splitlines():
        u = line.upper()
        if "NEAR" in u and ("ELECTRIC" in u or "MAGNETIC" in u) and "FIELD" in u:
            if cur:
                blocks.append({"header": header, "rows": cur})
            cur = []
            header = line.strip()
            continue
        if cur is None:
            continue
        p = line.split()
        nums = []
        ok = len(p) >= 9
        if ok:
            for tok in p:
                try:
                    nums.append(float(tok))
                except ValueError:
                    ok = False
                    break
        if ok and len(nums) >= 9:
            cur.append({"xyz": nums[:3], "vals": nums[3:]})
        elif cur and (
            "ANTENNA" in u or "POWER" in u or "RUN TIME" in u or "* * * * *" in line
        ):
            blocks.append({"header": header, "rows": cur})
            cur = None
    if cur:
        blocks.append({"header": header, "rows": cur})
    return blocks


def ne_spread(blocks_a, blocks_b):
    """Max relative field-component delta.  vals are (mag, phase_deg) pairs
    per component; compare as complex numbers: |a-b| / max(|a|,|b|,floor)."""
    if len(blocks_a) != len(blocks_b):
        return None
    worst = 0.0
    for ba, bb in zip(blocks_a, blocks_b, strict=True):
        if len(ba["rows"]) != len(bb["rows"]):
            return None
        for ra, rb in zip(ba["rows"], bb["rows"], strict=True):
            va, vb = ra["vals"], rb["vals"]
            for i in range(0, min(len(va), len(vb)) - 1, 2):
                ca = va[i] * complex(
                    math.cos(math.radians(va[i + 1])), math.sin(math.radians(va[i + 1]))
                )
                cb = vb[i] * complex(
                    math.cos(math.radians(vb[i + 1])), math.sin(math.radians(vb[i + 1]))
                )
                denom = max(abs(ca), abs(cb), 1e-30)
                worst = max(worst, abs(ca - cb) / denom)
    return worst


# ---------------------------------------------------------------- capture

RESULTS_PATH = ROOT / "captures.json"


def load_results():
    if RESULTS_PATH.exists():
        return json.loads(RESULTS_PATH.read_text())
    return {}


def save_results(res):
    RESULTS_PATH.write_text(json.dumps(res, indent=1, sort_keys=True))


def capture(res, cap_id: str, deck: str, kind: str, note: str = ""):
    """Run A/B, parse, record, return the record."""
    d = ROOT / cap_id
    ta = run_once(d, deck, ezoff=False)
    tb = run_once(d, deck, ezoff=True)
    rec = {"kind": kind, "deck": deck, "note": note}
    za, zb = parse_z(ta), parse_z(tb)
    rec["Z_stock"] = za
    rec["Z_ezoff"] = zb
    if za and zb:
        rec["spread_dZ"] = math.hypot(za[0] - zb[0], za[1] - zb[1])
    else:
        rec["spread_dZ"] = None
    if kind.startswith("ne") or kind == "control":
        na, nb = parse_ne_blocks(ta), parse_ne_blocks(tb)
        rec["ne_stock"] = na
        rec["ne_ezoff"] = nb
        rec["ne_blocks"] = len(na)
        rec["ne_points"] = sum(len(b["rows"]) for b in na)
        rec["spread_ne_maxrel"] = ne_spread(na, nb)
    err = [l for l in ta.splitlines() if "ERROR" in l.upper()]
    rec["stock_errors"] = err[:5]
    rec["identical_output"] = ta == tb
    res[cap_id] = rec
    save_results(res)
    return rec


# ---------------------------------------------------------------- decks


def fed_seg(base_seg: int, base_n: int, mult: int) -> int:
    """Keep the fed segment centered on the same physical spot."""
    frac = (base_seg - 0.5) / base_n
    n = base_n * mult
    s = int(frac * n + 0.5)
    return min(max(s, 1), n)


TAIL_FMT = (
    "FR 0,1,0,0,{freq}\nGN 0,0,0,0,{eps},{sig}\n"
    "EX 4,{tag},{seg},0,1.,0.\nPQ 0\nXQ 0\nEN\n"
)


def anchor_deck(name: str, mult: int = 1) -> str:
    m = mult
    mono = f"GW 1,{15 * m},0.,0.,10.,0.,0.,0.,.001\n"
    if name == "lone-radial":
        # Reconstructed geometry that reproduces the 92.13 - j70.14 anchor:
        # flat radial at constant depth -0.15 m starting directly below the
        # monopole base (detached), NOT the sloping from-origin variant.
        geo = mono + f"GW 2,{10 * m},0.,0.,-0.15,5.,0.,-0.15,.001\n"
        ex_tag, ex_seg = 1, fed_seg(7, 15, m)
    elif name == "four-radial":
        geo = mono + "".join(
            f"GW {t},{10 * m},0.,0.,0.,{x}.,{y}.,-0.15,.001\n"
            for t, (x, y) in enumerate([(5, 0), (0, 5), (-5, 0), (0, -5)], start=2)
        )
        ex_tag, ex_seg = 1, fed_seg(7, 15, m)
    elif name == "crossing":
        geo = (
            f"GW 1,{4 * m},0.,0.,-2.,0.,0.,0.,.001\n"
            f"GW 2,{15 * m},0.,0.,0.,0.,0.,10.,.001\n"
        )
        ex_tag, ex_seg = 2, fed_seg(7, 15, m)
    else:
        raise ValueError(name)
    tail = TAIL_FMT.format(freq="7.", eps="13.", sig=".005", tag=ex_tag, seg=ex_seg)
    return "CM probe\nCE\n" + geo + "GE 1,-1\n" + tail


SOILS = {"A": ("13.", ".005"), "B": ("20.", ".03"), "C": ("5.", ".001")}

NE_CARDS = (
    # T-line: y=0, z=+1.0, x=2..30 step 2 (15 pts)
    "NE 0,15,1,1,2.,0.,1.,2.,0.,0.\n"
    # T-vert: x=10, y=0, z in {0.1,0.3,1,3,10} (5 single-point cards)
    + "".join(
        f"NE 0,1,1,1,10.,0.,{z},0.,0.,0.\n" for z in ("0.1", "0.3", "1.", "3.", "10.")
    )
    # M-line: y=0, z=-0.5, x=1..10 step 1 (10 pts)
    + "NE 0,10,1,1,1.,0.,-0.5,1.,0.,0.\n"
)


def dipole_geo(kind: str, depth: float) -> tuple[str, int, int]:
    """Return (GW lines, ex_tag, ex_seg)."""
    d = f"{-depth:.3g}"
    if kind == "bhd10":
        return (f"GW 1,21,-5.,0.,{d},5.,0.,{d},.001\n", 1, 11)
    if kind == "bhd1":
        return (f"GW 1,11,-0.5,0.,{d},0.5,0.,{d},.001\n", 1, 6)
    if kind == "bvd1":
        zlo = f"{-(depth + 1.0):.3g}"
        return (f"GW 1,11,0.,0.,{zlo},0.,0.,{d},.001\n", 1, 6)
    raise ValueError(kind)


def ne_deck(
    kind: str,
    depth: float,
    soil: str,
    freq_mhz: float,
    ne_after_xq: bool = False,
    extra_geo: str = "",
) -> str:
    geo, tag, seg = dipole_geo(kind, depth)
    eps, sig = SOILS[soil]
    head = f"CM 524p0 {kind} d={depth} soil{soil} {freq_mhz}MHz\nCE\n"
    body = geo + extra_geo + "GE 1,-1\n"
    fr = (
        f"FR 0,1,0,0,{freq_mhz:g}.\n"
        if float(freq_mhz).is_integer()
        else f"FR 0,1,0,0,{freq_mhz}\n"
    )
    gn = f"GN 0,0,0,0,{eps},{sig}\n"
    ex = f"EX 4,{tag},{seg},0,1.,0.\n"
    if ne_after_xq:
        tail = fr + gn + ex + "PQ 0\nXQ 0\n" + NE_CARDS + "EN\n"
    else:
        tail = fr + gn + ex + "PQ 0\n" + NE_CARDS + "XQ 0\nEN\n"
    return head + body + tail


# ---------------------------------------------------------------- stages


def stage_anchors():
    """Stock-only single runs of the three anchor decks; print Z."""
    for name in ("four-radial", "crossing", "lone-radial"):
        d = ROOT / f"anchor-{name}-x1"
        text = run_once(d, anchor_deck(name), ezoff=False)
        z = parse_z(text)
        err = [l for l in text.splitlines() if "ERROR" in l.upper()]
        print(f"{name:12s} Z = {z}  errors={err[:2]}", flush=True)


def stage_ladders():
    res = load_results()
    for name in ("lone-radial", "four-radial", "crossing"):
        for m in (1, 2, 4, 8):
            cid = f"anchor-{name}-x{m}"
            rec = capture(
                res, cid, anchor_deck(name, m), kind="anchor", note=f"ladder x{m}"
            )
            print(
                f"{cid:24s} Zs={rec['Z_stock']} Ze={rec['Z_ezoff']} "
                f"dZ={rec['spread_dZ']}",
                flush=True,
            )


def ne_matrix():
    jobs = []
    for kind, depths in (
        ("bhd10", (0.02, 0.05, 0.10, 0.15)),
        ("bhd1", (0.02, 0.05, 0.10, 0.15)),
        ("bvd1", (0.05, 0.10, 0.15)),
    ):
        for d in depths:
            jobs.append((kind, d, "A", 7))
    for soil, freq in (("B", 7), ("C", 7), ("A", 21)):
        for kind in ("bhd10", "bhd1"):
            for d in (0.05, 0.15):
                jobs.append((kind, d, soil, freq))
    return jobs


def stage_ne(ne_after_xq: bool):
    res = load_results()
    for kind, d, soil, freq in ne_matrix():
        cid = f"ne-{kind}-d{d:g}-{soil}-{freq}MHz"
        rec = capture(res, cid, ne_deck(kind, d, soil, freq, ne_after_xq), kind="ne")
        print(
            f"{cid:28s} Zs={rec['Z_stock']} dZ={rec['spread_dZ']} "
            f"blocks={rec['ne_blocks']} pts={rec['ne_points']} "
            f"neSpread={rec['spread_ne_maxrel']} "
            f"err={rec['stock_errors'][:1]}",
            flush=True,
        )


def stage_control(ne_after_xq: bool):
    res = load_results()
    extra = "GW 2,21,125.,0.,-0.05,135.,0.,-0.05,.001\n"
    deck = ne_deck("bhd10", 0.05, "A", 7, ne_after_xq, extra_geo=extra)
    rec = capture(
        res,
        "control-bhd10-pair-130m",
        deck,
        kind="control",
        note="positive control: parasitic twin at x=130 m",
    )
    print(
        f"control  Zs={rec['Z_stock']} Ze={rec['Z_ezoff']} "
        f"dZ={rec['spread_dZ']} neSpread={rec['spread_ne_maxrel']} "
        f"identical={rec['identical_output']}",
        flush=True,
    )


if __name__ == "__main__":
    stage = sys.argv[1] if len(sys.argv) > 1 else "anchors"
    after_xq = "--ne-after-xq" in sys.argv
    if stage == "anchors":
        stage_anchors()
    elif stage == "ladders":
        stage_ladders()
    elif stage == "ne":
        stage_ne(after_xq)
    elif stage == "control":
        stage_control(after_xq)
    else:
        raise SystemExit(f"unknown stage {stage}")

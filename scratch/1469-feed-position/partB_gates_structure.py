"""AK#1469 part B gates G1, G3, G4 and G6: import structure, the NEC-2 export
and NEC-5 deck round trips, and FeedPlacement advisories. Reads the structure
captures, and re-imports every deck from the tree PYTHONPATH puts first (the
part-B branch). Nothing is solved.

    PYTHONPATH=<branch>/src python partB_gates_structure.py <catalog dir> <portal dir> <baseline.jsonl> <after.jsonl>

A deck's attachments are compared as physical points: each port of the source
import is placed on its piece at its position, and the same is done for the
deck re-imported from the NEC-2 export and from the NEC-5 deck text. Names may
be renumbered on the way, so points are matched per kind (feed, load, tl, nt).
"""

import json
import math
import os
import re
import shutil
import sys
import tempfile
import warnings
from collections import Counter

TOL_M = 1e-6


def _load(path):
    with open(path, encoding="utf-8") as fh:
        return {(r["set"], r["deck"]): r for r in map(json.loads, fh)}


def _points(deck):
    """(kind, point) for each positioned or middle port of an imported deck,
    plus the vertex-port count."""
    tups = deck.wire_tuples()
    by_name = {t[4]: t for t in tups if len(t) > 4 and t[4]}
    pts, vertex = [], 0
    for name, port in deck.network().ports.items():
        kind = re.sub(r"\d+[ab]?$", "", name)
        if type(port).__name__ != "PortOnWire":
            vertex += 1
            continue
        piece = by_name.get(getattr(port, "wire", None) or name)
        if piece is None:
            pts.append((kind, None))
            continue
        at = getattr(port, "at", None)
        at = 0.5 if at is None else at
        p1, p2 = piece[0], piece[1]
        pts.append((kind, tuple(a + (b - a) * at for a, b in zip(p1, p2, strict=True))))
    return sorted(pts, key=lambda kp: (kp[0], kp[1] or ())), vertex


def _same_points(a, b):
    if len(a) != len(b):
        return False
    for (ka, pa), (kb, pb) in zip(a, b, strict=True):
        if ka != kb or pa is None or pb is None:
            return False
        if max(abs(x - y) for x, y in zip(pa, pb, strict=True)) > TOL_M:
            return False
    return True


def _match_points(a, b):
    """Order-free match within TOL_M, per kind."""
    if len(a) != len(b):
        return False
    left = list(b)
    for ka, pa in a:
        for i, (kb, pb) in enumerate(left):
            if (
                ka == kb
                and pa is not None
                and pb is not None
                and max(abs(x - y) for x, y in zip(pa, pb, strict=True)) <= TOL_M
            ):
                del left[i]
                break
        else:
            return False
    return True


def _at_on_grid(deck):
    """Every positioned port's `at` is (k - 1/2)/n or k/n on its piece."""
    tups = deck.wire_tuples()
    n_of = {t[4]: t[2] for t in tups if len(t) > 4 and t[4]}
    bad = []
    for name, port in deck.network().ports.items():
        at = getattr(port, "at", None)
        if at is None:
            continue
        n = n_of[getattr(port, "wire", None) or name]
        x = at * n
        if not (
            math.isclose(x, round(x), abs_tol=1e-9)
            or math.isclose(x - 0.5, round(x - 0.5), abs_tol=1e-9)
        ):
            bad.append((name, at, n))
    return bad


def _named_one_seg(row):
    return sum(1 for n, name in row.get("tuples", []) if n == 1 and name)


def _advisories(eng):
    return [
        a
        for a in (getattr(eng, "advisories", None) or [])
        if a.get("category") == "FeedPlacement"
    ]


def main(argv):
    warnings.filterwarnings("ignore")
    catalog, portal, base_path, after_path = argv
    from antennaknobs.engines.nec5 import NEC5Engine
    from antennaknobs.file_designs import builder_from_file
    from antennaknobs.nec_import import parse_nec

    try:
        from antennaknobs.engines.pynec import PyNECEngine
    except ImportError:
        PyNECEngine = None

    base, after = _load(base_path), _load(after_path)
    assert set(base) == set(after), "the two captures cover different decks"
    tally = Counter()
    lists = {
        k: []
        for k in (
            "import_changed",
            "segs_changed",
            "at_off_grid",
            "one_seg_named_after",
            "nec2_rt_miss",
            "nec5_rt_miss",
            "nec2_counts_changed",
            "nec2_lane_err_changed",
            "nec5_lane_err_changed",
            "adv_pynec",
            "adv_nec5",
            "vertex_dropped",
        )
    }
    for key in sorted(base):
        b, a = base[key], after[key]
        label, name = key
        tally[label] += 1
        if ("import" in b) != ("import" in a) or b.get("import") != a.get("import"):
            lists["import_changed"].append((name, b.get("import"), a.get("import")))
        if "import" in a or "import" in b:
            continue
        if sum(n for n, _ in b["tuples"]) != sum(n for n, _ in a["tuples"]):
            lists["segs_changed"].append(name)
        if _named_one_seg(a):
            lists["one_seg_named_after"].append(
                (name, _named_one_seg(b), _named_one_seg(a))
            )
        vb = sum(1 for p in b["ports"].values() if p[0] == "PortAtVertex")
        va = sum(1 for p in a["ports"].values() if p[0] == "PortAtVertex")
        if va != vb:
            lists["vertex_dropped"].append((name, vb, va))
        for lane in ("nec2", "nec5"):
            eb, ea = str(b.get(lane, "")), str(a.get(lane, ""))
            if eb.startswith("ERR") or ea.startswith("ERR"):
                if eb != ea:
                    lists[f"{lane}_lane_err_changed"].append((name, eb[:120], ea[:120]))

        path = os.path.join(catalog if label == "catalog-nec5" else portal, name)
        text = open(path, encoding="utf-8", errors="replace").read()
        src = parse_nec(text, name=name, network=True)
        off = _at_on_grid(src)
        if off:
            lists["at_off_grid"].append((name, off[:3]))
        src_pts, _ = _points(src)
        for lane in ("nec2", "nec5"):
            out = a.get(lane)
            if not isinstance(out, str) or out.startswith("ERR"):
                continue
            try:
                back = parse_nec(out, name=f"rt.{lane}.nec", network=True)
                back_pts, _ = _points(back)
                ok = _match_points(src_pts, back_pts)
            except Exception as exc:  # noqa: BLE001 — a failed re-import is a miss
                ok, back = False, None
                back_pts = f"ERR {type(exc).__name__}: {exc}"[:120]
            if not ok:
                lists[f"{lane}_rt_miss"].append((name, str(back_pts)[:160]))
            elif lane == "nec2" and back is not None:
                src_n = sorted(w.n_seg for w in src.wires)
                back_n = sorted(w.n_seg for w in back.wires)
                if src_n != back_n:
                    lists["nec2_counts_changed"].append(name)

        tmp = tempfile.mkdtemp()
        try:
            nec = os.path.join(tmp, os.path.splitext(name)[0] + ".nec")
            shutil.copyfile(path, nec)
            bld = builder_from_file(nec)
            bld = bld() if isinstance(bld, type) else bld
            ground = getattr(bld, "file_ground", None)
            try:
                eng = NEC5Engine(bld, ground=ground, require_exe=False)
                eng.deck([bld.freq])
                if _advisories(eng):
                    lists["adv_nec5"].append((name, _advisories(eng)[0]["text"][:160]))
            except Exception:  # noqa: BLE001 — the lane-error list counts refusals
                pass
            if PyNECEngine is not None:
                try:
                    eng = PyNECEngine(bld, ground=ground)
                    if _advisories(eng):
                        lists["adv_pynec"].append(
                            (name, _advisories(eng)[0]["text"][:160])
                        )
                except Exception:  # noqa: BLE001 — the PyNEC capture counts refusals
                    pass
        except Exception:  # noqa: BLE001 — a census records what it cannot build
            pass
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    print(dict(tally))
    for k, v in lists.items():
        print(f"{k}: {len(v)}")
        for item in v[:12]:
            print("   ", item)

    # G6: AC6LA's deck as he wrote it.
    dan = "SY len=.4836\nGW 1 20 0 -len/2 0 0 len/2 0 .0001\nEX 0 1 10 0 1 0\nFR 0 1 0 0 310\nEN\n"
    deck = parse_nec(dan, name="dan2.nec", network=True)
    port = deck.network().ports["feed"]
    tmp = tempfile.mkdtemp()
    try:
        p = os.path.join(tmp, "dan2.nec")
        open(p, "w").write(dan)
        bld = builder_from_file(p)
        bld = bld() if isinstance(bld, type) else bld
        n5 = NEC5Engine(bld, ground=None, require_exe=False)
        text5 = n5.deck([bld.freq])
        gw = [ln for ln in text5.splitlines() if ln.startswith("GW")]
        ex = [ln for ln in text5.splitlines() if ln.startswith("EX")]
        py = PyNECEngine(bld, ground=None) if PyNECEngine else None
        print(
            "G6 dan2.nec: tuples",
            [(t[2], t[4] if len(t) > 4 else None) for t in deck.wire_tuples()],
            "at",
            port.at,
            "| PyNEC counts",
            py and [t[2] for t in py.tups],
            "adv",
            py and _advisories(py),
            "| NEC-5",
            gw,
            ex,
            "adv",
            _advisories(n5),
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main(sys.argv[1:])

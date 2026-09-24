"""AK#1714 census: a SimNEC circuit's dcl constants as knobs, over SimNEC's
own shipped examples.

For every unique ``.ssn`` under the corpus root (default
``~/.SimNEC/5/3/Examples``, deduplicated by content hash) whose NETWORK
script has a ``NEC2`` block, load the file design through the production
seam (``file_designs.builder_from_file``), build it at its defaults, and
print one row: whether it imports and builds, how many knobs it publishes,
and why when it does not. For a design with knobs, check:

  1. DEFAULT IDENTITY. The design at its default knob values builds wires
     and network equal to the file imported with knobs OFF
     (``file_designs._ssn_circuit(text, name)``, no overrides) -- ``==`` on
     the wire tuples and the ``Network``, and ``repr`` equality on the wires
     too (``==`` would let ``-0.0`` pass for ``0.0``). The deck is read back
     from an INSTANCE, which goes through the ``dcl_overrides`` re-parse, and
     the script counts that the override path actually ran.
  2. MOVE == HAND EDIT. Each knob moved by +5 % (or to 0.5 from a zero
     default) either is refused with a ``ValueError`` naming the knob, or
     builds wires and network equal to the same file with that one ``dcl``
     value edited in the text and imported with knobs OFF -- never the knob
     path itself -- and different from the defaults.

A mismatch in either is a FAILURE: the script prints each one and exits 1.
Files with no NEC2 block (SimNEC-scripted antennas, RUSE blocks) are counted
by the refusal they get, which is the pre-AK#1714 behaviour.

    PYTHONPATH=src prlimit --as=$((8*1024**3)) \\
        .venv/bin/python scripts/census_dcl_knobs_1714.py [corpus_root]
"""

from __future__ import annotations

import hashlib
import re
import sys
import time
from collections import Counter
from pathlib import Path

from antennaknobs import file_designs
from antennaknobs.file_designs import builder_from_file
from antennaknobs.simnec_import import _NEC2_LINE


def has_nec2_block(text: str) -> bool:
    return any(_NEC2_LINE.match(line.strip()) for line in text.splitlines())


def edit_dcl(text: str, spelling: str, new: str) -> str | None:
    """``text`` with the one uncommented ``dcl spelling = ...;`` (or
    ``$spelling = ...;``) set to ``new``, or None when that assignment is not
    found exactly once."""
    head = (
        r"\$" + re.escape(spelling[1:])
        if spelling.startswith("$")
        else (r"\bdcl\s+" + re.escape(spelling))
    )
    pat = re.compile(rf"({head}\s*=\s*)([^;\n]+?)(\s*;)")
    hits = []
    for m in pat.finditer(text):
        line_start = text.rfind("\n", 0, m.start()) + 1
        if "//" not in text[line_start : m.start()]:
            hits.append(m)
    if len(hits) != 1:
        return None
    m = hits[0]
    return text[: m.start(2)] + new + text[m.end(2) :]


def moved_value(sym) -> float | int:
    d = sym.default
    if sym.integer:
        return d + 1
    return d * 1.05 if d else 0.5


def frozen(cls, b, text: str, name: str):
    """Wires and network of ``text`` imported with knobs OFF."""
    circuit = file_designs._ssn_circuit(text, name)
    wires = cls.auto_mesh(b, list(circuit.deck.wire_tuples(specs=True)))
    return wires, circuit.network()


def main(root: Path) -> int:
    counts: Counter = Counter()
    failures: list[str] = []
    rows: list[tuple[str, str, str, str]] = []
    seen: set[str] = set()
    t0 = time.time()
    for path in sorted(root.rglob("*.ssn")):
        raw = path.read_bytes()
        h = hashlib.sha256(raw).hexdigest()
        if h in seen:
            continue
        seen.add(h)
        counts["unique"] += 1
        text = path.read_text(encoding="utf-8", errors="replace")
        rel = str(path.relative_to(root))
        if not has_nec2_block(text):
            counts["no_nec2_block"] += 1
            continue
        counts["nec2_block"] += 1
        try:
            cls = builder_from_file(str(path))
        except (ValueError, SystemExit) as e:
            rows.append((rel, "n", "-", f"import refused: {e}"))
            continue
        try:
            b = cls()
            wires = b.build_wires()
            net = b.build_network()
            inst_deck = b.file_deck_parsed
        except ValueError as e:
            knobs = cls.file_sy_knobs
            n = str(len(knobs.symbols)) if knobs else "0"
            rows.append((rel, "n", n, f"imports, does not build: {e}"))
            continue
        counts["builds"] += 1
        knobs = cls.file_sy_knobs
        notes = (cls.default_params.get("ui_params") or {}).get("notes") or ""
        if "not offered as knobs" in notes:
            failures.append(f"{rel}: knobs dropped (defaults do not reproduce)")
        if knobs is None:
            counts["frozen"] += 1
            rows.append((rel, "y", "0", "no dcl constant in the cards"))
            continue
        counts["with_knobs"] += 1
        counts["knobs"] += len(knobs.symbols)
        rows.append((rel, "y", str(len(knobs.symbols)), ""))
        ref_w, ref_n = frozen(cls, b, text, path.name)
        if wires != ref_w or repr(wires) != repr(ref_w):
            failures.append(f"{rel}: default wires differ from the knobs-off import")
        if net != ref_n:
            failures.append(f"{rel}: default network differs from the knobs-off import")
        if knobs._parse.cache_info().misses < 1 or inst_deck is cls.file_deck_parsed:
            failures.append(f"{rel}: the override path did not run")
        else:
            counts["override_path_ran"] += 1
        for sym in knobs.symbols:
            v = moved_value(sym)
            mb = cls(dict(cls.default_params, **{sym.param: v}))
            try:
                mw, mn = mb.build_wires(), mb.build_network()
            except ValueError as e:
                if sym.param not in str(e):
                    failures.append(f"{rel}: {sym.param} refusal does not name it: {e}")
                counts["move_refused"] += 1
                continue
            counts["move_accepted"] += 1
            if (mw, mn) == (wires, net):
                failures.append(f"{rel}: moving {sym.param} changed nothing")
            literal = str(int(v)) if sym.integer else repr(float(v))
            edited = edit_dcl(text, sym.spelling, literal)
            if edited is None:
                counts["move_uneditable"] += 1
                continue
            hw, hn = frozen(cls, b, edited, path.name)
            if hw != mw or repr(hw) != repr(mw) or hn != mn:
                failures.append(f"{rel}: {sym.param} = {v!r} differs from hand edit")
            else:
                counts["move_matches_hand_edit"] += 1
    counts["seconds"] = round(time.time() - t0)
    print("| file | imports | knobs | reason |")
    print("|---|---|---|---|")
    for rel, ok, n, why in rows:
        print(f"| {rel} | {ok} | {n} | {why[:160]} |")
    print()
    for k in (
        "unique",
        "no_nec2_block",
        "nec2_block",
        "builds",
        "frozen",
        "with_knobs",
        "knobs",
        "override_path_ran",
        "move_accepted",
        "move_refused",
        "move_matches_hand_edit",
        "move_uneditable",
        "seconds",
    ):
        print(f"{k:>24}: {counts[k]}")
    for f in failures:
        print("FAIL", f)
    print(f"{len(failures)} failures")
    return 1 if failures else 0


if __name__ == "__main__":
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "~/.SimNEC/5/3/Examples")
    sys.exit(main(root.expanduser()))

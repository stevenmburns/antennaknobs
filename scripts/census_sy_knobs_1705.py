"""AK#1705 census: SY knobs over the nec-wild corpus.

For every unique ``.nec`` deck under the corpus root (default
``~/antennas/nec-wild``, deduplicated by content hash) that imports today
(``parse_nec(text, network=True)``), build the file design through the
production seam (``file_designs.builder_from_file``) and check:

  1. DEFAULT IDENTITY. The design at its default knob values builds wires,
     network and deck equal to today's import -- ``==`` on the wire tuples,
     the ``Network`` and the ``NecDeck``, and ``repr`` equality on the wires
     too (``==`` would let ``-0.0`` pass for ``0.0``). For a deck with knobs
     the deck is read back from an INSTANCE, which goes through the
     ``sy_overrides`` re-parse, and the script counts that the override path
     actually ran (the knobs' parse cache saw a miss) rather than trusting it.
  2. MOVE == HAND EDIT. Each knob moved by +5 % (or to 0.5 from a zero
     default) either is refused with a ``ValueError`` naming the knob, or
     builds wires and network equal to importing a copy of the deck with that
     one SY value edited in the text. Knobs whose SY assignment the simple
     text editor below cannot locate uniquely are counted, not checked.

A mismatch in either is a FAILURE: the script prints each one and exits 1.

    PYTHONPATH=src prlimit --as=$((8*1024**3)) \\
        .venv/bin/python scripts/census_sy_knobs_1705.py [corpus_root]
"""

from __future__ import annotations

import hashlib
import re
import sys
import time
from collections import Counter
from pathlib import Path

from antennaknobs.file_designs import builder_from_file
from antennaknobs.nec_import import parse_nec


def edit_sy(text: str, spelling: str, new: str) -> str | None:
    """``text`` with the SY assignment of ``spelling`` set to ``new``, or None
    when that assignment is not found exactly once."""
    pat = re.compile(
        r"(?im)^(\s*SY\b[^'\n]*?(?<![\w.])"
        + re.escape(spelling)
        + r"\s*=\s*)([^,'\n]+?)(\s*(?:,|'|$))"
    )
    hits = list(pat.finditer(text))
    if len(hits) != 1:
        return None
    m = hits[0]
    return text[: m.start(2)] + new + text[m.end(2) :]


def moved_value(sym) -> float | int:
    d = sym.default
    if sym.integer:
        return d + 1
    return d * 1.05 if d else 0.5


def edited_literal(sym, v) -> str:
    if sym.integer:
        return str(int(v))
    if sym.unit_factor is not None:
        # The deck's own shape: the number times its unit symbol.
        unit = re.search(r"([A-Za-z_]\w*)\s*$", sym.expr).group(1)
        return f"{float(v)!r}*{unit}"
    return repr(float(v))


def main(root: Path) -> int:
    counts: Counter = Counter()
    failures: list[str] = []
    inert: list[str] = []
    seen: set[str] = set()
    t0 = time.time()
    paths = sorted(p for p in root.rglob("*") if p.suffix.lower() == ".nec")
    for path in paths:
        raw = path.read_bytes()
        h = hashlib.sha256(raw).hexdigest()
        if h in seen:
            continue
        seen.add(h)
        counts["unique"] += 1
        text = path.read_text(encoding="utf-8", errors="replace")
        try:
            plain = parse_nec(text, name=path.name, network=True)
            plain_wires = plain.wire_tuples(specs=True)
            plain_net = plain.network()
        except Exception:  # noqa: BLE001 — census: a deck refused today is out of scope
            counts["refused_today"] += 1
            continue
        counts["imports"] += 1
        has_sy = bool(re.search(r"(?im)^\s*SY\b", text))
        counts["sy_bearing"] += has_sy
        rel = path.relative_to(root)
        try:
            # builder_from_file dispatches on the lower-cased suffix; `.NEC`
            # decks go through the same loader.
            cls = builder_from_file(str(path))
            b = cls()
            wires = b.build_wires()
            net = b.build_network()
            inst_deck = b.file_deck_parsed
        except Exception as e:  # noqa: BLE001 — census: every failure is recorded
            failures.append(f"{rel}: design fails to build at defaults: {e!r}")
            continue
        knobs = cls.file_sy_knobs
        notes = (cls.default_params.get("ui_params") or {}).get("notes") or ""
        if "not offered as knobs" in notes:
            counts["knobs_dropped"] += 1
            failures.append(f"{rel}: knobs dropped (defaults do not reproduce)")
        ref = cls.auto_mesh(b, list(plain_wires))
        if wires != ref or repr(wires) != repr(ref):
            failures.append(f"{rel}: default wires differ from today's import")
        if net != plain_net:
            failures.append(f"{rel}: default network differs from today's import")
        if inst_deck != plain:
            failures.append(f"{rel}: default deck differs from today's import")
        if knobs is None:
            counts["frozen"] += 1
            continue
        counts["with_knobs"] += 1
        counts["knobs"] += len(knobs.symbols)
        if knobs._parse.cache_info().misses < 1 or inst_deck is plain:
            failures.append(f"{rel}: the override path did not run")
        else:
            counts["override_path_ran"] += 1
        for sym in knobs.symbols:
            v = moved_value(sym)
            params = dict(cls.default_params)
            params[sym.param] = v
            mb = cls(params)
            try:
                mw = mb.build_wires()
                mn = mb.build_network()
            except ValueError as e:
                if sym.param not in str(e):
                    failures.append(f"{rel}: {sym.param} refusal does not name it: {e}")
                counts["move_refused"] += 1
                msg = str(e)
                reason = (
                    "topology"
                    if "topology is frozen" in msg
                    else "degenerate"
                    if "would have" in msg
                    else "parse"
                )
                counts[f"move_refused_{reason}"] += 1
                continue
            counts["move_accepted"] += 1
            if mw == wires:
                counts["move_wires_unchanged"] += 1
                if mn == net:
                    counts["move_changes_nothing"] += 1
                    inert.append(
                        f"{rel}: {sym.param} ({sym.expr}) -> {sorted(sym.reaches)}"
                    )
            edited = edit_sy(text, sym.spelling, edited_literal(sym, v))
            if edited is None:
                counts["move_uneditable"] += 1
                continue
            try:
                hand = parse_nec(edited, name=path.name, network=True)
                hw = cls.auto_mesh(b, list(hand.wire_tuples(specs=True)))
                hn = hand.network()
            except ValueError as e:
                failures.append(f"{rel}: {sym.param}: hand-edited deck fails: {e}")
                continue
            if hw != mw or hn != mn:
                failures.append(f"{rel}: {sym.param} = {v!r} differs from hand edit")
            else:
                counts["move_matches_hand_edit"] += 1
    counts["seconds"] = round(time.time() - t0)
    for k in (
        "unique",
        "imports",
        "refused_today",
        "sy_bearing",
        "frozen",
        "with_knobs",
        "knobs",
        "override_path_ran",
        "knobs_dropped",
        "move_accepted",
        "move_refused",
        "move_matches_hand_edit",
        "move_uneditable",
        "move_refused_topology",
        "move_refused_degenerate",
        "move_refused_parse",
        "move_wires_unchanged",
        "move_changes_nothing",
        "seconds",
    ):
        print(f"{k:>26}: {counts[k]}")
    for line in inert:
        print("NO CHANGE", line)
    for f in failures:
        print("FAIL", f)
    print(f"{len(failures)} failures")
    return 1 if failures else 0


if __name__ == "__main__":
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "~/antennas/nec-wild")
    sys.exit(main(root.expanduser()))

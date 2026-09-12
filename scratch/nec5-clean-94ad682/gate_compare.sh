#!/usr/bin/env bash
# Every comparison the unit-2 gate is made of, in one place, so the report's
# numbers and the commands that produced them cannot drift apart.
#
# Run AFTER run_unit2.sh and run_rest.sh. Nothing here times anything, so it is
# safe to run with other work on the box.
set -u
T="$HOME/nec5-timing"
AK="$HOME/stevenmburns/antennaknobs"
PY="$AK/.venv/bin/python"
R="$(cd "$(dirname "$0")" && pwd)"
OUT="$T/gate-94ad682"
mkdir -p "$OUT"

hdr() { printf '\n\n========== %s ==========\n\n' "$1"; }

hdr "1. impedance rows, byte-identical vs d8e2147 (the solve is untouched)"
for nt in 1 4; do
  echo "--- t$nt"
  "$PY" "$R/compare_impedance.py" "$T/unit2-runs/d8e2147-t$nt" "$T/unit2-runs/94ad682-t$nt"
done

hdr "2. impedance rows, 94ad682 t1 vs t4 (thread invariance)"
"$PY" "$R/compare_impedance.py" "$T/unit2-runs/94ad682-t1" "$T/unit2-runs/94ad682-t4"

hdr "3. RP / NE / NH tables vs d8e2147, the room's rule at 1e-9"
for nt in 1 4; do
  echo "--- t$nt"
  "$PY" "$R/compare_tables.py" "$T/unit2-runs/d8e2147-t$nt" "$T/unit2-runs/94ad682-t$nt"
done

hdr "4. RP / NE / NH tables, 94ad682 t1 vs t4"
"$PY" "$R/compare_tables.py" "$T/unit2-runs/94ad682-t1" "$T/unit2-runs/94ad682-t4"

hdr "5. the same two gates against x13 (fan_dipole is expected to move: unit 1's"
echo "   Sommerfeld flag effect, which d8e2147 already shows against x13)"
"$PY" "$R/compare_tables.py" "$T/unit2-runs/x13-t4" "$T/unit2-runs/94ad682-t4"
echo "--- and d8e2147 against x13, for the same decks, so the comparison is like-for-like"
"$PY" "$R/compare_tables.py" "$T/unit2-runs/x13-t4" "$T/unit2-runs/d8e2147-t4"

hdr "6. corpus impedance movers: 94ad682 vs x13 and vs d8e2147, at 1e-9"
for base in x13 d8e2147; do
  echo "--- vs $base"
  "$PY" "$AK/scripts/nec5_corpus/nec5_corpus.py" compare \
    "$T/check-$base-t4.jsonl" "$T/check-94ad682-t4.jsonl" --ignore-env --tol 1e-9 2>&1 | tail -6
done
echo "--- 94ad682 t1 vs t4 (a thread-count move in the SOLVE would be a regression)"
"$PY" "$AK/scripts/nec5_corpus/nec5_corpus.py" compare \
  "$T/check-94ad682-t1.jsonl" "$T/check-94ad682-t4.jsonl" --ignore-env --tol 1e-9 2>&1 | tail -6

hdr "7. the 22-deck unit-1 regression set: printouts vs d8e2147 and vs x13"
for base in d8e2147 x13; do
  echo "--- vs $base (impedance)"; "$PY" "$R/compare_impedance.py" "$T/unit1-regression/$base" "$T/unit1-regression/94ad682" | tail -4
  echo "--- vs $base (field tables)"; "$PY" "$R/compare_tables.py" "$T/unit1-regression/$base" "$T/unit1-regression/94ad682" | tail -4
done

echo
echo "GATECOMPAREDONE"

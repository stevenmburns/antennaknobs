#!/usr/bin/env bash
# Everything after the headline set, in sequence, one process at a time.
# Waits for run_unit2.sh to finish first so no two timed runs ever overlap.
set -u
T="$HOME/nec5-timing"
R="$(cd "$(dirname "$0")" && pwd)"
PY="$HOME/stevenmburns/antennaknobs/.venv/bin/python"
AK="$HOME/stevenmburns/antennaknobs"

until grep -q UNIT2DONE "$T/unit2-run.log" 2>/dev/null; do sleep 30; done
echo "=== headline set done, $(date +%T) ==="

echo "=== corpus check, 94ad682, t4 ($(date +%T)) ==="
OMP_NUM_THREADS=4 OPENBLAS_NUM_THREADS=4 PYTHONUTF8=1 \
  "$PY" "$AK/scripts/nec5_corpus/nec5_corpus.py" check \
    --exe "$T/nec5cl-94ad682" --src "$T/nec5" --timeout 300 \
    --report "$T/check-94ad682-t4.jsonl" 2>&1 | tail -4

echo "=== corpus check, 94ad682, t1 ($(date +%T)) ==="
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 PYTHONUTF8=1 \
  "$PY" "$AK/scripts/nec5_corpus/nec5_corpus.py" check \
    --exe "$T/nec5cl-94ad682" --src "$T/nec5" --timeout 300 --jobs 4 \
    --report "$T/check-94ad682-t1.jsonl" 2>&1 | tail -4

echo "=== the 38 slow decks, t1 and t4 ($(date +%T)) ==="
bash "$R/run_slow38.sh" 2>&1 | tail -6

echo "=== the 22-deck unit-1 regression ($(date +%T)) ==="
bash "$R/run_unit1_regression.sh" 2>&1 | tail -5

echo "RESTDONE $(date +%T)"

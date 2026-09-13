#!/usr/bin/env bash
# Two corpus passes for the THREADING map, both with jobs x threads == the CPU
# count, so `timing_valid` is true on each and the ratio between them means what
# its axis label says.
#
# WHY NOT REUSE THE EXISTING REPORTS. check-94ad682-t1 was 4 jobs x 1 thread (4
# of 8 CPUs busy) and check-94ad682-t4 was 4 jobs x 4 threads (16 threads on 8
# CPUs, and the tool flags it `timing_valid: false`). Dividing the first by the
# second would charge four-thread running for oversubscription it did not ask
# for and understate the very thing the map is about.
#
#   t1: 8 jobs x 1 thread  = 8   valid
#   t4: 2 jobs x 4 threads = 8   valid
#
# Both saturate the 8 logical CPUs, so this is a THROUGHPUT-mode ratio: what four
# threads buy a deck when the box is full either way. The authoritative per-deck
# ratios are still the serialised sets (`unit2-timing.tsv`, `slow38-timing.tsv`),
# one process at a time, and the write-up quotes those as the headline.
set -u
T="$HOME/nec5-timing"
AK="$HOME/stevenmburns/antennaknobs"
PY="$AK/.venv/bin/python"

echo "=== t1: 8 jobs x 1 thread ($(date +%T)) ==="
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONUTF8=1 \
  "$PY" "$AK/scripts/nec5_corpus/nec5_corpus.py" check \
    --exe "$T/nec5cl-94ad682" --src "$T/nec5" --timeout 300 --jobs 8 \
    --report "$T/check-94ad682-map-t1.jsonl" 2>&1 | tail -3

echo "=== t4: 2 jobs x 4 threads ($(date +%T)) ==="
OMP_NUM_THREADS=4 OPENBLAS_NUM_THREADS=4 MKL_NUM_THREADS=4 PYTHONUTF8=1 \
  "$PY" "$AK/scripts/nec5_corpus/nec5_corpus.py" check \
    --exe "$T/nec5cl-94ad682" --src "$T/nec5" --timeout 300 --jobs 2 \
    --report "$T/check-94ad682-map-t4.jsonl" 2>&1 | tail -3

echo "MAPPASSESDONE $(date +%T)"

# --- appended: the two BASELINE passes, re-run in the same session ------------
# Maps 1 and 2 first used the x13 and d8e2147 corpus reports from 2026-09-10.
# They are not comparable across days on this box: `2ELK9AY` reads 0.178 s in the
# d8e2147 report but 0.2655 s serialised TODAY, and a serialised 7-rep probe has
# 94ad682 and d8e2147 IDENTICAL on it (0.2651 vs 0.2655, and 0.992-1.006 on four
# decks). So the corpus-wide "94ad682 is 5 % slower than d8e2147" was cross-day
# drift in the box, not the build -- the memory rule here is ratios and repeated
# reps, never absolute seconds across sessions. Both baselines are re-run in the
# same session as the 94ad682 pass, at the same 4 jobs x 1 thread.

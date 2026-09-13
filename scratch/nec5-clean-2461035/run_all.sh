#!/usr/bin/env bash
# Every run the 2461035 gate needs, in sequence, one process at a time.
#
# Four corpus passes rather than two, because a wall-time COMPARISON is only
# valid between passes taken the same way AND in the same session:
#
#   4 jobs x 1 thread   statuses at one thread, and the baseline-matched maps
#                       (vs x13 / vs d8e2147). 94ad682 is re-run here too: its
#                       11:08 pass and the 16:2x baselines are hours apart, and
#                       this box drifts -- d8e2147 read 852 s on 09-10 and 1135 s
#                       today for the same pass.
#   2 jobs x 4 threads  statuses at four threads, and the t4 side of the
#                       threading map. jobs x threads == 8, so timing_valid.
#   8 jobs x 1 thread   the t1 side of the threading map, also saturating the
#                       box, so the ratio is throughput-mode t1 vs t4.
set -u
T="$HOME/nec5-timing"; AK="$HOME/stevenmburns/antennaknobs"; PY="$AK/.venv/bin/python"
R="$(cd "$(dirname "$0")" && pwd)"

echo "=== headline set, 2461035, t1 and t4 ($(date +%T)) ==="
OUT="$T/unit2-runs"
for nt in 1 4; do
  d="$OUT/2461035-t$nt"; rm -rf "$d"; mkdir -p "$d"
  for deck in "$T"/decks-unit2/*.nec; do
    b=$(basename "$deck" .nec); work=$(mktemp -d); cp "$deck" "$work/model.nec"
    n=$(awk '$1=="GW"{s+=$3} END{print s+0}' "$deck")
    t0=$(date +%s.%N)
    ( cd "$work" && export OMP_NUM_THREADS=$nt OPENBLAS_NUM_THREADS=$nt MKL_NUM_THREADS=$nt; \
      printf 'model.nec\nmodel.out\n\n' | "$T/nec5cl-2461035" >/dev/null 2>&1 )
    t1=$(date +%s.%N)
    cp "$work/model.out" "$d/$b.out" 2>/dev/null
    rt=$(grep -m1 "RUN TIME" "$d/$b.out" 2>/dev/null | awk '{print $NF}')
    z=$(grep -A4 "ANTENNA INPUT PARAMETERS" "$d/$b.out" 2>/dev/null | tail -1 | awk '{print $8"\t"$9}')
    printf "2461035\t%s\t%s\t%s\t%.2f\t%s\t%s\n" "$nt" "$b" "$n" \
      "$(echo "$t1 - $t0" | bc)" "${rt:-NA}" "${z:-NA	NA}" >> "$OUT/timing.tsv"
    rm -rf "$work"
  done
  echo "  done t$nt"
done

corpus () {  # <exe-tag> <jobs> <omp> <report-suffix>
  echo "=== corpus: $1, $2 jobs x $3 thread(s) ($(date +%T)) ==="
  OMP_NUM_THREADS=$3 OPENBLAS_NUM_THREADS=$3 MKL_NUM_THREADS=$3 PYTHONUTF8=1 \
    "$PY" "$AK/scripts/nec5_corpus/nec5_corpus.py" check \
      --exe "$T/nec5cl-$1" --src "$T/nec5" --timeout 300 --jobs "$2" \
      --report "$T/check-$1-$4.jsonl" 2>&1 | tail -3
}
corpus 2461035 4 1 j4t1
corpus 2461035 2 4 j2t4
corpus 2461035 8 1 j8t1
corpus 94ad682 4 1 j4t1

echo "ALLDONE $(date +%T)"

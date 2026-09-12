#!/usr/bin/env bash
# The unit-2 headline rows: every deck in decks-unit2 x {x13, d8e2147, 94ad682}
# x {1 thread, 4 threads}, one process at a time, run_set.sh's stdin protocol
# (the binaries read the deck NAME on stdin, never argv).
#
# Printouts are KEPT, one directory per (build, threads), because the gate is a
# table comparison and not just a wall clock: the impedance rows are compared
# byte-for-byte against d8e2147, and the RP/NE tables numerically.
set -u
T="$HOME/nec5-timing"
OUT="$T/unit2-runs"
rm -rf "$OUT"; mkdir -p "$OUT"
printf "build\tthreads\tdeck\tsegments\twall_s\tcpu_time_s\tR\tX\n" > "$OUT/timing.tsv"
for bin in nec5cl-x13 nec5cl-d8e2147 nec5cl-94ad682; do
  for nt in 1 4; do
    d="$OUT/${bin#nec5cl-}-t$nt"; mkdir -p "$d"
    for deck in "$T"/decks-unit2/*.nec; do
      b=$(basename "$deck" .nec)
      work=$(mktemp -d); cp "$deck" "$work/model.nec"
      n=$(awk '$1=="GW"{s+=$3} END{print s+0}' "$deck")
      t0=$(date +%s.%N)
      ( cd "$work" && export OMP_NUM_THREADS=$nt OPENBLAS_NUM_THREADS=$nt MKL_NUM_THREADS=$nt; \
          printf 'model.nec\nmodel.out\n\n' | "$T/$bin" >/dev/null 2>&1 )
      t1=$(date +%s.%N)
      cp "$work/model.out" "$d/$b.out" 2>/dev/null
      rt=$(grep -m1 "RUN TIME" "$d/$b.out" 2>/dev/null | awk '{print $NF}')
      z=$(grep -A4 "ANTENNA INPUT PARAMETERS" "$d/$b.out" 2>/dev/null | tail -1 | awk '{print $8"\t"$9}')
      printf "%s\t%s\t%s\t%s\t%.2f\t%s\t%s\n" "${bin#nec5cl-}" "$nt" "$b" "$n" \
        "$(echo "$t1 - $t0" | bc)" "${rt:-NA}" "${z:-NA	NA}" | tee -a "$OUT/timing.tsv"
      rm -rf "$work"
    done
  done
done
echo UNIT2DONE

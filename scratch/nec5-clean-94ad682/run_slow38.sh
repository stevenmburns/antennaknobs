#!/usr/bin/env bash
# The number this build is for: t1/t4 on the 38 large decks that d8e2147 did NOT
# speed up (AK#1433's set, < 1.7x against x13). Their t1/t4 ratio read ~1.00x
# under both earlier builds -- four threads bought them nothing -- because their
# wall is the pattern and near-field paths, which is what unit 2 rewrites.
#
# 94ad682 at both thread counts, plus d8e2147 as the standing baseline, one
# process at a time. The deck list is committed beside this script so the set
# cannot drift.
set -u
T="$HOME/nec5-timing"
LIST="$(cd "$(dirname "$0")" && pwd)/slow38-decks.txt"
OUT="$T/slow38-runs"
rm -rf "$OUT"; mkdir -p "$OUT"
printf "build\tthreads\tdeck\tsegments\twall_s\tcpu_time_s\n" > "$OUT/timing.tsv"
for bin in nec5cl-94ad682 nec5cl-d8e2147; do
  for nt in 1 4; do
    d="$OUT/${bin#nec5cl-}-t$nt"; mkdir -p "$d"
    while IFS= read -r rel; do
      [ -n "$rel" ] || continue
      deck="$T/nec5/$rel"
      b=$(echo "$rel" | tr '/' '_' | sed 's/\.nec$//')
      work=$(mktemp -d); cp "$deck" "$work/model.nec"
      n=$(awk '$1=="GW"{s+=$3} END{print s+0}' "$deck")
      t0=$(date +%s.%N)
      ( cd "$work" && export OMP_NUM_THREADS=$nt OPENBLAS_NUM_THREADS=$nt MKL_NUM_THREADS=$nt; \
          printf 'model.nec\nmodel.out\n\n' | "$T/$bin" >/dev/null 2>&1 )
      t1=$(date +%s.%N)
      cp "$work/model.out" "$d/$b.out" 2>/dev/null
      rt=$(grep -m1 "RUN TIME" "$d/$b.out" 2>/dev/null | awk '{print $NF}')
      printf "%s\t%s\t%s\t%s\t%.2f\t%s\n" "${bin#nec5cl-}" "$nt" "$rel" "$n" \
        "$(echo "$t1 - $t0" | bc)" "${rt:-NA}" >> "$OUT/timing.tsv"
      rm -rf "$work"
    done < "$LIST"
    echo "done ${bin#nec5cl-} t$nt"
  done
done
echo SLOW38DONE

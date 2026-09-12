#!/usr/bin/env bash
# perf stat on three LOW-speedup decks and one fast control of similar wall,
# at OMP=1 and OMP=4 for 63d0f93 and d8e2147. Same columns as
# perf-rows-t1-t4.csv.
#
# The binaries read the deck on STDIN, so this uses run_set.sh's protocol and
# never `perf stat <binary> <deck>` — that form runs a binary that read no deck
# and exited, which is fast, plausible and meaningless. Each row prints the
# impedance it produced so a row from a run that did not solve cannot pass as a
# fast one.
set -u
cd "$HOME/nec5-timing"
EV=cache-misses,cache-references,instructions,cycles
DECKS=(
  "g1ojs/Trapped/TRAPx2_V.nec"
  "opennec/6mYagi-Onec.nec"
  "antenna-modeling/gbhoyt.nec"
  "w8io/LP144-35-MAXFB.nec"
)
for deck in "${DECKS[@]}"; do
  for bin in nec5cl-63d0f93 nec5cl-d8e2147; do
    for nt in 1 4; do
      work=$(mktemp -d); cp "nec5/$deck" "$work/model.nec"
      echo "### $deck | $bin | OMP=$nt"
      ( cd "$work" && printf 'model.nec\nmodel.out\n\n' | \
        OMP_NUM_THREADS=$nt OPENBLAS_NUM_THREADS=$nt \
        perf stat -e "$EV" "$HOME/nec5-timing/$bin" >/dev/null ) 2>&1 \
        | grep -E "cache-misses|cache-references|instructions|cycles|seconds time elapsed|not counted"
      z=$(grep -A4 "ANTENNA INPUT PARAMETERS" "$work/model.out" 2>/dev/null | tail -1 | awk '{print $8", "$9}')
      echo "    Z = ${z:-<NO PRINTOUT — this row is void>}"
      rm -rf "$work"
    done
  done
done
echo PERFSLOWDONE

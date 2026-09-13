#!/usr/bin/env bash
# Does 94ad682 carry a fixed per-RUN cost that d8e2147 does not?
#
# The corpus-wide throughput totals say it might: over the 2,9xx decks each
# build solves, at ONE thread per worker, d8e2147 totals 852 s and 94ad682
# 1,124 s -- while on the large serialised decks the two are within 3 % at one
# thread. The corpus is dominated by decks under 50 ms, so a fixed cost per run
# would show there and nowhere else.
#
# Serialised, one process at a time, 7 reps, smallest decks first. If the delta
# is roughly CONSTANT in seconds rather than proportional, it is a fixed cost.
set -u
T="$HOME/nec5-timing"
printf "%-46s %5s %10s %10s %10s %9s\n" deck segs d8e2147 94ad682 delta_s ratio
for rel in 4nec2-models/Aperiodic/2ELK9AY.nec 4nec2-models/Aperiodic/2beverage.nec \
           nec2c/dipole.nec 4nec2-models/Aperiodic/Rhombic.nec \
           antenna-modeling/yagitools/ON6MU.nec opennec/6mYagi-Onec.nec; do
  deck="$T/nec5/$rel"; [ -f "$deck" ] || continue
  segs=$(awk '$1=="GW"{s+=$3} END{print s+0}' "$deck")
  declare -A best
  for exe in nec5cl-d8e2147 nec5cl-94ad682; do
    b=999999
    for rep in 1 2 3 4 5 6 7; do
      w=$(mktemp -d); cp "$deck" "$w/model.nec"
      t0=$(date +%s.%N)
      ( cd "$w" && export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1; \
        printf 'model.nec\nmodel.out\n\n' | timeout 300 "$T/$exe" >/dev/null 2>&1 )
      t1=$(date +%s.%N); rm -rf "$w"
      d=$(echo "$t1 - $t0" | bc)
      b=$(echo "if ($d < $b) $d else $b" | bc -l)
    done
    best[$exe]=$b
  done
  a=${best[nec5cl-d8e2147]}; c=${best[nec5cl-94ad682]}
  printf "%-46s %5s %10.4f %10.4f %10.4f %9.3f\n" "$(basename "$rel")" "$segs" "$a" "$c" \
    "$(echo "$c - $a" | bc -l)" "$(echo "$c / $a" | bc -l)"
done
echo SMALLDECKDONE

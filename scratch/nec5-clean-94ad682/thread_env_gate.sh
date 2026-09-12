#!/usr/bin/env bash
# THE GATE ON THE HARNESS ITSELF: does the thread setting reach the binary?
#
# It did not, for a while, and every t1/t4 ratio measured in between was void.
# The shape of the mistake:
#
#     VAR=v printf '...' | "$exe"        # VAR goes to PRINTF, not to $exe
#
# A variable assignment prefixes ONE command, and in a pipeline that command is
# the left-hand one. The binary on the right inherits the shell's environment
# instead, so a "1 thread" pass and a "4 thread" pass run the same
# configuration and every ratio comes out 1.00 -- which reads exactly like
# "this build does not thread".
#
# `export VAR=v; printf ... | "$exe"` is the fix, and this script is the proof:
# it prints the wall and NEC-5's own RUN TIME (CPU, summed over threads) for one
# deck at 1 and 4 threads. RUN TIME/wall near 1 means one thread actually ran;
# near 4 means four did. A harness that cannot separate those cannot measure
# scaling at all.
set -u
T="$HOME/nec5-timing"
deck="${1:-$T/decks-unit2/gbhoyt.nec}"
exe="${2:-$T/nec5cl-94ad682}"
printf "%-8s %8s %10s %8s\n" threads wall_s run_time ratio
for nt in 1 4; do
  work=$(mktemp -d); cp "$deck" "$work/model.nec"
  t0=$(date +%s.%N)
  ( cd "$work" && export OMP_NUM_THREADS=$nt OPENBLAS_NUM_THREADS=$nt MKL_NUM_THREADS=$nt; \
    printf 'model.nec\nmodel.out\n\n' | "$exe" >/dev/null 2>&1 )
  t1=$(date +%s.%N)
  w=$(echo "$t1 - $t0" | bc)
  rt=$(grep -m1 "RUN TIME" "$work/model.out" 2>/dev/null | awk '{print $NF}')
  printf "%-8s %8.2f %10s %8.2f\n" "$nt" "$w" "${rt:-NA}" "$(echo "${rt:-0} / $w" | bc -l)"
  rm -rf "$work"
done

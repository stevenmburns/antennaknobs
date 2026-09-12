#!/usr/bin/env bash
# Where does 6mYagi-Onec's time go? It is 88 segments — a trivial fill — with
# `FR 0 41` and `RP 0 361 361`, i.e. 130,321 pattern points at each of 41
# frequencies. Three variants decompose it, same build, same thread count:
#
#   as-is      41 frequencies, full pattern each
#   no-RP      41 frequencies, solve only (RP replaced by XQ so it still runs)
#   one-FR     1 frequency, full pattern
#
# If the fill were the cost, no-RP would stay slow. If the pattern is the cost,
# no-RP collapses and one-FR collapses proportionally.
set -u
cd "$HOME/nec5-timing"
src=nec5/opennec/6mYagi-Onec.nec
for bin in nec5cl-63d0f93 nec5cl-d8e2147; do
  for variant in as-is no-RP one-FR; do
    work=$(mktemp -d)
    case $variant in
      as-is)  cp "$src" "$work/model.nec" ;;
      no-RP)  sed 's/^RP .*/XQ/' "$src" > "$work/model.nec" ;;
      one-FR) sed 's/^FR 0 41 /FR 0 1 /' "$src" > "$work/model.nec" ;;
    esac
    t0=$(date +%s.%N)
    ( cd "$work" && printf 'model.nec\nmodel.out\n\n' | \
      OMP_NUM_THREADS=4 OPENBLAS_NUM_THREADS=4 "$HOME/nec5-timing/$bin" >/dev/null 2>&1 )
    t1=$(date +%s.%N)
    z=$(grep -A4 "ANTENNA INPUT PARAMETERS" "$work/model.out" 2>/dev/null | tail -1 | awk '{print $8", "$9}')
    printf "%-18s %-10s wall %7.2f s   Z = %s\n" "$bin" "$variant" \
      "$(echo "$t1 - $t0" | bc)" "${z:-<NO PRINTOUT>}"
    rm -rf "$work"
  done
done
echo PROBEDONE

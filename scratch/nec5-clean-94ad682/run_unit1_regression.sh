#!/usr/bin/env bash
# The regression check: the 22-deck unit-1 study set (study/decks) under 94ad682
# and d8e2147, one pass each at 4 threads. Unit 1's decks are XQ-only, so every
# printout should be identical -- this is the "did the pattern work break the
# solve" question, asked on the set the earlier gates used.
set -u
T="$HOME/nec5-timing"
OUT="$T/unit1-regression"
rm -rf "$OUT"; mkdir -p "$OUT"
for bin in nec5cl-94ad682 nec5cl-d8e2147 nec5cl-x13; do
  d="$OUT/${bin#nec5cl-}"; mkdir -p "$d"
  for deck in "$T"/study/decks/*.nec; do
    b=$(basename "$deck" .nec)
    work=$(mktemp -d); cp "$deck" "$work/model.nec"
    ( cd "$work" && export OMP_NUM_THREADS=4 OPENBLAS_NUM_THREADS=4 MKL_NUM_THREADS=4; \
        printf 'model.nec\nmodel.out\n\n' | "$T/$bin" >/dev/null 2>&1 )
    cp "$work/model.out" "$d/$b.out" 2>/dev/null
    rm -rf "$work"
  done
  echo "done ${bin#nec5cl-}: $(ls "$d" | wc -l) printouts"
done
echo UNIT1DONE

#!/usr/bin/env bash
# The gate's one FAILING finding: 94ad682 segfaults on two corpus decks that x13
# and d8e2147 both solve. Five reps per (build, thread count) so "crash" is a
# property of the deck and not of one run.
#
# Both decks are tiny (28 and 47 segments) and both carry NE AND NH -- the
# near-field path unit 2 rewrote. `10-30m_vert4` crashes at ONE thread too, so
# it is not purely a race.
set -u
T="$HOME/nec5-timing"
for deck in cebik-w4rnl/nec4-ex11.nec qantenna/10-30m_vert4.nec; do
  echo "=== $deck  ($(awk '$1=="GW"{s+=$3} END{print s+0}' "$T/nec5/$deck") segments; $(grep -hoE '^(NE|NH|RP)' "$T/nec5/$deck" | sort -u | tr '\n' ' '))"
  for exe in nec5cl-x13 nec5cl-d8e2147 nec5cl-94ad682; do
    for nt in 1 4; do
      out=""
      for rep in 1 2 3 4 5; do
        w=$(mktemp -d); cp "$T/nec5/$deck" "$w/model.nec"
        ( cd "$w" && export OMP_NUM_THREADS=$nt OPENBLAS_NUM_THREADS=$nt MKL_NUM_THREADS=$nt; \
          printf 'model.nec\nmodel.out\n\n' | timeout 300 "$T/$exe" >/dev/null 2>err.txt )
        rc=$?
        sig=$(grep -oE "SIGSEGV|double free|corruption|Backtrace" "$w/err.txt" 2>/dev/null | head -1)
        out="$out rc=$rc${sig:+/$sig}"
        rm -rf "$w"
      done
      printf "  %-16s t%s  %s\n" "${exe#nec5cl-}" "$nt" "$out"
    done
  done
done
echo REPRODONE

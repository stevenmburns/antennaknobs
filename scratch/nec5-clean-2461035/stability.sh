#!/usr/bin/env bash
# The blocking item from #1448: 94ad682 segfaulted on two corpus decks, one
# deterministically at ONE thread and one as a race at four. 2461035 claims both
# fixed. 20 reps per (build, thread count) on both decks -- the race showed 3 of
# 5 before, so 20 reps at four threads is what makes "0 failures" mean something.
set -u
T="$HOME/nec5-timing"
REPS=${REPS:-20}
printf "%-28s %-10s %-3s %6s %6s  %s\n" deck build thr ok segv note
for deck in qantenna/10-30m_vert4.nec cebik-w4rnl/nec4-ex11.nec; do
  for exe in nec5cl-94ad682 nec5cl-2461035; do
    for nt in 1 4; do
      ok=0; segv=0; other=""
      for rep in $(seq "$REPS"); do
        w=$(mktemp -d); cp "$T/nec5/$deck" "$w/model.nec"
        ( cd "$w" && export OMP_NUM_THREADS=$nt OPENBLAS_NUM_THREADS=$nt MKL_NUM_THREADS=$nt; \
          printf 'model.nec\nmodel.out\n\n' | timeout 300 "$T/$exe" >/dev/null 2>/dev/null )
        rc=$?
        case $rc in
          0)   ok=$((ok+1)) ;;
          139) segv=$((segv+1)) ;;
          *)   other="$other rc=$rc" ;;
        esac
        rm -rf "$w"
      done
      printf "%-28s %-10s t%-2s %6s %6s  %s\n" "$(basename "$deck")" "${exe#nec5cl-}" "$nt" \
        "$ok/$REPS" "$segv" "$other"
    done
  done
done
echo STABILITYDONE

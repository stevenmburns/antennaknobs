#!/usr/bin/env bash
# The pinned-4 map: 3b75639 against x13 over the whole corpus, in the conditions
# `scratch/nec5-clean-d8e2147/README.md` names — `--jobs 1`, OMP and OPENBLAS 4,
# one deck at a time, 300 s cap.
#
# FOUR PASSES, IN OPPOSITE ORDER: x13 -> 3b75639 -> 3b75639 -> x13.
#
# Two passes would not be enough. This box drifts between sessions -- an
# identical d8e2147 pass read 852 s on 09-10 and 1,135 s on 09-12, 33 % with no
# code involved -- and a single A-then-B pair cannot separate a build difference
# from a box that moved between them. Running the two x13 passes FIRST and LAST
# brackets the whole run: any monotone drift lands on both builds equally, and
# the bracket's own spread is a measured number rather than an assumption. If the
# two x13 passes disagree by more than 2 %, the map says so at the top instead of
# absorbing it.
set -u
T="$HOME/nec5-timing"; AK="$HOME/stevenmburns/antennaknobs"; PY="$AK/.venv/bin/python"
pass () {  # <tag> <label>
  echo "=== pass $2: $1 ($(date +%T)) ==="
  t0=$(date +%s)
  OMP_NUM_THREADS=4 OPENBLAS_NUM_THREADS=4 MKL_NUM_THREADS=4 PYTHONUTF8=1 \
    "$PY" "$AK/scripts/nec5_corpus/nec5_corpus.py" check \
      --exe "$T/nec5cl-$1" --src "$T/nec5" --timeout 300 --jobs 1 \
      --report "$T/check-$1-p$2.jsonl" 2>&1 | tail -2
  echo "    pass $2 wall $(( $(date +%s) - t0 )) s"
}
pass x13      1
pass 3b75639  2
pass 3b75639  3
pass x13      4
echo "BRACKETDONE $(date +%T)"

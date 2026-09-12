#!/usr/bin/env bash
# AK#896 census RE-RENDER on the corpus tool carrying #1416 and #1430.
#
# The published page (2026-09-11, tool 1.6) predates both fixes. This is the
# whole re-render, in order, with the two things that make it comparable to the
# published run rather than merely newer:
#
#   * the SAME NEC-5 binary. The published report's meta names
#     `nec5-src/nec5cl`, which no longer exists; `nec5cl-x13` is byte-identical
#     to it (sha256 2068ae67..., 1,265,856 bytes) and `compare` over the
#     published tree reports 0 moved / 0 impedance moved at 1e-9 on 3,076 decks.
#   * `--jobs 4` on the momwire side, which is what the published run used
#     (`_meta.environment.jobs`). The script's own default is 1, and a 1-way
#     run measured 3x the wall for 0.93x the summed per-deck time -- the same
#     answers, an incomparable wall figure.
#
# Nothing here writes into the repo; the outputs land under ~/nec5-timing/ and
# are copied in deliberately.
set -eu
cd "$(dirname "$0")/../.."          # repo root
T="$HOME/nec5-timing"
PY=.venv/bin/python

# 1. translate, twice, into two trees -- determinism is checked, not assumed.
for pass in 1430 1430b; do
  rm -rf "$T/nec5-$pass"
  PYTHONUTF8=1 $PY scripts/nec5_corpus/nec5_corpus.py translate \
    --src "$T/raw" --out "$T/nec5-$pass" \
    --report "$T/nec5-$pass/translate-report.jsonl"
done
diff -r -q --exclude=translate-report.jsonl "$T/nec5-1430" "$T/nec5-1430b"

# 2. the NEC-5 side, same exe and same environment as the published run
#    (OMP/OPENBLAS 4, PYTHONUTF8=1, timeout 300, --jobs default 4).
OMP_NUM_THREADS=4 OPENBLAS_NUM_THREADS=4 PYTHONUTF8=1 \
  $PY scripts/nec5_corpus/nec5_corpus.py check \
    --exe "$T/nec5cl-x13" --src "$T/nec5-1430" \
    --timeout 300 --report "$T/check-1430-nec5.jsonl"

# 3. the momwire side, twice, at the published dispatch width.
for pass in a b; do
  $PY scratch/896-census/census_momwire.py --jobs 4 \
    --src "$T/nec5-1430" --report "$T/census-1430-momwire-$pass.jsonl"
done

# 4. the page's generated half. `--cases 20` is not optional: the published
#    page's tail table is 20 rows, and without the flag the script prints 25
#    and the regeneration claim fails on exactly that table.
$PY scratch/896-census/census_report.py --cases 20 \
  --nec5 "$T/check-1430-nec5.jsonl" \
  --momwire "$T/census-1430-momwire-a.jsonl"

#!/usr/bin/env bash
# AK#896 census RE-RENDER on corpus tool 1.11 — the three fixes the 1.9 re-render
# found and filed, plus the one its review found:
#
#   #1442  `GN 2` passes through as `GN 2`. Under 1.9 it was rewritten to `GN 0`
#          on 1,104 of 1,105 decks, and the two engines read `GN 0` differently:
#          NEC-5 has no reflection-coefficient option so there it IS Sommerfeld,
#          while momwire's portal honours the NEC-2 meaning. ~930 comparable
#          decks were therefore momwire refl-coef against NEC-5 Sommerfeld.
#   #1435  a `collision` status. `foo.inp` and `foo.nec` used to land on the same
#          output path with the second write silently winning; the `.nec` source
#          now wins by rule and the `.inp` is reported. `written` must equal the
#          number of deck files on disk.
#   1.11   the tab-field tokenizer: a number and its unit in ONE tab field
#          (`-68 ft`, `60.7 uh`) is one value. Under 1.10 it split on the inner
#          space and every later column shifted, which put an 80 m sloper's wire
#          at z = -68 m and published it as a buried deck.
#
# Predictions for every item were registered in writing BEFORE this script ran
# (see RERENDER-1442.md's first section), so none of them can be fitted to the
# result.
#
# ATTRIBUTION. The momwire column runs on the SAME momwire commit the published
# page used -- 23d81e5, v0.53.0 -- so every row that moves belongs to tool 1.10
# alone. A second, separately labelled column runs momwire v0.54.0 (260bd91) on
# the CHANGED rows only, to see whether #956/#1004 move any corpus row at all.
set -eu
cd "$(dirname "$0")/../.."
T="$HOME/nec5-timing"
PY=.venv/bin/python

# 1. translate, twice, for determinism
for pass in 1443 1443b; do
  rm -rf "$T/nec5-$pass"
  PYTHONUTF8=1 $PY scripts/nec5_corpus/nec5_corpus.py translate \
    --src "$T/raw" --out "$T/nec5-$pass" \
    --report "$T/nec5-$pass/translate-report.jsonl"
done
diff -r -q --exclude=translate-report.jsonl "$T/nec5-1443" "$T/nec5-1443b"

# 2. the NEC-5 side: the same binary the published page's metadata names, whose
#    sha is byte-identical to the deleted one it points at.
OMP_NUM_THREADS=4 OPENBLAS_NUM_THREADS=4 PYTHONUTF8=1 \
  $PY scripts/nec5_corpus/nec5_corpus.py check \
    --exe "$T/nec5cl-x13" --src "$T/nec5-1443" --timeout 300 \
    --report "$T/check-1443-nec5.jsonl"

# 3. the momwire side at the PUBLISHED pointer, twice
for pass in a b; do
  $PY scratch/896-census/census_momwire.py --jobs 4 \
    --src "$T/nec5-1443" --report "$T/census-1443-momwire-$pass.jsonl"
done

# 4. the page's generated half. `--cases 20` is not optional -- without it the
#    tail table comes out five rows longer and the byte-for-byte claim fails.
$PY scratch/896-census/census_report.py --cases 20 \
  --nec5 "$T/check-1443-nec5.jsonl" \
  --momwire "$T/census-1443-momwire-a.jsonl"

# 5. the attribution column: momwire v0.54.0 on the rows this re-render moved,
#    and Population B's column on momwire main after #1052 / #1050. Both are
#    SEPARATE checkouts selected by PYTHONPATH, never the submodule pointer.
#      PYTHONPATH=$HOME/momwire-260bd91/src  ... --src $T/changed-1443
#      PYTHONPATH=$HOME/momwire-553d671/src  ... --src $T/popb-1443

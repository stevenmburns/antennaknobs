#!/bin/bash
# The Skylake record behind site/src/content/docs/advanced/faster-solves.md.
#
#   run_skylake.sh examples MW_SRC   the page's worked examples (measure.py),
#                                    on a momwire built at the v0.97.1 tag
#   run_skylake.sh ladder   MW_SRC   dense fill / factor / mixed factor against
#                                    segment count (ladder.py), on a momwire
#                                    built at mixed-lu-all (momwire PR #2129)
#
# MW_SRC is that momwire checkout's src/ (built with `make build`); it is put
# first on PYTHONPATH so it outranks the venv's own momwire. Run from the
# antennaknobs checkout's root, with PY set to its venv's python. One process
# at a time, each under a 12 GB address-space cap, at default threads.
set -u
MODE=$1
MW_SRC=$2
PY=${PY:-.venv/bin/python}
HERE=$(cd "$(dirname "$0")" && pwd)
OUTDIR=$HERE/skylake
mkdir -p "$OUTDIR"
export PYTHONPATH="$MW_SRC:$PWD/src"
CAP=$((12 * 1024 * 1024 * 1024))
{
  echo "# mode: $MODE  date: $(date -Is)"
  echo "# host: $(hostname) $(lscpu | sed -n 's/^Model name: *//p'), nproc $(nproc), $(free -g | awk '/Mem:/{print $2}') GB"
  # momwire has no __version__: read its pyproject, beside MW_SRC.
  echo "# momwire: $(sed -n 's/^version = "\(.*\)"/\1/p' "$MW_SRC/../pyproject.toml") $($PY -c 'import momwire; print(momwire.__file__)') at $(git -C "$MW_SRC/.." rev-parse --short HEAD)"
  echo "# antennaknobs: $(git rev-parse --short HEAD) ($(git rev-parse --abbrev-ref HEAD))"
  echo "# OMP_NUM_THREADS=${OMP_NUM_THREADS:-unset} OPENBLAS_NUM_THREADS=${OPENBLAS_NUM_THREADS:-unset}"
} >> "$OUTDIR/env.txt"

case $MODE in
examples)
  : > "$OUTDIR/raw.jsonl"
  : > "$OUTDIR/raw_small.jsonl"
  CASES="vertical16_sector_bs2 vertical16_sector_sin vertical16_reuse_bs2 vertical16_reuse_sin
longwire_reuse_bs2 longwire_reuse_sin longwire_reuse_razor
yagi10_reuse_bs2 yagi10_reuse_sin yagi10_reuse_razor
yagi10_free_reuse_bs2 yagi10_free_reuse_sin longwire_free_reuse_sin"
  for c in $CASES; do
    for sw in off on; do
      prlimit --as=$CAP $PY "$HERE/measure.py" "$c" "$sw" 4 >> "$OUTDIR/raw.jsonl" \
        2>> "$OUTDIR/stderr.txt" || echo "FAILED $c $sw" >> "$OUTDIR/stderr.txt"
    done
  done
  for c in vertical16_sector_bs2 yagi10_reuse_bs2 longwire_reuse_bs2; do
    for sw in off on; do
      prlimit --as=$CAP $PY "$HERE/measure.py" "$c" "$sw" 4 15 >> "$OUTDIR/raw_small.jsonl" \
        2>> "$OUTDIR/stderr.txt" || echo "FAILED small $c $sw" >> "$OUTDIR/stderr.txt"
    done
  done
  $PY "$HERE/summarize.py" "$OUTDIR/raw.jsonl" > "$OUTDIR/summary.txt"
  $PY "$HERE/summarize.py" "$OUTDIR/raw_small.jsonl" > "$OUTDIR/summary_small.txt"
  ;;
ladder)
  : > "$OUTDIR/ladder.jsonl"
  # Main ladder: beams.yagi at 8 directors (about 18 segments per unit of N:
  # 2,154 at N = 120), where the mixed route refines. Second: wire.longwire
  # (about 13.9 per N), where on the laptop it stalled and fell back at ~2k.
  for eng in bs2 sinusoidal razor2p; do
    for gnd in free somm; do
      NS="30 60 120 180 240 330 420 520"
      [ "$eng" = sinusoidal ] && [ "$gnd" = somm ] && NS="$NS 700"
      for n in $NS; do
        prlimit --as=$CAP $PY "$HERE/ladder.py" "$eng" "$gnd" "$n" beams.yagi '{"n_directors": 8}' \
          >> "$OUTDIR/ladder.jsonl" 2>> "$OUTDIR/stderr.txt" \
          || echo "FAILED ladder yagi $eng $gnd $n" >> "$OUTDIR/stderr.txt"
      done
    done
  done
  for eng in bs2 razor2p; do
    for n in 75 145 320 575; do
      prlimit --as=$CAP $PY "$HERE/ladder.py" "$eng" free "$n" wire.longwire \
        >> "$OUTDIR/ladder.jsonl" 2>> "$OUTDIR/stderr.txt" \
        || echo "FAILED ladder longwire $eng $n" >> "$OUTDIR/stderr.txt"
    done
  done
  ;;
*)
  echo "usage: $0 examples|ladder MW_SRC" >&2
  exit 2
  ;;
esac
echo "done $MODE"

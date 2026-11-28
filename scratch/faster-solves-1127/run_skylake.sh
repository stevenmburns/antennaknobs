#!/bin/bash
# The Skylake record behind site/src/content/docs/advanced/faster-solves.md,
# re-measured on momwire 0.99.0. Run from the antennaknobs checkout's root with
# PY set to a python that can import both; MW_SRC is the momwire checkout's
# src/. One process at a time, each under a 12 GB address-space cap, default
# threads. Each config: 4 solves in one process (rep 0 = the first solve of
# the geometry, census included; reps 1-3 timed).
set -u
MW_SRC=$1
PY=${PY:-python}
HERE=$(cd "$(dirname "$0")" && pwd)
OUTDIR=$HERE/skylake
mkdir -p "$OUTDIR"
export PYTHONPATH="$PWD/src:$MW_SRC"
CAP=$((12 * 1024 * 1024 * 1024))
{
  echo "# pre-run: uptime: $(uptime)"
  echo "# date: $(date -Is)"
  echo "# host: $(hostname) $(lscpu | sed -n 's/^Model name: *//p'), nproc $(nproc), $(free -g | awk '/Mem:/{print $2}') GB"
  echo "# momwire tree: $MW_SRC/.. at $(git -C "$MW_SRC/.." rev-parse --short HEAD) (v0.99.0 = b1cf04f1; differs from it only in pyproject version, CLAUDE.md, one docs line)"
  $PY -c 'import momwire; print("# momwire imported from:", momwire.__file__)'
  echo "# antennaknobs: $(git rev-parse --short HEAD) ($(git rev-parse --abbrev-ref HEAD)), imported from $PWD/src"
  echo "# OMP_NUM_THREADS=${OMP_NUM_THREADS:-unset} OPENBLAS_NUM_THREADS=${OPENBLAS_NUM_THREADS:-unset}"
} >> "$OUTDIR/env.txt"
: > "$OUTDIR/raw.jsonl"
: > "$OUTDIR/raw_small.jsonl"
CASES="vertical16_sector_bs2 vertical16_sector_sin vertical16_reuse_bs2 vertical16_reuse_sin
longwire_reuse_bs2 longwire_reuse_sin longwire_reuse_razor longwire_free_reuse_bs2 longwire_free_reuse_sin
yagi10_reuse_bs2 yagi10_reuse_sin yagi10_reuse_razor
yagi10_free_reuse_bs2 yagi10_free_reuse_sin yagi10_free_reuse_razor
yagi10uc_reuse_bs2 yagi10uc_reuse_sin yagi10uc_reuse_razor
yagi10uc_free_reuse_bs2 yagi10uc_free_reuse_sin yagi10uc_free_reuse_razor"
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
echo done

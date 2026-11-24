#!/bin/bash
# The Skylake record behind the "Designing for reuse" section of
# site/src/content/docs/advanced/faster-solves.md.
#
#   run_skylake.sh MW_SRC    MW_SRC: a momwire checkout's src/, built with
#                            `make build`, first on PYTHONPATH
#
# Run from the antennaknobs checkout's root with PY set to its venv's python.
# One process at a time, each under a 12 GB address-space cap, default threads.
set -u
MW_SRC=$1
PY=${PY:-.venv/bin/python}
HERE=$(cd "$(dirname "$0")" && pwd)
OUT=$HERE/skylake
mkdir -p "$OUT"
export PYTHONPATH="$MW_SRC:$PWD/src"
CAP=$((12 * 1024 * 1024 * 1024))
{
  echo "# date: $(date -Is)  uptime: $(uptime)"
  echo "# host: $(hostname) $(lscpu | sed -n 's/^Model name: *//p'), nproc $(nproc)"
  echo "# momwire: $(sed -n 's/^version = "\(.*\)"/\1/p' "$MW_SRC/../pyproject.toml") at $(git -C "$MW_SRC/.." rev-parse --short HEAD)"
  echo "# antennaknobs: $(git rev-parse --short HEAD) ($(git rev-parse --abbrev-ref HEAD))"
} >> "$OUT/env.txt"
: > "$OUT/raw.jsonl"
for eng in sinusoidal razor2p bs2; do
  for gnd in free sommerfeld; do
    for uni in 0 1; do
      for sw in off on; do
        prlimit --as=$CAP $PY "$HERE/measure.py" $eng $gnd $uni $sw 4 >> "$OUT/raw.jsonl" \
          2>> "$OUT/stderr.txt" || echo "FAILED $eng $gnd $uni $sw" >> "$OUT/stderr.txt"
      done
    done
  done
done
echo ALLDONE >> "$OUT/env.txt"

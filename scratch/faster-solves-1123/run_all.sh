#!/bin/bash
# The measurement record behind site/src/content/docs/advanced/faster-solves.md.
# One process at a time, each under an 8 GB address-space cap; default threads.
# Each config: 4 solves in one process (rep 0 cold, reps 1-3 timed), off and
# on alternating.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
PY=/home/smburns/antennas/antennaknobs/.venv/bin/python
OUT=$HERE/raw.jsonl
: > "$OUT"
{
  echo "# date: $(date -Is)"
  echo "# host: $(lscpu | sed -n 's/^Model name: *//p'), nproc $(nproc), $(free -g | awk '/Mem:/{print $2}') GB"
  echo "# momwire: $($PY -c 'from importlib.metadata import version; print(version("momwire"))') at $(git -C /home/smburns/antennas/antennaknobs/momwire rev-parse --short HEAD)"
  echo "# antennaknobs imported from: $(git -C /home/smburns/antennas/antennaknobs rev-parse --short HEAD) ($(git -C /home/smburns/antennas/antennaknobs rev-parse --abbrev-ref HEAD))"
  echo "# OMP_NUM_THREADS=${OMP_NUM_THREADS:-unset} OPENBLAS_NUM_THREADS=${OPENBLAS_NUM_THREADS:-unset}"
} > "$HERE/env.txt"
CASES="vertical16_sector_bs2 vertical16_sector_sin vertical16_reuse_bs2 vertical16_reuse_sin
longwire_reuse_bs2 longwire_reuse_sin longwire_reuse_razor
yagi10_reuse_bs2 yagi10_reuse_sin yagi10_reuse_razor
yagi10_free_reuse_bs2 yagi10_free_reuse_sin longwire_free_reuse_sin"
for c in $CASES; do
  for sw in off on; do
    (cd /home/smburns/antennas/antennaknobs && prlimit --as=$((8*1024*1024*1024)) \
      $PY "$HERE/measure.py" "$c" "$sw" 4 >> "$OUT" 2>> "$HERE/stderr.txt") \
      || echo "FAILED $c $sw" >> "$HERE/stderr.txt"
  done
done
echo done

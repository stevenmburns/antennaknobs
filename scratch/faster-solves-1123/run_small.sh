#!/bin/bash
# The same designs at the stock bs2 slot's N (15 segments per quarter wave),
# for "when it won't help". Same protocol as run_all.sh.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
PY=/home/smburns/antennas/antennaknobs/.venv/bin/python
OUT=$HERE/raw_small.jsonl
: > "$OUT"
for c in vertical16_sector_bs2 yagi10_reuse_bs2 longwire_reuse_bs2; do
  for sw in off on; do
    (cd /home/smburns/antennas/antennaknobs && prlimit --as=$((8*1024*1024*1024)) \
      $PY "$HERE/measure.py" "$c" "$sw" 4 15 >> "$OUT" 2>> "$HERE/stderr_small.txt") \
      || echo "FAILED $c $sw" >> "$HERE/stderr_small.txt"
  done
done
echo done

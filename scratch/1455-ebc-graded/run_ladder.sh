#!/bin/bash
# AK#1455's ladder (G1, G3, C1): graded default then stock radiator, one after
# the other so the wall times do not contend. Launched as a transient service
# under MemoryMax=24G; a script file keeps systemd-run from expanding the
# variables below.
set -euo pipefail
cd /home/smburns/stevenmburns/antennaknobs-wt-1455
export NEC5_EXE=/home/smburns/nec5-timing/nec5cl-x13-static
export PYTHONPATH=/home/smburns/stevenmburns/momwire-wt-1064-v055/src:src
PY=/home/smburns/stevenmburns/antennaknobs/.venv/bin/python
D=scratch/1455-ebc-graded
for r in graded stock; do
    "$PY" "$D/ladder.py" "$r" --out "$D/ladder_$r.json" > "$D/ladder_$r.log" 2>&1
done
echo done > "$D/ladder.done"

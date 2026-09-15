#!/bin/bash
# The bs2 split-equivalence study's solves (PLAN.md), launched as a transient
# service under MemoryMax=24G. A script file keeps systemd-run from expanding
# the variables below.
set -uo pipefail
W=/home/smburns/stevenmburns/antennaknobs-wt-1511study
cd "$W"
export NEC5_EXE=/home/smburns/nec5-timing/nec5cl-x13-static
export PYTHONPATH=/home/smburns/stevenmburns/momwire-wt-1064-v055/src:$W/src
export OMP_NUM_THREADS=8
PY=/home/smburns/stevenmburns/antennaknobs/.venv/bin/python
D=scratch/1511-bs2-split
"$PY" -W ignore "$D/study.py" --out "$D/rows.jsonl" > "$D/rows.log" 2>&1
echo "exit $?" > "$D/rows.done"

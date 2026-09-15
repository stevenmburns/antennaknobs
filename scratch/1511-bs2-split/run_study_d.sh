#!/bin/bash
# Part D's solves (PLAN.md, Part D), launched as a transient service under
# MemoryMax=24G. A script file keeps systemd-run from expanding the variables
# below.
set -uo pipefail
W=/home/smburns/stevenmburns/antennaknobs-wt-1511study
cd "$W"
export PYTHONPATH=/home/smburns/stevenmburns/momwire-wt-1064-v055/src:$W/src
export OMP_NUM_THREADS=8
PY=/home/smburns/stevenmburns/antennaknobs/.venv/bin/python
D=scratch/1511-bs2-split
"$PY" -W ignore "$D/study_d.py" --out "$D/rows_d.jsonl" > "$D/rows_d.log" 2>&1
echo "exit $?" > "$D/rows_d.done"

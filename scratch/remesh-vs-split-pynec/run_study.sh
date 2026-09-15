#!/bin/bash
# The PyNEC re-mesh-vs-split solves (PLAN.md), launched as a transient service
# under MemoryMax=24G. A script file keeps systemd-run from expanding the
# variables below.
set -uo pipefail
W=/home/smburns/stevenmburns/antennaknobs-wt-remesh-pynec
cd "$W"
export PYTHONPATH=/home/smburns/stevenmburns/momwire-wt-1064-v055/src:$W/src
export OMP_NUM_THREADS=8
PY=/home/smburns/stevenmburns/antennaknobs/.venv/bin/python
D=scratch/remesh-vs-split-pynec
"$PY" -W ignore "$D/pynec_study.py" --out "$D/rows.jsonl" > "$D/rows.log" 2>&1
echo "exit $?" > "$D/rows.done"

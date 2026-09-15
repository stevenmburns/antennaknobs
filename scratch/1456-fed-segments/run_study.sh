#!/bin/bash
# AK#1456's size-sensitivity study (PLAN.md), launched as a transient service
# under MemoryMax=24G. It runs from a detached worktree at the committed harness
# (antennaknobs-wt-1456-run), so edits in the development worktree cannot change
# the code under a running study; the records land in the development worktree.
# A script file keeps systemd-run from expanding the variables below.
set -uo pipefail
RUN=/home/smburns/stevenmburns/antennaknobs-wt-1456-run
OUT=/home/smburns/stevenmburns/antennaknobs-wt-1456/scratch/1456-fed-segments
cd "$RUN"
export NEC5_EXE=/home/smburns/nec5-timing/nec5cl-x13-static
export PYTHONPATH=/home/smburns/stevenmburns/momwire-wt-1064-v055/src:$RUN/src
PY=/home/smburns/stevenmburns/antennaknobs/.venv/bin/python
WORKERS=4
export OMP_NUM_THREADS=$(( $(nproc) / WORKERS ))
"$PY" "$RUN/scratch/1456-fed-segments/sensitivity.py" --outdir "$OUT/study" --workers "$WORKERS" > "$OUT/study.log" 2>&1
echo "exit $?" > "$OUT/study.done"

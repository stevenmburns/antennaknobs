#!/bin/bash
# The antennaknobs suite for AK#1456 with momwire at the pointer (0.55.0,
# 1ca8725), as CI runs it: NEC5_EXE unset. It runs from the detached run
# worktree at the committed head, so edits in the development worktree cannot
# change the code under it; the log lands in the development worktree.
set -uo pipefail
RUN=/home/smburns/stevenmburns/antennaknobs-wt-1456-run
OUT=/home/smburns/stevenmburns/antennaknobs-wt-1456/scratch/1456-fed-segments
cd "$RUN"
export PYTHONPATH=/home/smburns/stevenmburns/momwire-wt-1064-v055/src:$RUN/src
export OMP_NUM_THREADS=2
unset NEC5_EXE
PY=/home/smburns/stevenmburns/antennaknobs/.venv/bin/python
"$PY" -m pytest -q -p no:cacheprovider -W ignore::UserWarning -n 6 tests > "$OUT/fulltests.log" 2>&1
echo "exit $?" > "$OUT/fulltests.done"

#!/bin/bash
# The antennaknobs suite with momwire at the pointer (0.55.0, 1ca8725), as CI
# runs it: NEC5_EXE unset, so the NEC-5 tests skip as they do there.
set -uo pipefail
cd /home/smburns/stevenmburns/antennaknobs-wt-1455
export PYTHONPATH=/home/smburns/stevenmburns/momwire-wt-1064-v055/src:src
export OMP_NUM_THREADS=2
unset NEC5_EXE
PY=/home/smburns/stevenmburns/antennaknobs/.venv/bin/python
D=scratch/1455-ebc-graded
X=""
if "$PY" -c "import xdist" 2>/dev/null; then X="-n 6"; fi
"$PY" -m pytest -q -p no:cacheprovider -W ignore::UserWarning $X tests > "$D/fulltests.log" 2>&1
echo "exit $?" > "$D/fulltests.done"

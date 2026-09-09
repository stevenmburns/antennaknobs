#!/usr/bin/env bash
# antennaknobs — Linux / macOS install, in one run.
#
#   bash scripts/install.sh              # into ./.venv in the current directory
#   PYTHON=python3.14 bash scripts/install.sh
#
# Idempotent; everything lives in the .venv it creates. On macOS the momwire
# wheel links Homebrew's OpenMP: `brew install libomp` first. If any step
# fails, this script's whole output is the thing to paste into an issue.
set -euo pipefail
PYTHON="${PYTHON:-python3}"
VENV="${VENV:-.venv}"

step() { printf '\n== %s\n' "$*"; }

step "Python"
command -v "$PYTHON" >/dev/null || { echo "$PYTHON not found. Install Python 3.12 (the version every test lane runs) and re-run."; exit 1; }
"$PYTHON" -VV

step "Virtual environment $VENV"
[ -x "$VENV/bin/python" ] || "$PYTHON" -m venv "$VENV"
PY="$VENV/bin/python"
"$PY" -c "import sys; print('venv python:', sys.executable)"

step "Install antennaknobs[web] (prebuilt wheels; momwire comes along)"
"$PY" -m pip install --upgrade pip
"$PY" -m pip install --upgrade "antennaknobs[web]"
"$PY" -m pip list | grep -E "^(antennaknobs|momwire|numpy|scipy|fastapi|uvicorn) " || true

step "Smoke: import and one solve"
"$PY" -X faulthandler -c "import momwire; print('momwire', momwire.__file__); print('accelerated =', momwire.accelerated)"
"$PY" -X faulthandler -c "import antennaknobs; print('IMPORT OK')"
"$PY" -c "from antennaknobs import Antenna; from antennaknobs.designs.dipoles.invvee import Builder; print('invvee free space:', Antenna(Builder()).impedance())"

step "Done"
cat <<MSG
Start the workbench:
    source $VENV/bin/activate
    uvicorn antennaknobs.web.server:app          # then open http://127.0.0.1:8000
With a licensed NEC-5, export NEC5_EXE=/path/to/nec5cl in the same shell first;
the NEC-5 tab appears in the solver panel. Keep that server on your local network only.
MSG

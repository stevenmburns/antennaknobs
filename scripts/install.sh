#!/usr/bin/env bash
# antennaknobs — Linux / macOS install, in one run: the README's "From PyPI"
# section, step for step, ending in the smoke test whose output is the thing
# to paste into an issue if anything fails.
#
#   bash scripts/install.sh                     # into ./.venv in the current directory
#   PYTHON=python3.14 bash scripts/install.sh   # a specific interpreter
#   PYNEC=1 bash scripts/install.sh             # also the README's optional NEC2 line
#
# Idempotent; everything lives in the .venv it creates. On macOS the momwire
# wheel links Homebrew's OpenMP: `brew install libomp` first.
#
# CI runs THIS script (test.yml `wheel-smoke`, publish.yml `published-smoke`)
# on Linux, Windows (the .ps1 twin) and macOS, so the README path a user
# follows and the path CI certifies are one file — edit both scripts together.
# The knobs below exist for those lanes; a user never needs them:
#   ANTENNAKNOBS_SPEC   pip requirement to install (default "antennaknobs[web]";
#                       CI passes the just-built wheel, the tag gate a ==version)
#   PYNEC=1             add "pynec-accel>=1.7.4.post2" (the README's optional
#                       NEC2 solver) and smoke it in the SAME process as momwire
#   SERVER_SMOKE=0      skip starting the web server for the health check
set -euo pipefail
PYTHON="${PYTHON:-python3}"
VENV="${VENV:-.venv}"
SPEC="${ANTENNAKNOBS_SPEC:-antennaknobs[web]}"
PYNEC="${PYNEC:-0}"
SERVER_SMOKE="${SERVER_SMOKE:-1}"

step() { printf '\n== %s\n' "$*"; }

step "Python"
command -v "$PYTHON" >/dev/null || { echo "$PYTHON not found. Install Python 3.12 (the version every test lane runs) and re-run."; exit 1; }
"$PYTHON" -VV

step "Virtual environment $VENV"
[ -x "$VENV/bin/python" ] || "$PYTHON" -m venv "$VENV"
PY="$VENV/bin/python"
"$PY" -c "import sys; print('venv python:', sys.executable)"

step "Install $SPEC (prebuilt wheels; momwire comes along)"
"$PY" -m pip install --upgrade pip
"$PY" -m pip install --upgrade "$SPEC"
if [ "$PYNEC" = "1" ]; then
    step "Install the optional NEC2 solver (pynec-accel)"
    "$PY" -m pip install --upgrade "pynec-accel>=1.7.4.post2"
fi
"$PY" -m pip list | grep -E "^(antennaknobs|momwire|pynec-accel|numpy|scipy|fastapi|uvicorn) " || true

step "Smoke: import and one solve"
"$PY" -X faulthandler -c "import momwire; print('momwire', momwire.__file__); print('accelerated =', momwire.accelerated); assert momwire.accelerated, 'momwire accelerator did not load'"
"$PY" -X faulthandler -c "import antennaknobs; print('IMPORT OK')"
"$PY" -c "from antennaknobs import Antenna; from antennaknobs.designs.dipoles.invvee import Builder; print('invvee free space:', Antenna(Builder()).impedance())"
if [ "$PYNEC" = "1" ]; then
    # Both engines in ONE process, momwire imported second: a private OpenMP
    # runtime on either side knocks momwire's accelerator onto pure Python
    # (the libgomp static-TLS clash the >=1.7.4.post2 floor exists for) or
    # aborts outright on macOS (duplicate libomp). accelerated must stay True.
    "$PY" -X faulthandler -c "import PyNEC; import momwire; assert momwire.accelerated, 'momwire lost its accelerator next to PyNEC (OpenMP runtime clash)'; from antennaknobs.engines.pynec import PyNECEngine; from antennaknobs.designs.dipoles.invvee import Builder; print('invvee free space (NEC2):', PyNECEngine(Builder()).impedance())"
fi

if [ "$SERVER_SMOKE" = "1" ]; then
    step "Smoke: the web server answers"
    PORT=$("$PY" -c "import socket; s=socket.socket(); s.bind(('127.0.0.1',0)); print(s.getsockname()[1]); s.close()")
    "$PY" -m uvicorn antennaknobs.web.server:app --host 127.0.0.1 --port "$PORT" --log-level warning &
    SERVER_PID=$!
    trap 'kill "$SERVER_PID" 2>/dev/null || true' EXIT
    "$PY" - "$PORT" <<'EOF'
import json, sys, time, urllib.request
port = sys.argv[1]
deadline = time.time() + 90
while True:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz", timeout=5) as r:
            body = json.load(r)
        assert body.get("ok") is True, body
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/capabilities", timeout=30) as r:
            assert r.status == 200, r.status
        print("server OK on port", port)
        break
    except Exception as e:  # polling until the server is up
        if time.time() > deadline:
            print("server did not answer within 90 s:", e)
            sys.exit(1)
        time.sleep(1)
EOF
    kill "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
    trap - EXIT
fi

step "Done"
cat <<MSG
Start the workbench:
    source $VENV/bin/activate
    uvicorn antennaknobs.web.server:app          # then open http://127.0.0.1:8000
With a licensed NEC-5, export NEC5_EXE=/path/to/nec5cl in the same shell first;
the NEC-5 tab appears in the solver panel. Keep that server on your local network only.
MSG

#!/usr/bin/env bash
# Hand smoke test for the momwire SimNEC portal daemon (issue #792).
#
# The unit suite proves the printout is right. This proves the PROCESS is
# right — the part a SimNEC session actually depends on and that no in-process
# test can see:
#
#   * `-version` prints exactly the one line `Execute.testCommand()` parses;
#   * three real decks go down ONE resident process, in order, each answered
#     with its own `NX` data-card echo (the sentinel `processResponse` blocks
#     in `readLine()` waiting for — miss it and the SimNEC UI hangs forever,
#     with no timeout on the Java side);
#   * it all works from a working directory that has nothing to do with the
#     checkout, because SimNEC launches the engine through `sh -c` with
#     cwd=$HOME.
#
# Run it before pointing a live SimNEC at a new build:
#
#     bash scripts/nec_portal_smoke.sh
#
# PYTHON overrides the interpreter (default: the repo's .venv, else python3).
set -uo pipefail

here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
repo=$(dirname "$here")
fixtures="$repo/tests/fixtures/nec_portal"

# The engine must never need the checkout on the path at runtime, but a source
# tree that was never `pip install`ed does — so offer src/ and let an installed
# antennaknobs win or not on its own.
export PYTHONPATH="$repo/src${PYTHONPATH:+:$PYTHONPATH}"

# Interpreter: $PYTHON if set, else the first candidate that can import momwire.
# A git worktree has no .venv of its own and borrows the main checkout's, which
# is what --git-common-dir finds.
candidates=("$repo/.venv/bin/python")
if main_git=$(git -C "$repo" rev-parse --path-format=absolute --git-common-dir 2>/dev/null); then
  candidates+=("$(dirname "$main_git")/.venv/bin/python")
fi
candidates+=(python3)

python=${PYTHON:-}
if [[ -z $python ]]; then
  for c in "${candidates[@]}"; do
    if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import momwire' >/dev/null 2>&1; then
      python=$c
      break
    fi
  done
fi
if [[ -z $python ]]; then
  echo "FAIL  no interpreter with momwire installed; set PYTHON=/path/to/python"
  exit 1
fi

# Free space, the two-source sensor probe (the path SimNEC drives an N-port
# antenna with — successor to the YY deck retired in #839), a radiation
# pattern, and the GN re-arm probe (#933): one deck per printout family.
decks=(dipole_free_space two_source_sensor_lines dipole_rp_pattern dipole_gn_rearm)

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

fail=0
note() { printf '  %s\n' "$*"; }
check() { # check <description> <condition-already-evaluated-as-exit-status>
  if [[ $2 -eq 0 ]]; then note "ok    $1"; else note "FAIL  $1"; fail=1; fi
}

echo "engine: $python -m antennaknobs.nec_portal"
echo "cwd:    $work  (unrelated to $repo, as SimNEC's sh -c would be)"
echo

# ---------------------------------------------------------------- version ---
echo "version probe"
probe=$(cd "$work" && "$python" -m antennaknobs.nec_portal -version 2>"$work/probe.err")
probe_rc=$?
check "exit 0" $probe_rc
[[ $(printf '%s\n' "$probe" | wc -l) -eq 1 ]]
check "exactly one line of stdout" $?
# nec2/Execute.versionNECd — `(NEC\d+\D.*)`, the honest-identity probe this
# build has answered since v0.46. `--legacy-probe` still offers versionA's
# `nec2c.ae6ty.<double>` shape for a SimNEC old enough to predate it.
[[ $probe =~ ^NEC2[^0-9].*$ ]]
check "matches Execute.versionNECd  (got: ${probe:-<empty>})" $?
[[ ! -s $work/probe.err ]]
check "stderr empty" $?
echo

# ------------------------------------------------------------------ decks ---
echo "resident run: ${decks[*]}"
for d in "${decks[@]}"; do
  cat "$fixtures/$d.deck"
done >"$work/in.deck"

(cd "$work" && "$python" -m antennaknobs.nec_portal <"$work/in.deck" \
  >"$work/out.txt" 2>"$work/out.err")
run_rc=$?
check "exit 0" $run_rc

sentinels=$(grep -cE '^ *DATA CARD No: +[0-9]+ NX' "$work/out.txt")
[[ $sentinels -eq ${#decks[@]} ]]
check "one NX sentinel per deck (${sentinels}/${#decks[@]})" $?

inputs=$(grep -c 'ANTENNA INPUT PARAMETERS' "$work/out.txt")
[[ $inputs -ge 6 ]]  # 1 + 2 (the sensor probe) + 1 + 2 (the GN re-arm)
check "every deck produced ANTENNA INPUT PARAMETERS ($inputs)" $?

grep -q 'VERSION:nec2c.ae6ty.momwire' "$work/out.txt"
check "printout banner carries the momwire identity" $?

grep -q 'PERFECT GROUND' "$work/out.txt"
check "the GN re-arm's second group answered over ground" $?

grep -q 'RADIATION PATTERNS' "$work/out.txt"
check "the pattern table came back" $?

! grep -q 'ERROR' "$work/out.txt"
check "no error line in the printout" $?

# NEC2Daemon never drains the child's stderr, so anything we write there can
# fill the pipe buffer and deadlock a long session. CM FF is the only licence.
[[ ! -s $work/out.err ]]
check "stderr empty" $?
echo

if [[ $fail -eq 0 ]]; then
  echo "PASS  ${#decks[@]} decks, one process, sentinels intact"
else
  echo "FAIL  see above; printout is at $work/out.txt (kept below)"
  cp "$work/out.txt" "$work/out.err" "${TMPDIR:-/tmp}/" 2>/dev/null || true
  echo "      copies in ${TMPDIR:-/tmp}/out.txt, ${TMPDIR:-/tmp}/out.err"
fi
exit $fail

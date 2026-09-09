# antennaknobs — Windows install, in one run: the README's Windows section,
# step for step, ending in the smoke test whose output is the thing to paste
# into an issue if anything fails.
#
#   Right-click > "Run with PowerShell", or from a PowerShell window:
#       .\install-windows.ps1            # into .\.venv beside this script
#       .\install-windows.ps1 -Python 3.14
#       .\install-windows.ps1 -PyNEC     # also the README's optional NEC2 line
#
# Idempotent: re-running upgrades in place. Everything it does is confined
# to the .venv folder it creates; nothing is installed system-wide except
# Python itself, and only if you say yes. If any step fails, the whole output
# of this script is what to paste into an issue at
# https://github.com/stevenmburns/antennaknobs/issues — it is the diagnostic.
#
# CI runs THIS script on windows-latest (test.yml `wheel-smoke`, publish.yml
# `published-smoke`), with scripts/install.sh as its Linux/macOS twin — edit
# both together. The parameters below the first two exist for those lanes:
#   -PythonExe   an interpreter path, bypassing the `py` launcher
#   -Spec        pip requirement (default "antennaknobs[web]"; CI passes the
#                just-built wheel, the tag gate a ==version)
#   -NoServer    skip starting the web server for the health check
param(
    [string]$Python = "3.12",     # 3.12 is the version every antennaknobs test lane runs
    [string]$Venv = ".venv",
    [string]$PythonExe = "",
    [string]$Spec = "antennaknobs[web]",
    [switch]$PyNEC,
    [switch]$NoServer
)
$ErrorActionPreference = "Stop"

function Step($msg) { Write-Host ""; Write-Host "== $msg" -ForegroundColor Cyan }
# Native commands do not throw on a non-zero exit under $ErrorActionPreference;
# every step that must succeed goes through this.
function Run { & $args[0] $args[1..($args.Length - 1)]; if ($LASTEXITCODE -ne 0) { throw "failed (exit $LASTEXITCODE): $args" } }

if ($PythonExe) {
    Step "Python $PythonExe"
    $base = @($PythonExe)
} else {
    Step "Python $Python"
    $have = $false
    try { $have = (& py -$Python -c "import sys; print(sys.version)" 2>$null) -ne $null } catch { $have = $false }
    if (-not $have) {
        Write-Host "Python $Python is not installed (py -$Python found nothing)."
        $ans = Read-Host "Install it now with winget (Python.Python.$Python)? [y/N]"
        if ($ans -match '^[Yy]') {
            winget install --id "Python.Python.$Python" --source winget --accept-package-agreements --accept-source-agreements
            Write-Host "Installed. Close this window, open a NEW PowerShell, and run this script again (the py launcher needs a fresh shell)."
            exit 0
        }
        Write-Host "Get it from https://www.python.org/downloads/windows/ (tick 'Add python.exe to PATH') and re-run."
        exit 1
    }
    $base = @("py", "-$Python")
}
Run @base -VV

Step "Virtual environment $Venv"
if (-not (Test-Path "$Venv\Scripts\python.exe")) { Run @base -m venv $Venv }
$py = Join-Path $Venv "Scripts\python.exe"
Run $py -c "import sys; print('venv python:', sys.executable)"

Step "Install $Spec (prebuilt wheels; momwire comes along)"
Run $py -m pip install --upgrade pip
Run $py -m pip install --upgrade $Spec
if ($PyNEC) {
    Step "Install the optional NEC2 solver (pynec-accel)"
    Run $py -m pip install --upgrade "pynec-accel>=1.7.4.post2"
}
& $py -m pip list | Select-String -Pattern "^(antennaknobs|momwire|pynec-accel|numpy|scipy|fastapi|uvicorn) "

Step "Smoke: import and one solve"
Run $py -X faulthandler -c "import momwire; print('momwire', momwire.__file__); print('accelerated =', momwire.accelerated); assert momwire.accelerated, 'momwire accelerator did not load'"
Run $py -X faulthandler -c "import antennaknobs; print('IMPORT OK')"
Run $py -c "from antennaknobs import Antenna; from antennaknobs.designs.dipoles.invvee import Builder; print('invvee free space:', Antenna(Builder()).impedance())"
if ($PyNEC) {
    # Both engines in ONE process, momwire imported second: the two wheels
    # carry different OpenMP runtimes today (LLVM libomp140 vs vcomp140), so
    # coexistence must keep momwire's accelerator loaded.
    Run $py -X faulthandler -c "import PyNEC; import momwire; assert momwire.accelerated, 'momwire lost its accelerator next to PyNEC (OpenMP runtime clash)'; from antennaknobs.engines.pynec import PyNECEngine; from antennaknobs.designs.dipoles.invvee import Builder; print('invvee free space (NEC2):', PyNECEngine(Builder()).impedance())"
}

if (-not $NoServer) {
    Step "Smoke: the web server answers"
    $port = & $py -c "import socket; s=socket.socket(); s.bind(('127.0.0.1',0)); print(s.getsockname()[1]); s.close()"
    $server = Start-Process -FilePath $py -ArgumentList @("-m", "uvicorn", "antennaknobs.web.server:app", "--host", "127.0.0.1", "--port", "$port", "--log-level", "warning") -PassThru -NoNewWindow
    try {
        $probeFile = Join-Path ([System.IO.Path]::GetTempPath()) "antennaknobs-server-probe.py"
        Set-Content -Path $probeFile -Value @"
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
    except Exception as e:
        if time.time() > deadline:
            print("server did not answer within 90 s:", e)
            sys.exit(1)
        time.sleep(1)
"@
        Run $py $probeFile $port
    } finally {
        Stop-Process -Id $server.Id -Force -ErrorAction SilentlyContinue
    }
}

Step "Done"
Write-Host "Start the workbench (in this or any new PowerShell window):"
Write-Host "    .\$Venv\Scripts\Activate.ps1"
Write-Host "    python -m uvicorn antennaknobs.web.server:app       # then open http://127.0.0.1:8000"
Write-Host ""
Write-Host "With a licensed NEC-5 (EZNEC Pro+ ships NEC5CL.exe), set this in the SAME window before starting:"
Write-Host "    `$env:NEC5_EXE = 'C:\Program Files\EZNEC Pro+\NEC5CL.exe'"
Write-Host "and the NEC-5 tab appears in the solver panel. Keep that server on your local network only."

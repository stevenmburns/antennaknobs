# antennaknobs — Windows install, in one run.
#
#   Right-click > "Run with PowerShell", or from a PowerShell window:
#       .\install-windows.ps1            # into .\.venv beside this script
#       .\install-windows.ps1 -Python 3.14
#
# Idempotent: re-running upgrades in place. Everything it does is confined
# to the .venv folder it creates; nothing is installed system-wide except
# Python itself, and only if you say yes. If any step fails, the whole output
# of this script is what to paste into an issue at
# https://github.com/stevenmburns/antennaknobs/issues — it is the diagnostic.
param(
    [string]$Python = "3.12",     # 3.12 is the version every antennaknobs test lane runs
    [string]$Venv = ".venv"
)
$ErrorActionPreference = "Stop"

function Step($msg) { Write-Host ""; Write-Host "== $msg" -ForegroundColor Cyan }

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
& py -$Python -VV

Step "Virtual environment $Venv"
if (-not (Test-Path "$Venv\Scripts\python.exe")) { & py -$Python -m venv $Venv }
$py = Join-Path $Venv "Scripts\python.exe"
& $py -c "import sys; print('venv python:', sys.executable)"

Step "Install antennaknobs[web] (prebuilt wheels; momwire comes along)"
& $py -m pip install --upgrade pip
& $py -m pip install --upgrade "antennaknobs[web]"
& $py -m pip list | Select-String -Pattern "^(antennaknobs|momwire|numpy|scipy|fastapi|uvicorn) "

Step "Smoke: import and one solve"
& $py -X faulthandler -c "import momwire; print('momwire', momwire.__file__); print('accelerated =', momwire.accelerated)"
& $py -X faulthandler -c "import antennaknobs; print('IMPORT OK')"
& $py -c "from antennaknobs import Antenna; from antennaknobs.designs.dipoles.invvee import Builder; print('invvee free space:', Antenna(Builder()).impedance())"

Step "Done"
Write-Host "Start the workbench (in this or any new PowerShell window):"
Write-Host "    .\$Venv\Scripts\Activate.ps1"
Write-Host "    python -m uvicorn antennaknobs.web.server:app       # then open http://127.0.0.1:8000"
Write-Host ""
Write-Host "With a licensed NEC-5 (EZNEC Pro+ ships NEC5CL.exe), set this in the SAME window before starting:"
Write-Host "    `$env:NEC5_EXE = 'C:\Program Files\EZNEC Pro+\NEC5CL.exe'"
Write-Host "and the NEC-5 tab appears in the solver panel. Keep that server on your local network only."

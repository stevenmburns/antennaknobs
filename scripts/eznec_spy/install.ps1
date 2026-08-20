<#
.SYNOPSIS
  Install the spy shim in place of a host's NEC engine (momwire#390, #413).

.DESCRIPTION
  Renames the real engine to <name>.real.exe and puts the shim at the exact path
  the host launches, so nothing about the host's configuration changes. Idempotent,
  and reversible with uninstall.ps1.

  The host must be closed while this runs — a running instance holds no lock on the
  engine between calculations, but swapping mid-calculation would corrupt a run.

  Defaults target EZNEC's NEC-5 engine. For 4nec2 (#413), which picks among several
  engine builds by segment count, install once per binary:

    ./install.ps1 -Engine C:\4nec2\exe\nec2dxs11k.exe -Shim .\nec2dxs11k.exe `
                  -HostProcess 4nec2 -MinEngineSize 200KB

  Provenance is recorded per engine, so several installs coexist.
#>
[CmdletBinding()]
param(
    [string] $Engine = 'C:\EZNEC 7.0\Docs\NEC5CL_x13.exe',
    [string] $Shim,
    # Process name that must not be running (the host front-end), without .exe.
    [string] $HostProcess = 'EZWpro2+',
    # Floor for "this is a real engine, not our own shim". NEC-5 is ~10 MB, but
    # the 4nec2 builds are ~300 KB, so the floor has to travel with the host.
    [long]   $MinEngineSize = 1MB,
    [switch] $Force
)

$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $Shim) { $Shim = Join-Path $here 'NEC5CL_x13.exe' }

if (-not (Test-Path $Shim))   { throw "Shim not built: $Shim (run build.ps1 first)" }
if (-not (Test-Path $Engine)) { throw "Engine not found: $Engine" }

$real   = [IO.Path]::ChangeExtension($Engine, $null).TrimEnd('.') + '.real.exe'
$record = Join-Path $here ('installed-' + [IO.Path]::GetFileNameWithoutExtension($Engine) + '.tsv')

if (Test-Path $real) {
    if (-not $Force) {
        Write-Host "Shim already installed (real engine at $real). Refreshing shim binary."
    }
    Copy-Item $Shim $Engine -Force
    Write-Host "Refreshed: $Engine"
    exit 0
}

# Guard: refuse to archive our own shim as if it were the real engine.
$engineSize = (Get-Item $Engine).Length
$shimSize   = (Get-Item $Shim).Length
if ($engineSize -lt $MinEngineSize) {
    throw "Refusing to install: $Engine is only $engineSize bytes, under the -MinEngineSize floor of $MinEngineSize — that looks like a shim, not a real engine. Run uninstall.ps1 first."
}

$engineHash = (Get-FileHash $Engine -Algorithm SHA256).Hash

if (Get-Process -Name $HostProcess -ErrorAction SilentlyContinue) {
    throw "$HostProcess is running. Close it before installing the shim."
}

Move-Item $Engine $real
Copy-Item $Shim $Engine

@(
    "installed_utc`t$([DateTime]::UtcNow.ToString('o'))"
    "engine_path`t$Engine"
    "real_engine_path`t$real"
    "real_engine_sha256`t$engineHash"
    "real_engine_bytes`t$engineSize"
    "shim_bytes`t$shimSize"
    "shim_source`t$Shim"
) | Set-Content -Path $record -Encoding UTF8

Write-Host "Real engine -> $real"
Write-Host "Shim        -> $Engine"
Write-Host "Provenance  -> $record"
Write-Host ''
Write-Host "Next: start $HostProcess, run one model, then check the capture root."

<#
.SYNOPSIS
  Install the spy shim in place of EZNEC's NEC-5 engine (momwire#390 step 1).

.DESCRIPTION
  Renames the real engine to <name>.real.exe and puts the shim at the exact path
  EZNEC launches, so nothing about EZNEC's configuration changes. Idempotent, and
  reversible with uninstall.ps1.

  EZNEC must be closed while this runs — a running instance holds no lock on the
  engine between calculations, but swapping mid-calculation would corrupt a run.
#>
[CmdletBinding()]
param(
    [string] $Engine = 'C:\EZNEC 7.0\Docs\NEC5CL_x13.exe',
    [string] $Shim,
    [switch] $Force
)

$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $Shim) { $Shim = Join-Path $here 'NEC5CL_x13.exe' }

if (-not (Test-Path $Shim))   { throw "Shim not built: $Shim (run build.ps1 first)" }
if (-not (Test-Path $Engine)) { throw "Engine not found: $Engine" }

$real   = [IO.Path]::ChangeExtension($Engine, $null).TrimEnd('.') + '.real.exe'
$record = Join-Path $here 'installed.tsv'

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
if ($engineSize -lt 1MB) {
    throw "Refusing to install: $Engine is only $engineSize bytes — that looks like a shim, not the NEC-5 engine. Run uninstall.ps1 first."
}

$engineHash = (Get-FileHash $Engine -Algorithm SHA256).Hash

if (Get-Process -Name 'EZWpro2+' -ErrorAction SilentlyContinue) {
    throw 'EZNEC is running. Close it before installing the shim.'
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
Write-Host 'Next: open EZNEC, confirm the calculating engine is NEC-5, and run one model.'

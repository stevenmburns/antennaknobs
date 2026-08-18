<#
.SYNOPSIS
  Restore a host's real NEC engine, removing the spy shim (momwire#390, #413).

.DESCRIPTION
  Reverses install.ps1 and verifies the restored binary against the per-engine
  provenance record. Pass -HostProcess for hosts other than EZNEC.
#>
[CmdletBinding()]
param(
    [string] $Engine = 'C:\EZNEC 7.0\Docs\NEC5CL_x13.exe',
    [string] $HostProcess = 'EZWpro2+'
)

$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$real = [IO.Path]::ChangeExtension($Engine, $null).TrimEnd('.') + '.real.exe'

if (-not (Test-Path $real)) { throw "No archived engine at $real — nothing to restore." }

if (Get-Process -Name $HostProcess -ErrorAction SilentlyContinue) {
    throw "$HostProcess is running. Close it before uninstalling the shim."
}

if (Test-Path $Engine) { Remove-Item $Engine -Force }
Move-Item $real $Engine

$record = Join-Path $here ('installed-' + [IO.Path]::GetFileNameWithoutExtension($Engine) + '.tsv')
if (-not (Test-Path $record)) { $record = Join-Path $here 'installed.tsv' }   # pre-#413 layout
if (Test-Path $record) {
    $want = ((Get-Content $record) -match '^real_engine_sha256') -replace '^\S+\s+', ''
    $got  = (Get-FileHash $Engine -Algorithm SHA256).Hash
    if ($want -and ($want -ne $got)) {
        Write-Warning "Restored engine hash $got does not match recorded $want"
    } else {
        Write-Host "Restored and hash-verified: $Engine"
    }
    Remove-Item $record -Force
} else {
    Write-Host "Restored: $Engine"
}

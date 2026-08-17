<#
.SYNOPSIS
  Restore EZNEC's real NEC-5 engine, removing the spy shim (momwire#390).
#>
[CmdletBinding()]
param(
    [string] $Engine = 'C:\EZNEC 7.0\Docs\NEC5CL_x13.exe'
)

$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$real = [IO.Path]::ChangeExtension($Engine, $null).TrimEnd('.') + '.real.exe'

if (-not (Test-Path $real)) { throw "No archived engine at $real — nothing to restore." }

if (Get-Process -Name 'EZWpro2+' -ErrorAction SilentlyContinue) {
    throw 'EZNEC is running. Close it before uninstalling the shim.'
}

if (Test-Path $Engine) { Remove-Item $Engine -Force }
Move-Item $real $Engine

$record = Join-Path $here 'installed.tsv'
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

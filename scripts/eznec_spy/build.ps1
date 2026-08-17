<#
.SYNOPSIS
  Compile the NEC-5 spy shim (momwire#390).

.DESCRIPTION
  Uses the in-box .NET Framework C# compiler, so nothing needs installing on the
  Windows host. The capture root is baked into the binary at compile time; it can
  still be overridden at run time with the EZNEC_SPY_ROOT environment variable.
#>
[CmdletBinding()]
param(
    # Where captures land. Default: <repo>/scratch/eznec-capture
    [string] $CaptureRoot,
    [string] $OutFile
)

$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$repo = Split-Path -Parent (Split-Path -Parent $here)

if (-not $CaptureRoot) { $CaptureRoot = Join-Path $repo 'scratch\eznec-capture' }
if (-not $OutFile)     { $OutFile     = Join-Path $here 'NEC5CL_x13.exe' }

$csc = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
if (-not (Test-Path $csc)) { throw "C# compiler not found at $csc" }

$src = Get-Content (Join-Path $here 'Nec5Spy.cs') -Raw
$src = $src.Replace('__CAPTURE_ROOT__', $CaptureRoot.Replace('\', '\\'))

$tmp = Join-Path ([IO.Path]::GetTempPath()) ('Nec5Spy_{0}.cs' -f [Guid]::NewGuid().ToString('N'))
Set-Content -Path $tmp -Value $src -Encoding UTF8

try {
    & $csc /nologo /target:exe /platform:anycpu /optimize+ `
        /r:System.dll /r:System.Core.dll `
        ("/out:" + $OutFile) $tmp
    if ($LASTEXITCODE -ne 0) { throw "csc failed with exit code $LASTEXITCODE" }
} finally {
    Remove-Item $tmp -ErrorAction SilentlyContinue
}

New-Item -ItemType Directory -Force -Path $CaptureRoot | Out-Null
Write-Host "Built  : $OutFile"
Write-Host "Capture: $CaptureRoot"

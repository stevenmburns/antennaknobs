param([string]$Name, [string]$Exe, [int]$N = 50)

$rig = "C:\Users\smbur\antennas\antennaknobs\scratch\718-phase4\rig"
Set-Location $rig
$deck = "$rig\EZN5.NEC"
$outf = "$rig\sweep_$Name.out"

# 50 points across 20m, exactly as EZNEC steps a sweep: one launch per point.
$f0 = 14.0; $f1 = 14.35
$rows = @()
$sweep = [Diagnostics.Stopwatch]::StartNew()
foreach ($i in 0..($N-1)) {
  $f = $f0 + ($f1 - $f0) * $i / ($N - 1)
  @"
CM Back yard dipole
CM
CM EZNEC Pro/2+ v. 7.0.4  sweep point $i
CM
CM ! Written by EZNEC/Pro+ v. 7.0 in NEC-5 format.
CE
GW 1,11,0.,0.,9.144,0.,10.18946,9.144,.0010262
GE 1,-1
FR 0,1,0,0,$($f.ToString('0.######'))
GN 0,0,0,0,20.,.0303,1.,0.
EX 4,1,6,0,1.414214,0.
PQ 0
XQ 0
EN
"@ | Set-Content -Path $deck -Encoding ASCII

  $sw = [Diagnostics.Stopwatch]::StartNew()
  & $Exe $deck $outf 2>&1 | Out-Null
  $sw.Stop()

  $z = Select-String -Path $outf -Pattern '^\s+1\s+6\s+1\s' | Select-Object -First 1
  $r = $null; $x = $null
  if ($z) {
    $p = ($z.Line -split '\s+') | Where-Object { $_ -ne '' }
    $r = [double]$p[7]; $x = [double]$p[8]
  }
  $rows += [pscustomobject]@{ i=$i; f_MHz=[math]::Round($f,4); ms=[math]::Round($sw.Elapsed.TotalMilliseconds,1); R=$r; X=$x }
}
$sweep.Stop()

$rows | Export-Csv -Path "$rig\sweep_$Name.csv" -NoTypeInformation
$s = $rows.ms | Measure-Object -Average -Minimum -Maximum
""
"=== $Name : $N-point sweep ==="
"  total wall : $([math]::Round($sweep.Elapsed.TotalSeconds,2)) s"
"  per point  : mean $([math]::Round($s.Average,1)) ms   min $($s.Minimum)  max $($s.Maximum)"
$ok = ($rows | Where-Object { $_.R -ne $null }).Count
"  points with impedance parsed : $ok / $N"
"  Z at band edges : $($rows[0].f_MHz) MHz -> $($rows[0].R) $($rows[0].X)j    $($rows[-1].f_MHz) MHz -> $($rows[-1].R) $($rows[-1].X)j"

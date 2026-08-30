param([string]$Mode = "const", [int]$N = 60)
$rig = "C:\Users\smbur\antennas\antennaknobs\scratch\718-phase4\rig"
$B   = "C:\Users\smbur\antennas\antennaknobs\scratch\718-phase4\bundle\momwire-eznec"
Set-Location $rig
$deck = "$rig\EZN5.NEC"; $outf = "$rig\stress.out"
$slow = @(); $t = @()
foreach ($i in 0..($N-1)) {
  if ($Mode -eq "vary") {
    $f = 14.0 + 0.35 * $i / ($N - 1)
    "CM s`nCM`nCM x`nCM`nCM y`nCE`nGW 1,11,0.,0.,9.144,0.,10.18946,9.144,.0010262`nGE 1,-1`nFR 0,1,0,0,$($f.ToString('0.######'))`nGN 0,0,0,0,20.,.0303,1.,0.`nEX 4,1,6,0,1.414214,0.`nPQ 0`nXQ 0`nEN" | Set-Content $deck -Encoding ASCII
  }
  $sw = [Diagnostics.Stopwatch]::StartNew()
  $o = & "$B\momwire-eznec.exe" $deck $outf 2>&1 | Out-String
  $sw.Stop()
  $ms = [math]::Round($sw.Elapsed.TotalMilliseconds,1); $t += $ms
  if ($ms -gt 500) { $slow += [pscustomobject]@{ i=$i; ms=$ms; out=$o.Trim() } }
}
$s = $t | Measure-Object -Average -Minimum -Maximum
"=== mode=$Mode  N=$N ==="
"  mean=$([math]::Round($s.Average,1)) min=$($s.Minimum) max=$($s.Maximum) ms"
"  fallbacks (>500ms): $($slow.Count) / $N  = $([math]::Round(100*$slow.Count/$N,1))%"
foreach ($x in $slow) { "    i=$($x.i) $($x.ms) ms  stdout=[$($x.out)]" }
$fast = $t | Where-Object { $_ -le 500 }
if ($fast) { $f2 = $fast | Measure-Object -Average -Minimum; "  fast-only mean=$([math]::Round($f2.Average,1)) min=$($f2.Minimum) ms" }

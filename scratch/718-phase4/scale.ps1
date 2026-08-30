param([int[]]$Segs = @(401,801,1601), [string]$Tag = "accel-on", [int]$Reps = 2)
$P = "C:\Users\smbur\antennas\antennaknobs\scratch\718-phase4"
$B7 = "$P\bundle7\momwire-eznec"; $rig = "$P\rig"
Set-Location $rig
$deck = "$rig\scale.nec"; $outf = "$rig\scale.out"
function Deck($n, $f) {
  $mid = [int](($n + 1) / 2)
  "CM bydipole1 scaled $n seg`nCM`nCM x`nCM`nCM y`nCE`nGW 1,$n,0.,0.,9.144,0.,10.18946,9.144,.0010262`nGE 1,-1`nFR 0,1,0,0,$f`nGN 0,0,0,0,20.,.0303,1.,0.`nEX 4,1,$mid,0,1.414214,0.`nPQ 0`nXQ 0`nEN" | Set-Content $deck -Encoding ASCII
  return $mid
}
# Warm the daemon AND the Sommerfeld grid at the frequency every timed run uses,
# so what we time is the solve, not a one-off ground fill.
Deck 21 "14." | Out-Null
& "$B7\momwire-eznec.exe" $deck $outf 2>&1 | Out-Null
& "$B7\momwire-eznec.exe" $deck $outf 2>&1 | Out-Null
foreach ($n in $Segs) {
  $mid = Deck $n "14."
  $t = @()
  foreach ($r in 1..$Reps) {
    $sw = [Diagnostics.Stopwatch]::StartNew()
    & "$B7\momwire-eznec.exe" $deck $outf 2>&1 | Out-Null
    $sw.Stop(); $t += [math]::Round($sw.Elapsed.TotalMilliseconds,1)
  }
  $l = Select-String -Path $outf -Pattern "^\s+1\s+$mid\s+1\s" | Select-Object -First 1
  $z = if ($l) { $p=($l.Line -split '\s+')|Where-Object{$_ -ne ''}; "$($p[7]) $($p[8])j" } else { "NO Z" }
  $best = ($t | Measure-Object -Minimum).Minimum
  "{0,-10} segs={1,5}  best={2,9} ms  runs=[{3}]  Z={4}" -f $Tag, $n, $best, ($t -join ', '), $z
}

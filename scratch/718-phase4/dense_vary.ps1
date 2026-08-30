param([int]$Segs = 401, [string]$Bundle = "bundle")
$rig = "C:\Users\smbur\antennas\antennaknobs\scratch\718-phase4\rig"
$B   = "C:\Users\smbur\antennas\antennaknobs\scratch\718-phase4\$Bundle\momwire-eznec"
Set-Location $rig
$mid = [int](($Segs + 1) / 2); $deck = "$rig\dense_v.nec"
# warm-up on a frequency none of the timed runs reuse
"CM w`nCM`nCM x`nCM`nCM y`nCE`nGW 1,$Segs,0.,0.,9.144,0.,10.18946,9.144,.0010262`nGE 1,-1`nFR 0,1,0,0,13.9`nGN 0,0,0,0,20.,.0303,1.,0.`nEX 4,1,$mid,0,1.414214,0.`nPQ 0`nXQ 0`nEN" | Set-Content $deck -Encoding ASCII
& "$B\momwire-eznec.exe" $deck "$rig\dense_v.out" 2>&1 | Out-Null
$t=@(); $zs=@()
foreach($i in 0..2){
  $f = 14.0 + 0.05*$i           # every run a DIFFERENT frequency: no repeat, no cache hit
  "CM d`nCM`nCM x`nCM`nCM y`nCE`nGW 1,$Segs,0.,0.,9.144,0.,10.18946,9.144,.0010262`nGE 1,-1`nFR 0,1,0,0,$($f.ToString('0.###'))`nGN 0,0,0,0,20.,.0303,1.,0.`nEX 4,1,$mid,0,1.414214,0.`nPQ 0`nXQ 0`nEN" | Set-Content $deck -Encoding ASCII
  $sw=[Diagnostics.Stopwatch]::StartNew()
  & "$B\momwire-eznec.exe" $deck "$rig\dense_v.out" 2>&1|Out-Null
  $sw.Stop(); $t+=[math]::Round($sw.Elapsed.TotalMilliseconds,1)
  $l = Select-String -Path "$rig\dense_v.out" -Pattern "^\s+1\s+$mid\s+1\s" | Select-Object -First 1
  $p=($l.Line -split '\s+')|Where-Object{$_ -ne ''}; $zs += "$($p[7])$($p[8])j"
}
"segs=$Segs  distinct freqs 14.00/14.05/14.10 -> [$($t -join ', ')] ms  mean=$([math]::Round(($t|Measure-Object -Average).Average,1)) ms"
"  Z per run (must differ, proving distinct solves): $($zs -join ' | ')"

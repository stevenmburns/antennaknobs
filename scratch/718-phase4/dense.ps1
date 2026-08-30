param([string]$Tag, [int]$Segs = 201)
$rig = "C:\Users\smbur\antennas\antennaknobs\scratch\718-phase4\rig"
$B   = "C:\Users\smbur\antennas\antennaknobs\scratch\718-phase4\bundle\momwire-eznec"
Set-Location $rig
$mid = [int](($Segs + 1) / 2)
$deck = "$rig\dense.nec"
"CM dense dipole $Segs seg`nCM`nCM x`nCM`nCM y`nCE`nGW 1,$Segs,0.,0.,9.144,0.,10.18946,9.144,.0010262`nGE 1,-1`nFR 0,1,0,0,14.`nGN 0,0,0,0,20.,.0303,1.,0.`nEX 4,1,$mid,0,1.414214,0.`nPQ 0`nXQ 0`nEN" | Set-Content $deck -Encoding ASCII
# warm the engine on this deck shape first, then time 3
& "$B\momwire-eznec.exe" $deck "$rig\dense.out" 2>&1 | Out-Null
$t=@(); foreach($i in 1..3){ $sw=[Diagnostics.Stopwatch]::StartNew(); & "$B\momwire-eznec.exe" $deck "$rig\dense.out" 2>&1|Out-Null; $sw.Stop(); $t+=[math]::Round($sw.Elapsed.TotalMilliseconds,1) }
$l = Select-String -Path "$rig\dense.out" -Pattern "^\s+1\s+$mid\s+1\s" | Select-Object -First 1
$z = if ($l) { $p=($l.Line -split '\s+')|Where-Object{$_ -ne ''}; "$($p[7]) $($p[8])j" } else { "no Z" }
"{0,-22} segs={1}  [{2}] ms  mean={3} ms   Z={4}" -f $Tag, $Segs, ($t -join ', '), [math]::Round(($t|Measure-Object -Average).Average,1), $z

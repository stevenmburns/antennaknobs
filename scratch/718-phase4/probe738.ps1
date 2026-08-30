param([string]$Tag, [string]$Ground = "real", [double]$F0 = 14.0, [double]$F1 = 14.35, [int]$N = 50)
$P = "C:\Users\smbur\antennas\antennaknobs\scratch\718-phase4"
$B7 = "$P\bundle7\momwire-eznec"; $rig = "$P\rig"
Set-Location $rig
$deck = "$rig\p738.nec"; $outf = "$rig\p738.out"
# fresh daemon every time: the stall only shows on a cold one
Get-Process -Name momwire-eznec-engine -EA SilentlyContinue | ForEach-Object { Stop-Process -Id $_.Id -Force }
Start-Sleep -Milliseconds 1200
$gn = if ($Ground -eq "free") { "GE 0" } else { "GE 1,-1`nGN 0,0,0,0,20.,.0303,1.,0." }
$t = @()
foreach ($i in 0..($N-1)) {
  $f = $F0 + ($F1 - $F0) * $i / ($N - 1)
  "CM p738`nCM`nCM x`nCM`nCM y`nCE`nGW 1,11,0.,0.,9.144,0.,10.18946,9.144,.0010262`n$gn`nFR 0,1,0,0,$($f.ToString('0.######'))`nEX 4,1,6,0,1.414214,0.`nPQ 0`nXQ 0`nEN" | Set-Content $deck -Encoding ASCII
  $sw = [Diagnostics.Stopwatch]::StartNew()
  & "$B7\momwire-eznec.exe" $deck $outf 2>&1 | Out-Null
  $sw.Stop(); $t += [math]::Round($sw.Elapsed.TotalMilliseconds,1)
}
$slow = @(); for ($i=0; $i -lt $t.Count; $i++) { if ($t[$i] -gt 300) { $slow += "i=${i}:$($t[$i])" } }
$fast = $t | Where-Object { $_ -le 300 }
"{0,-26} ground={1,-4} band={2}-{3}  total={4,6} s  fastmean={5,5} ms  slow=[{6}]" -f `
  $Tag, $Ground, $F0, $F1, [math]::Round((($t|Measure-Object -Sum).Sum)/1000,2), `
  [math]::Round((($fast|Measure-Object -Average).Average),1), ($slow -join ', ')

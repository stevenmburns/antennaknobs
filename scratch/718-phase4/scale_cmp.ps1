param([int[]]$Segs = @(401,801,1601), [int]$Reps = 2)
$P = "C:\Users\smbur\antennas\antennaknobs\scratch\718-phase4"
$B7 = "$P\bundle7\momwire-eznec"; $rig = "$P\rig"
$LIC = "C:\EZNEC 7.0\Docs\NEC5CL_x13.exe"
Set-Location $rig
$deck = "$rig\cmp.nec"
function Deck($n) {
  $mid = [int](($n + 1) / 2)
  "CM bydipole1 scaled $n seg`nCM`nCM x`nCM`nCM y`nCE`nGW 1,$n,0.,0.,9.144,0.,10.18946,9.144,.0010262`nGE 1,-1`nFR 0,1,0,0,14.`nGN 0,0,0,0,20.,.0303,1.,0.`nEX 4,1,$mid,0,1.414214,0.`nPQ 0`nXQ 0`nEN" | Set-Content $deck -Encoding ASCII
  return $mid
}
$engines = @(
  @("momwire bs2",  "$B7\momwire-eznec.exe"),
  @("momwire twin", "$B7\momwire-eznec-razor-nec5.exe"),
  @("licensed NEC5", $LIC)
)
# warm both momwire rooms + their Sommerfeld grid at 14 MHz, so we time solves
Deck 21 | Out-Null
foreach ($e in $engines) { & $e[1] $deck "$rig\cmp.out" 2>&1 | Out-Null; & $e[1] $deck "$rig\cmp.out" 2>&1 | Out-Null }
"{0,7}  {1,>16}  {2,>16}  {3,>16}" -f "segs","momwire bs2","momwire twin","licensed NEC5"
foreach ($n in $Segs) {
  $mid = Deck $n
  $row = @(); $zs = @()
  foreach ($e in $engines) {
    $t = @()
    foreach ($r in 1..$Reps) {
      $sw = [Diagnostics.Stopwatch]::StartNew()
      & $e[1] $deck "$rig\cmp_$($e[0].Split(' ')[1]).out" 2>&1 | Out-Null
      $sw.Stop(); $t += $sw.Elapsed.TotalMilliseconds
    }
    $best = ($t | Measure-Object -Minimum).Minimum
    $row += [math]::Round($best,1)
    $l = Select-String -Path "$rig\cmp_$($e[0].Split(' ')[1]).out" -Pattern "^\s+1\s+$mid\s+1\s" | Select-Object -First 1
    $zs += if ($l) { $p=($l.Line -split '\s+')|Where-Object{$_ -ne ''}; "$($p[7])$($p[8])j" } else { "NO-Z" }
  }
  "{0,7}  {1,16}  {2,16}  {3,16}   Z: {4}" -f $n, $row[0], $row[1], $row[2], ($zs -join ' | ')
}

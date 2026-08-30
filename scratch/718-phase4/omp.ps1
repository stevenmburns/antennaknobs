param([int]$Segs = 1601, [int[]]$Threads = @(1,2,4,8,16), [string]$Places = "")
$P = "C:\Users\smbur\antennas\antennaknobs\scratch\718-phase4"
$B7 = "$P\bundle7\momwire-eznec"; $rig = "$P\rig"
Set-Location $rig
$n = $Segs; $mid = [int](($n+1)/2)
"CM omp`nCM`nCM x`nCM`nCM y`nCE`nGW 1,$n,0.,0.,9.144,0.,10.18946,9.144,.0010262`nGE 1,-1`nFR 0,1,0,0,14.`nGN 0,0,0,0,20.,.0303,1.,0.`nEX 4,1,$mid,0,1.414214,0.`nPQ 0`nXQ 0`nEN" | Set-Content "$rig\omp.nec" -Encoding ASCII
foreach ($t in $Threads) {
  Get-Process -Name momwire-eznec-engine -EA SilentlyContinue | ForEach-Object { Stop-Process -Id $_.Id -Force }
  Start-Sleep -Milliseconds 900
  $env:OMP_NUM_THREADS = "$t"
  if ($Places) { $env:OMP_PLACES = $Places; $env:OMP_PROC_BIND = "close" }
  & "$B7\momwire-eznec.exe" "$rig\omp.nec" "$rig\omp.out" 2>&1 | Out-Null   # cold: spawns daemon with this env
  $d = Get-Process -Name momwire-eznec-engine | Sort-Object StartTime | Select-Object -Last 1
  $c0 = $d.TotalProcessorTime.TotalSeconds
  $sw = [Diagnostics.Stopwatch]::StartNew()
  & "$B7\momwire-eznec.exe" "$rig\omp.nec" "$rig\omp.out" 2>&1 | Out-Null
  $sw.Stop(); $d.Refresh()
  $c = $d.TotalProcessorTime.TotalSeconds - $c0; $w = $sw.Elapsed.TotalSeconds
  "{0,-14} threads={1,3}  wall={2,7:N2} s  cpu={3,7:N2} s  par={4,4:N1}x" -f "segs=$Segs", $t, $w, $c, ($c/$w)
}
Remove-Item Env:\OMP_NUM_THREADS -EA SilentlyContinue
Remove-Item Env:\OMP_PLACES -EA SilentlyContinue
Remove-Item Env:\OMP_PROC_BIND -EA SilentlyContinue

param([int]$Segs = 1601)
$P = "C:\Users\smbur\antennas\antennaknobs\scratch\718-phase4"
$B7 = "$P\bundle7\momwire-eznec"; $rig = "$P\rig"
Set-Location $rig
$n = $Segs; $mid = [int](($n+1)/2)
"CM aff`nCM`nCM x`nCM`nCM y`nCE`nGW 1,$n,0.,0.,9.144,0.,10.18946,9.144,.0010262`nGE 1,-1`nFR 0,1,0,0,14.`nGN 0,0,0,0,20.,.0303,1.,0.`nEX 4,1,$mid,0,1.414214,0.`nPQ 0`nXQ 0`nEN" | Set-Content "$rig\aff.nec" -Encoding ASCII
# On Alder Lake i5-1240P: logical 0-7 = the 4 P-cores (HT pairs), 8-15 = the 8 E-cores.
$cases = @(
  @("4T all cores (free)",   4, $null),
  @("4T P-cores only",       4, [IntPtr]0x55),   # logical 0,2,4,6 -> one thread per P-core
  @("4T P-cores +HT",        4, [IntPtr]0xFF),
  @("4T E-cores only",       4, [IntPtr]0xF00),  # logical 8-11 -> 4 E-cores
  @("8T P-cores +HT",        8, [IntPtr]0xFF),
  @("8T E-cores only",       8, [IntPtr]0xFF00)
)
foreach ($c in $cases) {
  Get-Process -Name momwire-eznec-engine -EA SilentlyContinue | ForEach-Object { Stop-Process -Id $_.Id -Force }
  Start-Sleep -Milliseconds 900
  $env:OMP_NUM_THREADS = "$($c[1])"
  & "$B7\momwire-eznec.exe" "$rig\aff.nec" "$rig\aff.out" 2>&1 | Out-Null
  $d = Get-Process -Name momwire-eznec-engine | Sort-Object StartTime | Select-Object -Last 1
  if ($c[2]) { try { $d.ProcessorAffinity = $c[2] } catch { "  (affinity set failed: $($_.Exception.Message))" } }
  & "$B7\momwire-eznec.exe" "$rig\aff.nec" "$rig\aff.out" 2>&1 | Out-Null   # re-warm under the new mask
  $d.Refresh(); $c0 = $d.TotalProcessorTime.TotalSeconds
  $sw = [Diagnostics.Stopwatch]::StartNew()
  & "$B7\momwire-eznec.exe" "$rig\aff.nec" "$rig\aff.out" 2>&1 | Out-Null
  $sw.Stop(); $d.Refresh()
  $cpu = $d.TotalProcessorTime.TotalSeconds - $c0; $w = $sw.Elapsed.TotalSeconds
  "{0,-22} wall={1,7:N2} s  cpu={2,7:N2} s  par={3,4:N1}x" -f $c[0], $w, $cpu, ($cpu/$w)
}
Remove-Item Env:\OMP_NUM_THREADS -EA SilentlyContinue

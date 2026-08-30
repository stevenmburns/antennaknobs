$log = "C:\Users\smbur\antennas\antennaknobs\scratch\718-phase4\retire.log"
$portal = "$env:LOCALAPPDATA\momwire-portal"
$start = Get-Date
$pids = (Get-Process -Name "momwire-eznec-engine" -ErrorAction SilentlyContinue).Id
"$($start.ToString('HH:mm:ss'))  watch start; engines=[$($pids -join ',')]; ports=[$((Get-ChildItem "$portal\*.port" -EA SilentlyContinue).Name -join ',')]" | Set-Content $log
$seen = @{}
while ($true) {
  Start-Sleep -Seconds 10
  $now = Get-Date
  $alive = (Get-Process -Name "momwire-eznec-engine" -ErrorAction SilentlyContinue).Id
  foreach ($p in $pids) {
    if ($alive -notcontains $p -and -not $seen[$p]) {
      $seen[$p] = $true
      $mins = [math]::Round(($now - $start).TotalMinutes, 2)
      "$($now.ToString('HH:mm:ss'))  pid $p EXITED after $mins min idle" | Add-Content $log
    }
  }
  if ($alive.Count -eq 0) {
    $ports = (Get-ChildItem "$portal\*.port" -EA SilentlyContinue).Name
    $left  = (Get-ChildItem "$portal\*" -EA SilentlyContinue).Name
    "$($now.ToString('HH:mm:ss'))  all engines gone after $([math]::Round(($now-$start).TotalMinutes,2)) min; .port remaining=[$($ports -join ',')]; all files=[$($left -join ',')]" | Add-Content $log
    break
  }
  if (($now - $start).TotalMinutes -gt 25) { "$($now.ToString('HH:mm:ss'))  TIMEOUT at 25 min; still alive=[$($alive -join ',')]" | Add-Content $log; break }
}

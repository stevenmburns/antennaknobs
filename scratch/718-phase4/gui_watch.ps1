# Times each external-engine run EZNEC makes, by watching the output file it rewrites.
# No stopwatch needed: every engine invocation rewrites NEC5.OUT exactly once.
$log = "C:\Users\smbur\antennas\antennaknobs\scratch\718-phase4\gui_runs.log"
$paths = @(
  "C:\EZNEC 7.0\Docs\NEC5.OUT",
  "C:\Users\smbur\antennas\antennaknobs\scratch\718-phase4\bundle7\momwire-eznec\NEC5.OUT"
)
"$(Get-Date -Format 'HH:mm:ss.fff')  watcher armed; watching:`n  $($paths -join "`n  ")" | Set-Content $log
$last = @{}; foreach ($p in $paths) { $last[$p] = if (Test-Path $p) { (Get-Item $p).LastWriteTime } else { [datetime]::MinValue } }
$prevTick = $null; $n = 0
while ($true) {
  foreach ($p in $paths) {
    if (Test-Path $p) {
      $t = (Get-Item $p).LastWriteTime
      if ($t -gt $last[$p]) {
        $last[$p] = $t; $n++
        $now = Get-Date
        $delta = if ($prevTick) { [math]::Round(($now - $prevTick).TotalMilliseconds,1) } else { $null }
        $prevTick = $now
        $engines = (Get-Process -Name momwire-eznec-engine -EA SilentlyContinue).Count
        "$($now.ToString('HH:mm:ss.fff'))  run #$n  delta=$(if($delta){"$delta ms"}else{'(first)'})  engines=$engines  $(Split-Path $p -Parent)" | Add-Content $log
      }
    }
  }
  Start-Sleep -Milliseconds 15
}

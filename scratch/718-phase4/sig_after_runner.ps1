# Waits until the signing leaf has expired, then captures the after-half.
# Detached on purpose: this completes even if the originating session ends.
$exp = [datetime]::Parse("2026-08-31T17:55:02Z").ToUniversalTime()
while ((Get-Date).ToUniversalTime() -lt $exp.AddSeconds(60)) { Start-Sleep -Seconds 30 }
& "C:\Users\smbur\antennas\antennaknobs\scratch\718-phase4\sig_after.ps1" |
  Set-Content "C:\Users\smbur\antennas\antennaknobs\scratch\718-phase4\sig_after_console.txt"

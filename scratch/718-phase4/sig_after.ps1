# Run any time AFTER 2026-08-31 17:55:02 UTC. Verifies the same bytes and
# diffs against sig_before.txt. Status staying Valid on an expired signing
# certificate is the proof that the RFC-3161 countersignature carries it.
$d   = "C:\Users\smbur\antennas\antennaknobs\scratch\718-phase4\release\x\momwire-eznec"
$out = "C:\Users\smbur\antennas\antennaknobs\scratch\718-phase4\sig_after.txt"
$exp = [datetime]::Parse("2026-08-31T17:55:02Z").ToUniversalTime()
$now = (Get-Date).ToUniversalTime()
$a = @()
$a += "SIGNATURE CHECK - AFTER CERTIFICATE EXPIRY"
$a += "captured: " + (Get-Date -Format "yyyy-MM-dd HH:mm:ss K") + "  |  UTC: " + $now.ToString("yyyy-MM-dd HH:mm:ss") + "Z"
if ($now -lt $exp) { $a += "*** TOO EARLY: cert does not expire for another " + [math]::Round(($exp-$now).TotalMinutes,1) + " min - rerun later ***" }
else { $a += "cert expired " + [math]::Round(($now-$exp).TotalHours,2) + " h ago" }
$a += ""
foreach ($n in @("momwire-eznec.exe","momwire-eznec-razor-nec5.exe","momwire-eznec-engine.exe")) {
  $s = Get-AuthenticodeSignature "$d\$n"
  $a += "=== $n ==="
  $a += "SHA256          : " + (Get-FileHash "$d\$n" -Algorithm SHA256).Hash
  $a += "Size            : " + (Get-Item "$d\$n").Length
  $a += "Status          : $($s.Status)"
  $a += "StatusMessage   : $($s.StatusMessage)"
  $a += "SignerNotAfter  : $($s.SignerCertificate.NotAfter)"
  $a += "SignerThumbprint: $($s.SignerCertificate.Thumbprint)"
  $a += "TSA Thumbprint  : $($s.TimeStamperCertificate.Thumbprint)"
  $a += ""
}
$a | Set-Content $out
Get-Content $out
""
"================ BEFORE vs AFTER ================"
"(SHA256 and thumbprints MUST match - same bytes, same certs. Status MUST stay Valid.)"
git diff --no-index --color=never `
  "C:\Users\smbur\antennas\antennaknobs\scratch\718-phase4\sig_before.txt" $out 2>&1 | Select-Object -Skip 4

# Drop-in engine diagnostics (ws4, 2026-08-20)

Three throwaway C# wrappers that established what EZNEC actually requires of a
replacement calculating engine. Kept because they are the evidence behind
momwire#512 and momwire#513, and because each isolates exactly one variable.

Build any of them with the in-box compiler, same as `../build.ps1` uses:

```powershell
& "$env:WINDIR\Microsoft.NET\Framework64\v4.0.30319\csc.exe" `
    /nologo /target:exe /out:"C:\EZNEC 7.0\Docs\<name>.exe" <name>.cs
```

Then point `Options -> Calculating engine -> External NEC5` at the result.

## `slow.cs` — is latency a gate?

Sleeps (default 2000 ms, override with `SLOW_MS`) and then forwards argv to the
real engine. Output is byte-identical to an unwrapped real-engine run, so the
only changed variable is delay.

**Result: EZNEC accepted it.** Latency is not a gate — which is what makes the
client/server shape viable for momwire.

## `logengine.cs` — what does EZNEC actually pass?

Records cwd, the full command line, argv, and which of `EZN5.NEC` / `NEC.IN` /
`NEC5.OUT` / `NEC.OUT` exist before and after, plus the child's stdout, stderr,
exit code and elapsed time, to `Docs\engine_probe.log`. Forwards to
`momwire_real.exe`.

**Result:** EZNEC passes `"EZN5.NEC" "NEC5.OUT"` with cwd `C:\EZNEC 7.0\Docs`.
`NEC.OUT` never exists — so the "Output file NEC.OUT is present, but was written
earlier from another calculation" popup names a file it never looks for, and the
message cannot be taken at face value.

## `crlfengine.cs` — the CRLF proof

Forwards to `momwire_real.exe`, then rewrites the output file converting bare LF
to CRLF. Changes nothing else — same engine, same numbers, same timing.

**Result: EZNEC rendered momwire's results first try.** This is the proof for
momwire#512, and the reason that fix is a single character
(`_shell.py:95`, `newline="\n"` -> `newline="\r\n"`).

## Not included

The frozen engine itself (PyInstaller onedir, ~120 MB) is a build artifact —
rebuild with `momwire==0.35.0` + `pyinstaller` over a four-line entry shim
calling `momwire.eznec.main`. Use **onedir**: onefile re-unpacks 50 MB on every
launch for ~17 s and is unusable.

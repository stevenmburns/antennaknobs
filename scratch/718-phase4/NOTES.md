# momwire#718 phase 4 — EZNEC launch economics, measured on the EZNEC box

Sitting: 2026-08-29, Windows 11 Pro 26200, EZNEC Pro/2+ v7.0.4.
Driven from `WINDOWS-SESSION-6.local.md`.

- antennaknobs `d8c02e9df` → `e707933c6`
- momwire `e5925ff` → `290c685` (exactly the commit the session doc was written against)
- Bundle: run **33281638017**, artifact `momwire-eznec-windows-SELFSIGNED-rehearsal`
- Licensed comparison engine: `C:\EZNEC 7.0\Docs\NEC5CL_x13.exe` (present, untouched)

## Headline — the three-column table (Job A)

Model throughout: `Bydipole1` as EZNEC writes it (`EZN5.NEC`), 11-segment bare
wire dipole over real ground, source at segment 6, no transmission lines — so
per-point cost is launch + solve only. 50 points, 14.000–14.350 MHz, one
process launch per point, exactly as EZNEC steps a sweep.

| | per-launch (median) | per-launch (mean) | 50-point sweep |
|---|---|---|---|
| **launcher** (`momwire-eznec.exe`, phase 3) | **39.8 ms** | 43.0 ms | **2.15 s** |
| **engine-direct** (`momwire-eznec-engine.exe` = old one-shot) | 5322 ms | 5452 ms | **272.6 s** |
| **licensed** (`NEC5CL_x13.exe`) | 22.3 ms | 147 ms | 7.33 s |

Same box, same model, same hour. Two independent launcher sweeps agreed:
2.47 s / 2.34 s wall (2.15 s / 2.17 s summed per-point).

**The phase-3 delta is 127x** on the sweep (272.6 s to 2.15 s), and that is
measured against the engine run directly, which *is* the old behaviour — not
against a remembered number.

Three things the table says that the plan did not predict:

1. **The old economics were far worse than the ~45 s on record.** A one-shot
   frozen engine costs ~5.3 s per point here, not ~0.9 s. The 50-point sweep
   was **4 minutes 33 seconds**, not 45 s. Confirmed against the *actual*
   phase-2 bundle still in `~/Downloads` (self-contained 9.6 MB launchers):
   5335 / 5267 ms steady-state, i.e. engine-direct reproduces the old
   one-shot faithfully.
2. **The launcher beats the licensed native engine on a sweep** — 2.15 s vs
   7.33 s — despite a higher *median* per launch (39.8 vs 22.3 ms). The
   licensed engine pays full process start every point and is erratic
   (min 13.2 ms, max 499.7 ms); the warm launcher is tightly bounded
   (min 32.8 ms, max 64.8 ms). Predictability, not raw speed, wins the sweep.
3. **Warm launch landed at ~40 ms, above the 18–37 ms CI window.** CI measured
   24 ms on windows-latest. Real box, real EZNEC deck: 33–65 ms, median 40.
   The twin is faster than the default (21–25 ms steady) — see Job B.

Cold first calc: **5.3 s**, not the predicted 0.6–1 s. That is the engine's
own frozen start-up (numpy/scipy import out of a PyInstaller onedir), paid
once per formulation per 15-minute idle window.

## The finding that matters most — the bundle ships without its accelerator

`momwire-eznec-engine.exe` prints, on every start:

> RuntimeWarning: momwire: the compiled accelerator '_accelerators' is
> installed but failed to import (ImportError('DLL load failed while importing
> _accelerators: The specified module could not be found.')); falling back to
> the slower pure-Python path.

Diagnosed, not guessed. Both extensions in the bundle
(`_accelerators.cp312-win_amd64.pyd`, `_near_interface_accel.cp312-win_amd64.pyd`)
import **`libomp140.x86_64.dll`** — LLVM's OpenMP runtime, i.e. they are built
with clang-cl, not MSVC. PyInstaller does not collect it, and it is **not** a
Windows system DLL: the only copy anywhere on this machine is inside
Autodesk Fusion's bundled ngspice. `vcomp140.dll` (the *MSVC* OpenMP runtime,
which is present in System32) is a different library and does not satisfy it.

So on any machine without the LLVM redistributable — which is the ordinary
case — **the shipped engine does every solve in pure Python.**

Two further notes on it:

- **This predates phase 3.** The phase-2 bundle in `~/Downloads` fails
  identically. It is a long-standing packaging gap the launcher work exposed,
  not a regression introduced by the split.
- **The diagnostic text is wrong for the platform it printed on.** The advice
  is entirely Linux (`apt install libgomp1`, `GLIBC_TUNABLES=...`) on a Windows
  bundle whose actual missing file is `libomp140.x86_64.dll`. Anyone hitting
  this on Windows is sent somewhere useless.

Impact on *this* table is small — an 11-segment dipole solves fast even in
pure Python, and launch cost dominates — so the launch economics above stand.
It would not stay small on a real model.

`momwire-eznec-razor-nec5` does **not** emit the warning (its `.port.log` is
empty), so the twin's path does not touch the failing extension.

## Job B — the twin answers, and matches

Same deck, 14 MHz, source impedance from `ANTENNA INPUT PARAMETERS`:

| engine | Z (ohms) |
|---|---|
| default `momwire-eznec` (bs2) | 75.033 − 43.681j |
| `momwire-eznec-razor-nec5` (twin) | 72.378 − 58.547j |
| licensed `NEC5CL_x13` | 72.380 − 58.548j |

The twin answers (does not refuse), **differs from the default**, and matches
the licensed engine to **0.002 ohm real / 0.001 ohm imaginary** — inside the
0.003–0.007 ohm the bundle README claims. Job B passes on every clause.

Cross-check on the default: the launcher and the engine run directly returned
bit-identical impedance at both band edges across the 50-point sweeps
(75.033 − 43.681j at 14.000, 79.068 − 8.5099j at 14.350). The resident path
changes the cost, not the answer.

## Job C — residency hygiene

- **One engine per formulation, as designed.** After only the default had run:
  exactly one `momwire-eznec-engine.exe`. After the twin ran: exactly two
  (pids 20360, 27360) — one per basis, never more, across ~330 launches.
- **Portal room is correct.** `%LOCALAPPDATA%\momwire-portal\` held one
  `<16hex>.lock` / `.port` / `.port.log` triple per warm engine
  (`fef1f72685bd3a07` = default, `8b4febcffe88aa5d` = twin), and each log's
  `listening pid=` line matched the live process.
- **Idle-retire:** measured; see below.

## The intermittent fallback — worth a look before this ships

The **first** launcher sweep ran 22.88 s, not 2.4 s. The engine never died
(same pid throughout, one room), so this was not a respawn: 4 launches out of
50 took 3.7–6.0 s each, i.e. the launcher silently took the **one-shot
fallback ladder** while a perfectly good warm engine was listening. 46 of 50
were normal (57 ms mean). Those 4 fallbacks were essentially the entire 20 s.

It did not reproduce: two repeat sweeps and 120 back-to-back launches
(constant deck and per-point-varying deck) gave **zero** fallbacks. At an 8%
rate, 0/120 would be a 4e-5 coincidence, so the condition was real and
transient — it occurred only in the first minutes of the bundle's life, which
points at Defender scanning the freshly unzipped `_internal` tree and pushing
a connect past its timeout.

Worth flagging because of *how* it fails: correct answers, no warning, no log
line — the daemon's `.port.log` recorded nothing — just a 5-second stall.
That is exactly the "ladder hides problems as slowness" shape the session doc
warns about, and a user's first sweep is precisely when they will meet it.

## Job D — observations, not verdicts

- **No Defender or SmartScreen prompt appeared** for any of the three exes —
  no dialog, no quarantine, no block, despite the self-signed (untrusted-root)
  signature. Nothing needed unblocking. Recorded as data; the Smart App
  Control verdict is a separate sitting on the signed zip.
- **First execution of the phase-2 bundle cost 58 s** (vs 5.3 s steady) — the
  scan-on-first-run tax, on a 9.6 MB self-contained exe. The phase-3 split
  pays it once on the 9.7 MB engine instead of on every launcher, which is a
  real second-order win for the split that the plan did not claim.
- **Cold spawn does read as a hang.** 5.3 s with EZNEC showing nothing is long
  enough to look wedged on a first calculation, and it recurs after every
  15-minute idle gap, not just at startup.
- **Launcher size is ~180 KB, not the ~31 KB the plan states** (184,832 bytes
  for both `momwire-eznec.exe` and `momwire-eznec-razor-nec5.exe`). Harmless,
  but the figure in the phase-3 write-up is stale.

## Reproducing

`sweep.ps1` (50-point sweep, any engine) and `stress.ps1` (back-to-back launch
stress, constant or varying deck) are beside this file. Per-point CSVs with
frequency, wall time and R/X are in `data/`. The bundle and working directory
are gitignored — refetch the artifact to re-run.

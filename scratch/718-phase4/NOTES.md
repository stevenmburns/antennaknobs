# momwire#718 phase 4 — EZNEC launch economics, measured on the EZNEC box

Sitting: 2026-08-29, Windows 11 Pro 26200, EZNEC Pro/2+ v7.0.4.
Driven from `WINDOWS-SESSION-6.local.md`.

- antennaknobs `d8c02e9df` → `e707933c6`
- momwire `e5925ff` → `290c685` (exactly the commit the session doc was written against)
- Bundle: run **33281638017**, artifact `momwire-eznec-windows-SELFSIGNED-rehearsal`
- Licensed comparison engine: `C:\EZNEC 7.0\Docs\NEC5CL_x13.exe` (present, untouched)

## What was and was not done — read this before trusting the numbers

**The EZNEC GUI was never driven.** This session has no way to click in a
Win32 app, so Job 0 step 4 (`Options → Calculating engine → External`) and the
"click Src Dat N times" framing of Job A were not performed as written, and
`LastRun.log` carries no new entries from this sitting.

Instead every number below was taken by invoking the engines **exactly as
EZNEC invokes them**, which the box itself told us: `LastRun.log` shows
`Running ext engine <path>`, and the phase-2 bundle left behind the
`EZN5.NEC` / `NEC5.OUT` pair proving the contract is
`<engine>.exe <deck-in> <output-out>`, one process per frequency point. The
sweeps therefore reproduce EZNEC's actual cost model — a fresh process launch
per point on a deck EZNEC wrote — and are more precise and repeatable than a
stopwatch over clicks. What they cannot capture is anything EZNEC does *around*
the engine (its own file handling and redraw per point), so treat the sweep
totals as the engine-side cost, which is what phase 3 changed.

Two consequences: the "does the cold spawn read as a hang" question in Job D
is answered from the measured 5 s stall rather than from watching EZNEC's
window, and the SmartScreen/Defender observations come from launching the exes
directly, not from EZNEC launching them. If a real-GUI confirmation matters
before the economics claims go into the site, that is a short follow-up for a
human at the keyboard — the engine path is already proven correct by the
cross-era check in Job B.

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

`momwire-eznec-razor-nec5` does **not** emit the warning (its `.port.log` is
empty), so the twin's path does not touch the failing extension.

### Confirmed by experiment, and priced

Dropping that one 699 KB file into `_internal\` makes the warning disappear
and the accelerator load. Removing it brings the warning straight back. That
is the whole fix — one file.

What it costs, measured both ways on the same box. Every timed run uses a
**different frequency**, so no run repeats a deck and none of this is a cache
hit; the per-run impedances differ, which is the receipt:

| model | as shipped | with `libomp140` | cost of the gap |
|---|---|---|---|
| 11-seg dipole, 50-pt sweep | 2.15 s (39.8 ms/pt) | **1.65 s (26.7 ms/pt)** | 1.3x |
| 101-seg dipole, single solve | 459 ms | 79 ms | ~5.8x |
| 201-seg dipole, single solve | 1666 ms | 107 ms | 15.6x |
| 401-seg dipole, single solve | 5777 ms | 277 ms | **20.8x** |

Two consequences worth carrying into the write-up:

- **The doc's ~1.5 s sweep target was right — for a bundle with its
  accelerator.** As shipped it is 2.15 s. With `libomp140` present it is
  1.65 s. The target was not wrong; the bundle is missing a file.
- **On anything bigger than a toy the gap dominates everything else this
  phase bought.** Phase 3 took 5.3 s of launch overhead off each point; the
  missing DLL puts 5.5 s of *solve* back on at 401 segments. A user modelling
  a real antenna would see the launcher work perfectly and the calculation
  still crawl.

Answers are identical either way (bit-identical Z at every mesh and frequency
tried), so this is purely a speed defect — which is exactly why it shipped.

### Why CI did not catch it

`scripts/eznec_freeze/smoke.py` has no gate asserting the accelerator is
live — nothing greps for the fallback warning or checks
`momwire._accelerators` imported. The GitHub Windows runner has Visual Studio
installed, so `libomp140.x86_64.dll` resolves there and the frozen engine
behaves. The gap only appears on a machine without VS, which is every user.

Suggested fix, in order of value: (1) a smoke gate that fails the build if the
frozen engine emits the fallback warning; (2) collect
`libomp140.x86_64.dll` into the bundle in `scripts/eznec_freeze/build.py`
(it ships with MSVC under `VC\Redist\MSVC\<ver>\x64\Microsoft.VC143.OpenMP.LLVM\`);
(3) make the warning's advice platform-aware — it currently offers Linux
remedies for a Windows failure.

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

**Job B step 2 — the cross-era spot-check, and it is a real one.** The
phase-2 bundle in `~/Downloads` still holds the `EZN5.NEC` that *real EZNEC
wrote* on 2026-08-28 (same dipole at 15 MHz) together with the `NEC5.OUT` the
frozen one-shot produced from it. Running that exact deck through today's
phase-3 launcher:

| | R (ohms) | X (ohms) |
|---|---|---|
| phase-2 frozen one-shot, 2026-08-28 | 8.7091E+01 | 5.7731E+01 |
| phase-3 launcher, 2026-08-29 | 8.7091E+01 | 5.7731E+01 |

Delta zero in both parts — bit-identical across the whole launcher/engine
rearchitecture, on a deck this box's EZNEC generated. That is the strongest
correctness evidence in the sitting, because nothing about it was constructed
by me.

## Job C — residency hygiene

- **One engine per formulation, as designed.** After only the default had run:
  exactly one `momwire-eznec-engine.exe`. After the twin ran: exactly two
  (pids 20360, 27360) — one per basis, never more, across ~330 launches.
- **Portal room is correct.** `%LOCALAPPDATA%\momwire-portal\` held one
  `<16hex>.lock` / `.port` / `.port.log` triple per warm engine
  (`fef1f72685bd3a07` = default, `8b4febcffe88aa5d` = twin), and each log's
  `listening pid=` line matched the live process.
- **Idle-retire works, and says so.** Left alone, both engines exited on their
  own: pid 20360 at 14.0 min, pid 27360 at 14.5 min (measured from a watcher
  started just after the last launch, so ~15 min of true idle each). Each
  daemon logged its own reason —

      2026-08-29T18:00:32 idle 900s; exiting
      2026-08-29T18:00:32 stopped after 287 connection(s)

  Both `.port` files were gone afterwards, as specified. The `.lock` and
  `.port.log` files **remain** — harmless, and the log is what makes the
  retirement auditable, but the plan predicted only that `.port` would go, so
  note that the room directory is not left empty.
- **The next click pays cold exactly once**, as designed: 4.94 s for the first
  calculation after retirement, then 35–57 ms again on a freshly spawned
  engine. No manual cleanup was needed anywhere in the sitting.
- **Nothing left running.** Engines killed at the end; `momwire-eznec-engine.exe`
  absent from the process list.

## The intermittent stall — worth a look before this ships

The **first** launcher sweep ran 22.88 s, not 2.4 s. 4 launches out of 50 took
3.7–6.0 s each; the other 46 were normal (57 ms mean), and those 4 were
essentially the entire 20 s.

It was **not** a fallback to the one-shot ladder, and not a respawn. The
engine held the same pid throughout with one room, and on retirement its log
read `stopped after 287 connection(s)` — exactly the number of default-launcher
invocations made in the whole sitting (1 + 10 + 5 + 50 + 60 + 60 + 50 + 50 + 1).
Every launch reached the daemon and opened a connection, the four slow ones
included. So the resident path was working; it just took ~5 s to answer.
(The log cannot separate "served slowly" from "served, failed, retried" — both
would count one connection — but it rules out the launcher never getting
there, which is what a ladder fallback would look like.)

It did not reproduce: two repeat sweeps and 120 back-to-back launches
(constant deck and per-point-varying deck) gave **zero** stalls. At an 8%
rate, 0/120 would be a 4e-5 coincidence, so the condition was real and
transient — it occurred only in the first minutes of the bundle's life, which
points at Defender scanning the freshly unzipped `_internal` tree.

Worth flagging because of *how* it fails: correct answers, no warning, no log
line — the daemon's `.port.log` recorded nothing about these — just a
5-second stall. That is the "hides problems as slowness" shape the session doc
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

Beside this file:

- `sweep.ps1` — 50-point sweep against any engine, one launch per point,
  writing a fresh deck at each frequency.
- `stress.ps1` — back-to-back launch stress, constant or per-launch-varying
  deck, reporting the stall rate.
- `dense.ps1` / `dense_vary.ps1` — single-solve timing at a chosen segment
  count; `dense_vary` gives every timed run its own frequency, which is the
  cache control.
- `retire_watch.ps1` — polls for engine exit and records the idle-retire time.

Per-point CSVs (frequency, wall time, R, X) are in `data/`. The bundle, the
working directory and the staged `libomp140.x86_64.dll` are gitignored —
refetch the artifact to re-run.

**Method note.** No measurement here repeats a deck: every sweep point and
every timed dense run changes the frequency, so nothing can be served from a
cached solution. The one place identical decks were reused (`dense.ps1`) was
re-run through `dense_vary.ps1` with distinct frequencies as a control and
agreed within noise (401 segments: 5726/5723/5773 ms repeated vs
5705/5846/5780 ms distinct), so the engine is not caching results.

**State of the box at hand-back.** The bundle is back exactly as CI produced
it — the `libomp140.x86_64.dll` used for the experiment was removed and the
fallback warning verified to return. No engine processes are left running.
EZNEC's own configuration was never touched (see the scope note at the top),
and `NEC5CL_x13.exe` was read-only throughout — invoked for the comparison
column, never modified.

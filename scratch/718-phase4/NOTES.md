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

---

# Sitting 7 — the accelerated re-measure (2026-08-30)

Driven from `WINDOWS-SESSION-7.local.md`. Same box, same model, same harness
as sitting 6, so every column below is comparable to the ones above.

- antennaknobs `85b151dcf` (sitting 6's PR #1039 merged), momwire `dbf66a7`
- Bundle: run **33288451391**, unzipped **fresh** into `bundle7/` — the first
  build carrying its own OpenMP runtime (momwire#737, fixed in PR #739)
- Sitting 6's leftover hand-staged `libomp140.x86_64.dll` was **deleted**
  before any measurement, so nothing here can be contaminated by it

Same scope limit as sitting 6: **the EZNEC GUI was still not driven.** Engines
were invoked exactly as EZNEC invokes them. The one GUI-driven sweep remains
the open box on AK#1039's test plan.

## Job A — gate 7 confirmed in the field

One launcher solve into a private room (`MOMWIRE_PORTAL_RUNTIME_DIR`), then
the daemon's own log:

    accelerators: loaded (_accelerators, _near_interface_accel)
    openmp runtime: ...\bundle7\momwire-eznec\_internal\libomp140.x86_64.dll

Both required lines present, and the runtime path resolves **inside the
bundle** — not System32. The box does still have no system `libomp140`, so
this is the strong form of the test: the bundle is genuinely self-contained.
No fallback warning appears anywhere, in any room, for the whole sitting.

The shipped DLL is 661,856 bytes (the MSVC redistributable copy) — a
different build from the 698,944-byte one borrowed from Autodesk's ngspice in
sitting 6. Worth knowing when comparing the two sittings' solve times.

## Job B — the honest economics

50 points, 14.000–14.350 MHz, 11-segment dipole over real ground, one process
launch per point. All three columns measured today on the accelerated bundle:

| | per-launch (median) | 50-point sweep |
|---|---|---|
| **launcher**, warm resident | **22.3 ms** | **1.18 s** |
| **engine-direct** (the old one-shot) | 2060 ms | **103.2 s** |
| **licensed** `NEC5CL_x13` | 22.6 ms | 6.93 s |

Three warm launcher sweeps: 1.18 / 1.19 / 1.53 s. The engine-direct column is
measured over all 50 points, not extrapolated.

- **The phase-3 delta, both engines accelerated, is 87x** (103.2 s -> 1.18 s).
  Sitting 6's 127x compared two *pure-Python* engines; this is the honest
  like-for-like number now that both halves are fast, and it is the one for
  the site.
- **The shipped bundle beats sitting 6's hand-patched result.** Sitting 6
  measured 1.65 s with the DLL added by hand; shipped it is **1.18 s** at
  22.3 ms/point, better than the plan's ~33 ms/pt expectation.
- **The launcher now ties the licensed engine per launch and beats it 5.9x on
  the sweep** (22.3 vs 22.6 ms median; 1.18 s vs 6.93 s). Same story as
  sitting 6 and now for a better reason: it is bounded (max 39 ms) where
  process-per-point is erratic (max 457 ms).

### Dense decks — the accelerator recovery

Via `dense.ps1` / `dense_vary.ps1`; `dense_vary` gives every timed run its own
frequency, which is the cache control.

| model | sitting 6, as shipped (pure Python) | sitting 7, shipped accelerated | recovery |
|---|---|---|---|
| 201-seg, repeated deck | 1666 ms | 184 ms | 9.1x |
| 401-seg, repeated deck | 5741 ms | 372 ms | 15.4x |
| 201-seg, distinct freqs | — | 219 ms | — |
| 401-seg, distinct freqs | 5777 ms | 376 / 428 ms | ~14x |

The predicted 15.6x/20.8x recovery is met at 201 and approached at 401.

**One honest discrepancy.** Sitting 6's *hand-patched* 401-segment figure was
277 ms; today's shipped bundle gives 376–428 ms across two runs — about 1.4x
slower. Both are internally consistent and the answers are identical, so this
is not a correctness issue. The candidates are the different `libomp` build
(see Job A) and machine state; it was not chased further. Quote the shipped
number, 376–428 ms, since that is what users get.

## Job C — momwire#738 is not a defect, and here is what it actually is

**The stalls reproduced, and they are deterministic.** The first 50-launch
sweep on the fresh accelerated bundle stalled at sweep indices **9, 29, 43 and
49** — *exactly* the four indices sitting 6 saw, on a different bundle, a
different day, pure-Python versus accelerated. That immediately kills the
Defender/first-touch theory the last two write-ups (mine included) leaned on:
scanning does not pick the same four indices three times.

The magnitudes track the accelerator, which says the cost is compute:

| index | sitting 6 (pure Python) | sitting 7 (accelerated) |
|---|---|---|
| 9 | 4008 ms | 907 ms |
| 29 | 3762 ms | 836 ms |
| 43 | 5952 ms | 998 ms |
| 49 | 5613 ms | 894 ms |

Ratio ~4.4-6.3x, i.e. the accelerator's own ratio.

**Cause: Sommerfeld ground-grid fills, one per frequency ladder rung.** Three
experiments, each on a freshly killed daemon:

| condition | stalls |
|---|---|
| real ground, 14.00–14.35 (2.5% span) | i = 9, 29, 43, 49 |
| **free space**, same band | **none** |
| real ground, **14.00–14.01** (0.07% span) | **none** |
| same sweep, **warm** daemon | **none** |

Ground-dependent, span-dependent, cold-daemon-only. That is precisely the
cache described in momwire's own source at `src/momwire/_sommerfeld.py`
L117-137, "Frequency-axis grid reuse (issue #159, phase 2)": the normalized
master grid is keyed on `Im(eps_t)` quantized onto a geometric ladder
(`_SOMM_EPS_IM_BUCKET`, default 0.01), so a band sweep costs one fill per rung
crossed instead of one per frequency. The comment even predicts the count —
*"a 3%-span sweep: 21 fills -> ~4"*. Our span is 2.5% and we measure exactly 4.

Proved causally with the documented override:

| `MOMWIRE_SOMM_EPS_IM_BUCKET` | stalls in the same sweep |
|---|---|
| 0.20 (coarse) | 1 |
| 0.01 (default) | 4 |
| 0.002 (fine) | 13 |

The stall count moves with the ladder step exactly as the design says it
should. **#738 should close as working-as-designed** — it is cold-cache grid
fill, not a portal, launcher or residency defect.

**And it is an argument *for* residency, not against it.** A one-shot engine
has no cache to carry, so it refills on every point. Measured on the same
deck: one-shot with real ground **2023 ms/pt** vs free space **1321 ms/pt** —
about 700 ms of ground fill on *every* launch. The resident daemon pays that
four times for a whole sweep. That is a second, independent win from phase 3
that the plan never claimed.

Practical consequence worth a line on the site: a user's **first** sweep over
a band with real ground pays roughly 4 x 0.9 s of grid fill; every later sweep
in the same session is clean. It is not a hang and it is not per-point.

## Job D — observations

- **Exactly one `momwire-eznec-engine.exe` while warm**, throughout. None left
  at hand-back.
- **No Defender detections in the last 24 hours**, no quarantine, no prompt,
  and no scan-delay resembling sitting 6's 58 s first-run tax on the phase-2
  bundle.
- **SmartScreen was never actually exercised — do not read this as a pass.**
  None of the three exes carries a `Zone.Identifier` stream: `gh run download`
  plus a command-line unzip do not apply Mark-of-the-Web, and SmartScreen keys
  off exactly that. A user who downloads the zip in a browser gets MOTW and
  may well see a prompt this sitting could not provoke. The same caveat
  applies retroactively to sitting 6's "no prompt appeared" note. **The SAC
  sitting must fetch the signed zip through a browser** (or apply MOTW by
  hand) or it will measure nothing.
- Cold spawn on the fresh bundle was 8.1 s, versus 5.3 s in sitting 6 —
  first-touch of a newly unzipped `_internal` tree. It settles immediately.
- Launchers remain 184,832 bytes; the plan's "~31 KB" is still stale.

## What sitting 7 did not do

- No GUI-driven EZNEC sweep (Steve remote). Still the open box on AK#1039.
- Idle-retire was not re-measured; sitting 6 established it (14.0/14.5 min,
  `idle 900s; exiting`) and nothing in this bundle touches that path.
- `NEC5CL_x13.exe` invoked read-only for the third column, never modified.

## Sitting 7 addendum — scaling to bigger designs, and where the threads go

The box: **Intel i5-1240P**, 12 physical cores (4 performance + 8 efficiency),
16 logical, 15.6 GB RAM, 1.7 GHz base. A hybrid laptop part, which turns out
to matter a lot below.

Method: the Bydipole1 geometry with the segment count scaled up, 14 MHz, real
ground, warm resident daemon, best of 2. Frequency is held fixed while N
varies, so the Sommerfeld grid is filled once and what is timed is the solve.

### momwire against the licensed engine, as the design grows

Wall time, ms:

| segments | momwire bs2 | momwire twin (razor) | licensed `NEC5CL_x13` | bs2 vs licensed |
|---|---|---|---|---|
| 101 | 75 | 140 | **39** | 0.52x |
| 401 | 349 | 1,355 | **309** | 0.89x |
| 801 | **690** | 5,501 | 1,327 | **1.92x** |
| 1601 | **2,484** | 20,332 | 5,603 | **2.26x** |
| 3201 | **9,810** | 117,440 | 25,320 | **2.58x** |
| 6401 | **59,590** | not run | 111,220 | **1.87x** |

**The crossover is around 400-500 segments.** Below it the licensed Fortran
wins on raw efficiency; above it momwire's parallel fill pulls ahead and the
lead grows to ~2.6x by 3201.

The reason is simple and worth stating plainly: **the licensed engine is
single-threaded.** Measured directly at 3201 segments, `NEC5CL_x13` used
24.94 s of CPU in 25.32 s of wall — 1.0x. momwire's daemon on the same deck
ran at 7.4x. Per core the Fortran is far more efficient (momwire spends
92.6 s of CPU to the licensed engine's 24.9 s for the same answer); momwire
wins on wall-clock purely by spending more cores.

The 6401 row breaks the trend (1.87x, down from 2.58x). Peak working set
there is well into multiple GB, so this is likely memory pressure on a
15.6 GB box rather than anything about the algorithm. Not chased.

Accuracy across the range is unchanged: the twin tracks the licensed engine
to ~1e-3 ohm at every size (at 1601, 73.828 - 41.380j vs 73.828 - 41.393j).

### How many threads actually help

`OMP_NUM_THREADS` swept at 1601 segments, bs2:

| threads | wall | CPU | speedup | efficiency |
|---|---|---|---|---|
| 1 | 10.07 s | 9.81 s | 1.00x | 100% |
| 2 | 5.04 s | 8.67 s | 2.00x | 100% |
| **4** | **3.19 s** | **8.88 s** | **3.16x** | **79%** |
| 6 | 3.06 s | 11.36 s | 3.29x | 55% |
| 8 | 2.89 s | 13.97 s | 3.48x | 44% |
| 12 | 2.66 s | 16.86 s | 3.79x | 32% |
| 16 | 2.95 s | 25.00 s | 3.41x | 21% |

**Speedup saturates just under 4x**, and 16 threads is *slower* than 12 while
burning 2.8x the CPU of the 4-thread run. By Amdahl a ~3.8x ceiling implies
roughly a quarter of the work is still serial — worth knowing before anyone
optimizes for more cores.

Practical reading: **4 threads is the efficiency knee.** It gives 3.16x for
essentially the single-thread CPU budget; everything past it buys single-digit
percentages of wall time for multiples of the energy. On a laptop that is the
difference between a warm fan and a hot one.

### Yes, you can pin the cores — and it helps

Windows process affinity on the daemon (`$proc.ProcessorAffinity`) works
fine. On this part logical 0-7 are the four P-cores with hyperthreading and
8-15 are the eight E-cores. At 1601 segments:

| configuration | mask | wall | CPU |
|---|---|---|---|
| 4 threads, free | — | 3.28 s | 9.17 s |
| **4 threads, one per P-core** | `0x55` | **3.09 s** | **8.56 s** |
| 4 threads, P-cores + HT | `0xFF` | 3.34 s | 9.50 s |
| 4 threads, E-cores only | `0xF00` | 6.78 s | 20.89 s |
| 8 threads, P-cores + HT | `0xFF` | 3.22 s | 15.59 s |
| 8 threads, E-cores only | `0xFF00` | 4.48 s | 22.08 s |

- **E-cores are ~2.2x slower per core** (6.78 s vs 3.09 s for the same four
  threads). Letting OpenMP scatter work onto them is why the free-threaded
  runs are erratic.
- **Hyperthread siblings contend**: four threads spread one-per-P-core beats
  four threads on `0xFF` where two may land on the same physical core.
- Best overall config measured: **4 threads pinned to the four P-cores** —
  3.09 s at 8.56 s of CPU, versus the default 16-thread run's 2.95 s at
  25.00 s. Five percent slower for a third of the energy.

`OMP_PLACES` / `OMP_PROC_BIND` are also available (this is LLVM's libomp), but
the affinity mask is the blunt instrument that definitely works and needs no
cooperation from the engine.

### Why the twin is slow — filed as momwire#742

The twin's problem is not that it computes more. At 1601 segments razor burns
29.6 s of CPU to bs2's 19.4 s — comparable work — but takes 20.45 s of wall
to bs2's 2.56 s. The difference is entirely parallelism: **bs2 runs at 7.6x,
razor at 1.4x.**

Threads do nothing for it: razor at `OMP_NUM_THREADS=1` is 22.41 s (1.0x) and
at 16 is 19.90 s (1.4x) — 11% for sixteen times the threads. The residual is
BLAS inside the LU solve; the fill is flat serial. And the fill is what
dominates: razor scales 4.06x then 3.70x per doubling of N, i.e. O(N^2).

**There is no razor kernel to add pragmas to.** `setup.py` builds
`_accel_bspline`, `_accel_sinusoidal`, `_accel_somm` and `_accel_mw568`; there
is no `_accel_razor.cpp`, and `razor.py` never imports `._accel` — where
`bspline.py` dispatches to `_acc.assemble_Z_bspline*` throughout.

The memory numbers say the fix is not just threading, it is the temporaries:

| basis | segments | peak working set | Z-matrix alone |
|---|---|---|---|
| bs2 | 1601 | 808 MB | 39 MB |
| razor | 1601 | **2,110 MB** | 39 MB |
| bs2 | 3201 | 2,979 MB | 156 MB |
| razor | 3201 | **8,067 MB** | 156 MB |

At 3201 segments razor materializes **52x the size of the matrix it is
building** and takes over half the machine's RAM. `_seg_moments_from_prepared`
allocates full `(n_obs, n_seg)` complex128 `M0`/`M1` planes (razor.py
L1844-1845) and folds them with `np.einsum` (L1875-1877); the chunk loops at
L2391/L2693 block the work but are sized for convenience, not for cache.

So a thread pool over the existing chunks would hit memory bandwidth almost
immediately. Tiling the fill for cache residency first, then parallelizing
over tiles, is the order that matters — details and targets in momwire#742.

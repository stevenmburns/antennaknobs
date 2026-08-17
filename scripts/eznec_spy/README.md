# EZNEC → NEC-5 capture harness (momwire#390)

Black-box capture of the interface EZNEC Pro+ v7 speaks to its external NEC-5
engine, to answer the issue's headline question — **when a model contains
transmission lines or networks, does EZNEC emit `TL`/`NT` cards into the deck, or
keep lines/networks in its own code and send NEC-5 bare wires?** — and to price a
momwire NEC-5-dialect drop-in.

I/O observation only. Nothing here inspects or modifies the engine binary; the
shim logs what crosses the process boundary and delegates. Same courtesy stance as
the SimNEC studies.

## Files

| file | role |
| --- | --- |
| `Nec5Spy.cs` | the shim: logs argv/cwd/stdin/stdout/stderr + pre/post file snapshots, then delegates |
| `build.ps1` | compiles it with the in-box .NET Framework `csc.exe` (nothing to install) |
| `install.ps1` | renames the real engine to `*.real.exe`, drops the shim at the exact launch path |
| `uninstall.ps1` | restores the real engine and hash-verifies it |
| `index_captures.py` | walks the corpus, tabulates the card vocabulary, emits the TL/NT verdict |
| `installed.tsv` | provenance of the current install (written by `install.ps1`) |

Captures land in `scratch/eznec-capture/` (override with `EZNEC_SPY_ROOT`).

## What is already established

**Host layout.** EZNEC Pro+ v7.0.4 program dir is `C:\Program Files (x86)\EZNEC 7.0`
(`EZWpro2+.exe`, 32-bit); its data dir is `C:\EZNEC 7.0`. The engine lives at
`C:\EZNEC 7.0\Docs\NEC5CL_x13.exe` and `LastRun.log` records each launch as
`Running ext engine C:\EZNEC 7.0\Docs\NEC5CL_x13.exe`. The deck goes to
`C:\EZNEC 7.0\Docs\EZN5.NEC`, the printout comes back as `NEC5.OUT`, and
`SOMMPD.NEX` (737 KB) is the Sommerfeld table.

**Invocation.** The engine takes **two positional command-line arguments** —
input deck, then output file — verified directly:

```
NEC5CL_x13.exe test.nec test.out   ->  exit 0, "Fill complete, FMHZ=  7.1500E+00", 66 KB printout
NEC5CL_x13.exe test.nec            ->  exit 0, "ERROR getting output file from command line"
NEC5CL_x13.exe -i x -o y           ->  exit 0, "GETIOF: ERROR - UNABLE TO OPEN FILE -i"
```

With no arguments it falls back to prompting `Enter INPUT file name (or RETURN) >`
— but it reads that from **`CONIN$`, the console device, not stdin**, so a piped
answer is ignored and the engine dies `forrtl: severe (24): end-of-file`. Two
consequences: EZNEC must be using the argv form (the shim capture will confirm),
and a momwire drop-in only has to implement argv — not the prompt loop.

Note the error paths **exit 0**. A drop-in that signals refusals through the exit
code would be signalling into a channel EZNEC has no reason to read; the SimNEC
`NEC ERROR` precedent (antennaknobs#829) is the shape to look at instead.

**The verdict is in — see `docs/status/2026-08-16-eznec-nec5-dialect-capture.md`.**
TL/NT ride the deck: `4sqtl` emits `TL` ×6, the Cardioid L-network model emits
`TL` ×2 + `NT` ×1, NEC-5 solves the network (`NETWORK DATA` + network connection
points in the printout), and EZNEC's Src Dat matches the printout's feedpoint Z to
4 figures — so EZNEC does no post-processing. The corpus loop below still matters
for the **card vocabulary**, which is what prices the NEC-5 dialect front-end for
its other consumers.

Confirmed invocation, from capture `0001`:
`"…\NEC5CL_x13.exe" "EZN5.NEC" "NEC5.OUT"`, cwd `C:\EZNEC 7.0\Docs`, stdin unused,
exit 0. One launch per calculation, file-based and one-shot — not resident.

**The deck that started it.** A deck left in `Docs\EZN5.NEC` from a
2026-08-16 15:37 session — `Cardioid - L Network Feed`, preserved as capture
`0000_preexisting-*` — carries `TL` ×2 and `NT` ×1. It also shows EZNEC's
anchoring idiom: a third wire, commented `! *Wire #3 for virtual segments.`,
parked ~4.2 km out at `GW 3,3,4192.901,...`, whose segments are the far terminals
the `TL`/`NT` cards address. That is one deck from one model, which is why the
corpus loop below still has to run — but it is already evidence that lines and
networks ride the deck rather than being solved inside EZNEC.

**Dialect semantics worth carrying into a front-end.** W7EL's own
`Network connection test.txt` documents NEC-5's rule that an inserted object
(source/load) is not *at* a junction but *on a wire right next to* it, with the
"favored" wire named by the object's position declaration — two nominally parallel
loads at one junction go series if declared on different wires. That is the
semantics momwire's knot-addressed `node_gaps` has to match.

## The capture loop

1. **Install** (EZNEC must be closed; the script refuses otherwise):

   ```powershell
   pwsh scripts/eznec_spy/build.ps1
   pwsh scripts/eznec_spy/install.ps1
   ```

2. **Confirm the engine selection** in EZNEC: `Options → Calculating engine →
   External NEC-5`. `LastRun.log` should say `Running ext engine ...NEC5CL_x13.exe`.

3. **Run each bundled example.** Open the `.ez`, then trigger a calculation
   (`SWR`, `FF Plot`, or `Src Dat` — each is one engine launch, and each gets its
   own capture directory). No batch mode exists, so this is a manual-but-mechanical
   sitting; the deck self-identifies by its first `CM` line, so nothing needs
   labelling as you go.

4. **Index the corpus:**

   ```powershell
   python scripts/eznec_spy/index_captures.py `
       --markdown docs/status/2026-08-17-eznec-nec5-dialect-capture.md `
       --json scratch/eznec-capture/index.json
   ```

5. **Uninstall** when done: `pwsh scripts/eznec_spy/uninstall.ps1`.

### Model checklist

Bundled examples in `C:\EZNEC 7.0\Docs\Ant`. Group A decides the headline
question; group B is the control and coverage set. `LAST.EZ` is EZNEC's
session-restore copy, not a distinct model — skip it.

**A. Transmission lines and networks (run these first)**

- [ ] `4sqtl.ez` — 4-square, all-transmission-line feed
- [ ] `4Square TL ARRL Example.ez` — the ARRL "simplest" TL feed
- [ ] `CardTL.ez` — cardioid with TL feed system
- [ ] `Cardioid TL ARRL Example.ez` — ARRL cardioid TL feed
- [ ] `DipTL1.ez` — coax modelled as TL (inside) + wire (outside)
- [ ] `Logpertl.ez` — log-periodic with TL interelement feed
- [ ] `Legacy\Diptl.ez`, `Legacy\DipTLxx.ez` — older DipTL variants
- [ ] `4Square L Network Feed ARRL Example.ez` — L-network feed
- [ ] `4Square L Network Feed With Z Matching.ez` — + transformer and series C
- [ ] `Cardioid L Network Feed ARRL Example.ez` — the `0000` capture's model
- [ ] `Network connection test.EZ` — W7EL's NEC-5 junction-object demonstration

**B. Controls and feature coverage**

- [ ] `Dipole1.ez` — plainest possible control (free space, bare wires)
- [ ] `Bydipole1.ez`, `Byvee.ez`, `Legacy\Bydipole.ez` — bare-wire controls
- [ ] `Vert1.ez` — source connected to ground
- [ ] `Elevrad1.ez`, `Elevrad2.ez` — elevated radials (ground types)
- [ ] `Vhfgp.ez` — five-wire junction source (the `favored wire` case)
- [ ] `4square.ez`, `Cardioid.ez` — phased arrays without the TL feed
- [ ] `15mquad.ez`, `20m5elya.ez`, `Nbsyagi.ez`, `W8jk.ez`, `Logper.ez` — Yagi/quad/array
- [ ] `Fdsp1.ez`, `Legacy\Fdsp.ez`, `K5rp.ez`, `N4pcloop1.ez`, `Legacy\N4pcloop.ez` — loops and wire antennas

Hand-supplement only where the bundled set leaves a gap — the issue calls out
Y-parameter networks and ground types that no example exercises.

## Capture layout

```
scratch/eznec-capture/0007_20260817-101530/
  meta.tsv            argv, cwd, real-engine hash, stdin/stdout redirection, exit code, elapsed
  stdin.bin           bytes EZNEC wrote to the engine (empty if it uses argv only)
  stdout.bin          the engine's progress chatter
  stderr.bin          Fortran runtime errors, if any
  pre-manifest.tsv    every file in cwd + engine dir before the run: size, mtime, sha256
  post-manifest.tsv   the same after, so new/changed files are a diff
  pre/                copies (<4 MB, excluding .exe/.dll/.nex) — the deck EZNEC wrote
  post/               the same after — the printout the engine produced
```

## Safety notes

- The shim never blocks the session: every capture step is wrapped, and a failure
  still delegates and still returns the engine's real exit code.
- stdin/stdout/stderr are *pumped* (tee'd, flushed per read), never read to EOF,
  so a prompt-driven protocol cannot deadlock behind the shim.
- `install.ps1` refuses to archive a file under 1 MB as "the real engine", so a
  double install cannot overwrite the archived original with the shim.
- `uninstall.ps1` hash-verifies the restored binary against `installed.tsv`.

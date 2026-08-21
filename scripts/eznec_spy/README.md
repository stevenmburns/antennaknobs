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

**CLOSED** by the 2026-08-20 sitting: 29 models clicked that sitting, 3 already
covered, `LAST.EZ` skipped. Ids below are capture directory prefixes in
`scratch/eznec-capture/`. The capture records a model's *title*, not its
filename, and same-title models never share a deck body — so where one
checklist line names several files with one title between them, the ids are
grouped by the distinct deck bodies the sweep found rather than by filename.

**A. Transmission lines and networks (run these first)**

- [x] `4sqtl.ez` — 4-square, all-transmission-line feed — `0001`–`0009` (a nine-point frequency sweep: EZNEC regenerates the anchor wire and every `TL` length per point), `0097`, `0098` (body 1)
- [x] `4Square TL ARRL Example.ez` — the ARRL "simplest" TL feed — `0024`, `0049`, `0050` (body 2; both bodies carry the title `4-square array w/feed system`, so which body is which file is not recorded)
- [x] `CardTL.ez` — cardioid with TL feed system — `0026`, `0051`, `0052` (body 1 of `Cardioid with feed system`)
- [x] `Cardioid TL ARRL Example.ez` — ARRL cardioid TL feed — `0027`, `0099`, `0100` (body 2, same title caveat)
- [x] `DipTL1.ez` — coax modelled as TL (inside) + wire (outside) — `0011`, `0029`, `0030`, `0053`–`0056`, `0101`, `0102`
- [x] `Logpertl.ez` — log-periodic with TL interelement feed — `0028`, `0073`, `0074`
- [x] `Legacy\Diptl.ez`, `Legacy\DipTLxx.ez` — older DipTL variants — captured under the `Dipole with coax feedline` title, whose nine captures resolve to ONE deck body once frequency-dependent fields are normalized. Either reading is a closed box: the legacy variants emit the same geometry as `DipTL1.ez`, or they are the same model under three filenames
- [x] `4Square L Network Feed ARRL Example.ez` — L-network feed — `0023`, `0087`, `0088`
- [x] `4Square L Network Feed With Z Matching.ez` — + transformer and series C — `0025`, `0089`, `0090`
- [x] `Cardioid L Network Feed ARRL Example.ez` — the `0000` capture's model — `0000`, `0095`, `0096`, and the phased-through-network variants `0118`/`0119`, `0120`/`0121`
- [x] `Network connection test.EZ` — W7EL's NEC-5 junction-object demonstration — `0012`, `0014`, `0016`, `0017`, `0018` (four configs)

**B. Controls and feature coverage**

- [x] `Dipole1.ez` — plainest possible control (free space, bare wires) — `0010`, `0036`–`0042` (the frequency-stepping session)
- [x] `Bydipole1.ez`, `Byvee.ez`, `Legacy\Bydipole.ez` — bare-wire controls — `Back yard dipole` `0057`, `0058`, `0061`, `0062`, `0113`–`0115` (two bodies); `Back yard inverted vee` `0059`, `0060`
- [x] `Vert1.ez` — source connected to ground — `0015`, `0019`–`0022`, `0043`–`0048`, `0107`–`0112` (the ground cycle and the near-field family)
- [x] `Elevrad1.ez`, `Elevrad2.ez` — elevated radials (ground types) — `0033`, `0103`, `0104` and `0034`, `0105`, `0106` (two distinct bodies, one per file)
- [x] `Vhfgp.ez` — five-wire junction source (the `favored wire` case) — `0013`, `0085`, `0086`
- [x] `4square.ez`, `Cardioid.ez` — phased arrays without the TL feed — `0031`, `0091`, `0092` (+ the TL variant `0116`/`0117`); `0032`, `0093`, `0094`
- [x] `15mquad.ez`, `20m5elya.ez`, `Nbsyagi.ez`, `W8jk.ez`, `Logper.ez` — Yagi/quad/array — `0063`/`0064`; `0035`, `0065`, `0066`; `0067`/`0068`; `0069`/`0070`; `0071`/`0072`
- [x] `Fdsp1.ez`, `Legacy\Fdsp.ez`, `K5rp.ez`, `N4pcloop1.ez`, `Legacy\N4pcloop.ez` — loops and wire antennas — `0075`–`0078` (one body, so the legacy Fdsp deck emits the same geometry); `0079`/`0080` — the corpus's only `EX 0` model outside the elevated radials; `0081`–`0084` (one body, same reading for the legacy N4PC deck, and the corpus's worst impedance disagreement — see the matrix's 2026-08-21 re-weight)

Hand-supplement only where the bundled set leaves a gap — the issue calls out
Y-parameter networks and ground types that no example exercises.

What the closed checklist bought, measured by `scripts/eznec_serve_sweep.py`
and scored in `docs/status/2026-08-20-eznec-nec5-scored-matrix.md`: the corpus
went 49 → 122 captures and 15 → 23 model titles, the seam serves 115 of them,
and the two cards the bundle had never shown — a phased drive reaching the
structure through a network, and `NH` — are both in it.

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

## Fault injection

The engine's error paths all exit 0, so EZNEC must detect failure by reading the
printout. To find out what it reads for, the shim can damage the printout *after*
a real run and hand the damaged file back.

Armed by a **marker file**, not an environment variable — EZNEC inherits its
environment from Explorer, so a variable set in a shell never reaches it:

```powershell
'error_at:1670' | Set-Content scratch/eznec-capture/fault.txt
```

The marker is **consumed on read**, so exactly one launch is affected and a session
can never get stuck failing. The engine always runs for real first, and its
undamaged printout is saved into the capture as `printout-undamaged.txt`.

| spec | what EZNEC receives |
| --- | --- |
| `empty` | printout truncated to 0 bytes |
| `delete` | printout removed |
| `truncate:N` | first N bytes only (default 2000) |
| `error_at:N` | first N bytes, then a `NEC ERROR` refusal line |
| `nec_error[:msg]` | printout replaced by a single `NEC ERROR` line |
| `garbage` | printout replaced by non-NEC text |
| `exit:N` | printout untouched; process exit status forced to N |

Then trigger **one** engine launch in EZNEC. Because EZNEC caches results, an edit
that returns a model to an already-computed state produces no launch at all —
nudge the frequency before clicking `Src Dat` so a launch actually happens.

Findings are written up in the status doc under "Error convention"; captures
0036-0042 are the evidence. In short: the exit status is ignored, the printout must
echo the deck's `CM` cards or it is rejected as stale, and a `NEC ERROR` line placed
after that echo is displayed to the user verbatim.

## Safety notes

- The shim never blocks the session: every capture step is wrapped, and a failure
  still delegates and still returns the engine's real exit code.
- stdin/stdout/stderr are *pumped* (tee'd, flushed per read), never read to EOF,
  so a prompt-driven protocol cannot deadlock behind the shim.
- `install.ps1` refuses to archive a file under 1 MB as "the real engine", so a
  double install cannot overwrite the archived original with the shim.
- `uninstall.ps1` hash-verifies the restored binary against `installed.tsv`.

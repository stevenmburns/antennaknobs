# 4nec2 → NEC-2 subengine: invocation, dialect, and the intersection

Status doc for momwire#413, the third front door after SimNEC (shipped,
antennaknobs#846) and EZNEC (measured, #390). Black-box I/O observation only — the
spy shim logs what crosses the process boundary and delegates; nothing was
decompiled. Same courtesy stance as the SimNEC and EZNEC studies.

Host: 4nec2 (freeware) on the Windows box that ran the SimNEC live session and the
#390 EZNEC captures. Harness: `scripts/eznec_spy/`, generalized for a second host.
Captures: `scratch/4nec2-capture/`.

## Headline

**4nec2 batches sweeps into a single engine launch.** One process, one deck, an
`FR` card carrying `NFRQ=30`, and 31 frequency blocks in the printout. EZNEC
cannot and does not — it relaunches per frequency point with the whole deck
regenerated, leaving momwire's swept machinery nothing to amortize. This is the
first of the three seams where that machinery pays off at all, and it is the
strongest argument yet found for the 4nec2 front door.

**The dialect splits cleanly in two.** 4nec2's own extensions are resolved away
before the engine sees anything; NEC's own advanced cards are passed through
untouched. That split is the whole work list, and it falls out better than #413
feared on the item it feared most (`SY`) and worse on geometry and patches.

## Invocation protocol

Nothing like EZNEC's. The engine takes **no arguments at all** — it prompts, and
4nec2 answers with a two-line response file on **stdin**:

```
command line : Nec2dXS1k5.exe            (no arguments)
cwd          : C:\4nec2\exe
stdin        : "..\out\MultiTra.inp\r\n..\out\MultiTra.out\r\n"
stdout       : banner, then "ENTER NAME OF INPUT FILE > ENTER NAME OF OUTPUT FILE >"
exit         : 0
```

- **Deck first, printout second**, CRLF-terminated, relative to the engine's own
  directory — so the decks live one level up in `..\out\`, not beside the engine.
  `4nec2.bat`, shipped in the install, documents the same convention
  (`%nec2d% < nec2d.tmp`), and 4nec2 leaves its last response file on disk as
  `exe\nec2d.tmp`.
- **The line endings matter.** A response file whose first line ends `\n` instead
  of `\r\n` makes the engine answer `Error opening input-file` on a path that
  demonstrably exists. A drop-in reading stdin must not assume the host is lenient
  about this, because the real engine is not.
- **One-shot, not resident**, like both other seams.
- **stdout is a prompt stream, not a log.** The engine writes `ENTER NAME OF INPUT
  FILE >` and waits. A drop-in must either reproduce the prompts or ignore them,
  but it cannot read stdin to EOF before answering — the shim pumps stdio for
  exactly this reason.

### The engine set

4nec2 ships **eleven** engine binaries and picks among them; there is no single
path to stand in at.

| family | binaries |
| --- | --- |
| current, merged nec2d/som2d | `nec2dxs500`, `nec2dxs1K5`, `nec2dxs3k0`, `nec2dxs5k0`, `nec2dxs8k0`, `nec2dxs11k` |
| legacy | `nec2d`, `nec2d512`, `nec2d960`, `nec2d1k4` |
| Sommerfeld | `Somnec2d` |

All six `nec2dxs*` builds are byte-distinct despite identical file size. They
self-identify on stdout, and **the limits differ per build, not just segment
count**:

```
nec2dxs1K5 : Build 2.7  30-jan-08  (maxLD=  150, MaxEX=  99, MaxTL= 128)
nec2dxs11k : Build 2.7  30-jan-08  (maxLD= 1100, MaxEX= 256, MaxTL= 256)
```

They also announce themselves as a **merged nec2d/som2d file** — so the Sommerfeld
ground solver is built into the engine, and the separate `Somnec2d.exe` step that
`4nec2.bat` provides for is a legacy path. `Somnec2d.exe` was shimmed alongside the
others and has not fired in any capture so far.

**Selection rule: not yet determined.** Both captured models chose `Nec2dXS1k5`,
including one of ~60 segments that would fit `nec2dxs500` comfortably — so it is
not "smallest build that fits". A drop-in must cover every path it can be launched
from, the analogue of SimNEC's `nec2c`-substring rule.

**The engine path is user-configurable** (`Settings → Nec engine → Manual select`,
with a max-segment count). That matters twice: it is a supported way to point 4nec2
at a drop-in without renaming anything, and it is how the NEC-4 slot becomes
capturable on a box with no NEC-4 licence.

## Sweep batching: one launch, `NFRQ=30`

The finding with the most leverage for momwire.

| run | launches | elapsed | request cards |
| --- | --- | --- | --- |
| single point | 1 | 267 ms | `FR 0 1 0 0 1.91 1` + `XQ` |
| 30-point sweep | **1** | 2787 ms | `FR 0 1 0 0 1.91 0`, `XQ`, `FR 0 30 0 0 1 1`, `RP 0 37 1 1000 -90 0 5` |

The sweep deck is **two-phase in a single file**: a single-point solve terminated
by `XQ`, then a 30-point `FR` with a pattern request. The printout carries 31
frequency blocks. Nothing relaunches.

Against EZNEC — one launch per point, whole deck regenerated, a Sommerfeld cache
invalidated by exactly what a sweep varies — this is a different economic
proposition entirely. A drop-in here is asked one question and answers it once.

Also worth noting: the two run modes emit **identical model bodies** and differ
only in the request-card tail. The mode changes what is asked, not how the antenna
is described — the same shape as the EZNEC study's "request cards follow the
display".

## What 4nec2 resolves before the engine

These never reach the subengine, so the portal never has to speak them. Verified by
diffing source models against the decks 4nec2 emitted from them.

| source (what the user writes) | emitted (what the engine sees) |
| --- | --- |
| `SY H=20`, `SY L28=2.629049, L28a=L28-t` | gone — expanded to literals |
| `LD 6 81 1 1 100 73.639uH 7.0pF` | `LD 1 81 1 1 8.83821e4 7.36464e-5 7.e-12` |
| `73.639uH`, `7.0pF` | SI floats |
| `'FR 0 1 0 0 28.05 1` | gone — `'` is 4nec2's comment marker |
| `SM 04,08, 0.000, 0.000` | `SM 04 08 0.000 0.000` — commas normalized to spaces |

**`SY` is the big one.** It appears in **174 of 467** bundled models — 37% of the
corpus, and by far the most-used card on momwire's refusal list. #413 flagged it as
the case that could force "the whole expression grammar" on the portal. It does
not: symbols, arithmetic (`L28-t`, `qturns*5`), and inline `'` comments are all
resolved by 4nec2 itself. **That refusal can stay refused.**

`LD 6` is a 4nec2 trap extension (R, L, C with a Q figure) that becomes a standard
`LD 1` parallel RLC. Note that the emitted `L` differs slightly from the source
(`7.36464e-5` vs `73.639uH`), so 4nec2 is recomputing rather than merely
converting units — a drop-in sees only the result and does not need the rule.

## What passes straight through

Untouched, into the engine, in one model (`SPatch/gs_8d_bb.nec`):

```
SM 04 08 0.000 0.000 0.000 0.150 0.000 0.000
SC 00 00 0.150 0.250 0.000 0.000 0.250 0.000
GX 28 110
TL 0 01 0 06 -300. 0.110          <- negative Z0: crossed line
EX 0 0 01 0 1. 0                  <- tag 0: absolute segment numbering
LD 5 0 0 0 3.72E+07               <- tag 0: all wires
PT -1
NE 0 26 1 26 -20 0 0 1.6 1 2
```

So **geometry transforms and surface patches are not pre-expanded** the way `SY`
was. A model with four `GW` cards and a `GX 28,110` reflection is handed to the
engine as four wires and a `GX`. The portal must implement them or refuse them.

Two dialect details a parser must tolerate:

- **`GE` is emitted bare**, with no argument at all, in the patch model. Other
  decks emit `GE 0` or `GE -1`.
- **`EN` is optional.** The `gs_8d_bb` deck ends at its `NE` card with no
  terminator; the engine synthesizes card 13 as `EN` at EOF, reusing the previous
  card's numeric fields. Of six emitted decks on disk, only one carries `EN`. A
  drop-in must not require it.

## The intersection

`(what 4nec2 emits) ∩ (what momwire.deck refuses)` — the work list #413 asked for.
Model counts are over the 467-model bundled corpus; "resolved" means 4nec2 handles
it before the engine.

| card | models | status | portal work |
| --- | --- | --- | --- |
| `SY` | 174 | **resolved by 4nec2** | none — refusal can stand |
| `TL` | 45 | passes through | required (already the #390 verdict) |
| `GX` | 18 | passes through | **required** — geometry reflection |
| `SP` | 10 | passes through | **required** — surface patches |
| `SM` | 9 | passes through | **required** — multiple patches |
| `GR` | 5 | passes through (assumed) | rotation |
| `GH` | 4 | passes through (assumed) | helix |
| `GC` | 3 | passes through (assumed) | tapered-wire continuation |
| `PQ` | 3 | passes through (assumed) | charge-density print |
| `WG` | 2 | passes through (assumed) | **Green's-function write** — see below |
| `NT` | 1 | passes through | required (already the #390 verdict) |
| `CP` | 1 | passes through (assumed) | coupling |
| `GF` | 1 | passes through (assumed) | **Green's-function read** — see below |

"Assumed" means the card is in the corpus and nothing resolves cards of its family,
but no capture has yet driven that specific model. Those are the runs still to do.

**Not on the refusal list, but adjacent and unverified:** `SC` (2695 cards, 15
models) always accompanies `SP`/`SM`; `GM` (199 cards, 41 models) and `GS` (153
cards, 152 models) are geometry move/scale. None is refused by name, but whether
momwire implements them is a separate question from whether it refuses them, and
`GS` appears in a third of the corpus.

### The Green's-function pair is not a card problem

`WG RADIAL8.NGF` writes a Numerical Green's Function file; `GF 0 RADIAL8.NGF`
reads it back in a later run. That is a **second file channel** beyond the deck and
printout — persistent state written by one invocation and consumed by another, in a
binary format nobody here has specified. Two models write one, one model reads one.

This is a different *kind* of obligation from a card, and closer to EZNEC's
`SOMPD.NEX` Sommerfeld cache than to anything on the dialect list. A drop-in that
accepts `WG` silently and writes nothing would break the *next* run, not this one.

## Error convention

Fault injection, same harness as #414. The engine runs for real and the printout is
damaged before 4nec2 reads it; the marker is consumed on use.

| what the engine left behind | exit | 4nec2's response |
| --- | --- | --- |
| valid printout, **exit code 1** | 1 | **nothing — results rendered normally** |
| printout emptied to 0 bytes | 0 | popup: "Nec error ? Check output (F8)" |
| single `***** NEC ERROR - <text>` line, no header | 0 | popup **displays the text verbatim** |

Three conclusions:

1. **The exit status is ignored**, exactly as with EZNEC. This retires the risk
   #413's session notes flagged: the shim's 9009 "cannot find real engine" code
   would not have been noticed either.
2. **No stale results.** The failure the issue named as the dangerous one — a host
   silently redisplaying the previous run's printout, making a drop-in's refusals
   invisible — does not occur. 4nec2 detects the bad printout and says so.
3. **Refusals can speak, in free-form text, with no framing requirements.** A
   single `NEC ERROR` line replacing the entire printout is surfaced verbatim in a
   popup. This is **materially easier than EZNEC**, which rejected the identical
   input as "written earlier from another calculation" because it had lost the
   echoed `CM` cards; 4nec2 needs no header, no timestamp echo, nothing.

A separate popup — "Errors or warnings found, run 'Segment check'" — is 4nec2's own
geometry validator, not an engine channel. It fired on a model whose printout was
123 KB of clean results and whose pattern rendered correctly.

## The NEC-4 slot

Not yet captured, but two things are already established.

The corpus ships a `models/Nec4/` folder using cards that are **NEC-4 only** and
appear nowhere else in the bundle:

```
CW  1  39  -19.64 0.0 20  19.64 0.0 20  0.001 2 19.64 1     (catenary wire)
IS  -1  1  0  0  14  .006  .002                             (insulated sheath)
VC  0
UM  0  0  0  0  14  .006
```

None of these is on momwire's refusal list — the list was built against NEC-2/NEC-5
surface. Standing in at the NEC-4 slot means claiming NEC-4 physics, and a drop-in
that answered NEC-2 physics there would be wrong in a way the user cannot see. The
go/no-go must treat the two slots separately, as #413 says.

Because the engine path is configurable, the NEC-4 deck is capturable without
owning NEC-4: point the slot at a shim, let 4nec2 write the deck, and let
delegation fail. Whether 4nec2 emits a *different* deck for the NEC-4 slot is still
open.

## Harness changes this required

The #390 harness was written against one host with one protocol. Three things had
to give, all committed:

- **Host parameters** — `install.ps1`/`uninstall.ps1` hardcoded EZNEC's process
  name and a 1 MB "this is a real engine" floor. The 4nec2 builds are ~300 KB and
  `Somnec2d` is 77 KB. Provenance is now per engine, so eleven installs coexist.
- **`watchdirs.txt`** — the shim snapshotted cwd and the engine directory, which
  for 4nec2 are the same place, while every deck and printout lives in `..\out`.
- **A latent stdin bug.** .NET builds the child's stdin writer from
  `Console.InputEncoding` and auto-flushes it at `Process.Start`, emitting that
  encoding's preamble — so on a UTF-8 console the shim prepended a **BOM** to
  everything the host sent. EZNEC ignores stdin, so it never showed. 4nec2's
  engines read their response file from stdin and answered `Error opening
  input-file` on the BOM'd first line.

## Open work

- Drive the models behind the "assumed" rows: `GR`, `GH`, `GC`, `PQ`, `CP`, and
  above all the `WG`/`GF` Green's-function pair, which is a file-format obligation
  rather than a card.
- The engine-selection rule — both captures chose `Nec2dXS1k5`; find the boundary.
- The optimiser/sweeper loop: launch rate and per-launch cost while 4nec2 drives
  the engine in a tight loop. Static examples cannot answer it.
- The NEC-4 slot, via a non-delegating shim at a manually selected engine path.
- Whether `GM`/`GS`/`SC` are implemented in momwire, as distinct from refused.
- The July-vintage `MultiTra.inp` on disk carried `EK`, six `CM FR` cards and
  `GE -1` where today's runs emit none of them. Some 4nec2 mode rewrites the ground
  flag and injects the extended thin-wire kernel; which one is unknown, and `GE -1`
  vs `GE 0` is a ground-contact question worth pinning for #151/#282/#291/#292.

## Go / no-go

**Better than either other seam on plumbing, and the only one where batching
pays.** One console executable, a two-line response file on stdin, a printout back,
no resident protocol, refusals in free-form text with no framing ritual, and the
exit code ignored. The sweep answer is the prize: a 30-point sweep is one launch,
not thirty.

The blocker is the same one #390 found, plus geometry. `TL`/`NT` are already known
to be required. What 4nec2 adds is **surface patches (`SP`/`SM`/`SC`) and geometry
transforms (`GX`, and probably `GR`/`GH`/`GC`)** — 19 models of patches and 18 of
reflections in the bundled corpus, none of them resolved before the engine. And the
`WG`/`GF` Green's-function pair is an obligation of a different kind entirely.

The good news is that the single scariest item evaporated: `SY` saturates 37% of the
corpus and never reaches the engine.

Scope decision, for a separate issue as in #390: the same three options apply, and
the same third one looks best — put the seam where the parsing already lives.

# 4nec2 → NEC-2/NEC-4 subengine: invocation, dialect, and the intersection

Status doc for momwire#413, the third front door after SimNEC (shipped,
antennaknobs#846) and EZNEC (measured, #390). Black-box I/O observation only — the
spy shim logs what crosses the process boundary and delegates; nothing was
decompiled. Same courtesy stance as the SimNEC and EZNEC studies.

Host: 4nec2 (freeware) on the Windows box that ran the SimNEC live session and the
#390 EZNEC captures. Harness: `scripts/eznec_spy/`, generalized for a second host.
**38 captures over 17 distinct emitted decks**, plus the 467-model bundled corpus
read statically. Captures: `scratch/4nec2-capture/`.

## Verdict

**Mechanically the best of the three seams; dialectally the widest.**

Sweeps batch — a 30-point sweep is *one* engine launch, against EZNEC's one launch
per point. This is the first seam where momwire's swept machinery amortizes at all,
and on its own it is the strongest argument for the 4nec2 front door.

But the dialect splits in two, and the split decides the work:

- **4nec2's own extensions never reach the engine.** `SY` symbols and arithmetic,
  `LD 6` traps, `LD 7` wire-coating, `#nn` AWG gauges, `ft` units, `'` comments.
  The scariest item on #413's list — `SY`, in **174 of 467** bundled models —
  evaporates entirely. That refusal can stand.
- **NEC's own advanced cards pass straight through.** `GX`, `GR`, `GC`, `GH`, `GM`,
  `SP`, `SM`, `SC`, `CP`, `PQ`, `TL`, `NT`, `WG`, `GF`, `NX`. These are the portal's
  new work, and geometry transforms and surface patches are the bulk of it.

Two translations are worse than a pass-through, because they manufacture cards the
user never wrote: **`EX 6` becomes a voltage source behind an `NT` network**, and
**`GN 3` becomes `GN 1` + `GD`**. The first drags network solving into models whose
authors wrote none; the second silently substitutes ground physics.

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
  directory — the decks live one level up in `..\out\`, not beside the engine.
  `4nec2.bat`, shipped in the install, documents the same convention
  (`%nec2d% < nec2d.tmp`), and 4nec2 leaves its last response file at
  `exe\nec2d.tmp`.
- **Line endings matter.** A response file whose first line ends `\n` instead of
  `\r\n` makes the engine answer `Error opening input-file` on a path that
  demonstrably exists. A drop-in reading stdin must not assume the host is lenient,
  because the real engine is not.
- **One-shot, not resident**, like both other seams.
- **stdout is a prompt stream, not a log.** A drop-in must not read stdin to EOF
  before answering.
- **Side-files land in cwd**, not in `..\out` with the decks — see the Green's
  function section.

### The engine set and how one is chosen

4nec2 ships **eleven** engine binaries; there is no single path to stand in at.

| family | binaries |
| --- | --- |
| current, merged nec2d/som2d | `nec2dxs500`, `nec2dxs1K5`, `nec2dxs3k0`, `nec2dxs5k0`, `nec2dxs8k0`, `nec2dxs11k` |
| legacy | `nec2d`, `nec2d512`, `nec2d960`, `nec2d1k4` |
| Sommerfeld | `Somnec2d` |

All six `nec2dxs*` builds are byte-distinct despite identical file size, and the
**array limits scale with the build**, not just the segment count:

```
nec2dxs1K5 : MAXMAT= 1500   (maxLD=  150, MaxEX=  99, MaxTL= 128)
nec2dxs3k0 : MAXMAT= 3000   (maxLD=  300, MaxEX= 128, MaxTL= 256)
nec2dxs11k : MAXMAT=11000   (maxLD= 1100, MaxEX= 256, MaxTL= 256)
```

They announce themselves as a **merged nec2d/som2d file**, so the Sommerfeld solver
is built into the engine; the separate `Somnec2d.exe` step `4nec2.bat` provides for
is a legacy path, and it never fired in 38 captures.

**Selection scales with the model.** A ~2,100-segment model selected `Nec2dXS3k0`;
smaller models selected `Nec2dXS1k5`. `nec2dxs500` was never selected, even for a
~60-segment model, so the rule is "smallest build that fits" with `1K5` as an
effective floor. **A drop-in must cover all six paths**, the analogue of SimNEC's
`nec2c`-substring rule.

**The engine path is user-configurable** (`Settings → Nec engine → Manual select`).
That is a supported way to point 4nec2 at a drop-in without renaming anything, and
it is how the NEC-4 slot was captured on a box with no NEC-4 licence.

## Sweep batching: one launch, `NFRQ=30`

The finding with the most leverage for momwire.

| run | launches | elapsed | request cards |
| --- | --- | --- | --- |
| single point | 1 | 267 ms | `FR 0 1 0 0 1.91 1` + `XQ` |
| 30-point sweep | **1** | 2787 ms | `FR 0 1 0 0 1.91 0`, `XQ`, `FR 0 30 0 0 1 1`, `RP …` |

The sweep deck is **two-phase in a single file**: a single-point solve terminated by
`XQ`, then a 30-point `FR` with a pattern request. The printout carries 31 frequency
blocks. Nothing relaunches.

Batching also arrives **from user decks**: `VHFmultiband/Dc8ce.nec` carries its own
`FR 0 25 0 0 1100 100`, so a drop-in sees multi-frequency `FR` whether or not the
sweep UI was used.

The two run modes emit **identical model bodies** and differ only in the
request-card tail — the same shape as the EZNEC study's "request cards follow the
display".

## The optimiser loop

20 launches in 10 s — a sustained **~2 Hz**, each ~90 ms, same engine build, same
deck path.

**The whole deck is regenerated every iteration.** The optimiser perturbs one `SY`
variable and re-expands all geometry from it:

```
GW 1 11 0 -2.529049 20 0 2.529049 20 .001
GW 1 11 0 -2.531678 20 0 2.531678 20 .001
```

Per iteration: ~500 ms wall, of which the engine is ~90 ms. **Roughly 400 ms is
4nec2's own overhead** — deck generation, printout parsing, UI. Process startup cost
is therefore not the bottleneck at this seam, which is a materially different
picture from EZNEC's sweep, where per-launch cost was the whole story.

## What 4nec2 resolves before the engine

Never reaches the subengine, so the portal never speaks it. Verified by diffing
source models against the decks 4nec2 emitted from them.

| source (what the user writes) | emitted (what the engine sees) |
| --- | --- |
| `SY H=20`, `SY L28=2.629049, L28a=L28-t` | expanded to literals, including inside `FR`/`GH` fields |
| `LD 6 81 1 1 100 73.639uH 7.0pF` | `LD 1 81 1 1 8.83821e4 7.36464e-5 7.e-12` |
| `LD 7` (wire-coating) | 4nec2 extension; NEC-2 has no `LD 7` |
| `73.639uH`, `7.0pF`, `100 ft`, `.5ft` | SI floats — `100 ft` → `30.48` |
| `#16` (AWG gauge) | `6.4515e-4` m radius |
| `'FR 0 1 0 0 28.05 1` | dropped — `'` is 4nec2's comment marker |
| `SM 04,08, 0.000` | `SM 04 08 0.000` — commas and tabs → single spaces |

`LD 6` and `LD 7` are documented in 4nec2's own card table (`data/Edit2.txt`) as
`LC-Trap` and `Wire-coating`; neither exists in NEC-2. Note the emitted inductance
differs slightly from the source (`7.36464e-5` vs `73.639uH`), so 4nec2 recomputes
rather than merely converting units — a drop-in sees only the result.

### Two translations that manufacture cards

**`EX 6` → voltage source + `NT` + a phantom wire.** The source drives with forced
current:

```
EX 6 800 3 0 1 0 0
EX 6 801 3 0 6.12e-17 1 0
```

and 4nec2 emits:

```
GW 9901 1 -1.1945e-4 0 9901 1.19452e-4 0 9901 5.97258e-6
GW 9902 1 -1.1945e-4 0 9902 1.19452e-4 0 9902 5.97258e-6
EX 0 9901 1 0 0 1
EX 0 9902 1 0 -1 0
NT 9901 1 800 3 0 0 0 1
NT 9902 1 801 3 0 0 0 1
```

So a model whose author wrote only current sources still lands **network cards** in
the deck — the same "wider than it looks" trap the EZNEC study hit when junction
loads became `NT`. `EX 6` cannot be scored as a clean win.

**The phantom wire is 4nec2's anchoring idiom** (antennaknobs#944 asks whether it
has one): a 1-segment wire ~0.24 mm long, radius 5.97e-6, parked at **z = its own
tag number** — tag 9901 sits 9901 m up. Different constants from EZNEC's 100 λ
anchor, same purpose. And like EZNEC's it is **driven and an `NT` endpoint**, so it
fails `_anchor_wires`' guards (#427) exactly as EZNEC's does.

**`GN 3` → `GN 1` + `GD`.** 4nec2's own "MiniNec ground (4nec2 specific)" is not a
NEC-2 ground type, and is rewritten:

```
source:   GN 3 0 0 0 13  0.005 0.0 0.0
emitted:  GN 1
          GD 0 0 0 0 13 0.005      (NEC-2 slot)
          GD 2 0 0 0 13 0.005      (NEC-4 slot)
```

This is a **physics substitution, not a syntax one**, and it converges with the
EZNEC study, which also expressed MININEC-type ground as a `GD` card — and where
`GD` versus `GN 0`, both printing the same Sommerfeld banner, came out **34% apart
in R** on a ground-contacting vertical. Two independent hosts reaching for `GD` for
the same purpose makes this a ready-made oracle for the ground-contact thread
(#151, #282, #291, #292).

**`GD` is not on momwire's by-name refusal list**, and **33 of 467** bundled models
use `GN 3`. Those arrive as decks momwire accepts syntactically while meaning
something it may not implement — the most dangerous category on this page.

## What passes straight through

Untouched, into the engine. Observed across 17 emitted decks:

```
SM 04 08 0.000 0.000 0.000 0.150 0.000 0.000
SC 00 00 0.150 0.250 0.000 0.000 0.250 0.000
GX 28 110                       GR 45 8              GR 0 6
GC 0 0 1 0.004 0.001            GM 3 1 0 0 180 0 0 0 2
GH 10 10 109.88632 56.319872 21.69538 …   (symbols already resolved)
SP 0 0 10. 0. 7.3333 0. 0. 38.4            CP 1 1 2 1
TL 0 01 0 06 -300. 0.110        (negative Z0: crossed line)
NT 11 10 11 2 .005484 -.019898 0. 0. 1.E10 0.
LD 5 0 0 0 3.72E+07             PT -1        PQ -1
```

A model with four `GW` cards and a `GX 28,110` reflection is handed to the engine as
four wires and a `GX`. **Geometry transforms are not pre-expanded** the way `SY` was.

`TL` with negative Z₀ appears in a log-periodic here exactly as it did in the EZNEC
corpus, and hand-written `NT` cards use `1.E10` on the far port to pin it open —
the same idiom EZNEC used, arrived at independently.

`GA` (wire arc) is **documented in 4nec2's card table but used by zero bundled
models**. Nothing resolves cards of its family, so it must be assumed to pass
through; it is the one row here without direct capture evidence.

### Dialect details a parser must tolerate

- **`CE` carries trailing text.** 4nec2 turns the last `CM` line into
  `CE more complex NGF files. See 4nec2.hlp (F1)…`. A parser treating `CE` as a bare
  terminator loses content.
- **`GE` may be emitted bare**, with no argument at all; other decks emit `GE 0`,
  `GE 1`, `GE -1`, and the NEC-4 slot emits **`GE 0 1`** with two fields.
- **`EN` is optional.** The `gs_8d_bb` deck ends at its `NE` card with no
  terminator; the engine synthesizes card 13 as `EN` at EOF, reusing the previous
  card's numeric fields.
- **`XQ` is injected.** 4nec2 adds execute cards the user never wrote.
- The printout echoes every card as `***** DATA CARD NO. n <MNEMONIC> …` — the parse
  echo a stand-in must reproduce.

## The Green's function pair is not a card problem

`WG` writes a Numerical Green's Function file; `GF` reads it back. Both appear with
**and without** a filename:

```
WG RADIAL8.NGF      GF 0 RADIAL8.NGF      (named)
WG                  GF                    (bare — default file)
```

Executing `WG RADIAL8.NGF` wrote **889,616 bytes to `C:\4nec2\exe`** — the engine's
cwd, *not* `..\out` where decks and printouts live. The printout of the consuming
run carries `** NUMERICAL GREEN'S FUNCTION **` and echoes the **originating** deck's
comment cards, so the `.NGF` is a self-describing binary carrying provenance.

**And a single deck can hold two structures.** `Objects/Gr_func.nec` emits:

```
… WG        (bare — write)
NX          (next structure)
CE
GF          (bare — read it back)
… NT ×6, EX ×2, XQ
```

So the write-then-read handoff can happen **inside one engine invocation**, via `NX`.
A drop-in that accepts `WG` and writes nothing breaks the *next* structure, or the
next run, not this one. This is an obligation of a different kind from a card —
closer to EZNEC's `SOMPD.NEX` Sommerfeld cache.

## The intersection

`(what 4nec2 emits) ∩ (what momwire.deck refuses)` — the work list #413 asked for.
Model counts are over the 467-model bundled corpus.

| card | models | disposition | portal work |
| --- | --- | --- | --- |
| `SY` | 174 | **resolved by 4nec2** | none — refusal can stand |
| `TL` | 45 | passes through | required (already the #390 verdict) |
| `GX` | 18 | passes through | **required** — reflection |
| `SP` | 10 | passes through | **required** — surface patches |
| `SM` | 9 | passes through | **required** — multiple patches |
| `GR` | 5 | passes through | required — cylindrical structure |
| `GH` | 4 | passes through | required — helix/spiral |
| `GC` | 3 | passes through | required — radius tapering |
| `PQ` | 3 | passes through | required — charge density print |
| `WG` | 3 | passes through | **required** — NGF write (side-file) |
| `GF` | 2 | passes through | **required** — NGF read (side-file) |
| `NT` | 1 + synthesized | passes through | required; **also manufactured from `EX 6`** |
| `CP` | 1 | passes through | required — coupling |
| `GA` | 0 | documented, unsampled | assume required |

**Not refused by name, but emitted and physics-bearing** — the category that needs a
decision rather than a parser:

| card | models | why it matters |
| --- | --- | --- |
| `GD` | 33 (via `GN 3`) | ground substitution; 34% R divergence in the EZNEC twin |
| `GM` | 41 | coordinate transform |
| `GS` | 152 | scale factor — a third of the corpus |
| `SC` | 15 | always accompanies `SP`/`SM` |
| `NX` | 2 | multi-structure decks |
| `EK` | 82 | extended thin-wire kernel |

## Error convention

Fault injection, same harness as #414. The engine runs for real and the printout is
damaged before 4nec2 reads it; the marker is consumed on use.

| what the engine left behind | exit | 4nec2's response |
| --- | --- | --- |
| valid printout, **exit code 1** | 1 | **nothing — results rendered normally** |
| printout emptied to 0 bytes | 0 | popup: "Nec error ? Check output (F8)" |
| single `***** NEC ERROR - <text>` line, no header | 0 | popup **displays the text verbatim** |

1. **The exit status is ignored**, as with EZNEC. This retires the risk #413's
   session notes flagged: the shim's 9009 "cannot find real engine" code would not
   have been noticed either.
2. **No stale results.** The failure the issue named as dangerous — a host silently
   redisplaying the previous printout, making refusals invisible — does not occur.
3. **Refusals can speak, in free-form text, with no framing requirements.** A single
   `NEC ERROR` line replacing the entire printout is surfaced verbatim in a popup.
   **Materially easier than EZNEC**, which rejected identical input as "written
   earlier from another calculation" because it had lost the echoed `CM` cards.

A separate popup — "Errors or warnings found, run 'Segment check'" — is 4nec2's own
geometry validator, not an engine channel. It fired on a model whose printout was
123 KB of clean results and whose pattern rendered correctly.

## NEC-2 slot vs NEC-4 slot

Captured by pointing `Settings → Nec engine → Manual select` at a shim named
`NEC42W64CL.exe`, with a NEC-2 build behind it. **The protocol is identical** — same
stdin response file, same cwd, same prompts. **The dialect is not.**

`models/Nec4/Catenary.nec` emits cards that exist nowhere else in the bundle:

```
CW 1 39 -19.64 0.0 20 19.64 0.0 20 0.001 2 19.64 1     (catenary wire)
GE 0 1                                                  (TWO fields)
IS -1 1 0 0 14 .006 .002                                (insulated sheath)
VC 0
UM 0 0 0 0 14 .006
```

4nec2's own NEC-4 card table (`data/Edit4.txt`) documents **eight** cards absent from
the NEC-2 table: `CW IS JN LE LH PS UM VC`. Four were captured.

And the slot changes physics-bearing fields on *shared* cards: the same `GP80.nec`
emits `GD 0 …` on the NEC-2 slot and **`GD 2 …`** on the NEC-4 slot.

**None of these eight is on momwire's refusal list**, because that list was built
against NEC-2/NEC-5 surface. Standing in at the NEC-4 slot means claiming NEC-4
physics — buried wires and the rest of what #388 lists as NEC-4-only — and a
drop-in that answered NEC-2 physics there would be wrong in a way the user cannot
see. **The go/no-go must treat the two slots separately.**

## Harness changes this required

The #390 harness was written against one host with one protocol. Three things had to
give, all committed:

- **Host parameters** — `install.ps1`/`uninstall.ps1` hardcoded EZNEC's process name
  and a 1 MB "this is a real engine" floor. The 4nec2 builds are ~300 KB and
  `Somnec2d` is 77 KB. Provenance is now per engine, so eleven installs coexist.
- **`watchdirs.txt`** — the shim snapshotted cwd and the engine directory, which for
  4nec2 are the same place, while every deck and printout lives in `..\out`.
- **A latent stdin bug.** .NET builds the child's stdin writer from
  `Console.InputEncoding` and auto-flushes it at `Process.Start`, emitting that
  encoding's preamble — so on a UTF-8 console the shim prepended a **BOM** to
  everything the host sent. EZNEC ignores stdin, so it never showed. 4nec2's engines
  read their response file from stdin and answered `Error opening input-file` on the
  BOM'd first line.
- Fault injection learned to find the printout **from the stdin response file** when
  there is no argv to read it from.

## Open work

- `GA` is documented but unsampled — no bundled model uses an arc. Hand-supplement.
- `LD 7` (wire-coating) is documented but unsampled for the same reason; the
  translation target is unknown, though `LD 6`'s precedent suggests a standard `LD`.
- The remaining four NEC-4 cards (`JN`, `LE`, `LH`, `PS`).
- Whether `GM`/`GS`/`SC`/`NX`/`EK` are *implemented* in momwire, as distinct from
  refused — none is on the by-name list.
- The July-vintage `MultiTra.inp` on disk carried `EK`, six `CM FR` cards and
  `GE -1` where today's runs emit none of them. Which mode produced it is unknown.
- `nec2dxs500` was never selected; the bottom of the selection range is unconfirmed.

## Go / no-go

**Plumbing: the best of the three seams.** One console executable, a two-line
response file on stdin, a printout back, no resident protocol, refusals in free-form
text with no framing ritual, exit code ignored, and — the prize — **a 30-point sweep
is one launch, not thirty**. The optimiser's ~400 ms of host overhead per iteration
means a drop-in's startup cost is not the bottleneck either.

**Dialect: the widest of the three.** `TL`/`NT` were already required by #390. 4nec2
adds surface patches (`SP`/`SM`/`SC`), geometry transforms (`GX`, `GR`, `GC`, `GH`,
`GM`), and the `WG`/`GF` Green's-function side-file with its `NX` multi-structure
handoff. And two silent manufacturings — `EX 6` into `NT`, `GN 3` into `GD` — put
network solving and substituted ground physics into decks whose authors wrote
neither.

**The NEC-4 slot is a separate decision** and should not be taken on the strength of
the NEC-2 answer.

The good news is real: the single scariest item evaporated. `SY` saturates 37% of the
corpus and never reaches the engine, along with AWG gauges, imperial units, traps and
wire-coating. What is left is honest NEC surface, not 4nec2 idiosyncrasy — which is
the right kind of work to be quoting.

Scope decision, for a separate issue as in #390: the same three options apply, and
the same third one looks best — put the seam where the parsing already lives.

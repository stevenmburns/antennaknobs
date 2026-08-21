# EZNEC capture session — 2026-08-20 (momwire#456, Target 1)

Ground-type cycle on `Vert1`, closing the 2026-08-16 capture doc's "perfect ground
and MININEC-type ground unsampled" gap. I/O observation only; no interpretation of
results here — that belongs against the oracle.

**Captures `0043`–`0048`.** Harness: `scripts/eznec_spy`, shim rebuilt from source
this session (capture root baked to `scratch/eznec-capture`), installed 08:12 local,
uninstalled 08:24 with the hash-verify passing. Engine restored to its original
10,804,224 bytes / Aug-16 mtime, no `.real.exe` residue.

Model `C:\EZNEC 7.0\Docs\Ant\Vert1.ez` — `CM Vertical over real ground`, a single
`GW 1,10,0.,0.,0.,0.,0.,10.3,.02`. Engine `External NEC-5`, invoked argv-form as
`"…\NEC5CL_x13.exe" "EZN5.NEC" "NEC5.OUT"`, cwd `C:\EZNEC 7.0\Docs`, stdin unused,
exit 0 throughout.

## What was clicked, in order

| # | capture | ground setting | click | `FR` | ground card | request tail | ms | printout |
|---|---|---|---|---|---|---|---|---|
| 1 | — | Free space | Src Dat | — | — | — | — | **refused, no launch** |
| 2 | — | Free space | FF Plot | — | — | — | — | **refused, no launch** |
| 3 | `0043` | Perfect | Src Dat | `7.` | `GN 1` | `XQ 0` | 118 | 6,904 B |
| 4 | `0044` | Perfect | FF Plot | `7.` | `GN 1` | `RP 0,181,1,1000,90.,0.,-1.,0.,0.` | 21 | 29,443 B |
| 5 | — | Real/MININEC | Src Dat | — | — | — | — | **skipped launch** |
| 6 | `0045` | Real/MININEC | FF Plot | `7.` | `GD 0,0,0,0,13.,.005,1.,0.` | `RP 0,181,1,1000,90.,0.,-1.,0.,0.` | 30 | 29,851 B |
| 7 | — | Real/MININEC | Src Dat (retry, window closed first) | — | — | — | — | **skipped launch** |
| 8 | `0046` | Real/MININEC | Src Dat (after `FR` nudge) | `7.01` | `GD 0,0,0,0,13.,.005,1.,0.` | `XQ 0` | 19 | 7,312 B |
| 9 | `0047` | Real/High Accuracy | FF Plot | `7.` | `GN 0,0,0,0,13.,.005,1.,0.` | `RP 0,181,1,1000,90.,0.,-1.,0.,0.` | 122 | 29,944 B |
| 10 | — | Real/High Accuracy | Src Dat | — | — | — | — | **skipped launch** |
| 11 | `0048` | Real/High Accuracy | Src Dat (after `FR` nudge) | `7.02` | `GN 0,0,0,0,13.,.005,1.,0.` | `XQ 0` | 101 | 7,405 B |

Launch accounting: `LastRun.log` ended with **6** `Running ext engine` lines against
**6** capture directories. Every launch is accounted for and no capture is missing.

## Ground card per menu setting

The card each menu setting emits, payload verbatim, same model and same session:

| menu setting | emitted ground card |
| --- | --- |
| Free space | *(not obtainable on this model — see anomaly 1; `GN -1` elsewhere in corpus)* |
| Perfect | `GN 1` |
| Real / MININEC type | `GD 0,0,0,0,13.,.005,1.,0.` |
| Real / High Accuracy | `GN 0,0,0,0,13.,.005,1.,0.` |

The MININEC decks (`0045`, `0046`) carry a `GD` card and **no `GN` card at all**.
Stated as an observation about the emitted bytes, not a claim about what it means.

This settles a `GD`-vs-`GN 0,…` ambiguity the earlier Vert1 captures left open:
`0015` emitted the bare `GD` form and `0021`/`0022` the `GN 0,…` form, with no record
of which menu setting produced which.

## Anomalies

1. **Free space is unrunnable on this model.** Both clicks raised EZNEC's
   "sources incorrectly placed" popup. `LastRun.log` records `MM SD` / `MM CR` with
   no `Running ext engine` between them — EZNEC refused at its own validation stage,
   nothing crossed the process boundary, no deck was emitted. Not a harness failure,
   and not a coverage loss: free space (`GN -1`) is already sampled 14× in this
   corpus.
2. **Src Dat skipped its launch on both real-ground settings** — twice under
   MININEC (plain click, then again after closing and reopening the Src Dat window)
   and once under High Accuracy. Under perfect ground the same click launched
   normally. In each skip `LastRun.log` shows `MM SD` … `MM Done SD` with no launch.
   The README's documented remedy worked both times: nudge `FR` so the model leaves
   an already-computed state, then click again.
3. **Consequence of that remedy:** `0046` sits at 7.01 MHz and `0048` at 7.02 MHz,
   so neither is byte-comparable to its FF Plot partner — they differ in `FR` as well
   as the request tail. `0043`/`0044` (perfect ground) *are* a clean pair: byte
   identical apart from timestamp and tail.
4. **Ground-contact warning on selecting Real/High Accuracy** — advisory, not
   blocking; the run proceeded and captured. The engine's own printout in `0047`
   echoes the same caveat verbatim:
   `WHERE WIRE ENDS TOUCH GROUND, CURRENT WILL BE INTERPOLATED TO IMAGE IN GROUND PLANE.`
   followed by `Will compute Sommerfeld-ground tables` /
   `FINITE GROUND.  SOMMERFELD SOLUTION`.
5. **The capture doc's premise was partly stale.** Perfect ground was *not*
   unsampled — `GN 1` already appears in captures `0019` (Vert1), `0027` and `0032`.
   What today's run adds there is the first perfect-ground *pattern* deck on this
   model; `0019` was Src Dat (`XQ 0`) only. MININEC-type was a genuine gap.

---

# EZNEC capture session — 2026-08-20 evening (windows sitting 4, momwire#456 ws3/ws5)

Plan: `WINDOWS-SESSION-4.local.md`. Five jobs, one trip. Jobs 1–4 run against the
REAL engine behind the spy shim; Job 5 replaces the engine binary, so it goes last.

**Captures `0049`–`0123`** (75 this sitting; 73 committed here — `0122`/`0123` are held in the private W7EL set, see Job 4; public corpus now 122). Harness:
`scripts/eznec_spy`, shim rebuilt from source this session (capture root baked to
`scratch/eznec-capture`), installed 20:07 local / 03:08:03Z, uninstalled 23:12 with
**the hash-verify passing**. Real engine restored to its original 10,804,224 bytes,
Aug-16 14:58 mtime, sha256 `4FFAC711…5A01D7C`; no `.real.exe` residue. All six Job-5
test artifacts removed from `C:\EZNEC 7.0\Docs` (`momwire_engine.exe`,
`momwire_real.exe`, `engine_test.exe`, `slow_engine.exe`, `_internal/`,
`engine_probe.log`).

Pre-flight: repo at `bc3e61f00` / `v0.55.0`, tree clean. EZNEC closed at install
time. Contrary to the plan's assumption, the engine selection did **not** persist (Finding 1) — EZNEC opened on `EZCalcD`
and had to be re-pointed at `External NEC5` before Job 1.

## Job 1 — the 33 uncaptured bundled models

| # | capture | model | ground card | click | ms | printout | notes |
|---|---|---|---|---|---|---|---|
| 1 | `0049` | `4Square TL ARRL Example` | `GD 0` | Src Dat | 119 | 28,017 B | `EX 4` current source; virtual wire #5 at ~4,193 m, `LD 4` open-circuit on 3 segs; EZNEC warned about virtual wires (advisory) |
| 2 | `0050` | `4Square TL ARRL Example` | `GD 0` | FF Plot | 38 | 72,516 B | `RP 0,1,361,1000,67.,…` — clean pair with 0049 |
| 3 | `0051` | `Cardioid TL ARRL Example` | `GD 0` | Src Dat | 23 | 20,863 B | `EX 4,3,1`; title `Cardioid with feed system` |
| 4 | `0052` | `Cardioid TL ARRL Example` | `GD 0` | FF Plot | 25 | 65,362 B | `RP 0,1,361,1000,80.,…` — clean pair with 0051 |
| 5 | `0053` | `Legacy\Diptl` | **`GD 0`** | Src Dat | 25 | 15,536 B | `EX 4,4,1`; title `Dipole with coax feedline` |
| 6 | `0054` | `Legacy\Diptl` | **`GD 0`** | FF Plot | 20 | 38,075 B | `RP 0,181,1,1000,90.,…` |
| 7 | `0055` | `Legacy\DipTLxx` | **`GN 0`** | Src Dat | **289** | 15,641 B | same title/constants as 0053, different ground mnemonic — see Anomaly 1 |
| 8 | `0056` | `Legacy\DipTLxx` | **`GN 0`** | FF Plot | 27 | 38,120 B | `RP 0,181,1,1000,90.,…` |
| 9 | `0057` | `Bydipole1` | `GN 0` | Src Dat | 17 | 7,561 B | `EX 4,1,6`; title `Back yard dipole` |
| 10 | `0058` | `Bydipole1` | `GN 0` | FF Plot | 26 | 30,100 B | `RP 0,181,1,1000,90.,…` |
| 11 | `0059` | `Byvee` | `GN 0` | Src Dat | 22 | 7,464 B | `EX 4,1,-1`; title `Back yard inverted vee` |
| 12 | `0060` | `Byvee` | `GN 0` | FF Plot | 19 | 30,003 B | `RP 0,181,1,1000,90.,…` |
| 13 | `0061` | `Legacy\Bydipole` | `GD 0` | Src Dat | 19 | 7,561 B | byte-identical to 0057 apart from the ground mnemonic |
| 14 | `0062` | `Legacy\Bydipole` | `GD 0` | FF Plot | 24 | 30,100 B | byte-identical to 0058 apart from the ground mnemonic |
| 15 | `0063` | `15mquad` | `GN -1` free space | Src Dat | 25 | | `EX 4,5,4`; title `15m Quad (Ant Book p. 12-2)` |
| 16 | `0064` | `15mquad` | `GN -1` | FF Plot | 29 | | `RP 0,1,361,1000,90.,…` azimuth |
| 17 | `0065` | `20m5elya` | `GN -1` | Src Dat | 26 | | `EX 4,12,2`; title `Five-element Yagi` |
| 18 | `0066` | `20m5elya` | `GN -1` | FF Plot | 55 | | **3-D pattern** `RP 0,37,73,1001,0.,0.,5.,5.,0.` — 37x73 = 2,701 pts, XNDA 1001. Satisfies part of the plan's P2 3-D ask, unprompted |
| 19 | `0067` | `Nbsyagi` | `GN -1` | Src Dat | 25 | | `EX 4,2,6`; title `NBS Yagi (ANT. BOOK p. 18-7)` |
| 20 | `0068` | `Nbsyagi` | `GN -1` | FF Plot | 23 | | `RP 0,1,361,1000,90.,…` azimuth |
| 21 | `0069` | `W8jk` | `GN 0` | Src Dat | **262** | | `EX 4,1,6`; second Sommerfeld table build of the session (new ground constants) |
| 22 | `0070` | `W8jk` | `GN 0` | FF Plot | 21 | | `RP 0,181,1,1000,90.,…` elevation; table now cached |
| 23 | `0071` | `Logper` | `GN -1` | Src Dat | 23 | | `EX 4,19,-1`; **no** TL rows; title `17-10m Log Per - ARRL Ant Book` |
| 24 | `0072` | `Logper` | `GN -1` | FF Plot | 28 | | `RP 0,1,361,1000,90.,…` |
| 25 | `0073` | `Logpertl` | `GN -1` | Src Dat | 47 | | same title as 0071 but **5 `TL` rows** + `LD` — the matched with/without-TL contrast |
| 26 | `0074` | `Logpertl` | `GN -1` | FF Plot | 29 | | `RP 0,1,361,1000,90.,…` |
| 27 | `0075` | `Fdsp1` | `GN 0` | Src Dat | **314** | | third Sommerfeld table build of the session; title `Field Day Special (Jun 84 QST)` |
| 28 | `0076` | `Fdsp1` | `GN 0` | FF Plot | 21 | | table cached |
| 29 | `0077` | `Legacy\Fdsp` | `GD 0` | Src Dat | 29 | | same title/constants as 0075, MININEC ground instead |
| 30 | `0078` | `Legacy\Fdsp` | `GD 0` | FF Plot | 19 | | |
| 31 | `0079` | `K5rp` | `GN 0` | Src Dat | **277** | | **`EX 0,1,4` — the first voltage source of the session; closes the `EX 0` hunt** |
| 32 | `0080` | `K5rp` | `GN 0` | FF Plot | 47 | | **3-D** `RP 0,19,73,1001,…` (19x73) — a grid shape new to the corpus |
| 33 | `0081` | `N4pcloop1` | `GN 0` | Src Dat | **420** | | slowest launch of the session; title `N4PC Loop (CQ, Dec. 1990)` |
| 34 | `0082` | `N4pcloop1` | `GN 0` | FF Plot | 37 | | **3-D** `RP 0,13,49,1001,…` (13x49) — another new grid shape |
| 35 | `0083` | `Legacy\N4pcloop` | `GD 0` | Src Dat | 31 | | MININEC twin of 0081 |
| 36 | `0084` | `Legacy\N4pcloop` | `GD 0` | FF Plot | 43 | | **3-D**, same 13x49 grid |
| 37 | `0085` | `Vhfgp` | `GN -1` | Src Dat | 17 | | title `VHF Ground Plane` |
| 38 | `0086` | `Vhfgp` | `GN -1` | FF Plot | 44 | | **3-D** `RP 0,37,73,1001,…` |
| 39 | `0087` | `4Square L Network Feed ARRL Example` | `GD 0` | Src Dat | 33 | | `NT`=1, `TL`=4, single `EX 4,5,1` |
| 40 | `0088` | `4Square L Network Feed ARRL Example` | `GD 0` | FF Plot | 38 | | completes the pair 0023 left half-open |
| 41 | `0089` | `4Square L Network Feed With Z Matching` | `GD 0` | Src Dat | 23 | | **`NT`=3, `TL`=4 — the richest network deck in the corpus** |
| 42 | `0090` | `4Square L Network Feed With Z Matching` | `GD 0` | FF Plot | 35 | | completes the pair 0025 left half-open |
| 43 | `0091` | `4square` | `GD 0` | Src Dat | 23 | | **4 `EX` cards** (multi-source), no `NT`/`TL`; title `40-meter four-square array` |
| 44 | `0092` | `4square` | `GD 0` | FF Plot | 25 | | completes the pair 0031 left half-open |
| 45 | `0093` | `Cardioid` | `GN 1` perfect | Src Dat | 20 | | 2 `EX` cards, no `NT`/`TL` |
| 46 | `0094` | `Cardioid` | `GN 1` | FF Plot | 25 | | completes the pair 0032 left half-open |
| 47 | `0095` | `Cardioid L Network Feed ARRL Example` | `GD 0` | Src Dat | 28 | | `NT`=1, `TL`=2 |
| 48 | `0096` | `Cardioid L Network Feed ARRL Example` | `GD 0` | FF Plot | 35 | | completes the pair 0000 left half-open |
| 49 | `0097` | `4sqtl` | `GD 0` | Src Dat | 28 | | `TL`=6; **not** byte-identical to `4Square TL ARRL Example` (0049) — 24 lines differ |
| 50 | `0098` | `4sqtl` | `GD 0` | FF Plot | 24 | | |
| 51 | `0099` | `CardTL` | `GN 1` perfect | Src Dat | 22 | | `TL`=2; differs from `Cardioid TL ARRL Example` (0051) by 16 lines, and by ground type |
| 52 | `0100` | `CardTL` | `GN 1` | FF Plot | 24 | | |
| 53 | `0101` | `DipTL1` | `GN 0` | Src Dat | **294** | | differs from `Legacy\Diptl` (0053) by only **2 lines** — the closest near-twin pair in the corpus |
| 54 | `0102` | `DipTL1` | `GN 0` | FF Plot | 38 | | |
| 55 | `0103` | `Elevrad1` | `GN 0` | Src Dat | **304** | | **`EX 0,1,-1`** voltage source |
| 56 | `0104` | `Elevrad1` | `GN 0` | FF Plot | 32 | | completes the pair 0033 left half-open |
| 57 | `0105` | `Elevrad2` | `GN 0` | Src Dat | 34 | | **`EX 0,1,2`**; 51 lines differ from Elevrad1 — genuinely distinct models sharing a title |
| 58 | `0106` | `Elevrad2` | `GN 0` | FF Plot | 49 | | completes the pair 0034 left half-open |

**Job 1 complete.** Every bundled model under `Docs\Ant` and `Docs\Ant\Legacy` now
has captures — 29 models clicked this sitting (`0049`-`0106`, 58 captures), the
remaining three (`Dipole1`, `Vert1`, `Network connection test`) already covered by
earlier sessions. `LAST.EZ` skipped by instruction. No fifteenth mnemonic appeared:
the corpus vocabulary stands at `CE CM EN EX FR GD GE GN GW LD NT PQ RP TL XQ`.

Filenames carry real information: every same-title pair tested came back with a
*different* deck body (`4sqtl` vs `4Square TL ARRL Example`, 24 lines; `CardTL` vs
`Cardioid TL ARRL Example`, 16; `DipTL1` vs `Legacy\Diptl`, 2; `Elevrad1` vs
`Elevrad2`, 51). Same `CM` title never meant the same model.


## Job 2 — the NE gate captures (un-refuses 0022)

Grid used throughout on `Vert1`: X 1..5 step 1, Y 0, Z 2..10 step 2 — a vertical
plane offset from the wire, 25 points, emitted as `NE 0,5,1,5,1.,0.,2.,1.,0.,2.`.
Printout row order is **X fastest, Z slowest**.

| # | capture | model | ground | card | ms | rows | notes |
|---|---|---|---|---|---|---|---|
| 1 | `0107` | `Vert1` | `GD 0` MININEC | `NE 0,1,1,1,0.,…` | 153 | 1 | the degenerate origin-point default, reached by clicking `NF Tab` with a virgin dialog — same shape as `0022` but under MININEC |
| 2 | `0108` | `Vert1` | `GD 0` MININEC | `NE 0,5,1,5,…` | 29 | 25 | first real grid |
| 3 | `0109` | `Vert1` | `GN 1` perfect | `NE 0,5,1,5,…` | 27 | 25 | |
| 4 | `0110` | `Vert1` | `GN 0` Sommerfeld | `NE 0,5,1,5,…` | 99 | 25 | |
| — | — | `Vert1` | free space | — | — | — | **refused, no launch** — "sources incorrectly placed", as session 3 documented. Expected; `Vert1`'s base stands on the ground |
| 5 | `0111` | `Vert1` | `GN 0` Sommerfeld | **`NH 0,5,1,5,…`** | 31 | 25 | **new mnemonic — see Headline** |
| 6 | `0112` | `Vert1` | `GN 0` Sommerfeld | `NE 0,1,1,1,0.,…` | 19 | 1 | `0022`'s exact shape under `GN 0` — the byte-continuity item |

`0108`/`0109`/`0110` differ **only** in their ground card — same `FR 7.`, same `NE`
card, same 25 rows. That is the gate family Job 2 was after.

| 7 | `0113` | `Bydipole1` | `GN 0` Sommerfeld | `NE 0,5,1,5,.3048,…` | 666 | 25 | **units finding — see below**; slowest launch of the session (new Sommerfeld table at 14 MHz) |
| — | `0114` | `Bydipole1` | `GN -1` free space | *(`RP`)* | 22 | — | **mis-click**: `FF Tab` not `NF Tab` (log says `MM TA`). Harmless; kept as a free-space far-field table |
| 8 | `0115` | `Bydipole1` | `GN -1` free space | `NE 0,5,1,5,.3048,…` | 18 | 25 | the free-space near field `Vert1` cannot produce |

**Job 2 complete.** The `NE`/`NH` family went from 1 capture (`0022`) to 9, spanning
all four ground types, both grid shapes (degenerate 1x1x1 and 5x1x5), both field
types, and two models in two unit systems:

| ground | `NE` grid | `NE` origin-point | `NH` grid |
|---|---|---|---|
| free space `GN -1` | `0115` | — | — |
| Sommerfeld `GN 0` | `0110`, `0113` | `0022`, `0112` | `0111` |
| perfect `GN 1` | `0109` | — | — |
| MININEC `GD 0` | `0108` | `0107` | — |

Note also that free space changes the `GE` flag: grounded decks carry `GE 1,-1`,
the free-space ones `GE 0,-1`.

### Near-field coordinates are entered in display units and emitted in metres

`Vert1` is a metres model, `Bydipole1` a feet model. The same typed grid (start 1,
step 2) emitted:

| model | display units | emitted `NE` payload |
|---|---|---|
| `Vert1` | metres | `…,1.,0.,2.,1.,0.,2.` |
| `Bydipole1` | feet | `…,.3048,0.,.6096,.3048,0.,.6096` |

0.3048 and 0.6096 are 1 ft and 2 ft exactly. The dialog's column headers track the
model's units (`X (m)` on `Vert1`), and the deck is **always metric**. This settles
the open units question in `scratch/qrz-lfa-thread/README.md` ahead of Job 4: the
coupled-loop deck will come out in metres whatever its `MFT` flag displays as.

### HEADLINE — EZNEC emits `NH`, and momwire 0.35.0 refuses it by name

Capture `0111` is the **only `NH` in the 113-capture corpus**. It costs one radio
button: the Near Field Analysis dialog (reached from the `Setups` menu) has a
`Field: E / H` pair, and selecting `H` swaps the emitted card from `NE` to `NH`
with an otherwise identical ten-field payload.

momwire 0.35.0's nec5 dialect refuses it, on a premise this capture falsifies —
`momwire/src/momwire/deck/_nec5.py:403`:

> `NH` (near magnetic field) **has never been emitted by EZNEC** and is not part of
> this engine's nec5 dialect; `NE` (near electric field) is the near-field card this
> seam serves

The dialect's accepted set is 16 mnemonics (`CM CE GW GE GN GD EX LD TL NT FR PQ RP
XQ NE EN`) and `NH` is not among them, so this deck is refused by name today.

The repair looks small: `deck/_nec2.py:48` already lists `NH` in `_EXECUTE_CARDS`
and `:694` already carries `magnetic=card.mnemonic == "NH"`, so the field machinery
exists — only the nec5 front-end's allow-list and this refusal string are wrong.
Oracle now in hand: header `- - - NEAR MAGNETIC FIELDS - - -`, columns
`HX/HY/HZ` magnitude+phase in `AMPS/M`, same X-fastest 25-row layout as `NE`.

Corpus mnemonic census after this sitting — **17 distinct**, with first appearance:
`CE CM EN EX FR GE GW PQ` (0000), `GD` (0000), `NT` (0000), `RP` (0000), `TL` (0000),
`LD` (0000), `GN` (0010), `XQ` (0002), `NE` (0022), **`NH` (0111)**.

## Job 3 — phased drive through a network (momwire#511)

**Deviation from the plan, deliberate.** The plan called for a transmission line run
out to a new virtual wire, and for the second model to be `Cardioid with feed system`
(TL-only). Both were changed for something cheaper and richer:

- part 1's line connects **two real driven elements** instead of a virtual wire — the
  virtual-wire machinery buys nothing when the goal is just multi-source + `TL` in
  one deck;
- part 2 used `Cardioid L Network Feed ARRL Example` instead, because it already
  carries `NT` **and** `TL`, so adding a source yields all three at once.

| # | capture | model | modification | click | ms | notes |
|---|---|---|---|---|---|---|
| 1 | `0116` | `4square` | added `TL` wire 1 @50% to wire 3 @50%, 50 ohm, 10 ft, VF 1, loss 0 @10 MHz | Src Dat | 25 | **4 `EX` + 1 `TL`** — emitted `TL 1,3,3,3,50.,3.048,…` (3.048 m = the 10 ft entered) |
| 2 | `0117` | `4square` | same | FF Plot | 21 | `RP 0,1,361,1000,67.,…` |
| — | `0118` | `Cardioid L Ntwk Feed` | *(void)* | Src Dat | 22 | **VOID** — the existing source was edited rather than a second added; deck still has 1 `EX`, relocated to wire 2 |
| — | `0119` | `Cardioid L Ntwk Feed` | *(void)* | FF Plot | 31 | **VOID**, same cause |
| 3 | `0120` | `Cardioid L Ntwk Feed` | added 2nd source, wire 2 @0%, amplitude 1, phase -90 | Src Dat | 29 | **2 `EX` + 2 `TL` + 1 `NT`** — the richest deck in the corpus |
| 4 | `0121` | `Cardioid L Ntwk Feed` | same | FF Plot | 33 | `RP 0,1,361,1000,80.,…` |

**Job 3 complete.** Before this sitting, no deck in 113 captures combined
multi-source with `NT` or `TL`; the two sets were disjoint. There are now four such
decks, covering both sides the plan wanted:

- **TL side** — `0116`/`0117`: four sources at four phases through one transmission line
- **NT side** — `0120`/`0121`: two sources 90 degrees apart through an L-network **and**
  two transmission lines

Neither model was saved over its original; both edits live only in these captures.
`0118`/`0119` are left on disk rather than deleted, marked void here so the index
does not read them as intentional coverage.

## Job 4 — Roy's coupled-loop model

`scratch/qrz-lfa-thread/NEC-4 coupled loop.ez`, 1,877 B,
md5 `0659f9d0c7dcd9bb8c18022f421dec7c` - transferred and verified this session.

| # | capture | click | ms | notes |
|---|---|---|---|---|
| 1 | `0122` | Src Dat | 25 | `XQ 0`; title `NEC-4 Example` |
| 2 | `0123` | FF Plot | 19 | `RP 0,1,361,1000,90.,…` |

**`0122`/`0123` are not in this tree.** They are the spy's record of Roy's
model and carry its full deck, so they live with the rest of the W7EL set in
the untracked private companion directory (`scratch/qrz-lfa-thread/`) until
the contact sequence has happened — the same rule the PR applies to the
`.ez` and the exports. The findings below are the citable record; the
capture ids refer to the private copies.

### Every open question in the README, answered

| question | README's guess | deck says |
|---|---|---|
| frequency | 5 MHz (header float 5.0) | **0.0005 MHz = 500 Hz** - the decode found the mantissa, missed the exponent |
| units | `MFT` flag, undetermined | **metres** - the deck echoes the decoded (20,-40,300) verbatim |
| source position | not decoded | wire 1 segment 14 (90% of 15 segs) |
| source type | not decoded | **`EX 0`** - a voltage source, the corpus's rare form |
| ground | not decoded | free space (`GN -1`, `GE 0,-1`) |

**Correction to the decode:** the README recorded "radius field 0.01". The deck emits
`.005`. That field is a **diameter**, not a radius.

**Peak vs RMS, confirmed twice.** EZNEC displayed the source as 286,149 V; the deck
carries 404,675.9. The ratio is sqrt(2) exactly - the same relation seen in the
near-field table (`0107`: 471.465 V/m displayed, 6.6673E+02 printed). EZNEC displays
RMS; the deck and the engine printout carry peak.

### W7EL's pathology reproduced, against a NEC-5 control on the same deck

The whole point of the model. Same six wires, same 500 Hz, same voltage source,
same machine, minutes apart - only the engine changed:

| engine | source current | max loop current (wires 2-6) |
|---|---|---|
| **NEC-5** (external, capture `0122`) | 1.0367 A | **1.0 x 10^-6 A** |
| **NEC-2** (internal `EZCalcD_70_x64.EXE`) | **0.7325 A** | **162 A** |

Both halves of Roy's QRZ post #11 claim land as stated: the source delivers **under
1 A** while the small horizontal loop carries **over 150 A**. Between engines the loop
current differs by a factor of **1.6 x 10^8**. Under NEC-5 the loop current is
221 million times *smaller* than the feed current; under NEC-2 it is 221 times
*larger*.

This is consistent with Burke's attribution (quoted by Roy): quadrature error in the
line integral of grad(phi) around the loop, growing as 1/f - hence the deliberate
500 Hz - and absent from NEC-5's basis.

**Not captured:** the NEC-2 run launched `EZCalcD_70_x64.EXE`, an internal engine at a
path the spy does not shim, so no capture directory exists for it. The numbers above
were read off EZNEC's own Src Dat and Currents displays. Shimming `EZCalcD` would be
a separate install if a byte-level record of the NEC-2 side is ever wanted.

### The `.nec` export, and proof that "NEC-5 format" is a real dialect

`File > Save As` offers a `.nec` type. The written deck is **not** what the engine
receives: it carries `GE 0` rather than `GE 0,-1`, omits `PQ 0`, and includes the
`RP` card. Its third line names the format, and that label tracks the selected
calculating engine.

**Coupled loop - no divergence.** Exported once per engine, the two files are
byte-identical apart from the `NEC-2 format` / `NEC-5 format` comment (body md5
`58ddcc12`, 397 B each). That model uses only `GW/GE/FR/GN/EX/RP/EN` - cards both
dialects share - and a voltage source. Convenient for the Roy story: the pathology
comparison is provably the same cards fed to two engines.

**`Cardioid L Network Feed` - substantial divergence.** Re-run on a model using
`GD` ground plus `TL` and `NT`, the exports differ in five ways:

| | NEC-5 export (1,348 B) | NEC-2 export (1,677 B) |
|---|---|---|
| source | `EX 4,3,1,…` native current source | `EX 0,4,2,…` **voltage** source **plus** `NT 4,2,3,2,0.,0.,0.,1.,0.,0.` |
| MININEC ground | `GD 0,0,0,0,13.,.005,1.,0.` | `GN 1,0,0,0,0.,0.` **plus** `GD 2,0,0,0,13.,.005,0.,0.` |
| geometry | wire 3 with 3 segs | wire 3 with 4 segs **plus a new wire 4** |
| loads | `LD 4,1,-1,…` | `LD 4,1,1,…` |
| pattern request | `RP 0,…` | `RP 3,…` |

EZNEC documents the substitutions in its own comment block:

    CM ! Wire #4 for I srcs, shorted/open TL, and/or parallel loads.
    CM ! NT #1 is EZNEC current source
    CM ! WARNING: MININEC-type ground may not work properly with standard
    CM !          NEC-2 or -4 program.

NEC-2 has no current source, so EZNEC synthesises one from a voltage source and an
ideal-transformer `NT` on a helper wire; MININEC ground becomes perfect ground plus
a `GD 2` second-medium card, with a warning that it may not work at all.

**Why this matters to the seam.** `EX 4` and `GD 0` are NEC-5-native forms with no
NEC-2 equivalent - which is why momwire's nec5 front-end has to serve them directly
rather than translating. The dialect is real, and the divergence is concentrated
exactly where the front-end already draws its line.

Files kept in `scratch/qrz-lfa-thread/`: `coupled-loop-nec5.nec`,
`coupled-loop-nec2.nec`, `cardL-nec5.nec`, `cardL-nec2.nec` (plus two earlier
same-body saves, `NEC-4 coupled loop.nec` and `NEC-5 coupled loop.nec`).

**Job 4 complete.**

## Job 5 — the ws5 freeze smoke test

**The plan's binary swap was not needed.** Because the engine path is a browsable
absolute path (Finding 3), EZNEC can be pointed straight at a frozen exe wherever it
sits. No renaming of the real engine, no backup/restore dance, nothing at risk. The
spy shim stays installed at `NEC5CL_x13.exe` and is simply bypassed while EZNEC
points elsewhere.

### Build

`.venv-freeze` (Python 3.12.1) with `momwire==0.35.0` + `pyinstaller 6.22.2`, built
off a four-line entry shim calling `momwire.eznec.main`. Built both variants:

| variant | size | files |
|---|---|---|
| onefile | 50,187,770 B single exe | 1 |
| onedir | 120 MB bundle | 147 |

### Standalone smoke — it serves

Run against capture `0010`'s deck (`Dipole in free space`, 299.7925 MHz): exit 0,
full NEC-5-shaped printout, 50,967 B against the real engine's 51,482 B, same 515
lines, same CRLF endings, same structure and geometry blocks.

### Launch economics — the cost is Python, not PyInstaller

CPU: 12th Gen Intel Core i5-1240P.

| engine | per launch | vs real engine |
|---|---|---|
| real NEC-5 (`NEC5CL_x13.real.exe`) | 18-37 ms | 1x |
| momwire, plain interpreter | ~1,480 ms | ~50x |
| momwire, PyInstaller **onedir** | ~1,285 ms warm (2,049 first) | ~45x |
| momwire, PyInstaller **onefile** | **~17,000 ms every launch** | ~600x |

A bare `import momwire.eznec` costs **1,504 ms** on its own - the whole onedir launch
budget. So:

* **onefile is disqualified.** It re-unpacks a 50 MB archive on every launch and
  shows no warm-up benefit at all (17.1 s, 17.1 s, 16.8 s on repeat runs). That is
  ~13x the onedir cost purely in unpacking.
* **onedir costs essentially nothing over the interpreter.** Freezing is not the
  problem.
* **The floor is the numpy/scipy import**, and no packaging choice can go below it.
  Beating ~1.3 s needs deferred imports inside momwire, not a better freezer.

Projected SWR sweep of 50 points: real engine ~1-2 s total; momwire onedir ~65 s;
momwire onefile ~14 minutes.

### Numerical agreement — divergence is pre-existing and already gated

The frozen printout is **bit-identical to the unfrozen interpreter's**, so freezing
changes nothing numerically. It differs from the real engine's numbers (source
impedance 85.073 + 45.369j against 79.948 + 29.919j), but that exact pair is already
recorded in momwire's own suite at `tests/test_eznec_serve.py:218`:

    #   0010  79.948 +29.919j      85.073 +45.369j    16.278   2.18/2.09   0.09

a documented 16.278% tolerance, not a new defect and not a freeze artifact. The seam
gates envelopes, not numeric bytes.

### HEADLINE 2 — momwire 0.35.0 writes LF printouts; EZNEC requires CRLF

**The drop-in works. One character stops it.**

`momwire/src/momwire/eznec/_shell.py:95` writes the printout as:

    with printout_path.open("w", encoding=_CODEC, newline="\n") as handle:

The real engine writes **CRLF**. Byte counts on the same deck, same moment:

| | CR bytes | LF bytes | size |
|---|---|---|---|
| real `NEC5CL_x13.real.exe` | 144 | 144 | 6,983 B |
| momwire | **0** | 144 | 6,839 B |

The size gap is exactly the missing CRs (144 = the line count; on the larger `0010`
deck, 51,482 - 50,967 = 515 = its line count). Everything else is byte-identical:
the header, the banner, the echoed `CM` timestamp, the section order, the column
layout. Only 50 numeric lines differ, and those by the already-gated tolerance.

EZNEC's refusal names a file it never even looks for:

> Calculating engine is malfunctioning or not present. Output file **NEC.OUT** is
> present, but was written earlier from another calculation

`NEC.OUT` never existed at any point (the instrumented run proves EZNEC passed
`"EZN5.NEC" "NEC5.OUT"`). The filename in the message is a hardcoded label and the
"written earlier" clause is what an unparseable printout degrades into - a badly
misleading diagnostic that cost most of this job's debugging time.

**Why momwire's own gates never caught it.** The fixtures are correct - e.g.
`0000_cardioid-l-network-feed.out` has CR=679, LF=679, proper CRLF. The byte-gates
compare the *rendering function's string*, not the bytes the shell writes to disk.
The single `newline="\n"` on the file write is the one step no test observes.

**Fix:** `newline="\r\n"` at `_shell.py:95` (or `newline=""` with CRLF in the
rendered text). Nothing else in the seam needs to change.

**Proof.** A C# wrapper that runs the frozen momwire unchanged and converts LF to
CRLF before returning made EZNEC render momwire's results in its own viewer, first
try. Same engine, same numbers, same 1.0 s timing - only the line endings changed.

### What EZNEC actually requires of a drop-in engine

Established by controlled substitution, each variable changed alone:

| variable | verdict | evidence |
|---|---|---|
| **filename** | **free** | `engine_test.exe` (byte copy of the real engine, arbitrary name) worked |
| **directory** | **must be `C:\EZNEC 7.0\Docs`** | outside it, EZNEC sets the child's cwd to the *engine's* folder and writes `EZN5.NEC` there, then reads results from `Docs` - the two split and it fails |
| **latency** | **not a gate** | `slow_engine.exe` (real engine + a deliberate 2 s sleep) worked |
| **line endings** | **must be CRLF** | the only difference between momwire failing and succeeding |
| exit code | ignored | confirmed by the earlier fault-injection study |

So the plan's identity question for Roy is answered in its strongest form: a drop-in
needs **no name impersonation** and **no speed**, but must live in `Docs` and speak
CRLF.

### In-app behaviour, through the CRLF-corrected drop-in

| test | result |
|---|---|
| `Dipole1` Src Dat | renders in EZNEC's own viewer |
| `Vert1` over Real/High Accuracy | renders - momwire's Sommerfeld path drives the app |
| a deck momwire refuses (`NH` via Field: H) | EZNEC shows **"Unable to read NEC output file due to NEC program error"** |
| SWR sweep | **1-2 seconds per point** (measured), against the real engine's 18-37 ms |

**The refusal channel works, but the reason is one click down.** momwire writes a
textbook NEC error line:

    ***** NEC ERROR - NH (near magnetic field) has never been emitted by EZNEC and is
    not part of this engine's nec5 dialect; NE (near electric field) is the near-field
    card this seam serves

EZNEC's first dialog shows only the generic "Unable to read NEC output file due to
NEC program error" - but it then **offers to display the NEC5 output file**, where
the full reason is visible. So the refusal does reach the operator: the seam's
carefully worded messages are worth writing, they are simply not surfaced in the
first dialog.

This still compounds Headline 1: momwire refuses `NH` on a premise today's `0111`
falsifies, and a user must accept a second prompt to find out why.

**Measured sweep cost confirms the projection.** At 1-2 s per point, a 50-point sweep
costs 50-100 s where the real engine costs ~1-2 s total. Usable for single clicks,
painful for sweeps - and the fix is deferred imports in momwire, not packaging.

### Recommended path on launch cost: the client/server shape

Per the user, the portal has already been run as a long-lived server with light
client processes sending requests. That shape fits here exactly, and this sitting's
substitution tests say it is *allowed*:

* the drop-in **may be named anything** (`engine_test.exe` proved it), so the client
  can be a purpose-built stub;
* EZNEC **does not enforce a latency budget** (`slow_engine.exe`, real engine plus a
  deliberate 2 s sleep, was accepted), so even a cold-start handshake is safe;
* the client **must live in `C:\EZNEC 7.0\Docs`** and **must write CRLF** - the only
  two hard constraints found.

A thin client (a small native exe, no Python) that hands `EZN5.NEC`/`NEC5.OUT` to a
resident momwire server would drop the per-launch cost from ~1,300 ms to roughly
process-start plus IPC. That is plausibly in the real engine's own 18-37 ms band,
which no packaging choice can reach - the 1,504 ms `import momwire.eznec` is paid
once by the server instead of once per click. It also turns the 50-point SWR sweep
from 50-100 s back into a couple of seconds.

Worth noting the ordering: fix `newline="\r\n"` first, since it is one character and
gates everything; the server is the follow-on that makes the drop-in pleasant rather
than merely possible.

**Job 5 complete.**

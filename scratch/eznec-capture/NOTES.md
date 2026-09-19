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
| **NEC-5** (external, capture `0122`) | 1.0524 A | **0.4792 A** |
| **NEC-2** (internal `EZCalcD_70_x64.EXE`) | **0.7325 A** | **162 A** |

Both halves of Roy's QRZ post #11 claim land as stated: the source delivers **under
1 A** while the small horizontal loop carries **over 150 A**. Between engines the loop
current differs by a factor of about **338**. Under NEC-5 the loop carries roughly
half the feed current (0.46x), which is legitimate through-current - charge
distributed onto the loop by the 404 kV drive; under NEC-2 it is 221 times *larger*
than the feed, which is the pathology.

> **CORRECTION (2026-08-25).** As first written this table read `1.0 x 10^-6 A` for
> the NEC-5 loop current, and claimed a `1.6 x 10^8` ratio. **Both were wrong.** The
> figure was taken from the printout's **Wire Charge Densities** block, whose values
> are C/m, mistaken for a row of the Wire Currents block above it. Re-derived from
> capture `0122`'s own printout: vertical (tag 1) max 1.0524 A, loop (tags 2-6) max
> **4.79204E-01 A**. The qualitative finding is unchanged - NEC-2 exhibits the
> pathology and NEC-5 does not - but the magnitude was inflated by six orders of
> magnitude. Quote the printout, never the display, and never a neighbouring block.
> The corrected number agrees with `scratch/qrz-lfa-thread/README.md`, which reached
> it independently, and with momwire's own run (loop 4.80727E-01 A, within 0.5%).

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

---

# EZNEC capture session — 2026-08-25 (windows sitting 5, momwire#456 ws3)

Plan: `WINDOWS-SESSION-5.local.md`. Two jobs as handed over; **Job B was not run** -
see "Job B was already done" below. Engine binary untouched this trip.

**Captures `0124`-`0182`** (59 this sitting; corpus now 183). Harness: `scripts/eznec_spy`, shim rebuilt from source,
installed 22:53:32Z. Real engine archived to `NEC5CL_x13.real.exe`, sha256
`4FFAC711...5A01D7C`, 10,804,224 bytes - same engine as sitting 4.

Pre-flight: repo at `49eccf18c` / v0.58.0, momwire submodule fast-forwarded to
`a1bbbe5` / v0.39.0. As in sitting 4, the calculating-engine selection did **not**
persist across launches - EZNEC opened on `EZCalcD` and was re-pointed at
`External NEC5`.

## Job A — an NE grid with NY > 1

Grid throughout: **NX=2, NY=3, NZ=4** - three deliberately different counts, so row
order alone fixes the nesting with no ambiguity. Start (1,2,3), step (2,2,2), all
points >=1 unit clear of the wire and >=3 above ground so the contact cell cannot
swallow the capture. Emitted as `NE 0,2,3,4,1.,2.,3.,2.,2.,2.`, 24 rows.

| # | capture | model | ground | FR | ms | rows |
|---|---|---|---|---|---|---|
| 1 | `0124` | `Vert1` | `GD 0` MININEC | 7.00 | 277 | 24 |
| 2 | `0125` | `Vert1` | `GN 1` perfect | 7.00 | 24 | 24 |
| 3 | `0126` | `Vert1` | `GN 1` perfect | 7.01 | 27 | 24 |
| 4 | `0127` | `Vert1` | `GN 0` Sommerfeld | 7.02 | 333 | 24 |
| 5 | `0128` | `Vert1` | `GN 0` Sommerfeld | 7.00 | 329 | 24 |
| — | — | `Vert1` | free space | — | — | **refused, no launch** ("sources incorrectly placed", as sitting 4) |
| 6 | `0129` | `Bydipole1` | `GN 0` Sommerfeld | 14.0 | 652 | 24 |
| 7 | `0130` | `Bydipole1` | `GN -1` free space | 14.0 | 20 | 24 |

`0124` / `0125` / `0128` are a **clean three-ground family**: identical `NE` card,
identical `FR 7.`, differing only in the ground card. (`0126` and `0127` are the
frequency-nudged runs taken on the way and are not byte-comparable to them.)
`0130` supplies the free space that `Vert1` cannot produce.

### RESULT — the X/Y/Z nesting is now confirmed against EZNEC's own engine

The deliverable this trip existed for. Printed row order, `0124`:

    X   Y   Z            X   Y   Z
    1   2   3            1   2   5
    3   2   3    ...     3   2   5
    1   4   3            1   4   5
    3   4   3            3   4   5
    1   6   3            1   6   5
    3   6   3            3   6   5

**X varies fastest, then Y, then Z outermost** - exactly what `_serve.py:846-850`
assumed. With counts 2/3/4 all distinct there is no alternative reading, and the
feet-model captures (`0129`/`0130`) print the same order in converted metres
(0.3048/0.9144 fastest, then 0.6096/1.2192/1.8288, then Z), so the nesting is a
property of the card and not of the model's units.

This retires the "no capture separates the Y nesting from the Z one - every captured
grid is NY = 1" caveat in `_serve._grid_points`' docstring. The NE format family can
now be gated against EZNEC's own engine rather than the linux oracle of 2026-08-21.

## Job B — already done, not run

The plan listed eleven bundled models as "still uncaptured" (`Byvee`, `15mquad`,
`20m5elya`, `Nbsyagi`, `W8jk`, `Fdsp1`, `Legacy\Fdsp`, `K5rp`, `N4pcloop1`,
`Legacy\N4pcloop`, `Legacy\Bydipole`). **All eleven were captured in sitting 4** and
are on main: 0059/0060, 0063/0064, 0065/0066, 0067/0068, 0069/0070, 0075/0076,
0077/0078, 0079/0080, 0081/0082, 0083/0084, 0061/0062 respectively. Sitting 4 reached
every bundled model except `LAST.EZ`, so nothing in `Docs\Ant` was left to capture.

Its side-asks were stale for the same reason: 3-D `XNDA 1001` captures stand at
**7**, not 2, across three grid shapes (37x73, 19x73, 13x49).

**Where the plan's numbers came from.** "16 distinct models across 62 deck files"
describes **momwire's fixture corpus**, not this one - `momwire/tests/fixtures/eznec/`
holds exactly 62 decks / 16 model slugs, highest index 0121. The capture corpus holds
124 captures / 23 titles. So the models are not uncaptured; they are **captured but
not promoted into momwire's fixtures**, and closing that gap is a desk task in
momwire, not a trip to this box.

Running Job B as written would have been ~22 launches re-answering closed questions.

## The H field at NY > 1, and the format family closed

| # | capture | model | card | rows | header |
|---|---|---|---|---|---|
| 8 | `0131` | `Bydipole1` | `NH 0,2,3,4,.3048,…` | 24 | `- - - NEAR MAGNETIC FIELDS - - -` |

`NH` now exists at **both** NY=1 (`0111`, sitting 4) and NY>1 (`0131`), same as `NE`,
so the H-field column presence, the `AMPS/M` units and the row counts can be gated
across the same grid shapes as the electric family rather than at one shape only.

Still true, and still the open item from sitting 4: momwire 0.35.0 refuses `NH` by
name (momwire#513). These captures are its oracle whenever that is taken up.

## Launch economics of a real SWR sweep — the engine is 10 % of it

`Dipole1`, 51-point sweep, one launch per frequency point (`FR 300.`, `301.`, `302.`
… each with an `XQ 0` tail). Captures `0132`-`0182`.

| | |
|---|---|
| launches | 51 |
| engine ms, min / median / max | 15 / 24 / 36 |
| engine total | 1.27 s |
| wall-clock span (first start to last finish) | 12.41 s |
| per point | 243 ms |
| **engine share of wall clock** | **10.3 %** |

The median 24 ms sits inside sitting 4's 18-37 ms single-launch band, so the engine
does not slow down under repetition. **The other ~220 ms per point is EZNEC's own
work** - writing the deck, reading the printout, updating the plot - and it is paid
no matter how fast the engine is.

That puts a floor under any sweep and gives the client/server plan a concrete target:

| engine per launch | projected 51-point sweep |
|---|---|
| real NEC-5 (24 ms) | ~12.4 s (measured) |
| momwire one-dir frozen (~1,300 ms) | ~79 s |
| a client/server momwire at ~30 ms | ~12.7 s - indistinguishable from the real engine |

So the client/server shape does not need to be fast in absolute terms; it needs to
get under EZNEC's own per-point overhead, at which point the difference stops being
observable to the operator.

---

# EZNEC capture session — 2026-09-17 (momwire#1099/#1105/#1110)

Load entry forms and wire loss, requested from the laptop session. I/O observation
only. **Captures `0183`–`0199`.** Harness: `scripts/eznec_spy`, shim rebuilt this
session (capture root baked to `scratch/eznec-capture`), installed 13:07 local.
Engine `External NEC-5` throughout, argv-form, exit 0, every launch accounted for.

Host: `EZNEC Pro/2+ v. 7.0.4` as the deck header prints it. AutoEZ 
drove the `.weq` models; EZNEC drove the `.ez` ones.

## What was clicked, in order

| capture | model | what changed | card emitted | probe |
|---|---|---|---|---|
| `0183` | `Dipole1.ez` | bare — smoke test, also the control for `0193` | — | no |
| `0184` | `Dipole1.ez` | Wire Loss = Copper | `LD 5,0,1,11,5.7471E+7,1.` | no |
| `0185` | `OCF Dipole.weq` | Wire Loss = Copper | `LD 5,0,1,271,…` + 4:1 `NT` | no |
| `0186` | `4Square TL Separate Sources.weq` | as-is | `EX 4` ×4 | no |
| `0187` | ″ | sources I → V | `EX 0` ×4 | no |
| `0188` | `4Square TL With Feed System.weq` | as-is | `EX 4`, `TL` ×6 | no |
| `0189` | ″ | source I → V | `EX 0` | no |
| `0190` | `Stepped Dipole 1.weq` | as-is | `LD 5,0,1,33,2.5E+07,1.` | no |
| `0191` | `Stepped Dipole 2.weq` | as-is | same card, wires ordered centre-out | no |
| `0192` | `TFD.weq` | as-is | `LD 0,2,34,0,820.,0.,0.` | **YES** |
| `0193` | `Dipole1.ez` | RLC/Ser, R=18 L=0 C=0, wire 1 seg 8 | `LD 0,1,8,0,18.,0.,0.` | **YES** |
| `0194` | ″ | RLC/Ser, R=0 L=0.1 µH C=5 pF | `LD 0,1,8,0,0.,.0000001,5.E-12` | **YES** |
| `0195` | ″ | RLC/**Par**, same values | `LD 1,1,8,0,0.,.0000001,5.E-12` | **YES** |
| `0196` | ″ | RLC/**Trap**, same values | `LD 4,1,8,0,0.,-243.3432` | **YES** |
| `0197` | ″ | **Ext Con = Par** | `NT 1,8,2,1,0.,-1.217E-2,…` + new virtual wire | no |
| `0198` | `Cardioid L Network Feed ARRL Example.ez` | as-is — R+jX control | `LD 4,1,-1` and `LD 4,2,-1` | no |
| `0199` | ″ | both loads → RLC/Ser, positions untouched | `LD 0,1,-1` and `LD 0,2,-1` | **no** ← counterexample |

`0198` reproduces `0000` (2026-08-16) **byte for byte apart from the timestamp**.

## What the sitting established

**The 1.E-10 V probe is not a Pro/4+ trait.** Pro/2+ writes it (`0192` onward).
The old corpus missed it only because all 149 of its `LD` cards were `LD 4` — the
bundled examples enter every load as an impedance.

**Load type is a property of the MODEL, not of individual loads.** Switching one
load to the RLC window converts them all, so a deck cannot mix entry forms and
either carries probes on all its discrete loads or none. The
`CM ! 1.E-10 volt sources for recording currents at load locations.` header is
therefore a reliable deck-level flag.

**Where NEC has no card for the shape, EZNEC does the algebra and the deck becomes
single-frequency.** Twice: Trap → `LD 4` at −243.3432 Ω (`XL`=188.36, `XC`=106.17,
parallel = −243.4 at 299.7925 MHz), and Ext Con=Par → a one-port `NT` at
−j1.217E-2 S (= 1/(j82.19)). Everything NEC *can* express passes through with only
a type field changing and the payload untouched — `EX 4`/`EX 0`, `LD 0`/`LD 1`.

**A second virtual-wire idiom**, distinct from the feed-system one: comment
`! Wire #2 for shorted/open trans. lines and/or parallel loads.`, parked at 100 m
rather than the 4–8 km of `! *Wire #N for virtual segments.`

**Wire loss** is `LD 5` with EZNEC's own conductivities — copper `5.7471E+7`,
aluminum `2.5E+7`, both off-book — using absolute segment numbering that spans
wires and **excludes virtual wires** (`0185`: 88+3+180 = 271, range `1,271`;
`0192`: 69+69+1+1 = 140, range `1,140`).

**`LD 0`/`LD 1` units are SI base** — ohms, henries, farads. EZNEC mixes decimal
and exponential notation within one card (`.0000001` beside `5.E-12`).

**No stepped-diameter correction card**, correctly: it is a NEC-2 workaround for
unequal-radius junctions, which NEC-5 handles natively. The consequence inverts
into a requirement — a drop-in must handle those junctions itself, because EZNEC
will not pre-correct. `0190`/`0191` are the regression pair.

## The open question

`0199` has `LD 0` and **no probe**. Every probed load so far sits at a numbered
segment (`2,34`, `1,8`); these sit at `-1`, EZNEC's junction addressing, at the
base of each vertical. Either EZNEC will not place an `EX` at a junction, or a
load-data option is simply off for this model — not yet separated, and they are
different answers for the seam.

**Next sitting, in this order** (agreed with the laptop session):

1. **The deciding capture** — the Cardioid with ONE load moved to a mid-wire
   segment (50 % along wire 1), R+jX twin as the control. If a probe appears
   there and not on the wire-2 junction load, the addressing is the rule.
2. **Laplace** — it exists in this edition (`The_Laplace_Loads_Window.htm` is a
   real help topic); expect another computed equivalent, so record the frequency.
3. **Insulated wire** (item 5c).
4. **The 14 bonus AutoEZ workbooks** — pure clicking, new corpus titles.

Item 6 (census of the bundled examples) is closed on titles: all 32 bundled `.ez`
resolve to titles the corpus already holds.

---

# EZNEC capture session — 2026-09-18 (AK#1579, momwire#1116)

The other two writers, and a knot-rule result that came out of checking them.
**No new spy captures** — neither writer produces one, for different reasons.
Decks banked under `scratch/eznec-capture/exports/`.

## The three stamps

Every EZNEC writer emits the same sentence with one token swapped:

| writer | stamp |
|---|---|
| NEC-5 | `! Written by EZNEC/Pro+ v. 7.0 in NEC-5 format.` |
| NEC-4.2 | `! Written by EZNEC/Pro+ v. 7.0 in NEC-4.2 format.` |
| NEC-2 | `! Written by EZNEC/Pro+ v. 7.0 in NEC-2 format.` |

The token is `NEC-4.2`, not `NEC-4`. AK#1579 reads the token off the fixed frame
rather than matching whole strings.

## The same antenna through all three

`Dipole1.ez`; the NEC-5 column is capture `0183`.

| | NEC-5 | NEC-4.2 | NEC-2 |
|---|---|---|---|
| wires | 1 | 1 | **2** (virtual wire added) |
| `GE` | `GE 0,-1` | `GE 0,-1` | **`GE 0`** |
| source | `EX 4,1,6,0` | `EX 6,1,6,0` | `EX 0,2,2,0` + `NT 2,2,1,6` |
| `PQ` | `PQ 0` | `PQ 0` | absent |
| version/date `CM` | yes | yes | **no** |

NEC-4.2 and NEC-5 are otherwise identical — the split is not by NEC version but
by **whether the dialect has a native current source**. NEC-2 doesn't, so EZNEC
synthesizes one from a virtual wire, a *voltage* source on it, and an `NT`
injector with Y12 = j1, and says so itself: `! NT #1 is EZNEC current source`.

**A third virtual-wire comment wording**, completing the census:

| context | comment |
|---|---|
| TL/NT feed systems | `! *Wire #N for virtual segments.` |
| NEC-5 parallel load (`0197`) | `! Wire #2 for shorted/open trans. lines and/or parallel loads.` |
| NEC-2 export | `! Wire #2 for I srcs, shorted/open TL, and/or parallel loads.` |

The NEC-2 form is a superset — it adds `I srcs` and abbreviates `trans. lines`.
`#1577`'s detector is structural and doesn't read these, but the census is worth
keeping.

## How each was obtained — neither is a capture

- **NEC-2 has no external-engine slot** in Pro/2+; it runs on the built-in
  engine, so it can never be captured. `File → Save As` with a `.nec` type writes
  it, and offers **no format choice**. That export also carries the model's
  descriptive `CM` prose, which engine decks strip.
- **NEC-4.2 does take an executable path**, but the shim resolves
  `<name>.real.exe` *before* it starts capturing (`Nec5Spy.cs` line 48 vs 58) and
  returns `9009` when that's missing — and there is no real 4.2 engine here to
  rename. EZNEC launched the shim and no capture directory appeared.

  The deck was recoverable because **the 4.2 slot writes `EZ.NEC` in the
  ENGINE's directory**, not `EZN5.NEC` in `Docs` the way the NEC-5 slot does.
  Worth knowing before anyone spends an hour on it.

## `EX 4` is a knot source — and EZNEC can't hit the centre of an odd wire

Measured directly against `NEC5CL_x13.real.exe`, `Dipole1` re-cut to 10 segments
so the centre *is* a knot, `EX 4` spelled eight ways, nothing else changed.
Reproduced independently on both boxes, every digit:

| spelling | lands on | Z (Ω) |
|---|---|---|
| `5,0` ≡ `5,2` ≡ `-6,0` ≡ `6,1` | knot 5 (the centre) | 77.639 + 27.349j |
| `6,0` ≡ `6,2` ≡ `-5,0` ≡ `4,2` | knots 6 / 4 (mirrors) | 86.047 + 29.035j |

So: **a positive segment with I4 = 0 means that segment's END 2; negative means
end 1.** The printout's third column (`6 1`) is NEC-5's own end index, not I4.

On the 11-segment deck EZNEC actually wrote, every spelling gives `0183`'s
79.948 + 29.919j, because knots 5 and 6 sit symmetrically about the centre —
which is why it looked undecidable from the capture alone.

**The consequence is a fact about EZNEC.** `Dipole1.ez` specifies a source at
50 %. An 11-segment wire has no knot at its centre, so EZNEC writes `EX 4,1,6,0`
— knot 6, **0.5455 of the wire**, half a segment off. On
even segment counts the knot rule lands exactly. **The model says 50 %, the deck
says 54.55 %, on odd counts only.**

Whether that goes to Roy is Steve's call.

### It is not a NEC-5 quirk — it is addressing parity, and it cannot be re-cut away

Re-cutting `Dipole1` to 10 segments and exporting NEC-2 (`Dipole1-10seg-nec2-export.nec`)
was meant to give one model whose NEC-5 and NEC-2 sources sit at the same point.
It does the opposite, and shows why none can. The injector lands on **segment 5
of 10**, whose centre is **0.45** — half a segment off, the mirror of the NEC-5
failure.

For a wire of length L in N segments:

| | positions |
|---|---|
| knots (NEC-5 `EX 4`) | `i·L/N`, i = 1…N−1 — multiples of `L/N` |
| segment centres (NEC-2 source) | `(i−0.5)·L/N`, i = 1…N — **odd** multiples of `L/2N` |

An odd multiple of a half-step is never an integer multiple of a whole step, so
**those sets are disjoint for every N.** A knot source and a segment-centre
source are never co-located, at any position, for any segment count.

At the centre the conditions are complementary: a knot lands on L/2 only when N
is **even**, a segment centre only when N is **odd**. No N satisfies both.

So the model's stated 50 % is honoured exactly **only when the segment count
matches the dialect's addressing parity**.

**EZNEC discloses this — it is not silent.** The Loads and Sources windows carry
two position columns side by side: **`Specified` (Wire # / % From E1)** and
**`Act Pos` (Seg / % From E1)**. The requested percentage and the one the
segmentation actually produced are both on screen, so a user who asks for 50 %
on an 11-segment wire can see 54.55 % in the next column. The deck reflects what
the display already shows.

That reframes the finding and defuses it. It is not "EZNEC drops a model
property on the floor" — it is the ordinary consequence of discretising a
continuous position onto a segmentation, surfaced in the UI. Worth knowing when
reading a deck (the `EX`/`LD` address is the *actual* position, never the
requested one), but not a defect, and not something to raise with Roy. A NEC-5-vs-NEC-2 comparison of one model can therefore never be an
equality case; any residual difference is irreducibly geometric. AK#1579's gate
is the NEC-4.2 deck against the NEC-2 export instead — `EX 6,1,6,0` and the
injector at wire 1 segment 6, both read at 5.5/11 = 0.5, genuinely co-located.

It also means the NEC-5 deck and the NEC-2 export of the same model put the
source in *different physical places* (knot 6 = 0.5455 versus segment 6's centre
= 0.5), so a residual impedance difference between them is expected and is not
evidence about any detector. AK#1579's gate was re-cut onto the NEC-4.2 deck
against the NEC-2 export, which both sit at 0.5.

## The probe rule, settled — and it is neither of my two guesses

Item 1 ran as `0200` / `0201`, and its control is what decided it. Cardioid,
wire 1's load moved to 50 % (segment 15), wire 2's left at the junction:

| | wire 1 load | wire 2 load | probe |
|---|---|---|---|
| `0200` RLC window | `LD 0,1,15` | `LD 0,2,-1` | on `1,15` only |
| `0201` R+jX window | `LD 4,1,15` | `LD 4,2,-1` | on `1,15` only |

So the **entry window is irrelevant to the probe** — an `LD 4` straight from the
R+jX window carries one. That kills the rule the 09-17 section proposed.

"Explicit segment vs junction address" also fits both captures, but it is a
**proxy, not the mechanism**. Roy's own statement (QRZ #98) is the real one:

> A probe is written at a load's location **unless an `EX`, `NT` or `TL`
> already reports current there.**

The captures all turn on that, and the `-1` addresses are incidental — they are
simply where the feed system happens to terminate:

- `0198`/`0199` — loads at `1,-1` and `2,-1`; the deck's `TL 3,1,1,-1` and
  `TL 3,2,2,-1` end at exactly those two points. Both loads are already reported.
  No probes.
- `0200`/`0201` — wire 1's load moves to `1,15`, clear of the `TL` end still at
  `1,-1`, and gains a probe. Wire 2's stays at the `TL` end and does not.
- `0192` — the TFD's load is at `2,34` while its `NT` ends at `1,34`. Different
  *wire*, so nothing reports there, so it gets a probe. That near-miss is why the
  TFD showed the first probe in the corpus.
- `0193`–`0196` — plain dipole, load at `1,8`, source at `1,6`, no `TL`/`NT`
  anywhere. Nothing reports at the load. Probe.
- `0197` — `Ext Con = Par` turns the load into an `NT`, so there is no `LD` to
  probe at all.

**A consumer cannot infer probe presence from card type, entry form, or address
form.** It must read the `EX`/`NT`/`TL` cards and match addresses — which is what
momwire's seam already does.

Corollary worth one capture some day, not on this sitting's list: a load at an
explicit segment that coincides with a `TL` end should get **no** probe. Nothing
in the corpus exercises it yet.

## Laplace — no new card, and the reduction lives in one place

The third Loads window takes a rational function in s, ascending powers to s^5,
numerator over denominator: **Z(s) = (N0 + N1s + N2s^2 + …) / (D0 + D1s + …)**.
Three runs on `Dipole1`, load at wire 1 / 75 % (segment 8), same place as
`0193`–`0196`:

| | cells set | predicted | `LD` written |
|---|---|---|---|
| `0203` | N0 = 18, D0 = 1 | 18 + 0j | `LD 4,1,8,0,18.,0.` |
| `0204` | N1 = 1E-7, D0 = 1 | +188.36j | `LD 4,1,8,0,0.,188.3652` |
| `0205` | N1 = 1E-7, D0 = 1, D2 = 5E-19 | −243.34j | `LD 4,1,8,0,0.,-243.3432` |

**`0205` is byte-identical to `0196`** — the whole deck, not just the card; the
only line that differs is the timestamp, a day apart. `0196` reached that trap
through the **RLC window with Config = Trap**; `0205` reached it through the
**Laplace window** as `sL / (1 + s²LC)`. Two unrelated dialogs, one output.

So the reduction to an equivalent `LD 4` happens **in one place, downstream of
every dialog**, rather than being special-cased per entry form. That is worth
more than the Laplace answer itself: it means a consumer never has to model
EZNEC's dialogs, only the four cards they can produce.

**For lumped loads the vocabulary is `LD 0` / `LD 1` / `LD 4`**: there is no
Laplace card, and anything NEC cannot express is computed at the frequency into
an `LD 4` — or, for a parallel external connection, leaves `LD` entirely and
becomes an `NT` (`0197`). ~~The `LD` vocabulary is closed.~~ **It is not** —
insulated wire adds `LD 2`, below.

Probes on all three, at `1,8`, exactly as the rule predicts.

### The engine selection does not survive `Save As`

All three were saved and calculated in one pass and produced **no captures** —
`LastRun.log` showed `edit load(s)` → `SA` → `Running EZCalcD_70_x64.EXE`. A
model saved under a new name comes up on the **internal** engine even when the
model it was saved *from* was set to External NEC-5. Re-opening each and setting
the engine produced all three immediately.

So the per-model rule in the harness README needs the sharper version: **re-set
the engine after every `Save As`, not only when opening a different model.**

## Insulated wire — `LD 2`, and the `GW` radius is rewritten

`0206`, `Dipole1` with insulation only (Diel C 2.5, Thk 1.0 mm, Loss Tan 0.01),
against `0183` its byte-exact bare twin. The whole diff beyond the timestamp:

```
GW 1,11,…,.0005      ->  GW 1,11,…,9.666E-4
(added)                  LD 2,1,0,0,1.655357,1.3184E-7,0.
```

EZNEC does **two things at once** — modifies the geometry *and* adds a
distributed load. `LD 2` is series R-L-C **per unit length**, addressed as tag 1
with segments `0,0` (the whole wire), which is neither the explicit-segment form
nor the `-1` junction form.

**The model reproduces from closed form to five figures**, using a complex
permittivity ε\* = εr(1 − j·tanδ), with a = 0.0005 (conductor), b = 0.0015
(a + thickness), b/a = 3:

| | expression | computed | deck |
|---|---|---|---|
| radius | a·(b/a)^(1−1/εr) | 9.66591e-4 | `9.666E-4` |
| L′ | (μ₀/2π)·ln(b/a)·Re[1−1/ε\*] | 1.318423e-7 | `1.3184E-7` |
| R′ | ω·(μ₀/2π)·ln(b/a)·Im[1−1/ε\*] | 1.65538 | `1.655357` |

Using **real** εr instead of ε\* gives Im = 0.004 flat and R′ = 1.655522, which
is 0.01 % off. So EZNEC uses the **exact complex form**, not the first-order
approximation — worth knowing if momwire ever reproduces it.

Three consequences:

- **A parser that knows only `LD 0/1/4/5` fails on any insulated model**, and
  insulated wire is common in real models. This is not an exotic corner.
- **The `GW` radius cannot be trusted as the physical conductor.** EZNEC
  silently substitutes the equivalent radius and the original 0.5 mm appears
  nowhere in the deck. Anything round-tripping geometry out of a deck and back
  reports the wrong wire.
- **Partially frequency-specific**: R′ carries ω, the radius and L′ do not.

**No probe**, correctly — `LD 2` is distributed over the whole wire, so there is
no location at which to report a current.

## The AutoEZ workbooks — and a refusal, which is a new category

`0207`–`0218`, twelve of the fourteen. Mostly `TL`/`NT`-rich decks, which the
corpus was thin on: `0215` (W5TX stack) is 21 `GW` and 6 `NT`, the three LPDAs
carry 7 `TL` each, and `0212` (Complete Feed System) puts 4 `NT` on a model whose
title the corpus already held but whose deck is far richer.

**Two were refused outright:**

> Use of split sources is not allowed when using the External NEC-5 engine

— `Diamond Pentaband Quad` and `Vee With Formulas`. That is a **new category**.
Everywhere else, when NEC had no card for something EZNEC computed an
equivalent: the trap became `LD 4`, a parallel load became an `NT`, insulation
became a rewritten radius plus `LD 2`. Split sources are the first feature where
it **refuses instead of reducing**.

So the reduction strategy has a boundary, and the useful consequence is that
**a NEC-5 deck will never contain a split source** — a drop-in need not handle
the case at all. `Split_Source.htm` is a real help topic, so this is a
documented EZNEC feature that simply does not survive the seam. Two of fourteen
bundled AutoEZ samples hit it, so it is not a rarity.

## Insulation + wire loss — the `(a/a′)²` rule is EZNEC's too

`0219`, `Dipole1-insulated.ez` with **Wire Loss = Copper** added and nothing
else changed. Against `0206` (insulation alone) the whole diff is one added
line; against `0184` (copper alone) it is the radius, the conductivity and the
added `LD 2`.

```
GW 1,11,0.,-.25,0.,0.,.25,0.,9.666E-4
LD 5,0,1,11,1.5378E+7,1.
LD 2,1,0,0,1.655357,1.3184E-7,0.
```

**EZNEC scales the conductivity by (a/a′)².** The three predictions were
mutually exclusive and only one survives:

| | value | verdict |
|---|---|---|
| raw, no compensation | 5.7471E+7 | ruled out |
| **(a/a′)²** | **1.53781e7** | **matches the deck's `1.5378E+7`** |
| linear (a/a′) | 2.9729e7 | ruled out |

So AK#1523's rule is not merely AK's own — EZNEC does the same thing, and
AK#1587 can drop the "not EZNEC-verified" caveat.

**The scaling uses the EXACT equivalent radius, not the rounded one in the
deck.** From a′ = 9.665910e-4 the product is 1.53781e7, matching to five
figures; from the `GW` card's own `9.666E-4` it is 1.53778e7, which differs in
the fifth. A consumer recomputing the scaling *from the deck* cannot reproduce
EZNEC's figure exactly, because the radius it would use has already been
rounded. Fine for physics, a trap for byte-comparison.

Why the compensation is needed at all: the `GW` radius is the insulation's
equivalent radius (0.9666 mm), not the physical conductor (0.5 mm), so a
conductivity applied to that cross-section would describe roughly 3.7× too much
metal. The square is the area ratio.

**`LD 5` and `LD 2` coexist on one wire, and they address it differently** —
`LD 5,0,1,11` is tag 0 with an absolute segment span, `LD 2,1,0,0` is tag 1 with
`0,0` for the whole wire. `LD 5` is written **first**. That combination is new to
the corpus and gates independently of the conductivity question.

## Still to run

1. **Insulation + wire loss together** — the one remaining capture that could
   change a rule. `0206` has **no `LD 5`**, so nothing here gates the
   conductivity question: EZNEC rewrote the conductor radius to `9.666E-4`, and
   `LD 5` is a conductivity over a cross-section, so a conductivity written
   against the rewritten radius describes a different amount of metal than the
   physical 0.5 mm wire. Either EZNEC compensates or the loss is silently wrong
   on every insulated lossy wire.

   Run `Dipole1` with the same insulation (2.5 / 1.0 mm / 0.01) **and Wire Loss
   = Copper**. It diffs three ways against `0184` (copper alone) and `0206`
   (insulation alone), which are byte-exact twins with each effect isolated.

   | `LD 5` conductivity | means |
   |---|---|
   | `5.7471E+7` | no compensation — loss wrong on insulated wires |
   | `1.5377E+7` | scaled by (a/a′)² = 0.2676× |
   | `2.9727E+7` | scaled by (a/a′) = 0.5173× |

   AK#1523's `(a/a′)²` rule is **AK's own, not EZNEC-verified** — AK#1587 now
   says so. The deck would also be the first to carry `LD 2` (tag with `0,0`)
   beside `LD 5` (tag 0 with an absolute span) on one wire, which is a parser
   test in its own right.

2. The 14 bonus AutoEZ workbooks — pure clicking, new corpus titles.
3. The AutoEZ `GE` confirmation run — corroboration only; provenance is closed.
2. **One `Save As` of `Dipole1` re-cut to 10 segments** — the one pair with a
   NEC-5 knot source and a NEC-2 injector at the same physical point. Bank it
   beside the other two exports.
3. Laplace, insulated wire, the 14 workbooks.
4. Item 4's confirmation run — AutoEZ Calculate against AutoEZ's own export.
   Corroboration only; the question below is already answered.

## Who writes a one-field `GE` — closed, from files already in the repo

momwire#1116 asked which writer emits a bare `GE 0`. **Two do**, and Mike
WA7ARK's decks are the second:

- **EZNEC's own NEC-2 export** — `Save As` with a `.nec` type (above).
- **AutoEZ**, writing the deck itself. Its decks say so in their first line:
  `CM Created from AutoEZ`, then EZNEC's NEC-5 stamp copied verbatim, then
  `GE 0`, and no version/date line.

**But `Created from AutoEZ` is NOT a discriminator on its own** — it marks the
MODEL's origin and appears on both paths. AK#1577's three fixtures settle it:

| fixture | `Created from AutoEZ` | `CM EZNEC Pro/… v. 7.0.x <date>` | `GE` |
|---|---|---|---|
| `WA7ARK-OCF-LoadOnly.nec` | yes | — | `GE 0` |
| `WA7ARK-OCF-Load-Xfmr-TL.nec` | yes | — | `GE 0` |
| `failEZN5.nec` | yes | **yes** | `GE 0,-1` |

`failEZN5.nec` is AutoEZ building the model and then *driving EZNEC*, which
wrote the deck — so it gets EZNEC's version line and EZNEC's two-field `GE`.
**AutoEZ's own writer is the triple:** `Created from AutoEZ` **and** no version/
date line **and** the bare `GE`. Mike's two files have all three; Dan's has only
the first. Counting on the comment alone over-counts.

## `! NT #N is EZNEC <thing>` — a family, not a one-off

Three members so far, numbered per `NT` card:

| annotation | seen in |
|---|---|
| `! NT #1 is EZNEC current source` | NEC-2 export |
| `! NT #1 is EZNEC lossy transmission line` | `WA7ARK-OCF-Load-Xfmr-TL.nec` |
| `! NT #2 is EZNEC transformer` | same |

Better than the virtual-wire comment for telling what a network *does* — the
wire comment only says a virtual wire exists, these say what each `NT`
implements. Corroboration only; the cards decide. On AK#1577 for the detector's
docstring.

That AutoEZ-written fixture carries both the virtual-wire comment and the `NT`
annotations, so AutoEZ reproduces EZNEC's whole comment idiom, not just the
stamp.

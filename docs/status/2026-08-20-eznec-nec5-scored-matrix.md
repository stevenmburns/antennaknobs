# The EZNEC matrix, scored: NEC-5 dialect statements vs momwire today

Workstream-3 deliverable for momwire#456 (target A of the re-cut): the
successor to the *planned-disposition* EZNEC table in
`2026-08-19-frontend-statement-matrix.md`, promoted to a scored matrix the
way workstream 1 scored the 4nec2 half — measure first, decide second. Two
C0 probe families ran against the licensed oracle before any row was scored;
their results are folded in below. Sources: the 2026-08-16 capture study
(momwire#390/#414), the 2026-08-20 ground-cycle captures (`0043`–`0048`,
antennaknobs#963), momwire's `docs/design/mininec-ground-idiom.md` ("what
workstream 3 inherits"), and the probes recorded here. Courtesy stance
throughout: printed I/O and the Users Manual only; no engine internals.

Scores, per the ws3 framing (the seam is unbuilt, so "today" is what a thin
seam lands on the day it exists):

| score | meaning |
| --- | --- |
| **serve** | momwire has the physics and the semantics today; the seam's work is translation |
| **work-item** | needs identified, buildable work — priced and ordered below |
| **trap** | would be silently wrong (or a hang) unless specifically gated; each trap names its gate |

Weights are **captures containing the statement, out of the 49 captured
launches (15 distinct model titles)** — the 31-capture corpus of the study
plus the fault-injection septet and the ground cycle. The 33 uncaptured
bundled models can still shift the tail weights; request cards are
display-driven, so their counts are lower bounds.

## Verdict

**The blocking physics is gone; what remains is routing, addressing, and
formatting — plus three gated traps.** The 2026-08-16 study's no-go rested
on momwire refusing networks; momwire#482 phase C dissolved that (TL/NT
solve in momwire, nec2 dialect serving). Re-scored today: **every one of the
fourteen mnemonics lands on physics momwire already computes**, with two
genuine work fronts — the bare-`GD` MININEC ground mode (routing, not
physics) and NEC-5's node/favored-wire addressing (the W7EL trap, now a
committed gate) — and one protocol front (the launch-stamp echo and
byte-gated printout renderer, proven feasible by probe V0 below).

## Re-score: the build landed (2026-08-20, same day)

The seam-skeleton arc (momwire#497, PR #499) and the ground-rungs arc
(momwire#504, PR #506) both merged to momwire main the day this matrix was
scored. The measured, as-built ladder — captures served after each unit,
counted by the corpus sweep the suite now pins id by id:

| landed | adds | serve |
| --- | --- | --- |
| #497 (5 units) | shell, parser, byte-gated renderer, rung-1 physics, node-addressed `TL`/`NT` | **20/49** |
| #504 U1 | `GN 0`/`GN 2` Sommerfeld (+ 0011/0030/0033/0034 falling in) | **27/49** |
| #504 U2 | bare-`GD` MININEC mode (+ eleven `GD` feed systems falling in) | **43/49** |
| #504 U3 | mixed `TL`+`NT` table; 19 printouts promoted to full gates | **46/49** |
| #504 U4 | phased multi-`EX 4` drive | **48/49** |

The one refusal left is 0022 — `NE`, by NE's name, until the queued Windows
session captures its gate. 41 of the 48 carry full byte gates (structure
gate: zero diff lines on every one; round-trip byte-exact); the other seven
are the frequency-stepping session whose printouts are unusable (see the
fixture manifest's `withheld_printouts` note — 0036/0038 are landable,
momwire#511).

What the build measured beyond this matrix:

* **Envelopes, family-wide**: |ΔZ| runs 0.055–16.3 Ω, X-dominated, pinned
  per capture at measured + 25 %; elevation cuts agree to ≤ 0.06 dB at every
  printed angle; azimuth lobes to ≤ 0.17 dB (nulls amplify to ~0.7–0.95 dB
  at −30 dB depth — cancellation arithmetic, not phasing error). The printed
  εc cell uses the engine's own constant (εr − j·σ·λ·59.96, pinned across a
  1–299.8 MHz oracle sweep); the negative-σ spelling folds at the door.
* **The `GD` identity is mechanical**: bare-`GD` Z ≡ `GN 1` Z bit-exact
  (same solver constructor call), on contacting and elevated geometry; the
  `GD`/`GN 0` pattern difference is a uniform 1.28 dB level, reproduced to
  0.02 dB. The environment banner lie is reproduced byte for byte and
  nothing parses it back.
* **The virtual-wire hang is gone, not guarded**: momwire#157 was fixed by
  `57a8b22` (Sommerfeld grid r1_max cap); the 4-square geometry with its
  100 λ anchor fills+solves in 0.82 s vs 0.17 s without, port Z unmoved.
  Virtual-wire decks serve as real geometry.
* **The mixed `TL`+`NT` table was observed all along**: capture 0000's
  printout shows the layout (one heading, one sub-table per run of same-kind
  rows) — the rung-1 study missed it to a filename-glob slip on the
  `0000_preexisting-…` directory. Served, byte-gated on 0000/0023/0025; a
  deck that INTERLEAVES `NT` before `TL` (0/49) refuses naming the order.
* **A fourth trap surfaced and is gated**: the elevated-radial captures
  (0033/0034, radials 1.09e-4 λ over `GN 0`) sit 275/188 Ω from the engine
  with the reactance sign flipped — momwire's finite-ground solve at grazing
  height (momwire#510), held by a named divergence gate that fails when
  fixed, forcing a re-measure.
* **Multi-`EX` arithmetic**: `INPUT POWER` = Σ per-card rows; 0031's
  negative-power row (−1.779 Ω, −1.779 W — the element absorbing through
  mutual coupling) rides through sum, efficiency and pattern normalization
  untouched. Five multi-source shapes nothing has printed refuse by name.

The statement tables below keep their measure-phase scores as the record of
what was known before the build; a **[landed]** tag marks every row the two
arcs closed.

## C0 probes, run before scoring

Oracle: the licensed `nec5cl` (linux build, same NEC-5 release as EZNEC's
`NEC5CL_x13.exe`), invoked exactly as EZNEC invokes it — two positional
args, cwd = run dir, printout read, exit status ignored. Probe decks and
raw printouts live in the session scratchpad per the capture protocol; the
facts below are what the printouts say.

### V0 — the two builds are byte-equivalent, so a byte-gate is buildable

Every captured Windows deck (`0043`–`0048`, the W7EL quartet, the
fault-injection base) re-run through the linux build reproduces the captured
`NEC5.OUT` **byte-for-byte** except: the `FILL=`/`RUN TIME` timing lines,
gfortran's `-0.00` where Intel prints `0.00` in pattern TILT columns, and
the `SOMMPD.NEX` cache preamble (`GMPINO:` lines — present/absent/stale by
what the file in cwd held; last-digit noise on one `-999.99` null row's raw
E-magnitude is the only numeric consequence). **Consequence:** the seam's
printout renderer can be byte-gated against the captured Windows printouts,
with those three families normalized — the same discipline the portal's
nec2 dialect uses, available here at full strength.

### Probe family 1 — ground-mode routing (the ws3 inheritance, measured)

`Vert1` (base-fed 10.3 m vertical touching z = 0, 7 MHz) and an elevated
horizontal half-wave, each under every ground card; impedance and 181-point
pattern both read. Captured-comparable cells reproduce `0043`–`0048`
exactly.

| deck | Z (Ω) | pattern | banner |
| --- | --- | --- | --- |
| vertical, `GN 1` | 35.571 − j1.4223 | PEC lobe, horizon max | `PERFECT GROUND` |
| vertical, **bare `GD ε σ`** | **35.571 − j1.4223** — identical to `GN 1` to every digit | **finite-medium**: horizon null, Fresnel shape | `FINITE GROUND.  SOMMERFELD SOLUTION` |
| vertical, `GN 0 ε σ` | 47.789 − j0.78525 | finite-medium, lower still | `FINITE GROUND.  SOMMERFELD SOLUTION` |
| dipole @ λ/4, `GN 1` | 89.933 + j52.053 | PEC | `PERFECT GROUND` |
| dipole @ λ/4, bare `GD` | **89.933 + j52.053** — identical to `GN 1` | finite-medium | same finite banner |
| dipole @ λ/4, `GN 0` | 87.399 + j37.711 | finite-medium | same finite banner |

1. **Routing settled.** In the NEC-5 dialect, bare `GD` = **PEC currents +
   second-medium far field under ordinary `RP 0`** — on contacting and
   elevated geometry alike. Exactly the mode `mininec-ground-idiom.md` said
   ws3 inherits; now measured on both geometry classes. This is the physics
   momwire already computes on the nec2 dialect's `RP 2`/`RP 3` path; the
   build item is a ground *mode* that applies it to plain requests.
2. **The banner lies here too.** `GD` and `GN 0` print byte-identical
   environment sections (banner, ε, σ, εc lines). The only printout tell is
   FILL time (PEC fill ~0.002 s vs Sommerfeld fill ~0.856 s on this model).
   A renderer must reproduce the shared banner; a parser must never use it
   to distinguish the modes.
3. **The trailing `1.,0.` is the ground's complex relative permeability**
   (per the Users Manual; distinct from NEC-2's `GD` cliff fields).
   Measured: varying it moves the far field only — Z is pinned at the PEC
   value throughout — and `0.`/omitted behaves as 1. EZNEC always emits
   `1.,0.`; a seam should accept μr = 1 and refuse a non-unity μr loudly
   (momwire has no magnetic ground).
4. **First integer field: `-1` cancels the `GD` ground** (measured: free
   space results); other integer fields are ignored (`GD 0,7,8,9,…` ≡
   `GD 0,0,0,0,…`). A negative σ sets Im εc directly (measured equivalent
   at the matched value).
5. **Order semantics: the last ground card wins.** `GN 1` then `GD` →
   MININEC mode; `GD` then `GN 1` → perfect; `GD` then `GN 0` → Sommerfeld;
   `GN 0` then `GD` → MININEC; two `GD`s → the second. No NEC-2-style
   merge of `GD` into a `GN` environment exists in this dialect. EZNEC
   emits exactly one ground card per deck, so this is refusal-grammar
   armor, not a hot path.
6. **`GN 2` ≡ `GN 0` to every printed digit** (the NEC-4-compat spelling;
   unemitted by EZNEC).
7. **Refusals speak in the printout.** A node-0 drive on a wire whose end
   is open (`GE 0` + the vertical) fails with a named
   `SORVT1: ERROR - Voltage source specified where there is no basis
   function` line — the engine-side twin of EZNEC's own "sources
   incorrectly placed" pre-validation, which is why EZNEC never emits the
   combination (ground-cycle anomaly 1). Incoherent states EZNEC cannot
   emit (`GE 1` with `GD -1`) produce garbage, not errors — the seam owes
   them nothing beyond its own loud refusal.

### Probe family 2 — the W7EL signed-node triple, verified and committed

The four captured runs of W7EL's `Network Connection Test` script re-run
locally; every impedance reproduces the Windows capture to every printed
digit, and A/B agree while C sits 70 % away on an unmoved geometric point:

| config | cards | Z printed | W7EL published |
| --- | --- | --- | --- |
| A (`0012` RP / `0014` XQ) | `NT 3,-1,4,1` + `NT 3,-1,4,2` | 114.47 + j21.096 | 114.5 + j21.1 |
| B (`0016`) | `NT 2,3,4,1` + `NT 2,3,4,2` | **114.47 + j21.096** | unchanged |
| C (`0017`) | `NT 3,-1,4,1` + `NT 2,3,4,2` | 195.34 − j57.458 | 195.3 − j57.46 |

Committed as **`tests/fixtures/eznec_nec5/`** (decks + Windows printouts +
manifest with the gate semantics): the first ws3 gate, standing before any
seam code exists. The tag in a node-addressed card is the favored wire and
carries physics; a seam that canonicalizes `2,3` ≡ `3,-1` answers A's
impedance for C.

## The scored matrix

### Protocol statements (every launch)

| statement | weight | score | notes |
| --- | --- | --- | --- |
| argv invocation, cwd-relative, stdin unused | 49/49 | work-item **[landed #497]** | trivial: two positional paths |
| exit status unread in both directions | 49/49 | serve (by doing nothing) | exit 0 always; never signal through it |
| `CM` launch-stamp echo at printout top | 49/49 | **work-item, blocking** **[landed #497]** | without it every printout is "written earlier from another calculation" and no message survives |
| refusal = `NEC ERROR` line after the echo | — | work-item **[landed #497]** | the #829 frame, placed where results would be; fault-injection table says it reaches the operator verbatim |
| printout renderer, byte-gated | 49/49 | work-item **[landed — 41 captures byte-gated]** | **feasibility proven by V0**; normalize timing lines, signed zero, `GMPINO` preamble |
| one process per frequency point, whole deck regenerated | every sweep | serve (accept) | nothing batches at this seam; warm-server economics stay a separate #456 item |
| `SOMMPD.NEX` read-only cache in cwd | Sommerfeld decks | serve (accept) | expect present/absent/stale; never depend on writing it back; V0: presence changes preamble lines only |

### Geometry and framing

| statement | weight | score | notes |
| --- | --- | --- | --- |
| `GW` | 49/49 | serve | |
| `GE 1,-1` / `GE 0,-1` | 33 / 16 of 49 | serve | ground flag routing; second field `-1` in all 49 |
| `FR` single-point | 49/49 | serve | |
| `PQ 0` | 49/49 | **work-item** **[landed #497 U4]** | every printout carries a `Wire Charge Densities` block (all 10 byte-gate fixtures; the header is mixed-case — an all-caps grep misses it, which briefly mis-scored this row as inert). The nec2 dialect refuses charge requests today, so this is a real readout: q = −(1/jω)·dI/ds from the solved current, plus the renderer block |
| `EN` | 49/49 | serve | |

### Ground

| statement | weight | score | notes |
| --- | --- | --- | --- |
| `GN -1` free space | 16/49 | serve | |
| `GN 1` perfect | 5/49 | serve | PEC contact is gated momwire physics |
| `GN 0,…,ε,σ` Sommerfeld | 8/49 | serve | pillar 2; the contact envelope (1.2–4.4 Ω lossy-soil) is named, not hidden; `0047`'s printout carries the engine's own contact-interpolation caveat |
| **bare `GD …,ε,σ,μr′,μr″`** | 20/49, 8 models | **work-item; trap if aliased** **[landed #504 U2 — identity gate bit-exact]** | the second-most-common ground in the corpus. Probe family 1 pinned the whole semantics: PEC currents + second-medium far field on plain requests, μr fields far-field-only, `-1` cancels, last-card-wins. Aliasing onto `GN 0` is 34 % wrong in R; aliasing onto `GN 1` is a PEC pattern. Gate: `0043`–`0048` + the probe matrix. Physics exists (the cliff path); the build is a ground mode + routing |
| non-unity μr on `GD` | 0/49 | refuse loudly | EZNEC always emits `1.,0.`; momwire has no magnetic ground |
| `GN 2` alias | 0/49 | serve (alias) **[landed #504 U1]** | measured ≡ `GN 0`; unemitted by EZNEC |

### Excitation, loads, addressing

| statement | weight | score | notes |
| --- | --- | --- | --- |
| `EX 4` current source, single | 47/49 | work-item, tractable **[landed #497 U4]** | EZNEC's universal drive. Portal drives voltage today; `NEC5Engine` already speaks native `EX 4`; single-source current drive is a readout transform |
| `EX 4` multi-source phased | 2/49 | work-item **[landed #504 U4]** | 0/−90/−90/−180 four-square: constrained multi-port current drive; only three drive values corpus-wide |
| `EX 0` voltage | 2/49 | serve | |
| **signed node addressing on `EX`/`LD`/`TL`/`NT`** (`-1`/`+k`, favored-wire tag) | 38/49, 12 models | **trap — gate committed** **[passing since #497 U5]** | the headline trap. `DeckModel.node_gaps` (B-spline families) is the momwire seam object; the favored wire must survive translation. Gate: `tests/fixtures/eznec_nec5/` (this arc); `-1` is the only negative in all 49 captures |
| `LD 4` fixed Z, single-point | 21/49 | serve | the only load type emitted; rides the addressing trap |
| `LD 4` `1.E+10` pins | 21/49 | serve | ordinary loads mechanically |

### Networks

| statement | weight | score | notes |
| --- | --- | --- | --- |
| `TL` (metres pre-resolved; crossed −Z₀; stubs via `1.E+10` shunt) | 19/49 | work-item **[landed #497 U5 + #504 U3]** | **re-priced by momwire#482 phase C**: the network solve is momwire's now, crossed lines and shunt idioms already serve in the nec2 dialect. Remaining work is the NEC-5 addressing (node endpoints, favored wire) — the same trap, same gate |
| `NT` reciprocal Y; junction loads; L-networks | 8/49 | work-item **[landed #497 U5 + #504 U3]** | junction loads arrive as `NT`, so ordinary loaded models need this — but the solve exists today |
| **virtual-wire feed idiom** (100 λ out, λ/10000 radius, driven + pinned + `NT`/`TL` endpoint) | 21/49, 7 models | **trap → hang** **[dissolved — momwire#157 fixed by `57a8b22`; served as real geometry]** | fine under free space/PEC (ordinary wires + pins, cheap fill); under `GN 0` a ~100 λ extent is momwire#157's Sommerfeld-grid shape — a hang, not a wrong answer. antennaknobs#944 covers the app importer; the momwire seam needs its own answer (anchor virtualization or a bounded-extent guard + loud refusal) |

### Requests

| statement | weight | score | notes |
| --- | --- | --- | --- |
| `RP 0` 2-D (`XNDA` 1000) | 24/49 | serve; renderer work **[landed]** | pattern physics exists; the format is the byte-gate's business |
| `RP 0` 3-D (`XNDA` 1001) | 2/49 | serve; renderer work **[landed]** | distinct printout format |
| `XQ 0` | 22/49 | serve | |
| `NE` at defaults | 1/49 | serve\* **[still refused by name — the corpus's one open gate]** | rectangular E, free-space/PEC; over finite ground refuse loudly (#388's near-field row) |

## The priced ladder (cumulative captures served, as planned)

Superseded by the as-built ladder in the re-score section above — kept as
the measure-phase plan the arcs were decomposed from. The planned counts ran
low because each ground rung also unlocked network decks the plan had parked
on rung 5 (nothing refused them once their ground served), and because the
mixed-table refusal's premise dissolved on contact with capture 0000.

Model-level: a capture serves when its worst statement does. The protocol
skeleton (stamp echo, renderer, refusal frame) is rung 0 — nothing serves
without it and it serves nothing alone.

| rung | adds | serve |
| --- | --- | --- |
| 1 | skeleton + node addressing + `EX 4`/`EX 0` + `LD 4` + `GN -1`/`GN 1` + requests | **13/49** (Dipole1, VHF Ground Plane, Vert1-perfect, the Yagi) |
| 2 | + `GN 0` Sommerfeld | **19/49** |
| 3 | + bare-`GD` MININEC mode | **23/49** |
| 4 | + multi-`EX` phased drive | **25/49** |
| 5 | + node-addressed `TL`/`NT` + the virtual-wire answer | **49/49** |

Rung 1 is where the W7EL gate must already pass — `EX 4,tag,-1` node
addressing is in 38 of 49 captures, including the simplest verticals. Rungs
2–4 are cheap relative to their weight (physics exists; routing and drive
transforms). Rung 5 is the deep one, and it is addressing + the hang guard,
not network physics.

Everything here scores serve or work-item **with zero silent rows only
because the three traps are named and gated**: the favored-wire trap (gate
committed this arc), the `GD` aliasing trap (gate = the ground-cycle
captures + probe matrix), and the virtual-wire hang (gate = a bounded-extent
guard until virtualization lands). That is the same bar ws1 met on the
4nec2 side.

## What the probes changed vs the planned-disposition table

* `GD` moved from "refuse-loudly until built" to a fully-specified
  work-item — semantics measured, not inferred, including the μr fields,
  the cancel flag, and last-card-wins.
* `TL`/`NT` moved from "the #456 layering decision" to addressing-only
  work — the layering was decided (networks live in momwire) and phase C
  shipped the solve.
* `PQ 0` moved from "serve (accept)" to a real work-item: every printout
  carries a `Wire Charge Densities` block, and momwire has no charge
  readout today (the nec2 dialect refuses charge requests). Corrected
  2026-08-20 after the first pass mis-graded it inert on an all-caps grep.
* The byte-gated renderer moved from aspiration to proven (V0).
* The seam's refusal grammar gained an engine-side precedent (`SORVT1`
  speaks in the printout, exactly where a drop-in's `NEC ERROR` would).

## Open

*Superseded by the 2026-08-21 re-weight's own "Open" list at the end of this
document; kept as the record of what was open on 2026-08-20.*

* The 33 uncaptured bundled models (checklist `scripts/eznec_spy/README.md`)
  — next Windows session; weights above are lower bounds on the tail. The
  same sitting owes the `NE` gate (un-refuses 0022, the last capture), a
  phased-drive-through-network capture (momwire#511), and the ws5
  launch-protocol answers.
* `NE` beyond defaults, `NH`, radial-screen grounds: never emitted so far.
* momwire#510: the grazing-height Sommerfeld divergence (0033/0034) — the
  seam serves those decks under a named divergence gate until the ground
  model closes the gap.
* momwire#511: land 0036/0038's withheld printouts.
* The build itself: **done** — momwire#497 (skeleton, 5 units) and
  momwire#504 (ground rungs, 4 units), both on momwire main 2026-08-20.

## Re-weighted over the 122-capture corpus (2026-08-21, momwire main @ 5adaae5)

Everything above was weighted out of forty-nine captured launches and scored
against the same forty-nine. Both denominators moved. The Windows sitting of
2026-08-20 clicked every remaining bundled model and the near-field family,
taking the public corpus to **122 captures across 23 distinct model titles**
(antennaknobs PR #970 regenerated `index.json`; two captures from that sitting
are Roy's own model and moved to the private set, which is why the public index
is 122 rather than the sitting's 124). Meanwhile the seam climbed two more
rungs. So the matrix is re-measured here rather than re-remembered.

**The measurement is a command now**: `scripts/eznec_serve_sweep.py` renders
every capture in the index through `momwire.eznec.render` in one interpreter —
122 solves in **13.2 s**, 23 s with the impedance pass — and refuses to report
anything until two anchors reproduce: the original 49 still stand 48/49 with
`0022` refusing by `NE`'s name, and momwire's own 62-capture fixture corpus
stands 55/62 refusing exactly the seven ids its corpus-ladder test names. Every
number in this section is that script's output.

**Engine state, stated honestly.** This is momwire **main @ `5adaae5`**, which
is four commits AHEAD of the `momwire==0.35.1` pin this repo ships — by
momwire#511 (PR #517, the phased drive composing with the network reducer) and
momwire#516 (PR #519, the `NE`/`NH` rungs). Six of the 115 serve only on main —
`0116`/`0117`/`0120`/`0121`, the phased-drive-through-network family PR #517
dissolved the refusal for, and `0109`/`0115`, the two near-field cells PR #519
turned from refusals into answers. A build from the `0.35.1` pin refuses all
six; 115/122 is main's number, not the shipping one.

### The ladder, over the whole corpus

| corpus | served | refused |
| --- | --- | --- |
| the original 49 (`0000`–`0048`) | **48/49** | `0022` |
| momwire's fixture corpus (62, post-#516) | **55/62** | the near-field seven |
| **the public corpus (122)** | **115/122** | **7/122** |

**The seven refusals are the same seven, and the roster did not grow.** Sixty
of the 122 decks (`0049`–`0106`, `0118`, `0119`) had never been swept — they are
outside momwire's fixture corpus entirely — and **all sixty serve**. No new
refusal sentence, and **no crash**: every one of the 122 came back either a
printout or a named `NEC ERROR`, never an exception — which is the seam's whole
contract, since the shell writes both of those at exit 0 and has nothing to say
about a third outcome.

| refusal sentence (verbatim naming clause) | captures |
| --- | --- |
| `NE (near electric field) over a GN 0 finite ground` | `0022`, `0110`, `0112`, `0113` |
| `NE (near electric field) over the bare GD MININEC-type ground` | `0107`, `0108` |
| `NH (near magnetic field) over a GN 0 finite ground` | `0111` |

That is one work front wearing three sentences — the Sommerfeld near-field
evaluator momwire does not have — and it is the only thing this corpus asks for
that the seam cannot answer.

### The statement weights, out of 122

A new table rather than an edit to the old one: the `/49` weights above are the
record of what the first re-score knew, and they were not wrong, they were
narrower. Mnemonic counts come from the index's own `cards` census; the finer
rows (a `GN` is four different grounds, an `EX` is one card or several, an `RP`
is 2-D or 3-D) are read off the deck text by the same sweep.

| statement | 122-corpus | 49-corpus | share moved |
| --- | --- | --- | --- |
| `GW` / `GE` / `FR` / `PQ 0` / `EX` / `EN` | 122/122 | 49/49 | — (every launch) |
| `GE 1,-1` | 92/122 | 33/49 | 67 % → 75 % |
| `GE 0,-1` | 30/122 | 16/49 | 33 % → 25 % |
| `GN` (any) | 72/122 | 29/49 | 59 % → 59 % |
| `GN -1` free space | 30/122 | 16/49 | 33 % → **25 %** |
| `GN 0` Sommerfeld | 32/122 | 8/49 | 16 % → **26 %** |
| `GN 1` perfect | 10/122 | 5/49 | 10 % → 8 % |
| bare `GD` MININEC | 50/122 | 20/49 | 41 % → 41 % |
| `GN 2` alias | 0/122 | 0/49 | still never emitted |
| `EX 4` single | 94/122 | 45/49 | 92 % → **77 %** |
| `EX 4` phased multi-source | 20/122 | 2/49 | 4 % → **16 %** |
| `EX 0` voltage | 8/122 | 2/49 | 4 % → 7 % |
| signed node addressing (`-1` tag) | 86/122 | 38/49 | 78 % → 70 % |
| `LD 4` fixed Z | 41/122 | 21/49 | 43 % → **34 %** |
| `TL` | 47/122 | 19/49 | 39 % → 39 % |
| `NT` | 18/122 | 8/49 | 16 % → 15 % |
| remote anchor wire (> 10 λ out) | 41/122 | 21/49 | 43 % → 34 % |
| `RP 0` 2-D (`XNDA` 1000) | 52/122 | 24/49 | 49 % → 43 % |
| `RP 0` 3-D (`XNDA` 1001) | 7/122 | 2/49 | 4 % → 6 % |
| `XQ 0` | 54/122 | 22/49 | 45 % → 44 % |
| `NE` near electric field | 8/122 | 1/49 | 2 % → **7 %** |
| **`NH` near magnetic field** | **1/122** | 0/49 | the fifteenth mnemonic |

Three movements are worth naming, and none of them is noise:

1. **The phased drive is not a curiosity.** `EX 4` multi-source went from two
   captures to **twenty**, across six models — the 40-m four-square
   (`0031`/`0091`/`0092`/`0116`/`0117`, four cards), the Cardioid
   (`0032`/`0093`/`0094`), the Cardioid L-network (`0120`/`0121`), Field Day
   Special (`0075`–`0078`), N4PC Loop (`0081`–`0084`) and W8JK (`0069`/`0070`).
   The first re-score priced this rung off two captures and called out "only
   three drive values corpus-wide"; the free-space two-element pairs are a whole
   family the 49 had not shown. `#504 U4` built it wide enough anyway.
2. **`GN 0` overtook `GN -1`.** Free space fell from a third of the corpus to a
   quarter while the Sommerfeld ground rose from a sixth to a quarter: the
   bundled models the first corpus under-sampled mostly stand over real ground.
   Pillar 2 carries more of this seam than the 49 suggested.
3. **`NH` exists.** momwire 0.35.0 refused it on the stated premise that EZNEC
   never emits it; capture `0111` falsified that on one radio button in the Near
   Field Analysis dialog, and momwire#513 (PR #514, shipped in 0.35.1) added it
   to the vocabulary. One capture in 122 is a real weight, not a rounding error —
   the corpus is display-driven and a card nobody clicked is not a card nobody
   has.

### What changed since the first re-score

* **momwire#511 (PR #517) — the phased drive composes with the network
  reducer.** No deck in the first 113 captures combined a multi-source drive
  with a `TL` or an `NT`; the two sets were disjoint, so the composition was
  untested by construction. The 2026-08-20 sitting made four such decks exist — four sources
  through a `TL` (`0116`/`0117`) and two sources 90° apart through an L-network
  plus two `TL`s (`0120`/`0121`) — and all four serve. The same issue landed
  `0036`/`0038`'s withheld printouts, which is what makes the frequency-stepping
  session's remaining five (`0037`, `0039`–`0042`) the only captures this sweep
  cannot compare against an engine printout.
* **momwire#516 (PR #519) — the near-field rungs, and they came out a matrix
  rather than a rung.** `NE`/`NH` serve over `GN -1` and `GN 1` and refuse over
  `GN 0` and the bare `GD`. The finding underneath is that **`GD` solves its own
  near field**: `0108` and `0110` are one grid over one medium with only the
  ground mnemonic changed, and their captured tables agree to 4.4 % — including
  the `EY` column a vertical monopole's symmetry forbids and a PEC image makes
  exactly zero. So the MININEC-type ground is not a PEC-currents-plus-image
  shortcut at an observation point the way it is in the far field; the engine
  evaluates the finite half-space there too. momwire's Sommerfeld machinery
  fills a matrix between wire elements and has no evaluator at a point in space,
  and the best image the seam can build is a factor of two low on the captured
  tables, so those six decks refuse by the ground's name rather than answer
  wrong. The refusal roster growing from one to seven is that measurement, not a
  regression: `0022` was refused before this rung and after it, and what changed
  is that the sentence can now name a ground and a number.
* **The protocol grew a byte.** momwire#512 (PR #514): the real engine writes
  **CRLF**, momwire's shell was forcing LF, and EZNEC discards an LF-only
  printout behind the popup "Output file NEC.OUT is present, but was written
  earlier from another calculation" — naming a file that never existed in any
  run. Proven by controlled substitution on the Windows box (a wrapper changing
  nothing but the line endings made EZNEC render this engine's results first
  try; the wrapper is kept at `scripts/eznec_spy/diagnostics/`). The byte-gates
  missed it because they compare the rendering function's *string*, not the
  bytes the shell *writes* — the protocol table's "printout renderer,
  byte-gated" row was true and still let this through, so the shell now has its
  own gate on the written bytes. By the same substitution method, a drop-in
  needs no name impersonation and no speed; it must live in `Docs` and speak
  CRLF.
* **The model checklist is closed.** `scripts/eznec_spy/README.md`'s group A and
  group B are ticked with their capture ids. The "33 uncaptured bundled models"
  open item is retired.

### Serving is not agreeing: the corpus-wide impedance envelope

The sweep also reads back every `ANTENNA INPUT PARAMETERS` impedance and
compares it with the captured printout's, because a ladder counts decks that get
an *answer* and says nothing about whether the answer is right. **140 printed
source rows across 110 captures** (four uncomparable — `0037`/`0039`–`0041`,
the frequency-stepping session's damaged files — and `0042` ships no printout):

| abs(ΔZ) | value |
| --- | --- |
| min | **0.055 Ω** |
| median | **5.469 Ω** |
| max | **4,308.6 Ω** |

The floor is exactly where the first re-score left it. The ceiling is not: the
first re-score quoted a family envelope of 0.055–16.3 Ω, measured over the
twenty single-source captures momwire's gates pin. Over the whole corpus,
**nineteen rows on fifteen captures sit above 16.3 Ω**, in four groups:

| abs(ΔZ) | captures | capture Z | seam Z | reading |
| --- | --- | --- | --- | --- |
| 3,757.8 / 4,308.6 Ω | `0081`–`0084` (N4PC Loop) | 6948 + j3810 / 7298 + j4230 | 8976 + j646 / 9682 + j641 | ~~new — a two-source loop at a ~7–9 kΩ anti-resonance~~ **resolved 2026-08-21: the CAPTURE's mesh** — see the correction below |
| 275.3 Ω | `0033`, `0103`, `0104` (Elevrad1) | 38.791 − j49.583 | 45.325 + j225.59 | momwire#510, unchanged |
| 188.3 Ω | `0034`, `0105`, `0106` (Elevrad2) | 40.730 − j43.452 | 91.615 + j137.87 | momwire#510, unchanged |
| 21.8 Ω | `0067`, `0068` (NBS Yagi) | 14.301 − j17.726 | 12.055 + j3.982 | **new** — above the quoted ceiling |
| 19.5 Ω | `0028`, `0073`, `0074` (Logpertl) | 129.50 − j73.453 | 119.24 − j56.832 | **new**, and `0028` is in the ORIGINAL 49 |

Four things follow, and the fourth is the one worth acting on.

1. **momwire#510's grazing-height divergence now has six captures, not two.**
   `0103`–`0106` are the same two elevated-radial geometries as `0033`/`0034`
   asked for different readouts, and they reproduce 275.3 Ω and 188.3 Ω to the
   digit. Nothing new is wrong; the divergence gate's blast radius tripled.
2. **`0028` says the old envelope was never corpus-wide.** momwire's pin table
   covers twenty single-source captures and tops out at 16.278 Ω on the
   free-space dipole; `0028` was in the first 49 the whole time, sat 19.5 Ω off,
   and was never enveloped because network decks were structure-gated rather
   than impedance-pinned. That is a gap in what was measured, not a regression.
3. **Every one of these is X-dominated in one direction.** The seam's reactance
   is consistently *less negative* than the engine's — `0058` −58.5 → −43.7,
   `0075` −46.0 → −31.1, `0069` −32.3 → −19.9, `0067` −17.7 → +4.0 — which is
   an under-estimated capacitance, not a random spread. That is exactly
   **momwire#518**'s signature: the B-spline family's smooth charge
   representation cannot sharpen the end/junction charge peaks that dominate a
   thin-wire capacitance, adjudicated at 1.9 % against an electrostatic referee
   on a pure-capacitor structure. The corpus's X offsets are now partially
   attributed rather than filed under "formulation difference".
4. **The N4PC Loop is the corpus's worst row and nothing has priced it.** A
   loop fed at an anti-resonance is a parallel LC, where a ~2 % capacitance bias
   becomes a several-kΩ reactance swing — which is the #518 mechanism at its
   most magnified, on a real bundled model, at a feedpoint an operator would
   actually look at. It serves, so no gate catches it. This is the strongest
   argument yet for the end/junction charge enrichment #518 proposes, and the
   sharpest available test case for it.

> **CORRECTION (2026-08-21).** Points 3 and 4 are overturned, in opposite
> directions, by two same-day investigations:
>
> * **momwire#518 is not a solver bias.** The coupled-loop ladder's bs1/bs2
>   models carried a mis-indexed junction list (wire 6 absent); with the
>   geometry fixed, NEC-5, razor, bs1, bs2 and the electrostatic referee all
>   converge to one limit. There is no B-spline capacitance bias to attribute
>   X offsets to; the corpus's X story reverts to "formulation/convergence
>   difference, disclosed". Postmortem on the issue; repro
>   `scratch/qrz-lfa-thread/ladder_geometry_postmortem.py`; guardrail shipped
>   as momwire#522.
> * **The N4PC row is the CAPTURE's mesh, not the seam's error**
>   (`scratch/n4pc-study/`). The deviation is ground-independent (GN 0 and GD
>   agree, exonerating Sommerfeld). At the deck's 16 segs/side the licensed
>   engine's anti-resonance sits ~0.14 MHz (~1 %) high and the ~1.8 kΩ/50 kHz
>   slope turns that into the 3.8–4.3 kΩ above; under ×8 refinement its curve
>   lands on the seam's, which is already converged at the deck's own mesh
>   (seam 9682 + j641 at ×1 → 9723 − j104 at ×8; NEC-5 7298 + j4230 at ×1 →
>   9673 + j677 at ×8). The row prices the capture, not the seam — the second
>   measured case (after the corrected coupled loop) of bs2 out-converging the
>   licensed engine at a deck's native segmentation. No gate should catch it,
>   and no issue is needed; a capture-side re-run at finer mesh would close the
>   row entirely.

### Open

Superseding the list above.

* **The Sommerfeld near-field evaluator** — the one thing this corpus asks for
  that the seam refuses (six `NE` decks and one `NH`, all over `GN 0` or bare
  `GD`). Inventoried in momwire#388's near-field row; no dedicated issue yet.
  Until it exists the refusals are correct and the sentence names the ground.
* **momwire#510** — the grazing-height Sommerfeld divergence (radials at
  1.09e-4 λ), now six captures: `0033`, `0034`, `0103`–`0106`. Held by a named
  divergence gate that fails when fixed.
* ~~**momwire#518** — the B-spline family's ~2 % gap-capacitance bias~~ —
  **overturned and closed 2026-08-21** (ladder geometry artifact; see the
  correction block above). The N4PC row is likewise resolved as capture-side
  under-convergence, not a seam item. The guardrail that makes the artifact's
  class refuse at construction is momwire#522 (shipped).
* **Buried wires — a capability gap the corpus cannot see (found 2026-08-21).**
  The licensed engine serves wires below the interface (probe: monopole +
  radial 15 cm down over `GN 0` → 92.13 − j70.14 Ω); momwire has no
  lower-half-space source anywhere in the tree, and zero of the 122 captures
  bury a wire — EZNEC's samples don't — so no serve rate ever noticed.
  Refuses BY NAME as of momwire#525 (below-plane and in-plane wires both);
  the capability is momwire#524; the release's honest-disclosure list must
  carry it. Method lesson: a deck-driven inventory only sees what the sample
  decks exercise — the manual's capability list is the complement source and
  deserves one deliberate pass.
* **The multi-request echo, latent.** Every capture in this corpus carries one
  request kind per launch — EZNEC regenerates the whole deck per frequency point
  and per display — so a deck asking for two different requests at once has
  never been observed and the printout's echo order for one is unpinned. Nothing
  is wrong today; nothing would catch it if it were.
* **The pin lags the measurement.** This repo ships `momwire==0.35.1`, which
  refuses the six captures named at the top of this section. The next momwire
  release closes the gap and makes 115/122 the shipping number.
* Re-run: `.venv/bin/python scripts/eznec_serve_sweep.py`.

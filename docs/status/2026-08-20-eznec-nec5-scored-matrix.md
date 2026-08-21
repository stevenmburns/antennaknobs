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
